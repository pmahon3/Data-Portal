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

    G -->|No| J["Backend submits URLs to Bundler<br/>and returns bundle_id"]
    J --> K["Bundler downloads source files<br/>and creates a ZIP"]
    K --> L["Bundler uploads ZIP<br/>to bundle S3 storage"]
    J --> M["Frontend polls bundle status"]
    L --> M
    M --> N["Backend requests a <br/>presigned archive URL"]
    N --> O["Browser downloads ZIP<br/>from bundle S3 storage"]
```

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
    J --> T

    B -->|Folder| K["Frontend builds folder manifest"]
    K --> L["Frontend initializes folder upload once<br/>POST /api/tree/folders/upload/init"]
    L --> M["Backend checks write access<br/>on selected parent folder"]
    M --> N["Backend validates paths,<br/>checks conflicts, and creates pending rows"]
    N --> O["Backend returns one presigned PUT URL<br/>per file"]
    O --> P["Browser uploads files directly<br/>to S3 storage in parallel"]
    P --> Q["Frontend completes folder upload once<br/>POST /api/tree/folders/upload/complete"]
    Q --> R["Backend checks permissions<br/>and batch-updates DB rows"]
    R --> S["Mark uploaded folders complete"]
    S --> T["Check declared datasets<br/>and notify the uploader once"]
```

## Folder Upload

One request prepares the whole folder, the browser sends the bytes straight to object storage,
and one request completes it. Write access is checked on the chosen folder and on every file it
will create, before anything is created ([AC-3](../requirements/access-control.md#ac-3)).

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Casbin
    participant Postgres as PostgreSQL (file tree)
    participant S3 as Object storage
    participant Mongo as MongoDB (notifications)

    User->>Frontend: Choose a folder in the Upload tab
    Frontend->>Frontend: Manifest: relative path, type, size per file<br/>(skips files like .DS_Store)
    Frontend->>Backend: POST /api/tree/folders/upload/init<br/>{instance_name, bucket, parent_id, on_conflict: "error", files}
    Backend->>Casbin: write on the chosen folder?
    Backend->>Casbin: write on every file key it will create?
    alt Any refused
        Backend-->>Frontend: 403
    else Allowed
        Backend->>Postgres: Existing complete files at those keys?
        alt Conflicts and on_conflict = "error"
            Backend-->>Frontend: 409 {conflicts}
        else No conflicts
            Backend->>Postgres: Create missing folders and pending file rows
            Backend->>Backend: Sign one PUT URL per file<br/>(locally, no S3 call)<br/>valid FOLDER_UPLOAD_PUT_EXPIRATION_SECONDS (2 h)
            Backend-->>Frontend: {files: [{file_id, relative_path, key, url}], folders_to_create}
        end
    end

    par Six at a time
        Frontend->>S3: PUT file bytes to its signed URL
    end

    Frontend->>Backend: POST /api/tree/folders/upload/complete<br/>{instance_name, file_ids}
    loop Each file
        Backend->>Casbin: still allowed to write this key?
        Backend->>S3: HEAD object (size, ETag)<br/>(skipped when FOLDER_UPLOAD_SKIP_HEAD_CHECK)
    end
    Backend->>Postgres: Mark files complete, then their folders,<br/>so they appear in the tree
    Backend->>Backend: Check declared datasets (STD-1)
    Backend->>Mongo: One notification: stored, or stored with failures (NT-1)
    Backend-->>Frontend: {completed, failed, checks}
    Frontend->>User: Done, or how many files failed
```

Completing the same upload again changes nothing and doesn't notify twice. See also
[Notifications](notifications.md) and [Data standards](data-standards.md).

## File Tree Loading

The tree comes from the file tree in PostgreSQL, not from listing object storage. Each tab
(Download, Upload, Delete) asks for the tree for its own action, so it shows what the user may do
that to ([AC-1](../requirements/access-control.md#ac-1), [AC-2](../requirements/access-control.md#ac-2)).
Browsing loads one folder at a time; searching loads the whole tree once and filters it in the browser.

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Casbin
    participant Postgres as PostgreSQL (file tree)

    User->>Frontend: Open an instance's card
    Frontend->>Backend: GET /api/tree/dashboard/{instance_uuid}/children?access=read
    Backend->>Casbin: Load the user's rules for this instance once
    Backend->>Postgres: Root folder of each bucket
    Backend->>Backend: Keep a bucket when the user may act on it<br/>or on something inside it
    Backend-->>Frontend: {access, assets: [nodes]}
    User->>Frontend: Expand a folder
    Frontend->>Backend: GET .../children?access=read&parent_id={id}
    Backend->>Postgres: Its folders and files
    Backend->>Backend: Folders on the way to something allowed,<br/>and files the user may act on
    Backend-->>Frontend: {access, assets}
    User->>Frontend: Search, e.g. *.nii
    Frontend->>Backend: GET /api/tree/dashboard/{instance_uuid}?access=read
    Backend-->>Frontend: The whole allowed tree
    Frontend->>Frontend: Filter in the browser
```

## Storage Instance Creation

An administrator or project manager adds an instance. Its creator is granted the whole instance.

```mermaid
sequenceDiagram
    actor Admin as Administrator or project manager
    participant Frontend
    participant Backend
    participant InstanceMgr as Instance manager
    participant S3 as Object storage
    participant Mongo as MongoDB (instances)
    participant Casbin

    Admin->>Frontend: Fill in the instance form<br/>(name, endpoint, credentials, projects)
    Frontend->>Backend: POST /api/instances/<br/>Bearer {token}
    Backend->>Backend: Administrator, or manager of the named projects?
    Backend->>InstanceMgr: save_instance(config)
    InstanceMgr->>S3: Connect and list buckets
    InstanceMgr->>InstanceMgr: No bucket already tracked by another instance
    InstanceMgr->>Mongo: Save the config, secrets encrypted
    alt Invalid, duplicate or unreachable
        Backend-->>Frontend: 409, 422 or 502
    else Saved
        Backend->>Casbin: Grant the creator admin on "*" (the whole instance)
        alt Grant fails
            Backend->>InstanceMgr: Delete the instance again
            Backend-->>Frontend: 500
        else Granted
            Backend->>Backend: Link the instance to its projects
            Backend-->>Frontend: Created {uuid, name}
        end
    end
```

## Storage Instance Deletion

Only an administrator can delete an instance. The files in object storage are left alone.

```mermaid
sequenceDiagram
    actor Admin as Administrator
    participant Frontend
    participant Backend
    participant Postgres as PostgreSQL (file tree)
    participant Mongo as MongoDB (instances, projects)
    participant Casbin

    Admin->>Frontend: Delete the instance
    Frontend->>Backend: DELETE /api/instances/{uuid}<br/>Bearer {token}
    Backend->>Backend: Administrator?
    Backend->>Postgres: Delete the file tree of its buckets
    Backend->>Mongo: Delete the instance
    Backend->>Mongo: Remove it from every project
    Backend->>Casbin: Remove every policy on the instance
    Backend-->>Frontend: Removed
```

---

## Storage Agent Operations

### Supported Operations

Every storage agent (`backend/core/storage_agents/`) provides these; the S3 agent is the one in use.

| Operation | Does |
|-----------|------|
| `generate_access_link(resource, method, ttl)` | A short-lived signed URL to read (`read`) or upload (`write`) one object |
| `get_object_metadata(resource)` | Size, ETag, type and date of an object (HEAD), to confirm an upload |
| `delete_object(resource)`, `delete_objects(resources)` | Delete one object, or many |
| `fetch_all_buckets()` | The instance's buckets, for the tree and for bucket uniqueness |
| `connect()`, `close()` | Open and close the connection; connecting checks the credentials |

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

Policy paths are literal: a file, a folder and everything in it (`folder/*`), or `*` for the whole
instance. The full guide, with what each policy allows: [Policies](../user-guide/policies.md).

| Policy (path, action) | Allows |
|---|---|
| `*`, `read` | Reading every file in the instance |
| `study/project1/*`, `read` | Reading everything in `study/project1/`, including files added later |
| `study/shared/*`, `read` and `study/uploads/*`, `write` | Reading from `shared`, uploading to `uploads` |
| `*`, `admin` | Everything, on the whole instance (what an instance's creator gets) |

---

**Last Updated:** 2026-10-31
