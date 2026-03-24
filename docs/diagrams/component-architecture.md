# Component Architecture

## System Overview

High-level view of the AMS Data Portal components and their relationships.

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

    style Backend fill:#4A90E2
    style Keycloak fill:#E94B3C
    style ReactUI fill:#61DAFB
    style Policy fill:#FFD700
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
        PolicyStore[Policy Storage<br/>JSON Files]
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

How data moves through the system for a typical file download request.

```mermaid
graph LR
    User[User] -->|1. Request File| Frontend
    Frontend -->|2. API Call + JWT| Backend
    Backend -->|3. Validate Token| Keycloak
    Keycloak -->|4. User Info| Backend
    Backend -->|5. Check Policy| Casbin
    Casbin -->|6. ALLOW| Backend
    Backend -->|7. Get Presigned URL| StorageAgent
    StorageAgent -->|8. Generate URL| S3
    S3 -->|9. Presigned URL| StorageAgent
    StorageAgent -->|10. URL| Backend
    Backend -->|11. URL Response| Frontend
    Frontend -->|12. Redirect| User
    User -->|13. Direct Download| S3

    style Backend fill:#4A90E2
    style Keycloak fill:#E94B3C
    style Casbin fill:#FFD700
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
- Policy enforcement (Casbin)
- Storage agent coordination
- User and instance management

### Keycloak
- User authentication (OIDC)
- Token issuance (JWT)
- User management
- Role-based access control
- SSO support

### Storage Agents
- Abstract storage interface
- S3 presigned URL generation
- File tree loading
- Backend-specific operations

### Casbin Policy Engine
- RBAC policy enforcement
- Fine-grained access control
- Dynamic policy management
- Resource-level permissions

---

**Last Updated:** 2025-10-23
