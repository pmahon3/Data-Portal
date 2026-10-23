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

### 🔐 [Authentication Sequences](./sequence-authentication.md)
Authentication and authorization flows:
- User login flow (OAuth2/OIDC)
- Token validation
- Admin operations
- Token refresh
- Service account flow
- User management
- Logout flow

### 💾 [Storage Access Sequences](./sequence-storage-access.md)
Storage operations and access control:
- File download (S3)
- File upload (S3)
- File tree loading
- Folder download (ZIP)
- Instance creation/deletion
- Access control patterns

### 🗄️ POSIX Storage
Access to data on researcher-owned POSIX machines; overview and decisions in [docs/posix](../posix/README.md).
Diagrams marked *checked* are verified against the build by tests.
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
