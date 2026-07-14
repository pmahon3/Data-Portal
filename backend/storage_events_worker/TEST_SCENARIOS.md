# Storage Events Worker Test Scenarios

These scenarios describe what should be tested for the storage events worker.
They are not test implementations.

## Event Classification

- Folder marker key ending in `/` is treated as a folder.
  Example: `notif/`
- Object key not ending in `/` is treated as a file.
  Example: `notif/s2.txt`
- File key under root folder is handled correctly.
  Example: `readme.txt`
- Folder or file keys with extra leading/trailing `/` are normalized correctly.

## Created Events

- A folder `created` event creates a row in `folders`.
- A folder `created` event updates `marker_key` when the folder already exists.
- A file `created` event creates missing parent folders first.
- A file `created` event creates a row in `files`.
- A file `created` event updates an existing file row with the same `bucket` and `key`.
- File metadata is saved correctly: `size`, `etag`, and `last_modified`.
- Creating a file directly under root stores it under the root folder row.

## Removed Events

- A file `removed` event deletes only the matching row from `files`.
- A file `removed` event for a missing file does not fail.
- A folder `removed` event deletes the matching folder row.
- Deleting a folder cascades to child folders and files.
- A folder `removed` event for a missing folder does not fail.
- A root folder delete is rejected and marks the event as failed.

## Event Ordering

- Events are processed by `created_at`, then `id`.
- Folder create followed by file create creates both folder and file.
- File create followed by file remove leaves no file row.
- Folder create, file create, file remove, folder remove leaves no folder or file row.
- Rename/move represented as create-new-key then remove-old-key results in only the new key remaining.

## Event Status

- Successfully applied event changes status from `pending` to `processed`.
- Successfully applied event sets `processed_at`.
- Successfully applied event clears `error_message`.
- Unsupported event action changes status to `failed`.
- Failed event increments `retry_count`.
- Failed event stores `error_message`.
- Failed event sets `processed_at`.
- Events not in `pending` status are skipped.

## Batching

- One batch processes no more than `--batch-size` pending events.
- Watch mode immediately processes another batch when previous batch processed events.
- Watch mode sleeps only when a batch processes zero events.
- A large backlog is drained in multiple batches without loading all events at once.
- Batch size of `1000` handles thousands of events in chunks.

## Retention

- Event worker does not delete old event rows.
- Cleanup script default retention deletes `processed` events older than 30 days.
- Cleanup script `--retention-days 7` deletes `processed` events older than 7 days.
- Cleanup script `--retention-days 0` disables cleanup.
- Cleanup script does not delete `pending` events.
- Cleanup script does not delete `failed` events.
- Cleanup script does not delete recent `processed` events.

## Database State

- Root folder is created when needed.
- Missing nested parent folders are created recursively.
- Existing folder rows are reused instead of duplicated.
- Unique constraints for `folders(bucket, full_path)` are respected.
- Unique constraints for `files(bucket, key)` are respected.
- Multiple buckets with the same object key remain separate.

## Error Handling

- Database error during file/folder update rolls back the file/folder change.
- Database error marks the event as `failed` when possible.
- Invalid file key without a filename marks the event as `failed`.
- Unsupported action marks the event as `failed`.
- Logging includes enough context to identify failed event id and reason.

## Docker

- Worker Docker image builds using `backend/storage_events_worker/Dockerfile.worker`.
- Worker image installs only `backend/storage_events_worker/requirements.txt`.
- Worker image starts with the default entrypoint.
- Worker image requires `DATABASE_URL`.
- Docker run with `--batch-size` passes the argument to the worker script.
- Docker run with `--watch --interval 10` starts polling mode.
- Cleanup Docker image builds using `backend/storage_events_worker/Dockerfile.cleanup`.
- Cleanup Docker image starts with the cleanup entrypoint.
- Cleanup Docker run with `--retention-days` passes the argument to the cleanup script.

## Nomad

- Long-running Nomad worker task can run with `--watch --batch-size 1000 --interval 5`.
- Separate Nomad periodic cleanup job can run once per day.
- Nomad task logs are emitted to stdout/stderr.
- Missing `DATABASE_URL` causes the task to fail clearly.
