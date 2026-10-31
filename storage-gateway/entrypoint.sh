#!/bin/bash
# Starts the privileged helper (root) and the web service (unprivileged, no access to the data).
# Layout on the data volume (/srv/posix):
#   data/     governed files: owner inndata, folders 0710 with group posix-traverse, files 0600
#   staging/  one folder per temporary ID for uploads in progress (outside the data tree)
#   .helper/  the helper's state (which IDs hold which grants), so a restart still revokes them
set -eu

# HTTPS (DS-tls-in-service): with GATEWAY_TLS_CERT and GATEWAY_TLS_KEY set, the web service serves its own
# TLS; nothing sits between users and the storage. Without them it serves plain HTTP (local tests only).
tls=()
if [ -n "${GATEWAY_TLS_CERT:-}${GATEWAY_TLS_KEY:-}" ]; then
  [ -r "${GATEWAY_TLS_CERT:-}" ] && [ -r "${GATEWAY_TLS_KEY:-}" ] \
    || { echo "GATEWAY_TLS_CERT and GATEWAY_TLS_KEY must both name readable files" >&2; exit 1; }
  tls=(--ssl-certfile "$GATEWAY_TLS_CERT" --ssl-keyfile "$GATEWAY_TLS_KEY")
fi

# Without administrator access (GATEWAY_ACCESS=account): no root, no helper. The web service runs as
# the container's user, which must hold the data (docs/posix/README.md, "Administrator access").
if [ "${GATEWAY_ACCESS:-helper}" = account ]; then
  unset GATEWAY_HELPER_SOCKET
  export GATEWAY_REQUIRE_ISOLATION=0
  exec uvicorn --factory app.main:app_from_env --host 0.0.0.0 --port "${GATEWAY_PORT:-9100}" --no-access-log "${tls[@]}"
fi

mkdir -p /srv/posix/data /srv/posix/staging /srv/posix/.helper /run/gateway
chmod 0755 /srv/posix
chown inndata:posix-traverse /srv/posix/data && chmod 0710 /srv/posix/data
chown root:root /srv/posix/staging && chmod 0711 /srv/posix/staging
chown root:root /srv/posix/.helper && chmod 0700 /srv/posix/.helper
chown root:gateway /run/gateway && chmod 0750 /run/gateway
# The web service drops to 'gateway' before it reads the key, so it gets its own copy, readable by it alone.
if [ ${#tls[@]} -gt 0 ]; then
  install -o gateway -g gateway -m 0400 "$GATEWAY_TLS_CERT" /run/gateway/tls.crt
  install -o gateway -g gateway -m 0400 "$GATEWAY_TLS_KEY" /run/gateway/tls.key
  tls=(--ssl-certfile /run/gateway/tls.crt --ssl-keyfile /run/gateway/tls.key)
fi

python -m app.helper &
helper=$!
for _ in $(seq 1 50); do [ -S "$HELPER_SOCKET" ] && break; sleep 0.1; done
[ -S "$HELPER_SOCKET" ] || { echo "helper did not start" >&2; exit 1; }

# The web service runs as 'gateway' with no supplementary groups and no way to regain privileges.
setpriv --reuid=gateway --regid=gateway --clear-groups --no-new-privs \
  uvicorn --factory app.main:app_from_env --host 0.0.0.0 --port "${GATEWAY_PORT:-9100}" --no-access-log "${tls[@]}" &
web=$!

# If either process stops, stop the container (fail closed).
wait -n "$helper" "$web" 2>/dev/null || true
kill "$helper" "$web" 2>/dev/null || true
exit 1
