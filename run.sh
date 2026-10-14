#!/bin/zsh
# Local development. Production runs WITHOUT this flag and needs LEXBHARAT_SECRET (see .env.example).
cd "$(dirname "$0")"
export LEXBHARAT_ENV=dev
exec ./.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
