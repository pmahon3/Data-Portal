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

> **Outdated.** This describes `GET /api/asset/download-folder` returning a list of
> presigned URLs for the browser to assemble with JSZip. That endpoint no longer
> exists: multi-file downloads now go through `POST /api/tree/bundle/zip`, which
> hands the work to the bundler service. See "File Download Flow (S3)" above for the
> current shape. Kept for historical reference until it is rewritten.

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

## Single File Download URL

`GET /api/tree/files/{file_id}/download-url` — the request the browser makes for each
file it wants. No call reaches Keycloak or the object store: identity comes from the
verified token, the policy check is in memory, and presigning is local crypto.

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant Mongo
    participant Postgres
    participant Casbin
    participant S3Storage

    User->>Frontend: Click Download
    Frontend->>Backend: GET /api/tree/files/{id}/download-url<br/>Bearer {token}&instance_name={name}

    Backend->>Backend: Verify JWT with cached JWKS keys
    Backend->>Backend: Read caller uuid from 'sub' claim

    Backend->>Mongo: find_one({name: instance_name})
    Mongo-->>Backend: Instance document<br/>(agent comes from in-memory map)

    Backend->>Postgres: SELECT file WHERE id = {id}
    Postgres-->>Backend: bucket, key

    Backend->>Casbin: enforce(user_uuid, instance_uuid,<br/>bucket/key, read)

    alt Allowed
        Casbin-->>Backend: true
        Backend->>Backend: Sign presigned GET URL locally<br/>(no network call)
        Backend-->>Frontend: 200 {url}
        Frontend->>S3Storage: GET {presigned_url}
        S3Storage-->>Frontend: File data
        Frontend->>User: File downloaded
    else Denied
        Casbin-->>Backend: false
        Backend-->>Frontend: 403 Forbidden
    end
```

Per request this is one Mongo read, one Postgres read, one in-memory policy evaluation
and one local signing operation. Earlier revisions also made two Keycloak round trips
(OIDC discovery plus a JWKS fetch) and a third to resolve the caller's username into a
uuid, and read the instance document twice; those were removed in 2026-09.

## Bulk Manifest

`POST /api/tree/manifest` - one presigned URL per authorized file, in a single request.
Accepts file ids, folder ids, or both; folders expand to their completed descendants.

The cost that matters is the round trip. Asking for N files here is one request rather
than N: the caller's identity and the storage instance are resolved once for the whole
batch, and presigning is local crypto with no network call, so the marginal cost per
file is small. Over a link with real latency this is the difference between paying the
round trip once and paying it N times.

```mermaid
sequenceDiagram
    actor Caller
    participant Backend
    participant Mongo
    participant Postgres
    participant Casbin
    participant S3Storage

    Caller->>Backend: POST /api/tree/manifest<br/>{instance_name, file_ids[], folder_ids[]}

    Backend->>Backend: Verify JWT with cached JWKS keys
    Backend->>Backend: Read caller uuid from 'sub' claim

    Note over Backend,Mongo: Resolved once for the whole batch
    Backend->>Mongo: find_one({name: instance_name})
    Mongo-->>Backend: Instance document

    Backend->>Postgres: SELECT files WHERE id IN {file_ids}
    Postgres-->>Backend: file rows

    opt folder_ids given
        Backend->>Postgres: Expand folders to completed descendants
        Postgres-->>Backend: file rows
    end

    loop For each resolved file
        Backend->>Casbin: enforce(user_uuid, instance_uuid,<br/>bucket/key, read)
        Casbin-->>Backend: allow or deny
    end

    alt An explicitly requested file is denied
        Backend-->>Caller: 403 Forbidden
    else No readable files
        Backend-->>Caller: 404 Not Found
    else Authorized
        Backend->>Backend: generate_access_links(resources, read, ttl)<br/>sign each URL locally
        Backend-->>Caller: 200 {count, total_bytes, expires_in, entries[]}
        Caller->>S3Storage: GET each presigned URL
        S3Storage-->>Caller: File data
    end
```

Each entry carries `file_id`, `bucket`, `key`, `relative_path`, `size`, `etag` and
`url`, so a client can reconstruct the tree it asked for without a second call.

`relative_path` is the full `bucket/key`, so a manifest spanning buckets cannot collide
on disk. `etag` is a change detector rather than a checksum - a multipart upload yields
`<hash>-<partcount>`, which depends on part size rather than content alone - so a client
verifies by byte count and uses the etag only to notice that an object changed.

Only `url` and `relative_path` are needed to perform the transfer; the rest is
information the caller may or may not use.

### Denied files: 403 or skipped

The two cases differ deliberately. A file named **explicitly** in `file_ids` that the
caller cannot read raises 403 - asking for something specific and silently not getting
it is worse than an error. A file reached by **expanding a folder** is skipped instead,
because a folder the caller can partly read should return the readable part.

Both paths go through `resolve_authorized_files`, which the bundle endpoint also uses,
so a manifest and a bundle of the same selection make the same authorization decision.

### Redeeming a manifest: resumable transfer

A manifest is data, not a transfer. Something else redeems it - `protocol/client/fetch.py`
is the reference implementation, but the format is deliberately plain enough that a job
on the destination cluster or a container the receiving institution runs could do the
same.

What makes an unattended move of a large dataset possible is that **the partial files on
disk are the entire state**. The resume offset is the size of the file already there, so
there is no journal to corrupt and no sidecar to fall out of sync; an interrupt at any
moment leaves something valid to continue from.

```mermaid
sequenceDiagram
    actor Operator
    participant Client as Transfer client
    participant Disk
    participant S3Storage

    Operator->>Client: fetch.py manifest.json --dest DIR

    loop For each entry
        Client->>Disk: stat(DIR/relative_path)

        alt Size already equals entry.size
            Note over Client,Disk: Complete - skipped, so a rerun<br/>costs only the unfinished tail
        else Partial file present
            Disk-->>Client: offset = bytes on disk
            Client->>S3Storage: GET url<br/>Range: bytes=offset-
            alt 206 Partial Content
                S3Storage-->>Client: remaining bytes
                Client->>Disk: append
            else 200 OK (Range ignored)
                S3Storage-->>Client: whole object
                Client->>Disk: truncate, then write
            end
        else Nothing on disk
            Client->>S3Storage: GET url
            S3Storage-->>Client: object
            Client->>Disk: write
        end
    end

    Client->>Disk: Re-stat every entry against the manifest
    Client-->>Operator: Report, or list what is still short
```

The backend is absent from this diagram, which is the point: it issued the references
and is out of the data path. Bytes move between storage and the destination over 443,
so no component has to be installed inside the network holding the data.

Two consequences worth stating, because they bound what this design gives you:

- **A presigned URL expires.** The TTL is fixed when the manifest is minted, so a
  transfer longer than that window needs a fresh manifest rather than a longer wait.
  Re-minting mid-transfer, against current policy, is the recorded direction in
  `workstreams/data-transfer/STATUS.md`; it is not implemented here.
- **Integrity is byte count, not content.** See the etag note above.

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
