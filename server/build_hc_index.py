"""Build data/hc_cases.duckdb: one row per High Court judgment (metadata only, no text).

Run once, and again if the corpus changes:
    ./.venv/bin/python server/build_hc_index.py [--only delhi,bombay]

Judgment text stays on the SSD; the app reads a few passages from the right court file when a case is opened.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
OUT = ROOT / "data" / "hc_cases.duckdb"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated court slugs, e.g. delhi,bombay")
    args = ap.parse_args()
    only = {x for x in args.only.split(",") if x}
    files = sorted(p for p in CORPUS.glob("in_*_judgments.parquet") if p.name != "in_supreme-court_judgments.parquet")
    if only:
        files = [p for p in files if p.name[3:-len("_judgments.parquet")] in only]
    (ROOT / "data" / "duck_tmp").mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(OUT))
    c.execute(f"SET memory_limit='4GB'; SET temp_directory='{ROOT / 'data' / 'duck_tmp'}'; SET threads=4")
    c.execute("""CREATE TABLE IF NOT EXISTS hc_cases(
        case_id VARCHAR, court VARCHAR, slug VARCHAR, title VARCHAR, petitioner VARCHAR, respondent VARCHAR,
        decision_date VARCHAR, year BIGINT, case_number VARCHAR, citation VARCHAR, disposition VARCHAR, total_chunks BIGINT)""")
    done = {r[0] for r in c.execute("SELECT DISTINCT slug FROM hc_cases").fetchall()}
    for p in files:
        slug = p.name[3:-len("_judgments.parquet")]
        if slug in done:
            print(f"skip {slug} (already indexed)")
            continue
        t0 = time.time()
        c.execute("BEGIN")
        c.execute("""INSERT INTO hc_cases
            SELECT case_id, court, ?, title, petitioner, respondent, decision_date, year, case_number, citation, disposition, total_chunks
            FROM read_parquet(?) WHERE chunk_index = 0""", [slug, str(p)])
        c.execute("COMMIT")
        n = c.execute("SELECT count(*) FROM hc_cases WHERE slug=?", [slug]).fetchone()[0]
        print(f"{slug:28} {n:>9,} cases  {time.time() - t0:5.0f}s", flush=True)
    c.execute("CREATE INDEX IF NOT EXISTS hc_id ON hc_cases(case_id)")
    print("total", c.execute("SELECT count(*) FROM hc_cases").fetchone()[0])


if __name__ == "__main__":
    sys.exit(main())
