-- Migration 008: Add FTS5 full-text search index for notes
-- Enables hybrid search combining vector similarity + keyword matching

-- FTS5 virtual table for full-text search on notes
-- Uses external content mode (content='') to avoid duplicating data
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    summary,
    categories,
    entities_text,
    content='',
    tokenize='porter unicode61'
);

-- Populate FTS index from existing notes
-- Extracts summary, categories, and entity names from json_payload
INSERT OR IGNORE INTO notes_fts(rowid, summary, categories, entities_text)
SELECT
    n.rowid,
    COALESCE(json_extract(n.json_payload, '$.summary'), ''),
    COALESCE(
        (SELECT GROUP_CONCAT(value, ' ') FROM json_each(json_extract(n.json_payload, '$.categories'))),
        ''
    ),
    COALESCE(
        (SELECT GROUP_CONCAT(json_extract(value, '$.name'), ' ') FROM json_each(json_extract(n.json_payload, '$.entities'))),
        ''
    )
FROM notes n
WHERE n.json_payload IS NOT NULL;

-- Track schema version
INSERT OR IGNORE INTO schema_version (version, description)
VALUES (8, 'Add FTS5 full-text search index for notes');
