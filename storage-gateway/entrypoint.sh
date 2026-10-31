#!/bin/bash
# Starts the file service as the account that holds the data.
set -eu

# HTTPS (DS-tls-in-service): with GATEWAY_TLS_CERT and GATEWAY_TLS_KEY set, the service serves its own
# TLS; nothing sits between users and the storage. Without them it serves plain HTTP (local tests only).
tls=()
if [ -n "${GATEWAY_TLS_CERT:-}${GATEWAY_TLS_KEY:-}" ]; then
  [ -r "${GATEWAY_TLS_CERT:-}" ] && [ -r "${GATEWAY_TLS_KEY:-}" ] \
    || { echo "GATEWAY_TLS_CERT and GATEWAY_TLS_KEY must both name readable files" >&2; exit 1; }
  tls=(--ssl-certfile "$GATEWAY_TLS_CERT" --ssl-keyfile "$GATEWAY_TLS_KEY")
fi

exec uvicorn --factory app.main:app_from_env --host 0.0.0.0 --port "${GATEWAY_PORT:-9100}" --no-access-log "${tls[@]}"
