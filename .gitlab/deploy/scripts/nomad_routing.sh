#!/bin/sh
# Temporarily disabled: set -eo pipefail
# set -eo pipefail

# Derive Traefik-safe name from __ENVIRONMENT__ (router names, path prefixes)
# Sanitize: lowercase, non-[a-z0-9] -> hyphen, collapse/trim hyphens (POSIX sed)
__ENVIRONMENT_SANITIZED__=$(echo "$__ENVIRONMENT__" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')
export __ENVIRONMENT_SANITIZED__="${__ENVIRONMENT_SANITIZED__:-default}"

# Review public host id (shared by Traefik Host and frontend API_GATEWAY).
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

# Always inject runtime env (independent of Traefik / external access)
if [ "$SERVICE_NAME" = "frontend" ]; then
  SERVICE_TYPE="frontend"
  export __RUNTIME_ENV__="${__RUNTIME_ENV_FRONTEND__}"
  # Frontend proxies /api/ to API_GATEWAY; it must match the backend's Traefik host or Traefik returns 418 (no route).
  if [ "$NOMAD_ENVIRONMENT" = "review" ]; then
    if [ -n "${CI_ENVIRONMENT_SLUG}" ]; then
      export __API_GATEWAY__="http://${CI_PROJECT_ID}-backend-${CI_ENVIRONMENT_SLUG}.${NOMAD_DOMAIN:-example.com}"
    else
      export __API_GATEWAY__="http://${CI_PROJECT_ID}-backend-review-${CI_COMMIT_REF_SLUG}.${NOMAD_DOMAIN:-example.com}"
    fi
  else
    export __API_GATEWAY__="http://backend-${NOMAD_ENVIRONMENT}.${NOMAD_DOMAIN:-example.com}"
  fi
else
  SERVICE_TYPE="backend"
  export __RUNTIME_ENV__="${__RUNTIME_ENV_BACKEND__}"
fi
echo "Selected runtime environment (NOMAD_ENVIRONMENT=${NOMAD_ENVIRONMENT}) for ${SERVICE_TYPE}"

# Determine if external (Traefik) access is needed
NEEDS_EXTERNAL_ACCESS="false"

if [ -n "$NOMAD_EXTERNAL_ACCESS" ]; then
  if [ "$NOMAD_EXTERNAL_ACCESS" = "true" ]; then
    NEEDS_EXTERNAL_ACCESS="true"
  fi
else
  # Defaults: Review Apps and frontend always need external access
  if [ "$NOMAD_ENVIRONMENT" = "review" ] || [ "$SERVICE_NAME" = "frontend" ]; then
    NEEDS_EXTERNAL_ACCESS="true"
  fi
fi

if [ "$NEEDS_EXTERNAL_ACCESS" = "true" ]; then
  # Generate hostname based on environment
  if [ "$NOMAD_ENVIRONMENT" = "review" ]; then
    export __HOSTNAME__="${__REVIEW_HOST_ID__}.${NOMAD_DOMAIN:-example.com}"
  else
    export __HOSTNAME__="${SERVICE_NAME}-${NOMAD_ENVIRONMENT}.${NOMAD_DOMAIN:-example.com}"
  fi
  export NOMAD_ENVIRONMENT_URL="https://${__HOSTNAME__}"
  export __NOMAD_ENVIRONMENT_URL__=${NOMAD_ENVIRONMENT_URL}

  # Build Traefik tags
  if [ "$SERVICE_TYPE" = "frontend" ]; then
    export __SERVICE_TAGS__="[\"${SERVICE_TYPE}\",\"traefik.enable=true\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.rule=Host(\`${__HOSTNAME__}\`)\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.entrypoints=websecure\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.tls=true\"]"
  else
    export __SERVICE_TAGS__="[\"${SERVICE_TYPE}\",\"api\",\"traefik.enable=true\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.rule=Host(\`${__HOSTNAME__}\`) || PathPrefix(\`/api/${__ENVIRONMENT_SANITIZED__}\`)\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.entrypoints=websecure\",\"traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT_SANITIZED__}.tls=true\"]"
  fi
else
  # Internal access only via service discovery (no Traefik)
  export __HOSTNAME__=""
  export NOMAD_ENVIRONMENT_URL=""
  export __NOMAD_ENVIRONMENT_URL__=${NOMAD_ENVIRONMENT_URL}
  export __SERVICE_TAGS__='["api"]'
fi
