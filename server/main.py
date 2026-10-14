"""Local copy of the lexbharat.ai API, backed by the Open India Law corpus on LAWSSD.

Run:  ./run.sh   (needs /Volumes/LAWSSD mounted; Qdrant optional for similarity)
Everything outside the legal-data endpoints is stubbed so the saved front end loads.
"""
import os
import re
import threading
import time
from pathlib import Path

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse

from server import topic
from server import auth  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
JUDGMENT_COURTS = os.environ.get("JUDGMENT_COURTS", "supreme-court").split(",")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "legal_corpus_v2")
CITATIONS_DB = ROOT / "data" / "citations.duckdb"
PARALLEL_DB = ROOT / "data" / "parallel.duckdb"
HC_DB = ROOT / "data" / "hc_cases.duckdb"

# Short codes the front end uses (BNS, IPC ...) -> act_id in the legislation parquet.
ACT_CODES = {
    "BNS": ("IND_central_20062", "Bharatiya Nyaya Sanhita, 2023"),
    "BNSS": ("IND_central_20099", "Bharatiya Nagarik Suraksha Sanhita, 2023"),
    "BSA": ("IND_central_20063", "Bharatiya Sakshya Adhiniyam, 2023"),
    "IPC": ("IND_REP_659_1860", "Indian Penal Code, 1860"),
    "IEA": ("IND_REP_971_1872", "Indian Evidence Act, 1872"),
    "NIA": ("IND_central_2189", "Negotiable Instruments Act, 1881"),
}
REPEALED = {"IPC", "IEA"}  # superseded by BNS / BSA
ALIASES = {"EVIDENCE": "IEA", "SAKSHYA": "BSA", "NI": "NIA", "NIACT": "NIA"}

app = FastAPI(
    title="LexBharat",
    docs_url=None, redoc_url=None, openapi_url=None,   # no public schema/Swagger UI
    dependencies=[Depends(auth.guard)],                # every route: /api needs a token unless public
)


@app.exception_handler(auth.AuthError)
async def _auth_error(request: Request, exc: auth.AuthError):
    # {"error": ...} is the shape the front end reads; 401 makes it sign the user out
    body = {"error": exc.message}
    if exc.code:
        body["code"] = exc.code
    return JSONResponse(body, status_code=exc.status, headers=exc.headers)


class SecurityHeaders:
    """Pure ASGI middleware (safe for streaming responses): hardening headers + request size cap."""

    _TS = " https://challenges.cloudflare.com" if os.environ.get("TURNSTILE_SITE_KEY") else ""
    CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'" + _TS + "; "
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; "
           "media-src 'self' blob: https:; connect-src 'self'; worker-src 'self' blob:; frame-src " + (_TS.strip() or "'none'") + "; "
           "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'")
    MAX_BODY = 1_000_000

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for k, v in scope.get("headers", []):
            if k == b"content-length" and v.isdigit() and int(v) > self.MAX_BODY:
                body = b'{"error":"Request too large"}'
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                return await send({"type": "http.response.body", "body": body})

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                h = msg.setdefault("headers", [])
                extra = {b"x-content-type-options": b"nosniff", b"x-frame-options": b"SAMEORIGIN",
                         b"referrer-policy": b"strict-origin-when-cross-origin",
                         b"permissions-policy": b"camera=(), microphone=(self), geolocation=()",
                         b"content-security-policy": self.CSP.encode(),
                         b"cross-origin-opener-policy": b"same-origin"}
                if auth.env() == "production":
                    extra[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                if scope.get("path", "").startswith("/api/"):
                    extra[b"cache-control"] = b"no-store"  # never cache personal or authenticated API data
                present = {k.lower() for k, _ in h}
                h.extend((k, v) for k, v in extra.items() if k not in present)
            await send(msg)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeaders)
_base = duckdb.connect(":memory:")
_tl = threading.local()


class _DB:
    """One DuckDB cursor per thread. A single shared connection is not safe when the
    front end fires several requests at once (the search screen sends 4 in parallel)."""

    def execute(self, *a, **k):
        c = getattr(_tl, "c", None)
        if c is None:
            c = _tl.c = _base.cursor()
        return c.execute(*a, **k)


db = _DB()
_ready = {"legislation": False, "cases": False, "citations": False, "hc": False}


def _pq(name: str) -> str:
    return str(CORPUS / name)


def load_legislation() -> None:
    ids = ",".join(f"'{v[0]}'" for v in ACT_CODES.values())
    db.execute(
        f"""CREATE TABLE leg AS
        SELECT act_id, chunk_id, title, chapter, section_number, section_type, act_status,
               in_force, text, source_url
        FROM read_parquet('{_pq("in_central_legislation.parquet")}')
        WHERE act_id IN ({ids}) AND section_number IS NOT NULL AND section_number <> ''"""
    )
    _ready["legislation"] = True


CLEAN: dict = {}        # (code, section number) -> verified section
UNAVAILABLE: dict = {}  # code -> section numbers in the data that have no verified text


_FIRST_NUMBERED = re.compile(r"\*\*\s*(\d+[A-Za-z]*)\s*[\.\)]")


def _opens_with_number(body: str, num: str) -> bool:
    """True if the first numbered heading in the text is this section's own number.

    A chapter heading may come first (the first section of a chapter), but a different number coming
    first means the row belongs to another provision (a schedule rule, an amendment, a stray fragment).
    """
    m = _FIRST_NUMBERED.search(body[:500])
    return bool(m) and m.group(1).upper() == num.upper()


def build_clean_sections() -> None:
    """Keep only sections whose text we can vouch for.

    The corpus holds several rows per section number (duplicates, schedule rules, amendments). For each
    section we take its canonical rows (chunk id `..._sNNN` plus its own `_pN` parts) and require the text
    to open with the section's own number. Anything else is treated as unavailable rather than guessed at.
    """
    CLEAN.clear(); UNAVAILABLE.clear()
    code_by_id = {v[0]: k for k, v in ACT_CODES.items()}
    groups, allnums = {}, {}
    for act_id, num, cid, text, status, url in db.execute(
            "SELECT act_id, section_number, chunk_id, text, act_status, source_url FROM leg WHERE section_type='section'").fetchall():
        code = code_by_id.get(act_id)
        if not code:
            continue
        allnums.setdefault(code, set()).add(num)
        m = re.search(r"_s0*" + re.escape(num) + r"(?:_p(\d+))?$", cid, re.I)
        if m:
            groups.setdefault((code, num), []).append((int(m.group(1)) if m.group(1) is not None else -1, text, status, url))
    for (code, num), parts in groups.items():
        parts.sort(key=lambda p: p[0])
        title, first = split_heading(parts[0][1])
        if not _opens_with_number(first, num):
            continue
        CLEAN[(code, num)] = {"title": title, "text": "\n\n".join(split_heading(p[1])[1] for p in parts),
                              "status": "repealed" if parts[0][2] == "repealed" else "in_force", "sourceUrl": parts[0][3]}
    for code, nums in allnums.items():
        UNAVAILABLE[code] = sorted((n for n in nums if (code, n) not in CLEAN), key=section_key)


def load_cases() -> None:
    """One row per case from the judgment files (metadata only, no full text)."""
    parts = []
    for c in JUDGMENT_COURTS:
        f = _pq(f"in_{c}_judgments.parquet")
        if os.path.exists(f):
            parts.append(
                f"""SELECT case_id, any_value(title) title, any_value(court) court,
                    any_value(petitioner) petitioner, any_value(respondent) respondent,
                    any_value(citation) citation, any_value(case_number) case_number,
                    any_value(decision_date) decision_date, any_value(disposition) disposition,
                    any_value(year) AS "year", any_value(source_url) AS source_url
                    FROM read_parquet('{f}') GROUP BY case_id"""
            )
    if parts:
        db.execute("CREATE TABLE cases AS " + " UNION ALL ".join(parts))
        _ready["cases"] = True


def _housekeeping() -> None:
    """Every day: finish account deletions whose grace period is over and drop chats past retention."""
    import logging
    while True:
        try:
            for uid in auth.due_for_deletion():
                nyra.delete_user(uid)
                editor.delete_user(uid)
                auth.erase_user(uid)
                logging.getLogger("lexbharat").info("erased an account whose deletion grace period ended")
            nyra.purge_old()
        except Exception:
            logging.getLogger("lexbharat").exception("housekeeping failed")
        time.sleep(24 * 3600)


@app.on_event("startup")
def startup() -> None:
    auth.init()  # raises if LEXBHARAT_SECRET is missing in production
    if not CORPUS.exists():
        print(f"WARNING: corpus not found at {CORPUS} - legal-data endpoints will 503")
        return
    load_legislation()
    build_clean_sections()
    build_equivalents()
    load_cases()
    if CITATIONS_DB.exists():
        db.execute(f"ATTACH '{CITATIONS_DB}' AS cg (READ_ONLY)")
        _ready["citations"] = True
    if PARALLEL_DB.exists():  # AIR/SCC -> case map from build_parallel_citations.py
        db.execute(f"ATTACH '{PARALLEL_DB}' AS pc (READ_ONLY)")
        _ready["parallel"] = True
    if HC_DB.exists():  # High Court case index from build_hc_index.py (metadata only)
        db.execute(f"ATTACH '{HC_DB}' AS hc (READ_ONLY)")
        _ready["hc"] = True
    # cited-by counts, used to rank search hits (empty table if the graph isn't built)
    if _ready["citations"]:
        db.execute("CREATE TABLE cited_counts AS SELECT cited, count(*) AS n FROM cg.edges GROUP BY cited")
    else:
        db.execute("CREATE TABLE cited_counts(cited VARCHAR, n BIGINT)")
    _ready["case_vectors"] = load_case_vectors()
    threading.Thread(target=_housekeeping, daemon=True).start()
    print("ready:", _ready)


def need(kind: str) -> None:
    if not _ready[kind]:
        raise HTTPException(503, f"{kind} data not loaded (is LAWSSD mounted?)")


def resolve_code(code: str) -> str:
    c = re.sub(r"[^A-Za-z]", "", code).upper()
    c = ALIASES.get(c, c)
    if c not in ACT_CODES:
        raise HTTPException(404, f"unknown act '{code}'")
    return c


HEAD = re.compile(r"Section\s+([0-9A-Za-z.\-]+):\s*([^\n]*)")


def split_heading(text: str) -> tuple[str, str]:
    """Rows start with an 'Act: ... | Section N: Title' header; return (title, body)."""
    body = (text.split("\n\n", 1)[1] if "\n\n" in text else text).strip()
    # Best source: the bold heading in the body, e.g. "**103. Punishment for murder.—**"
    b = BOLD_HEAD.search(body[:400])
    if b:
        return _clean_title(b.group(1)), body
    m = HEAD.search(text[:600])
    return _clean_title(m.group(2)) if m else "", body


BOLD_HEAD = re.compile(r"\*\*\s*\d+[A-Za-z]*\.\s*([^*]{2,160}?)\s*\.?\s*(?:[—–-]+\s*)?\*\*")


def _clean_title(t: str) -> str:
    t = re.sub(r"[*_]+", "", t)
    t = re.split(r"\s[—–]\s|\.\s*[—–]", t)[0]
    t = t.strip(" .—–-")
    return t[:120]


def section_key(n: str):
    m = re.match(r"(\d+)(.*)", n)
    return (int(m.group(1)), m.group(2)) if m else (10**9, n)


# --------------------------------------------------------------------------- statutes
@app.get("/api/statutes")
def statutes_list():
    need("legislation")
    out = []
    for code, (act_id, name) in ACT_CODES.items():
        n = sum(1 for (c, _) in CLEAN if c == code)
        out.append({"code": code, "fullName": name, "actId": act_id, "sectionCount": n,
                    "unavailableCount": len(UNAVAILABLE.get(code, [])),
                    "status": "repealed" if code in REPEALED else "in_force"})
    return {"acts": out}


# plain-language terms -> wording the statutes actually use
SYNONYMS = {
    "cheque bounce": "dishonour of cheque", "bounced cheque": "dishonour of cheque",
    "cheque dishonour": "dishonour of cheque", "murder": "murder", "rape": "rape",
    "defamation": "defamation", "cheating": "cheating", "theft": "theft", "bail": "bail",
    "anticipatory bail": "bail apprehending arrest", "advance bail": "bail apprehending arrest",
}
ACT_WORDS = {  # spelled-out act names -> short code
    "NEGOTIABLEINSTRUMENTSACT": "NIA", "NIACT": "NIA", "NI": "NIA",
    "INDIANPENALCODE": "IPC", "BHARATIYANYAYASANHITA": "BNS",
    "BHARATIYANAGARIKSURAKSHASANHITA": "BNSS", "BHARATIYASAKSHYAADHINIYAM": "BSA",
    "INDIANEVIDENCEACT": "IEA", "EVIDENCEACT": "IEA",
}


def _act_from_text(t: str):
    c = re.sub(r"[^A-Za-z]", "", t).upper()
    c = c.removeprefix("THE")
    if c in ACT_CODES:
        return c
    return ACT_WORDS.get(c) or ALIASES.get(c)


_SEC_FIRST = re.compile(r"(?i)^\s*(?:section|sec\.?|s\.?)\s*(\d+[A-Za-z]*)\s*(?:of\s+)?(?:the\s+)?(.+?)\s*$")
_ACT_FIRST = re.compile(r"(?i)^\s*(.+?)\s+(?:section\s+|sec\.?\s*|s\.?\s*)?(\d+[A-Za-z]*)\s*$")


def _section_hit(code: str, num: str):
    d = CLEAN.get((code, num))
    return _hit(code, num, d["title"], d["text"]) if d else None


@app.get("/api/statutes/search")
def statutes_search(q: str = "", limit: int = 20):
    need("legislation")
    q = q.strip()
    if len(q) < 2:
        return {"results": []}
    rows = []
    # 1) explicit section lookups: "IPC 302", "S.138 NI Act", "section 103 of BNS", "103 bns"
    pairs = []
    m = _SEC_FIRST.match(q)
    if m:
        pairs.append((m.group(1), m.group(2)))
    m = _ACT_FIRST.match(q)
    if m:
        pairs.append((m.group(2), m.group(1)))
    m = re.match(r"(?i)^\s*(\d+[A-Za-z]*)\s+(?:of\s+)?(?:the\s+)?([A-Za-z .]+?)\s*$", q)  # "103 bns"
    if m:
        pairs.append((m.group(1), m.group(2)))
    for num, act_text in pairs:
        code = _act_from_text(act_text)
        if code:
            h = _section_hit(code, num)
            if h:
                rows.append(h)
    # 2) bare number: "302" -> that section in every act
    if re.fullmatch(r"\d+[A-Za-z]*", q):
        rows += [h for h in (_section_hit(c, q) for c in ACT_CODES) if h]
    # 3) keywords: every word must appear (synonyms mapped to statute wording)
    ql = SYNONYMS.get(q.lower(), q.lower())
    words = [w for w in re.findall(r"[a-z0-9]+", ql) if len(w) >= 3 or w.isdigit()]
    if words and not rows:
        scored = []
        for (code, num), d in CLEAN.items():
            tl, bl = d["title"].lower(), d["text"].lower()
            if not all(w in tl or w in bl for w in words):
                continue
            score = sum(5 for w in words if w in tl) + sum(min(bl.count(w), 4) for w in words)
            if code in REPEALED:
                score -= 1  # repealed codes rank just below their replacements
            scored.append((-score, len(bl), code, num, d))
        for _, _, code, num, d in sorted(scored, key=lambda x: (x[0], x[1]))[:limit]:
            rows.append(_hit(code, num, d["title"], d["text"]))
    seen, uniq = set(), []
    for r in rows:
        k = (r["actCode"], r["number"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return {"results": uniq[:limit]}


_EQ = {"IPC": "BNS", "BNS": "IPC", "IEA": "BSA", "BSA": "IEA"}
_title_idx: dict = {}


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def build_equivalents() -> None:
    """Index verified section headings per code so IPC<->BNS and Evidence Act<->BSA can be paired."""
    for code in _EQ:
        idx: dict = {}
        for (c, num), d in CLEAN.items():
            if c == code:
                idx.setdefault(_norm_title(d["title"]), set()).add(num)
        _title_idx[code] = idx


def equivalent_section(code: str, title: str):
    """Likely counterpart in the new/old code: only when the heading is unique on both sides."""
    other = _EQ.get(code)
    nt = _norm_title(title)
    if not other or not nt:
        return None
    mine, theirs = _title_idx.get(code, {}).get(nt, set()), _title_idx.get(other, {}).get(nt, set())
    if len(mine) == 1 and len(theirs) == 1:
        return other, next(iter(theirs))
    return None


def _hit(code, num, title, body):
    return {"actCode": code, "actFullName": ACT_CODES[code][1], "number": num,
            "label": f"§ {num}", "title": title, "snippet": body[:240],
            "repealed": code in REPEALED}


@app.get("/api/statutes/cases")
def statutes_cases(q: str = "", limit: int = 20):
    return {"cases": _search_cases(q, limit)}


@app.get("/api/statutes/{act}")
def statute_act(act: str):
    need("legislation")
    code = resolve_code(act)
    act_id, name = ACT_CODES[code]
    secs = [{"number": num, "label": f"§ {num}", "title": d["title"]}
            for (c, num), d in CLEAN.items() if c == code]
    return {"act": {"code": code, "fullName": name, "actId": act_id,
                    "status": "repealed" if code in REPEALED else "in_force",
                    "unavailableSections": UNAVAILABLE.get(code, [])},
            "sections": sorted(secs, key=lambda x: section_key(x["number"]))}


def _equivalent_payload(code: str, title: str):
    eq = equivalent_section(code, title)
    if not eq:
        return None
    ocode, onum = eq
    try:
        o = statute_section_plain(ocode, onum)
    except Exception:
        return None
    return {"actCode": ocode, "actFullName": ACT_CODES[ocode][1], "number": onum, "label": f"§ {onum}",
            "title": o["title"], "text": o["text"], "status": o["status"], "basis": "same section heading"}


def statute_section_plain(code: str, section: str) -> dict:
    """A verified section (no equivalent lookup, so the equivalent can reuse it safely)."""
    need("legislation")
    d = CLEAN.get((code, section))
    if d is None:
        if section in UNAVAILABLE.get(code, []):
            raise HTTPException(404, f"The text of {code} section {section} isn't reliably available in this library.")
        raise HTTPException(404, f"{code} section {section} not found")
    return {"actCode": code, "actFullName": ACT_CODES[code][1], "number": section, "label": f"§ {section}",
            "title": d["title"], "text": d["text"], "status": d["status"], "sourceUrl": d["sourceUrl"]}


def _display_text(t: str) -> str:
    """The stored text is markdown; the section screen shows plain text."""
    t = re.sub(r"(?m)^#{1,6}\s*", "", t)
    t = t.replace("**", "")
    t = re.sub(r"(?<![\w])_([^_\n]+?)_(?![\w])", r"\1", t)
    return re.sub(r"[ \t]+([.,;:)])", r"\1", re.sub(r"\(\s+", "(", t))


@app.get("/api/statutes/{act}/{section}")
def statute_section(act: str, section: str):
    code = resolve_code(act)
    d = dict(statute_section_plain(code, section))
    d["text"] = _display_text(d["text"])
    # interpretedBy: the section screen requires the list; judgments that interpret a section are not indexed yet
    return {"section": d, "equivalent": _equivalent_payload(code, d["title"]), "interpretedBy": [], "interpretedByTotal": 0}


# --------------------------------------------------------------------------- cases
_AIR_Q = re.compile(r"(?i)(?:A\.?\s?I\.?\s?R\.?\s*\(?(\d{4})\)?\s*S\.?\s?C\.?\s*(\d{1,4})|(\d{4})\s*A\.?\s?I\.?\s?R\.?\s*(?:\(?S\.?\s?C\.?\)?\s*)?(\d{1,4}))")
_SCC_Q = re.compile(
    r"(?i)(?:\(?(\d{4})\)?\s*\(?(\d{1,3})\)?\s*S\.?\s?C\.?\s?C\.?\s*(\d{1,4})"   # (1979) 2 SCC 529 / 1979 (2) SCC 529
    r"|(\d{4})\s*S\.?\s?C\.?\s?C\.?\s*\(?(\d{1,3})\)?\s*(\d{1,4}))")                # 1979 SCC (2) 529


def parse_reporter_cite(q: str):
    """Turn a pasted AIR / SCC citation into the keys used by data/parallel.duckdb."""
    m = _SCC_Q.search(q)
    if m:
        y, v, p = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        return f"SCC|{y}|{int(v)}|{int(p)}"
    m = _AIR_Q.search(q)
    if m:
        y, p = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        return f"AIR|{y}|{int(p)}"
    return None


SCR_RX = re.compile(r"(?i)\[?\(?(\d{4})\)?\]?\s*(\d+)\s*S\.?\s?C\.?\s?R\.?\s*(\d+)")


def _by_scr_cite(q: str):
    """Supreme Court Reports citations such as "[1978] 2 S.C.R. 621", matched on the stored citation text."""
    mt = SCR_RX.search(q)
    if not mt:
        return []
    key = f"{mt.group(1)}{mt.group(2)}scr{mt.group(3)}"
    return [r[0] for r in db.execute(
        "SELECT case_id FROM cases WHERE regexp_replace(lower(coalesce(citation,'')),'[^a-z0-9]','','g') = ?", [key]).fetchall()]


def _by_reporter_cite(q: str):
    """Case ids for an AIR/SCC citation, or [] (also if the map is not built)."""
    if not _ready.get("parallel"):
        return []
    key = parse_reporter_cite(q)
    if not key:
        return _by_scr_cite(q)
    return [r[0] for r in db.execute("SELECT case_id FROM pc.parallel WHERE cite_key=?", [key]).fetchall()]


def _parallel_cites(case_id: str) -> list[str]:
    if not _ready.get("parallel"):
        return []
    return [re.sub(r"\s+", " ", r[0]).strip() for r in db.execute(
        "SELECT cite_text FROM pc.parallel WHERE case_id=? ORDER BY cite_key", [case_id]).fetchall()]


VS_RX = re.compile(r"(?i)\s+(?:v\.?|vs\.?|versus)\s+")


def _parties(ql: str):
    """'A v. B' -> ('a', 'b'); anything else -> None."""
    parts = [x.strip(" .,") for x in VS_RX.split(ql) if x.strip(" .,")]
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _search_cases(q: str, limit: int = 8, topic_ok: bool = True):
    need("cases")
    q = q.strip()
    if len(q) < 2:
        return []
    pp = _parties(q.lower())
    if pp:   # "Arnesh Kumar v. State of Bihar": both names must be in the title, whatever "v."/"versus"/"Vs" it uses
        rows = db.execute(
            """SELECT c.case_id, c.title, c.court, c.decision_date, c.citation, c.case_number, c.disposition, c.year
               FROM cases c LEFT JOIN cited_counts n ON n.cited = c.case_id
               WHERE lower(c.title) LIKE ? AND lower(c.title) LIKE ?
               ORDER BY coalesce(n.n, 0) DESC, c.year DESC NULLS LAST LIMIT ?""",
            [f"%{pp[0]}%", f"%{pp[1]}%", limit]).fetchall()
        if not rows and len(pp[0]) >= 6:   # titles are OCR text ("STA TE OF PUNJAB"): fall back to the first party alone
            rows = db.execute(
                """SELECT c.case_id, c.title, c.court, c.decision_date, c.citation, c.case_number, c.disposition, c.year
                   FROM cases c LEFT JOIN cited_counts n ON n.cited = c.case_id
                   WHERE lower(c.title) LIKE ? ORDER BY coalesce(n.n, 0) DESC, c.year DESC NULLS LAST LIMIT ?""",
                [f"%{pp[0]}%", min(limit, 3)]).fetchall()
        out = [{"docId": r[0], "title": r[1], "docsource": r[2], "publishdate": r[3], "citation": r[4],
                "caseNumber": r[5], "disposition": r[6], "year": r[7]} for r in rows]
        if len(out) < limit and _ready.get("hc"):
            out += _search_hc(q.lower(), limit - len(out))
        return out
    ids = _by_reporter_cite(q)  # "AIR 1979 SC 798", "(1979) 2 SCC 529" ...
    if ids:
        rows = db.execute(
            "SELECT case_id, title, court, decision_date, citation, case_number, disposition, year "
            "FROM cases WHERE case_id IN (" + ",".join("?" * len(ids)) + ")", ids).fetchall()
        return [{"docId": r[0], "title": r[1], "docsource": r[2], "publishdate": r[3],
                 "citation": r[4], "caseNumber": r[5], "disposition": r[6], "year": r[7]}
                for r in rows]
    ql = q.lower()
    like = f"%{ql}%"
    # Rank: exact citation, then phrase in the title, then in a party name, then
    # citation/case-number substring; ties go to the more-cited case, then the newer one.
    rows = db.execute(
        """SELECT c.case_id, c.title, c.court, c.decision_date, c.citation, c.case_number,
                  c.disposition, c.year
           FROM cases c LEFT JOIN cited_counts n ON n.cited = c.case_id
           WHERE lower(coalesce(c.title,'')) LIKE ? OR lower(coalesce(c.petitioner,'')) LIKE ?
              OR lower(coalesce(c.respondent,'')) LIKE ? OR lower(coalesce(c.citation,'')) LIKE ?
              OR lower(coalesce(c.case_number,'')) LIKE ?
           ORDER BY CASE WHEN lower(coalesce(c.citation,'')) = ? THEN 0
                         WHEN lower(coalesce(c.title,'')) LIKE ? THEN 1
                         WHEN lower(coalesce(c.petitioner,'')) LIKE ?
                           OR lower(coalesce(c.respondent,'')) LIKE ? THEN 2
                         ELSE 3 END,
                    coalesce(n.n, 0) DESC, c.year DESC NULLS LAST
           LIMIT ?""", [like] * 5 + [ql, like, like, like, limit]).fetchall()
    out = [{"docId": r[0], "title": r[1], "docsource": r[2], "publishdate": r[3],
            "citation": r[4], "caseNumber": r[5], "disposition": r[6], "year": r[7]}
           for r in rows]
    if topic_ok and len(out) < limit and topic.available() and len(topic.terms(q)) >= 1 and not re.search(r"\d{3,}", q):
        # topic words ("anticipatory bail"): Supreme Court judgments whose text discusses it
        seen = {d["docId"] for d in out}
        for r in topic.search(q, limit, cite_count=_cited_by_count):
            if r["case_id"] in seen or len(out) >= limit:
                continue
            row = db.execute("SELECT case_id, title, court, decision_date, citation, case_number, disposition, year FROM cases WHERE case_id=?",
                             [r["case_id"]]).fetchone()
            if row:
                out.append({"docId": row[0], "title": row[1], "docsource": row[2], "publishdate": row[3], "citation": row[4],
                            "caseNumber": row[5], "disposition": row[6], "year": row[7], "matchedPassages": r["hits"]})
    if len(out) < limit and _ready.get("hc"):
        out += _search_hc(ql, limit - len(out))
    return out


CASE_TYPE_TITLE = r"^[A-Z][A-Z .()/&-]*[ ][0-9]+ of [0-9]{4}$"   # "ANTICIPATORY BAIL 1 of 2025": a docket label, no parties


def _search_hc(ql: str, limit: int):
    """High Court judgments by party name / case number (title text). Newest first."""
    pp = _parties(ql)
    order = ""
    if pp:
        where, args = "lower(title) LIKE ? AND lower(title) LIKE ?", [f"%{pp[0]}%", f"%{pp[1]}%"]
        order = f"CASE WHEN lower(title) LIKE '% {pp[0].replace(chr(39), '')} %' OR lower(title) LIKE '{pp[0].replace(chr(39), '')} %' THEN 0 ELSE 1 END, "
    elif re.search(r"\d", ql):   # looks like a case number: also look there
        where, args = "lower(title) LIKE ? OR lower(coalesce(case_number,'')) LIKE ?", [f"%{ql}%"] * 2
    else:
        where, args = "lower(title) LIKE ?", [f"%{ql}%"]
    where = f"({where}) AND NOT regexp_matches(title, '{CASE_TYPE_TITLE}')"
    rows = db.execute(
        f"""SELECT case_id, title, court, decision_date, citation, case_number, disposition, year
            FROM hc.hc_cases WHERE {where} ORDER BY {order}year DESC NULLS LAST LIMIT ?""", args + [limit]).fetchall()
    return [{"docId": r[0], "title": r[1], "docsource": r[2], "publishdate": r[3], "citation": r[4] or "",
             "caseNumber": r[5], "disposition": r[6], "year": r[7]} for r in rows]


def _case_file(case_id: str):
    """Parquet file holding a case's text (Supreme Court file, or its High Court's file)."""
    if _ready.get("hc"):
        r = db.execute("SELECT slug FROM hc.hc_cases WHERE case_id=? LIMIT 1", [case_id]).fetchone()
        if r:
            return str(CORPUS / f"in_{r[0]}_judgments.parquet")
    return str(CORPUS / "in_supreme-court_judgments.parquet")


@app.post("/api/research/v3/search")
async def research_search(request: Request):
    body = await request.json()
    n = int((body.get("filters") or {}).get("maxResults", 8))
    return {"docs": _search_cases(body.get("query", ""), n)}


def _case_row(case_id: str):
    r = db.execute(
        "SELECT case_id, title, court, citation, year, decision_date FROM cases WHERE case_id=?",
        [case_id]).fetchone()
    if r is None and _ready.get("hc"):
        r = db.execute("SELECT case_id, title, court, citation, year, decision_date FROM hc.hc_cases WHERE case_id=? LIMIT 1",
                       [case_id]).fetchone()
    return r


def _cited_by_count(case_id: str) -> int:
    if not _ready["citations"]:
        return 0
    return db.execute("SELECT count(*) FROM cg.edges WHERE cited=?", [case_id]).fetchone()[0]


def _node(case_id: str, depth: int, is_root: bool = False):
    r = _case_row(case_id)
    return {"docId": case_id, "title": (r[1] if r else case_id), "court": r[2] if r else None,
            "citation": r[3] if r else None, "year": r[4] if r else None, "depth": depth,
            "isRoot": is_root, "citedByCount": _cited_by_count(case_id)}


@app.get("/api/research/citation-graph/lookup")
def cg_lookup(q: str = "", limit: int = 10):
    need("cases")
    out = []
    for d in _search_cases(q, limit):
        out.append({"docId": d["docId"], "title": d["title"], "matchedCitation": d["citation"],
                    "year": d["year"], "court": d["docsource"],
                    "parallelCitations": _parallel_cites(d["docId"]),
                    "citedByCount": _cited_by_count(d["docId"])})
    return {"results": out}


@app.get("/api/research/citation-graph/graph")
def cg_graph(docId: str = "", citation: str = "", depth: int = 2, direction: str = "both",
             maxCases: int = 50):
    """Breadth-first walk of the citation edges. Edge from=citing case, to=cited case."""
    need("cases")
    if not _ready["citations"]:
        return {"error": "citations_not_built",
                "message": "Run server/build_citations.py to build the citation graph."}
    if not docId and citation:
        r = db.execute("SELECT case_id FROM cases WHERE lower(citation)=lower(?) LIMIT 1",
                       [citation.strip()]).fetchone()
        docId = r[0] if r else ""
    if not docId or not _case_row(docId):
        return {"error": "not_found", "message": "Case not found in the Supreme Court index."}
    depth = max(1, min(depth, 3))
    maxCases = max(5, min(maxCases, 300))
    d = direction.lower().replace("-", "").replace("_", "")
    only_out = d in ("cites", "citing", "outbound", "forward", "out")  # cases this one cites
    only_in = d in ("citedby", "inbound", "backward", "in")           # cases that cite this one
    go_out = not only_in
    go_in = not only_out
    seen = {docId: 0}
    edges, truncated, frontier = {}, False, [docId]
    for level in range(1, depth + 1):
        nxt = []
        for cid in frontier:
            rows = []
            if go_out:
                rows += db.execute("SELECT citing, cited, mentions FROM cg.edges WHERE citing=? "
                                   "ORDER BY mentions DESC LIMIT 60", [cid]).fetchall()
            if go_in:
                rows += db.execute("SELECT citing, cited, mentions FROM cg.edges WHERE cited=? "
                                   "ORDER BY mentions DESC LIMIT 60", [cid]).fetchall()
            for a, b, n in rows:
                other = b if a == cid else a
                if other not in seen:
                    if len(seen) >= maxCases:
                        truncated = True
                        continue
                    seen[other] = level
                    nxt.append(other)
                edges[(a, b)] = n
        frontier = nxt
    # keep only edges whose endpoints both made it in
    edge_list = [{"from": a, "to": b, "treatmentType": "cited", "polarity": "neutral",
                  "confidence": 1.0, "contextSnippet": f"cited {n}x in the judgment"}
                 for (a, b), n in edges.items() if a in seen and b in seen]
    nodes = [_node(c, lvl, c == docId) for c, lvl in seen.items()]
    root = next(n for n in nodes if n["isRoot"])
    return {"root": root, "nodes": nodes, "edges": edge_list,
            "stats": {"cases": len(nodes), "links": len(edge_list), "truncated": truncated}}


# --------------------------------------------------------------------------- more like this
_qdrant = None


def qdrant():
    global _qdrant
    if _qdrant is None:
        from qdrant_client import QdrantClient
        _qdrant = QdrantClient(url=QDRANT_URL, timeout=60)
    return _qdrant


_cv = {"ids": None, "vecs": None, "pos": None}


def load_case_vectors() -> bool:
    """Per-case mean vectors built by build_case_vectors.py (Supreme Court)."""
    f = ROOT / "data" / "case_vectors.npz"
    if not f.exists():
        return False
    import numpy as np
    z = np.load(f, allow_pickle=False)
    _cv["ids"] = z["ids"]
    _cv["vecs"] = z["vecs"].astype("float32")
    _cv["pos"] = {c: i for i, c in enumerate(_cv["ids"])}
    return True


def _similar_local(case_id: str, limit: int):
    import numpy as np
    i = _cv["pos"].get(case_id)
    if i is None:
        return None
    scores = _cv["vecs"] @ _cv["vecs"][i]
    scores[i] = -1.0
    top = np.argpartition(-scores, min(limit, len(scores) - 1))[:limit]
    top = top[np.argsort(-scores[top])]
    docs = []
    for j in top:
        r = _case_row(str(_cv["ids"][j]))
        docs.append({"docId": str(_cv["ids"][j]), "title": r[1] if r else None,
                     "docsource": r[2] if r else None, "citation": r[3] if r else None,
                     "publishdate": r[5] if r else None, "score": round(float(scores[j]), 4)})
    return docs


@app.get("/api/research/similar/{case_id}")
def more_like_this(case_id: str, limit: int = 10, same_court: bool = False):
    """Cases most similar to a given case, from vectors already in the corpus (no embedder).

    Fast path: in-memory per-case vectors (Supreme Court). Fallback: Qdrant recommend, which
    works for any court but takes 30-80 s on this setup (vectors are on disk in a small VM).
    """
    limit = max(1, min(limit, 30))
    if _cv["ids"] is not None:
        docs = _similar_local(case_id, limit)
        if docs is not None:
            return {"caseId": case_id, "docs": docs, "source": "case-vectors"}
    from qdrant_client import models as qm
    try:
        qc = qdrant()
        pts, _ = qc.scroll(
            COLLECTION, scroll_filter=qm.Filter(must=[
                qm.FieldCondition(key="case_id", match=qm.MatchValue(value=case_id))]),
            limit=40, with_payload=["court", "section_priority", "section_type"], with_vectors=False)
    except Exception as e:  # Qdrant down / Colima not started
        raise HTTPException(503, f"Qdrant unavailable ({type(e).__name__}). Start Colima + qdrant.")
    if not pts:
        raise HTTPException(404, f"No vectors stored for case {case_id}")
    # anchor on the substantive chunks (analysis, ratio, conclusion ...) rather than the header
    pts.sort(key=lambda p: (p.payload.get("section_priority") or 0), reverse=True)
    positive = [p.id for p in pts[:5]]
    must = []
    if same_court and pts[0].payload.get("court"):
        must.append(qm.FieldCondition(key="court", match=qm.MatchValue(value=pts[0].payload["court"])))
    res = qc.query_points_groups(
        COLLECTION,
        query=qm.RecommendQuery(recommend=qm.RecommendInput(positive=positive)),
        using="dense", group_by="case_id", group_size=1, limit=max(1, min(limit, 30)),
        query_filter=qm.Filter(must=must, must_not=[
            qm.FieldCondition(key="case_id", match=qm.MatchValue(value=case_id))]),
        with_payload=["case_id", "title", "court", "citation", "decision_date", "year", "petitioner",
                      "respondent", "disposition"])
    docs = []
    for g in res.groups:
        h = g.hits[0]
        pl = h.payload
        docs.append({"docId": pl.get("case_id") or g.id, "title": pl.get("title"),
                     "docsource": pl.get("court"), "publishdate": pl.get("decision_date"),
                     "citation": pl.get("citation"), "disposition": pl.get("disposition"),
                     "score": round(h.score, 4)})
    return {"caseId": case_id, "docs": docs}


# --------------------------------------------------------------------------- KanoonBuddy (local model)
import sys  # noqa: E402
from server import nyra  # noqa: E402

nyra.register(app, sys.modules[__name__])  # before the catch-all /api/* stubs so it wins
from server import editor  # noqa: E402

editor.register(app)


# --------------------------------------------------------------------------- stubs
@app.get("/api/health")
def health():
    return {"ok": True}  # public liveness probe: deliberately reveals nothing else


@app.get("/api/health/status")
def health_status():
    return {"ok": True, **_ready}  # requires a token


@app.get("/api/me")
def me(request: Request):
    return auth.public_user(request.state.user)


@app.post("/api/auth/login")
async def auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise auth.AuthError("Invalid request", 400)
    if not isinstance(body, dict):
        raise auth.AuthError("Invalid request", 400)
    data = auth.login(request, str(body.get("email", "")), str(body.get("password", "")))
    return {"success": True, "data": data}


@app.post("/api/auth/refresh")
def auth_refresh(request: Request):
    return {"success": True, "data": auth.refresh(request)}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    auth.logout(request)
    return {"success": True}


@app.post("/api/auth/change-password")
async def auth_change_password(request: Request):
    body = await request.json()
    auth.change_password(request.state.user, str(body.get("currentPassword", "")), str(body.get("newPassword", "")))
    return {"success": True}


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise auth.AuthError("Invalid request", 400)
    if not isinstance(body, dict):
        raise auth.AuthError("Invalid request", 400)
    return body


@app.get("/api/auth/config")
def auth_config():
    return {"signupEnabled": auth.signup_enabled(), "captchaSiteKey": os.environ.get("TURNSTILE_SITE_KEY") or None,
            "termsVersion": auth.TERMS_VERSION}


@app.post("/api/auth/register")
async def auth_register(request: Request):
    b = await _json_body(request)
    out = auth.register(request, str(b.get("email", "")), str(b.get("password", "")), str(b.get("name", "")),
                        b.get("acceptTerms"), b.get("captchaToken"))
    return {"success": True, **out}


@app.post("/api/auth/verify-email")
async def auth_verify_email(request: Request):
    b = await _json_body(request)
    return {"success": True, **auth.verify_email(request, str(b.get("token", "")))}


@app.post("/api/auth/resend-verification")
async def auth_resend(request: Request):
    b = await _json_body(request)
    return {"success": True, **auth.resend_verification(request, str(b.get("email", "")))}


@app.post("/api/auth/forgot-password")
async def auth_forgot(request: Request):
    b = await _json_body(request)
    return {"success": True, **auth.forgot_password(request, str(b.get("email", "")))}


@app.post("/api/auth/reset-password")
async def auth_reset(request: Request):
    b = await _json_body(request)
    return {"success": True, **auth.reset_password(request, str(b.get("token", "")), str(b.get("newPassword", "")))}


# ---- the account-settings screen: export, profile, scheduled deletion (privacy rights) ----
def _full_export(row) -> dict:
    return {**auth.account_export(row), **nyra.export_user(row["id"]), "editorDocuments": editor.export_user(row["id"])}


@app.get("/api/gdpr/export")
def gdpr_export(request: Request):
    return {"success": True, "data": _full_export(request.state.user)}


@app.get("/api/gdpr/export/portable")
def gdpr_export_portable(request: Request):
    return {"@context": "https://schema.org", "@type": "Dataset", "name": "LexBharat account data", **_full_export(request.state.user)}


@app.get("/api/gdpr/profile")
def gdpr_profile(request: Request):
    return {"success": True, "data": auth._profile_fields(request.state.user)}


@app.put("/api/gdpr/profile")
async def gdpr_profile_update(request: Request):
    return {"success": True, "data": auth.update_profile(request.state.user, await _json_body(request))}


@app.post("/api/gdpr/delete-account")
def gdpr_delete(request: Request):
    return {"success": True, "data": auth.request_deletion(request.state.user)}


@app.post("/api/gdpr/cancel-deletion")
def gdpr_cancel(request: Request):
    auth.cancel_deletion(request.state.user)
    return {"success": True}


@app.get("/api/gdpr/deletion-status")
def gdpr_deletion_status(request: Request):
    return {"success": True, "data": auth.deletion_status(request.state.user)}


@app.api_route("/api/auth/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def auth_unknown(rest: str):
    raise HTTPException(404, "Not found")  # no Google / phone sign-in: never hand out tokens by default


@app.get("/api/me/entitlement")
def me_entitlement():
    return {"status": "active", "plan": "invite", "trialEndsAt": None, "canUseAI": True,
            "_failOpen": False}


@app.get("/api/subscription/current")
def subscription_current():
    # Fixture: an active plan so the front end's paywall gate stays open locally.
    return {"plan": {"status": "active", "planId": "invite", "name": "Invite-only access",
                     "trialEndsAt": None, "features": {}}}


@app.get("/api/subscription/plans")
def subscription_plans():
    return {"plans": []}


EMPTY = {  # shapes seen in the front end for list endpoints
    "teams/current": {"team": None, "role": None},
    "teams/invitations/pending": {"invitations": []},
    "notifications/history": {"notifications": [], "items": [], "total": 0, "unread": 0},
    "agent/sessions": {"sessions": []},
    "feature-flags": {"flags": {}},
}


def _camel(s: str) -> str:
    parts = re.split(r"[-_]", s)
    return parts[0] + "".join(p.title() for p in parts[1:])


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_fallback(rest: str, request: Request):
    """Everything not implemented: an empty success so the UI renders instead of crashing.

    GETs return an empty list under a key named after the endpoint (/api/cases -> {"cases": []})
    plus generic items/data, since the front end destructures e.g. `res.cases`.
    """
    if request.method != "GET":
        return JSONResponse({"ok": True})
    if rest in EMPTY:
        return EMPTY[rest]
    last = [p for p in rest.split("/") if p and not p.startswith(":")][-1] if rest else "items"
    return {"items": [], "data": [], last: [], _camel(last): [], "total": 0}


# --------------------------------------------------------------------------- static SPA
@app.get("/login")
@app.get("/signin")
def signin_page():
    return FileResponse(WEB / "signin.html")


@app.get("/signup")
def signup_page():
    return FileResponse(WEB / "signup.html")


@app.get("/verify")
def verify_page():
    return FileResponse(WEB / "verify.html")


@app.get("/forgot-password")
def forgot_page():
    return FileResponse(WEB / "forgot.html")


@app.get("/reset-password")
def reset_page():
    return FileResponse(WEB / "reset.html")


def _legal_route(slug: str):
    def handler():
        return FileResponse(WEB / "legal" / f"{slug}.html")
    return handler


for _slug in ("terms-conditions", "privacy-policy", "acceptable-use", "refund-policy", "legal-notice", "security", "delete-data"):
    app.add_api_route(f"/{_slug}", _legal_route(_slug), methods=["GET"], include_in_schema=False)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(WEB / "home.html")


def _to_home():
    return RedirectResponse("/", status_code=302)


# Pages of the original product's marketing site that describe features, plans and apps this build does not have.
for _p in ("about", "firms", "mobile", "pricing", "findmylawyer", "findmylawyer/compliance", "findmylawyer/how-it-works",
           "get-demo", "blog", "blog/videos", "docs", "tutorials", "whatsapp", "marketing/activate", "classic", "old",
           "signed-out", "contact", "leads"):
    app.add_api_route(f"/{_p}", _to_home, methods=["GET"], include_in_schema=False)


@app.get("/{path:path}")
def spa(path: str):
    f = (WEB / path).resolve()
    if path and f.is_file() and WEB in f.parents:
        return FileResponse(f)
    return FileResponse(WEB / "index.html")
