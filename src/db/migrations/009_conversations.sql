-- Migration: 009_conversations
-- Description: Add conversation persistence for chat history
-- Created: 2026-01-27

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Conversations table: stores chat sessions
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    title_generated_at TEXT,           -- NULL if user-set, timestamp if auto-generated
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts TEXT NOT NULL DEFAULT (datetime('now')),
    archived INTEGER NOT NULL DEFAULT 0,   -- 0 = active, 1 = archived
    pinned INTEGER NOT NULL DEFAULT 0      -- 0 = normal, 1 = pinned to top
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_ts DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_archived ON conversations(archived, updated_ts DESC);

-- Messages table: stores individual messages within conversations
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_ts TEXT NOT NULL DEFAULT (datetime('now')),

    -- Metadata for assistant messages (stored as JSON)
    metadata_json TEXT,                    -- Contains: citations, notes, aggregates, confidence, etc.

    -- Token tracking for context management
    token_count INTEGER,                   -- Estimated tokens in this message

    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_ts);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_ts);

-- Context window tracking: manages what messages are included in LLM calls
CREATE TABLE IF NOT EXISTS conversation_context (
    conversation_id TEXT PRIMARY KEY,
    summary_text TEXT,                     -- Compressed summary of older messages
    summary_token_count INTEGER,           -- Tokens in the summary
    last_summarized_at TEXT,               -- When summary was last updated
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

-- Record this migration
INSERT INTO schema_version (version, description)
VALUES (9, 'Add conversation persistence for chat history');
