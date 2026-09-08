# Storage Access Diagrams

## File Download Flow (S3)

The asset UI uses the bundle endpoint for every selection. A single resolved file
is downloaded directly; multiple files are assembled asynchronously into a ZIP.

```mermaid
flowchart TD
    A["User selects files or folders"] --> B["Frontend<br/>POST /api/tree/bundle/zip"]
    B --> C["Backend authenticates user<br/>and resolves files from PostgreSQL"]
    C --> D["Casbin authorizes read access<br/>for each file"]
    D -->|Denied| E["Return an access error"]
    D -->|Allowed| F["S3 Agent creates presigned<br/>source-file URLs"]
    F --> G{"One authorized file?"}

    G -->|Yes| H["Return single_file_url"]
    H --> I["Browser downloads file<br/>from source S3 storage"]

    G -->|No| J["Backend submits URLs to Bundler,<br/>records the bundle's folder scopes,<br/>and returns bundle_id"]
    J --> K["Bundler downloads source files<br/>and creates a ZIP"]
    K --> L["Bundler uploads ZIP<br/>to bundle S3 storage"]
    J --> M["Frontend polls bundle status"]
    L --> M
    M --> M2{"Caller still authorized<br/>for every scope?"}
    M2 -->|No| M3["404 Not Found"]
    M2 -->|Yes| N["Backend requests a <br/>presigned archive URL"]
    N --> O["Browser downloads ZIP<br/>from bundle S3 storage"]
```

## Bundle Redemption Authorization

`GET /api/tree/bundle/{id}/status` and `GET /api/tree/bundle/{id}/download` both
authorize before doing any work. A bundle id identifies an archive; it does not grant
access to one.

The check runs against the caller's policies **at redemption time**, not against an
owner recorded at creation, so an archive never outlives the access it was built under:
revoke a user's read on a folder and their existing bundles stop opening.

This is the backend's job precisely because the bundler is identity-unaware - it holds
the archive, not the question of who may have it.

```mermaid
sequenceDiagram
    actor Caller
    participant Backend
    participant Postgres
    participant Casbin
    participant Bundler

    Caller->>Backend: GET /api/tree/bundle/{id}/status<br/>or /download, Bearer {token}

    Backend->>Backend: Validate JWT
    Backend->>Postgres: SELECT bundle WHERE id = {id}

    alt No such bundle
        Postgres-->>Backend: none
        Backend-->>Caller: 404 Not Found
    else Bundle exists
        Postgres-->>Backend: instance_uuid
        Backend->>Postgres: SELECT bucket, folder_path<br/>FROM bundle_scopes WHERE bundle_id = {id}
        Postgres-->>Backend: distinct folder scopes

        loop For each scope
            Backend->>Casbin: enforce(user_uuid, instance_uuid,<br/>bucket/folder_path, read)
            Casbin-->>Backend: allow or deny
        end

        alt Any scope denied
            Note over Backend: Logged as a denied redemption
            Backend-->>Caller: 404 Not Found
        else All scopes allowed
            Backend->>Bundler: GET /bundles/{id}
            Bundler-->>Backend: status or archive URL
            Backend-->>Caller: 200 OK
        end
    end
```

**Unknown and unauthorized both answer 404.** A 403 would confirm which bundle ids
exist, and the ids are not treated as secrets - they travel in logs, proxy access logs,
and browser history. Distinguishing the two cases would make the endpoint an existence
oracle.

### Why scopes rather than files

`bundle_scopes` records the distinct parent folders a bundle draws from, deduplicated,
rather than one row per file. Policies are path-scoped, so files sharing a directory
resolve identically. A 10,000-file bundle spanning 50 directories costs 50 policy checks
rather than 10,000 - roughly 3 ms against 380 ms, measured.

Rationale and open decisions are in `docs/bundling-design.md`.

## File/Folder Upload Flow (S3)

Files are uploaded directly from the browser to S3 using a short-lived
presigned PUT URL. The backend manages authorization and file metadata.

```mermaid
flowchart TD
    A["User selects files or a folder"] --> B{"Folder upload?"}

    B -->|Single file| C["Frontend initializes single-file upload<br/>POST /api/tree/files/upload/init"]
    C --> D["Backend authenticates user<br/>and builds the S3 object key"]
    D --> E["Casbin authorizes write access"]
    E -->|Denied| F["Return an access error"]
    E -->|Allowed| G["Create pending file row<br/>and presigned PUT URL"]
    G --> H["Browser uploads file bytes<br/>directly to S3 storage"]
    H --> I["Frontend confirms upload<br/>POST /api/tree/files/upload/complete"]
    I --> J["Backend checks S3 object with HEAD<br/>and marks file complete"]

    B -->|Folder| K["Frontend builds folder manifest"]
    K --> L["Frontend initializes folder upload once<br/>POST /api/tree/folders/upload/init"]
    L --> M["Backend checks write access<br/>on selected parent folder"]
    M --> N["Backend validates paths,<br/>checks conflicts, and creates pending rows"]
    N --> O["Backend returns one presigned PUT URL<br/>per file"]
    O --> P["Browser uploads files directly<br/>to S3 storage in parallel"]
    P --> Q["Frontend completes folder upload once<br/>POST /api/tree/folders/upload/complete"]
    Q --> R["Backend checks permissions<br/>and batch-updates DB rows"]
    R --> S["Mark uploaded folders complete"]
```

## File Tree Loading

Loading directory structure from storage backend.

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Casbin
    participant S3Agent
    participant S3Storage

    User->>Frontend: Navigate to Storage Instance
    Frontend->>Backend: GET /api/asset/user-assets-data<br/>Bearer {token}

    Backend->>Backend: Validate JWT Token
    Backend->>Casbin: enforce(user_id, instance_uuid, list)

    alt List Allowed
        Casbin->>Backend: true (ALLOW)

        Backend->>S3Agent: load_file_tree()<br/>(instance_uuid)

        S3Agent->>S3Agent: Get Instance Config<br/>(bucket, prefix)

        loop Paginated Listing
            S3Agent->>S3Storage: list_objects_v2()<br/>Bucket={bucket}<br/>Prefix={prefix}<br/>MaxKeys=1000

            S3Storage->>S3Agent: Object List<br/>{objects[], is_truncated}

            S3Agent->>S3Agent: Build File Tree<br/>(parse keys, create hierarchy)

            alt More Objects
                S3Agent->>S3Agent: Store ContinuationToken
            end
        end

        S3Agent->>S3Agent: Apply Resource Filters<br/>(Casbin resource patterns)

        S3Agent->>Backend: FileTree<br/>{folders[], files[]}

        Backend->>Frontend: 200 OK<br/>{file_tree, metadata}

        Frontend->>Frontend: Render Tree View
        Frontend->>User: Display Files/Folders

    else List Denied
        Casbin->>Backend: false (DENY)
        Backend->>Frontend: 403 Forbidden
        Frontend->>User: Access Denied
    end
```

## Folder Download (ZIP)

Downloading an entire folder as a ZIP archive.

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Casbin
    participant S3Agent
    participant S3Storage

    User->>Frontend: Click Download Folder
    Frontend->>Backend: GET /api/asset/download-folder<br/>Bearer {token}<br/>instance_name={name}&resource=data/reports/

    Backend->>Backend: Validate JWT Token
    Backend->>Casbin: enforce(user_id, instance_uuid, read)

    alt Access Allowed
        Casbin->>Backend: true (ALLOW)

        Backend->>S3Agent: list_folder_contents()<br/>(instance_uuid, path)

        S3Agent->>S3Storage: list_objects_v2()<br/>Prefix=data/reports/

        S3Storage->>S3Agent: Object Keys[]

        S3Agent->>S3Agent: Filter Accessible Files<br/>(apply resource patterns)

        S3Agent->>Backend: File List[]

        loop For Each File
            Backend->>S3Agent: generate_access_link()<br/>(file_path)
            S3Agent->>Backend: Presigned URL
        end

        Backend->>Frontend: 200 OK<br/>{files: [{path, url}]}

        Frontend->>Frontend: Initialize ZIP Stream<br/>(JSZip library)

        loop For Each File URL
            Frontend->>S3Storage: GET {presigned_url}
            S3Storage->>Frontend: File Data Stream
            Frontend->>Frontend: Add to ZIP Archive
        end

        Frontend->>Frontend: Finalize ZIP
        Frontend->>User: Download folder.zip
    end
```

## Storage Instance Creation

Admin creating a new storage instance.

```mermaid
sequenceDiagram
    actor Admin
    participant Frontend
    participant Backend
    participant Casbin
    participant InstanceMgr
    participant S3Agent
    participant PolicyMgr

    Admin->>Frontend: Fill Instance Form<br/>(name, bucket, credentials)
    Frontend->>Backend: POST /api/admin/instances/<br/>Bearer {token}<br/>{flavour: "s3", config: {...}}

    Backend->>Backend: Validate Admin Token
    Backend->>Casbin: enforce(admin_id, admin, create_instance)
    Casbin->>Backend: true (ALLOW)

    Backend->>Backend: Generate instance_uuid<br/>uuid5(NAMESPACE_DNS, name)

    Backend->>S3Agent: Validate Configuration<br/>(test connection)

    S3Agent->>S3Storage: list_buckets()<br/>(test credentials)

    alt Connection Valid
        S3Storage->>S3Agent: Bucket List
        S3Agent->>Backend: Configuration Valid

        Backend->>InstanceMgr: create_instance()<br/>(uuid, name, config, agent)

        InstanceMgr->>InstanceMgr: Add to Instances List
        InstanceMgr->>InstanceMgr: Save Config JSON<br/>(configs/{uuid}.json)

        Backend->>PolicyMgr: add_policy()<br/>(admin_id, instance_uuid, .*, admin)

        PolicyMgr->>Casbin: Add Policy Rule
        Casbin->>PolicyMgr: Policy Added

        Backend->>Frontend: 201 Created<br/>{instance_uuid, name}
        Frontend->>Admin: Instance Created

    else Connection Invalid
        S3Storage->>S3Agent: 403 Forbidden
        S3Agent->>Backend: Invalid Credentials
        Backend->>Frontend: 400 Bad Request<br/>Invalid S3 configuration
        Frontend->>Admin: Error Message
    end
```

## Storage Instance Deletion

Admin deleting a storage instance and associated policies.

```mermaid
sequenceDiagram
    actor Admin
    participant Frontend
    participant Backend
    participant Casbin
    participant InstanceMgr
    participant PolicyMgr

    Admin->>Frontend: Click Delete Instance
    Frontend->>Backend: DELETE /api/admin/instances/{uuid}<br/>Bearer {token}

    Backend->>Backend: Validate Admin Token
    Backend->>Casbin: enforce(admin_id, admin, delete_instance)
    Casbin->>Backend: true (ALLOW)

    Backend->>InstanceMgr: get_instance_by_uuid(uuid)
    InstanceMgr->>Backend: Instance Details

    Backend->>PolicyMgr: get_instance_policies(uuid)
    PolicyMgr->>Backend: Policy List[]

    Note over Backend: Confirm policies will be removed

    Backend->>InstanceMgr: delete_instance(instance)
    InstanceMgr->>InstanceMgr: Remove from Instances List
    InstanceMgr->>InstanceMgr: Delete Config File<br/>(configs/{uuid}.json)

    Backend->>PolicyMgr: remove_policies(policy_list)
    PolicyMgr->>Casbin: Remove Policy Rules
    Casbin->>PolicyMgr: Policies Removed

    Backend->>Frontend: 200 OK<br/>Instance deleted
    Frontend->>Admin: Success Message
```

---

## Storage Agent Operations

### Supported Operations

| Operation | S3 Agent | Dummy Agent | Description |
|-----------|----------|-------------|-------------|
| `generate_access_link()` | ✅ Presigned GET URL | ✅ Mock URL | Get download URL |
| `generate_upload_link()` | ✅ Presigned PUT URL | ✅ Mock URL | Get upload URL |
| `load_file_tree()` | ✅ S3 list_objects | ✅ Mock tree | List files/folders |
| `validate_config()` | ✅ Test credentials | ✅ Always valid | Check connection |

### Presigned URL Security

**S3 Presigned URLs include:**
- AWS Access Key ID (in query params)
- Signature (HMAC-SHA256 of request)
- Expiration timestamp
- Specific operation (GET/PUT/POST)
- Resource path (locked to specific object)

**Validation by S3:**
1. Check signature matches request
2. Verify not expired
3. Confirm operation matches
4. Validate resource path

---

## Access Control Patterns

### Pattern 1: User-Level Access
```
p, user_uuid, instance_uuid, .*, read
```
User can read all files in the instance.

### Pattern 2: Resource-Level Access
```
p, user_uuid, instance_uuid, data/project1/.*, read
```
User can only read files in `data/project1/` folder.

### Pattern 3: Operation-Level Access
```
p, user_uuid, instance_uuid, data/shared/.*, read
p, user_uuid, instance_uuid, data/uploads/.*, write
```
User can read from `shared` but only write to `uploads`.

### Pattern 4: Admin Access
```
p, admin_uuid, instance_uuid, .*, admin
```
Admin has full control (read, write, delete, manage).

---

**Last Updated:** 2025-10-23
