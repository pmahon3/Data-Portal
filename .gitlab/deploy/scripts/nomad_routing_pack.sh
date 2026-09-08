#!/bin/sh
# Nomad Pack routing finishers.
# Expects shared policy already set by nomad_routing.sh:
#   __HOSTNAME__, __ENABLE_TRAEFIK__, __PUBLIC_DOMAIN__, __NOMAD_ENVIRONMENT_URL__,
#   __ROUTER_NAME__, __ENVIRONMENT_SANITIZED__, …
# Pack templates own Traefik tag strings from those scalars — no __SERVICE_TAGS__ / __HOST_RULE__.
#
# Nested deploy-time values for Nomad Pack `tpl` (not expanded here).
# __RUNTIME_ENV__ (from service CI → __RUNTIME_ENV_{BACKEND|FRONTEND}__) may use pack syntax, e.g.:
#   KEYCLOAK_REDIRECT_URI=[[ var "nomad_environment_url" . ]]
#   API_GATEWAY=http://{{- range nomadService "backend-[[ var "environment" . ]]" }}{{ .Address }}:{{ .Port }}{{- end }}
# Pack templates run: [[ tpl (var "runtime_env" .) . ]]
# Frontend pack may also default API_GATEWAY via service discovery in the .nomad.tpl;
# this safety net covers CI runtime_env that omits API_GATEWAY=.

# Do not set Traefik-host __API_GATEWAY__ here. Pack uses Nomad service discovery
# (cluster-internal Address:Port), not a public http://…NOMAD_DOMAIN URL.

# Frontend safety net: ensure API_GATEWAY uses Nomad service discovery when missing
if [ "$SERVICE_NAME" = "frontend" ]; then
  case "${__RUNTIME_ENV__}" in
    *API_GATEWAY=*) ;;
    *)
      # Pack tpl expands [[ var "environment" . ]]; Nomad later expands {{ range nomadService }}
      _api_gateway_line='API_GATEWAY=http://{{- range nomadService "backend-[[ var "environment" . ]]" }}{{ .Address }}:{{ .Port }}{{- end }}'
      export __RUNTIME_ENV__="${__RUNTIME_ENV__}
${_api_gateway_line}"
      ;;
  esac
fi
