# Component Architecture

**Last updated:** 2026-09-08

## System Overview

High-level view of the AMS Data Portal components and their relationships.
The frontend communicates with the backend via REST APIs secured by Bearer tokens;
the backend delegates authentication to Keycloak and enforces access through
Casbin policies backed by a MongoDB adapter.

```mermaid
graph TB
    subgraph "User Layer"
        User[User Browser]
        Admin[Admin User]
    end

    subgraph "Frontend Layer"
        ReactUI[React Frontend<br/>Port 3000]
    end

    subgraph "Application Layer"
        Backend[Backend API<br/>FastAPI<br/>Port 8000]

        subgraph "Core Components"
            Auth[Authentication<br/>Module]
            Policy[Policy Manager<br/>Casbin RBAC]
            Instance[Instance Manager]
            Storage[Storage Agents]
        end
    end

    subgraph "Authentication Layer"
        Keycloak[Keycloak<br/>OIDC Provider<br/>Port 8080]
    end

    subgraph "Bundling Layer"
        Bundler[Bundler Service<br/>Java or Python<br/>BUNDLER_PROVIDER]
    end

    subgraph "Storage Backends"
        S3[S3-Compatible<br/>Storage]
        Dummy[Dummy Storage<br/>Testing]
    end

    User -->|HTTPS| ReactUI
    Admin -->|HTTPS| ReactUI
    ReactUI -->|REST API<br/>Bearer Token| Backend
    Backend -->|OIDC/OAuth2| Keycloak
    Backend -->|Enforces Policies| Policy
    Backend -->|Manages Instances| Instance
    Backend -->|Delegates Access| Storage
    Storage -->|Native Presigned URLs| S3
    Storage -->|Mock Operations| Dummy
    Backend -->|Source URLs, job status| Bundler
    Bundler -->|Reads sources, stores ZIP| S3
    User -.->|Downloads archive directly| S3

    style Backend fill:#4A90E2
    style Keycloak fill:#E94B3C
    style ReactUI fill:#61DAFB
    style Policy fill:#FFD700
    style Bundler fill:#95E1D3
```

## Backend Core Components

Detailed view of the backend application structure.

```mermaid
graph LR
    subgraph "API Layer v0.1"
        AuthAPI[Auth Endpoints]
        AssetAPI[Asset Access API]
        AdminAPI[Admin Endpoints]
        InstanceAPI[Instance Management API]
    end

    subgraph "Core Business Logic"
        ConnMgr[Connectivity<br/>Manager]
        PolicyMgr[Policy<br/>Manager]
        InstanceMgr[Instance<br/>Manager]
        UserMgr[User<br/>Manager]
    end

    subgraph "Storage Agents"
        S3Agent[S3 Storage<br/>Agent]
        DummyAgent[Dummy Storage<br/>Agent]
        AbstractAgent[Abstract Storage<br/>Agent Interface]
    end

    subgraph "External Services"
        KeycloakSvc[Keycloak<br/>Service]
        S3Backend[S3<br/>Backend]
        BundlerSvc[Bundler<br/>Service]
    end

    AuthAPI --> ConnMgr
    AssetAPI --> ConnMgr
    AdminAPI --> PolicyMgr
    AdminAPI --> UserMgr
    InstanceAPI --> InstanceMgr

    ConnMgr --> AbstractAgent
    InstanceMgr --> AbstractAgent
    AbstractAgent --> S3Agent
    AbstractAgent --> DummyAgent

    AuthAPI -.->|Validates Tokens| KeycloakSvc
    PolicyMgr -.->|Casbin Rules| PolicyMgr
    UserMgr -.->|CRUD Operations| KeycloakSvc
    S3Agent -.->|Presigned URLs| S3Backend
    AssetAPI -.->|Submit job, poll status| BundlerSvc

    style ConnMgr fill:#4A90E2
    style PolicyMgr fill:#FFD700
    style AbstractAgent fill:#95E1D3
```

## Policy Management Architecture

Casbin-based RBAC system with flexible policy enforcement.

```mermaid
graph TB
    subgraph "Policy Layer"
        CasbinEnforcer[Casbin Enforcer<br/>RBAC Model]
        ModelConf[model.conf<br/>RBAC Definition]
        PolicyCSV[policy.csv<br/>Access Rules]
    end

    subgraph "Policy Manager"
        PolicyMgr[Policy Manager]
        PolicyStore[(MongoDB<br/>Policy Store)]
    end

    subgraph "Access Control"
        CheckAccess[Check Access]
        GrantAccess[Grant Access]
        RevokeAccess[Revoke Access]
    end

    ModelConf --> CasbinEnforcer
    PolicyCSV --> CasbinEnforcer
    PolicyMgr --> CasbinEnforcer
    PolicyMgr --> PolicyStore

    CheckAccess --> CasbinEnforcer
    GrantAccess --> PolicyMgr
    RevokeAccess --> PolicyMgr

    BackendAPI[Backend API] --> CheckAccess
    AdminAPI[Admin API] --> GrantAccess
    AdminAPI --> RevokeAccess

    style CasbinEnforcer fill:#FFD700
    style PolicyMgr fill:#4A90E2
```

## Data Flow

There are two ways to take many files out of the system, and they differ in whether a
server touches the bytes.

**Manifest + client (no proxy).** `POST /api/tree/manifest` returns one presigned URL
per authorized file and nothing else; a client redeems them and fetches objects straight
from storage. The backend is out of the data path entirely, and an interrupted transfer
resumes per file. See *Bulk Manifest* and *Redeeming a manifest* in
`sequence-storage-access.md`.

**Bundler (server-side assembly).** For callers that need a single artifact - a browser
cannot write many files to a directory - the bundler takes presigned *source* URLs from
the backend, downloads those objects itself, writes a ZIP, and uploads it to object
storage.

Two implementations are selected by `BUNDLER_PROVIDER`, defaulting to `java`, and they
are **not** equivalent:

- `java-bundler/` (Spring Boot) presigns the finished archive, so the caller fetches it
  from object storage directly and archive bytes do not proxy back through a server.
  This is what the diagram below shows.
- `bundler/` (Python) returns the archive as a response body
  (`default_api_impl.py`), which streams the whole ZIP through the application server
  and holds it in memory. It also returns bytes where the backend's
  `/tree/bundle/{id}/download` expects JSON, so that endpoint is effectively java-only.

Either way the bundler downloads every source object before it can produce anything, so
it is unsuited to large transfers: use the manifest path for those.

```mermaid
graph LR
    User -->|Select files| Frontend
    Frontend -->|Bundle request + JWT| Backend
    Backend -->|Check access| Casbin
    Backend -->|Create source URLs| StorageAgent
    StorageAgent -->|Presigned URLs| Backend
    Backend -->|Start job w/ URLs| Bundler
    Bundler <-->|Read files / store ZIP| S3
    Frontend -.->|Poll status| Backend
    Backend -.->|Check job| Bundler
    Bundler -->|ZIP URL| Backend
    Backend -->|ZIP URL| Frontend
    Frontend -->|Download ZIP| S3

    style Backend fill:#4A90E2
    style Casbin fill:#FFD700
    style Bundler fill:#95E1D3
    style S3 fill:#FF9900
```

The manifest path has no equivalent middle. The backend issues references and stops:

```mermaid
graph LR
    Operator -->|Request manifest + JWT| Backend
    Backend -->|Check access| Casbin
    Backend -->|Create URLs| StorageAgent
    StorageAgent -->|Presigned URLs| Backend
    Backend -->|Manifest| Client["Transfer client"]
    Client <-->|GET w/ Range, resume| S3

    style Backend fill:#4A90E2
    style Casbin fill:#FFD700
    style Client fill:#95E1D3
    style S3 fill:#FF9900
```

---

## Component Responsibilities

### Frontend (React)
- User interface and interaction
- Authentication flow (OAuth2/OIDC)
- API communication with Bearer tokens
- File upload/download UI
- Admin dashboard

### Backend (FastAPI)
- REST API endpoints
- JWT token validation
- Policy enforcement via Casbin (MongoDB adapter)
- Storage agent coordination (factory pattern)
- User and instance management
- File-tree metadata service (PostgreSQL)

### Keycloak
- User authentication (OIDC)
- Token issuance (JWT)
- User management
- Role-based access control
- SSO support

### Storage Agents
- Abstract storage interface
- S3 presigned URL generation
- Secret encryption and lifecycle management
- Backend-specific operations

### Casbin Policy Engine
- RBAC policy enforcement
- Fine-grained access control
- Dynamic policy management
- Resource-level permissions
