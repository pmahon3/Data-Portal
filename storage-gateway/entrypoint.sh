#!/bin/bash
# Starts the privileged helper (root) and the web service (unprivileged, no access to the data).
# Layout on the data volume (/srv/posix):
#   data/     governed files: owner inndata, folders 0710 with group posix-traverse, files 0600
#   staging/  one folder per temporary ID for uploads in progress (outside the data tree)
#   .helper/  the helper's state (which IDs hold which grants), so a restart still revokes them
set -eu

mkdir -p /srv/posix/data /srv/posix/staging /srv/posix/.helper /run/gateway
chmod 0755 /srv/posix
chown inndata:posix-traverse /srv/posix/data && chmod 0710 /srv/posix/data
chown root:root /srv/posix/staging && chmod 0711 /srv/posix/staging
chown root:root /srv/posix/.helper && chmod 0700 /srv/posix/.helper
chown root:gateway /run/gateway && chmod 0750 /run/gateway

python -m app.helper &
helper=$!
for _ in $(seq 1 50); do [ -S "$HELPER_SOCKET" ] && break; sleep 0.1; done
[ -S "$HELPER_SOCKET" ] || { echo "helper did not start" >&2; exit 1; }

# The web service runs as 'gateway' with no supplementary groups and no way to regain privileges.
setpriv --reuid=gateway --regid=gateway --clear-groups --no-new-privs \
  uvicorn --factory app.main:app_from_env --host 0.0.0.0 --port 9100 --no-access-log &
web=$!

# If either process stops, stop the container (fail closed).
wait -n "$helper" "$web" 2>/dev/null || true
kill "$helper" "$web" 2>/dev/null || true
exit 1
