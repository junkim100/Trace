"""
File Watcher Service for Trace

Watches the notes directory for file changes and syncs them to the database.
Uses watchdog with macOS FSEvents for native, efficient file monitoring.

Key features:
- Debounced event handling (1s per path) to coalesce rapid edits
- Write suppression registry to prevent circular sync when pipeline writes files
- Content hashing to skip unchanged files
- Frontmatter parsing for metadata extraction
- Preserves rich pipeline data (activities, details, media) that isn't in Markdown
"""

import json
import logging
import re
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.core.hashing import compute_file_hash
from src.core.paths import NOTES_DIR
from src.db.fts import delete_note_fts, index_note_fts
from src.db.migrations import get_connection
from src.summarize.render import parse_frontmatter

logger = logging.getLogger(__name__)

# Debounce interval in seconds
DEBOUNCE_SECONDS = 1.0

# Suppression TTL in seconds
SUPPRESSION_TTL = 5.0

# Pattern for valid note filenames
NOTE_FILE_PATTERN = re.compile(r"^(hour|day)-.*\.md$")

# Temp/junk file patterns to ignore
IGNORE_PATTERNS = {".tmp", "~", ".swp", ".DS_Store", ".bak"}


class WriteSuppressionRegistry:
    """
    Thread-safe registry tracking pipeline-initiated file writes.

    When the pipeline (summarizer, reviser, etc.) is about to write a file,
    it registers the expected content hash. The file watcher checks this
    registry to avoid re-syncing changes it already knows about.

    Entries auto-expire after SUPPRESSION_TTL seconds.
    """

    def __init__(self):
        self._entries: dict[str, tuple[str, float]] = {}  # path -> (hash, timestamp)
        self._lock = threading.Lock()

    def register(self, file_path: str | Path, content_hash: str) -> None:
        """
        Register an expected file write.

        Args:
            file_path: Absolute path to the file being written
            content_hash: SHA-256 hash of the content being written
        """
        key = str(file_path)
        with self._lock:
            self._entries[key] = (content_hash, time.monotonic())

    def should_suppress(self, file_path: str | Path, content_hash: str) -> bool:
        """
        Check if a file change should be suppressed (was pipeline-initiated).

        Also cleans up the entry if found (one-time use).

        Args:
            file_path: Path to the changed file
            content_hash: Hash of the current file content

        Returns:
            True if the change was pipeline-initiated and should be skipped
        """
        key = str(file_path)
        now = time.monotonic()

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False

            registered_hash, registered_time = entry

            # Expired
            if now - registered_time > SUPPRESSION_TTL:
                del self._entries[key]
                return False

            # Hash matches — this is a pipeline write
            if registered_hash == content_hash:
                del self._entries[key]
                return True

            return False

    def cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (_, ts) in self._entries.items() if now - ts > SUPPRESSION_TTL]
            for k in expired:
                del self._entries[k]


# Module-level singleton
_suppression_registry: WriteSuppressionRegistry | None = None
_registry_lock = threading.Lock()


def get_suppression_registry() -> WriteSuppressionRegistry:
    """Get the global write suppression registry singleton."""
    global _suppression_registry
    if _suppression_registry is None:
        with _registry_lock:
            if _suppression_registry is None:
                _suppression_registry = WriteSuppressionRegistry()
    return _suppression_registry


class NoteChangeHandler(FileSystemEventHandler):
    """
    Handles filesystem events for note files.

    Filters to only hour-*.md and day-*.md files, debounces rapid changes,
    and dispatches sync operations.
    """

    def __init__(self, db_path: Path | None = None):
        super().__init__()
        self.db_path = db_path
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _is_note_file(self, path: str) -> bool:
        """Check if path is a valid note file."""
        name = Path(path).name
        # Ignore temp/junk files
        if any(name.endswith(p) for p in IGNORE_PATTERNS):
            return False
        return bool(NOTE_FILE_PATTERN.match(name))

    def _debounced_sync(self, file_path: str, action: str) -> None:
        """Schedule a debounced sync for a file path."""
        with self._lock:
            # Cancel existing timer for this path
            existing = self._debounce_timers.get(file_path)
            if existing is not None:
                existing.cancel()

            # Schedule new timer
            timer = threading.Timer(
                DEBOUNCE_SECONDS,
                self._execute_sync,
                args=(file_path, action),
            )
            timer.daemon = True
            self._debounce_timers[file_path] = timer
            timer.start()

    def _execute_sync(self, file_path: str, action: str) -> None:
        """Execute the sync operation after debounce."""
        with self._lock:
            self._debounce_timers.pop(file_path, None)

        try:
            if action == "delete":
                _sync_file_deletion(file_path, self.db_path)
            elif action == "modify":
                _sync_file_to_db(file_path, self.db_path)
        except Exception as e:
            logger.error(f"File sync failed for {file_path} ({action}): {e}")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_note_file(event.src_path):
            return
        logger.debug(f"Note file created: {event.src_path}")
        self._debounced_sync(event.src_path, "modify")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_note_file(event.src_path):
            return
        logger.debug(f"Note file modified: {event.src_path}")
        self._debounced_sync(event.src_path, "modify")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or not self._is_note_file(event.src_path):
            return
        logger.debug(f"Note file deleted: {event.src_path}")
        self._debounced_sync(event.src_path, "delete")

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_is_note = self._is_note_file(event.src_path)
        dest_is_note = hasattr(event, "dest_path") and self._is_note_file(event.dest_path)

        if src_is_note and dest_is_note:
            # Note renamed/moved — update path in DB, then sync content
            _sync_file_move(event.src_path, event.dest_path, self.db_path)
            self._debounced_sync(event.dest_path, "modify")
        elif src_is_note:
            # Note moved to non-note path — treat as deletion
            self._debounced_sync(event.src_path, "delete")
        elif dest_is_note:
            # Non-note moved to note path — treat as creation
            self._debounced_sync(event.dest_path, "modify")

    def cancel_all_timers(self) -> None:
        """Cancel all pending debounce timers."""
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()


class NoteFileWatcher:
    """
    Watches the notes directory for file changes and syncs to DB.

    Wraps watchdog Observer with lifecycle management.
    """

    def __init__(
        self,
        notes_dir: Path | None = None,
        db_path: Path | None = None,
    ):
        self._notes_dir = notes_dir or NOTES_DIR
        self._db_path = db_path
        self._observer: Observer | None = None
        self._handler: NoteChangeHandler | None = None
        self._running = False

    def start(self) -> bool:
        """
        Start watching the notes directory.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("File watcher already running")
            return True

        if not self._notes_dir.exists():
            self._notes_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._handler = NoteChangeHandler(db_path=self._db_path)
            self._observer = Observer()
            self._observer.schedule(self._handler, str(self._notes_dir), recursive=True)
            self._observer.daemon = True
            self._observer.start()
            self._running = True
            logger.info(f"File watcher started on {self._notes_dir}")

            # Run backfill of content_hash in background
            thread = threading.Thread(
                target=self._backfill_content_hashes,
                daemon=True,
                name="hash-backfill",
            )
            thread.start()

            return True
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        """Stop the file watcher."""
        if self._handler:
            self._handler.cancel_all_timers()

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        self._handler = None
        self._running = False
        logger.info("File watcher stopped")

    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running and self._observer is not None and self._observer.is_alive()

    def _backfill_content_hashes(self) -> None:
        """Backfill content_hash for existing notes that have NULL hashes."""
        try:
            conn = get_connection(self._db_path)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT note_id, file_path FROM notes WHERE content_hash IS NULL")
                rows = cursor.fetchall()

                if not rows:
                    return

                logger.info(f"Backfilling content_hash for {len(rows)} notes")
                updated = 0

                for i in range(0, len(rows), 100):
                    batch = rows[i : i + 100]
                    for row in batch:
                        file_path = Path(row["file_path"])
                        if file_path.exists():
                            try:
                                content_hash = compute_file_hash(file_path)
                                cursor.execute(
                                    "UPDATE notes SET content_hash = ? WHERE note_id = ?",
                                    (content_hash, row["note_id"]),
                                )
                                updated += 1
                            except Exception as e:
                                logger.debug(f"Failed to hash {file_path}: {e}")
                    conn.commit()

                logger.info(f"Backfilled content_hash for {updated} notes")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Content hash backfill failed: {e}")


def _sync_file_to_db(file_path: str, db_path: Path | None = None) -> None:
    """
    Sync a note file's content to the database.

    Core merge logic:
    1. Read file and compute hash
    2. Check suppression registry (skip if pipeline-initiated)
    3. Compare with stored hash (skip if unchanged)
    4. Parse frontmatter and body
    5. Merge into existing json_payload (preserve rich data)
    6. Update DB and FTS index

    Args:
        file_path: Absolute path to the note file
        db_path: Path to SQLite database
    """
    path = Path(file_path)
    if not path.exists():
        return

    # Read file and compute hash
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return

    content_hash = compute_file_hash(path)

    # Check suppression registry
    registry = get_suppression_registry()
    if registry.should_suppress(file_path, content_hash):
        logger.debug(f"Suppressed sync for pipeline write: {path.name}")
        return

    # Parse frontmatter
    frontmatter, body = parse_frontmatter(content)
    if not frontmatter:
        logger.debug(f"No frontmatter in {path.name}, skipping sync")
        return

    note_id = frontmatter.get("id")
    if not note_id:
        logger.debug(f"No id in frontmatter of {path.name}")
        return

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Look up existing record
        cursor.execute(
            "SELECT note_id, json_payload, content_hash, rowid FROM notes WHERE note_id = ?",
            (note_id,),
        )
        row = cursor.fetchone()

        if row is None:
            # New file — try to find by file_path
            cursor.execute(
                "SELECT note_id, json_payload, content_hash, rowid FROM notes WHERE file_path = ?",
                (file_path,),
            )
            row = cursor.fetchone()

        if row is not None:
            # Check if content actually changed
            stored_hash = row["content_hash"]
            if stored_hash == content_hash:
                logger.debug(f"Content unchanged for {path.name}, skipping")
                return

            # Merge into existing payload
            existing_payload = {}
            if row["json_payload"]:
                try:
                    existing_payload = json.loads(row["json_payload"])
                except json.JSONDecodeError:
                    pass

            updated_payload = _merge_file_into_payload(existing_payload, frontmatter, body)

            cursor.execute(
                """
                UPDATE notes
                SET json_payload = ?, content_hash = ?, file_path = ?, updated_ts = ?
                WHERE note_id = ?
                """,
                (
                    json.dumps(updated_payload),
                    content_hash,
                    file_path,
                    _now_iso(),
                    row["note_id"],
                ),
            )
            conn.commit()

            # Update FTS index
            try:
                rowid = row["rowid"]
                index_note_fts(
                    conn,
                    rowid,
                    updated_payload.get("summary", ""),
                    updated_payload.get("categories"),
                    updated_payload.get("entities"),
                )
            except Exception as e:
                logger.warning(f"FTS index update failed for {note_id}: {e}")

            logger.info(f"Synced file change to DB: {path.name}")

        else:
            # Brand new file not in DB — insert
            note_type = frontmatter.get("type", "hour")
            start_time = frontmatter.get("start_time")
            end_time = frontmatter.get("end_time")

            if not start_time or not end_time:
                logger.debug(f"Missing timestamps in {path.name}, skipping insert")
                return

            payload = _build_payload_from_file(frontmatter, body)

            now = _now_iso()
            cursor.execute(
                """
                INSERT INTO notes
                (note_id, note_type, start_ts, end_ts, file_path, json_payload,
                 content_hash, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    note_type,
                    start_time,
                    end_time,
                    file_path,
                    json.dumps(payload),
                    content_hash,
                    now,
                    now,
                ),
            )
            conn.commit()

            # Index in FTS
            try:
                rowid = cursor.lastrowid
                index_note_fts(
                    conn,
                    rowid,
                    payload.get("summary", ""),
                    payload.get("categories"),
                    payload.get("entities"),
                )
            except Exception as e:
                logger.warning(f"FTS index failed for new note {note_id}: {e}")

            logger.info(f"Indexed new file to DB: {path.name}")

    finally:
        conn.close()


def _sync_file_deletion(file_path: str, db_path: Path | None = None) -> None:
    """
    Handle deletion of a note file by removing its DB records.

    Args:
        file_path: Path of the deleted file
        db_path: Path to SQLite database
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Find the note by file path
        cursor.execute(
            "SELECT note_id, rowid, start_ts FROM notes WHERE file_path = ?",
            (file_path,),
        )
        row = cursor.fetchone()

        if row is None:
            return

        note_id = row["note_id"]
        rowid = row["rowid"]
        start_ts = row["start_ts"]

        # Delete from all related tables
        cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
        cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note_id,))
        cursor.execute(
            "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
            (note_id,),
        )
        cursor.execute(
            "DELETE FROM jobs WHERE job_type = 'hourly' AND window_start_ts = ?",
            (start_ts,),
        )

        # Delete from FTS
        try:
            delete_note_fts(conn, rowid)
        except Exception:
            pass

        conn.commit()
        logger.info(f"Deleted DB records for removed file: {Path(file_path).name}")

    finally:
        conn.close()


def _sync_file_move(src_path: str, dest_path: str, db_path: Path | None = None) -> None:
    """
    Handle a file move by updating the file_path in DB.

    Args:
        src_path: Original file path
        dest_path: New file path
        db_path: Path to SQLite database
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE notes SET file_path = ?, updated_ts = ? WHERE file_path = ?",
            (dest_path, _now_iso(), src_path),
        )
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Updated file path: {Path(src_path).name} -> {Path(dest_path).name}")
    finally:
        conn.close()


def _merge_file_into_payload(existing_payload: dict, frontmatter: dict, body: str) -> dict:
    """
    Merge file content into existing json_payload, preserving rich pipeline data.

    Replaces: summary, categories, entities, location (from file)
    Preserves: activities, details, media, documents, websites, is_idle, topics,
               co_activities (rich data not representable in Markdown)

    Args:
        existing_payload: Current json_payload from DB
        frontmatter: Parsed YAML frontmatter
        body: Markdown body content

    Returns:
        Merged payload dict
    """
    updated = existing_payload.copy()

    # Extract summary from body (text under first ## Summary heading)
    summary = _extract_summary(body)
    if summary:
        updated["summary"] = summary

    # Update from frontmatter
    if "categories" in frontmatter:
        updated["categories"] = frontmatter["categories"]

    if "entities" in frontmatter:
        updated["entities"] = frontmatter["entities"]

    if "location" in frontmatter:
        updated["location"] = frontmatter["location"]

    return updated


def _build_payload_from_file(frontmatter: dict, body: str) -> dict:
    """
    Build a json_payload from a file that has no existing DB record.

    Args:
        frontmatter: Parsed YAML frontmatter
        body: Markdown body content

    Returns:
        Payload dict
    """
    summary = _extract_summary(body) or ""

    return {
        "summary": summary,
        "categories": frontmatter.get("categories", []),
        "entities": frontmatter.get("entities", []),
        "location": frontmatter.get("location"),
        "schema_version": frontmatter.get("schema_version", 3),
    }


def _extract_summary(body: str) -> str | None:
    """
    Extract the summary text from the Markdown body.

    Looks for text between ## Summary heading and the next ## heading.

    Args:
        body: Markdown body content

    Returns:
        Summary text or None
    """
    match = re.search(r"## Summary\s*\n\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _now_iso() -> str:
    """Get current time as ISO string."""
    from datetime import datetime

    return datetime.now().isoformat()
