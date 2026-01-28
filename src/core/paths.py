"""
Data Directory Structure Management for Trace

This module defines and manages the data directory structure for Trace.
All paths are relative to the DATA_ROOT (~/Library/Application Support/Trace by default).

Directory structure:
    ~/Library/Application Support/Trace/
    ├── notes/YYYY/MM/DD/          # Durable Markdown notes
    │   ├── hour-YYYYMMDD-HH.md
    │   └── day-YYYYMMDD.md
    ├── db/trace.sqlite            # SQLite database (source of truth)
    ├── index/                     # Vector embeddings (if not in SQLite)
    └── cache/                     # Temporary, deleted daily after revision
        ├── screenshots/YYYYMMDD/  # YYYYMMDD is "Trace day", not calendar day
        ├── text_buffers/YYYYMMDD/
        └── ocr/YYYYMMDD/

"Trace day" concept:
    A Trace day runs from daily_revision_hour to daily_revision_hour the next day.
    For example, if daily_revision_hour=8:
    - "Jan 28 Trace day" = 8am Jan 28 to 8am Jan 29
    - A screenshot at 7am Jan 29 belongs to "Jan 28 Trace day"
    This ensures all activity before the daily revision is grouped together.
"""

import logging
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_default_data_root() -> Path:
    """Get the default data root path based on platform."""
    import sys

    if sys.platform == "darwin":
        # macOS: Use Application Support (Apple recommended)
        return Path.home() / "Library" / "Application Support" / "Trace"
    elif sys.platform == "win32":
        # Windows: Use AppData/Local
        appdata = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return Path(appdata) / "Trace"
    else:
        # Linux/other: Use XDG data home or ~/.local/share
        xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        return Path(xdg_data) / "Trace"


# Allow override via environment variable for testing/development
_data_root_override = os.environ.get("TRACE_DATA_ROOT")
DATA_ROOT: Path = Path(_data_root_override) if _data_root_override else _get_default_data_root()

# Primary directories
NOTES_DIR: Path = DATA_ROOT / "notes"
DB_DIR: Path = DATA_ROOT / "db"
INDEX_DIR: Path = DATA_ROOT / "index"
CACHE_DIR: Path = DATA_ROOT / "cache"

# Database file path
DB_PATH: Path = DB_DIR / "trace.sqlite"

# Alias for backward compatibility (some modules still reference APP_SUPPORT_DIR)
APP_SUPPORT_DIR: Path = DATA_ROOT

# Cache subdirectories
SCREENSHOTS_CACHE_DIR: Path = CACHE_DIR / "screenshots"
TEXT_BUFFERS_CACHE_DIR: Path = CACHE_DIR / "text_buffers"
OCR_CACHE_DIR: Path = CACHE_DIR / "ocr"

# All directories that should exist
_REQUIRED_DIRS: tuple[Path, ...] = (
    NOTES_DIR,
    DB_DIR,
    INDEX_DIR,
    CACHE_DIR,
    SCREENSHOTS_CACHE_DIR,
    TEXT_BUFFERS_CACHE_DIR,
    OCR_CACHE_DIR,
)


def get_daily_revision_hour() -> int:
    """
    Get the configured daily revision hour from settings.

    Returns:
        Hour (0-23) when daily revision runs. Defaults to 3 (3am).
    """
    try:
        from src.core.config import get_capture_config

        config = get_capture_config()
        return config.get("daily_revision_hour", 3)
    except Exception:
        return 3  # Default to 3am if config not available


def get_trace_day(dt: datetime | None = None, daily_revision_hour: int | None = None) -> date:
    """
    Get the "Trace day" for a given datetime.

    A Trace day runs from daily_revision_hour to daily_revision_hour the next day.
    For example, if daily_revision_hour=8:
    - 9am Jan 28 → Trace day is Jan 28
    - 7am Jan 29 → Trace day is Jan 28 (before 8am cutoff)
    - 9am Jan 29 → Trace day is Jan 29

    Args:
        dt: The datetime to check. Defaults to now.
        daily_revision_hour: Override the revision hour. Defaults to config value.

    Returns:
        The date representing the Trace day.
    """
    if dt is None:
        dt = datetime.now()

    if daily_revision_hour is None:
        daily_revision_hour = get_daily_revision_hour()

    # If current hour is before the revision hour, we're still in "yesterday's" Trace day
    if dt.hour < daily_revision_hour:
        return (dt - timedelta(days=1)).date()
    else:
        return dt.date()


def get_trace_day_range(
    trace_day: date, daily_revision_hour: int | None = None
) -> tuple[datetime, datetime]:
    """
    Get the datetime range for a Trace day.

    Args:
        trace_day: The Trace day date
        daily_revision_hour: Override the revision hour. Defaults to config value.

    Returns:
        Tuple of (start_datetime, end_datetime) for the Trace day.
        Start is inclusive, end is exclusive.
    """
    if daily_revision_hour is None:
        daily_revision_hour = get_daily_revision_hour()

    # Trace day starts at daily_revision_hour on that date
    start = datetime(trace_day.year, trace_day.month, trace_day.day, daily_revision_hour)

    # Trace day ends at daily_revision_hour the next calendar day
    next_day = trace_day + timedelta(days=1)
    end = datetime(next_day.year, next_day.month, next_day.day, daily_revision_hour)

    return (start, end)


def ensure_data_directories() -> dict[str, bool]:
    """
    Ensure all required data directories exist.

    Creates the directory structure on first run. This function is idempotent
    and safe to call multiple times.

    Returns:
        Dictionary mapping directory names to whether they were created (True)
        or already existed (False).
    """
    results: dict[str, bool] = {}

    for dir_path in _REQUIRED_DIRS:
        try:
            created = not dir_path.exists()
            dir_path.mkdir(parents=True, exist_ok=True)
            results[str(dir_path.relative_to(DATA_ROOT))] = created
            if created:
                logger.info(f"Created directory: {dir_path}")
        except OSError as e:
            logger.error(f"Failed to create directory {dir_path}: {e}")
            raise

    return results


def get_note_path(dt: datetime | date, note_type: str = "hour") -> Path:
    """
    Get the path for a note file based on date/time and type.

    Args:
        dt: The datetime or date for the note
        note_type: Either "hour" or "day"

    Returns:
        Full path to the note file

    Raises:
        ValueError: If note_type is not "hour" or "day"
    """
    if note_type not in ("hour", "day"):
        raise ValueError(f"note_type must be 'hour' or 'day', got '{note_type}'")

    if isinstance(dt, datetime):
        d = dt.date()
        hour = dt.hour
    else:
        d = dt
        hour = 0

    # Build the directory path: notes/YYYY/MM/DD/
    note_dir = NOTES_DIR / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"

    # Build the filename
    date_str = f"{d.year:04d}{d.month:02d}{d.day:02d}"
    if note_type == "hour":
        filename = f"hour-{date_str}-{hour:02d}.md"
    else:
        filename = f"day-{date_str}.md"

    return note_dir / filename


def get_daily_cache_dirs(dt: datetime | date | None = None) -> dict[str, Path]:
    """
    Get the cache directory paths for a specific Trace day.

    Cache directories are organized by Trace day (YYYYMMDD) to enable
    easy cleanup after daily revision. The Trace day is determined by
    the daily_revision_hour setting.

    Args:
        dt: The datetime or date. Defaults to now.
            If datetime, uses get_trace_day() to determine the Trace day.
            If date, uses that date directly as the Trace day.

    Returns:
        Dictionary with 'screenshots', 'text_buffers', and 'ocr' paths
    """
    if dt is None:
        trace_day = get_trace_day(datetime.now())
    elif isinstance(dt, datetime):
        trace_day = get_trace_day(dt)
    else:
        trace_day = dt  # Assume it's already the Trace day date

    date_str = f"{trace_day.year:04d}{trace_day.month:02d}{trace_day.day:02d}"

    return {
        "screenshots": SCREENSHOTS_CACHE_DIR / date_str,
        "text_buffers": TEXT_BUFFERS_CACHE_DIR / date_str,
        "ocr": OCR_CACHE_DIR / date_str,
    }


def get_hourly_screenshot_dir(dt: datetime | None = None) -> Path:
    """
    Get the screenshot directory path for a specific hour.

    Screenshots are organized by Trace day and hour (YYYYMMDD/HH) to enable
    cleanup after each hourly note is created. The Trace day is determined
    by the daily_revision_hour setting.

    For example, if daily_revision_hour=8:
    - 9am Jan 28 → saved to 20260128/09/
    - 7am Jan 29 → saved to 20260128/07/ (still Jan 28's Trace day)

    Args:
        dt: The datetime. Defaults to now.

    Returns:
        Path to the hour-specific screenshot directory
    """
    if dt is None:
        dt = datetime.now()

    # Get the Trace day for this datetime
    trace_day = get_trace_day(dt)

    date_str = f"{trace_day.year:04d}{trace_day.month:02d}{trace_day.day:02d}"
    hour_str = f"{dt.hour:02d}"

    return SCREENSHOTS_CACHE_DIR / date_str / hour_str


def ensure_hourly_screenshot_dir(dt: datetime | None = None) -> Path:
    """
    Ensure the screenshot directory for a specific hour exists.

    Args:
        dt: The datetime. Defaults to now.

    Returns:
        Path to the hour-specific screenshot directory
    """
    dir_path = get_hourly_screenshot_dir(dt)
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured hourly screenshot directory exists: {dir_path}")
    return dir_path


def delete_hourly_screenshot_dir(dt: datetime) -> bool:
    """
    Delete the screenshot directory for a specific hour.

    This should be called after successfully creating the hourly note.
    Handles both:
    - New structure: screenshots/YYYYMMDD/HH/
    - Legacy structure: screenshots/YYYYMMDD/ (files with HHMMSS timestamp prefix)

    Args:
        dt: The datetime for the hour to clean up

    Returns:
        True if deleted successfully, False otherwise
    """
    dir_path = get_hourly_screenshot_dir(dt)
    date_str = f"{dt.year:04d}{dt.month:02d}{dt.day:02d}"
    hour_prefix = f"{dt.hour:02d}"
    date_dir = SCREENSHOTS_CACHE_DIR / date_str
    deleted_count = 0

    # 1. Delete hourly subdirectory if it exists (new structure)
    if dir_path.exists():
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Deleted hourly screenshot directory: {dir_path}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete screenshot directory {dir_path}: {e}")
            return False

    # 2. Delete screenshots in parent date folder with matching hour prefix (legacy structure)
    # Screenshot filenames are: HHMMSSMMM_m{monitor}_{hash}.jpg
    if date_dir.exists():
        try:
            for file_path in date_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    # Check if filename starts with the hour prefix (HH)
                    filename = file_path.name
                    if filename[:2] == hour_prefix:
                        file_path.unlink()
                        deleted_count += 1
            if deleted_count > 1:  # More than just the directory
                logger.info(
                    f"Deleted {deleted_count - 1} legacy screenshots for hour {hour_prefix}"
                )
        except Exception as e:
            logger.error(f"Failed to delete legacy screenshots: {e}")
            return False

    # 3. Clean up empty directories in the screenshots cache
    cleanup_empty_cache_directories(SCREENSHOTS_CACHE_DIR)

    return True


def cleanup_empty_cache_directories(root_dir: Path) -> int:
    """
    Recursively remove empty directories under root_dir.

    Walks bottom-up through the directory tree and removes any empty
    directories (ignoring .DS_Store files). This handles cleanup when
    days, months, or years change.

    Args:
        root_dir: The root directory to clean (e.g., SCREENSHOTS_CACHE_DIR)

    Returns:
        Number of directories removed
    """
    if not root_dir.exists():
        return 0

    removed_count = 0

    # Walk bottom-up so we can remove child directories before checking parents
    # Use sorted() with reverse=True to process deepest paths first
    all_dirs = sorted(
        [d for d in root_dir.rglob("*") if d.is_dir()],
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for dir_path in all_dirs:
        try:
            # Check if directory is empty (ignoring .DS_Store)
            contents = list(dir_path.iterdir())
            non_ds_store = [f for f in contents if f.name != ".DS_Store"]

            if not non_ds_store:
                # Directory is empty or only has .DS_Store - remove it
                shutil.rmtree(dir_path)
                removed_count += 1
                logger.debug(f"Removed empty directory: {dir_path}")
        except Exception as e:
            logger.warning(f"Could not remove directory {dir_path}: {e}")

    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} empty directories under {root_dir}")

    return removed_count


def get_all_screenshot_hours() -> list[datetime]:
    """
    Get all hours that have screenshot directories.

    Returns:
        List of datetime objects representing hours with screenshots
    """
    hours = []

    if not SCREENSHOTS_CACHE_DIR.exists():
        return hours

    # Iterate through date directories (YYYYMMDD)
    for date_dir in sorted(SCREENSHOTS_CACHE_DIR.iterdir()):
        if not date_dir.is_dir():
            continue

        date_str = date_dir.name
        if len(date_str) != 8 or not date_str.isdigit():
            continue

        # Check for hour subdirectories
        for hour_dir in sorted(date_dir.iterdir()):
            if not hour_dir.is_dir():
                continue

            hour_str = hour_dir.name
            if len(hour_str) != 2 or not hour_str.isdigit():
                # Legacy: if it's not an hour dir, it might be old format files
                continue

            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                hour = int(hour_str)
                dt = datetime(year, month, day, hour)
                hours.append(dt)
            except ValueError:
                continue

    return hours


def ensure_daily_cache_dirs(dt: datetime | date | None = None) -> dict[str, Path]:
    """
    Ensure the cache directories for a specific date exist.

    Args:
        dt: The datetime or date. Defaults to today.

    Returns:
        Dictionary with paths that were created/verified
    """
    dirs = get_daily_cache_dirs(dt)

    for _name, dir_path in dirs.items():
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured cache directory exists: {dir_path}")

    return dirs


def ensure_note_directory(dt: datetime | date) -> Path:
    """
    Ensure the note directory for a specific date exists.

    Args:
        dt: The datetime or date

    Returns:
        Path to the note directory
    """
    if isinstance(dt, datetime):
        d = dt.date()
    else:
        d = dt

    note_dir = NOTES_DIR / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    note_dir.mkdir(parents=True, exist_ok=True)
    return note_dir


# Legacy data location (for migration)
_LEGACY_DATA_ROOT = Path.home() / "Trace"


def check_legacy_data() -> dict[str, bool]:
    """
    Check if there is data in the legacy location (~/Trace).

    Returns:
        Dictionary with 'has_legacy_data', 'has_new_data', 'needs_migration'
    """
    legacy_db = _LEGACY_DATA_ROOT / "db" / "trace.sqlite"
    legacy_notes = _LEGACY_DATA_ROOT / "notes"

    has_legacy = legacy_db.exists() or legacy_notes.exists()
    has_new = DB_PATH.exists() or NOTES_DIR.exists()

    return {
        "has_legacy_data": has_legacy,
        "has_new_data": has_new,
        "needs_migration": has_legacy and not has_new,
        "legacy_path": str(_LEGACY_DATA_ROOT),
        "new_path": str(DATA_ROOT),
    }


def migrate_legacy_data(dry_run: bool = True) -> dict[str, list[str]]:
    """
    Migrate data from legacy location (~/Trace) to new location.

    Args:
        dry_run: If True, only report what would be migrated without moving files

    Returns:
        Dictionary with lists of 'migrated' and 'errors' paths
    """
    status = check_legacy_data()

    if not status["needs_migration"]:
        return {
            "migrated": [],
            "errors": [],
            "message": "No migration needed",
        }

    migrated = []
    errors = []

    # Directories to migrate
    dirs_to_migrate = [
        ("db", _LEGACY_DATA_ROOT / "db", DB_DIR),
        ("notes", _LEGACY_DATA_ROOT / "notes", NOTES_DIR),
        ("index", _LEGACY_DATA_ROOT / "index", INDEX_DIR),
    ]

    for name, src, dst in dirs_to_migrate:
        if src.exists():
            if dry_run:
                migrated.append(f"[DRY RUN] Would migrate {name}: {src} -> {dst}")
            else:
                try:
                    # Ensure parent directory exists
                    dst.parent.mkdir(parents=True, exist_ok=True)

                    # Check if destination already exists
                    if dst.exists():
                        errors.append(f"Cannot migrate {name}: destination {dst} already exists")
                        logger.error(f"Cannot migrate {name}: destination {dst} already exists")
                    else:
                        # Move the directory
                        shutil.move(str(src), str(dst))
                        migrated.append(f"Migrated {name}: {src} -> {dst}")
                        logger.info(f"Migrated {name} from {src} to {dst}")
                except Exception as e:
                    errors.append(f"Failed to migrate {name}: {e}")
                    logger.error(f"Failed to migrate {name}: {e}")

    return {
        "migrated": migrated,
        "errors": errors,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    import fire

    def init():
        """Initialize all data directories."""
        results = ensure_data_directories()
        created_count = sum(1 for created in results.values() if created)
        return {
            "data_root": str(DATA_ROOT),
            "directories": results,
            "created": created_count,
            "total": len(results),
        }

    def show():
        """Show all data directory paths."""
        return {
            "data_root": str(DATA_ROOT),
            "notes": str(NOTES_DIR),
            "db": str(DB_DIR),
            "db_file": str(DB_PATH),
            "index": str(INDEX_DIR),
            "cache": str(CACHE_DIR),
            "screenshots_cache": str(SCREENSHOTS_CACHE_DIR),
            "text_buffers_cache": str(TEXT_BUFFERS_CACHE_DIR),
            "ocr_cache": str(OCR_CACHE_DIR),
        }

    def verify():
        """Verify all required directories exist."""
        missing = [str(d) for d in _REQUIRED_DIRS if not d.exists()]
        return {
            "valid": len(missing) == 0,
            "missing": missing,
        }

    def check_migration():
        """Check if migration from legacy location is needed."""
        return check_legacy_data()

    def migrate(dry_run: bool = True):
        """Migrate data from legacy ~/Trace to new location."""
        return migrate_legacy_data(dry_run=dry_run)

    def cleanup_empty():
        """Clean up empty directories in the cache."""
        screenshots_removed = cleanup_empty_cache_directories(SCREENSHOTS_CACHE_DIR)
        text_buffers_removed = cleanup_empty_cache_directories(TEXT_BUFFERS_CACHE_DIR)
        ocr_removed = cleanup_empty_cache_directories(OCR_CACHE_DIR)
        return {
            "screenshots_dirs_removed": screenshots_removed,
            "text_buffers_dirs_removed": text_buffers_removed,
            "ocr_dirs_removed": ocr_removed,
            "total_removed": screenshots_removed + text_buffers_removed + ocr_removed,
        }

    fire.Fire(
        {
            "init": init,
            "show": show,
            "verify": verify,
            "check_migration": check_migration,
            "migrate": migrate,
            "cleanup_empty": cleanup_empty,
        }
    )
