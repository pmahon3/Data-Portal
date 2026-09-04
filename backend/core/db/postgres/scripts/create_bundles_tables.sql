-- Bundle manifest: the folder scopes each bundle draws from.
-- Read at redemption to authorize the caller against current policy.
-- See docs/bundling-design.md.
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS bundles (
  id            TEXT PRIMARY KEY,
  instance_uuid UUID NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deduplicated by parent folder: policies are path-scoped, so files sharing a
-- directory resolve identically and need only one check between them.
CREATE TABLE IF NOT EXISTS bundle_scopes (
  id          BIGSERIAL PRIMARY KEY,
  bundle_id   TEXT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
  bucket      TEXT NOT NULL,
  folder_path TEXT NOT NULL,
  CONSTRAINT uq_bundle_scope UNIQUE (bundle_id, bucket, folder_path)
);

CREATE INDEX IF NOT EXISTS ix_bundle_scopes_bundle_id
  ON bundle_scopes(bundle_id);
