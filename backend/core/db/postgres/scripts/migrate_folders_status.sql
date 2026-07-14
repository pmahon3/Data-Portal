-- Adds upload lifecycle status to existing folders.
-- Existing rows are assumed to be complete because they were inserted before
-- pending folder upload tracking existed.

ALTER TABLE folders
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'complete';
