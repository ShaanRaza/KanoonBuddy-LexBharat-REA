"""One-time build: extract S.C.R. citations from Supreme Court judgment text and match
them to cases, producing data/citations.duckdb (table edges(citing, cited, mentions)).

The corpus's own `cases_cited` / `cited_by_count` payloads are empty, so the graph is
derived from the judgment text. Matching is on the reporter citation (year, volume, page).

Run:  ./.venv/bin/python server/build_citations.py
"""
import os
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
OUT = ROOT / "data" / "citations.duckdb"
SC = str(CORPUS / "in_supreme-court_judgments.parquet")

# "[1973] Supp. 1 S.C.R. 1", "[1952] S.C.R. 89", "[2015] 13 S.C.R. 1"
PAT = r"(?i)\[(\d{4})\]\s*(?:(supp\w*\.?)\s*)?(\d{1,3})?\s*S\.?\s?C\.?\s?R\.?\s*(\d{1,4})"

t0 = time.time()
OUT.parent.mkdir(exist_ok=True)
if OUT.exists():
    OUT.unlink()
con = duckdb.connect(str(OUT))
con.execute("SET memory_limit='6GB'")
con.execute("SET preserve_insertion_order=false")
tmp = ROOT / "data" / "duck_tmp"
tmp.mkdir(exist_ok=True)
con.execute(f"SET temp_directory='{tmp}'")


def norm(col: str) -> str:
    """Normalised key from a raw citation string: year|supp|volume|page."""
    return (
        f"regexp_extract({col}, '{PAT}', 1) || '|' || "
        f"CASE WHEN regexp_extract({col}, '{PAT}', 2) <> '' THEN 'S' ELSE '' END || '|' || "
        f"regexp_extract({col}, '{PAT}', 3) || '|' || regexp_extract({col}, '{PAT}', 4)"
    )


print("1/4 case reporter keys ...", flush=True)
con.execute(
    f"""CREATE TABLE case_keys AS
    SELECT case_id, {norm('citation')} AS k
    FROM (SELECT case_id, any_value(citation) AS citation
          FROM read_parquet('{SC}') GROUP BY case_id)
    WHERE citation <> ''"""
)
con.execute("CREATE TABLE ck AS SELECT * FROM case_keys WHERE k NOT LIKE '||%'")
# loose key (year|page) used only when it identifies exactly one case
con.execute(
    """CREATE TABLE loose AS
    SELECT split_part(k,'|',1)||'|'||split_part(k,'|',4) AS lk, min(case_id) AS case_id, count(*) AS n
    FROM ck GROUP BY 1"""
)

print("2/4 extracting citations from text (slow part) ...", flush=True)
con.execute(
    f"""CREATE TABLE raw AS
    SELECT case_id AS citing, unnest(regexp_extract_all(text, '{PAT}')) AS cit
    FROM read_parquet('{SC}')"""
)
print(f"   raw mentions: {con.execute('SELECT count(*) FROM raw').fetchone()[0]:,}  ({time.time()-t0:.0f}s)", flush=True)

print("3/4 normalising + matching ...", flush=True)
con.execute(f"CREATE TABLE mentions AS SELECT citing, {norm('cit')} AS k, count(*) AS m FROM raw GROUP BY 1,2")
con.execute("DROP TABLE raw")
con.execute(
    """CREATE TABLE edges AS
    SELECT citing, cited, sum(m) AS mentions FROM (
        SELECT mt.citing, c.case_id AS cited, mt.m
        FROM mentions mt JOIN ck c ON c.k = mt.k
      UNION ALL
        SELECT mt.citing, l.case_id, mt.m
        FROM mentions mt JOIN loose l
          ON l.lk = split_part(mt.k,'|',1)||'|'||split_part(mt.k,'|',4) AND l.n = 1
        WHERE split_part(mt.k,'|',3) = ''  -- text gave no volume, so only the loose key can match
    ) WHERE citing <> cited GROUP BY 1,2"""
)
con.execute("CREATE INDEX e_citing ON edges(citing)")
con.execute("CREATE INDEX e_cited ON edges(cited)")
con.execute("DROP TABLE mentions")

print("4/4 stats", flush=True)
e = con.execute("SELECT count(*), count(DISTINCT citing), count(DISTINCT cited) FROM edges").fetchone()
print(f"   edges={e[0]:,} citing_cases={e[1]:,} cited_cases={e[2]:,}  total {time.time()-t0:.0f}s")
print("   most cited:", con.execute("SELECT cited, count(*) c FROM edges GROUP BY 1 ORDER BY 2 DESC LIMIT 5").fetchall())
con.close()
