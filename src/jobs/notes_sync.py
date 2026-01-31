"""
Notes Sync Service for Trace

Provides comprehensive bidirectional synchronization between the notes database
and the filesystem. This service ensures:

1. DB → Filesystem: Regenerates missing markdown files from json_payload
2. Filesystem → DB: Indexes notes that exist on disk but not in DB
3. Orphan Cleanup: Removes DB records for files that no longer exist
4. Empty Note Cleanup: Removes notes with placeholder/empty content

The sync service runs on startup and periodically to maintain consistency.

Empty note detection rules:
- Summary contains "no activity", "no notes", "no summary available", etc.
- No meaningful activities recorded
- Summary is too short (< 50 chars)
- Only trivial categories/content
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH, NOTES_DIR
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


# Phrases that indicate empty/placeholder notes
EMPTY_NOTE_INDICATORS = [
    "no summary available",
    "no activity detected",
    "no activity",
    "no meaningful activity",
    "no activity details",
    "no details were captured",
    "no details captured",
    "insufficient evidence",
    "no evidence available",
    "no evidence to",
    "unable to generate",
    "could not generate",
    "nothing to summarize",
    "no notable activity",
    "missing note",
    "wasn't enough evidence",
    "isn't enough evidence",
    "not enough information",
    "not enough data",
    "no data available",
    "placeholder",
    "n/a",
    "none available",
    "activity unknown",
    "unknown activity",
    "no specific activity",
    "general computer use",
    "various tasks",
    "miscellaneous",
    "no notes",
    "no content",
    "empty note",
    "idle time",
    "system idle",
    "screen saver",
    "lock screen",
]

# Minimum summary length to be considered valid
MIN_SUMMARY_LENGTH = 50


@dataclass
class SyncResult:
    """Result of a sync operation."""

    # Filesystem → DB sync
    notes_on_disk: int = 0
    notes_in_db: int = 0
    notes_indexed: int = 0
    notes_index_failed: int = 0

    # DB → Filesystem sync
    files_missing: int = 0
    files_recovered: int = 0
    files_recover_failed: int = 0

    # Orphan cleanup
    orphaned_db_records: int = 0
    orphaned_cleaned: int = 0

    # Empty note cleanup
    empty_notes_found: int = 0
    empty_notes_removed: int = 0

    # Detailed lists for reporting
    indexed_notes: list[dict] = field(default_factory=list)
    recovered_files: list[dict] = field(default_factory=list)
    removed_orphans: list[dict] = field(default_factory=list)
    removed_empty: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if any changes were made."""
        return (
            self.notes_indexed > 0
            or self.files_recovered > 0
            or self.orphaned_cleaned > 0
            or self.empty_notes_removed > 0
        )


class NotesSyncService:
    """
    Bidirectional sync service for notes database and filesystem.

    Consolidates all sync operations into a single service that can be
    run on startup and periodically to ensure consistency.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        notes_dir: Path | str | None = None,
    ):
        """
        Initialize the sync service.

        Args:
            db_path: Path to SQLite database
            notes_dir: Path to notes directory
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.notes_dir = Path(notes_dir) if notes_dir else NOTES_DIR

    def sync_all(
        self,
        remove_empty: bool = True,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Run complete bidirectional sync.

        The sync runs in this order:
        1. Index notes from filesystem → DB (so we have all notes in DB)
        2. Recover missing files from DB → filesystem
        3. Clean up orphaned DB records (files that were deleted)
        4. Remove empty notes (placeholder content)

        Args:
            remove_empty: Whether to remove empty notes
            dry_run: If True, only report what would be done without making changes

        Returns:
            SyncResult with detailed statistics
        """
        result = SyncResult()

        logger.info(f"Starting notes sync (dry_run={dry_run}, remove_empty={remove_empty})")

        # Step 1: Index notes from filesystem → DB
        self._sync_filesystem_to_db(result, dry_run)

        # Step 2: Recover missing files from DB → filesystem
        self._sync_db_to_filesystem(result, dry_run)

        # Step 3: Clean up orphaned DB records
        self._cleanup_orphaned_records(result, dry_run)

        # Step 4: Remove empty notes
        if remove_empty:
            self._cleanup_empty_notes(result, dry_run)

        if result.has_changes:
            logger.info(
                f"Sync complete: indexed={result.notes_indexed}, "
                f"recovered={result.files_recovered}, orphans={result.orphaned_cleaned}, "
                f"empty_removed={result.empty_notes_removed}"
            )
        else:
            logger.debug("Sync complete: no changes needed")

        return result

    def _sync_filesystem_to_db(self, result: SyncResult, dry_run: bool) -> None:
        """
        Index notes from filesystem that aren't in the database.

        This handles cases where:
        - Database was recreated
        - Notes were manually created on disk
        - Migration from older version
        """
        from src.summarize.render import parse_frontmatter

        if not self.notes_dir.exists():
            logger.debug(f"Notes directory does not exist: {self.notes_dir}")
            return

        # Find all note files on disk
        hourly_files = list(self.notes_dir.glob("**/hour-*.md"))
        daily_files = list(self.notes_dir.glob("**/day-*.md"))
        note_files = sorted(hourly_files + daily_files)
        result.notes_on_disk = len(note_files)

        if not note_files:
            return

        # Get all note IDs and file paths from database
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT note_id, file_path FROM notes")
            db_notes = {row["note_id"]: row["file_path"] for row in cursor.fetchall()}
            result.notes_in_db = len(db_notes)

            # Also build a set of file paths in DB for checking
            db_file_paths = set(db_notes.values())

            # Find notes on disk that aren't in database
            for file_path in note_files:
                file_path_str = str(file_path)

                # Skip if already in database (by file path)
                if file_path_str in db_file_paths:
                    continue

                # Parse the note file
                try:
                    content = file_path.read_text(encoding="utf-8")
                    frontmatter, body = parse_frontmatter(content)

                    if not frontmatter:
                        logger.debug(f"No frontmatter in {file_path}")
                        continue

                    note_id = frontmatter.get("id")
                    note_type = frontmatter.get("type")
                    start_time = frontmatter.get("start_time")
                    end_time = frontmatter.get("end_time")

                    if not all([note_id, note_type, start_time, end_time]):
                        logger.debug(f"Missing required fields in {file_path}")
                        continue

                    # Skip if note ID already exists (file was moved)
                    if note_id in db_notes:
                        # Update file path in DB
                        if not dry_run:
                            cursor.execute(
                                "UPDATE notes SET file_path = ?, updated_ts = ? WHERE note_id = ?",
                                (file_path_str, datetime.now().isoformat(), note_id),
                            )
                            conn.commit()
                        logger.debug(f"Updated file path for note {note_id}")
                        continue

                    # Build json_payload from frontmatter
                    json_payload = json.dumps(
                        {
                            "summary": body.split("\n\n")[0][:500] if body else "",
                            "categories": frontmatter.get("categories", []),
                            "entities": frontmatter.get("entities", []),
                            "location": frontmatter.get("location"),
                            "schema_version": frontmatter.get("schema_version", 3),
                        }
                    )

                    if not dry_run:
                        now = datetime.now().isoformat()
                        cursor.execute(
                            """
                            INSERT INTO notes
                            (note_id, note_type, start_ts, end_ts, file_path, json_payload,
                             created_ts, updated_ts)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                note_id,
                                note_type,
                                start_time,
                                end_time,
                                file_path_str,
                                json_payload,
                                now,
                                now,
                            ),
                        )
                        conn.commit()

                    result.notes_indexed += 1
                    result.indexed_notes.append(
                        {
                            "note_id": note_id,
                            "note_type": note_type,
                            "file_path": file_path_str,
                        }
                    )
                    logger.info(f"Indexed note from disk: {file_path.name}")

                except Exception as e:
                    result.notes_index_failed += 1
                    result.errors.append(f"Failed to index {file_path}: {e}")
                    logger.error(f"Failed to index {file_path}: {e}")

        finally:
            conn.close()

    def _sync_db_to_filesystem(self, result: SyncResult, dry_run: bool) -> None:
        """
        Recover missing markdown files from database json_payload.

        This handles cases where:
        - Files were accidentally deleted
        - Filesystem corruption
        - Files were moved without updating DB
        """
        from src.revise.daily_note import DailyNoteGenerator
        from src.revise.schemas import DailyRevisionSchema
        from src.summarize.render import MarkdownRenderer
        from src.summarize.schemas import HourlySummarySchema

        hourly_renderer = MarkdownRenderer()
        daily_generator = DailyNoteGenerator(db_path=self.db_path)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                FROM notes
                WHERE json_payload IS NOT NULL AND json_payload != ''
                """
            )

            for row in cursor.fetchall():
                file_path = Path(row["file_path"])

                # Skip if file exists
                if file_path.exists():
                    continue

                result.files_missing += 1
                note_id = row["note_id"]
                note_type = row["note_type"]

                try:
                    if dry_run:
                        result.files_recovered += 1
                        result.recovered_files.append(
                            {
                                "note_id": note_id,
                                "note_type": note_type,
                                "file_path": str(file_path),
                            }
                        )
                        continue

                    payload_data = json.loads(row["json_payload"])

                    if note_type == "hour":
                        summary = HourlySummarySchema.model_validate(payload_data)
                        hour_start = datetime.fromisoformat(row["start_ts"])
                        hour_end = datetime.fromisoformat(row["end_ts"])

                        saved = hourly_renderer.render_to_file(
                            summary=summary,
                            note_id=note_id,
                            hour_start=hour_start,
                            hour_end=hour_end,
                            file_path=file_path,
                            location=summary.location,
                        )

                        if saved:
                            result.files_recovered += 1
                            result.recovered_files.append(
                                {
                                    "note_id": note_id,
                                    "note_type": note_type,
                                    "file_path": str(file_path),
                                }
                            )
                            logger.info(f"Recovered hourly note: {file_path}")
                        else:
                            raise Exception("Renderer returned False")

                    elif note_type == "day":
                        revision = DailyRevisionSchema.model_validate(payload_data)
                        day = datetime.fromisoformat(row["start_ts"])

                        content = daily_generator._render_daily_note(
                            day=day,
                            revision=revision,
                            note_id=note_id,
                        )

                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(content)

                        result.files_recovered += 1
                        result.recovered_files.append(
                            {
                                "note_id": note_id,
                                "note_type": note_type,
                                "file_path": str(file_path),
                            }
                        )
                        logger.info(f"Recovered daily note: {file_path}")

                except Exception as e:
                    result.files_recover_failed += 1
                    result.errors.append(f"Failed to recover {note_id}: {e}")
                    logger.error(f"Failed to recover {note_id}: {e}")

        finally:
            conn.close()

    def _cleanup_orphaned_records(self, result: SyncResult, dry_run: bool) -> None:
        """
        Remove database records for notes whose files no longer exist.

        This handles cases where:
        - Files were manually deleted
        - Files were moved to trash
        - Filesystem cleanup removed old notes
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT note_id, note_type, start_ts, file_path FROM notes")

            orphaned = []
            for row in cursor.fetchall():
                file_path = row["file_path"]
                if file_path and not Path(file_path).exists():
                    orphaned.append(
                        {
                            "note_id": row["note_id"],
                            "note_type": row["note_type"],
                            "start_ts": row["start_ts"],
                            "file_path": file_path,
                        }
                    )

            result.orphaned_db_records = len(orphaned)

            if not orphaned:
                return

            for orphan in orphaned:
                note_id = orphan["note_id"]
                start_ts = orphan["start_ts"]

                if not dry_run:
                    # Delete note and related records
                    cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
                    cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note_id,))
                    cursor.execute(
                        "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
                        (note_id,),
                    )

                    # Also delete job record so hour can be reprocessed
                    cursor.execute(
                        "DELETE FROM jobs WHERE job_type = 'hourly' AND window_start_ts = ?",
                        (start_ts,),
                    )
                    conn.commit()

                result.orphaned_cleaned += 1
                result.removed_orphans.append(orphan)
                logger.info(f"Cleaned up orphaned DB record: {orphan['file_path']}")

        finally:
            conn.close()

    def _cleanup_empty_notes(self, result: SyncResult, dry_run: bool) -> None:
        """
        Remove notes with empty/placeholder content.

        Empty notes are detected by:
        1. Summary contains known empty indicators
        2. No meaningful activities
        3. Summary is too short
        4. No categories/entities
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, file_path, json_payload
                FROM notes
                ORDER BY start_ts DESC
                """
            )

            empty_notes = []
            for row in cursor.fetchall():
                if self._is_empty_note(row):
                    empty_notes.append(
                        {
                            "note_id": row["note_id"],
                            "note_type": row["note_type"],
                            "start_ts": row["start_ts"],
                            "file_path": row["file_path"],
                        }
                    )

            result.empty_notes_found = len(empty_notes)

            if not empty_notes:
                return

            for note in empty_notes:
                note_id = note["note_id"]
                file_path = note["file_path"]
                start_ts = note["start_ts"]

                if not dry_run:
                    # Delete from database
                    cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
                    cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note_id,))
                    cursor.execute(
                        "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
                        (note_id,),
                    )

                    # Delete job record so hour can be reprocessed
                    cursor.execute(
                        "DELETE FROM jobs WHERE job_type = 'hourly' AND window_start_ts = ?",
                        (start_ts,),
                    )

                    # Delete file if it exists
                    if file_path and Path(file_path).exists():
                        try:
                            Path(file_path).unlink()
                            logger.debug(f"Deleted empty note file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete file {file_path}: {e}")

                    conn.commit()

                result.empty_notes_removed += 1
                result.removed_empty.append(note)
                logger.info(f"Removed empty note: {note['start_ts']}")

        finally:
            conn.close()

    def _is_empty_note(self, row: dict) -> bool:
        """
        Check if a note is empty/placeholder content.

        Uses multiple heuristics:
        1. Summary contains empty indicators
        2. No activities or all trivial
        3. Summary too short
        4. No categories
        """
        json_payload = row.get("json_payload")
        file_path = row.get("file_path")

        # Check JSON payload
        if json_payload:
            try:
                payload = json.loads(json_payload)
                summary = (payload.get("summary") or "").lower().strip()
                categories = payload.get("categories", [])
                activities = payload.get("activities", [])
                entities = payload.get("entities", [])

                # Check for empty indicators in summary
                for indicator in EMPTY_NOTE_INDICATORS:
                    if indicator in summary:
                        # Additional check: has no meaningful content
                        if not categories and not activities and not entities:
                            return True
                        # Even with some content, certain indicators mean empty
                        if indicator in [
                            "no summary available",
                            "no activity detected",
                            "no activity",
                            "placeholder",
                            "no notes",
                        ]:
                            if len(activities) == 0:
                                return True

                # Check if summary is too short
                if len(summary) < MIN_SUMMARY_LENGTH:
                    # Very short summary with no activities is empty
                    if not activities:
                        return True

                # Check if only trivial activities
                if activities:
                    non_trivial = self._count_non_trivial_activities(activities)
                    if non_trivial == 0:
                        return True

            except (json.JSONDecodeError, TypeError):
                pass

        # Also check file content if it exists
        if file_path and Path(file_path).exists():
            try:
                content = Path(file_path).read_text(encoding="utf-8").lower()

                # Check for empty indicators
                for indicator in EMPTY_NOTE_INDICATORS:
                    if indicator in content:
                        # Verify it's actually empty by checking for activities section
                        if "## activities" not in content:
                            return True
                        # If activities section exists but has no entries
                        if re.search(r"## activities\s*\n\s*\n", content):
                            return True

            except Exception:
                pass

        return False

    def _count_non_trivial_activities(self, activities: list) -> int:
        """Count activities that are not trivial/idle."""
        trivial_keywords = [
            "idle",
            "lock screen",
            "screen saver",
            "screensaver",
            "sleep",
            "no activity",
            "system idle",
            "away",
            "afk",
            "inactive",
            "standby",
            "login screen",
            "desktop",
            "blank screen",
            "waiting",
            "finder",  # Just Finder with no specific task
        ]

        count = 0
        for activity in activities:
            if isinstance(activity, dict):
                desc = (activity.get("description") or "").lower()
                app = (activity.get("app") or "").lower()
            else:
                desc = str(activity).lower() if activity else ""
                app = ""

            # Skip trivial activities
            is_trivial = any(t in desc for t in trivial_keywords)

            # Check if description is too short (< 15 chars)
            is_too_short = len(desc) < 15

            # Check if app is meaningful
            has_real_app = app and app not in ["unknown", "n/a", "", "none"]

            if not is_trivial and (not is_too_short or has_real_app):
                count += 1

        return count

    def check_status(self) -> dict:
        """
        Check sync status without making changes.

        Returns:
            Dict with status information
        """
        result = self.sync_all(remove_empty=True, dry_run=True)

        return {
            "notes_on_disk": result.notes_on_disk,
            "notes_in_db": result.notes_in_db,
            "needs_indexing": result.notes_indexed,
            "files_missing": result.files_missing,
            "orphaned_records": result.orphaned_db_records,
            "empty_notes": result.empty_notes_found,
            "in_sync": not result.has_changes,
        }


def sync_notes(
    db_path: str | None = None,
    notes_dir: str | None = None,
    remove_empty: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Run complete notes sync.

    Convenience function for external callers.

    Args:
        db_path: Path to database
        notes_dir: Path to notes directory
        remove_empty: Whether to remove empty notes
        dry_run: If True, only report what would be done

    Returns:
        Dict with sync statistics
    """
    service = NotesSyncService(db_path=db_path, notes_dir=notes_dir)
    result = service.sync_all(remove_empty=remove_empty, dry_run=dry_run)

    return {
        "dry_run": dry_run,
        "notes_indexed": result.notes_indexed,
        "files_recovered": result.files_recovered,
        "orphans_cleaned": result.orphaned_cleaned,
        "empty_removed": result.empty_notes_removed,
        "has_changes": result.has_changes,
        "errors": result.errors,
    }


def cleanup_orphaned_screenshots(
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Clean up orphaned screenshot directories.

    Finds screenshot directories for hours that were already processed
    (marked as success in jobs table) but have no note. These are
    screenshots from skipped/idle hours that weren't deleted due to
    a bug in earlier versions.

    Args:
        db_path: Path to database
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup statistics
    """
    import shutil

    from src.core.paths import CACHE_DIR, DB_PATH

    db_path = Path(db_path) if db_path else DB_PATH
    screenshots_dir = CACHE_DIR / "screenshots"

    if not screenshots_dir.exists():
        return {"orphaned_dirs": 0, "files_deleted": 0, "bytes_freed": 0}

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Get all hours that were processed (success status)
        cursor.execute(
            """
            SELECT window_start_ts, result_json
            FROM jobs
            WHERE job_type = 'hourly' AND status = 'success'
            """
        )
        processed_hours = {}
        for row in cursor.fetchall():
            hour_ts = row["window_start_ts"]
            result = json.loads(row["result_json"]) if row["result_json"] else {}
            processed_hours[hour_ts] = result

        # Get all hours that have notes
        cursor.execute(
            """
            SELECT start_ts FROM notes WHERE note_type = 'hour'
            """
        )
        hours_with_notes = {row["start_ts"] for row in cursor.fetchall()}

    finally:
        conn.close()

    # Find orphaned screenshot directories
    orphaned_dirs = []
    total_files = 0
    total_bytes = 0

    for date_dir in screenshots_dir.iterdir():
        if not date_dir.is_dir() or len(date_dir.name) != 8:
            continue

        for hour_dir in date_dir.iterdir():
            if not hour_dir.is_dir() or len(hour_dir.name) != 2:
                continue

            # Build the hour timestamp from directory names
            try:
                date_str = date_dir.name  # YYYYMMDD
                hour_str = hour_dir.name  # HH
                hour_ts = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T{hour_str}:00:00"

                # Check if hour was processed
                if hour_ts in processed_hours:
                    # Check if hour has a note
                    if hour_ts not in hours_with_notes:
                        # This is an orphaned screenshot directory
                        # (processed, no note, but screenshots still exist)
                        file_count = sum(1 for f in hour_dir.rglob("*") if f.is_file())
                        byte_count = sum(
                            f.stat().st_size for f in hour_dir.rglob("*") if f.is_file()
                        )

                        orphaned_dirs.append(
                            {
                                "hour": hour_ts,
                                "path": str(hour_dir),
                                "files": file_count,
                                "bytes": byte_count,
                            }
                        )
                        total_files += file_count
                        total_bytes += byte_count

            except (ValueError, IndexError):
                continue

    # Delete orphaned directories
    deleted_dirs = 0
    if not dry_run:
        for orphan in orphaned_dirs:
            try:
                shutil.rmtree(orphan["path"])
                deleted_dirs += 1
                logger.info(f"Deleted orphaned screenshot dir: {orphan['path']}")
            except Exception as e:
                logger.warning(f"Failed to delete {orphan['path']}: {e}")

    return {
        "orphaned_dirs": len(orphaned_dirs),
        "deleted_dirs": deleted_dirs if not dry_run else 0,
        "files_deleted": total_files if not dry_run else 0,
        "bytes_freed": total_bytes if not dry_run else 0,
        "dry_run": dry_run,
        "details": orphaned_dirs if dry_run else [],
    }


if __name__ == "__main__":
    import fire

    logging.basicConfig(level=logging.INFO)

    def status(db_path: str | None = None, notes_dir: str | None = None):
        """
        Check sync status without making changes.

        Args:
            db_path: Path to database
            notes_dir: Path to notes directory
        """
        service = NotesSyncService(db_path=db_path, notes_dir=notes_dir)
        return service.check_status()

    def sync(
        db_path: str | None = None,
        notes_dir: str | None = None,
        remove_empty: bool = True,
        dry_run: bool = False,
    ):
        """
        Run complete notes sync.

        Args:
            db_path: Path to database
            notes_dir: Path to notes directory
            remove_empty: Whether to remove empty notes
            dry_run: If True, only report what would be done
        """
        return sync_notes(
            db_path=db_path,
            notes_dir=notes_dir,
            remove_empty=remove_empty,
            dry_run=dry_run,
        )

    def find_empty(db_path: str | None = None, notes_dir: str | None = None):
        """
        Find empty notes without removing them.

        Args:
            db_path: Path to database
            notes_dir: Path to notes directory
        """
        service = NotesSyncService(db_path=db_path, notes_dir=notes_dir)
        result = SyncResult()
        service._cleanup_empty_notes(result, dry_run=True)

        return {
            "empty_notes_found": result.empty_notes_found,
            "notes": [
                {"start_ts": n["start_ts"], "file_path": n["file_path"]}
                for n in result.removed_empty
            ],
        }

    def cleanup_screenshots(db_path: str | None = None, dry_run: bool = True):
        """
        Clean up orphaned screenshot directories.

        Args:
            db_path: Path to database
            dry_run: If True, only report what would be deleted (default: True for safety)
        """
        return cleanup_orphaned_screenshots(db_path=db_path, dry_run=dry_run)

    fire.Fire(
        {
            "status": status,
            "sync": sync,
            "find_empty": find_empty,
            "cleanup_screenshots": cleanup_screenshots,
        }
    )
