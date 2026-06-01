-- Creates the queue table used by Arbutus/Ceph object storage webhooks.
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS storage_events (
  id            BIGSERIAL PRIMARY KEY,
  event_id      TEXT NULL,
  bucket        TEXT NOT NULL,
  object_key    TEXT NOT NULL,
  event_type    TEXT NOT NULL,
  action        TEXT NOT NULL,
  size          BIGINT NULL,
  etag          TEXT NULL,
  event_time    TIMESTAMPTZ NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  retry_count   INTEGER NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  raw_event     JSONB NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at  TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_storage_events_status_created
  ON storage_events(status, created_at);

CREATE INDEX IF NOT EXISTS idx_storage_events_bucket_key
  ON storage_events(bucket, object_key);

CREATE INDEX IF NOT EXISTS idx_storage_events_event_time
  ON storage_events(event_time);
