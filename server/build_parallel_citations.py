"""One-time build: map AIR and SCC citations to Supreme Court cases (data/parallel.duckdb).

The corpus stores only each case's S.C.R. citation, and a judgment never prints its own AIR/SCC
cite. Later judgments do, in two useful ways, and we use both:

 A. Parallel strings   "1973 Supp SCR 1 : (1973) 4 SCC 225 : AIR 1973 SC 1461"
    An S.C.R. cite next to an AIR/SCC cite links them exactly (the S.C.R. cite identifies the
    case in our table). Strongest signal.
 B. Name + cite        "Maneka Gandhi v. Union of India, AIR 1978 SC 597"
    Party names + year are matched to a case. Used only where A gave nothing.

A mapping is kept only when exactly one case wins, so ambiguous cites are dropped, not guessed.

Output: data/parallel.duckdb  parallel(cite_key, cite_text, case_id, mentions, runner_up, source)
  cite_key e.g. 'AIR|1978|597' or 'SCC|1978|1|248'
Run:  ./.venv/bin/python server/build_parallel_citations.py
"""
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(os.environ.get("CORPUS_DIR", "/Volumes/LAWSSD/open-india-law"))
OUT = ROOT / "data" / "parallel.duckdb"
SC = str(CORPUS / "in_supreme-court_judgments.parquet")

# --- citation shapes (RE2; \x27 is an apostrophe) ---------------------------------------------
AIR = r"A\.?\s?I\.?\s?R\.?\s*\(?\d{4}\)?\s*S\.?\s?C\.?\s*\d{1,4}"
SCC = r"\(\d{4}\)\s*\d{1,3}\s*S\.?\s?C\.?\s?C\.?\s*\d{1,4}"
SCR = r"[\[(]?\d{4}[\])]?\s*(?:supp(?:l(?:ement(?:ary)?)?)?\.?\s*)?(?:\d{1,3}\s*)?S\.?\s?C\.?\s?R\.?\s*\d{1,4}"
NAME = r"[A-Z][A-Za-z0-9.,&\x27() \-]{1,70}?"
PAT_NAME = rf"({NAME})\s+(?:v\.|vs\.?|versus|v)\s+({NAME})\s*[,(\[]?\s*(?:reported (?:in|at)\s+)?({AIR}|{SCC})"
GAP = r".{0,80}?"
PAT_PAIR = rf"(?i)(?:(?:{SCR}){GAP}(?:{AIR}|{SCC})|(?:{AIR}|{SCC}){GAP}(?:{SCR}))"

STOP = {"the", "and", "ors", "ors.", "anr", "anr.", "another", "others", "etc", "of", "by", "lrs",
        "dead", "through", "smt", "shri", "sri", "m/s", "messrs", "dr", "mr", "mrs", "ltd", "co",
        "company", "pvt", "limited", "versus", "ltd.", "private",
        "his", "holiness", "kumari", "late", "prof", "hon", "sir", "ms", "mohd", "md"}
# state/union/india are kept on purpose: they are real parties ("Union of India")


def toks(s: str, n: int = 2):
    out = []
    for t in re.findall(r"[a-z0-9]+", s.lower()):
        if t in STOP or (len(t) < 3 and not t.isdigit()):
            continue
        out.append(t)
        if len(out) == n:
            break
    return tuple(out)


def allt(s: str):
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP and (len(t) >= 3 or t.isdigit())}


R_AIR = re.compile(r"(?i)A\.?\s?I\.?\s?R\.?\s*\(?(\d{4})\)?\s*S\.?\s?C\.?\s*(\d{1,4})")
R_SCC = re.compile(r"(?i)\((\d{4})\)\s*(\d{1,3})\s*S\.?\s?C\.?\s?C\.?\s*(\d{1,4})")
R_SCR = re.compile(r"(?i)[\[(]?(\d{4})[\])]?\s*(supp(?:l(?:ement(?:ary)?)?)?\.?\s*)?(\d{1,3})?\s*S\.?\s?C\.?\s?R\.?\s*(\d{1,4})")


def parse_cite(c: str):
    m = R_AIR.search(c)
    if m:
        return f"AIR|{m.group(1)}|{m.group(2)}", int(m.group(1))
    m = R_SCC.search(c)
    if m:
        return f"SCC|{m.group(1)}|{m.group(2)}|{m.group(3)}", int(m.group(1))
    return None, None


def scr_keys(c: str):
    """(exact key, loose key) for an S.C.R. citation string."""
    m = R_SCR.search(c)
    if not m:
        return None, None
    y, supp, vol, page = m.group(1), bool(m.group(2)), m.group(3) or "", m.group(4)
    return (y, "S" if supp else "", vol, page), (y, page)


t0 = time.time()
OUT.parent.mkdir(exist_ok=True)
tmp = ROOT / "data" / "duck_tmp"
tmp.mkdir(exist_ok=True)
if OUT.exists():
    OUT.unlink()
con = duckdb.connect(str(OUT))
con.execute("SET memory_limit='6GB'")
con.execute("SET preserve_insertion_order=false")
con.execute(f"SET temp_directory='{tmp}'")

print("1/5 extracting parallel strings (SCR next to AIR/SCC) ...", flush=True)
con.execute(
    f"""CREATE TABLE pairs AS
    SELECT m, count(*) AS n FROM (
        SELECT unnest(regexp_extract_all(text, '{PAT_PAIR}')) AS m FROM read_parquet('{SC}'))
    GROUP BY m"""
)
print(f"   distinct parallel strings: {con.execute('SELECT count(*) FROM pairs').fetchone()[0]:,} ({time.time()-t0:.0f}s)", flush=True)

print("2/5 extracting 'Party v. Party, cite' mentions ...", flush=True)
con.execute(
    f"""CREATE TABLE ment AS
    SELECT trim(regexp_extract(m, '{PAT_NAME}', 1)) AS p1,
           trim(regexp_extract(m, '{PAT_NAME}', 2)) AS p2,
           trim(regexp_extract(m, '{PAT_NAME}', 3)) AS cite, count(*) AS n
    FROM (SELECT unnest(regexp_extract_all(text, '{PAT_NAME}')) AS m FROM read_parquet('{SC}'))
    GROUP BY ALL"""
)
print(f"   distinct name mentions: {con.execute('SELECT count(*) FROM ment').fetchone()[0]:,} ({time.time()-t0:.0f}s)", flush=True)

print("3/5 loading cases ...", flush=True)
case_rows = duckdb.connect().execute(
    f"""SELECT case_id, any_value(title), any_value(petitioner), any_value(respondent),
               any_value(year), any_value(citation)
        FROM read_parquet('{SC}') GROUP BY case_id"""
).fetchall()
exact, loose = {}, defaultdict(set)
info, tok_idx, year_of = {}, defaultdict(list), {}
for cid, title, pet, res, yr, cit in case_rows:
    year_of[cid] = int(yr) if yr is not None else None
    if cit:
        ek, lk = scr_keys(cit)
        if ek:
            exact.setdefault(ek, set()).add(cid)
            loose[lk].add(cid)
    a, b = pet, res
    if (not a or not b) and title and " versus " in title:
        a, b = title.split(" versus ", 1)
    if a and b and yr is not None:
        t1, t2 = allt(a), allt(b)
        if t1 and t2:
            info[cid] = (t1, t2, int(yr))
            for t in t1 | t2:
                tok_idx[t].append(cid)

print("4/5 linking ...", flush=True)
votes_a = defaultdict(lambda: defaultdict(int))  # A: via the S.C.R. cite
votes_b = defaultdict(lambda: defaultdict(int))  # B: via party names + year
texts = {}
for m, n in con.execute("SELECT m, n FROM pairs").fetchall():
    ek, lk = scr_keys(m)
    if not ek:
        continue
    cands = exact.get(ek) or (loose[lk] if len(loose.get(lk, ())) == 1 else set())
    if len(cands) != 1:
        continue
    if len(R_SCR.findall(m)) != 1:  # span runs across two list entries -> pairing unreliable
        continue
    cid = next(iter(cands))
    for rx in (R_AIR, R_SCC):
        for hit in rx.finditer(m):
            ck, cy = parse_cite(hit.group(0))
            # the AIR/SCC report year must agree with the case's decision year
            if ck and year_of.get(cid) is not None and abs(year_of[cid] - cy) <= 1:
                votes_a[ck][cid] += n
                texts.setdefault(ck, hit.group(0))

for p1, p2, cite, n in con.execute("SELECT p1,p2,cite,n FROM ment").fetchall():
    ck, cy = parse_cite(cite)
    m1, m2 = set(toks(p1, 3)), set(toks(p2, 3))
    if not ck or not m1 or not m2:
        continue
    rare = min(m1 | m2, key=lambda t: len(tok_idx.get(t, ())) or 10**9)
    for cid in tok_idx.get(rare, ()):
        t1, t2, yr = info[cid]
        if m1 <= t1 and m2 <= t2 and abs(yr - cy) <= 1:
            votes_b[ck][cid] += n
            texts.setdefault(ck, cite)


def winner(d):
    if not d:
        return None
    r = sorted(d.items(), key=lambda x: -x[1])
    return (r[0][0], r[0][1], r[1][1] if len(r) > 1 else 0) if r[0][1] > (r[1][1] if len(r) > 1 else 0) else None


print("5/5 keeping unambiguous winners ...", flush=True)
con.execute("CREATE TABLE parallel(cite_key VARCHAR, cite_text VARCHAR, case_id VARCHAR, mentions BIGINT, runner_up BIGINT, source VARCHAR)")
rows, src = [], defaultdict(int)
for ck in set(votes_a) | set(votes_b):
    w = winner(votes_a.get(ck)) ; s = "A"
    if w is None:
        w = winner(votes_b.get(ck)) ; s = "B"
    if w:
        rows.append((ck, texts[ck], w[0], w[1], w[2], s))
        src[s] += 1

# A case has exactly one AIR cite and one SCC cite. Pinpoint pages and OCR run-ons ("SCC 2251")
# show up as extra, weaker cites for the same case, so keep only the best-supported one per
# (case, scheme); a tie at the top means we cannot tell, so drop both.
best = defaultdict(list)
for r in rows:
    best[(r[2], r[0].split("|")[0])].append(r)
kept, dropped_extra, dropped_tie = [], 0, 0
for lst in best.values():
    lst.sort(key=lambda r: -r[3])
    if len(lst) > 1 and lst[0][3] == lst[1][3]:
        dropped_tie += len(lst)
        continue
    kept.append(lst[0])
    dropped_extra += len(lst) - 1
print(f"   one-per-case filter: kept {len(kept):,}, dropped {dropped_extra:,} weaker extras and {dropped_tie:,} tied", flush=True)
rows = kept
con.executemany("INSERT INTO parallel VALUES (?,?,?,?,?,?)", rows)
con.execute("CREATE INDEX p_key ON parallel(cite_key)")
con.execute("CREATE INDEX p_case ON parallel(case_id)")
con.execute("DROP TABLE ment"); con.execute("DROP TABLE pairs")
n_air = con.execute("SELECT count(*) FROM parallel WHERE cite_key LIKE 'AIR|%'").fetchone()[0]
n_scc = con.execute("SELECT count(*) FROM parallel WHERE cite_key LIKE 'SCC|%'").fetchone()[0]
n_case = con.execute("SELECT count(DISTINCT case_id) FROM parallel").fetchone()[0]
print(f"   mapped: AIR={n_air:,} SCC={n_scc:,} cases={n_case:,} | from parallel strings={src['A']:,} from names={src['B']:,} | {time.time()-t0:.0f}s")
for ck in ["AIR|1978|597", "SCC|1978|1|248", "AIR|1973|1461", "SCC|1973|4|225", "AIR|1997|3011", "SCC|1997|6|241"]:
    print("  ", ck, "->", con.execute("SELECT case_id, mentions, runner_up, source FROM parallel WHERE cite_key=?", [ck]).fetchall())
con.close()
