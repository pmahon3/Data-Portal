-- Adds upload lifecycle status to existing files.
-- Existing rows are assumed to be complete because they were inserted before
-- pending upload tracking existed.

ALTER TABLE files
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'complete';
