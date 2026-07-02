**Last Updated:** 2026-06-29

# Project Management

Project management groups users, project managers, and storage instances under a named project.
It controls who belongs to a project, who can manage that project, and which storage instances are available through the project.

## Core Concepts

- **Project**: A logical group with users, managers, and storage instances.
- **User**: A project member who can access project resources.
- **Project Manager**: A user assigned to the project's `managers` subgroup.
- **Storage Instance**: A storage backend linked to a project by instance UUID.

## Implementation

Project membership is stored in Keycloak groups:

- `/{project}` stores project users.
- `/{project}/managers` stores project managers.

Project-to-storage-instance links are stored in MongoDB using the project ID and storage instance UUID. This keeps the association stable even if a storage instance name changes.

## Keycloak JWT Group Claims

Project management uses Keycloak groups. Because of this, the user's project groups must be included in the JWT.

To configure the group claim:

1. Navigate to the Keycloak page: `https://keycloak.rmcintos.cedar.researchcomputinggroup.ca/` or `localhost:8080`.
2. Change to the `AMS-Portal` realm.
3. Navigate to `Clients` in the left sidebar.
4. Choose `ams-portal-ui`.
5. Click `Client Scopes` and choose `ams-portal-ui-dedicated`.
6. Add a new mapper `By configuration`.
7. Add a `Group Membership` mapper.
8. Name the mapper `projects` and set the token claim name to `projects`.

## Access Rules

- Admins can create and delete projects.
- Admins can add and remove project managers.
- Admins and project managers can add or remove project users.
- Admins can add or remove storage instances from projects.

- Project managers can manage regular users only inside projects where they are assigned as managers.
- Project managers cannot create or delete projects.
- Project managers cannot add or remove other project managers.
- Project managers cannot add or remove storage instances from projects.

- Projects are not relevant for regular users. Regular users are unable to view their projects from the application.

## Diagrams

- [Class Diagram](./class-project.md)
- [Project CRUD Sequences](./sequence-project-crud.md)
- [Membership Management Sequences](./sequence-project-membership.md)
