"""
Reset/Clear Data Functionality for Trace

Provides functionality to completely reset Trace data:
- Delete all notes (markdown files)
- Clear the database (entities, edges, aggregates, etc.)
- Clear user memory
- Clear cache (screenshots, text buffers, OCR)

WARNING: This is a destructive operation that cannot be undone.
Users should export their data first using the export feature.
"""

import logging
import shutil
import sqlite3

from src.core.paths import APP_SUPPORT_DIR, CACHE_DIR, DB_PATH, NOTES_DIR

logger = logging.getLogger(__name__)


def reset_all_data() -> dict:
    """
    Reset all Trace data.

    This will:
    1. Delete all notes (markdown files)
    2. Clear the database
    3. Clear user memory
    4. Clear cache (screenshots, text buffers, OCR)

    Returns:
        Dictionary with success status and details
    """
    results = {
        "success": True,
        "notes_deleted": False,
        "database_cleared": False,
        "memory_cleared": False,
        "cache_cleared": False,
        "errors": [],
    }

    # 1. Delete all notes
    try:
        if NOTES_DIR.exists():
            shutil.rmtree(NOTES_DIR)
            NOTES_DIR.mkdir(parents=True, exist_ok=True)
            results["notes_deleted"] = True
            logger.info("Deleted all notes")
        else:
            results["notes_deleted"] = True
            logger.info("Notes directory doesn't exist, nothing to delete")
    except Exception as e:
        results["errors"].append(f"Failed to delete notes: {e}")
        results["success"] = False
        logger.error(f"Failed to delete notes: {e}")

    # 2. Clear the database
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH)
            try:
                cursor = conn.cursor()

                # Get all table names
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

                # Delete data from all tables (except sqlite_sequence)
                for table in tables:
                    if table != "sqlite_sequence":
                        try:
                            cursor.execute(f"DELETE FROM {table}")  # noqa: S608
                            logger.info(f"Cleared table: {table}")
                        except sqlite3.OperationalError as e:
                            logger.warning(f"Could not clear table {table}: {e}")

                # Reset autoincrement counters
                try:
                    cursor.execute("DELETE FROM sqlite_sequence")
                except sqlite3.OperationalError:
                    pass  # Table might not exist

                conn.commit()
                results["database_cleared"] = True
                logger.info("Database cleared")
            finally:
                conn.close()
        else:
            results["database_cleared"] = True
            logger.info("Database doesn't exist, nothing to clear")
    except Exception as e:
        results["errors"].append(f"Failed to clear database: {e}")
        results["success"] = False
        logger.error(f"Failed to clear database: {e}")

    # 3. Clear user memory
    try:
        memory_path = APP_SUPPORT_DIR / "MEMORY.md"
        if memory_path.exists():
            memory_path.unlink()
            results["memory_cleared"] = True
            logger.info("User memory cleared")
        else:
            results["memory_cleared"] = True
            logger.info("User memory doesn't exist, nothing to clear")
    except Exception as e:
        results["errors"].append(f"Failed to clear memory: {e}")
        results["success"] = False
        logger.error(f"Failed to clear memory: {e}")

    # 4. Clear cache (screenshots, text buffers, OCR)
    try:
        if CACHE_DIR.exists():
            # Delete contents but keep the cache directory
            for item in CACHE_DIR.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            results["cache_cleared"] = True
            logger.info("Cache cleared")
        else:
            results["cache_cleared"] = True
            logger.info("Cache directory doesn't exist, nothing to clear")
    except Exception as e:
        results["errors"].append(f"Failed to clear cache: {e}")
        results["success"] = False
        logger.error(f"Failed to clear cache: {e}")

    return results


def get_data_summary() -> dict:
    """
    Get a summary of all data that would be deleted by a reset.

    Returns:
        Dictionary with counts of data to be deleted
    """
    summary = {
        "notes_count": 0,
        "notes_size_bytes": 0,
        "database_exists": False,
        "tables_with_data": [],
        "memory_exists": False,
        "cache_size_bytes": 0,
    }

    # Count notes
    if NOTES_DIR.exists():
        for md_file in NOTES_DIR.rglob("*.md"):
            summary["notes_count"] += 1
            summary["notes_size_bytes"] += md_file.stat().st_size

    # Check database
    if DB_PATH.exists():
        summary["database_exists"] = True
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Check which tables have data
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                if table != "sqlite_sequence":
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                        count = cursor.fetchone()[0]
                        if count > 0:
                            summary["tables_with_data"].append({"table": table, "count": count})
                    except sqlite3.OperationalError:
                        pass

            conn.close()
        except Exception as e:
            logger.error(f"Failed to check database: {e}")

    # Check memory
    memory_path = APP_SUPPORT_DIR / "MEMORY.md"
    summary["memory_exists"] = memory_path.exists()

    # Check cache size
    if CACHE_DIR.exists():
        for item in CACHE_DIR.rglob("*"):
            if item.is_file():
                summary["cache_size_bytes"] += item.stat().st_size

    return summary


if __name__ == "__main__":
    import fire

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def summary():
        """Show summary of data that would be deleted."""
        return get_data_summary()

    def reset(confirm: bool = False):
        """Reset all data. Pass --confirm to actually perform the reset."""
        if not confirm:
            print("WARNING: This will delete ALL your Trace data!")
            print("This includes notes, entities, relationships, and user memory.")
            print("Run with --confirm to actually perform the reset.")
            print("\nData that would be deleted:")
            return get_data_summary()

        return reset_all_data()

    fire.Fire({"summary": summary, "reset": reset})
