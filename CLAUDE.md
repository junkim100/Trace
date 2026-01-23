# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trace is a macOS desktop app that continuously observes digital activity, converts it into durable Markdown notes, stores typed relationships in a local graph, and enables time-aware chat and search over past activity.

## Architecture

### Background Processes (Daemons)

1. **Capture Daemon** - Runs every 1 second
   - Multi-monitor screenshot capture (capped to 1080p, deduplicated)
   - Foreground app/window metadata collection
   - Now playing state (Spotify, Apple Music)
   - OS location snapshots
   - Best-effort URL capture (Safari, Chrome via automation)

2. **Evidence Builder** - Triggered on document context detection
   - PDF text extraction (direct when file path known)
   - OCR fallback for on-screen documents
   - Stores transient text buffers (deleted daily)

3. **Hourly Summarizer** - Runs every hou
   - Selects keyframes from screenshots
   - Calls vision LLM with curated evidence
   - Outputs structured JSON + Markdown note
   - Computes embeddings

4. **Daily Reviser** - Runs once per day
   - Revises all hourly notes with full day context
   - Normalizes entities across notes
   - Builds typed graph edges with weights
   - Runs integrity checkpoint
   - Deletes raw artifacts only after successful completion

### Primary UI

Desktop Chat UI with time filtering, note retrieval, and graph-expanded search.

## Data Layout

```
Trace/
├── notes/YYYY/MM/DD/          # Durable Markdown notes
│   ├── hour-YYYYMMDD-HH.md
│   └── day-YYYYMMDD.md
├── db/trace.sqlite            # Source of truth for metadata, entities, edges
├── index/                     # Vector embeddings (if not in SQLite)
└── cache/                     # Temporary, deleted daily after revision
    ├── screenshots/YYYYMMDD/
    ├── text_buffers/YYYYMMDD/
    └── ocr/YYYYMMDD/
```

## Database Schema

Core tables: `notes`, `entities`, `note_entities`, `edges`, `events`, `screenshots`, `text_buffers`, `jobs`, `aggregates`

Key edge types: `ABOUT_TOPIC`, `WATCHED`, `LISTENED_TO`, `USED_APP`, `VISITED_DOMAIN`, `DOC_REFERENCE`, `CO_OCCURRED_WITH`, `STUDIED_WHILE`

## Key Constraints

- Notes must never contain full document/website contents (only small capped snippets)
- Raw artifacts (screenshots, text buffers) deleted daily after successful revision
- Deletion blocked if integrity checkpoint fails
- All LLM outputs must be validated JSON conforming to versioned schemas
- Time filters in queries are hard constraints

## Tech Stack

- **Backend**: Python 3.11+ (core logic, capture, LLM calls, database)
- **Frontend**: Electron + React
- **Database**: SQLite with sqlite-vec extension for embeddings
- **LLM Provider**: OpenAI API
  - Frame triage: gpt-5-nano-2025-08-07
  - Hourly summarization: gpt-5-mini-2025-08-07
  - Daily revision: gpt-5.2-2025-12-11
- **OCR**: LLM-based via OpenAI vision API
- **IPC**: Python subprocess managed by Electron main process

## Planning Workflow

- For any non-trivial feature or change:
  1. First run `/plan-from-prd`
  2. Answer all clarifying questions in detail
  3. Review the generated `PLAN.md` and edit manually if needed
  4. Only then start implementation work
- Treat `PLAN.md` as the single source of truth for implementation tasks on this branch
- Update task status in `PLAN.md` as work progresses (`[ ]` → `[x]`)
