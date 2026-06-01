-- Schema for Object Storage Tree Backend
-- Requires: Postgres 13+, extensions: ltree, pg_trgm
-- pg_trgm partial text search (e.g., search by filename or folder name)  SELECT id, name
-- FROM folders
-- WHERE name % 'proj'
-- ORDER BY similarity(name, 'proj') DESC;
CREATE EXTENSION IF NOT EXISTS ltree;

-- # pg_trgm + GIN: for fast text search by indexing trigrams (3‑char chunks) in an inverted index ( for text search, it tells the DB which rows contain a given word or trigram, instead of scanning every row)
-- # This significantly speeds up ILIKE/similarity queries  (fuzzy search) on names by mapping trigrams --->  matching rows, and avoiding full table scans
-- We have not used it yet, but it could be useful in future to speed up search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS folders (
  id         BIGSERIAL PRIMARY KEY,
  bucket     TEXT NOT NULL,
  parent_id  BIGINT NULL REFERENCES folders(id) ON DELETE CASCADE,
  name       VARCHAR(512) NOT NULL,
  path       LTREE NOT NULL,
  full_path  TEXT NOT NULL,

  -- S3 folder-marker key (e.g., "demo/sub/")
  marker_key TEXT NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_folders_bucket_path UNIQUE (bucket, path),
  CONSTRAINT uq_folders_bucket_full_path UNIQUE (bucket, full_path)
);


CREATE INDEX IF NOT EXISTS idx_folders_marker_key ON folders(marker_key);

CREATE INDEX IF NOT EXISTS idx_folders_path_gist
  ON folders USING GIST (path);

CREATE INDEX IF NOT EXISTS idx_folders_name_trgm
  ON folders USING GIN (name gin_trgm_ops);

-- Files (object pointers)
CREATE TABLE IF NOT EXISTS files (
  id            BIGSERIAL PRIMARY KEY,
  bucket        TEXT NOT NULL,
  folder_id     BIGINT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
  name          VARCHAR(512) NOT NULL,
  key           TEXT NOT NULL,
  size          BIGINT NULL,
  etag          TEXT NULL,
  last_modified TIMESTAMPTZ NULL,
  content_type  TEXT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_files_bucket_key UNIQUE (bucket, key)
);

CREATE INDEX IF NOT EXISTS idx_files_bucket_folder
  ON files(bucket, folder_id);

CREATE INDEX IF NOT EXISTS idx_files_name_trgm
  ON files USING GIN (name gin_trgm_ops);

-- Object storage notification events.
-- Webhook handlers insert rows quickly; a worker can process pending rows later.
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
