#!/usr/bin/env bash
set -euo pipefail

umask 077
destination="${1:-data/runtime/backups}"
if [[ -z "${destination}" || "${destination}" == "/" || "${destination}" == "." ]]; then
  echo "Refusing an unsafe backup destination." >&2
  exit 2
fi
mkdir -p "${destination}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="${destination%/}/phase3-postgres-${stamp}.dump"
checksum="${archive}.sha256"

docker compose exec -T postgres sh -c \
  'pg_dump --format=custom --no-owner --no-privileges --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  >"${archive}"
shasum -a 256 "${archive}" >"${checksum}"
chmod 600 "${archive}" "${checksum}"

printf '%s\n' "${archive}"
