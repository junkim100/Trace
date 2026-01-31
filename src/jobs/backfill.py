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

from src.core.paths import DB_PATH, get_all_screenshot_hours, get_trace_day
from src.db.migrations import get_connection
from src.memory.memory import is_memory_empty, populate_memory_from_notes
from src.platform.notifications import send_backfill_notification, send_error_notification
from src.summarize.summarizer import HourlySummarizer, SummarizationResult

logger = logging.getLogger(__name__)

# Minimum number of screenshots/events to consider an hour "active"
MIN_ACTIVITY_THRESHOLD = 5

# Minimum screenshots (with files) required for backfill
# Events alone are not sufficient - the summarizer needs images to analyze
MIN_SCREENSHOTS_FOR_BACKFILL = 3

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

    def find_missing_hours(self, ignore_job_status: bool = False) -> list[datetime]:
        """
        Find ALL hours with activity but no notes.

        Scans both the database and screenshot directories for hours that have
        activity but no corresponding hourly note. This ensures we catch:
        1. Hours with screenshots/events in the database
        2. Hours with screenshot directories on disk (e.g., after restart before DB sync)

        Also checks the jobs table to skip hours that were already processed
        (even if no note was created because the hour was skipped).

        Args:
            ignore_job_status: If True, don't skip hours that were marked as processed.
                              Used for force reprocessing.

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

            # Find hours that have been successfully processed or intentionally skipped
            # - "success": Note was created
            # - "skipped": Hour was intentionally skipped (truly idle)
            # - "failed": Should NOT be in this set - we want to retry failed hours
            hours_already_processed: set[str] = set()
            if not ignore_job_status:
                cursor.execute(
                    """
                    SELECT window_start_ts
                    FROM jobs
                    WHERE job_type = 'hourly'
                    AND status IN ('success', 'skipped')
                    """
                )
                hours_already_processed = {row[0] for row in cursor.fetchall()}

            # Combine all sources of activity hours
            all_activity_hours = hours_with_screenshots | hours_with_events | hours_with_dirs

            logger.debug(
                f"Found {len(all_activity_hours)} hours with activity "
                f"(db_screenshots: {len(hours_with_screenshots)}, "
                f"db_events: {len(hours_with_events)}, "
                f"disk_dirs: {len(hours_with_dirs)}), "
                f"{len(hours_already_processed)} already processed"
                + (", ignoring job status" if ignore_job_status else "")
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

                # Check if note exists - this is the definitive check
                # In force mode, we still skip hours that already have notes
                if self._note_exists(cursor, hour_start):
                    continue

                # If job was marked success but no note exists, trust the job status.
                # The hour was intentionally skipped (idle/no meaningful content) and
                # screenshots should have been deleted at that time.
                # Skip this check in force mode (ignore_job_status=True)
                if not ignore_job_status:
                    was_processed = hour_start.isoformat() in hours_already_processed
                    if was_processed:
                        # Trust the job status - hour was intentionally skipped
                        # Note: Screenshots may still exist on disk if they were created
                        # before the fix to delete screenshots for skipped hours.
                        # But we should NOT reprocess just because screenshots exist.
                        logger.debug(
                            f"Hour {hour_start.isoformat()} was already processed "
                            "(no note = intentionally skipped), skipping"
                        )
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
        """
        Check if a note exists for the given hour.

        CRITICAL: Validates BOTH database record AND file existence.
        If a DB record exists but the file is missing, the orphaned
        DB record is deleted and False is returned.
        """
        cursor.execute(
            """
            SELECT note_id, file_path FROM notes
            WHERE note_type = 'hour'
            AND start_ts = ?
            LIMIT 1
            """,
            (hour_start.isoformat(),),
        )
        row = cursor.fetchone()

        if row is None:
            return False

        # CRITICAL: Verify the file actually exists on disk
        file_path = row["file_path"]
        if file_path and Path(file_path).exists():
            return True

        # DB record exists but file is missing - this is an orphaned record
        # Delete it so the hour can be reprocessed
        note_id = row["note_id"]
        logger.warning(
            f"Found orphaned DB record for {hour_start.isoformat()}: "
            f"note_id={note_id}, file_path={file_path} does not exist. "
            "Cleaning up orphaned record."
        )

        # Clean up the orphaned record
        cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
        cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note_id,))
        cursor.execute(
            "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
            (note_id,),
        )
        # Also clean up the job record so it can be reprocessed
        cursor.execute(
            "DELETE FROM jobs WHERE job_type = 'hourly' AND window_start_ts = ?",
            (hour_start.isoformat(),),
        )
        cursor.connection.commit()

        logger.info(f"Cleaned up orphaned record for {hour_start.isoformat()}")
        return False

    def _has_activity(self, cursor, hour_start: datetime, hour_end: datetime) -> bool:
        """
        Check if there's meaningful activity in the given hour.

        Checks both:
        1. Screenshots in the database (with existing files)
        2. Screenshot files on disk (for hours where DB sync may have failed)

        Requires at least MIN_SCREENSHOTS_FOR_BACKFILL screenshots with files,
        since the summarizer needs images to analyze.
        """
        # Get screenshot paths from database and check if files exist
        cursor.execute(
            """
            SELECT path FROM screenshots
            WHERE ts >= ? AND ts < ?
            """,
            (hour_start.isoformat(), hour_end.isoformat()),
        )
        screenshot_count = 0
        for row in cursor.fetchall():
            path = row[0]
            if path and Path(path).exists():
                screenshot_count += 1

        # If no screenshots in DB, check the filesystem directly
        # This handles cases where capture saved files but DB insert failed
        if screenshot_count == 0:
            screenshot_count = self._count_screenshots_on_disk(hour_start)

        # Must have at least some screenshots to create a meaningful note
        if screenshot_count < MIN_SCREENSHOTS_FOR_BACKFILL:
            return False

        # Check for events (these don't have files to verify)
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

    def _count_screenshots_on_disk(self, hour_start: datetime) -> int:
        """
        Count screenshot files on disk for a given hour.

        Used as fallback when screenshots aren't in the database.
        """
        from src.core.paths import CACHE_DIR

        date_str = hour_start.strftime("%Y%m%d")
        hour_str = hour_start.strftime("%H")

        hour_dir = CACHE_DIR / "screenshots" / date_str / hour_str
        if not hour_dir.exists():
            return 0

        count = 0
        for f in hour_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                count += 1

        if count > 0:
            logger.debug(f"Found {count} screenshots on disk for {hour_start.isoformat()}")

        return count

    def _register_orphaned_screenshots(self, hour_start: datetime) -> int:
        """
        Register screenshot files from disk that aren't in the database.

        This handles cases where screenshots were captured but not registered
        in the database (e.g., database was reset/recreated).

        Args:
            hour_start: Start of the hour to scan

        Returns:
            Number of screenshots registered
        """
        import uuid

        from src.core.paths import CACHE_DIR

        date_str = hour_start.strftime("%Y%m%d")
        hour_str = hour_start.strftime("%H")

        hour_dir = CACHE_DIR / "screenshots" / date_str / hour_str
        if not hour_dir.exists():
            return 0

        # Get existing screenshot paths from database
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path FROM screenshots
                WHERE ts >= ? AND ts < ?
                """,
                (
                    hour_start.isoformat(),
                    (hour_start + timedelta(hours=1)).isoformat(),
                ),
            )
            existing_paths = {row[0] for row in cursor.fetchall()}

            registered = 0
            for f in sorted(hour_dir.iterdir()):
                if not f.is_file() or f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue

                # Skip if already in database
                if str(f) in existing_paths:
                    continue

                # Parse filename: 141537694_m2_1e6fc8ca.jpg
                # Format: HHMMSSMMM_mN_fingerprint.ext
                try:
                    parts = f.stem.split("_")
                    if len(parts) < 3:
                        continue

                    time_part = parts[0]  # e.g., "141537694"
                    monitor_part = parts[1]  # e.g., "m2"
                    fingerprint = parts[2]  # e.g., "1e6fc8ca"

                    # Parse time: HHMMSSMMM -> HH:MM:SS.MMM
                    if len(time_part) >= 9:
                        hh = int(time_part[0:2])
                        mm = int(time_part[2:4])
                        ss = int(time_part[4:6])
                        ms = int(time_part[6:9])

                        ts = hour_start.replace(
                            hour=hh, minute=mm, second=ss, microsecond=ms * 1000
                        )
                    else:
                        # Fallback: use file modification time
                        ts = datetime.fromtimestamp(f.stat().st_mtime)

                    # Parse monitor ID: "m2" -> 2
                    monitor_id = int(monitor_part[1:]) if monitor_part.startswith("m") else 1

                    # Insert into database
                    screenshot_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO screenshots
                        (screenshot_id, ts, monitor_id, path, fingerprint, diff_score, created_ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            screenshot_id,
                            ts.isoformat(),
                            monitor_id,
                            str(f),
                            fingerprint,
                            0.5,  # Default diff score
                            datetime.now().isoformat(),
                        ),
                    )
                    registered += 1

                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse screenshot filename {f.name}: {e}")
                    continue

            conn.commit()

            if registered > 0:
                logger.info(
                    f"Registered {registered} orphaned screenshots for {hour_start.isoformat()}"
                )

            return registered

        except Exception as e:
            logger.error(f"Error registering orphaned screenshots: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def _reindex_orphaned_notes(self) -> int:
        """
        Reindex note files from disk that aren't in the database.

        This handles cases where notes were manually added to the notes directory
        or the database was reset/recreated.

        Returns:
            Number of notes reindexed
        """
        try:
            from src.jobs.note_reindex import NoteReindexer

            reindexer = NoteReindexer()
            note_files = reindexer.find_note_files()

            conn = get_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM notes")
            db_count = cursor.fetchone()["count"]
            conn.close()

            if len(note_files) > db_count:
                logger.info(
                    f"Detected orphaned notes: {len(note_files)} on disk, {db_count} in database. "
                    "Running reindex..."
                )
                result = reindexer.reindex_all()
                logger.info(f"Reindex complete: {result.notes_indexed} notes indexed")

                # Compute embeddings for notes that don't have them
                from src.core.config import get_api_key

                api_key = get_api_key()
                if api_key:
                    self._compute_missing_embeddings(api_key)

                return result.notes_indexed

            return 0

        except Exception as e:
            logger.warning(f"Note reindex check failed: {e}")
            return 0

    def _cleanup_orphaned_db_records(self) -> int:
        """
        Remove database records for notes whose files no longer exist.

        This handles cases where note files were manually deleted but
        the database records remain (stale references).

        CRITICAL: Also cleans up corresponding job records so the hour
        can be properly reprocessed by backfill.

        Returns:
            Number of orphaned records cleaned up
        """
        conn = get_connection(self.db_path)
        cleaned = 0

        try:
            cursor = conn.cursor()

            # Find notes in DB with their start times (needed to clean up jobs)
            cursor.execute("SELECT note_id, file_path, start_ts FROM notes")
            notes = cursor.fetchall()

            orphaned_notes = []
            for note in notes:
                file_path = note["file_path"]
                if file_path and not Path(file_path).exists():
                    orphaned_notes.append(
                        {
                            "note_id": note["note_id"],
                            "file_path": file_path,
                            "start_ts": note["start_ts"],
                        }
                    )
                    logger.info(f"Found orphaned DB record: {file_path}")

            if orphaned_notes:
                for orphan in orphaned_notes:
                    note_id = orphan["note_id"]
                    start_ts = orphan["start_ts"]

                    # Delete the note and related records
                    cursor.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
                    cursor.execute("DELETE FROM note_entities WHERE note_id = ?", (note_id,))
                    cursor.execute(
                        "DELETE FROM embeddings WHERE source_type = 'note' AND source_id = ?",
                        (note_id,),
                    )

                    # CRITICAL: Also delete the job record so the hour can be reprocessed
                    # Without this, find_missing_hours() would skip this hour because
                    # the job was marked as 'success'
                    cursor.execute(
                        "DELETE FROM jobs WHERE job_type = 'hourly' AND window_start_ts = ?",
                        (start_ts,),
                    )
                    logger.debug(f"Also cleaned up job record for {start_ts}")

                    cleaned += 1

                conn.commit()
                logger.info(
                    f"Cleaned up {cleaned} orphaned database records (and their job records)"
                )

        except Exception as e:
            logger.error(f"Error cleaning orphaned DB records: {e}")
            conn.rollback()
        finally:
            conn.close()

        return cleaned

    def _compute_missing_embeddings(self, api_key: str) -> int:
        """
        Compute embeddings for notes that don't have them.

        Args:
            api_key: OpenAI API key

        Returns:
            Number of embeddings computed
        """
        import json as json_module

        from src.summarize.embeddings import EmbeddingComputer
        from src.summarize.schemas import HourlySummarySchema

        computer = EmbeddingComputer(api_key=api_key)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # Get notes without embeddings
        cursor.execute(
            "SELECT note_id, json_payload, start_ts FROM notes WHERE embedding_id IS NULL"
        )
        notes = cursor.fetchall()
        conn.close()

        if not notes:
            return 0

        logger.info(f"Computing embeddings for {len(notes)} notes...")
        computed = 0

        for note in notes:
            try:
                note_id = note["note_id"]
                payload = json_module.loads(note["json_payload"]) if note["json_payload"] else {}
                start_ts = datetime.fromisoformat(note["start_ts"])

                # Create a minimal summary object
                summary = HourlySummarySchema(
                    summary=payload.get("summary", ""),
                    categories=payload.get("categories", []),
                    activities=[],
                    learning=[],
                    entities=[],
                )

                result = computer.compute_for_note(note_id, summary, start_ts)
                if result.success:
                    computed += 1
            except Exception as e:
                logger.warning(f"Failed to compute embedding for {note_id}: {e}")

        logger.info(f"Computed {computed} embeddings")
        return computed

    def _record_backfill_job(self, hour_start: datetime, result: SummarizationResult) -> None:
        """
        Record a backfill job in the jobs table.

        Job status meanings:
        - "success": Note was created successfully
        - "skipped": Hour was intentionally skipped (no activity, truly idle)
        - "failed": Processing failed or content validation failed

        CRITICAL: If result.success=True but note_id=None and idle_reason contains
        "No meaningful content", this means the LLM returned empty/placeholder content.
        We mark this as "failed" so the hour can be reprocessed with better settings.
        """
        import json
        import uuid

        hour_end = hour_start + timedelta(hours=1)
        job_id = str(uuid.uuid4())

        # Determine the appropriate status
        # Note: DB constraint only allows: 'pending', 'running', 'success', 'failed'
        if result.success and result.note_id:
            # Note was actually created
            status = "success"
        elif result.success and result.skipped_idle:
            # Check if this was a true idle skip or a content validation failure
            idle_reason = result.idle_reason or ""
            if (
                "No meaningful content" in idle_reason
                or "no summary available" in idle_reason.lower()
            ):
                # LLM returned empty content - mark as failed so we retry
                status = "failed"
                logger.info(
                    f"Marking {hour_start.isoformat()} as failed (not success) "
                    "because LLM returned empty content - will retry on next backfill"
                )
            else:
                # True idle detection (user was AFK) - mark as success
                # We use success because we don't want to retry truly idle hours
                status = "success"
        elif result.success:
            # Success but no note and not skipped_idle - treat as success (no activity)
            status = "success"
        else:
            status = "failed"

        result_json = json.dumps(
            {
                "note_id": result.note_id,
                "file_path": str(result.file_path) if result.file_path else None,
                "backfill": True,
                "skipped_idle": result.skipped_idle,
                "idle_reason": result.idle_reason,
            }
        )

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Check if job already exists for this hour
            cursor.execute(
                """
                SELECT job_id FROM jobs
                WHERE job_type = 'hourly'
                AND window_start_ts = ?
                """,
                (hour_start.isoformat(),),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing job
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = ?, result_json = ?, last_error = ?, updated_ts = ?
                    WHERE job_id = ?
                    """,
                    (
                        status,
                        result_json,
                        result.error,
                        datetime.now().isoformat(),
                        existing["job_id"],
                    ),
                )
            else:
                # Create new job record
                cursor.execute(
                    """
                    INSERT INTO jobs
                    (job_id, job_type, window_start_ts, window_end_ts, status, attempts,
                     result_json, last_error, created_ts, updated_ts)
                    VALUES (?, 'hourly', ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        hour_start.isoformat(),
                        hour_end.isoformat(),
                        status,
                        result_json,
                        result.error,
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            conn.commit()
            logger.debug(f"Recorded backfill job for {hour_start.isoformat()}: {status}")
        finally:
            conn.close()

    def _register_all_orphaned_screenshots(self) -> int:
        """
        Pre-scan and register ALL orphaned screenshots across all hours.

        This runs BEFORE find_missing_hours() to ensure screenshots are in the
        database before we check for activity. Without this, hours with
        screenshots on disk but not in DB might be incorrectly skipped.

        Returns:
            Total number of screenshots registered
        """
        from src.core.paths import CACHE_DIR

        total_registered = 0
        screenshots_dir = CACHE_DIR / "screenshots"

        if not screenshots_dir.exists():
            return 0

        try:
            # Iterate through all date directories (YYYYMMDD)
            for date_dir in sorted(screenshots_dir.iterdir()):
                if not date_dir.is_dir() or len(date_dir.name) != 8:
                    continue

                # Iterate through all hour directories (HH)
                for hour_dir in sorted(date_dir.iterdir()):
                    if not hour_dir.is_dir() or len(hour_dir.name) != 2:
                        continue

                    try:
                        # Parse the hour
                        date_str = date_dir.name  # YYYYMMDD
                        hour_str = hour_dir.name  # HH
                        hour_start = datetime.strptime(
                            f"{date_str}T{hour_str}:00:00", "%Y%m%dT%H:%M:%S"
                        )

                        # Register orphaned screenshots for this hour
                        registered = self._register_orphaned_screenshots(hour_start)
                        total_registered += registered

                    except ValueError:
                        continue

            if total_registered > 0:
                logger.info(
                    f"Pre-registered {total_registered} orphaned screenshots across all hours"
                )

        except Exception as e:
            logger.warning(f"Error pre-registering orphaned screenshots: {e}")

        return total_registered

    def trigger_backfill(
        self,
        hours: list[datetime] | None = None,
        notify: bool = True,
        max_hours: int = MAX_BACKFILL_PER_RUN,
        force: bool = False,
    ) -> BackfillResult:
        """
        Generate notes for missing hours.

        Args:
            hours: List of hours to backfill (uses find_missing_hours if not provided)
            notify: Whether to send macOS notifications
            max_hours: Maximum hours to backfill in this run
            force: If True, bypass LLM quality checks and idle detection

        Returns:
            BackfillResult with statistics
        """
        if hours is None:
            # CRITICAL: Register orphaned screenshots BEFORE finding missing hours
            # This ensures screenshots on disk are in the DB before we check activity
            self._register_all_orphaned_screenshots()
            hours = self.find_missing_hours(ignore_job_status=force)

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
                # First, register any orphaned screenshots from disk that aren't in the database
                # This handles cases where screenshots were captured but DB insert failed
                registered = self._register_orphaned_screenshots(hour)
                if registered > 0:
                    logger.info(
                        f"Registered {registered} orphaned screenshots for {hour.isoformat()}"
                    )

                result = summarizer.summarize_hour(hour, force=force)
                results.append(result)

                # Record this hour as processed in the jobs table to prevent re-processing
                self._record_backfill_job(hour, result)

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
                # Record the failed attempt
                self._record_backfill_job(
                    hour,
                    SummarizationResult(success=False, note_id=None, file_path=None, error=str(e)),
                )
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

    def check_and_backfill(self, notify: bool = True, force: bool = False) -> BackfillResult:
        """
        Comprehensive sync and backfill operation.

        This is the main entry point for startup and periodic backfill checks.
        It performs a complete bidirectional sync to ensure:
        1. All screenshots on disk are registered in DB
        2. All notes on disk are indexed in DB
        3. All orphaned DB records (files deleted) are cleaned up
        4. Missing hours with activity are detected and backfilled

        CRITICAL: The order of operations matters:
        1. Register orphaned screenshots (so activity detection works)
        2. Reindex orphaned notes (so we don't re-create existing notes)
        3. Cleanup orphaned DB records (so hours with deleted notes get reprocessed)
        4. Find and backfill missing hours

        Args:
            notify: Whether to send macOS notifications
            force: If True, reprocess all hours with activity, ignoring job status

        Returns:
            BackfillResult with statistics
        """
        logger.info("Starting comprehensive sync and backfill check...")

        # Step 1: Register orphaned screenshots from disk into DB
        # This ensures _has_activity() correctly counts screenshots
        registered_screenshots = self._register_all_orphaned_screenshots()
        if registered_screenshots > 0:
            logger.info(f"Registered {registered_screenshots} orphaned screenshots")

        # Step 2: Reindex notes on disk that aren't in the database
        # This prevents re-creating notes that exist as files
        reindexed = self._reindex_orphaned_notes()
        if reindexed > 0:
            logger.info(f"Reindexed {reindexed} orphaned notes from disk")

        # Step 3: Cleanup DB records for deleted note files
        # This ensures hours with deleted notes get detected as missing
        cleaned = self._cleanup_orphaned_db_records()
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} orphaned DB records")

        # Step 4: Find and backfill missing hours
        if force:
            # Force mode: find ALL hours with activity (ignore job status)
            missing = self.find_missing_hours(ignore_job_status=True)
        else:
            missing = self.find_missing_hours()

        if missing:
            logger.info(f"Found {len(missing)} hours to backfill")
            return self.trigger_backfill(missing, notify=notify, force=force)

        logger.info("Sync complete, no hours to backfill")
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
        "no activity details were captured",
        "no activity details captured",
        "no details were captured",
        "missing note",
        "wasn't enough evidence",
        "isn't enough evidence",
        "no evidence to",
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


@dataclass
class DailyBackfillResult:
    """Result of a daily backfill operation."""

    days_checked: int
    days_missing: int
    days_backfilled: int
    days_failed: int


class DailyBackfillDetector:
    """
    Detects and fills gaps in daily notes.

    Finds days that have hourly notes but no daily note, and triggers
    the daily revision pipeline to create them.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the daily backfill detector.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key for daily revision
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.api_key = api_key

    def find_missing_days(self) -> list[datetime]:
        """
        Find all Trace days with hourly notes but no daily note.

        A Trace day runs from daily_revision_hour to daily_revision_hour the next day.
        For example, if daily_revision_hour=8:
        - "Jan 28 Trace day" = 8am Jan 28 to 8am Jan 29
        - A note with start_ts 7am Jan 29 belongs to Jan 28 Trace day

        Returns:
            List of Trace days that need daily backfilling (oldest first)
        """
        # Get current Trace day (don't backfill current day - still accumulating)
        current_trace_day = get_trace_day(datetime.now())
        missing = []

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Find all hourly notes and their Trace days
            cursor.execute(
                """
                SELECT start_ts
                FROM notes
                WHERE note_type = 'hour'
                ORDER BY start_ts
                """
            )
            trace_days_with_hourly_notes = set()
            for row in cursor.fetchall():
                start_ts = datetime.fromisoformat(row[0])
                trace_day = get_trace_day(start_ts)
                if trace_day < current_trace_day:
                    trace_days_with_hourly_notes.add(trace_day.isoformat())

            # Find all days that have daily notes
            cursor.execute(
                """
                SELECT DISTINCT date(start_ts) as day_date
                FROM notes
                WHERE note_type = 'day'
                """
            )
            days_with_daily_notes = {row[0] for row in cursor.fetchall()}

            # Find days that have been successfully processed (even if no note created)
            cursor.execute(
                """
                SELECT date(window_start_ts) as day_date
                FROM jobs
                WHERE job_type = 'daily'
                AND status = 'success'
                """
            )
            days_already_processed = {row[0] for row in cursor.fetchall()}

            # Find missing days: have hourly notes but no daily note and not processed
            for day_str in sorted(trace_days_with_hourly_notes):
                if day_str in days_with_daily_notes:
                    continue
                if day_str in days_already_processed:
                    # Check if daily note actually exists despite "success" status
                    # (handles the bug where success was returned without creating note)
                    cursor.execute(
                        """
                        SELECT 1 FROM notes
                        WHERE note_type = 'day' AND date(start_ts) = ?
                        LIMIT 1
                        """,
                        (day_str,),
                    )
                    if cursor.fetchone() is not None:
                        continue
                    # Job marked success but no note - needs reprocessing

                try:
                    day = datetime.strptime(day_str, "%Y-%m-%d")
                    missing.append(day)
                    logger.debug(f"Found missing daily note for Trace day: {day_str}")
                except ValueError:
                    continue

        finally:
            conn.close()

        if missing:
            logger.info(f"Found {len(missing)} days with hourly notes but no daily note")

        return missing

    def trigger_daily_backfill(
        self,
        days: list[datetime] | None = None,
        notify: bool = True,
        max_days: int = 5,
    ) -> DailyBackfillResult:
        """
        Generate daily notes for missing days.

        Args:
            days: List of days to backfill (uses find_missing_days if not provided)
            notify: Whether to send macOS notifications
            max_days: Maximum days to backfill in this run

        Returns:
            DailyBackfillResult with statistics
        """
        from src.jobs.daily import DailyJobExecutor

        if days is None:
            days = self.find_missing_days()

        if not days:
            logger.info("No days to backfill")
            return DailyBackfillResult(
                days_checked=0,
                days_missing=0,
                days_backfilled=0,
                days_failed=0,
            )

        # Limit the number of days to backfill in one run
        days_to_process = sorted(days)[:max_days]
        remaining = len(days) - len(days_to_process)

        if remaining > 0:
            logger.info(
                f"Backfilling {len(days_to_process)} days "
                f"({remaining} more will be processed in next run)"
            )

        if notify:
            send_backfill_notification(len(days_to_process), "daily_started")

        logger.info(f"Starting daily backfill for {len(days_to_process)} days")

        executor = DailyJobExecutor(db_path=self.db_path, api_key=self.api_key)
        successful = 0
        failed = 0

        # Process in chronological order
        for day in days_to_process:
            day_str = day.strftime("%Y-%m-%d")
            logger.info(f"Backfilling daily note for {day_str}")

            try:
                job_id = executor.create_pending_job(day)
                result = executor.execute_job(job_id)

                if result.success and result.hourly_notes_count > 0:
                    successful += 1
                    logger.info(f"Successfully backfilled daily note for {day_str}")
                elif result.hourly_notes_count == 0:
                    logger.info(f"No hourly notes for {day_str}, skipping")
                else:
                    failed += 1
                    logger.error(f"Failed to backfill daily note for {day_str}: {result.error}")
                    if notify:
                        send_error_notification(
                            f"Daily backfill failed for {day_str}",
                            result.error,
                        )

            except Exception as e:
                failed += 1
                logger.error(f"Exception during daily backfill for {day_str}: {e}")
                if notify:
                    send_error_notification(
                        f"Daily backfill error for {day_str}",
                        str(e),
                    )

        if notify and successful > 0:
            send_backfill_notification(successful, "daily_completed")

        logger.info(f"Daily backfill complete: {successful} successful, {failed} failed")

        return DailyBackfillResult(
            days_checked=len(days),
            days_missing=len(days),
            days_backfilled=successful,
            days_failed=failed,
        )


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

    def check_daily(db_path: str | None = None):
        """Check for ALL missing daily notes without backfilling."""
        detector = DailyBackfillDetector(db_path=db_path)
        missing = detector.find_missing_days()

        return {
            "missing_days": len(missing),
            "days": [d.strftime("%Y-%m-%d") for d in missing],
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

    def backfill_daily(
        db_path: str | None = None,
        notify: bool = False,
        max_days: int = 5,
    ):
        """Find and backfill missing daily notes."""
        from src.core.config import get_api_key

        api_key = get_api_key()
        detector = DailyBackfillDetector(db_path=db_path, api_key=api_key)
        result = detector.trigger_daily_backfill(notify=notify, max_days=max_days)

        return {
            "days_checked": result.days_checked,
            "days_missing": result.days_missing,
            "days_backfilled": result.days_backfilled,
            "days_failed": result.days_failed,
        }

    fire.Fire(
        {
            "check": check,
            "check_daily": check_daily,
            "backfill": backfill,
            "backfill_daily": backfill_daily,
            "cleanup": cleanup,
        }
    )
