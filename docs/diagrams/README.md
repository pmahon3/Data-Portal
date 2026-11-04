# Architecture Diagrams

Visual documentation of the AMS Data Portal system architecture using Mermaid diagrams.

## Available Diagrams

### 📐 [Component Architecture](./component-architecture.md)
System structure and component relationships:
- System overview
- Backend core components
- Storage agent architecture
- Policy management
- Data flow

### ✅ [Data Standards](./data-standards.md)
How uploaded datasets are checked against the standard they declare:
- Declaring a standard
- Checking on upload, and quarantine

### 🔐 [Authentication Sequences](./sequence-authentication.md)
Authentication and authorization flows:
- User login flow (OAuth2/OIDC)
- Token validation
- Admin operations
- Token refresh
- Service account flow
- User management
- Logout flow

### 🔔 [Notifications](./notifications.md)
How researchers are told their upload is stored:
- In the portal (navbar bell)
- By email, through a mail relay

### 💾 [Storage Access Sequences](./sequence-storage-access.md)
Storage operations and access control:
- File download (S3)
- File upload (S3)
- File tree loading
- Folder download (ZIP)
- Instance creation/deletion
- Access control patterns

### 🗄️ POSIX Storage
Access to data on researcher-owned POSIX machines; decisions in the [decision log](../design/decision-log.md#posix-storage).
Diagrams marked *checked* are verified against the build by tests ([how](#how-the-posix-diagrams-are-checked)).
- [Components](./posix-components.md): system overview; file service and backend modules (checked)
- [Deployment](./posix-deployment.md): processes, accounts and permissions on the machine (checked)
- [Sequences](./posix-sequences.md): download, resume, upload, delete (checked); expiry
- [Temporary ID lifecycle](./posix-link-lifecycle.md) (checked)

---

## Viewing the Diagrams

These diagrams are written in **Mermaid** syntax and render automatically in:

- ✅ **GitHub/GitLab** - View directly in the repository
- ✅ **VS Code** - Install [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
- ✅ **Mermaid Live Editor** - [https://mermaid.live/](https://mermaid.live/) for editing

## Color Legend

- 🔵 **Blue (#4A90E2)** - Backend / Application Services
- 🔴 **Red (#E94B3C)** - Authentication / Keycloak
- 🟦 **Light Blue (#61DAFB)** - Frontend / React
- 🟡 **Yellow (#FFD700)** - Policy / Authorization
- 🟠 **Orange (#FF9900)** - External Storage (S3)
- 🟢 **Green (#90EE90)** - Success / Healthy States

---

**Last Updated:** 2025-10-23
**Branch:** backend-containerization

## How the POSIX diagrams are checked

Only Mermaid blocks whose first line is `%% check: <name>` are checked; others are explanation.

- **Module diagrams** (flowcharts): each node's label starts with the module's path in its component
  (`app/access_broker`, `core/storage_agents/posix_agent`). A plain solid arrow `A --> B` claims "A imports B".
  The test reads the imports from the source and fails if an arrow is missing or extra. Labelled or
  dotted arrows are runtime relationships and aren't import claims.
- **Deployment** (flowchart): labels state facts in a fixed form (`process uvicorn · uid 10001 · groups
  none`, `path /srv/posix/data · mode 0710 · owner 10002:10010`). They're compared with the Dockerfile and
  entrypoint, and with the running container.
- **Sequences**: a solid arrow `A->>B: METHOD /path → status` or `A->>Broker: op` is a claim.
  `{id}` and `{path}` stand for any ID or path; text in parentheses is explanation. The end-to-end test
  performs the operation and reads what the backend, file service and access broker logged; since each logs a
  call when it finishes, the expected order is the diagram's completion order (a call made during
  another call finishes first). Dashed replies, async arrows and notes aren't checked.
- **Lifecycle** (state diagram): every `S1 --> S2` must be observed when the access broker is driven through
  each case, and nothing else may occur.

When the code changes, a test fails until the diagram is updated, and the other way round.
