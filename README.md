# AMS Data Portal

**Policy-Driven Data Access Management Platform for Decentralized and Heterogeneous Storage Instances**

A modular platform that enables secure, policy-driven collaboration across institutional boundaries while preserving data sovereignty. Designed to support the full research lifecycle - from data collection and analysis to collaboration and external sharing - the system accommodates diverse organizational needs through flexible deployment models: institutions can participate in a shared governance instance for collaborative convenience, or self-host their own instance for complete control over authentication, authorization, and policy infrastructure.

Data never leaves the owner's storage infrastructure; the platform provides only the access control layer while data remains on owner-controlled systems. This separation of governance from storage enables multi-institutional research collaboration across heterogeneous storage backends, bridging diverse systems into a unified governance layer without requiring data migration or storage consolidation. Each data owner defines and enforces their own access policies through administrative tools, enabling controlled sharing and external system integration while maintaining compliance with institutional requirements for sensitive datasets. The architecture respects data sovereignty at both the deployment level (who operates the governance platform) and the data level (who controls access policies for their assets).

## Developed By

**Institute for Neuroscience and Neurotechnology (INN) & Research Computing Group (RCG)**
- Consultation: [jpeltier@sfu.ca](mailto:jpeltier@sfu.ca), [kshen@sfu.ca](mailto:kshen@sfu.ca)
- Deployment Engineer: [aensan@sfu.ca](mailto:aensan@sfu.ca)
- Principal Architect: [pmahon@sfu.ca](mailto:pmahon@sfu.ca)

For detailed information, see the [project wiki](https://github.com/INN-SFU/Data-Portal/wiki).

## Documentation

📐 **Architecture Diagrams:**
- [Component Architecture](./docs/diagrams/component-architecture.md) - System structure and relationships
- [Authentication Sequences](./docs/diagrams/sequence-authentication.md) - Login, token validation, admin operations
- [Storage Access Sequences](./docs/diagrams/sequence-storage-access.md) - File operations and access control
- [All Diagrams](./docs/diagrams/) - Complete visual documentation

## Features

**Governance & Access Control:**
- **Policy-Based Authorization**: Fine-grained access control enabling data owners to define and enforce custom access policies for their assets, supporting delegation and role-based permissions
- **Heterogeneous Storage Support**: Unified access layer across diverse storage backends (S3-compatible, object storage) without requiring data migration or centralization
- **Presigned URL Access**: Secure, time-limited direct access to files, enabling controlled external sharing while maintaining audit trails

**Authentication & Identity:**
- **Institutional Identity Integration**: Standards-based authentication (OIDC/OAuth2) allowing organizations to integrate with existing identity providers and authentication infrastructure
- **Flexible Deployment Models**: Support for both shared governance instances and self-hosted deployments with complete control over authentication and authorization infrastructure

**Developer & Operations:**
- **RESTful API**: Well-documented API with automatic OpenAPI specification, enabling integration with institutional workflows and custom applications
- **Containerized Architecture**: Production-ready Docker deployment with service orchestration, health monitoring, and automated configuration

## Project Structure

**Main Directories:**
- `backend/` - Main backend service with FastAPI application
  - `api/v0_1/endpoints/` - API routes
  - `core/connectivity/` - Storage agents (S3, Dummy)
  - `core/services/` - Instances, policies, users, file and tree handling
  - `core/settings/` - Configuration
- `frontend/` - React application
- `local/keycloak/` - Keycloak configuration and realm export
- `deployment/` - Production configurations
- `docs/diagrams/` - Mermaid architecture diagrams

For detailed system architecture, see [Architecture Diagrams](./docs/diagrams/).

## API Reference

### Endpoints

All endpoints use the `/api` prefix.

**Authentication:**
- `GET /api/auth/validate` - Validate JWT token

**Asset Management:**
- `PUT /api/asset/upload` - Upload file
- `PUT /api/asset/download` - Download file
- `GET /api/asset/user-home-data` - User home directory
- `GET /api/asset/user-assets-data` - User assets list

**Users:**
- `GET /api/users/{username}/instances` - Get user's available storage instances

**Administration (all require admin privileges):**
- `GET /api/users/` - List users
- `POST /api/users/` - Create user
- `DELETE /api/users/{username}` - Delete user
- `GET /api/policies/` - List policies
- `POST /api/policies/` - Add policy
- `DELETE /api/policies/` - Remove policy
- `GET /api/instances/` - List storage instances
- `POST /api/instances/` - Create storage instance
- `GET /api/instances/{uuid}` - Get instance details
- `DELETE /api/instances/{uuid}` - Delete storage instance
- `GET /api/assets/dashboard/{instance}` - Get specific storage instance assets by UUID

**Health Monitoring:**
- `GET /api/health/` - Basic health
- `GET /api/health/detailed` - Detailed status
- `GET /api/health/ready` - Readiness probe
- `GET /api/health/live` - Liveness probe

### Authentication Flow

**React Frontend Integration:**

```javascript
// 1. Authenticate with Keycloak
const token = await keycloak.getToken();

// 2. Call API with Bearer token
const response = await fetch('/api/users/', {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
```

**Token Claims Available:**
- `preferred_username` - Username
- `sub` - User UUID
- `email` - Email address
- `realm_access.roles` - User roles
- `exp`, `iat` - Token expiration

## Development

### Environment Variables

Key configuration variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AMS_HOST` | Backend bind address | `0.0.0.0` |
| `AMS_PORT` | Backend port | `8000` |
| `KEYCLOAK_DOMAIN` | Keycloak URL | `http://localhost:8080` |
| `KEYCLOAK_REALM` | Realm name | `ams-portal` |

## Deployment

### Docker Compose (Development)

```bash
# Start all services
cd backend
docker compose -f docker-compose.dev-all.yml up -d

# View logs
docker compose -f docker-compose.dev-all.yml logs -f

# Stop services
docker compose -f docker-compose.dev-all.yml down
```

### Production

See `deployment/` directory for production configurations:
- `docker-compose.yml` - Production orchestration
- `docker-compose.prod.yml` - Production overrides

**Production checklist:**
- [ ] Configure HTTPS/SSL certificates
- [ ] Set secure passwords (not default `admin123`)
- [ ] Configure external PostgreSQL for Keycloak
- [ ] Set up log aggregation
- [ ] Configure backup strategy for policies and user data
- [ ] Enable container security scanning

## Troubleshooting

### Common Issues

**Backend won't start**
```bash
# Check Keycloak is running
docker ps | grep keycloak

# View backend logs
docker logs ams-backend

# Verify network exists
docker network ls | grep ams-network
```

**Authentication failing**
```bash
# Check Keycloak initialization
docker logs ams-backend | grep "Keycloak configured"

# Restart backend
docker restart ams-backend
```

**Storage access denied**
- Verify user has appropriate Casbin policies
- Check storage instance configuration
- Confirm S3 credentials are valid

**Docker issues**
```bash
# Clean restart
docker compose -f backend/docker-compose.dev-all.yml down -v
docker network create ams-network
docker compose -f backend/docker-compose.dev-all.yml up -d
```

### Logs

- **Docker**: `docker compose -f backend/docker-compose.dev-all.yml logs -f`
- **Local**: `backend/logs/`

## Security

- **Secrets Management**: Base64-encoded secrets stored separately
- **Authentication**: OAuth2/OIDC via Keycloak
- **Authorization**: RBAC with Casbin policy engine
- **Presigned URLs**: Time-limited, signature-validated storage access
- **Container Security**: Non-root users, minimal base images
- **Network Isolation**: Docker networking for service isolation

## Contributing

1. Create feature branch from `main`
2. Ensure code follows project conventions
3. Submit pull request with clear description

## License

Apache 2.0 License - see [LICENSE](LICENSE) file for details.
