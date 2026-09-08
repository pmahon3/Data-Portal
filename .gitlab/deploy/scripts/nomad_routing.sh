#!/bin/sh
# Shared Traefik / hostname policy, then Pack or legacy envsubst finishers.
# Set NOMAD_PACK_ENABLED=false to use nomad_routing_envsubst.sh.
# Temporarily disabled: set -eo pipefail
# set -eo pipefail

# Derive Traefik-safe name from __ENVIRONMENT__ (router names, path prefixes)
# Sanitize: lowercase, non-[a-z0-9] -> hyphen, collapse/trim hyphens (POSIX sed)
__ENVIRONMENT_SANITIZED__=$(echo "$__ENVIRONMENT__" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')
export __ENVIRONMENT_SANITIZED__="${__ENVIRONMENT_SANITIZED__:-default}"

# Review public host id (shared by Traefik Host; legacy also uses for API_GATEWAY Traefik URL).
# Mirrors Auto DevOps: $CI_PROJECT_ID-$CI_ENVIRONMENT_SLUG.$KUBE_INGRESS_BASE_DOMAIN
# where CI_ENVIRONMENT_SLUG is the DNS-safe slug of environment name review/<ref>
# (typically review-<branch>[-<unique>], truncated to 24 chars by GitLab).
# SERVICE_NAME is inserted so frontend/backend review apps in this monorepo
# do not share one Traefik Host (Auto DevOps assumes one app per project).
if [ "$NOMAD_ENVIRONMENT" = "review" ]; then
  if [ -n "${CI_ENVIRONMENT_SLUG}" ]; then
    __REVIEW_HOST_ID__="${CI_PROJECT_ID}-${SERVICE_NAME}-${CI_ENVIRONMENT_SLUG}"
  else
    # Fallback if environment: is missing (should not happen on the review job)
    __REVIEW_HOST_ID__="${CI_PROJECT_ID}-${SERVICE_NAME}-review-${CI_COMMIT_REF_SLUG}"
  fi
fi

# __RUNTIME_ENV__ is set in {service}/.gitlab-ci.yml from __RUNTIME_ENV_{BACKEND|FRONTEND}__.
# Extra Traefik Host (PUBLIC_DOMAIN) is frontend-only — never apply to backend/API jobs.
if [ "$SERVICE_NAME" = "frontend" ]; then
  export __PUBLIC_DOMAIN__="${PUBLIC_DOMAIN:-}"
else
  export __PUBLIC_DOMAIN__=""
fi
echo "Selected runtime environment (NOMAD_ENVIRONMENT=${NOMAD_ENVIRONMENT}) for ${SERVICE_NAME}"

# Determine if external (Traefik) access is needed.
# NOMAD_EXTERNAL_ACCESS=true|false overrides; unset → review/frontend defaults.
NEEDS_EXTERNAL_ACCESS="false"
case "$NOMAD_EXTERNAL_ACCESS" in
  true) NEEDS_EXTERNAL_ACCESS="true" ;;
  "") # unset or empty string
    if [ "$NOMAD_ENVIRONMENT" = "review" ] || [ "$SERVICE_NAME" = "frontend" ]; then
      NEEDS_EXTERNAL_ACCESS="true"
    fi
    ;;
esac

export __ROUTER_NAME__="${__SERVICE__:-$SERVICE_NAME}-${__ENVIRONMENT_SANITIZED__}"

if [ "$NEEDS_EXTERNAL_ACCESS" = "true" ]; then
  # Generate hostname based on environment
  if [ "$NOMAD_ENVIRONMENT" = "review" ]; then
    export __HOSTNAME__="${__REVIEW_HOST_ID__}.${NOMAD_DOMAIN:-example.com}"
  else
    export __HOSTNAME__="${SERVICE_NAME}-${NOMAD_ENVIRONMENT}.${NOMAD_DOMAIN:-example.com}"
  fi
  export NOMAD_ENVIRONMENT_URL="https://${__HOSTNAME__}"
  export __NOMAD_ENVIRONMENT_URL__=${NOMAD_ENVIRONMENT_URL}
  export __ENABLE_TRAEFIK__="true"
else
  # Internal access only via service discovery (no Traefik)
  export __HOSTNAME__=""
  export NOMAD_ENVIRONMENT_URL=""
  export __NOMAD_ENVIRONMENT_URL__=${NOMAD_ENVIRONMENT_URL}
  export __ENABLE_TRAEFIK__="false"
fi

# Path-specific finishers (tags / API_GATEWAY strategy)
NOMAD_PACK_ENABLED="${NOMAD_PACK_ENABLED:-true}"
_SCRIPTS_DIR="${CI_PROJECT_DIR}/.gitlab/deploy/scripts"

if [ "$NOMAD_PACK_ENABLED" = "true" ]; then
  # shellcheck disable=SC1091
  . "$_SCRIPTS_DIR/nomad_routing_pack.sh"
else
  # shellcheck disable=SC1091
  . "$_SCRIPTS_DIR/nomad_routing_envsubst.sh"
fi
