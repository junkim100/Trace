-- Migration 005: Add hierarchical note structure
-- Adds parent_note_id for daily->hourly relationship
-- and note_type index for efficient filtering

-- Add parent_note_id column to notes table
ALTER TABLE notes ADD COLUMN parent_note_id TEXT REFERENCES notes(note_id);

-- Create index for hierarchical queries
CREATE INDEX IF NOT EXISTS idx_notes_parent ON notes(parent_note_id);

-- Create index for note_type filtering (for hierarchical search)
CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(note_type);

-- Create index for efficient date range + type queries
CREATE INDEX IF NOT EXISTS idx_notes_type_start ON notes(note_type, start_ts);

-- Update embeddings table to support note_type filtering
-- (embeddings already linked to notes via note_id, so we can join)

-- Record migration version
INSERT INTO schema_version (version, applied_at, description)
VALUES (5, datetime('now'), 'Add hierarchical note structure with parent_note_id');
