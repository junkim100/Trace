-- Migration: 007_performance_indexes
-- Description: Add performance indexes for common query patterns
-- Created: 2025-01-25

-- ============================================================================
-- Jobs Performance Indexes
-- ============================================================================

-- Index on status alone for quick pending/running job lookups
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

-- ============================================================================
-- Note-Entity Association Indexes
-- ============================================================================

-- Composite index for entity lookups with strength ordering
-- Useful for "top entities in a note" and "strongest associations" queries
CREATE INDEX IF NOT EXISTS idx_note_entities_entity_strength ON note_entities(entity_id, strength DESC);

-- Composite index for note lookups with strength
-- Useful for "top notes for an entity" queries
CREATE INDEX IF NOT EXISTS idx_note_entities_note_strength ON note_entities(note_id, strength DESC);

-- ============================================================================
-- Entity Resolution Indexes
-- ============================================================================

-- Composite index for entity type + name lookups
-- Speeds up entity normalization and deduplication
CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities(entity_type, canonical_name);

-- ============================================================================
-- Time-Based Query Indexes
-- ============================================================================

-- Index on notes for date-based filtering (extract date portion of start_ts)
-- Useful for "notes from today" or "notes from last week" queries
CREATE INDEX IF NOT EXISTS idx_notes_start_date ON notes(date(start_ts));

-- Index on events for date-based filtering
CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(date(start_ts));

-- Index on screenshots for date-based cleanup queries
CREATE INDEX IF NOT EXISTS idx_screenshots_date ON screenshots(date(ts));

-- ============================================================================
-- Aggregates Query Indexes
-- ============================================================================

-- Composite index for aggregate lookups by period and key type
CREATE INDEX IF NOT EXISTS idx_aggregates_period_keytype ON aggregates(period_type, period_start_ts, key_type);

-- Record this migration
INSERT INTO schema_version (version, description)
VALUES (7, 'Add performance indexes for common query patterns');
