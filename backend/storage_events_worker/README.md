# Storage Events Worker

This folder contains the storage event processing and cleanup jobs:

- `process_storage_events.py`
- `cleanup_storage_events.py`
- `Dockerfile.worker`
- `Dockerfile.cleanup`
- `requirements.txt`
- `nomad/`

The worker applies rows from `storage_events` to the Postgres `folders` and
`files` tables. It reads events with:

```text
status = 'pending'
```

Then it:

- creates or updates folders/files for `created` events
- deletes folders/files for `removed` events
- marks each event as `processed` or `failed`

## Create Event Verification

Before applying an `ObjectCreated` event, the worker sends an S3 `HeadObject`
request for the event bucket/key. `HeadObject` is a metadata-only request: it
checks whether the object exists right now and returns metadata such as size,
ETag, last modified time, and content type without downloading the file body.

This guards against stale create events. For example:

1. A file is uploaded and Ceph emits `ObjectCreated`.
2. The same file is deleted soon after and Ceph emits `ObjectRemoved`.
3. The worker is delayed or receives the events out of order.
4. The old `ObjectCreated` event is processed after the object has already
   been deleted.

Without the `HeadObject` check, the worker could recreate a `files` row for an
object that no longer exists. With the check, Ceph returns not found and the
worker skips the stale create event.

## Required Environment

Both scripts need the Postgres async database URL:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database
```

The event processing worker also needs S3-compatible object storage access so
it can verify `ObjectCreated` events before creating file rows:

```bash
OBJECT_STORAGE_ENDPOINT_URL=https://object-storage.example.ca
OBJECT_STORAGE_ACCESS_KEY_ID=access-key
OBJECT_STORAGE_SECRET_ACCESS_KEY=secret-key
OBJECT_STORAGE_REGION=region-name
```

`OBJECT_STORAGE_REGION` can be omitted when the storage endpoint does not
require one.

## Run Once

Run from the `backend` directory:

```bash
python storage_events_worker/process_storage_events.py
```

By default, one run processes up to 100 pending events and exits.

To change the maximum number of events processed per run:

```bash
python storage_events_worker/process_storage_events.py --batch-size 500
```

## Watch Mode

Use watch mode when you want one long-running worker process:

```bash
python storage_events_worker/process_storage_events.py --watch --batch-size 1000 --interval 5
```

Watch mode uses polling. It checks the database for pending events. If it finds
events, it immediately loops again to drain the backlog. If it finds no events,
it sleeps for `--interval` seconds before checking again.

## Cleanup Job

Retention cleanup is handled by a separate script:

```bash
python storage_events_worker/cleanup_storage_events.py
```

By default, cleanup deletes `processed` events older than 30 days. Failed events
are kept for debugging.

Run cleanup with a different retention window:

```bash
python storage_events_worker/cleanup_storage_events.py --retention-days 7
```

## Docker Images

Build from the repository root with `backend` as the build context:

```bash
docker build -f backend/storage_events_worker/Dockerfile.worker -t inn-storage-events-worker backend
docker build -f backend/storage_events_worker/Dockerfile.cleanup -t inn-storage-events-cleanup backend
```

Run worker once:

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://user:password@host:5432/database" \
  -e OBJECT_STORAGE_ENDPOINT_URL="https://object-storage.example.ca" \
  -e OBJECT_STORAGE_ACCESS_KEY_ID="access-key" \
  -e OBJECT_STORAGE_SECRET_ACCESS_KEY="secret-key" \
  inn-storage-events-worker
```

Run worker in watch mode:

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://user:password@host:5432/database" \
  -e OBJECT_STORAGE_ENDPOINT_URL="https://object-storage.example.ca" \
  -e OBJECT_STORAGE_ACCESS_KEY_ID="access-key" \
  -e OBJECT_STORAGE_SECRET_ACCESS_KEY="secret-key" \
  inn-storage-events-worker --watch --batch-size 1000 --interval 5
```

Run cleanup:

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://user:password@host:5432/database" \
  inn-storage-events-cleanup --retention-days 30
```

## Nomad

Nomad job files are in `nomad/`:

```text
nomad/storage-events-worker.nomad
nomad/storage-events-cleanup.nomad
```

The worker job runs as a service in watch mode. The cleanup job runs as a daily
periodic batch job.

Run the worker job:

```bash
nomad job run \
  -var database_url="postgresql+asyncpg://user:password@host:5432/database" \
  -var object_storage_endpoint_url="https://object-storage.example.ca" \
  -var object_storage_access_key_id="access-key" \
  -var object_storage_secret_access_key="secret-key" \
  -var registry_password="YOUR_REGISTRY_TOKEN" \
  backend/storage_events_worker/nomad/storage-events-worker.nomad
```

Run the cleanup job:

```bash
nomad job run \
  -var database_url="postgresql+asyncpg://user:password@host:5432/database" \
  -var registry_password="YOUR_REGISTRY_TOKEN" \
  backend/storage_events_worker/nomad/storage-events-cleanup.nomad
```
