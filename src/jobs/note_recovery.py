"""
Note Recovery Service for Trace

Detects and recovers note files that exist in the database but are missing
from the filesystem. This handles cases where users manually delete note
files or filesystem corruption occurs.

The service:
1. Scans the notes table for records where file_path doesn't exist on disk
2. Regenerates markdown files from stored json_payload
3. Runs on startup, periodically during health checks, and on-demand via IPC
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.revise.daily_note import DailyNoteGenerator
from src.revise.schemas import DailyRevisionSchema
from src.summarize.render import MarkdownRenderer
from src.summarize.schemas import HourlySummarySchema

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of note recovery operation."""

    notes_scanned: int = 0
    notes_missing_file: int = 0
    notes_recovered: int = 0
    notes_failed: int = 0
    recovered_details: list[dict] = field(default_factory=list)
    failed_details: list[dict] = field(default_factory=list)


class NoteRecoveryService:
    """
    Detects and recovers notes where:
    - DB record exists with valid json_payload
    - Markdown file is missing from filesystem

    This handles accidental deletion, filesystem corruption, or sync issues.
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the recovery service.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.hourly_renderer = MarkdownRenderer()
        self.daily_generator = DailyNoteGenerator(db_path=self.db_path)

    def find_missing_files(self) -> list[dict]:
        """
        Scan notes table for records where file_path doesn't exist.

        Returns:
            List of note records with missing files:
            {note_id, note_type, start_ts, end_ts, file_path, json_payload}
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                FROM notes
                WHERE json_payload IS NOT NULL
                AND json_payload != ''
                ORDER BY start_ts DESC
                """
            )

            missing = []
            for row in cursor.fetchall():
                file_path = Path(row["file_path"])
                if not file_path.exists():
                    missing.append(
                        {
                            "note_id": row["note_id"],
                            "note_type": row["note_type"],
                            "start_ts": row["start_ts"],
                            "end_ts": row["end_ts"],
                            "file_path": row["file_path"],
                            "json_payload": row["json_payload"],
                        }
                    )

            return missing

        finally:
            conn.close()

    def recover_note(self, note_record: dict) -> bool:
        """
        Regenerate a single note from its json_payload.

        Args:
            note_record: Dict with note_id, note_type, start_ts, end_ts, file_path, json_payload

        Returns:
            True if recovered successfully
        """
        note_type = note_record["note_type"]

        if note_type == "hour":
            return self._recover_hourly_note(note_record)
        elif note_type == "day":
            return self._recover_daily_note(note_record)
        else:
            logger.warning(f"Unknown note type: {note_type}")
            return False

    def _recover_hourly_note(self, note_record: dict) -> bool:
        """
        Regenerate hourly note from HourlySummarySchema json_payload.

        Args:
            note_record: Note record from database

        Returns:
            True if recovered successfully
        """
        try:
            # Parse the JSON payload
            payload_data = json.loads(note_record["json_payload"])
            summary = HourlySummarySchema.model_validate(payload_data)

            # Parse timestamps
            hour_start = datetime.fromisoformat(note_record["start_ts"])
            hour_end = datetime.fromisoformat(note_record["end_ts"])

            # Get file path
            file_path = Path(note_record["file_path"])

            # Extract location from summary
            location = summary.location

            # Render and save
            saved = self.hourly_renderer.render_to_file(
                summary=summary,
                note_id=note_record["note_id"],
                hour_start=hour_start,
                hour_end=hour_end,
                file_path=file_path,
                location=location,
            )

            if saved:
                logger.info(f"Recovered hourly note: {file_path}")
            else:
                logger.error(f"Failed to save recovered hourly note: {file_path}")

            return saved

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload for note {note_record['note_id']}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to recover hourly note {note_record['note_id']}: {e}")
            return False

    def _recover_daily_note(self, note_record: dict) -> bool:
        """
        Regenerate daily note from DailyRevisionSchema json_payload.

        Args:
            note_record: Note record from database

        Returns:
            True if recovered successfully
        """
        try:
            # Parse the JSON payload
            payload_data = json.loads(note_record["json_payload"])
            revision = DailyRevisionSchema.model_validate(payload_data)

            # Parse the day from start_ts
            day = datetime.fromisoformat(note_record["start_ts"])

            # Get file path
            file_path = Path(note_record["file_path"])

            # Render the daily note content
            content = self.daily_generator._render_daily_note(
                day=day,
                revision=revision,
                note_id=note_record["note_id"],
            )

            # Ensure directory exists and write file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Recovered daily note: {file_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload for note {note_record['note_id']}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to recover daily note {note_record['note_id']}: {e}")
            return False

    def recover_all(self, notify: bool = True) -> RecoveryResult:
        """
        Find all missing files and recover them.

        Args:
            notify: Whether to send macOS notifications (not implemented yet)

        Returns:
            RecoveryResult with statistics
        """
        result = RecoveryResult()

        # Find missing files
        missing = self.find_missing_files()
        result.notes_missing_file = len(missing)

        if not missing:
            logger.debug("No missing note files found")
            return result

        logger.info(f"Found {len(missing)} notes with missing files, attempting recovery...")

        # Count total notes scanned
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM notes WHERE json_payload IS NOT NULL")
            row = cursor.fetchone()
            result.notes_scanned = row["count"] if row else 0
        finally:
            conn.close()

        # Recover each note
        for note_record in missing:
            success = self.recover_note(note_record)

            if success:
                result.notes_recovered += 1
                result.recovered_details.append(
                    {
                        "note_id": note_record["note_id"],
                        "note_type": note_record["note_type"],
                        "file_path": note_record["file_path"],
                    }
                )
            else:
                result.notes_failed += 1
                result.failed_details.append(
                    {
                        "note_id": note_record["note_id"],
                        "note_type": note_record["note_type"],
                        "file_path": note_record["file_path"],
                    }
                )

        logger.info(
            f"Recovery complete: {result.notes_recovered} recovered, "
            f"{result.notes_failed} failed out of {result.notes_missing_file} missing"
        )

        return result

    def check_and_recover(self, notify: bool = True) -> RecoveryResult:
        """
        Convenience method for scheduled execution.

        This is the main entry point for periodic recovery checks.

        Args:
            notify: Whether to send notifications

        Returns:
            RecoveryResult with statistics
        """
        return self.recover_all(notify=notify)


if __name__ == "__main__":
    import fire

    def check(db_path: str | None = None):
        """
        Check for notes with missing files without recovering.

        Args:
            db_path: Path to database

        Returns:
            Dict with count and list of missing notes
        """
        service = NoteRecoveryService(db_path=db_path)
        missing = service.find_missing_files()

        return {
            "missing_count": len(missing),
            "missing_notes": [
                {
                    "note_id": n["note_id"][:8] + "...",
                    "note_type": n["note_type"],
                    "file_path": n["file_path"],
                }
                for n in missing
            ],
        }

    def recover(db_path: str | None = None, notify: bool = False):
        """
        Recover all notes with missing files.

        Args:
            db_path: Path to database
            notify: Whether to send notifications

        Returns:
            Dict with recovery statistics
        """
        service = NoteRecoveryService(db_path=db_path)
        result = service.recover_all(notify=notify)

        return {
            "notes_scanned": result.notes_scanned,
            "notes_missing": result.notes_missing_file,
            "notes_recovered": result.notes_recovered,
            "notes_failed": result.notes_failed,
            "recovered": [
                {"note_id": d["note_id"][:8] + "...", "file_path": d["file_path"]}
                for d in result.recovered_details
            ],
            "failed": [
                {"note_id": d["note_id"][:8] + "...", "file_path": d["file_path"]}
                for d in result.failed_details
            ],
        }

    fire.Fire({"check": check, "recover": recover})
