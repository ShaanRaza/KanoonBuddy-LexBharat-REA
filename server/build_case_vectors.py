"""One-time build: one embedding per Supreme Court case = mean of its stored chunk vectors.

Reads (never writes) Qdrant's legal_corpus_v2, writes data/case_vectors.npz with
  ids  (N,)   case_id strings
  vecs (N,1024) float16, L2-normalised mean dense vectors
so "more like this" is an in-memory matrix multiply instead of a 30-80 s Qdrant ANN query.

Run:  ./.venv/bin/python server/build_case_vectors.py   (Qdrant must be up)
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models as m

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "case_vectors.npz"
COURT = os.environ.get("COURT", "Supreme Court of India")
BATCH = int(os.environ.get("BATCH", "512"))

q = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"), timeout=300)
C = "legal_corpus_v2"
flt = m.Filter(must=[m.FieldCondition(key="court", match=m.MatchValue(value=COURT))])
total = q.count(C, count_filter=flt, exact=True).count
print(f"{COURT}: {total:,} points to read", flush=True)

index, sums, counts = {}, [], []
off, seen, t0 = None, 0, time.time()
while True:
    pts, off = q.scroll(C, scroll_filter=flt, limit=BATCH, offset=off, with_payload=["case_id"],
                        with_vectors=["dense"])
    for p in pts:
        cid = p.payload.get("case_id")
        v = p.vector.get("dense") if isinstance(p.vector, dict) else p.vector
        if not cid or v is None:
            continue
        i = index.get(cid)
        if i is None:
            i = index[cid] = len(sums)
            sums.append(np.zeros(len(v), dtype=np.float32))
            counts.append(0)
        sums[i] += np.asarray(v, dtype=np.float32)
        counts[i] += 1
    seen += len(pts)
    if seen % (BATCH * 20) < BATCH or off is None:
        rate = seen / max(time.time() - t0, 1e-6)
        eta = (total - seen) / max(rate, 1e-6)
        print(f"  {seen:,}/{total:,}  {rate:,.0f} pts/s  cases={len(index):,}  eta {eta/60:.1f} min", flush=True)
    if off is None:
        break

ids = np.array(list(index.keys()))
mat = np.stack(sums) / np.maximum(np.array(counts, dtype=np.float32)[:, None], 1)
mat /= np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
OUT.parent.mkdir(exist_ok=True)
np.savez(OUT, ids=ids, vecs=mat.astype(np.float16))
print(f"saved {OUT} cases={len(ids):,} size={OUT.stat().st_size/1e6:.0f} MB in {(time.time()-t0)/60:.1f} min")
