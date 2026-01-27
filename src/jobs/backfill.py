"""
Backfill Detection and Execution for Trace

Detects missing hourly notes where activity data exists and
triggers automatic summarization to fill gaps.

This runs on startup and every hour to ensure no activity
goes unsummarized. It scans ALL historical hours with activity,
not just a recent window.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import DB_PATH, get_all_screenshot_hours
from src.db.migrations import get_connection
from src.memory.memory import is_memory_empty, populate_memory_from_notes
from src.platform.notifications import send_backfill_notification, send_error_notification
from src.summarize.summarizer import HourlySummarizer, SummarizationResult

logger = logging.getLogger(__name__)

# Minimum number of screenshots/events to consider an hour "active"
MIN_ACTIVITY_THRESHOLD = 5

# Maximum hours to backfill in a single run (to avoid overwhelming the API)
MAX_BACKFILL_PER_RUN = 10


@dataclass
class BackfillResult:
    """Result of a backfill operation."""

    hours_checked: int
    hours_missing: int
    hours_backfilled: int
    hours_failed: int
    results: list[SummarizationResult]


class BackfillDetector:
    """
    Detects and fills gaps in hourly notes.

    Scans ALL historical hours for activity data (screenshots, events) that
    doesn't have a corresponding note, and triggers summarization.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the backfill detector.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for summarization
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key
        self._summarizer: HourlySummarizer | None = None

    def _get_summarizer(self) -> HourlySummarizer:
        """Get or create the summarizer (lazy initialization)."""
        if self._summarizer is None:
            self._summarizer = HourlySummarizer(db_path=self.db_path, api_key=self.api_key)
        return self._summarizer

    def find_missing_hours(self) -> list[datetime]:
        """
        Find ALL hours with activity but no notes.

        Scans both the database and screenshot directories for hours that have
        activity but no corresponding hourly note. This ensures we catch:
        1. Hours with screenshots/events in the database
        2. Hours with screenshot directories on disk (e.g., after restart before DB sync)

        Returns:
            List of hour start times that need backfilling (oldest first)
        """
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        missing = []

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Find all distinct hours with screenshots in database
            cursor.execute(
                """
                SELECT DISTINCT strftime('%Y-%m-%dT%H:00:00', ts) as hour_start
                FROM screenshots
                WHERE ts < ?
                ORDER BY hour_start
                """,
                (current_hour.isoformat(),),
            )
            hours_with_screenshots = {row[0] for row in cursor.fetchall()}

            # Find all distinct hours with events in database
            cursor.execute(
                """
                SELECT DISTINCT strftime('%Y-%m-%dT%H:00:00', start_ts) as hour_start
                FROM events
                WHERE start_ts < ?
                ORDER BY hour_start
                """,
                (current_hour.isoformat(),),
            )
            hours_with_events = {row[0] for row in cursor.fetchall()}

            # Also check for screenshot directories on disk (hourly structure)
            # This catches cases where screenshots exist but may not be in DB yet
            hours_with_dirs = set()
            try:
                for hour_dt in get_all_screenshot_hours():
                    if hour_dt < current_hour:
                        hours_with_dirs.add(hour_dt.isoformat())
            except Exception as e:
                logger.warning(f"Error scanning screenshot directories: {e}")

            # Combine all sources of activity hours
            all_activity_hours = hours_with_screenshots | hours_with_events | hours_with_dirs

            logger.debug(
                f"Found {len(all_activity_hours)} hours with activity "
                f"(db_screenshots: {len(hours_with_screenshots)}, "
                f"db_events: {len(hours_with_events)}, "
                f"disk_dirs: {len(hours_with_dirs)})"
            )

            # Check each hour for missing notes
            for hour_str in sorted(all_activity_hours):
                try:
                    hour_start = datetime.fromisoformat(hour_str)
                except ValueError:
                    continue

                # Skip current hour (still accumulating)
                if hour_start >= current_hour:
                    continue

                # Check if note exists
                if self._note_exists(cursor, hour_start):
                    continue

                # Check if there's enough activity
                hour_end = hour_start + timedelta(hours=1)
                if self._has_activity(cursor, hour_start, hour_end):
                    missing.append(hour_start)
                    logger.debug(f"Found missing note for hour: {hour_start.isoformat()}")

        finally:
            conn.close()

        if missing:
            logger.info(f"Found {len(missing)} hours with activity but no notes")

        return missing

    def _note_exists(self, cursor, hour_start: datetime) -> bool:
        """Check if a note exists for the given hour."""
        cursor.execute(
            """
            SELECT 1 FROM notes
            WHERE note_type = 'hour'
            AND start_ts = ?
            LIMIT 1
            """,
            (hour_start.isoformat(),),
        )
        return cursor.fetchone() is not None

    def _has_activity(self, cursor, hour_start: datetime, hour_end: datetime) -> bool:
        """Check if there's meaningful activity in the given hour."""
        # Check for screenshots
        cursor.execute(
            """
            SELECT COUNT(*) FROM screenshots
            WHERE ts >= ? AND ts < ?
            """,
            (hour_start.isoformat(), hour_end.isoformat()),
        )
        screenshot_count = cursor.fetchone()[0]

        # Check for events
        cursor.execute(
            """
            SELECT COUNT(*) FROM events
            WHERE start_ts >= ? AND start_ts < ?
            """,
            (hour_start.isoformat(), hour_end.isoformat()),
        )
        event_count = cursor.fetchone()[0]

        total_activity = screenshot_count + event_count
        has_activity = total_activity >= MIN_ACTIVITY_THRESHOLD

        if has_activity:
            logger.debug(
                f"Hour {hour_start.isoformat()}: {screenshot_count} screenshots, "
                f"{event_count} events"
            )

        return has_activity

    def trigger_backfill(
        self,
        hours: list[datetime] | None = None,
        notify: bool = True,
        max_hours: int = MAX_BACKFILL_PER_RUN,
    ) -> BackfillResult:
        """
        Generate notes for missing hours.

        Args:
            hours: List of hours to backfill (uses find_missing_hours if not provided)
            notify: Whether to send macOS notifications
            max_hours: Maximum hours to backfill in this run

        Returns:
            BackfillResult with statistics
        """
        if hours is None:
            hours = self.find_missing_hours()

        if not hours:
            logger.info("No hours to backfill")
            return BackfillResult(
                hours_checked=0,
                hours_missing=0,
                hours_backfilled=0,
                hours_failed=0,
                results=[],
            )

        # Limit the number of hours to backfill in one run
        hours_to_process = sorted(hours)[:max_hours]
        remaining = len(hours) - len(hours_to_process)

        if remaining > 0:
            logger.info(
                f"Backfilling {len(hours_to_process)} hours "
                f"({remaining} more will be processed in next run)"
            )

        if notify:
            send_backfill_notification(len(hours_to_process), "started")

        logger.info(f"Starting backfill for {len(hours_to_process)} hours")

        summarizer = self._get_summarizer()
        results = []
        successful = 0
        failed = 0

        # Process in chronological order
        for hour in hours_to_process:
            logger.info(f"Backfilling note for {hour.isoformat()}")

            try:
                result = summarizer.summarize_hour(hour, force=False)
                results.append(result)

                if result.success:
                    successful += 1
                    logger.info(f"Successfully backfilled {hour.isoformat()}")
                else:
                    failed += 1
                    logger.error(f"Failed to backfill {hour.isoformat()}: {result.error}")
                    if notify:
                        send_error_notification(
                            f"Backfill failed for {hour.strftime('%H:%M')}",
                            result.error,
                        )

            except Exception as e:
                failed += 1
                logger.error(f"Exception during backfill for {hour.isoformat()}: {e}")
                if notify:
                    send_error_notification(
                        f"Backfill error for {hour.strftime('%H:%M')}",
                        str(e),
                    )

        if notify and successful > 0:
            send_backfill_notification(successful, "completed")

        logger.info(f"Backfill complete: {successful} successful, {failed} failed")

        # Populate memory from notes if it's empty
        if successful > 0 and is_memory_empty():
            logger.info("Memory is empty, populating from notes...")
            try:
                memory_result = populate_memory_from_notes(api_key=self.api_key)
                if memory_result.get("success"):
                    logger.info(
                        f"Memory populated: {memory_result.get('items_added', 0)} items added"
                    )
                else:
                    logger.warning(f"Memory population failed: {memory_result.get('error')}")
            except Exception as e:
                logger.warning(f"Failed to populate memory: {e}")

        return BackfillResult(
            hours_checked=len(hours),
            hours_missing=len(hours),
            hours_backfilled=successful,
            hours_failed=failed,
            results=results,
        )

    def check_and_backfill(self, notify: bool = True) -> BackfillResult:
        """
        Convenience method to find and backfill missing hours.

        Args:
            notify: Whether to send macOS notifications

        Returns:
            BackfillResult with statistics
        """
        missing = self.find_missing_hours()
        if missing:
            return self.trigger_backfill(missing, notify=notify)
        return BackfillResult(
            hours_checked=0,
            hours_missing=0,
            hours_backfilled=0,
            hours_failed=0,
            results=[],
        )


def cleanup_empty_notes(db_path: Path | str | None = None, dry_run: bool = True) -> dict:
    """
    Clean up empty notes that have "No summary available" or similar placeholder content.

    These notes were created before the empty note skip check was added.

    Args:
        db_path: Path to SQLite database
        dry_run: If True, only report what would be deleted without actually deleting

    Returns:
        Dictionary with cleanup statistics
    """
    import json

    db_path = Path(db_path) if db_path else DB_PATH

    # Indicators of empty/placeholder notes
    empty_indicators = [
        "no summary available",
        "no activity detected",
        "no meaningful activity",
    ]

    conn = get_connection(db_path)
    empty_notes = []

    try:
        cursor = conn.cursor()

        # Find all notes
        cursor.execute(
            """
            SELECT note_id, note_type, start_ts, file_path, json_payload
            FROM notes
            ORDER BY start_ts DESC
            """
        )

        for row in cursor.fetchall():
            note_id = row["note_id"]
            file_path = row["file_path"]
            json_payload = row["json_payload"]

            is_empty = False

            # Check JSON payload for empty summary
            if json_payload:
                try:
                    payload = json.loads(json_payload)
                    summary = payload.get("summary", "").lower().strip()
                    categories = payload.get("categories", [])
                    entities = payload.get("entities", [])
                    activities = payload.get("activities", [])

                    # Note is empty if:
                    # 1. Summary contains empty indicator AND
                    # 2. Has no categories, entities, or activities
                    if any(indicator in summary for indicator in empty_indicators):
                        if not categories and not entities and not activities:
                            is_empty = True
                except json.JSONDecodeError:
                    pass

            # Also check file content if it exists
            if file_path and Path(file_path).exists():
                try:
                    content = Path(file_path).read_text(encoding="utf-8").lower()
                    if any(indicator in content for indicator in empty_indicators):
                        # Additional check: no meaningful content after summary section
                        if "## activities" not in content or "- **" not in content:
                            is_empty = True
                except Exception:
                    pass

            if is_empty:
                empty_notes.append(
                    {
                        "note_id": note_id,
                        "start_ts": row["start_ts"],
                        "file_path": file_path,
                        "note_type": row["note_type"],
                    }
                )

        if not dry_run and empty_notes:
            # Delete empty notes
            for note in empty_notes:
                # Delete from database
                cursor.execute("DELETE FROM notes WHERE note_id = ?", (note["note_id"],))
                cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note["note_id"],))
                cursor.execute(
                    "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
                    (note["note_id"],),
                )

                # Delete file if it exists
                if note["file_path"] and Path(note["file_path"]).exists():
                    try:
                        Path(note["file_path"]).unlink()
                        logger.info(f"Deleted empty note file: {note['file_path']}")
                    except Exception as e:
                        logger.warning(f"Failed to delete file {note['file_path']}: {e}")

            conn.commit()
            logger.info(f"Cleaned up {len(empty_notes)} empty notes")

    finally:
        conn.close()

    return {
        "dry_run": dry_run,
        "empty_notes_found": len(empty_notes),
        "notes": [{"start_ts": n["start_ts"], "file_path": n["file_path"]} for n in empty_notes],
    }


if __name__ == "__main__":
    import fire

    def check(db_path: str | None = None):
        """Check for ALL missing hours without backfilling."""
        detector = BackfillDetector(db_path=db_path)
        missing = detector.find_missing_hours()

        return {
            "missing_hours": len(missing),
            "hours": [h.isoformat() for h in missing],
        }

    def backfill(
        db_path: str | None = None,
        notify: bool = False,
        max_hours: int = MAX_BACKFILL_PER_RUN,
    ):
        """Find and backfill missing hours."""
        from src.core.config import get_api_key

        api_key = get_api_key()
        detector = BackfillDetector(db_path=db_path, api_key=api_key)
        result = detector.trigger_backfill(notify=notify, max_hours=max_hours)

        return {
            "hours_checked": result.hours_checked,
            "hours_missing": result.hours_missing,
            "hours_backfilled": result.hours_backfilled,
            "hours_failed": result.hours_failed,
        }

    def cleanup(db_path: str | None = None, dry_run: bool = True):
        """
        Clean up empty notes from the database.

        Args:
            db_path: Path to database
            dry_run: If True, only report what would be deleted
        """
        return cleanup_empty_notes(db_path=db_path, dry_run=dry_run)

    fire.Fire({"check": check, "backfill": backfill, "cleanup": cleanup})
