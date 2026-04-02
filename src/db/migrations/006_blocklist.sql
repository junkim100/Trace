-- Migration: 006_blocklist
-- Description: Add blocklist table for selective capture filtering
-- Created: 2025-01-20

-- Blocklist table: allows users to block specific apps/domains from capture
CREATE TABLE IF NOT EXISTS blocklist (
    blocklist_id TEXT PRIMARY KEY,
    block_type TEXT NOT NULL CHECK (block_type IN ('app', 'domain')),
    pattern TEXT NOT NULL,
    display_name TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    block_screenshots INTEGER NOT NULL DEFAULT 1,
    block_events INTEGER NOT NULL DEFAULT 1,
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(block_type, pattern)
);

CREATE INDEX IF NOT EXISTS idx_blocklist_type ON blocklist(block_type);
CREATE INDEX IF NOT EXISTS idx_blocklist_enabled ON blocklist(enabled);

-- Record this migration
INSERT INTO schema_version (version, description)
VALUES (6, 'Add blocklist table for selective capture filtering');
