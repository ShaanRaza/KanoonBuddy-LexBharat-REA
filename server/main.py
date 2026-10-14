"""Local copy of the lexbharat.ai API, backed by the Open India Law corpus on LAWSSD.

Run:  ./run.sh   (needs /Volumes/LAWSSD mounted; Qdrant optional for similarity)
Everything outside the legal-data endpoints is stubbed so the saved front end loads.
"""
import os
import re
import threading
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
JUDGMENT_COURTS = os.environ.get("JUDGMENT_COURTS", "supreme-court").split(",")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "legal_corpus_v2")
CITATIONS_DB = ROOT / "data" / "citations.duckdb"
PARALLEL_DB = ROOT / "data" / "parallel.duckdb"

# Short codes the front end uses (BNS, IPC ...) -> act_id in the legislation parquet.
ACT_CODES = {
    "BNS": ("IND_central_20062", "Bharatiya Nyaya Sanhita, 2023"),
    "BNSS": ("IND_central_20099", "Bharatiya Nagarik Suraksha Sanhita, 2023"),
    "BSA": ("IND_central_20063", "Bharatiya Sakshya Adhiniyam, 2023"),
    "IPC": ("IND_REP_659_1860", "Indian Penal Code, 1860"),
    "IEA": ("IND_REP_971_1872", "Indian Evidence Act, 1872"),
    "CPC": ("IND_central_2191", "Code of Civil Procedure, 1908"),
    "NIA": ("IND_central_2189", "Negotiable Instruments Act, 1881"),
}
REPEALED = {"IPC", "IEA"}  # superseded by BNS / BSA
ALIASES = {"EVIDENCE": "IEA", "SAKSHYA": "BSA", "CRPC": "BNSS", "NI": "NIA", "NIACT": "NIA"}

app = FastAPI(title="lawcentral-copy")
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
_ready = {"legislation": False, "cases": False, "citations": False}


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


@app.on_event("startup")
def startup() -> None:
    if not CORPUS.exists():
        print(f"WARNING: corpus not found at {CORPUS} - legal-data endpoints will 503")
        return
    load_legislation()
    build_equivalents()
    load_cases()
    if CITATIONS_DB.exists():
        db.execute(f"ATTACH '{CITATIONS_DB}' AS cg (READ_ONLY)")
        _ready["citations"] = True
    if PARALLEL_DB.exists():  # AIR/SCC -> case map from build_parallel_citations.py
        db.execute(f"ATTACH '{PARALLEL_DB}' AS pc (READ_ONLY)")
        _ready["parallel"] = True
    # cited-by counts, used to rank search hits (empty table if the graph isn't built)
    if _ready["citations"]:
        db.execute("CREATE TABLE cited_counts AS SELECT cited, count(*) AS n FROM cg.edges GROUP BY cited")
    else:
        db.execute("CREATE TABLE cited_counts(cited VARCHAR, n BIGINT)")
    _ready["case_vectors"] = load_case_vectors()
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
        n, status = db.execute(
            "SELECT count(DISTINCT section_number), any_value(act_status) FROM leg WHERE act_id=?",
            [act_id],
        ).fetchone()
        out.append({"code": code, "fullName": name, "actId": act_id, "sectionCount": n,
                    "status": "repealed" if status == "repealed" else "in_force"})
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
    "INDIANEVIDENCEACT": "IEA", "EVIDENCEACT": "IEA", "CODEOFCIVILPROCEDURE": "CPC",
    "CODEOFCRIMINALPROCEDURE": "BNSS", "CRPC": "BNSS",
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
    r = db.execute("SELECT section_number, text FROM leg WHERE act_id=? AND section_number=? "
                   "AND section_type='section' ORDER BY chunk_id LIMIT 1",
                   [ACT_CODES[code][0], num]).fetchone()
    if not r:
        return None
    title, body = split_heading(r[1])
    return _hit(code, r[0], title, body)


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
        cond = " AND ".join("lower(text) LIKE ?" for _ in words)
        res = db.execute(
            f"SELECT act_id, section_number, text FROM leg WHERE section_type='section' AND {cond} "
            "LIMIT 400", [f"%{w}%" for w in words]).fetchall()
        by_id = {v[0]: k for k, v in ACT_CODES.items()}
        scored = []
        for act_id, num, text in res:
            title, body = split_heading(text)
            tl, bl = title.lower(), body.lower()
            score = sum(5 for w in words if w in tl) + sum(min(bl.count(w), 4) for w in words)
            if act_id in (ACT_CODES["IPC"][0], ACT_CODES["IEA"][0]):
                score -= 1  # repealed codes rank just below their replacements
            scored.append((-score, len(body), act_id, num, title, body))
        for _, _, act_id, num, title, body in sorted(scored)[:limit]:
            rows.append(_hit(by_id[act_id], num, title, body))
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
    """Index section headings per code so IPC<->BNS and Evidence Act<->BSA can be paired."""
    for code in _EQ:
        idx: dict = {}
        for num, text in db.execute(
                "SELECT section_number, text FROM leg WHERE act_id=? AND section_type='section'",
                [ACT_CODES[code][0]]).fetchall():
            title, body = split_heading(text)
            if BOLD_HEAD.search(body[:400]):  # only rows with a real heading
                idx.setdefault(_norm_title(title), set()).add(num)
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
    rows = db.execute(
        "SELECT section_number, text, act_status FROM leg WHERE act_id=? AND section_type='section'",
        [act_id]).fetchall()
    secs, proper = {}, set()
    for num, text, _ in rows:
        title, body = split_heading(text)
        is_proper = bool(BOLD_HEAD.search(body[:400]))
        # one section number can span several chunks; keep the row with a real heading
        if num not in secs or (is_proper and num not in proper):
            secs[num] = {"number": num, "label": f"§ {num}", "title": title}
            if is_proper:
                proper.add(num)
    status = rows[0][2] if rows else "in_force"
    return {"act": {"code": code, "fullName": name, "actId": act_id,
                    "status": "repealed" if status == "repealed" else "in_force"},
            "sections": sorted(secs.values(), key=lambda s: section_key(s["number"]))}


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
    """The section itself (no equivalent lookup, so the equivalent can reuse it safely)."""
    need("legislation")
    act_id, name = ACT_CODES[code]
    rows = db.execute(
        "SELECT text, act_status, section_type, chunk_id, source_url FROM leg "
        "WHERE act_id=? AND section_number=? ORDER BY chunk_id", [act_id, section]).fetchall()
    if not rows:
        raise HTTPException(404, f"{code} section {section} not found")
    main = [r for r in rows if r[2] == "section"] or rows
    # lead with the chunk that carries the real heading, then the rest in order
    main.sort(key=lambda r: 0 if BOLD_HEAD.search(split_heading(r[0])[1][:400]) else 1)
    title, _ = split_heading(main[0][0])
    body = "\n\n".join(split_heading(r[0])[1] for r in main)
    return {"actCode": code, "actFullName": name, "number": section,
            "label": f"§ {section}", "title": title, "text": body,
            "status": "repealed" if rows[0][1] == "repealed" else "in_force",
            "sourceUrl": rows[0][4]}


@app.get("/api/statutes/{act}/{section}")
def statute_section(act: str, section: str):
    code = resolve_code(act)
    d = statute_section_plain(code, section)
    return {"section": d, "equivalent": _equivalent_payload(code, d["title"])}


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


def _by_reporter_cite(q: str):
    """Case ids for an AIR/SCC citation, or [] (also if the map is not built)."""
    if not _ready.get("parallel"):
        return []
    key = parse_reporter_cite(q)
    if not key:
        return []
    return [r[0] for r in db.execute("SELECT case_id FROM pc.parallel WHERE cite_key=?", [key]).fetchall()]


def _parallel_cites(case_id: str) -> list[str]:
    if not _ready.get("parallel"):
        return []
    return [re.sub(r"\s+", " ", r[0]).strip() for r in db.execute(
        "SELECT cite_text FROM pc.parallel WHERE case_id=? ORDER BY cite_key", [case_id]).fetchall()]


def _search_cases(q: str, limit: int = 8):
    need("cases")
    q = q.strip()
    if len(q) < 2:
        return []
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
    return [{"docId": r[0], "title": r[1], "docsource": r[2], "publishdate": r[3],
             "citation": r[4], "caseNumber": r[5], "disposition": r[6], "year": r[7]}
            for r in rows]


@app.post("/api/research/v3/search")
async def research_search(request: Request):
    body = await request.json()
    n = int((body.get("filters") or {}).get("maxResults", 8))
    return {"docs": _search_cases(body.get("query", ""), n)}


def _case_row(case_id: str):
    r = db.execute(
        "SELECT case_id, title, court, citation, year, decision_date FROM cases WHERE case_id=?",
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


# --------------------------------------------------------------------------- Nyra (local model)
import sys  # noqa: E402
from server import nyra  # noqa: E402

nyra.register(app, sys.modules[__name__])  # before the catch-all /api/* stubs so it wins


# --------------------------------------------------------------------------- stubs
# Fixture user for the local copy. The front end's route guards require a role, a verified
# contact and a completed onboarding timestamp (no real sign-in happens locally).
USER = {"id": "local-user", "_id": "local-user", "email": "local@example.com", "name": "Local User",
        "role": "advocate", "emailVerified": True, "phoneVerified": True,
        "onboardingCompletedAt": "2026-01-01T00:00:00.000Z", "onboardingComplete": True,
        "subscription": {"status": "active", "plan": "local", "trialEndsAt": None}}


@app.get("/api/health")
def health():
    return {"ok": True, **_ready}


@app.get("/api/me")
def me():
    return USER


@app.get("/api/me/entitlement")
def me_entitlement():
    return {"status": "active", "plan": "local", "trialEndsAt": None, "canUseAI": True,
            "_failOpen": False}


@app.get("/api/subscription/current")
def subscription_current():
    # Fixture: an active plan so the front end's paywall gate stays open locally.
    return {"plan": {"status": "active", "planId": "local", "name": "Local copy",
                     "trialEndsAt": None, "features": {}}}


@app.get("/api/subscription/plans")
def subscription_plans():
    return {"plans": []}


@app.api_route("/api/auth/{rest:path}", methods=["GET", "POST"])
def auth_stub(rest: str):
    return {"accessToken": "local-dev-token", "token": "local-dev-token", "user": USER}


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
@app.get("/{path:path}")
def spa(path: str):
    f = (WEB / path).resolve()
    if path and f.is_file() and WEB in f.parents:
        return FileResponse(f)
    return FileResponse(WEB / "index.html")
