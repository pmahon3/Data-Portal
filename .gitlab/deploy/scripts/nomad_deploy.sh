#!/bin/sh
set -eo pipefail

# Check if deployment is enabled
if [ "$NOMAD_DEPLOY_ENABLED" != "true" ]; then
  echo "Nomad deployment is disabled. Skipping..."
  exit 0
fi

# Determine template file
if [ -z "$NOMAD_JOB_TEMPLATE" ]; then
  NOMAD_JOB_TEMPLATE=".gitlab/deploy/nomad-templates/${SERVICE_NAME}.template.nomad"
fi
if [ ! -f "$NOMAD_JOB_TEMPLATE" ]; then
  echo "Error - Nomad job template not found = $NOMAD_JOB_TEMPLATE"
  exit 1
fi

NOMAD_OUTPUT_FILE="${CI_PROJECT_DIR}/${SERVICE_NAME}-${__ENVIRONMENT__}.nomad"


# Substitute variables in template
echo "Extracting __*__ variables from template ($NOMAD_JOB_TEMPLATE)"
echo "Output file = $NOMAD_OUTPUT_FILE"

# GNU gettext envsubst format: '${VAR1} ${VAR2} ${VAR3}'
# Extract all ${__*__} patterns, get unique variable names (with __ prefix/suffix)
# Pattern matches: ${__VARIABLE_NAME__}
# Format string must contain variables with ${} wrapper
# Note: envsubst only replaces variables in the format string.
# Unspecified variables (like ${NOMAD_PORT_http}, ${meta.role}, ${node.unique.name})
# are left unchanged in the output.
echo "===== Pass 1: Substituting variables ======"
SHELL_FORMAT_STRING=$(grep -oE '\$\{__[A-Z_]+__\}' "$NOMAD_JOB_TEMPLATE" | \
  sort -u | \
  awk '{printf "%s ", $1}')

if [ -z "$SHELL_FORMAT_STRING" ]; then
  echo "Warning - No __*__ variables found in template"
fi

echo "Substituting variables = $SHELL_FORMAT_STRING"
echo "Note - Other variables (e.g. \${NOMAD_PORT_http}, \${meta.role}) will remain unchanged"
# GNU gettext envsubst format
envsubst "$SHELL_FORMAT_STRING" < "$NOMAD_JOB_TEMPLATE" > "${NOMAD_OUTPUT_FILE}".temp.nomad

echo "===== Pass 2: Substituting variables ======"
# in case a variable block contains another variable, we need to substitute again
SHELL_FORMAT_STRING=$(grep -oE '\$\{__[A-Z_]+__\}' "${NOMAD_OUTPUT_FILE}".temp.nomad | \
  sort -u | \
  awk '{printf "%s ", $1}')

if [ -z "$SHELL_FORMAT_STRING" ]; then
  echo "Warning - No __*__ variables found in template"
fi

echo "Substituting variables = $SHELL_FORMAT_STRING"
echo "Note - Other variables (e.g. \${NOMAD_PORT_http}, \${meta.role}) will remain unchanged"
# GNU gettext envsubst format
envsubst "$SHELL_FORMAT_STRING" < "${NOMAD_OUTPUT_FILE}".temp.nomad > "$NOMAD_OUTPUT_FILE"
rm "${NOMAD_OUTPUT_FILE}.temp.nomad"

nomad fmt "$NOMAD_OUTPUT_FILE" || {
  echo "===== Nomad job file is not formatted correctly ====="
  cat "$NOMAD_OUTPUT_FILE"
  exit 1
}

echo "===== Rendered Nomad job ====="
cat "$NOMAD_OUTPUT_FILE"

# Validate Nomad job
echo "===== Validating Nomad job ====="
nomad job validate \
  -address="$NOMAD_SERVER_ADDRESS" \
  -token="$NOMAD_SERVER_TOKEN" \
  -namespace="$__NAMESPACE__" \
  "$NOMAD_OUTPUT_FILE" || {
  echo "===== Nomad job file ====="
  cat "$NOMAD_OUTPUT_FILE"
  exit 1
}

# Deploy to Nomad
echo "===== Deploying to Nomad ====="
nomad job run \
  -address="$NOMAD_SERVER_ADDRESS" \
  -token="$NOMAD_SERVER_TOKEN" \
  -namespace="$__NAMESPACE__" \
  -verbose \
  "$NOMAD_OUTPUT_FILE"

# Nomad 'job run' (without -detach) already monitors the deployment
# until it is complete according to the job's update.health_check settings.
# By the time this command returns, Nomad reports a successful deployment.
# If the deployment/evaluation fails or is not healthy, 'nomad job run'
# exits with a non-zero status, causing this GitLab job to fail without
# any extra logic needed here.
echo "===== Nomad job run completed; deployment is considered healthy by Nomad ====="

