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

## Required Environment

Both scripts need the Postgres async database URL:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database
```

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
  inn-storage-events-worker
```

Run worker in watch mode:

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://user:password@host:5432/database" \
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

