#!/bin/zsh
# Start the local copy. Needs LAWSSD mounted. Open http://localhost:8000
cd "$(dirname "$0")"
exec ./.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000
