# Bundler Request Flow

> **Start here:** This doc is the **Bundle behavior** path (HTTP and worker sequences). To pick another goal, see [getting-started.md → Start here](../getting-started.md#start-here-what-to-read).

This document describes how a bundle request moves through the system from HTTP
acceptance to background processing and download. It complements
[`state-machine.md`](state-machine.md), which focuses on lifecycle states and
transitions.

Architecture: **Hexagonal (Ports & Adapters) + async job processing + explicit state machine**. For project layout and regeneration workflow, see [`README_dev.md`](README_dev.md) and [`README_reference.md`](README_reference.md).

## Layer Map

| Layer | Responsibility | Location |
|-------|----------------|----------|
| HTTP adapter | Map HTTP status codes and request/response models | `bundler/bundler_server/core/default_api_impl.py` |
| Domain service | Lifecycle, dedupe, queue, workers, download/zip | `bundler/bundler_core/src/bundles.py` (`BundleService`) |
| State machine | Allowed transitions and finalize/fail helpers | `bundler/bundler_core/src/models.py`, `state_ops.py` |
| Sync↔async bridge | Call async workers from sync entrypoints | AnyIO `BlockingPortal` (`_PortalRuntime`) |
| Worker queue | Producer–consumer job dispatch | AnyIO memory object streams |
| Idempotency | Normalized request fingerprint | `bundler/bundler_core/src/fingerprint.py` |

## Happy Path — Create, Poll, Download

Reliability path: **accept job → background work → poll → download**.

```mermaid
sequenceDiagram
    participant Client
    participant HTTP as bundler_server
    participant Svc as BundleService
    participant Portal as BlockingPortal
    participant Q as AnyIO memory stream
    participant W as Worker

    Client->>HTTP: POST /bundles
    HTTP->>Svc: create_bundle_job()
    Svc->>Svc: fingerprint key, persist PENDING
    Svc->>Portal: call(_enqueue_bundle_id)
    Portal->>Q: send(bundle_id)
    HTTP-->>Client: 202 Bundle (id, status=pending)

    loop poll until complete or failed
        Client->>HTTP: GET /bundles/{id}
        HTTP->>Svc: get_bundle_status()
        HTTP-->>Client: 202 Bundle (status)
    end

    W->>Q: receive(bundle_id)
    W->>Svc: PENDING to PROCESSING
    W->>W: parallel httpx downloads (task group + semaphore)
    W->>W: zip staged files (worker thread)
    W->>Svc: PROCESSING to COMPLETE

    Client->>HTTP: GET /bundles/{id}/download
    HTTP->>Svc: download_bundle_archive()
    Svc->>Svc: read archive bytes from disk
    HTTP-->>Client: 200 application/zip
```

### Notes on the happy path

- `POST /bundles` returns quickly (**202**); zip work runs in the background.
- The HTTP adapter is `async def`, but domain entrypoints are synchronous; `BlockingPortal` bridges into the AnyIO worker runtime.
- Downloads stream to a per-job temp staging directory; zip creation runs in a thread (`anyio.to_thread.run_sync`) to avoid blocking the event loop.
- `GET .../download` currently reads the full ZIP into memory (`Path.read_bytes()`); true streaming is a known future improvement.

## Worker Internals

What happens inside `_process_bundle_job` after the worker dequeues a `bundle_id`:

```mermaid
sequenceDiagram
    participant W as Worker
    participant Svc as BundleService
    participant TG as AnyIO TaskGroup
    participant HTTP as httpx AsyncClient
    participant Thread as worker thread

    W->>Svc: load record, skip if not PENDING
    W->>Svc: PENDING to PROCESSING

    W->>Svc: _build_bundle_archive
    Svc->>TG: start_soon per URL
    TG->>HTTP: GET each presigned URL
    HTTP-->>TG: stream bytes to staging files
    Note over TG: failures raise ExceptionGroup

    Svc->>Thread: _zip_from_files
    Thread-->>Svc: archive_path on disk

    alt success
        W->>Svc: _finalize_complete
        Svc->>Svc: PROCESSING to COMPLETE
    else build or finalize error
        W->>Svc: _mark_failed
        Svc->>Svc: classify_failure sets failure_kind
        Svc->>Svc: PROCESSING to FAILED
    end
```

## Create Dedupe and Retry Branches

Equivalent requests (same fingerprint; presigned query params ignored) branch on existing job status:

```mermaid
sequenceDiagram
    participant Client
    participant HTTP as bundler_server
    participant Svc as BundleService
    participant Q as AnyIO memory stream

    Client->>HTTP: POST /bundles (equivalent fingerprint)
    HTTP->>Svc: create_bundle_job()

    alt no existing job
        Svc->>Svc: new record PENDING
        Svc->>Q: enqueue
        HTTP-->>Client: 202 pending
    else existing COMPLETE
        Svc-->>HTTP: return existing record
        HTTP-->>Client: 202 complete (no enqueue)
    else existing FAILED + retry allowed
        Svc->>Svc: refresh URLs, retry_count++, FAILED to PENDING
        Svc->>Q: enqueue
        HTTP-->>Client: 202 pending
    else existing FAILED + permanent or max retries
        Svc-->>HTTP: KeyError duplicate
        HTTP-->>Client: 409 Conflict
    else existing PENDING or PROCESSING
        Svc-->>HTTP: KeyError duplicate
        HTTP-->>Client: 409 Conflict
    end
```

Retry policy: transient and unknown failures retry up to 3 times; permanent (403/404) failures do not. See [`state-machine.md`](state-machine.md#create-time-dedupe-post-bundles).

## Failure and Retry Loop

When a transient failure occurs, the backend typically regenerates fresh presigned URLs and the user re-initiates download (another `POST /bundles` with the same logical selection):

```mermaid
sequenceDiagram
    participant Client
    participant HTTP as bundler_server
    participant Svc as BundleService
    participant W as Worker

    Client->>HTTP: POST /bundles
    HTTP->>Svc: create_bundle_job()
    Svc->>W: enqueue
    W->>Svc: build fails (e.g. ConnectError in ExceptionGroup)
    Svc->>Svc: FAILED, failure_kind=transient

    Client->>HTTP: POST /bundles (fresh presigned URLs)
    HTTP->>Svc: create_bundle_job()
    Svc->>Svc: retry FAILED to PENDING, retry_count=1
    Svc->>W: enqueue same bundle_id
    W->>Svc: build succeeds
    Svc->>Svc: COMPLETE

    Client->>HTTP: GET /bundles/{id}/download
    HTTP-->>Client: 200 application/zip
```

## Runtime Startup (first request)

The worker runtime starts lazily on first create:

1. `start_runtime()` opens an AnyIO memory stream and starts `BlockingPortal` in a background thread.
2. `_worker_supervisor` spawns `worker_count` consumer tasks (task group).
3. Each consumer loops: `receive(bundle_id)` → `_process_bundle_job(bundle_id)`.

Environment knobs: `BUNDLER_WORKER_COUNT`, `BUNDLER_DOWNLOAD_CONCURRENCY`, `BUNDLER_HTTP_TIMEOUT_SECONDS`, `BUNDLER_QUEUE_MAX_SIZE`.

## Related Documentation

- [`state-machine.md`](state-machine.md) — states, transitions, dedupe table, failure kinds
- [`README_dev.md`](README_dev.md) — quick start, tools, test layout
- [`../getting-started.md`](../getting-started.md) — orientation and doc map
- [`README_reference.md`](README_reference.md) — OpenAPI generation, Make variables, protected paths
