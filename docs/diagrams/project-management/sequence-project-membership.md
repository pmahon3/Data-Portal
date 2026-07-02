**Last Updated:** 2026-06-29

# Project Membership Management Sequence Diagrams

## Add or Remove Project User

```mermaid
sequenceDiagram
    actor User as Admin or Project Manager
    participant API as Projects API
    participant PM as Project Manager
    participant KC as Keycloak

    User->>API: POST/DELETE /projects/{project}/users
    API->>PM: add/remove project user
    PM->>KC: group_user_add/remove
    KC-->>PM: membership updated
    PM-->>API: updated project
    API-->>User: 200 ProjectResponse
```

## Add or Remove Project Manager

```mermaid
sequenceDiagram
    actor Admin
    participant API as Projects API
    participant PM as Project Manager
    participant KC as Keycloak

    Admin->>API: POST/DELETE /projects/{project}/managers
    API->>PM: add/remove project manager
    PM->>KC: group_user_add/remove on /{project}/managers
    KC-->>PM: manager membership updated
    PM-->>API: updated project
    API-->>Admin: 200 ProjectResponse
```

## Add Storage Instance

```mermaid
sequenceDiagram
    actor Admin
    participant API as Projects API
    participant IM as Instance Manager
    participant PM as Project Manager
    participant DB as MongoDB

    Admin->>API: POST /projects/{project}/storage-instances
    API->>IM: get_instance_uuid(instance_name)
    IM-->>API: instance UUID
    API->>PM: add_project_storage_instance(project, instance)
    PM->>DB: upsert project-instance association by UUID
    DB-->>PM: association saved
    PM-->>API: updated project
    API-->>Admin: 200 ProjectResponse
```

## Remove Storage Instance

```mermaid
sequenceDiagram
    actor Admin
    participant API as Projects API
    participant PM as Project Manager
    participant DB as MongoDB

    Admin->>API: DELETE /projects/{project}/storage-instances/{instance}
    API->>PM: remove_project_storage_instance(project, instance)
    PM->>DB: delete project-instance association
    DB-->>PM: association removed
    PM-->>API: updated project
    API-->>Admin: 200 ProjectResponse
```
