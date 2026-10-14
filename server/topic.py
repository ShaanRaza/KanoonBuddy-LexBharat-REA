"""Topic search over Supreme Court judgment text (see build_topic_index.py).

search("anticipatory bail") -> cases whose judgments discuss it, best first, each with its best matching passages.
Ranking: BM25 over passages, the best three passages per case summed, then boosted for cases that later judgments cite.
This is keyword search, not semantic search: it finds the words you type (with stemming), not other ways of saying it.
"""
import math
import os
import re
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TOPIC_DB", ROOT / "data" / "sc_topic.sqlite"))
_local = threading.local()

STOP = set("""a an the of in on at to for and or but if is are was were be been being do does did what whats which who whom whose when
where why how can could should would will shall may might must have has had this that these those with without within about into
over under between than then there their they them you your i me my we our us it its tell explain describe give show find list
please say said says court courts supreme high india indian law legal case cases judgment judgments held hold holds decision
decisions ruling rulings precedent precedents section sections act under whether any some many much more most such also very just
like want need know latest recent""".split())


def available() -> bool:
    return DB_PATH.exists()


def _conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        _local.c = c
    return c


def terms(q: str):
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z0-9]+", q.lower()):
        if w in STOP or (len(w) < 3 and not w.isdigit()) or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _queries(ts):
    """From strictest to loosest: exact phrase, all terms, then the most distinctive terms."""
    qs = []
    if len(ts) >= 2:
        qs.append('"' + " ".join(ts[:6]) + '"')
    top = sorted(ts, key=len, reverse=True)[:5]
    qs.append(" AND ".join(top))
    if len(top) > 2:
        qs.append(" AND ".join(top[:3]))
    return qs


def search(q: str, limit: int = 10, cite_count=None, per_case: int = 3):
    """Ranked list of {case_id, score, hits, passages:[{chunk_index,page,kind}]}. [] if the index is missing or nothing matches."""
    if not available():
        return []
    ts = terms(q)
    if not ts:
        return []
    db = _conn()
    rows = []
    for fq in _queries(ts):
        try:
            rows = db.execute(
                "SELECT m.case_id, m.chunk_id, m.page, m.kind, bm25(fts) AS s FROM fts JOIN meta m ON m.id = fts.rowid "
                "WHERE fts MATCH ? ORDER BY s LIMIT 600", (fq,)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if len(rows) >= 25 or fq == _queries(ts)[-1]:
            break
    cases = {}
    for case_id, idx, page, kind, s in rows:
        c = cases.setdefault(case_id, {"case_id": case_id, "passages": [], "hits": 0, "raw": 0.0})
        c["hits"] += 1
        if len(c["passages"]) < per_case:
            c["passages"].append({"chunk_id": idx, "page": page, "kind": kind, "s": -s})
            c["raw"] += -s
    out = []
    for c in cases.values():
        boost = 1 + 0.5 * math.log1p(cite_count(c["case_id"])) if cite_count else 1
        c["score"] = c["raw"] * boost
        out.append(c)
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


def passage_text(corpus_file: str, case_id: str, chunk_ids, con):
    """Read the given passages of a judgment from the parquet file. con is a duckdb connection/cursor."""
    if not chunk_ids:
        return {}
    ph = ",".join("?" * len(chunk_ids))
    rows = con.execute(
        f"SELECT chunk_id, page_start, text FROM read_parquet(?) WHERE case_id=? AND chunk_id IN ({ph})",
        [corpus_file, case_id, *chunk_ids]).fetchall()
    return {i: (pg, t) for i, pg, t in rows}
