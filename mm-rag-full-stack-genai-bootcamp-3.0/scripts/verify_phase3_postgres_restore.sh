#!/usr/bin/env bash
set -euo pipefail

archive="${1:-}"
if [[ -z "${archive}" || ! -f "${archive}" || ! -f "${archive}.sha256" ]]; then
  echo "Usage: $0 PATH_TO_PHASE3_DUMP (with adjacent .sha256 file)" >&2
  exit 2
fi
shasum -a 256 --check "${archive}.sha256" >/dev/null

target="mm_rag_phase3_restore_$(date -u +%Y%m%d%H%M%S)_$$"
if [[ ! "${target}" =~ ^mm_rag_phase3_restore_[0-9_]+$ ]]; then
  echo "Generated restore database name is unsafe." >&2
  exit 2
fi

cleanup() {
  docker compose exec -T postgres dropdb \
    --if-exists --force --username="${POSTGRES_USER:-mm_rag}" "${target}" >/dev/null
}
trap cleanup EXIT

docker compose exec -T postgres createdb \
  --username="${POSTGRES_USER:-mm_rag}" "${target}"
docker compose exec -T postgres pg_restore \
  --exit-on-error --no-owner --no-privileges \
  --username="${POSTGRES_USER:-mm_rag}" --dbname="${target}" <"${archive}"

revision="$(docker compose exec -T postgres psql --tuples-only --no-align \
  --username="${POSTGRES_USER:-mm_rag}" --dbname="${target}" \
  --command='SELECT version_num FROM alembic_version;')"
if [[ "${revision}" != "20260830_0008" ]]; then
  echo "Restored database is not at the expected migration head." >&2
  exit 1
fi

docker compose exec -T postgres psql --tuples-only --no-align \
  --username="${POSTGRES_USER:-mm_rag}" --dbname="${target}" \
  --command='SELECT count(*) >= 0 FROM ingestion_jobs;' | grep -qx 't'
printf 'Phase 3 PostgreSQL restore verification passed.\n'
