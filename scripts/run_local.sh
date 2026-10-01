#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --frozen
uv run python scripts/setup_local.py
uv run alembic upgrade head
uv run python scripts/run_worker.py > data/worker.log 2>&1 &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
uv run python -c 'import os, uvicorn; from dotenv import load_dotenv; load_dotenv(); uvicorn.run("surveyor.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8010")))'
