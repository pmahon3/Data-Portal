# Project Management

Project management groups users, managers, and storage instances under a named
project.

## Who can use it?

Both administrators and project managers can open the page. The UI exposes
different actions based on the Keycloak `admin` realm role.

| Action | Administrator | Project manager |
| --- | --- | --- |
| View available projects | Yes | Yes |
| Add or remove project users | Yes | Yes |
| Create or delete a project | Yes | No |
| Add or remove project managers | Yes | No |
| Assign or remove storage instances | Yes | No |

The backend validates every action and limits project managers to their allowed
projects.

## Project contents

Each project card opens a management dialog with three lists:

| List | Purpose |
| --- | --- |
| Users | People who belong to the project. |
| Managers | People allowed to manage the project. |
| Storage Instances | Storage connections assigned to the project. |

Removing a project or an item from one of these lists requires confirmation.

## API calls

All requests include a Keycloak bearer token.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/projects` | List projects visible to the current user. |
| `POST` | `/api/projects` | Create a project. |
| `DELETE` | `/api/projects/{project_name}` | Delete a project. |
| `POST` | `/api/projects/{project_name}/users` | Add a user. |
| `DELETE` | `/api/projects/{project_name}/users/{username}` | Remove a user. |
| `POST` | `/api/projects/{project_name}/managers` | Add a manager. |
| `DELETE` | `/api/projects/{project_name}/managers/{username}` | Remove a manager. |
| `POST` | `/api/projects/{project_name}/storage-instances` | Assign a storage instance. |
| `DELETE` | `/api/projects/{project_name}/storage-instances/{instance_name}` | Remove a storage instance. |

## Main source files

| Purpose | File |
| --- | --- |
| Page state and API calls | `frontend/src/components/admin_page/project_management/index.js` |
| Create-project form | `frontend/src/components/admin_page/project_management/ProjectForm.js` |
| Project summary card | `frontend/src/components/admin_page/project_management/ProjectCard.js` |
| Membership dialog | `frontend/src/components/admin_page/project_management/ProjectModal.js` |

## Related diagrams

- [Project class model](../../../diagrams/project-management/class-project.md)
- [Project CRUD sequence](../../../diagrams/project-management/sequence-project-crud.md)
- [Project membership sequence](../../../diagrams/project-management/sequence-project-membership.md)
