#!/usr/bin/env bash
set -euo pipefail

uv lock --check
uv run ruff check backend frontend migrations scripts tests
uv run mypy backend frontend scripts tests/backend
uv run pytest
uv run alembic current
uv run alembic check

if [[ "${1:-}" == "--live" ]]; then
  curl --fail --silent --show-error http://127.0.0.1:8003/api/v1/health/live
  curl --fail --silent --show-error http://127.0.0.1:8003/api/v1/health/ready
  curl --fail --silent --show-error http://127.0.0.1:8503/_stcore/health
fi

git diff --check
printf '\nPhase 3 verification passed.\n'
