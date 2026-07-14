# Agent Context

## Product Summary

This repository implements an access management system for brain research data used by the Institute for Neuroscience and Neurotechnology (INN).

The platform manages access to medical and research datasets such as brain scans and related studies. Data may be provided by Surrey Memorial Hospital, other institutional partners, or individual researchers. Some datasets are owned and managed directly by INN, while other datasets remain under the control of external partners.

The core purpose of the application is to give storage administrators a way to manage who can read, write, or delete data within specific folders or subfolders, without forcing every dataset into a single storage system.

## Core Domain Model

- The system manages access to sensitive brain research data.
- Data is organized in folder and subfolder hierarchies, with individual files also subject to access control.
- Access may be granted at folder, subfolder, or file scope.
- Storage admins can create users and assign permissions.
- Permissions include read, write, and delete.
- Different users may see different views based on their roles.

## Storage Model

The platform supports both INN-owned storage and partner-owned storage.

- INN-owned data is intended to live in an object storage system managed by this application.
- Partner-owned data may remain in the partner's own object storage or POSIX-based storage.
- The application must support distributed storage ownership rather than assuming all data is centrally hosted.
- A major product goal is to provide one governance and access layer across these heterogeneous storage backends.

In short, this platform does two things:

1. Manages access to external partner storage without requiring ownership transfer.
2. Manages INN's own storage and access controls for data hosted directly by INN.

## Authorization and Identity

The application separates identity, role presentation, and access policy concerns:

- Keycloak manages users and realm roles.
- Keycloak realm roles influence which views or UI surfaces a user can access.
- Casbin manages fine-grained authorization policies for storage paths and operations.
- Casbin policies determine whether a user can read, write, or delete within a folder tree or for specific files.

This distinction matters when changing the codebase:

- Keycloak is the source of identity and coarse-grained role information.
- Casbin is the source of path-level access control.
- UI visibility and storage authorization are related but not interchangeable.

## Current Stack

- Frontend: React
- Backend: FastAPI
- Identity and user management: Keycloak
- Authorization and policy enforcement: Casbin
- Storage backends: object storage and POSIX-style storage
- Instance/config persistence: MongoDB
- DB-backed file tree metadata: PostgreSQL
- Deployment/orchestration: HashiCorp Nomad
- Local development: Docker Compose

## Primary Working Assumption

Do not change the codebase unless the user has explicitly granted permission to make code changes.

Default to analysis, explanation, proposal, and code suggestions unless the user clearly asks for edits or approves implementation work.

## Architecture Summary

The backend is a FastAPI application mounted under the `/api` prefix.

Main backend route groups:

- `/api/auth` for token validation
- `/api/users` for user CRUD and instance listing
- `/api/policies` for policy CRUD
- `/api/instances` for storage instance CRUD
- `/api/assets` for presigned asset upload/download/delete and dashboard-style asset data
- `/api/tree` for DB-backed file tree endpoints
- `/api/health` for health and environment validation

The system currently has two overlapping ways to reason about storage trees:

- an in-memory tree cached inside storage agents
- a DB-backed tree using PostgreSQL tables for folders/files

Future changes must be explicit about which source of truth they touch.

## Persistence Boundaries

The application does not store everything in one database or one backend.

Different kinds of data are persisted in different systems. This is important and easy to miss.

- Keycloak stores users, credentials, and realm role assignments.
- MongoDB stores storage instance configurations.
- Casbin policies are persisted through the MongoDB Casbin adapter.
- PostgreSQL stores folder and file tree metadata used by the newer tree endpoints.
- Object storage stores the actual data files.

In practice, a single feature may need to coordinate across several systems:

1. Keycloak for identity and realm roles
2. Casbin for fine-grained path authorization
3. MongoDB for instance configuration
4. PostgreSQL for file tree metadata
5. Object storage for the real files and folders represented by the portal

Examples:

- creating a user mainly affects Keycloak
- creating or removing a policy affects Casbin policy data in MongoDB
- creating a storage instance affects MongoDB and also in-memory agent initialization
- uploading or deleting a file may affect both object storage and PostgreSQL tree metadata

## Storage Instance Model

Storage instances are managed through the backend `InstanceManager`.

- Instance definitions are loaded from MongoDB at startup.
- A storage agent is created in memory for each configured instance.
- The instance UUID is stable and derived from the instance name.
- The backend currently supports `s3` and `dummy` flavours in code.
- The admin UI currently exposes only `s3` creation.

Important behavior:

- Creating an instance also creates an in-memory storage agent.
- Creating an instance automatically grants the creating admin an `admin` Casbin policy on resource `.*`.
- Deleting an instance removes it from MongoDB and attempts to close the in-memory agent connection.

## Authorization Model In Practice

There are two separate authorization layers in the running system:

- Keycloak realm roles determine coarse-grained UI access.
- Casbin policies determine path-level storage access.

Current frontend behavior:

- users with the Keycloak realm role `admin` are routed to the admin interface
- non-admin users are routed to a minimal normal-user page

Current backend behavior:

- admin-only routes use FastAPI dependencies that require admin privileges from the token
- storage access checks are evaluated through `Policy(user_uuid, instance_uuid, resource, action)`
- access actions in active use include `read`, `write`, `delete`, and `admin`

Do not treat Keycloak admin role checks as a replacement for Casbin resource checks.

## Path And Resource Semantics

This codebase uses path-based authorization, and the exact path format matters.

- Policies target storage resources as strings.
- Resource strings may represent bucket roots, folders, or exact file keys.
- Some flows use regex-style matching for reads.
- S3 write/delete presigned URL generation expects an exact `bucket/key` resource.
- The DB-backed tree builds resource strings differently for folders and files:
  - folders use bucket + normalized full path
  - files use bucket + object key

When changing policy logic, pay close attention to:

- exact path formatting
- trailing slash normalization
- regex vs exact-match behavior
- whether the target is a folder subtree or a single file

## File Tree Model

The current file tree model uses a PostgreSQL-backed folder and file tree built with the `ltree` extension.

The repository still contains older object-storage-derived tree handling in some parts of the codebase, so both approaches may appear during maintenance work.

### Legacy / direct storage-derived tree

- Storage agents such as the S3 agent can build an in-memory file tree directly from object storage contents.
- This tree is used in older asset access flows.
- It is used for matching resource paths and generating presigned read URLs.
- It can be refreshed in memory, including a differential refresh path for S3.

### Newer PostgreSQL-backed tree

- The newer implementation stores folder and file metadata in PostgreSQL.
- It uses the PostgreSQL `ltree` extension to represent hierarchical paths.
- It is exposed by `/api/tree/dashboard/{instance_uuid}`.
- It supports folder and file-level nodes.
- Bucket roots are ensured during startup and policy creation flows.

The PostgreSQL-backed tree is the current direction of the codebase, while some older asset flows still rely on the in-memory tree built from object storage.

## Synchronization Requirement

Even in the newer design, the source files still live in object storage.

That means the PostgreSQL tree metadata must stay synchronized with object storage state.

When changing upload, delete, rename, or folder-management flows, treat synchronization between:

- object storage
- PostgreSQL file tree metadata

as a required correctness concern.

## Frontend Summary

The frontend is a React app using `@react-keycloak/web`.

- Keycloak is initialized with `check-sso`.
- The app uses `silent-check-sso.html` for silent session checks.
- The main router sends authenticated users to `/app`.
- The admin UI includes user, policy, asset, and storage management sections.
- The non-admin user UI is still very minimal.

Current admin pages:

- `user_management` for Keycloak user CRUD
- `policy_management` for Casbin policy CRUD
- `asset_management` for per-instance tree and asset actions
- `storage_management` for instance CRUD

The frontend uses bearer tokens from Keycloak and refreshes them with `updateToken(30)` before API calls.

## Asset Access Flow

The backend issues presigned URLs instead of proxying file content through the API.

- upload uses `/api/assets/upload`
- download uses `/api/assets/download`
- delete uses `/api/assets/delete`

Current behavior for the S3 agent:

- `read` can match multiple files through regex-style resource matching
- `write` and `delete` expect a single exact object path
- the backend returns presigned URLs plus corresponding file paths

This is a core product invariant. Avoid changes that move bulk data transfer into the backend unless explicitly intended.

## Bundler Service

The Bundler service handles server-side ZIP creation for multi-file or folder-style downloads.

Current flow:

- The frontend requests a bundle through the backend tree endpoint using selected file IDs.
- The backend remains responsible for identity, Casbin read authorization, file metadata lookup, and storage-specific access preparation.
- For the current S3-backed path, the backend generates short-lived presigned GET URLs for each authorized file and sends those URLs to Bundler.
- Bundler accepts bundle requests at `/bundles`, processes them asynchronously, downloads the provided URLs into local staging space, and creates a ZIP archive.
- Bundle status is polled through `/bundles/{bundleId}`.
- Completed archives are fetched through `/bundles/{bundleId}/download`; the backend streams that ZIP response back to the frontend.
- Bundler should not be treated as the authorization authority. It assumes the backend has already checked access before submitting URLs.
- Current implementation is URL-based and S3-oriented from the backend side; POSIX support should be added explicitly rather than assumed.

## Known Transitional Areas

Some parts of the repository are clearly in transition and should be handled carefully.

- There are legacy asset/dashboard endpoints alongside newer DB-backed tree endpoints.
- Policy deletion currently accepts UUIDs directly and includes comments marking this as temporary.
- The frontend normal-user experience is not yet feature-complete.
- The admin asset management flow appears to rely on user-instance discovery first, then per-instance tree loading.
- Some docs in the repo describe older file-based policy/config paths that no longer match the active MongoDB-backed implementation.

When changing these areas, document whether you are preserving backward compatibility or intentionally consolidating old and new paths.

## Local And Deployment Notes

- Local development is orchestrated with Docker Compose.
- Nomad job files exist for at least frontend and Keycloak deployment.
- The backend expects many critical environment variables, especially for Keycloak, MongoDB, PostgreSQL, and Casbin model configuration.
- The backend reads some secrets from `_FILE` environment variables when available.

For agent work, avoid assuming the local Docker setup and the deployed Nomad setup are identical in detail.

## Testing Notes

The backend has smoke and CRUD-oriented tests for:

- authentication
- policies
- Casbin migration behavior
- user CRUD

There is much less evidence of deep frontend test coverage.

Changes in these areas deserve extra care:

- auth/token validation
- Keycloak integration
- Casbin policy enforcement
- instance creation/deletion
- file tree path handling

## Important Implementation Assumptions


- Do not assume all data belongs to INN.
- Do not assume all storage backends are object storage.
- Do not collapse Keycloak roles and Casbin policies into one concern.
- Preserve path-based authorization semantics at both folder and file level.
- Treat storage ownership and access governance as separate concerns.
- Changes around auth, policy, or storage routing should be considered high risk.

## Guidance For Future Codex Work
When working in this repository, optimize for:

- preserving the separation between authentication, roles, and policy enforcement
- keeping storage integrations backend-agnostic where possible
- respecting hierarchical folder permissions and file-level access controls
- avoiding assumptions that all data is local or centrally controlled
- being explicit about whether a change affects INN-owned storage, partner-owned storage, or both
- preserving the presigned-URL model for storage access unless a change explicitly redesigns it
- being clear about whether a change targets the in-memory tree path, the PostgreSQL tree path, or both
- checking whether MongoDB, PostgreSQL, Keycloak, and Casbin all need coordinated updates

When proposing changes, call out impacts on:

- Keycloak role handling
- Casbin policy checks
- storage backend behavior
- folder/subfolder permission inheritance
- file-level access behavior and precedence
- cross-institution or partner-owned data access flows
- instance persistence in MongoDB
- DB-backed tree consistency in PostgreSQL
- presigned URL generation semantics
