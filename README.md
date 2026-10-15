# LexBharat

A private, local build of the LexBharat legal-research web app, running on the
[Open India Law](https://huggingface.co/datasets/vaquill/open-india-law) corpus instead of the
original hosted data, with a local-model assistant (KanoonBuddy).

> **Status: private build. Authentication is in place; read [Before any deployment](#before-any-deployment) before putting it on the internet.**

## What works

| Area | How it works |
|---|---|
| Statutes (BNS, BNSS, BSA, IPC, Evidence Act, CPC, NI Act) | Read from the corpus parquet with DuckDB. Section lookup, keyword search, old to new code equivalents by identical heading |
| Case search (Supreme Court) | Title, party, S.C.R. / AIR / SCC citation, ranked by citation count |
| Citation graph | Derived from S.C.R. citations found in judgment text (the corpus's own citation fields are empty) |
| AIR and SCC lookup | Mapped from parallel citations and name matching (~15.6k cites, ~40% of cases) |
| More like this | Per-case vectors averaged from the stored Qdrant embeddings |
| KanoonBuddy chat | Local Ollama model, grounded in retrieved statute sections and judgment passages, with citation checks |

Not built: free-text semantic search (the stored vectors are Voyage `voyage-4` embeddings, so queries need the
Voyage API), cause lists, drafting, attachments, High Court judgments, payments, and sign-in by Google or phone.

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

## Authentication

Invite-only email and password. There is **no public sign-up**; an administrator creates accounts.

```bash
# create / manage accounts (set LEXBHARAT_ENV=dev if you are running in dev mode)
./.venv/bin/python -m server.manage_users add you@example.com --name "Your Name"   # prompts for a password
./.venv/bin/python -m server.manage_users add you@example.com --generate           # prints a random one, once
./.venv/bin/python -m server.manage_users list | passwd | disable | enable | delete
```

- Passwords: scrypt with a per-user salt, minimum 12 characters. Unknown emails cost the same as wrong passwords,
  so responses do not reveal which emails exist.
- Sessions: signed HS256 tokens (8 h, refreshable for up to 7 days after expiry, hard cap 30 days per login).
  Logout, password change and disabling an account revoke tokens.
- Every `/api/*` route needs a token except login, refresh, logout, health, and read-only statute pages (rate limited by IP).
- Lockout: 5 failed logins per email locks it for 15 minutes (the same for emails that do not exist); 10 attempts a minute per IP.
- KanoonBuddy chats are private to the account that created them.
- Limits: 12 chat messages a minute per user, 4,000 characters per message, 2 simultaneous model runs, 1 MB request bodies.
- Headers: CSP, `X-Frame-Options`, `nosniff`, HSTS (production), `Cache-Control: no-store` on the API. API docs are disabled.
- `LEXBHARAT_ENV` defaults to **production**, which **refuses to start** without `LEXBHARAT_SECRET` (32+ characters).
  `./run.sh` sets `LEXBHARAT_ENV=dev` for local use. See `.env.example`.

Tests: `LEXBHARAT_ENV=dev ./.venv/bin/python -m unittest tests.test_auth -v` (30 tests, throwaway database).

## Layout

- `web/` the saved front end (static build) with its API base patched to same-origin
- `server/main.py` the FastAPI app: statutes, cases, citations, stubs for everything else
- `server/auth.py`, `server/manage_users.py` authentication and the admin tool
- `server/nyra.py` the chat assistant (retrieval, prompt, SSE streaming, per-user history)
- `web/signin.html` the sign-in page (the original Google/phone login screen is replaced)
- `tests/` authentication tests
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
- The chat assistant, formerly called Nyra, is now **KanoonBuddy** in all visible text, the model's own prompt and the docs, and its "she/her" in the app copy became "it/its". Internal names were kept because renaming them would break the app or your configuration: `server/nyra.py`, the `NYRA_MODEL`, `NYRA_DB` and `NYRA_MAX_CONCURRENT` environment variables, the `?nyra=1` URL parameter, API paths such as `/api/notifications/nyra-popout`, CSS classes, storage keys and image file names.
- Product images and logos were not downloaded with the front end, so some images are missing.

## Before any deployment

Done: authentication, per-user chats, rate limits, request limits, security headers, fail-fast configuration.

Still needed:

- **HTTPS.** Run behind a TLS-terminating reverse proxy (Caddy, nginx, a cloud load balancer). Set `TRUST_PROXY=1`
  only if the proxy overwrites `X-Forwarded-For`. Never expose uvicorn or Ollama directly.
- **Where the model runs.** The app needs the 50 GB corpus and an Ollama model on the same host or reachable
  over a private network. A small local model is slow (10 to 20 s per answer) and can paraphrase or embellish,
  so keep the "not legal advice" framing and the citation checks.
- **Single process.** Rate limits live in memory, so run one worker, or move them to Redis before scaling out.
- **Accounts and backups.** `data/auth.sqlite` holds the password hashes. Back it up and keep it out of git.
  There is no self-service password reset or email verification; an administrator resets passwords.
- **Tokens live in the browser's localStorage** (that is how the front end works). The CSP limits script injection,
  but a stored-XSS bug would expose them. Moving to HttpOnly cookies means changing the front end.
- **The subscription and entitlement endpoints are fixtures** that report an active plan to every signed-in user.
  Real billing is not built.
- **Original site content.** The saved front end still contains the original's public identifiers (Razorpay key ID,
  Google client IDs, reCAPTCHA key), marketing claims (for example "10,000+ advocates") and page text such as
  "Text checked against the Gazette". Review and replace these for your own product.
- **Domains** `lexbharat.ai` and `@lexbharat.in` are placeholders.
- **Credit the dataset** (below) and check the terms of any other source you add.

## Data attribution

Legal text comes from **Open India Law** by Vaquill AI, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Judgments originate from official court sources, and
the High Court and Supreme Court judgment PDFs are on the AWS Open Data Registry. Cite the dataset if you publish
anything derived from it.

## Document import (editor)

The editor Import dialog reads PDF, Word (.docx), text, RTF and images (server/docparse.py). PDFs and OCR need system programs:

    brew install poppler tesseract tesseract-lang

Legacy .doc files are not supported. Export (download as Word or PDF) is not built yet.

## Editor extras (added 2026-10-14)

- **Templates**: ten standard Indian documents with fill-in forms (`server/templates.py`, `web/templates-ui.js`). Draft requests in chat use them instead of model-written text.
- **Check**: deterministic document check (blanks, missing verification clause, every cited section and case checked against the library, repealed law flagged). It replaces the original editor's "Risk Review / Fix Citations / Fields / Health", which needed services this build does not have and are hidden.
- **Landmark summaries**: `server/landmarks.py` holds short editorial summaries of 12 landmark cases and reading notes for dense sections (BNSS 187). They are labelled as editorial, not part of the judgment. A lawyer should review them.
- **Case page** `/case/<id>`: full judgment text (Supreme Court and High Courts), find-in-text, key-holding box for landmarks. Chat answers end with a Sources line linking to the cited sections and cases.
- **Editor guide** `/editor-guide` is our own page. The original site's guide described features that do not exist here.
