# POSIX downloads: streamed on demand

**Status:** draft, 2026-10-22. Defaults marked *proposed* need Patrick's confirmation before code.
Scope: the download path of the POSIX file service. Object storage is a separate proposal
(last section), to take to RDT only after measurement.


> **Reinstated 2026-10-29 (Patrick).** Multi-file POSIX downloads are streamed by the file service
> as below; the client-assembly plan of 2026-10-27 is shelved (data-transfer workstream notes).
> Changes since 2026-10-22: the approval is P11's `grant` (one temporary ID per approval); the
> link carries the approval ID and the file service fetches the file list from the portal
> (proposed); link lifetime for long downloads is deferred until it comes up, no fix chosen.
> The streaming core is kept under tag `backup/posix-port-before-stack` (`app/zipstream.py`).

## The idea

The portal approves a request, and the user's machine then receives one ZIP stream straight
from the storage machine. Nothing is pre-built or stored, so there's no job queue, scratch
disk, output bucket or retention. Peak demand becomes the number of downloads running at once,
which can be capped, instead of storage sized for the largest bundles.

1. The user asks the portal for a set of files.
2. The portal checks access on every file (the single decision layer, !166 and !164) and saves an
   **approval record**: the file list, each file's size and version (modification time), the
   user, and an expiry.
3. The portal returns a **signed link** naming the approval record.
4. The user's machine calls the file service on the POSIX machine with that link.
5. The file service checks the signature and expiry, reads the files from its disk and streams
   them as one ZIP.

## Decisions (proposed defaults)

| Decision | Proposed default | Why |
|---|---|---|
| Resumable downloads | Yes, by HTTP byte ranges | Large downloads; Patrick 2026-10-22 |
| Snapshot or current files | Current. If any file's version differs from the approval record, a resume is refused and the download restarts | Q10 (Part D) can require snapshots later |
| Compression | Stored (not compressed) by default; deflate only for compressible types (text, CSV, JSON) | Imaging is mostly compressed already; stored entries make every byte predictable, which resuming needs |
| Link reuse | **Confirmed 2026-10-22.** Bound to the user and the approval record; reusable for range requests until expiry | Resuming needs repeated requests. **Replaces the prototype's single-use tokens** (Redis `jti` tracking), and drops Redis |
| Link expiry | **Confirmed 2026-10-22.** Links keep a fixed lifetime (TTL), checked when a download starts or resumes; a running download finishes; resuming after expiry needs a new link, which re-checks access | Long transfers outlive short links |
| Where links are signed | In the portal backend; the file service verifies with the backend's public key | Alireza's October 2025 request (signing moves into the main service). **Differs from the scope of work**, which says to bring over the separate issuer |
| Downloads at once | Setting, default 8 per file service; extra requests wait rather than fail | Tuned in round 5; doesn't block implementation |
| Read-ahead | Setting, default 4 files or 64 MB, whichever is smaller | Tuned in round 5 |
| Request limits | Settings: files per request, default 200,000; total size, default no cap. ZIP64 always on, so size never changes the design | Tuned in round 5 |
| Audit | One record per approval (with its file list), one per download or resume | R5 |
| Popular public datasets | Out of scope: publish a ready-made archive at release | The one case where pre-building pays off |
| Resumable uploads | Separate, smaller piece (tus, or the S3 multipart pattern) | |

## What the streamer has to do

- **ZIP64**, so single files and whole streams can exceed 4 GB.
- **Predictable bytes:** fixed file order and fixed header fields, so the total size is known in
  advance (browser progress) and any byte range can be regenerated.
- **Checksums saved:** each file's CRC-32 is stored after its first full read, so a resume can jump
  to the break point without re-reading earlier files. Missing checksums are computed on demand.
- **Parallel read-ahead** within a small bounded buffer, so many small files don't stall the stream
  (e.g. 34,000 MEG derivatives).
- **Path safety:** every path resolves inside the service's root.
- **Truncation is detectable:** a failed source read ends the stream; the client resumes.

## From the October 2025 prototype

- **Carried over:** the file service skeleton (FastAPI, Docker), path validation, single-file
  streaming with ranges, the listing endpoint (feeds the file tree walk), signature checking.
- **Rewritten, not ported:** `storage-gateway/streaming/zip_stream.py`. It uses stdlib `zipfile`
  with deflate and buffers through `BytesIO`; it has no ZIP64 plan, predictable bytes or resume.
- **Dropped:** the separate issuer service (signing moves to the backend); Redis single-use
  tracking; the prototype agent's regex resource matching (matching now lives only in the
  decision layer).

## Rounds (after the defaults are confirmed)

1. Streaming core: predictable stored ZIP64, read-ahead, tests.
2. Approval record and signed link in the backend; per-file access checks.
3. Resume: byte ranges, saved checksums, version check.
4. Frontend: a direct link replaces poll-then-download for POSIX instances.
5. Measure: very large requests, many small files, slow connections.

## File service contract (port, 2026-10-22)

The interface between the backend's POSIX connector and the file service on the machine. Port
step 1 builds the backend side against it; step 3 builds the file service. Single files only;
the multi-file stream above comes later.

- **Namespace.** Each POSIX instance has one configured namespace (for example `inn-posix`),
  used where S3 instances use a bucket name: resources are `namespace/key`, file-tree rows use it as
  `bucket`, and policies name it as their first path segment. It must not clash with any bucket name
  (the existing uniqueness check covers this). *Proposed; confirm.*
- **Links (user-facing):** `GET` or `PUT {instance_url}/v1/files/{namespace}/{key}?token=…`.
  `GET` supports byte ranges. `PUT` is a single upload for now (resumable uploads later).
- **Backend calls (server to server):** `HEAD` (metadata) and `DELETE` on the same path, with
  `Authorization: Bearer <token>`. `HEAD` returns `Content-Length`, `ETag`, `Last-Modified`,
  `Content-Type`.
- **Health:** `GET {instance_url}/v1/health`.
- **Tokens:** RS256, signed by the backend. Claims: `iss` (`inn-portal`), `aud` (the namespace),
  `jti` (link ID), `iat`, `exp`, `op` (`read`, `write`, `stat`, `delete`), `path`
  (`namespace/key`). The file service accepts a token only for its own namespace, the exact path
  and the operation named. A user claim (`sub`) and the approval-record ID come with round 2.
- **Signing key:** loaded from the file named in `STORAGE_LINK_SIGNING_KEY_FILE`. No per-process
  generated keys (a restart or second replica would invalidate links). The backend publishes the
  public key; the file service fetches and caches it.
- **Bundler:** multi-file downloads from POSIX instances are refused (the Java bundler would store a
  copy in object storage, which R2 rules out) until the streaming path exists.

## Design direction: one streamer, two destinations (Patrick, 2026-10-23)

From the bundler discussion (sushi metaphor: plate at the table, or plate once and keep in the fridge):
- **To the person:** bespoke requests are streamed on demand. Nothing is stored.
- **To storage ("menu" archives):** frequently requested sets (a released open dataset, a popular
  study) are built once by the same streamer and stored as ordinary files, then served from storage
  to anyone allowed, with storage handling resume. This is a one-off build step, not a service: no
  job queue, locks or claim logic.
- Menu archives are keyed by file versions, so they're rebuilt rather than served stale.
- Access is still checked per person before a link to a stored archive is issued.
- **Never for identifiable data:** POSIX/PII is streamed only (R2 rules out stored copies).
- Whether menu archives are worth having depends on how often identical file sets are requested;
  the Java bundler's job table can measure it.

Findings about the current bundlers (code on `development`, 2026-10-23): the Java bundler (the
default) doesn't reuse bundles across requests; each request is a new job, the fingerprint columns
are never set, and a finished bundle is kept 7 days for the original requester only. The Python
bundler reuses complete bundles by fingerprint, checked before queueing, but its fingerprint
covers file names, not contents, and an identical request during an in-progress job errors.

## Object storage (proposal, after measurement)

The same streamer, reading from object storage and running next to it, could replace the
bundler for S3 instances too, removing its job database, scratch disk, output bucket and
retention. That is RDT's component; bring it to them with the measurements from round 5.
