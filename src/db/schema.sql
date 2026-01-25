-- Trace Database Schema
-- Version: 1
--
-- This schema supports the Trace MVP application which captures digital activity,
-- generates Markdown notes, and builds a relationship graph for time-aware search.

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Schema version tracking for migrations
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- ============================================================================
-- Core Notes and Entities
-- ============================================================================

-- Notes table: stores hourly and daily summary notes
CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    note_type TEXT NOT NULL CHECK (note_type IN ('hour', 'day')),
    start_ts TEXT NOT NULL,              -- ISO-8601 timestamp
    end_ts TEXT NOT NULL,                -- ISO-8601 timestamp
    file_path TEXT NOT NULL,             -- Path to Markdown file
    json_payload TEXT NOT NULL,          -- Validated structured output from LLM
    embedding_id TEXT,                   -- Reference to embedding in sqlite-vec
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(note_type);
CREATE INDEX IF NOT EXISTS idx_notes_time ON notes(start_ts, end_ts);
CREATE INDEX IF NOT EXISTS idx_notes_file_path ON notes(file_path);
CREATE INDEX IF NOT EXISTS idx_notes_start_date ON notes(date(start_ts));

-- Entities table: normalized entities extracted from notes
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,           -- topic, game, app, domain, doc, artist, track, video, etc.
    canonical_name TEXT NOT NULL,
    aliases TEXT,                        -- JSON array of alternate names
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities(entity_type, canonical_name);

-- Note-Entity associations with strength scores
CREATE TABLE IF NOT EXISTS note_entities (
    note_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    strength REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
    context TEXT,                        -- Optional context about the association
    PRIMARY KEY (note_id, entity_id),
    FOREIGN KEY (note_id) REFERENCES notes(note_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_note_entities_entity ON note_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_note_entities_entity_strength ON note_entities(entity_id, strength DESC);
CREATE INDEX IF NOT EXISTS idx_note_entities_note_strength ON note_entities(note_id, strength DESC);

-- ============================================================================
-- Graph Edges
-- ============================================================================

-- Typed, weighted edges for relationship graph
CREATE TABLE IF NOT EXISTS edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    edge_type TEXT NOT NULL CHECK (edge_type IN (
        'ABOUT_TOPIC',
        'WATCHED',
        'LISTENED_TO',
        'USED_APP',
        'VISITED_DOMAIN',
        'DOC_REFERENCE',
        'CO_OCCURRED_WITH',
        'STUDIED_WHILE'
    )),
    weight REAL NOT NULL CHECK (weight >= 0),
    start_ts TEXT,                       -- Optional time range for edge
    end_ts TEXT,
    evidence_note_ids TEXT,              -- JSON list of note_ids supporting this edge
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_id, to_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_time ON edges(start_ts, end_ts);

-- ============================================================================
-- Capture and Activity Data (Transient)
-- ============================================================================

-- Events: time-ranged activity spans with metadata
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    app_id TEXT,                         -- Bundle ID
    app_name TEXT,
    window_title TEXT,
    focused_monitor INTEGER,
    url TEXT,
    page_title TEXT,
    file_path TEXT,                      -- Document file path if applicable
    location_text TEXT,
    now_playing_json TEXT,               -- JSON: {track, artist, album, app}
    evidence_ids TEXT,                   -- JSON list of screenshot_id/text_id references
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_time ON events(start_ts, end_ts);
CREATE INDEX IF NOT EXISTS idx_events_app ON events(app_id);
CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(date(start_ts));

-- Screenshots: captured screen frames
CREATE TABLE IF NOT EXISTS screenshots (
    screenshot_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,                    -- Capture timestamp
    monitor_id INTEGER NOT NULL,
    path TEXT NOT NULL,                  -- File path to screenshot
    fingerprint TEXT NOT NULL,           -- Perceptual hash for dedup
    diff_score REAL NOT NULL,            -- Difference from previous frame
    width INTEGER,
    height INTEGER,
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_screenshots_ts ON screenshots(ts);
CREATE INDEX IF NOT EXISTS idx_screenshots_monitor ON screenshots(monitor_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_fingerprint ON screenshots(fingerprint);
CREATE INDEX IF NOT EXISTS idx_screenshots_date ON screenshots(date(ts));

-- Text buffers: transient extracted text (deleted daily)
CREATE TABLE IF NOT EXISTS text_buffers (
    text_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf_extract', 'ocr', 'web_content')),
    ref TEXT,                            -- Reference: file_path or screenshot_id
    compressed_text BLOB NOT NULL,       -- zlib compressed text
    token_estimate INTEGER NOT NULL,
    event_id TEXT,                       -- Optional link to event
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_text_buffers_ts ON text_buffers(ts);
CREATE INDEX IF NOT EXISTS idx_text_buffers_source ON text_buffers(source_type);
CREATE INDEX IF NOT EXISTS idx_text_buffers_event ON text_buffers(event_id);

-- ============================================================================
-- Jobs and Processing
-- ============================================================================

-- Jobs: track processing jobs (hourly summarization, daily revision)
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL CHECK (job_type IN ('hourly', 'daily', 'embedding', 'cleanup')),
    window_start_ts TEXT NOT NULL,
    window_end_ts TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    result_json TEXT,                    -- Optional job result metadata
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_type_status ON jobs(job_type, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_window ON jobs(window_start_ts, window_end_ts);

-- ============================================================================
-- Aggregates for Analytics
-- ============================================================================

-- Aggregates: pre-computed rollups for "most watched/listened" queries
CREATE TABLE IF NOT EXISTS aggregates (
    agg_id TEXT PRIMARY KEY,
    period_type TEXT NOT NULL CHECK (period_type IN ('day', 'week', 'month', 'year')),
    period_start_ts TEXT NOT NULL,
    period_end_ts TEXT NOT NULL,
    key_type TEXT NOT NULL,              -- category, entity, co_activity, app, domain
    key TEXT NOT NULL,                   -- The actual key value
    value_num REAL NOT NULL,             -- Duration in minutes or count
    extra_json TEXT,                     -- Additional metadata
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_aggregates_period ON aggregates(period_type, period_start_ts);
CREATE INDEX IF NOT EXISTS idx_aggregates_key ON aggregates(key_type, key);
CREATE INDEX IF NOT EXISTS idx_aggregates_period_keytype ON aggregates(period_type, period_start_ts, key_type);

-- ============================================================================
-- Embeddings (for sqlite-vec integration)
-- ============================================================================

-- Embeddings metadata: tracks embedding vectors stored in sqlite-vec
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('note', 'entity', 'query')),
    source_id TEXT NOT NULL,             -- Reference to note_id or entity_id
    model_name TEXT NOT NULL,            -- e.g., 'text-embedding-3-small'
    dimensions INTEGER NOT NULL,         -- e.g., 1536
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_type, source_id);

-- ============================================================================
-- Integrity and Cleanup Tracking
-- ============================================================================

-- Deletion log: tracks what has been deleted for audit
CREATE TABLE IF NOT EXISTS deletion_log (
    deletion_id TEXT PRIMARY KEY,
    deletion_date TEXT NOT NULL,         -- YYYYMMDD format
    artifact_type TEXT NOT NULL,         -- screenshots, text_buffers, ocr
    artifact_count INTEGER NOT NULL,
    integrity_passed INTEGER NOT NULL,   -- 1 = true, 0 = false
    created_ts TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_deletion_log_date ON deletion_log(deletion_date);

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version, description)
VALUES (1, 'Initial schema with all MVP tables');
