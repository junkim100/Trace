"""
Raw Artifact Deletion for Trace Daily Revision

Deletes screenshots, text buffers, and OCR cache after successful
integrity checkpoint. Only proceeds if integrity check passes.

P6-09: Raw artifact deletion
"""

import logging
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import (
    CACHE_DIR,
    DB_PATH,
    cleanup_empty_cache_directories,
    get_daily_cache_dirs,
)
from src.db.migrations import get_connection
from src.revise.integrity import IntegrityChecker

logger = logging.getLogger(__name__)


@dataclass
class DeletionStats:
    """Statistics for deleted artifacts."""

    artifact_type: str
    file_count: int
    bytes_deleted: int


@dataclass
class CleanupResult:
    """Result of cleanup operation."""

    day: str
    success: bool
    integrity_passed: bool
    deletion_stats: list[DeletionStats]
    total_files_deleted: int
    total_bytes_freed: int
    error: str | None = None


class ArtifactCleaner:
    """
    Cleans up raw artifacts after successful daily revision.

    Handles:
    - Integrity check before deletion
    - Screenshot deletion
    - Text buffer deletion
    - OCR cache deletion
    - Database record cleanup
    - Deletion logging for audit
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the cleaner.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.integrity_checker = IntegrityChecker(db_path=self.db_path)

    def cleanup_day(
        self,
        day: datetime,
        force: bool = False,
        dry_run: bool = False,
    ) -> CleanupResult:
        """
        Clean up raw artifacts for a day.

        Args:
            day: The day to clean up
            force: Skip integrity check (dangerous!)
            dry_run: Count files but don't delete

        Returns:
            CleanupResult with deletion statistics
        """
        # Run integrity check unless forced
        if not force:
            integrity_result = self.integrity_checker.check_integrity(day, require_embeddings=False)

            if not integrity_result.passed:
                logger.warning(
                    f"Integrity check failed for {day.strftime('%Y-%m-%d')}: "
                    f"{integrity_result.error_count} errors"
                )
                return CleanupResult(
                    day=day.strftime("%Y-%m-%d"),
                    success=False,
                    integrity_passed=False,
                    deletion_stats=[],
                    total_files_deleted=0,
                    total_bytes_freed=0,
                    error=f"Integrity check failed with {integrity_result.error_count} errors",
                )
        else:
            logger.warning(
                f"Force cleanup enabled - skipping integrity check for {day.strftime('%Y-%m-%d')}"
            )

        deletion_stats = []
        total_files = 0
        total_bytes = 0

        try:
            # Delete screenshots
            screenshot_stats = self._delete_cache_directory(day, "screenshots", dry_run)
            if screenshot_stats:
                deletion_stats.append(screenshot_stats)
                total_files += screenshot_stats.file_count
                total_bytes += screenshot_stats.bytes_deleted

            # Delete text buffers
            text_stats = self._delete_cache_directory(day, "text_buffers", dry_run)
            if text_stats:
                deletion_stats.append(text_stats)
                total_files += text_stats.file_count
                total_bytes += text_stats.bytes_deleted

            # Delete OCR cache
            ocr_stats = self._delete_cache_directory(day, "ocr", dry_run)
            if ocr_stats:
                deletion_stats.append(ocr_stats)
                total_files += ocr_stats.file_count
                total_bytes += ocr_stats.bytes_deleted

            # Clean up database records
            if not dry_run:
                self._cleanup_database_records(day)

            # Clean up any empty directories in the cache
            if not dry_run:
                cleanup_empty_cache_directories(CACHE_DIR)

            # Log deletion
            if not dry_run:
                self._log_deletion(day, deletion_stats, integrity_passed=not force)

            logger.info(
                f"Cleanup {'simulated' if dry_run else 'completed'} for {day.strftime('%Y-%m-%d')}: "
                f"{total_files} files, {total_bytes / (1024 * 1024):.1f} MB"
            )

            return CleanupResult(
                day=day.strftime("%Y-%m-%d"),
                success=True,
                integrity_passed=not force,
                deletion_stats=deletion_stats,
                total_files_deleted=total_files,
                total_bytes_freed=total_bytes,
            )

        except Exception as e:
            logger.error(f"Cleanup failed for {day.strftime('%Y-%m-%d')}: {e}")
            return CleanupResult(
                day=day.strftime("%Y-%m-%d"),
                success=False,
                integrity_passed=not force,
                deletion_stats=deletion_stats,
                total_files_deleted=total_files,
                total_bytes_freed=total_bytes,
                error=str(e),
            )

    def _delete_cache_directory(
        self,
        day: datetime,
        cache_type: str,
        dry_run: bool,
    ) -> DeletionStats | None:
        """
        Delete a cache directory for a specific day.

        Args:
            day: The day
            cache_type: Type of cache (screenshots, text_buffers, ocr)
            dry_run: If True, count but don't delete

        Returns:
            DeletionStats or None if directory doesn't exist
        """
        cache_dirs = get_daily_cache_dirs(day)
        cache_dir = cache_dirs.get(cache_type)

        if cache_dir is None or not cache_dir.exists():
            logger.debug(f"Cache directory not found: {cache_dir}")
            return None

        # Count files and bytes
        file_count = 0
        bytes_total = 0

        for file_path in cache_dir.rglob("*"):
            if file_path.is_file():
                file_count += 1
                bytes_total += file_path.stat().st_size

        if file_count == 0:
            logger.debug(f"Cache directory empty: {cache_dir}")
            return None

        # Delete if not dry run
        if not dry_run:
            shutil.rmtree(cache_dir)
            logger.info(f"Deleted {cache_type} cache: {cache_dir} ({file_count} files)")

        return DeletionStats(
            artifact_type=cache_type,
            file_count=file_count,
            bytes_deleted=bytes_total,
        )

    def _cleanup_database_records(self, day: datetime) -> None:
        """
        Clean up database records for deleted artifacts.

        Args:
            day: The day to clean up
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Delete screenshot records
            cursor.execute(
                """
                DELETE FROM screenshots
                WHERE ts >= ? AND ts <= ?
                """,
                (day_start.isoformat(), day_end.isoformat()),
            )
            screenshots_deleted = cursor.rowcount
            logger.debug(f"Deleted {screenshots_deleted} screenshot records")

            # Delete text buffer records
            cursor.execute(
                """
                DELETE FROM text_buffers
                WHERE ts >= ? AND ts <= ?
                """,
                (day_start.isoformat(), day_end.isoformat()),
            )
            text_buffers_deleted = cursor.rowcount
            logger.debug(f"Deleted {text_buffers_deleted} text buffer records")

            # Delete event records (optional - events might be useful for history)
            # For now, keep events as they contain metadata without raw data
            # cursor.execute("""
            #     DELETE FROM events
            #     WHERE start_ts >= ? AND end_ts <= ?
            # """, (day_start.isoformat(), day_end.isoformat()))

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to cleanup database records: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _log_deletion(
        self,
        day: datetime,
        deletion_stats: list[DeletionStats],
        integrity_passed: bool,
    ) -> None:
        """
        Log deletion for audit trail.

        Args:
            day: The day deleted
            deletion_stats: Statistics of what was deleted
            integrity_passed: Whether integrity check passed
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            for stats in deletion_stats:
                deletion_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO deletion_log
                    (deletion_id, deletion_date, artifact_type, artifact_count, integrity_passed, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deletion_id,
                        day.strftime("%Y%m%d"),
                        stats.artifact_type,
                        stats.file_count,
                        1 if integrity_passed else 0,
                        datetime.now().isoformat(),
                    ),
                )

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to log deletion: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_deletion_history(
        self,
        days: int = 30,
    ) -> list[dict]:
        """
        Get deletion history for audit.

        Args:
            days: Number of days to look back

        Returns:
            List of deletion records
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT deletion_date, artifact_type, artifact_count, integrity_passed, created_ts
                FROM deletion_log
                ORDER BY created_ts DESC
                LIMIT ?
                """,
                (days * 3,),  # ~3 artifact types per day
            )

            history = []
            for row in cursor.fetchall():
                history.append(
                    {
                        "date": row["deletion_date"],
                        "type": row["artifact_type"],
                        "count": row["artifact_count"],
                        "integrity_passed": bool(row["integrity_passed"]),
                        "deleted_at": row["created_ts"],
                    }
                )

            return history

        finally:
            conn.close()

    def get_cache_size(self, day: datetime) -> dict:
        """
        Get the total size of cache for a day.

        Args:
            day: The day to check

        Returns:
            Dictionary with sizes by cache type
        """
        cache_dirs = get_daily_cache_dirs(day)
        sizes = {}

        for cache_type, cache_dir in cache_dirs.items():
            if cache_dir.exists():
                total_bytes = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
                file_count = sum(1 for f in cache_dir.rglob("*") if f.is_file())
                sizes[cache_type] = {
                    "bytes": total_bytes,
                    "mb": total_bytes / (1024 * 1024),
                    "files": file_count,
                }
            else:
                sizes[cache_type] = {"bytes": 0, "mb": 0, "files": 0}

        return sizes


if __name__ == "__main__":
    import fire

    def cleanup(
        day: str | None = None,
        force: bool = False,
        dry_run: bool = True,
        db_path: str | None = None,
    ):
        """
        Clean up raw artifacts for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to yesterday)
            force: Skip integrity check (dangerous!)
            dry_run: Count files but don't delete (default: True for safety)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            # Default to yesterday (today's data is still being captured)
            from datetime import timedelta

            target_day = datetime.now() - timedelta(days=1)

        cleaner = ArtifactCleaner(db_path=db_path)
        result = cleaner.cleanup_day(target_day, force=force, dry_run=dry_run)

        output = {
            "day": result.day,
            "success": result.success,
            "dry_run": dry_run,
            "integrity_passed": result.integrity_passed,
            "total_files": result.total_files_deleted,
            "total_mb": result.total_bytes_freed / (1024 * 1024),
        }

        if result.deletion_stats:
            output["by_type"] = {
                stats.artifact_type: {
                    "files": stats.file_count,
                    "mb": stats.bytes_deleted / (1024 * 1024),
                }
                for stats in result.deletion_stats
            }

        if result.error:
            output["error"] = result.error

        return output

    def size(day: str | None = None):
        """
        Get cache size for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        cleaner = ArtifactCleaner()
        sizes = cleaner.get_cache_size(target_day)

        return {
            "day": target_day.strftime("%Y-%m-%d"),
            "cache": sizes,
            "total_mb": sum(s["mb"] for s in sizes.values()),
            "total_files": sum(s["files"] for s in sizes.values()),
        }

    def history(days: int = 30, db_path: str | None = None):
        """
        Get deletion history.

        Args:
            days: Number of days to look back
            db_path: Path to database
        """
        cleaner = ArtifactCleaner(db_path=db_path)
        return cleaner.get_deletion_history(days)

    fire.Fire(
        {
            "cleanup": cleanup,
            "size": size,
            "history": history,
        }
    )
