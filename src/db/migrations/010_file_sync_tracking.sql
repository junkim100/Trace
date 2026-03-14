-- Migration: 010_file_sync_tracking
-- Description: Add content_hash column for file-DB sync tracking
-- Created: 2026-03-15

-- Add content_hash column to notes table for detecting file changes
ALTER TABLE notes ADD COLUMN content_hash TEXT;

-- Record migration version
INSERT INTO schema_version (version, applied_at, description)
VALUES (10, datetime('now'), 'Add content_hash for file sync tracking');
