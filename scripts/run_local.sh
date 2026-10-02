#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --frozen
exec uv run python scripts/run_local.py
