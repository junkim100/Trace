"""IPC handlers for service management.

Provides handlers for:
- Getting service health status
- Restarting individual services
- Triggering backfill operations
"""

import logging
from typing import Any

from src.trace_app.ipc import server
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


def _get_service_manager():
    """Get the service manager instance from the server module.

    We access it through the module to get the current value,
    not the value at import time.
    """
    return server._service_manager


@handler("services.get_health")
def handle_get_service_health(params: dict[str, Any]) -> dict[str, Any]:
    """Get health status of all services."""
    if _get_service_manager() is None:
        return {
            "healthy": False,
            "error": "Service manager not initialized",
            "services": {},
        }

    return _get_service_manager().get_health_status()


@handler("services.restart")
def handle_restart_service(params: dict[str, Any]) -> dict[str, Any]:
    """Restart a specific service.

    Params:
        service: Name of service to restart ('capture', 'hourly', 'daily')
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    service_name = params.get("service")
    if not service_name:
        return {
            "success": False,
            "error": "Missing 'service' parameter",
        }

    if service_name not in ("capture", "hourly", "daily"):
        return {
            "success": False,
            "error": f"Unknown service: {service_name}",
        }

    success = _get_service_manager().restart_service(service_name)

    return {
        "success": success,
        "service": service_name,
    }


@handler("services.trigger_backfill")
def handle_trigger_backfill(params: dict[str, Any]) -> dict[str, Any]:
    """Manually trigger backfill for missing notes (both hourly and daily).

    Params:
        notify: Whether to send notifications (default: True)
        force: If True, reprocess all hours ignoring job status and LLM checks (default: False)
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    notify = params.get("notify", True)
    force = params.get("force", False)

    try:
        # This now runs both hourly and daily backfill
        result = _get_service_manager().trigger_backfill(notify=notify, force=force)

        # Also get daily backfill info
        daily_missing = []
        try:
            daily_missing = _get_service_manager().find_missing_daily_notes()
        except Exception:
            pass

        return {
            "success": True,
            "hours_checked": result.hours_checked,
            "hours_missing": result.hours_missing,
            "hours_backfilled": result.hours_backfilled,
            "hours_failed": result.hours_failed,
            "daily_missing_count": len(daily_missing),
        }

    except Exception as e:
        logger.error(f"Backfill trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.trigger_daily_backfill")
def handle_trigger_daily_backfill(params: dict[str, Any]) -> dict[str, Any]:
    """Manually trigger daily backfill for missing daily notes.

    Finds days with hourly notes but no daily note and creates them.

    Params:
        notify: Whether to send notifications (default: True)
        max_days: Maximum days to backfill (default: 5)
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    notify = params.get("notify", True)
    max_days = params.get("max_days", 5)

    try:
        result = _get_service_manager().trigger_daily_backfill(notify=notify, max_days=max_days)

        return {
            "success": True,
            "days_checked": result.days_checked,
            "days_missing": result.days_missing,
            "days_backfilled": result.days_backfilled,
            "days_failed": result.days_failed,
        }

    except Exception as e:
        logger.error(f"Daily backfill trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.check_missing_daily")
def handle_check_missing_daily(params: dict[str, Any]) -> dict[str, Any]:
    """Check for missing daily notes without triggering backfill.

    Finds days with hourly notes but no daily note.
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    try:
        missing = _get_service_manager().find_missing_daily_notes()

        return {
            "success": True,
            "missing_count": len(missing),
            "missing_days": [d.strftime("%Y-%m-%d") for d in missing],
        }

    except Exception as e:
        logger.error(f"Missing daily check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.check_missing")
def handle_check_missing(params: dict[str, Any]) -> dict[str, Any]:
    """Check for ALL missing hourly notes without triggering backfill.

    Scans entire database for hours with activity but no notes.
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    try:
        sm = _get_service_manager()
        if sm._backfill_detector is None:
            from src.jobs.backfill import BackfillDetector

            sm._backfill_detector = BackfillDetector(
                db_path=sm.db_path,
                api_key=sm.api_key,
            )

        missing = sm._backfill_detector.find_missing_hours()

        return {
            "success": True,
            "missing_count": len(missing),
            "missing_hours": [h.isoformat() for h in missing],
        }

    except Exception as e:
        logger.error(f"Missing hours check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.check_missing_files")
def handle_check_missing_files(params: dict[str, Any]) -> dict[str, Any]:
    """Check for notes with missing files without recovering.

    Scans database for notes where the file_path doesn't exist on disk
    but the json_payload is valid (can be recovered).
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    try:
        missing = _get_service_manager().check_missing_note_files()

        return {
            "success": True,
            "missing_count": len(missing),
            "missing_notes": [
                {
                    "note_id": n["note_id"],
                    "note_type": n["note_type"],
                    "file_path": n["file_path"],
                }
                for n in missing
            ],
        }

    except Exception as e:
        logger.error(f"Missing files check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.recover_notes")
def handle_recover_notes(params: dict[str, Any]) -> dict[str, Any]:
    """Manually trigger note file recovery.

    Finds notes with missing files and regenerates them from the
    stored json_payload in the database.

    Params:
        notify: Whether to send notifications (default: True)
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    notify = params.get("notify", True)

    try:
        result = _get_service_manager().trigger_note_recovery(notify=notify)

        return {
            "success": True,
            "notes_scanned": result.notes_scanned,
            "notes_missing": result.notes_missing_file,
            "notes_recovered": result.notes_recovered,
            "notes_failed": result.notes_failed,
            "recovered": [
                {
                    "note_id": d["note_id"],
                    "note_type": d["note_type"],
                    "file_path": d["file_path"],
                }
                for d in result.recovered_details
            ],
            "failed": [
                {
                    "note_id": d["note_id"],
                    "note_type": d["note_type"],
                    "file_path": d["file_path"],
                }
                for d in result.failed_details
            ],
        }

    except Exception as e:
        logger.error(f"Note recovery trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.sync_notes")
def handle_sync_notes(params: dict[str, Any]) -> dict[str, Any]:
    """Manually trigger bidirectional notes sync.

    Performs comprehensive sync between filesystem and database:
    1. Index notes from disk that aren't in DB
    2. Recover missing files from DB json_payload
    3. Clean up orphaned DB records
    4. Remove empty notes with placeholder content

    Params:
        remove_empty: Whether to remove empty notes (default: True)
        dry_run: If True, only report what would be done (default: False)
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    remove_empty = params.get("remove_empty", True)
    dry_run = params.get("dry_run", False)

    try:
        result = _get_service_manager().trigger_notes_sync(
            remove_empty=remove_empty, dry_run=dry_run
        )

        return {
            "success": True,
            "dry_run": dry_run,
            "notes_indexed": result.notes_indexed,
            "files_recovered": result.files_recovered,
            "orphans_cleaned": result.orphaned_cleaned,
            "empty_removed": result.empty_notes_removed,
            "has_changes": result.has_changes,
            "errors": result.errors,
            "details": {
                "indexed": result.indexed_notes,
                "recovered": result.recovered_files,
                "removed_orphans": result.removed_orphans,
                "removed_empty": result.removed_empty,
            },
        }

    except Exception as e:
        logger.error(f"Notes sync trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@handler("services.check_sync_status")
def handle_check_sync_status(params: dict[str, Any]) -> dict[str, Any]:
    """Check notes sync status without making changes.

    Returns current sync state between filesystem and database,
    including counts of notes that need syncing.
    """
    if _get_service_manager() is None:
        return {
            "success": False,
            "error": "Service manager not initialized",
        }

    try:
        status = _get_service_manager().check_notes_sync_status()

        return {
            "success": True,
            **status,
        }

    except Exception as e:
        logger.error(f"Sync status check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
