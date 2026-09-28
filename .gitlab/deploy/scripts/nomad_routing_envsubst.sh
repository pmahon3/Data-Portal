#!/bin/sh
# Legacy envsubst routing finishers.
# Expects shared policy already set by nomad_routing.sh:
#   __HOSTNAME__, __ENABLE_TRAEFIK__, __PUBLIC_DOMAIN__, __ROUTER_NAME__,
#   __ENVIRONMENT_SANITIZED__, __REVIEW_HOST_ID__, SERVICE_NAME, NOMAD_ENVIRONMENT, …
# Builds __HOST_RULE__ / __SERVICE_TAGS__ for ${__SERVICE_TAGS__} in .template.nomad files,
# and Traefik-host __API_GATEWAY__ for frontend envsubst (public URL, not Nomad discovery).

# Frontend proxies /api/ to API_GATEWAY; it must match the backend's Traefik host or Traefik returns 418 (no route).
if [ "$SERVICE_NAME" = "frontend" ]; then
  if [ "$NOMAD_ENVIRONMENT" = "review" ]; then
    if [ -n "${CI_ENVIRONMENT_SLUG}" ]; then
      export __API_GATEWAY__="http://${CI_PROJECT_ID}-backend-${CI_ENVIRONMENT_SLUG}.${NOMAD_DOMAIN:-example.com}"
    else
      export __API_GATEWAY__="http://${CI_PROJECT_ID}-backend-review-${CI_COMMIT_REF_SLUG}.${NOMAD_DOMAIN:-example.com}"
    fi
  else
    export __API_GATEWAY__="http://backend-${NOMAD_ENVIRONMENT}.${NOMAD_DOMAIN:-example.com}"
  fi
fi

if [ "${__ENABLE_TRAEFIK__:-false}" = "true" ]; then
  # Host rule: primary hostname, optionally OR PUBLIC_DOMAIN
  if [ -n "$__PUBLIC_DOMAIN__" ]; then
    __HOST_RULE__="Host(\`${__HOSTNAME__}\`) || Host(\`${__PUBLIC_DOMAIN__}\`)"
  else
    __HOST_RULE__="Host(\`${__HOSTNAME__}\`)"
  fi

  # Create Traefik tags for envsubst (pack templates build tags from enable_traefik/hostname/public_domain)
  if [ "$SERVICE_NAME" = "frontend" ]; then
    __SERVICE_TAGS__=$(cat <<EOF
	[
		"${SERVICE_NAME}",
		"traefik.enable=true",
		"traefik.http.routers.${__ROUTER_NAME__}.rule=${__HOST_RULE__}",
		"traefik.http.routers.${__ROUTER_NAME__}.entrypoints=websecure",
		"traefik.http.routers.${__ROUTER_NAME__}.tls=true"
	]
EOF
)
  else
    __SERVICE_TAGS__=$(cat <<EOF
	[
		"${SERVICE_NAME}",
		"api",
		"traefik.enable=true",
		"traefik.http.routers.${__ROUTER_NAME__}.rule=${__HOST_RULE__} || PathPrefix(\`/api/${__ENVIRONMENT_SANITIZED__}\`)",
		"traefik.http.routers.${__ROUTER_NAME__}.entrypoints=websecure",
		"traefik.http.routers.${__ROUTER_NAME__}.tls=true"
	]
EOF
)
  fi
  export __SERVICE_TAGS__
else
  if [ "$SERVICE_NAME" = "frontend" ]; then
    __SERVICE_TAGS__=$(cat <<EOF
	[
		"${SERVICE_NAME}"
	]
EOF
)
  else
    __SERVICE_TAGS__=$(cat <<EOF
	[
		"${SERVICE_NAME}",
		"api"
	]
EOF
)
  fi
  export __SERVICE_TAGS__
fi
