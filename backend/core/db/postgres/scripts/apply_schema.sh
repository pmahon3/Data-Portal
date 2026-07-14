#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="$(dirname "$0")/../../.env.development"
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

: "${DATABASE_URL:=postgresql://objtree_app:1q2w3e4r@localhost:5432/inn_objtree}"

echo "Applying schema.sql to $DATABASE_URL"
psql "$DATABASE_URL" -f "$(dirname "$0")/schema.sql"
echo "Done."
