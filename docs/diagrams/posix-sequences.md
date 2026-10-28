# POSIX Storage: Sequences

What happens, in order, for each operation on a POSIX instance. Each **checked** diagram is replayed
by an end-to-end test against the local stack: the test performs the operation through the portal,
collects what the backend, the file service and the helper logged, and compares it with the solid
arrows below, in order. Dashed replies, async arrows (to the opener) and notes are explanation only.
See [How the diagrams are checked](../posix/README.md#how-the-diagrams-are-checked).

Participants: **Backend** is the portal backend; **FileService** is the file service's web process
(uid 10001, can't read data); **Helper** is its privileged helper (root); **Opener** is a short-lived
process running as the link's temporary user ID.

---

## Download a File (checked)

```mermaid
%% check: download
sequenceDiagram
    participant Browser
    participant Backend as Portal backend
    participant FileService as File service (web)
    participant Helper as Helper (root)
    participant Opener as Opener (link's ID)

    Browser->>Backend: GET /api/tree/files/{id}/download-url
    Note over Backend: checks the user's read access (decision layer)<br/>signs a link: path, op read, sub = user, 15 min
    Backend-->>Browser: signed link to the file service

    Browser->>FileService: GET /v1/files/{path} → 200
    FileService->>Helper: open
    Note over Helper: checks the token itself<br/>gives the link's temporary ID read access to this one file
    Helper-)Opener: open the file as the link's ID
    Opener--)Helper: descriptor (the OS decided the open)
    Helper-->>FileService: descriptor
    FileService-->>Browser: file bytes
```

## Resume a Broken Download (checked)

Links can be reused until they expire, so the browser asks for the rest of the file with the same
link. `If-Range` makes the file service send the whole file instead if it changed in between.

```mermaid
%% check: resume
sequenceDiagram
    participant Browser
    participant FileService as File service (web)
    participant Helper as Helper (root)

    Browser->>FileService: GET /v1/files/{path} → 200
    FileService->>Helper: open
    Helper-->>FileService: descriptor
    FileService-->>Browser: bytes (connection breaks partway)

    Browser->>FileService: GET /v1/files/{path} → 206 (Range: bytes=N-, If-Range)
    FileService->>Helper: open
    Helper-->>FileService: descriptor
    FileService-->>Browser: the rest of the file
```

## Upload a File (checked)

The link's temporary ID writes only into a staging folder outside the data tree. The helper moves the
finished file into place and gives it to the data-owner account; temporary IDs never get write access
to data folders.

```mermaid
%% check: upload
sequenceDiagram
    participant Browser
    participant Backend as Portal backend
    participant FileService as File service (web)
    participant Helper as Helper (root)
    participant Opener as Opener (link's ID)

    Browser->>Backend: POST /api/tree/files/upload/init
    Note over Backend: checks write access, creates a pending file row<br/>signs a link: path, op write, sub = user
    Backend-->>Browser: file id, signed link

    Browser->>FileService: PUT /v1/files/{path} → 201
    FileService->>Helper: begin_write
    Helper-)Opener: create a staging file as the link's ID
    Opener--)Helper: descriptor
    Helper-->>FileService: staging descriptor
    Note over FileService: streams the body into the staging file
    FileService->>Helper: commit
    Note over Helper: checks the token again<br/>moves the file into place (no-follow), owner 10002, mode 0600
    Helper-->>FileService: placed
    FileService-->>Browser: 201

    Browser->>Backend: POST /api/tree/files/upload/complete
    Backend->>FileService: HEAD /v1/files/{path} → 200
    FileService->>Helper: stat
    Helper-->>FileService: size, times
    FileService-->>Backend: metadata
    Backend-->>Browser: complete
```

## Delete a File (checked)

POSIX can't grant "delete only this one file", so the helper carries out deletes itself after checking
the backend's delete token.

```mermaid
%% check: delete
sequenceDiagram
    participant Browser
    participant Backend as Portal backend
    participant FileService as File service (web)
    participant Helper as Helper (root)

    Browser->>Backend: DELETE /api/tree/files/{id}
    Note over Backend: checks delete access<br/>signs a short service token: op delete, sub = user
    Backend->>FileService: DELETE /v1/files/{path} → 204
    FileService->>Helper: delete
    Helper-->>FileService: done
    FileService-->>Backend: 204
    Backend-->>Browser: deleted
```

## Link Expiry

Every few seconds the helper's sweeper looks for expired links. The states an ID moves through are
in [the link lifecycle](./posix-link-lifecycle.md).

```mermaid
sequenceDiagram
    participant Sweeper as Helper sweeper (root)
    participant Data as Data tree

    loop every 15 s
        Sweeper->>Sweeper: links whose expiry has passed
        Sweeper->>Data: remove the ID's ACL entry, on the same file (device, inode) it was granted on
        Sweeper->>Data: remove the ID's staging folder
        Note over Sweeper: every grant revoked: quarantine the ID<br/>a granted file moved or replaced: retire the ID for good
    end
    Note over Sweeper,Data: downloads already running keep their open descriptor and finish
```

---

**Last Updated:** 2026-10-23
**Branch:** posix/stack
