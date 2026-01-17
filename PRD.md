# Trace PRD, MVP, macOS

**Product name:** Trace
**Description:** A second brain built from your digital activity
**Audience:** Engineering implementation, intended for a coding agent
**Platform:** macOS, single device
**Primary UI:** Desktop app for Chat UI
**Background processes:** Continuous capture, evidence building, hourly summarization, daily revision, indexing, deletion

---

## 1) Product overview

Trace is a macOS app that continuously observes a user’s digital activity, converts it into durable Markdown notes, stores typed relationships in a local graph, and enables time-aware chat and search over the user’s past activity.

Trace captures multi-monitor screenshots and contextual signals (active app, window title, best-effort browser URL, document text extracted in real time, background media like Spotify, and OS location). Every hour it generates an Hourly Note in Markdown. Once per day it revises that day’s notes using the full day’s evidence, builds a typed relationship graph, updates indices, and then deletes all raw activity artifacts for that day.

---

## 2) Goals and non-goals

### 2.1 Goals (MVP)

1. **Automatic recall by time and topic**
   Answer questions like “What games was I into in July 2025?” or “What did I watch while studying machine learning?” with reliable time filtering.

2. **Durable Markdown-first record**
   Notes are saved as Markdown files on disk, readable without Trace.

3. **Typed relationships stored outside notes**
   Relationships are stored in a database as typed, weighted edges, used to improve retrieval and answers.

4. **Concurrent context**
   Trace understands overlapping activities, for example reading a PDF while music is playing in the background.

5. **Daily deletion of raw artifacts**
   Screenshots and transient extracted text buffers are deleted daily after a successful revision and integrity checkpoint.

### 2.2 Non-goals (MVP)

* Cross-device sync
* Collaboration, sharing
* Per-app or per-site exclusion lists, pause, private mode (deferred)
* Perfect URL capture for all browsers (no browser extension, best-effort only)
* Saving full website contents or full file contents into notes
* Long-term retention of raw screenshots or full extracted document text

---

## 3) Target user and core use cases

### 3.1 Target user

A single-device macOS user who wants an automatic second brain, built from what they actually did on their computer, with strong time recall and topic recall.

### 3.2 Primary use cases

1. **Time recall**: “What was I doing on July 14, 2025 around 7pm?”
2. **Topic recall**: “When was I studying activation functions, and what resources did I use?”
3. **Entertainment recall**: “Which gameplays did I watch the most in July 2025?”
4. **Co-activity recall**: “What music did I listen to while reading that PDF?”
5. **Relationship-driven discovery**: “Show me related sessions where I worked on X and also watched Y.”

---

## 4) MVP scope, requirements

### 4.1 Always-on capture (background)

#### 4.1.1 Screenshot capture

* Capture cadence: **every 1 second**
* Multi-monitor: **capture each monitor**
* Downscale: persisted screenshots must be capped to **1080p class**, preserve aspect ratio, never store higher resolution than needed
* Dedup: if a monitor’s screen does not meaningfully change, do not persist additional screenshots for that monitor, but still track dwell time

**Acceptance criteria**

* Supports multiple monitors, persists screenshots only on meaningful change.
* When a screen is static for N seconds, at most 1 screenshot is stored for that static period per monitor.
* Disk usage is bounded by dedup plus daily deletion.

#### 4.1.2 Foreground activity metadata

Capture at least:

* Foreground app bundle id and name
* Foreground window title (best-effort)
* Focused monitor id
* Time range for the “active span” (start, end)

**Acceptance criteria**

* App and window transitions are recorded as time-ranged spans even if screenshots are deduped.

#### 4.1.3 Background activity signals (MVP)

Required for MVP:

* Now playing state, at minimum Spotify and Apple Music (track, artist, app, timestamps)
* OS location services (plain text), store location snapshots with timestamps

**Acceptance criteria**

* Music metadata continues to be captured even when the music app is not in foreground.
* Location is recorded when available, and tied to event spans or snapshots.

---

### 4.2 Best-effort URL capture without a browser extension

Trace should attempt URL capture using a tiered approach:

1. Browser automation for supported browsers (MVP target: Safari and Chrome, optionally Edge)
2. Fallback to window title, store page title and infer domain if possible
3. Optional OCR on a small address bar crop when needed

**Acceptance criteria**

* For supported browsers, URL is captured for the active tab in most cases.
* When URL cannot be captured, Trace still stores page title and domain inference when possible.

---

### 4.3 Real-time document text extraction (survive deletions)

Trace must extract text while the user is viewing a document because the file might be deleted later.

#### 4.3.1 Triggers

Start extraction when any is true:

* Foreground app indicates a document viewer/editor
* Window title indicates a local document
* A classifier labels the screen as document-like
* Dwell time in a document context exceeds a threshold (configurable)

#### 4.3.2 Extraction methods

1. If file path is known and format supported (PDF first), extract text directly.
2. Otherwise OCR selected frames at a controlled rate (page changes, or periodic anchors).

#### 4.3.3 Storage and constraints

* Store extracted text as **transient buffers**, not durable notes.
* Notes must not contain full document contents.
* Notes may include only small, necessary snippets, capped.

**Acceptance criteria**

* If a user spends meaningful time reading a PDF, the topics and key takeaways can appear in the hourly note even if the original file is later deleted.

---

### 4.4 Hourly summarization into Markdown

Every hour, Trace generates an Hourly Note for the previous hour.

#### 4.4.1 Inputs

* Aggregated event timeline for the hour
* A curated set of representative screenshots (keyframes), not all frames
* Selected text buffer snippets (bounded)
* Now playing timeline
* Location snapshots/timeline

#### 4.4.2 Outputs

* One Markdown file per hour
* Structured JSON representation stored in the database (source of truth for metadata)
* Entities extracted and normalized
* Embedding computed for retrieval

#### 4.4.3 Content constraints

* Do not include website body content.
* Do not include full document contents.
* Keep details sufficient for later recall and analytics-style questions.

**Acceptance criteria**

* Hourly note includes activities, topics, media consumed, and co-activity overlaps when present.
* Note has reliable timestamps and is searchable by time range.

---

### 4.5 Daily revision pass and graph building

Once per day, Trace revises all notes for the previous day while raw evidence still exists, then deletes raw artifacts.

#### 4.5.1 Daily revision responsibilities

* Load all hourly notes for the day (Markdown + stored JSON)
* Use the day’s evidence (selected keyframes, text buffers, event aggregates) to:

  * fix entity names and normalize categories
  * merge duplicates
  * improve co-activity detection summaries
* Generate an optional Daily Summary Note (recommended in MVP)
* Build typed graph edges and weights
* Refresh embeddings for revised notes
* Update aggregates for “most” style queries

#### 4.5.2 Typed graph edge requirements

Relationships must be stored outside Markdown, in the database, as typed weighted edges with time spans.

Minimum edge types for MVP:

* `ABOUT_TOPIC` (note -> topic entity)
* `WATCHED` (note -> content entity, game/video)
* `LISTENED_TO` (note -> artist/track entity)
* `USED_APP` (note -> app entity)
* `VISITED_DOMAIN` (note -> domain entity)
* `DOC_REFERENCE` (note -> document entity)
* `CO_OCCURRED_WITH` (note -> note)
* `STUDIED_WHILE` (note -> note), for foreground study overlaps with background media

**Acceptance criteria**

* Graph traversal can expand retrieval beyond direct text similarity.
* Edges include weights and time ranges to support time-aware reasoning.

---

### 4.6 Daily deletion of raw artifacts

After a successful daily revision and integrity checkpoint, Trace deletes:

* All cached screenshots for that day
* All transient extracted text buffers for that day
* OCR intermediates for that day

**Acceptance criteria**

* No deletion happens if the daily job fails or integrity checks fail.
* Deletion happens automatically after success.

---

### 4.7 Desktop Chat UI

Trace provides a desktop app with:

* Chat prompt input
* Time filter UI (date range, quick presets)
* Results list of relevant notes
* Ability to open note files from results

**Acceptance criteria**

* Queries respect time filters as hard constraints when specified.
* Answers cite which notes and time ranges were used.

---

## 5) End-to-end logic and pipelines

### 5.1 Capture pipeline (every second)

For each monitor:

1. Capture frame
2. Downscale to <= 1080p class
3. Compute fingerprint + diff score vs last persisted frame
4. Persist screenshot only if changed, or periodic anchor rule triggers
5. Update current event span with latest metadata

Separately:

* Poll or subscribe to now playing updates
* Record location snapshots when available

### 5.2 Evidence building pipeline

* If document context detected:

  * extract text directly if possible, else OCR selected frames
* Store text in transient buffers linked to time spans

### 5.3 Evidence selection per hour

Local selection rules:

* Always include frames at app/window transitions
* Include top diff-score frames
* Include periodic anchors during long segments (reading, video)
* Cap number of frames sent to the summarizer

### 5.4 Hourly summarization pipeline

* Build compact timeline summary
* Call LLM with curated evidence
* Validate JSON output, retry once on schema failure
* Render Markdown from JSON
* Store JSON, entities, embeddings, metadata

### 5.5 Daily revision and graph pipeline

* Reprocess the day’s hourly notes with day context
* Normalize entities and categories
* Build typed edges with deterministic and model-proposed steps
* Refresh embeddings and indices
* Run integrity checkpoint
* Delete raw artifacts after success

---

## 6) Data model

### 6.1 File layout

Durable:

* `Trace/notes/YYYY/MM/DD/hour-YYYYMMDD-HH.md`
* `Trace/notes/YYYY/MM/DD/day-YYYYMMDD.md` (optional but recommended)
* `Trace/db/trace.sqlite`
* `Trace/index/` (if vectors not embedded in SQLite)

Temporary:

* `Trace/cache/screenshots/YYYYMMDD/`
* `Trace/cache/text_buffers/YYYYMMDD/`
* `Trace/cache/ocr/YYYYMMDD/`

### 6.2 Hourly note format (Markdown + YAML frontmatter)

**Required frontmatter**

* `id`: UUID
* `type`: `hour`
* `start_time`, `end_time`: ISO-8601
* `location`: string or null
* `categories`: list
* `entities`: list of `{name, type, confidence}`
* `schema_version`: integer

**Body sections**

* Summary
* Activities (time anchored)
* Topics and learning
* Media
* Co-activities
* Open loops (optional)

### 6.3 Database tables (suggested MVP schema)

```sql
CREATE TABLE notes (
  note_id TEXT PRIMARY KEY,
  note_type TEXT NOT NULL,           -- 'hour' or 'day'
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  file_path TEXT NOT NULL,
  json_payload TEXT NOT NULL,        -- validated structured output
  embedding_id TEXT,
  created_ts TEXT NOT NULL,
  updated_ts TEXT NOT NULL
);

CREATE TABLE entities (
  entity_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,         -- topic, game, app, domain, doc, artist, track, etc
  canonical_name TEXT NOT NULL
);

CREATE TABLE note_entities (
  note_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  strength REAL NOT NULL,
  PRIMARY KEY (note_id, entity_id)
);

CREATE TABLE edges (
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  weight REAL NOT NULL,
  start_ts TEXT,
  end_ts TEXT,
  evidence_note_ids TEXT,            -- JSON list of note_ids
  created_ts TEXT NOT NULL,
  PRIMARY KEY (from_id, to_id, edge_type)
);

-- Transient activity timeline
CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  app_id TEXT,
  app_name TEXT,
  window_title TEXT,
  focused_monitor INTEGER,
  url TEXT,
  page_title TEXT,
  file_path TEXT,
  location_text TEXT,
  now_playing_json TEXT,             -- JSON: track/artist/app
  evidence_ids TEXT                  -- JSON list of screenshot_id/text_id references
);

CREATE TABLE screenshots (
  screenshot_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  monitor_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  diff_score REAL NOT NULL
);

CREATE TABLE text_buffers (
  text_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  source_type TEXT NOT NULL,         -- pdf_extract, ocr
  ref TEXT,                          -- file_path or screenshot_id
  compressed_text BLOB NOT NULL,
  token_estimate INTEGER NOT NULL
);

CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,            -- hourly, daily
  window_start_ts TEXT NOT NULL,
  window_end_ts TEXT NOT NULL,
  status TEXT NOT NULL,              -- pending, running, success, failed
  attempts INTEGER NOT NULL,
  last_error TEXT,
  created_ts TEXT NOT NULL,
  updated_ts TEXT NOT NULL
);

-- Optional but recommended for "most watched/listened" queries
CREATE TABLE aggregates (
  agg_id TEXT PRIMARY KEY,
  period_type TEXT NOT NULL,         -- day, month
  period_start_ts TEXT NOT NULL,
  period_end_ts TEXT NOT NULL,
  key_type TEXT NOT NULL,            -- category, entity, co_activity
  key TEXT NOT NULL,
  value_num REAL NOT NULL,           -- minutes or counts
  extra_json TEXT
);
```

---

## 7) Retrieval and chat logic

### 7.1 Retrieval pipeline

1. Parse query for time constraints, apply hard filter when specified.
2. Vector search over candidate notes in time range.
3. Expand with graph edges:

   * pull top related notes and entities by weight
4. If query asks for “most” or counting, consult aggregates first, then support with notes.

### 7.2 Answer synthesis

* Generate answer grounded in retrieved notes and aggregates.
* Include citations to note IDs and time ranges.
* Do not invent facts beyond retrieved evidence.

---

## 8) LLM integration requirements

### 8.1 Model roles

Trace should support tiered model usage:

* Small vision-capable model for frame triage and importance scoring (optional but recommended)
* Main vision-capable model for hourly summarization and daily revision
* Escalation model for failures or complex days

### 8.2 Structured outputs

All LLM calls that write durable artifacts must:

* Return strict JSON conforming to a versioned schema
* Be validated, retry once on failure
* Store the accepted JSON in the database

### 8.3 Evidence budgets

Even without cost constraints, impose budgets for:

* max keyframes per hour
* max OCR snippet tokens per hour
* max total tokens per summarization call
  This ensures stable runtime and avoids overloading the system.

---

## 9) Reliability, integrity, and deletion

### 9.1 Idempotency

* Hourly jobs keyed by exact hour window
* Daily jobs keyed by exact day window
* Re-running jobs updates notes and indices deterministically

### 9.2 Integrity checkpoint before deletion

Do not delete raw artifacts for a day unless:

1. All hourly notes exist and parse
2. Daily revision finished successfully
3. Embeddings exist for all revised notes
4. Graph edges written successfully
5. Note files exist for all `notes.file_path`
6. Database references are consistent

### 9.3 Failure behavior

* If daily revision fails, do not delete that day’s cache.
* Mark job as failed and retry later.

---

## 10) Performance and non-functional requirements

* Capture should not noticeably degrade system responsiveness.
* Dedup should be lightweight, based on downsampled fingerprints and diff scores.
* OCR and text extraction should be rate-limited.
* All storage is local, single device.
* Location is stored in plain text for MVP.

---

## 11) MVP success metrics

* Users can answer time-based recall questions accurately.
* Entities (topics, games, artists, domains) appear consistently across notes.
* Co-activity detection (study while listening/watching) appears when supported by evidence.
* Daily deletion occurs reliably after successful revision.

---

## 12) Implementation milestones (recommended order)

1. **Capture daemon v0**

* multi-monitor screenshots, 1s cadence, 1080p cap, dedup
* foreground app/window spans
* now playing and location snapshots
* events stored in SQLite

2. **Evidence builder v0**

* PDF extraction and OCR fallback
* transient text buffers

3. **Hourly summarizer v0**

* hourly scheduler
* evidence selection
* schema-first JSON output, Markdown rendering
* embeddings

4. **Daily reviser + graph v0**

* revise hourly notes
* build typed edges
* refresh embeddings
* integrity checkpoint + deletion

5. **Chat UI v0**

* time filter, retrieval, graph expansion
* answer synthesis with citations

6. **Aggregates v0**

* daily and monthly rollups for “most” questions

---

## 13) Explicit MVP constraints and known limitations

* URL capture coverage depends on supported browsers and automation reliability.
* Some apps may not expose file paths, OCR fallback will be used.
* Background events beyond now playing are limited in MVP.

---

