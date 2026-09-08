#!/bin/sh
# Deploy entrypoint: chooses Nomad Pack (default) or legacy envsubst.
# Set NOMAD_PACK_ENABLED=false to use nomad_deploy_envsubst.sh.
set -eo pipefail

# Check if deployment is enabled
if [ "$NOMAD_DEPLOY_ENABLED" != "true" ]; then
  echo "Nomad deployment is disabled. Skipping..."
  exit 0
fi

# Feature flag: set NOMAD_PACK_ENABLED=false to use legacy envsubst templates.
# Pack root: $CI_PROJECT_DIR/$NOMAD_PACK_DIR (CI default "deploy"; services override).
NOMAD_PACK_ENABLED="${NOMAD_PACK_ENABLED:-true}"
NOMAD_PACK_DIR="${NOMAD_PACK_DIR:-deploy}"
export NOMAD_PACK_DIR

_SCRIPTS_DIR="${CI_PROJECT_DIR}/.gitlab/deploy/scripts"

if [ "$NOMAD_PACK_ENABLED" = "true" ]; then
  # shellcheck disable=SC1091
  . "$_SCRIPTS_DIR/nomad_deploy_pack.sh"
else
  # shellcheck disable=SC1091
  . "$_SCRIPTS_DIR/nomad_deploy_envsubst.sh"
fi
