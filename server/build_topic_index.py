"""Build data/sc_topic.sqlite: a full-text (BM25) index over Supreme Court judgment text, for topic search.

Run once, and again if the corpus changes (about 10-20 minutes, needs the SSD):
    ./.venv/bin/python server/build_topic_index.py

The index stores no text, only the search structure and a map back to (case_id, chunk_index, page). The app reads the
matching passage from the parquet file on the SSD when it needs to show it.
"""
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
OUT = ROOT / "data" / "sc_topic.sqlite"
SRC = CORPUS / "in_supreme-court_judgments.parquet"
SKIP_TYPES = {"header", "judgment"}      # cover pages and the like
HEAD = re.compile(r"^Case:.*?Section:\s*[A-Z_ ]+\s*", re.S)   # every passage starts "Case: TITLE [cite] (year) Section: BODY"


def english(t: str) -> bool:
    return bool(t) and sum(c.isascii() for c in t) / len(t) > 0.93   # skips garbled / Hindi OCR passages


def main():
    tmp = OUT.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    db.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;
        CREATE TABLE meta(id INTEGER PRIMARY KEY, case_id TEXT, chunk_id TEXT, page INTEGER, kind TEXT);
        CREATE VIRTUAL TABLE fts USING fts5(body, content='', contentless_delete=0, tokenize='porter unicode61 remove_diacritics 2');
    """)
    con = duckdb.connect()
    con.execute(f"SET temp_directory='{ROOT / 'data' / 'duck_tmp'}'; SET threads=4")
    cur = con.execute("SELECT case_id, chunk_id, page_start, section_type, text FROM read_parquet(?)", [str(SRC)])
    n = kept = 0
    t0 = time.time()
    while True:
        rows = cur.fetchmany(20000)
        if not rows:
            break
        meta, fts = [], []
        for case_id, cid, page, kind, text in rows:
            n += 1
            text = HEAD.sub("", text or "", count=1)
            if kind in SKIP_TYPES or len(text) < 200 or not english(text):
                continue
            kept += 1
            meta.append((kept, case_id, cid, page, kind))
            fts.append((kept, text))
        db.executemany("INSERT INTO meta VALUES (?,?,?,?,?)", meta)
        db.executemany("INSERT INTO fts(rowid, body) VALUES (?,?)", fts)
        db.commit()
        print(f"{n:>9,} read  {kept:>9,} indexed  {time.time() - t0:5.0f}s", flush=True)
    db.execute("CREATE INDEX meta_case ON meta(case_id)")
    db.execute("INSERT INTO fts(fts) VALUES('optimize')")
    db.commit()
    db.close()
    tmp.replace(OUT)
    print(f"done: {kept:,} passages -> {OUT} ({OUT.stat().st_size / 1e9:.1f} GB)")


if __name__ == "__main__":
    sys.exit(main())
