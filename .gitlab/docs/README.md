# Nomad Deployment Integration with Auto DevOps

This directory contains reusable templates and configurations for integrating HashiCorp Nomad with GitLab Auto DevOps pipelines.

## Overview

This integration allows you to:
- Use Auto DevOps for build, test, and security scanning
- Deploy to Nomad instead of Kubernetes (with future Kubernetes support)
- Support Review Apps with automatic cleanup
- Deploy to multiple environments (review, development, staging, production)
- Monitor applications with health checks and Prometheus/Grafana (placeholders)

## Architecture

### Directory Structure

```
.gitlab/deploy/
├── README.md                    # This file
├── Deploy.nomad.gitlab-ci             # Reusable GitLab CI templates for Nomad deployment
├── nomad-templates/             # Nomad job specification templates
│   ├── base-service.template.nomad      # Base template for any service
│   ├── frontend.template.nomad       # Frontend-specific template
│   └── backend.template.nomad        # Backend-specific template
└── scripts/                     # Helper scripts
    ├── deploy-nomad.sh          # Deployment script
    └── cleanup-review-app.sh    # Review App cleanup script
```

### Integration Approach

We use **Option C: Reusable Templates** with the ability to run parallel with Kubernetes:

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

### Environment Variables

Required (set in GitLab CI/CD settings):
- `NOMAD_SERVER_ADDRESS`: Nomad server endpoint
- `NOMAD_SERVER_TOKEN`: Nomad ACL token
- `NOMAD_NAMESPACE`: Nomad namespace

Optional:
- `NOMAD_DATACENTERS`: Comma-separated list (default: `["dc1"]`)
- `NOMAD_DEPLOY_ENABLED`: Enable Nomad deployment (default: `"true"`)
- `NOMAD_EXTERNAL_ACCESS`: Control external access per service (default: environment-based)
  - `"true"`: Always enable external access via Traefik
  - `"false"`: Always disable external access (internal only)
  - Not set: Uses defaults (review=true, production/staging/development=false for backend, frontend typically always true)

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

See [External Access Control](./EXTERNAL_ACCESS_CONTROL.md) for detailed documentation.

## Customization

### Custom Nomad Job Templates

1. Create a template in `.gitlab/deploy/nomad-templates/` with naming convention `*.template.nomad`
2. Use `envsubst` variables: `${__SERVICE__}`, `${__ENVIRONMENT__}`, etc.
3. The template will be processed to generate a `*.nomad` file
4. Reference it via `NOMAD_JOB_TEMPLATE` variable

### Traefik Routing

Configure routing in your Nomad job template:

```hcl
service {
  tags = [
    "traefik.enable=true",
    "traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT__}.rule=Host(`${__HOSTNAME__}`)",
    "traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT__}.entrypoints=websecure",
    "traefik.http.routers.${__SERVICE__}-${__ENVIRONMENT__}.tls=true",
  ]
}
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

