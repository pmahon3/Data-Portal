# Nomad Deployment Integration with Auto DevOps

This directory documents how HashiCorp Nomad deploys integrate with GitLab Auto DevOps pipelines in this monorepo.

## Overview

This integration allows you to:
- Use Auto DevOps for build, test, and security scanning
- Deploy to Nomad instead of Kubernetes (with future Kubernetes support)
- Support Review Apps with automatic cleanup
- Deploy to multiple environments (review, development, staging, production)
- Monitor applications with health checks and Prometheus/Grafana (placeholders)

## Architecture

- Auto DevOps still owns build/test/scan and job names (`review`, `staging`, `production`, `deploy:development`, rollouts).
- Deploy jobs live in [`.gitlab/deploy/Deploy.nomad.gitlab-ci.yml`](../deploy/Deploy.nomad.gitlab-ci.yml).
- Routing policy (Traefik hosts, review host ids, runtime env selection) stays in [`nomad_routing.sh`](../deploy/scripts/nomad_routing.sh).
- Job render + submit uses **Nomad Pack** via [`nomad_deploy.sh`](../deploy/scripts/nomad_deploy.sh) (replaces two-pass `envsubst`).

## Directory structure

```text
.gitlab/deploy/
├── Deploy.nomad.gitlab-ci.yml   # Auto DevOps-shaped deploy jobs
├── packs/                       # Nomad Pack definitions (source of truth)
│   ├── backend/
│   │   ├── metadata.hcl
│   │   ├── variables.hcl
│   │   └── templates/backend.nomad.tpl
│   └── frontend/
│       ├── metadata.hcl
│       ├── variables.hcl
│       └── templates/frontend.nomad.tpl
├── nomad-templates/             # DEPRECATED envsubst templates (rollback only)
└── scripts/
    ├── nomad_setup.sh           # Installs nomad-pack; checks Nomad connectivity
    ├── nomad_routing.sh         # Traefik / runtime env policy
    └── nomad_deploy.sh          # Writes vars.hcl → nomad-pack plan/run
```

### Integration Approach

We use **Reusable Templates** with the ability to run parallel with Kubernetes:

1. **Extend Auto DevOps**: Our templates extend Auto DevOps jobs, maintaining compatibility
2. **Override Deploy Stage**: We override the `.deploy` job from Auto DevOps to use Nomad
3. **Parallel Support**: Templates are designed to work alongside Kubernetes deployments (future)
4. **Modular Design**: Each component can be reused across projects

## Key Features

### 1. Environment Mapping

Branches map to environments:
- `main` → `production`
- `development` → `development`
- `staging` → `staging`
- Feature branches/PRs → `review` (temporary)

### 2. Review Apps

- **Naming**: `review-pr-<id>`, `review-<branch-name>` (hyphenated, not slash-separated)
- **Cleanup**: Automatic cleanup on MR close/merge (following Auto DevOps patterns)
- **Routing**: Dynamic subdomain and path-based routing via Traefik

### 3. Health Checks

- Nomad service health checks
- Readiness probes
- Integration with monitoring systems

### 4. Monitoring

- Placeholders for Prometheus metrics
- Placeholders for Grafana dashboards
- Per-environment monitoring support

## Deploy flow

1. `nomad_setup.sh` — ensure `nomad-pack` on `PATH`, map `NOMAD_ADDR`/`NOMAD_TOKEN`.
2. `nomad_routing.sh` — set `__RUNTIME_ENV__`, `__SERVICE_TAGS__`, `__HOSTNAME__`, `__API_GATEWAY__`.
3. `nomad_deploy.sh` — write `${SERVICE_NAME}-${__ENVIRONMENT__}.vars.hcl`, `nomad-pack render` (CI artifact), `plan`, `run` with `--name=${SERVICE_NAME}-${__ENVIRONMENT__}`.

Set `NOMAD_PACK_ENABLED=false` to force the legacy `envsubst` + `.template.nomad` path (temporary rollback).

## Usage

### Basic Setup

Include the deployment template in your service's `.gitlab-ci.yml`:

```yaml
include:
  - template: Auto-DevOps.gitlab-ci.yml
  - local: '/.gitlab/deploy/Deploy.nomad.gitlab-ci'

variables:
  NOMAD_DEPLOY_ENABLED: "true"
  SERVICE_NAME: "backend"  # or "frontend"
```

## Pack variables

Defaults live in each pack’s `variables.hcl`. CI overrides them through the vars file written by `nomad_deploy.sh`:

| Pack var | Typical CI source |
|---|---|
| `service` | `SERVICE_NAME` / `__SERVICE__` |
| `environment` | `__ENVIRONMENT__` (e.g. `staging`, `review-<slug>`) |
| `datacenters` | `NOMAD_DATACENTERS` / `__DATACENTERS__` (HCL list) |
| `namespace` | `NOMAD_NAMESPACE` |
| `image_name` / `image_tag` | registry image + commit SHA |
| `service_tags` | built by `nomad_routing.sh` (Traefik or `["api"]`) |
| `runtime_env` | `__RUNTIME_ENV_BACKEND__` / `__RUNTIME_ENV_FRONTEND__` (may embed pack `[[ var … ]]` snippets; expanded by `tpl`) |
| `api_gateway` / `nomad_environment_url` / `hostname` | from `nomad_routing.sh` (for `tpl` inside `runtime_env`) |
| `resource_cpu` / `resource_memory` / `count` | `NOMAD_RESOURCE_*` / `NOMAD_COUNT` |
| `health_base` / `secret_encryption_key` | backend pack only |

**Nested values in runtime env (Nomad Pack):** use pack syntax in CI blobs, not `${__*__}`:

```text
KEYCLOAK_REDIRECT_URI=[[ var "nomad_environment_url" . ]]
API_GATEWAY=[[ var "api_gateway" . ]]
```

Pack templates evaluate these with `[[ tpl (var "runtime_env" .) . ]]`. No GitLab escaping is needed for `[[ … ]]` (no `$`). Keep `${DATABASE_URL}`-style refs for values GitLab should expand at job start.

Nomad interpolations such as `${meta.role}`, `${NOMAD_PORT_http}`, and `${NOMAD_SECRETS_DIR}` stay literal in `.nomad.tpl` files.

## How to add a new service pack

1. Copy `.gitlab/deploy/packs/backend` (or `frontend`) to `.gitlab/deploy/packs/<service>/`.
2. Update `metadata.hcl` `pack.name` and adjust `templates/*.nomad.tpl` (ports, health paths, secrets).
3. Declare defaults in `variables.hcl`.
4. Set `SERVICE_NAME: "<service>"` in that service’s `.gitlab-ci.yml` so deploy resolves `.gitlab/deploy/packs/<service>`.
5. Dry-run locally:

```bash
nomad-pack render .gitlab/deploy/packs/<service> \
  --name=<service>-staging \
  --var-file=/path/to/sample.vars.hcl \
  --to-dir=/tmp/pack-out --auto-approve
```

## Review Apps cleanup

`stop_review` calls `nomad-pack destroy` with `--name=${SERVICE_NAME}-review-${CI_COMMIT_REF_SLUG}` (same convention as deploy), then falls back to `nomad job stop -purge`.

## Environment variables

Required (GitLab CI/CD settings):

- `NOMAD_SERVER_ADDRESS`
- `NOMAD_SERVER_TOKEN`

Optional:
- `NOMAD_DEPLOY_ENABLED`: Enable Nomad deployment suite (default `true`)
- `NOMAD_PACK_ENABLED` (default `true`; set `false` for envsubst rollback)
- `NOMAD_PACK_VERSION` (default `0.4.2` when setup installs the binary)
- `NOMAD_EXTERNAL_ACCESS`: Control external access per service (`true`/`false`, or unset for environment defaults)
- `NOMAD_DATACENTERS`: Control external access per service (default: environment-based)
- `NOMAD_RESOURCE_CPU`, `NOMAD_RESOURCE_MEMORY`, `NOMAD_COUNT`

### Service-Specific Configuration

Each service can override default behavior:

```yaml
variables:
  SERVICE_NAME: "backend"
  NOMAD_JOB_TEMPLATE: ".gitlab/deploy/nomad-templates/backend.template.nomad"
  NOMAD_RESOURCE_CPU: "1000"
  NOMAD_RESOURCE_MEMORY: "1024"
  # Control external access per service
  NOMAD_EXTERNAL_ACCESS: "true"  # Enable external access (or "false" to disable)
```

**External Access Control Examples:**

```yaml
# Frontend: Always needs external access
variables:
  SERVICE_NAME: "frontend"
  NOMAD_EXTERNAL_ACCESS: "true"  # Explicitly enable

# Backend API: External access in review, internal in production
variables:
  SERVICE_NAME: "api-gateway"
  # NOMAD_EXTERNAL_ACCESS not set - uses defaults (review=true, production=false)

# Internal service: Never needs external access
variables:
  SERVICE_NAME: "data-service"
  NOMAD_EXTERNAL_ACCESS: "false"  # Always internal only
```


## Future Enhancements

- [ ] Kubernetes parallel deployment support
- [ ] Prometheus metrics scraping configuration
- [ ] Grafana dashboard auto-provisioning
- [ ] Advanced health check strategies
- [ ] Multi-region deployment support

## References

- [GitLab Auto DevOps](https://docs.gitlab.com/ee/topics/autodevops/)
- [GitLab Review Apps](https://docs.gitlab.com/ci/review_apps/)
- [HashiCorp Nomad](https://www.nomadproject.io/docs)
- [Nomad Service Discovery](https://www.nomadproject.io/docs/service-discovery)

- [Nomad Pack](https://developer.hashicorp.com/nomad/tools/nomad-pack)
