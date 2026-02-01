"""
Trace Day Migration Script

Migrates existing notes from calendar-date-based folders to Trace-day-based folders.

Before this migration:
- Notes were stored in folders based on calendar date (e.g., 3am Jan 26 in 2026/01/26/)

After this migration:
- Notes are stored in folders based on Trace day (e.g., 3am Jan 26 with revision_hour=6
  goes in 2026/01/25/ because it's before the revision hour)

This script:
1. Finds all hourly notes that need to be moved
2. Moves them to the correct Trace day folder
3. Updates the file_path in the database
"""

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.config import get_capture_config
from src.core.paths import NOTES_DIR, get_trace_day
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of the migration."""

    notes_scanned: int = 0
    notes_moved: int = 0
    notes_already_correct: int = 0
    notes_failed: int = 0
    db_updated: int = 0
    db_failed: int = 0
    errors: list[str] = field(default_factory=list)


def parse_hourly_note_filename(filename: str) -> datetime | None:
    """
    Parse an hourly note filename to get the datetime it represents.

    Args:
        filename: Filename like "hour-20260126-03.md"

    Returns:
        datetime or None if parsing fails
    """
    match = re.match(r"hour-(\d{4})(\d{2})(\d{2})-(\d{2})\.md$", filename)
    if not match:
        return None

    year, month, day, hour = map(int, match.groups())
    try:
        return datetime(year, month, day, hour)
    except ValueError:
        return None


def parse_daily_note_filename(filename: str) -> datetime | None:
    """
    Parse a daily note filename to get the date it represents.

    Args:
        filename: Filename like "day-20260126.md"

    Returns:
        datetime (at midnight) or None if parsing fails
    """
    match = re.match(r"day-(\d{4})(\d{2})(\d{2})\.md$", filename)
    if not match:
        return None

    year, month, day = map(int, match.groups())
    try:
        return datetime(year, month, day, 0)
    except ValueError:
        return None


def get_correct_note_path(
    dt: datetime, note_type: str, revision_hour: int, original_filename: str
) -> Path:
    """
    Get the correct path for a note based on Trace day.

    Args:
        dt: The datetime of the note
        note_type: "hour" or "day"
        revision_hour: The daily revision hour setting
        original_filename: The original filename of the note

    Returns:
        Correct path for the note
    """
    if note_type == "hour":
        # For hourly notes: calculate Trace day from the hour's datetime
        trace_day = get_trace_day(dt, daily_revision_hour=revision_hour)

        note_dir = (
            NOTES_DIR / f"{trace_day.year:04d}" / f"{trace_day.month:02d}" / f"{trace_day.day:02d}"
        )

        # Keep the original filename (includes calendar date and hour)
        return note_dir / original_filename
    else:
        # For daily notes: the date in the filename IS the Trace day
        # The file should be in a folder matching that date
        # Extract date from filename (day-YYYYMMDD.md)
        match = re.match(r"day-(\d{4})(\d{2})(\d{2})\.md$", original_filename)
        if match:
            year, month, day = map(int, match.groups())
            note_dir = NOTES_DIR / f"{year:04d}" / f"{month:02d}" / f"{day:02d}"
            return note_dir / original_filename

        # Fallback: use the date directly
        note_dir = NOTES_DIR / f"{dt.year:04d}" / f"{dt.month:02d}" / f"{dt.day:02d}"
        return note_dir / original_filename


def migrate_notes(dry_run: bool = True) -> MigrationResult:
    """
    Migrate all notes to use Trace day folder structure.

    Args:
        dry_run: If True, only report what would be done without making changes

    Returns:
        MigrationResult with details of what was done
    """
    result = MigrationResult()
    config = get_capture_config()
    revision_hour = config.get("daily_revision_hour", 3)

    logger.info(f"Starting Trace day migration (dry_run={dry_run})")
    logger.info(f"Daily revision hour: {revision_hour}")

    if not NOTES_DIR.exists():
        logger.info("Notes directory does not exist, nothing to migrate")
        return result

    # Find all note files
    note_files = list(NOTES_DIR.rglob("*.md"))
    result.notes_scanned = len(note_files)

    # Track moves to batch update database
    moves: list[tuple[Path, Path, str]] = []  # (old_path, new_path, note_id)

    for note_path in note_files:
        filename = note_path.name

        # Determine note type and parse datetime
        if filename.startswith("hour-"):
            note_dt = parse_hourly_note_filename(filename)
            note_type = "hour"
        elif filename.startswith("day-"):
            note_dt = parse_daily_note_filename(filename)
            note_type = "day"
        else:
            continue  # Skip unknown files

        if note_dt is None:
            logger.warning(f"Could not parse filename: {filename}")
            result.errors.append(f"Could not parse filename: {filename}")
            result.notes_failed += 1
            continue

        # Calculate correct path
        correct_path = get_correct_note_path(note_dt, note_type, revision_hour, filename)

        # Check if already in correct location
        if note_path == correct_path:
            result.notes_already_correct += 1
            continue

        # Note needs to be moved
        if dry_run:
            logger.info(f"[DRY RUN] Would move: {note_path} -> {correct_path}")
            result.notes_moved += 1
        else:
            try:
                # Ensure target directory exists
                correct_path.parent.mkdir(parents=True, exist_ok=True)

                # Move the file
                shutil.move(str(note_path), str(correct_path))
                logger.info(f"Moved: {note_path} -> {correct_path}")
                result.notes_moved += 1

                # Track for database update
                moves.append((note_path, correct_path, None))
            except Exception as e:
                logger.error(f"Failed to move {note_path}: {e}")
                result.errors.append(f"Failed to move {note_path}: {e}")
                result.notes_failed += 1

    # Update database file_path entries
    if not dry_run and moves:
        try:
            conn = get_connection()
            cursor = conn.cursor()

            for old_path, new_path, _ in moves:
                try:
                    cursor.execute(
                        "UPDATE notes SET file_path = ? WHERE file_path = ?",
                        (str(new_path), str(old_path)),
                    )
                    if cursor.rowcount > 0:
                        result.db_updated += 1
                    else:
                        # Try to find by matching end of path
                        old_relative = "/".join(old_path.parts[-4:])  # YYYY/MM/DD/file.md
                        cursor.execute(
                            "UPDATE notes SET file_path = ? WHERE file_path LIKE ?",
                            (str(new_path), f"%{old_relative}"),
                        )
                        if cursor.rowcount > 0:
                            result.db_updated += 1
                except Exception as e:
                    logger.error(f"Failed to update DB for {old_path}: {e}")
                    result.errors.append(f"Failed to update DB for {old_path}: {e}")
                    result.db_failed += 1

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            result.errors.append(f"Database connection failed: {e}")

    # Clean up empty directories
    if not dry_run:
        cleanup_empty_note_directories()

    return result


def cleanup_empty_note_directories() -> int:
    """
    Remove empty directories in the notes folder.

    Returns:
        Number of directories removed
    """
    if not NOTES_DIR.exists():
        return 0

    removed = 0
    # Walk bottom-up
    for dir_path in sorted(NOTES_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not dir_path.is_dir():
            continue

        # Check if empty (ignoring .DS_Store)
        contents = [f for f in dir_path.iterdir() if f.name != ".DS_Store"]
        if not contents:
            try:
                shutil.rmtree(dir_path)
                removed += 1
                logger.debug(f"Removed empty directory: {dir_path}")
            except Exception as e:
                logger.warning(f"Could not remove {dir_path}: {e}")

    if removed > 0:
        logger.info(f"Cleaned up {removed} empty directories")

    return removed


if __name__ == "__main__":
    import fire

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    def migrate(dry_run: bool = True):
        """
        Migrate notes to use Trace day folder structure.

        Args:
            dry_run: If True (default), only show what would be done.
                     Set to False to actually perform the migration.
        """
        result = migrate_notes(dry_run=dry_run)
        return {
            "dry_run": dry_run,
            "notes_scanned": result.notes_scanned,
            "notes_moved": result.notes_moved,
            "notes_already_correct": result.notes_already_correct,
            "notes_failed": result.notes_failed,
            "db_updated": result.db_updated,
            "db_failed": result.db_failed,
            "errors": result.errors,
        }

    def status():
        """Show current status without making changes."""
        return migrate(dry_run=True)

    fire.Fire(
        {
            "migrate": migrate,
            "status": status,
        }
    )
