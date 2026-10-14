# LexBharat

A private, local build of the LexBharat legal-research web app, running on the
[Open India Law](https://huggingface.co/datasets/vaquill/open-india-law) corpus instead of the
original hosted data, with a local-model assistant (Nyra).

> **Status: private and local only. Do not deploy publicly yet.** See [Before any deployment](#before-any-deployment).

## What works

| Area | How it works |
|---|---|
| Statutes (BNS, BNSS, BSA, IPC, Evidence Act, CPC, NI Act) | Read from the corpus parquet with DuckDB. Section lookup, keyword search, old to new code equivalents by identical heading |
| Case search (Supreme Court) | Title, party, S.C.R. / AIR / SCC citation, ranked by citation count |
| Citation graph | Derived from S.C.R. citations found in judgment text (the corpus's own citation fields are empty) |
| AIR and SCC lookup | Mapped from parallel citations and name matching (~15.6k cites, ~40% of cases) |
| More like this | Per-case vectors averaged from the stored Qdrant embeddings |
| Nyra chat | Local Ollama model, grounded in retrieved statute sections and judgment passages, with citation checks |

Not built: free-text semantic search (the stored vectors are Voyage `voyage-4` embeddings, so queries need the
Voyage API), cause lists, drafting, attachments, High Court judgments, real authentication and billing.

## Requirements

- Python 3.11+
- The Open India Law parquet files (about 50 GB). Set `CORPUS_DIR`, default `/Volumes/LAWSSD/open-india-law`
- [Ollama](https://ollama.com) with `ollama pull qwen2.5:7b` (override with `NYRA_MODEL`)
- Qdrant is optional. Only the slow fallback "more like this" for non-Supreme-Court cases uses it

## Run

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# one-time builds (each reads the corpus; a few minutes each)
./.venv/bin/python server/build_citations.py
./.venv/bin/python server/build_case_vectors.py     # needs Qdrant running
./.venv/bin/python server/build_parallel_citations.py

./run.sh        # http://localhost:8000
```

## Layout

- `web/` the saved front end (static build) with its API base patched to same-origin
- `server/main.py` the FastAPI app: statutes, cases, citations, stubs for everything else
- `server/nyra.py` the chat assistant (retrieval, prompt, SSE streaming, history)
- `server/build_*.py` one-time index builders
- `data/endpoints_all.txt` the API paths the front end calls

## Placeholders and kept names

- `lexbharat.ai` and `@lexbharat.in` addresses are **placeholders**. Replace them with domains you own.
- Third-party analytics (Google tag, Meta Pixel, Contentsquare) were removed from `web/index.html`.
- The front end still contains the original site's **public** identifiers: a Razorpay key ID, Google sign-in client
  IDs and a reCAPTCHA site key. They are publishable values, not secrets, but they belong to the original
  deployment. Replace or remove them before any public release.
- Internal storage keys and file names (for example `lawcentral_auth`, `LawCentralApp-*.js`) were left unchanged
  because renaming them inside minified bundles would break the app. External links to real accounts and
  names of unrelated organisations were not changed.
- Product images and logos were not downloaded with the front end, so some images are missing.

## Before any deployment

- Replace the stub authentication and the always-active subscription fixture with real ones.
- Decide where the model runs. Local small models can paraphrase or embellish, so keep the "not legal advice"
  framing and the citation checks.
- Remove or replace the original site's public identifiers listed above.
- Credit the dataset (below). Also check the terms of any other source you add.

## Data attribution

Legal text comes from **Open India Law** by Vaquill AI, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Judgments originate from official court sources, and
the High Court and Supreme Court judgment PDFs are on the AWS Open Data Registry. Cite the dataset if you publish
anything derived from it.
