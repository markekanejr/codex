#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR=/workspace/.cache/uv
export UV_PYTHON_DOWNLOADS=never
uv sync --locked
uv run python scripts/dev_setup.py
docker compose up -d --wait db
uv run python manage.py migrate --noinput
uv run python manage.py check
