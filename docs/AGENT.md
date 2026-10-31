# Agent Context

Context for anyone, human or AI agent, working in this repository. It grows with use: when you learn
something about the codebase or a way of working that the next person would want, add it here, and
fix or remove what has stopped being true. Keep entries short and concrete. Name the person or
ticket behind a rule when that helps someone ask about it later.

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
- `/api/tree` for DB-backed file tree endpoints
- `/api/notifications` for the current user's notifications
- `/api/health` for health and environment validation

The system currently has two overlapping ways to reason about storage trees:

- an in-memory tree cached inside storage agents
- a DB-backed tree using PostgreSQL tables for folders/files

Future changes must be explicit about which source of truth they touch.

## Persistence Boundaries

The application does not store everything in one database or one backend.

Different kinds of data are persisted in different systems. This is important and easy to miss.

- Keycloak stores users, credentials, and realm role assignments.
- MongoDB stores storage instance configurations, notifications (`notifications`), bundle owners (`bundle-owners`), and dataset check results (`dataset-checks`).
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
- Creating an instance automatically grants the creating admin an `admin` policy on the whole instance (`*`). Nothing checks the `admin` action on files; file access comes from `read`, `write` and `delete` grants.
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

- Policies target storage resources as literal strings: one file (`bucket/key`), a
  folder and everything in it (`bucket/folder/*`), or `*` for the whole instance.
- Every decision goes through `backend/core/services/policies/rules.py`:
  - `allows(path, action)`: may the user act on the path (used by every action);
  - `shows_folder(folder, action)`: does the folder appear when browsing for that
    action (the user holds the action on it or on something inside). Seeing a folder
    never allows acting on it.
- Build one checker per request (`policy_manager.checker(user, instance)`) and reuse it
  for every path the request checks.
- S3 write/delete presigned URL generation expects an exact `bucket/key` resource.
- The DB-backed tree builds resource strings differently for folders and files:
  - folders use bucket + normalized full path
  - files use bucket + object key

When changing policy logic, pay close attention to:

- exact path formatting
- trailing slash normalization
- whether the target is a folder subtree or a single file
- whether a check is about acting on a path or only browsing to it

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

- upload: `/api/tree/files/upload/init`, the browser PUTs to the URL, then `/api/tree/files/upload/complete` (folders: `/api/tree/folders/upload/...`)
- download: `/api/tree/files/{file_id}/download-url`; several files: `/api/tree/bundle/zip`
- delete: `DELETE /api/tree/files/{file_id}` or `/api/tree/folders/{folder_id}`

Current behavior for the S3 agent:

- `read` can cover many files through a folder policy (`bucket/folder/*`); policy paths are literal
- `write` and `delete` expect a single exact object path
- the backend returns presigned URLs plus corresponding file paths

This is a core product invariant. Avoid changes that move bulk data transfer into the backend unless explicitly intended.

## Bundler Service

The Java bundler (`java-bundler/`) handles server-side ZIP creation for multi-file or folder-style downloads.

Current flow:

- The frontend requests a bundle through the backend tree endpoint using selected file IDs.
- The backend remains responsible for identity, Casbin read authorization, file metadata lookup, and storage-specific access preparation.
- For the current S3-backed path, the backend generates short-lived presigned GET URLs for each authorized file and sends those URLs to Bundler.
- Bundler accepts bundle requests at `/bundles`, processes them asynchronously, downloads the provided URLs into local staging space, and creates a ZIP archive.
- Bundle status is polled through `/bundles/{bundleId}`.
- `/bundles/{bundleId}/download` returns a presigned URL for the completed archive in object storage; the backend passes that URL to the frontend.
- Bundler should not be treated as the authorization authority. It assumes the backend has already checked access before submitting URLs.
- A bundle belongs to the user who created it: the backend records the owner and the bundle's files, and refuses anyone else. When the bundle is fetched, every file in it is checked again, so revoked access or a deleted file stops the download (INN-272). Owner records expire after `BUNDLE_OWNER_RETENTION_HOURS` (192, a day past the bundler's 7-day retention).
- Current implementation is URL-based and S3-oriented from the backend side; POSIX support should be added explicitly rather than assumed.

## Notifications

Completing an upload records a notification for the user (MongoDB `notifications`), listed at
`GET /api/notifications/` and in the navbar bell. Each notification also goes to every channel in
`core/services/notifications`; email is the only one, off until `SMTP_HOST` is set, and never names
files, since file names can identify participants. See `docs/diagrams/notifications.md` and NT-1 in
`docs/requirements/notifications.md`.

## Data Standards

A folder holding a standard's marker file at its root declares that standard (BIDS:
`dataset_description.json`). When an upload completes, `core/services/standards` checks every
declared dataset it touched, as a whole, by file names and layout from the PostgreSQL tree (no file
contents). A failure puts the dataset in quarantine (MongoDB `dataset-checks`) and the upload response
lists the problems in `checks`. Quarantine is recorded only, until what it holds back is decided.
Standards plug in as validators; `DATA_STANDARDS` chooses them (default `bids`). See
`docs/diagrams/data-standards.md` and `docs/requirements/data-standards.md`.

## Known Transitional Areas

Some parts of the repository are clearly in transition and should be handled carefully.

- The old `/api/assets` endpoints are gone; the tree endpoints (`/api/tree/...`) replace them. Two routers share the `/tree` prefix (`s3_endpoints.py`, `file_tree_db.py`).
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

Backend tests are in `backend/tests/`; frontend tests sit next to the components (`*.test.js`).

| Tests | What they check | How to run |
|---|---|---|
| `test_access_control.py` | Access control through the HTTP API, as a user would hit it (AC-n) | Needs the local stack. From `backend/`: `set -a; . ../local/.env; set +a`, then `pytest tests/test_access_control.py -v` |
| `test_access_rules.py` with `features/` | The policy rules, as scenarios and property tests | `pytest tests/test_access_rules.py` (needs `pytest-bdd` and `hypothesis`) |
| `test_notifications.py`, `test_standards.py`, `test_bids.py`, `test_bundle_owner_ttl.py` | Units, with MongoDB and the file tree faked | In the backend container: `docker exec -w /app ams-backend python -m pytest tests/<file>` |
| smoke and CRUD tests (`test_*_smoke.py`, `test_policy_crud.py`) | Authentication, policies, users | Against the running backend |
| `test_policy_guide.py` | The policy guide's "Does this policy allow it?" table, row by row, against the decision layer | From a checkout (it reads `docs/`): `pytest tests/test_policy_guide.py`; it skips in the container |
| frontend | Components | From `frontend/`: `CI=true npm test` |

## Requirements and Tests

What the system must do is written down in `docs/requirements/`: access control (AC-n), notifications
(NT-n), data standards (STD-n). Each entry says which part of the INN Digital Infrastructure Strategy
it serves, and whether it's settled, proposed or open.

- Each test names the requirement it checks: its docstring starts with the ID (`"""AC-3. ..."""`), or
  the module docstring has a `Verifies: AC-1, AC-3` line covering every test in the file.
- A test that walks a whole use case through the running application says so in its module docstring
  (`Accepts: UC-5.1.`). Steps not built yet are known-failing, each naming what it waits on.
- When a test shows a requirement is wrong, change the requirement first, then the code.

## Bug Fixes

- Write the test that shows the bug first, in its own commit, marked known-failing:
  `pytest.mark.xfail(strict=True, reason="INN-123: ...")`, named for the ticket.
- Run it without the fix and see it fail. The fix removes the marker in the same change.
- Markers are strict, so a test that starts passing while still marked fails the run. That is how a
  fix landing elsewhere shows up (`--runxfail` shows the real failures).

## Merge Requests

- One change per MR: a fix, a feature, or a docs change. Its title is a Conventional Commits subject
  (`fix(authz): ...`); the body says which ticket it addresses, in a sentence or a few bullets.
- An MR that adds a component, endpoint or setting documents it in the same MR: the README's project
  structure, this file, `docs/api-reference.md`, and a page in `docs/diagrams/` when it adds a flow.
  The system overview (`docs/diagrams/component-architecture.md`) shows only what's merged; an MR
  adds itself there once the MRs it would clash with are merged.
- Stacked MRs (one built on another) say what they're based on, and merge in that order.
- User-facing docs (`docs/user-guide/`) mark what each section states with hidden comments:
  `<!-- claim: AC-5; tests: test_... -->`, or `<!-- planned: AC-7 -->` for what isn't settled. A table
  marked `<!-- check: ... -->` is executed by the test it names, so change the table and the rules together.

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

## Guidance For Future Agent Work
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
