#!/bin/sh
# Nomad Pack deploy: write vars.hcl → nomad-pack render / plan / run.
# Invoked by nomad_deploy.sh when NOMAD_PACK_ENABLED=true (default).
# Replaces two-pass envsubst with typed pack vars + nomad-pack plan/run.
set -eo pipefail

echo "===== Nomad Pack deploy (NOMAD_PACK_ENABLED=true) ====="

NOMAD_PACK_DIR="${NOMAD_PACK_DIR:-deploy}"
PACK_DIR="${CI_PROJECT_DIR}/${NOMAD_PACK_DIR}"
if [ ! -d "$PACK_DIR" ]; then
  echo "Error - Nomad Pack not found = $PACK_DIR (NOMAD_PACK_DIR=${NOMAD_PACK_DIR})"
  exit 1
fi
echo "Pack directory = $PACK_DIR"

if ! command -v nomad-pack > /dev/null 2>&1; then
  echo "Error - nomad-pack not found; source nomad_setup.sh first"
  exit 1
fi
echo "✓ nomad-pack = $(nomad-pack version 2>&1 | head -1)"

# Deployment / job naming matches previous envsubst convention:
#   job "${__SERVICE__}-${__ENVIRONMENT__}"
DEPLOYMENT_NAME="${SERVICE_NAME}-${__ENVIRONMENT__}"
NOMAD_OUTPUT_FILE="${CI_PROJECT_DIR}/${DEPLOYMENT_NAME}.nomad"
VARS_FILE="${CI_PROJECT_DIR}/${DEPLOYMENT_NAME}.vars.hcl"

echo "Deployment name = $DEPLOYMENT_NAME"
echo "Output job file = $NOMAD_OUTPUT_FILE"
echo "Vars file = $VARS_FILE"

# Ensure Nomad Pack uses the same cluster credentials as the rest of CI
export NOMAD_ADDR="${NOMAD_ADDR:-$NOMAD_SERVER_ADDRESS}"
export NOMAD_TOKEN="${NOMAD_TOKEN:-$NOMAD_SERVER_TOKEN}"
export NOMAD_NAMESPACE="${NOMAD_NAMESPACE:-${__NAMESPACE__:-default}}"
echo "NOMAD_ADDR = $NOMAD_ADDR"
echo "NOMAD_NAMESPACE = $NOMAD_NAMESPACE"

# Escape for HCL double-quoted strings: \, ", and $ ($$ → literal $)
hcl_escape_string() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\$/$$/g'
}

# Escape $ for HCL heredoc interpolation only (runtime_env multiline block)
hcl_escape_heredoc() {
  printf '%s' "$1" | sed 's/\$/$$/g'
}

# __DATACENTERS__ is already an HCL list literal from CI (e.g. '["dc1"]')
DATACENTERS_HCL="${__DATACENTERS__:-[\"dc1\"]}"

# Traefik: pack templates own tag strings; routing only supplies hosts/flags
ENABLE_TRAEFIK_HCL="false"
if [ "${__ENABLE_TRAEFIK__:-false}" = "true" ]; then
  ENABLE_TRAEFIK_HCL="true"
fi

RUNTIME_ENV_ESCAPED=$(hcl_escape_heredoc "${__RUNTIME_ENV__:-}")
RUNTIME_SECRETS_ESCAPED=$(hcl_escape_heredoc "${__RUNTIME_SECRETS__:-}")

echo "===== Writing pack vars file ====="
echo "Note - Traefik tags are rendered in the pack (hostname; public_domain is frontend-only)"
echo "Note - runtime_env / runtime_secrets may contain pack snippets like [[ var \"nomad_environment_url\" . ]]; pack tpl expands them"
echo "Note - Nomad interpolations (e.g. \${NOMAD_PORT_http}, \${meta.role}) stay literal in the pack template"
echo "enable_traefik = ${ENABLE_TRAEFIK_HCL}, hostname = ${__HOSTNAME__:-}, public_domain = ${__PUBLIC_DOMAIN__:-}"

cat > "$VARS_FILE" <<EOF
service                 = "$(hcl_escape_string "${__SERVICE__:-$SERVICE_NAME}")"
environment             = "$(hcl_escape_string "${__ENVIRONMENT__}")"
namespace               = "$(hcl_escape_string "${__NAMESPACE__:-default}")"
count                   = ${__COUNT__:-1}
job_driver              = "$(hcl_escape_string "${__JOB_DRIVER__:-docker}")"
image_name              = "$(hcl_escape_string "${__IMAGE_NAME__}")"
image_tag               = "$(hcl_escape_string "${__IMAGE_TAG__}")"
image_force_pull        = "$(hcl_escape_string "${__IMAGE_FORCE_PULL__:-true}")"
registry_username       = "$(hcl_escape_string "${__USERNAME__:-}")"
registry_password       = "$(hcl_escape_string "${__PASSWORD__:-}")"
registry_server         = "$(hcl_escape_string "${__CI_REGISTRY__:-}")"
resource_cpu            = ${__RESOURCE_CPU__:-1000}
resource_memory         = ${__RESOURCE_MEMORY__:-1024}
datacenters             = ${DATACENTERS_HCL}
enable_traefik          = ${ENABLE_TRAEFIK_HCL}
router_name             = "$(hcl_escape_string "${__ROUTER_NAME__:-${SERVICE_NAME}}")"
hostname                = "$(hcl_escape_string "${__HOSTNAME__:-}")"
api_gateway             = "$(hcl_escape_string "${__API_GATEWAY__:-}")"
nomad_environment_url   = "$(hcl_escape_string "${__NOMAD_ENVIRONMENT_URL__:-}")"
runtime_env             = <<-EOT
${RUNTIME_ENV_ESCAPED}
EOT
runtime_secrets         = <<-EOT
${RUNTIME_SECRETS_ESCAPED}
EOT
EOF

# Frontend-only: optional PUBLIC_DOMAIN Host alias
if [ -f "$PACK_DIR/variables.hcl" ] && grep -q 'variable "public_domain"' "$PACK_DIR/variables.hcl"; then
  echo "Appending frontend-only var public_domain=${__PUBLIC_DOMAIN__:-}"
  cat >> "$VARS_FILE" <<EOF
public_domain           = "$(hcl_escape_string "${__PUBLIC_DOMAIN__:-}")"
EOF
fi

# Backend-only vars (only append when the pack declares them in variables.hcl)
if [ -f "$PACK_DIR/variables.hcl" ] && grep -q 'variable "health_base"' "$PACK_DIR/variables.hcl"; then
  echo "Appending backend-only vars (health_base, environment_sanitized)"
  cat >> "$VARS_FILE" <<EOF
health_base             = "$(hcl_escape_string "${__HEALTH_BASE__:-api}")"
environment_sanitized   = "$(hcl_escape_string "${__ENVIRONMENT_SANITIZED__:-default}")"
EOF
fi

echo "===== Pack vars file (password redacted) ====="
sed 's/registry_password.*/registry_password   = "***"/' "$VARS_FILE" || true

# Render pack to a .nomad artifact for CI logs (same path as the old envsubst output)
echo "===== Rendering Nomad Pack ====="
echo "Pack = $PACK_DIR"
echo "Name = $DEPLOYMENT_NAME"
nomad-pack render "$PACK_DIR" \
  --name="$DEPLOYMENT_NAME" \
  --var-file="$VARS_FILE" \
  --to-dir="${CI_PROJECT_DIR}/.nomad-pack-render" \
  --auto-approve

# Flatten rendered job into the artifact path expected by CI jobs (*.nomad)
RENDERED_JOB=$(find "${CI_PROJECT_DIR}/.nomad-pack-render" -name '*.nomad' -type f | head -1)
if [ -z "$RENDERED_JOB" ] || [ ! -f "$RENDERED_JOB" ]; then
  echo "Error - nomad-pack render produced no .nomad file"
  echo "===== Contents of render directory ====="
  find "${CI_PROJECT_DIR}/.nomad-pack-render" -type f 2>/dev/null || true
  exit 1
fi
cp "$RENDERED_JOB" "$NOMAD_OUTPUT_FILE"
echo "Copied rendered job = $RENDERED_JOB -> $NOMAD_OUTPUT_FILE"

echo "===== Rendered Nomad job ====="
cat "$NOMAD_OUTPUT_FILE"

# Plan: show what will change before submitting
# Exit codes: 0 = no changes, 1 = changes, 255 = error
echo "===== Planning Nomad Pack deployment ====="
set +e
nomad-pack plan "$PACK_DIR" \
  --name="$DEPLOYMENT_NAME" \
  --var-file="$VARS_FILE"
PLAN_EXIT=$?
set -e
if [ "$PLAN_EXIT" -eq 255 ] || [ "$PLAN_EXIT" -gt 1 ]; then
  echo "Error - nomad-pack plan failed with exit code $PLAN_EXIT"
  exit 1
fi
echo "nomad-pack plan exit code = $PLAN_EXIT (0=no changes, 1=changes)"

# Deploy to Nomad via Nomad Pack
echo "===== Deploying to Nomad (nomad-pack run) ====="
nomad-pack run "$PACK_DIR" \
  --name="$DEPLOYMENT_NAME" \
  --var-file="$VARS_FILE"

# nomad-pack run monitors the deployment similarly to 'nomad job run' (without -detach):
# when it returns successfully, Nomad considers the deployment healthy according to the
# job's update.health_check settings. Non-zero exit fails this GitLab job.
echo "===== Nomad Pack run completed; deployment is considered healthy by Nomad ====="
