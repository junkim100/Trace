"""
Hourly Note Revision for Trace Daily Revision

Updates hourly notes with day context, refreshes files on disk,
and updates database records.

P6-03: Hourly note revision
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.revise.schemas import DailyRevisionSchema, HourlyRevisionItem
from src.summarize.render import MarkdownRenderer
from src.summarize.schemas import HourlySummarySchema

logger = logging.getLogger(__name__)


@dataclass
class RevisionResult:
    """Result of revising a single hourly note."""

    note_id: str
    hour: int
    success: bool
    file_path: Path | None
    revised_summary: str | None
    error: str | None = None


@dataclass
class DailyRevisionResult:
    """Result of revising all hourly notes for a day."""

    day: str
    total_notes: int
    revised_count: int
    failed_count: int
    revisions: list[RevisionResult]


class HourlyNoteReviser:
    """
    Revises hourly notes with daily context.

    Handles:
    - Updating hourly note summaries with day-level insights
    - Adding additional context from daily revision
    - Refreshing Markdown files on disk
    - Updating database records
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the reviser.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.renderer = MarkdownRenderer()

    def revise_hourly_notes(
        self,
        day: datetime,
        revision: DailyRevisionSchema,
    ) -> DailyRevisionResult:
        """
        Revise all hourly notes for a day using the daily revision output.

        Args:
            day: The day being revised
            revision: DailyRevisionSchema from LLM

        Returns:
            DailyRevisionResult with status of each revision
        """
        results = []
        revised_count = 0
        failed_count = 0

        conn = get_connection(self.db_path)
        try:
            # Get all hourly notes for the day
            hourly_notes = self._get_hourly_notes_for_day(conn, day)

            # Create a lookup of revisions by note_id
            revisions_by_id = {rev.note_id: rev for rev in revision.hourly_revisions}

            for note in hourly_notes:
                note_id = note["note_id"]
                hour = note["hour"]

                # Find revision for this note
                note_revision = revisions_by_id.get(note_id)

                if note_revision:
                    result = self._revise_single_note(conn, note, note_revision)
                else:
                    # No revision for this note - still mark as processed
                    result = RevisionResult(
                        note_id=note_id,
                        hour=hour,
                        success=True,
                        file_path=Path(note["file_path"]),
                        revised_summary=None,
                        error="No revision provided",
                    )

                results.append(result)
                if result.success:
                    revised_count += 1
                else:
                    failed_count += 1

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to revise hourly notes: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

        return DailyRevisionResult(
            day=day.strftime("%Y-%m-%d"),
            total_notes=len(hourly_notes),
            revised_count=revised_count,
            failed_count=failed_count,
            revisions=results,
        )

    def _get_hourly_notes_for_day(
        self,
        conn,
        day: datetime,
    ) -> list[dict]:
        """
        Get all hourly notes for a specific Trace day.

        A Trace day runs from daily_revision_hour to daily_revision_hour the next day.
        For example, if daily_revision_hour=3:
        - "Jan 28 Trace day" = 3am Jan 28 to 3am Jan 29

        This ensures notes from late night hours (e.g., 00:00-03:00 on Jan 29)
        are correctly included in Jan 28's daily revision.

        Args:
            conn: Database connection
            day: The Trace day to get notes for (uses date portion)

        Returns:
            List of note dicts
        """
        from src.core.paths import get_trace_day_range

        cursor = conn.cursor()

        # Calculate Trace day boundaries (not calendar day!)
        trace_day = day.date() if isinstance(day, datetime) else day
        day_start, day_end = get_trace_day_range(trace_day)

        cursor.execute(
            """
            SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
            FROM notes
            WHERE note_type = 'hour'
            AND start_ts >= ? AND start_ts < ?
            ORDER BY start_ts
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        notes = []
        for row in cursor.fetchall():
            start_ts = datetime.fromisoformat(row["start_ts"])
            notes.append(
                {
                    "note_id": row["note_id"],
                    "note_type": row["note_type"],
                    "start_ts": start_ts,
                    "end_ts": datetime.fromisoformat(row["end_ts"]),
                    "file_path": row["file_path"],
                    "json_payload": json.loads(row["json_payload"]),
                    "hour": start_ts.hour,
                }
            )

        return notes

    def _revise_single_note(
        self,
        conn,
        note: dict,
        revision: HourlyRevisionItem,
    ) -> RevisionResult:
        """
        Revise a single hourly note.

        Args:
            conn: Database connection
            note: Original note data
            revision: Revision data from daily revision

        Returns:
            RevisionResult
        """
        note_id = note["note_id"]
        hour = note["hour"]
        file_path = Path(note["file_path"])

        try:
            # Get the original summary
            original_payload = note["json_payload"]

            # Update the summary with revision
            updated_payload = self._apply_revision_to_payload(original_payload, revision)

            # Create updated HourlySummarySchema
            updated_summary = HourlySummarySchema.model_validate(updated_payload)

            # Render updated Markdown
            hour_start = note["start_ts"]
            hour_end = note["end_ts"]
            location = updated_summary.location

            # Render and write to file
            success = self.renderer.render_to_file(
                updated_summary,
                note_id,
                hour_start,
                hour_end,
                file_path,
                location,
            )

            if not success:
                return RevisionResult(
                    note_id=note_id,
                    hour=hour,
                    success=False,
                    file_path=file_path,
                    revised_summary=None,
                    error="Failed to write file",
                )

            # Update database record
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE notes
                SET json_payload = ?, updated_ts = ?
                WHERE note_id = ?
                """,
                (
                    json.dumps(updated_payload),
                    datetime.now().isoformat(),
                    note_id,
                ),
            )

            logger.info(f"Revised note {note_id} for hour {hour:02d}:00")

            return RevisionResult(
                note_id=note_id,
                hour=hour,
                success=True,
                file_path=file_path,
                revised_summary=revision.revised_summary,
            )

        except Exception as e:
            logger.error(f"Failed to revise note {note_id}: {e}")
            return RevisionResult(
                note_id=note_id,
                hour=hour,
                success=False,
                file_path=file_path,
                revised_summary=None,
                error=str(e),
            )

    def _apply_revision_to_payload(
        self,
        original_payload: dict,
        revision: HourlyRevisionItem,
    ) -> dict:
        """
        Apply revision data to the original payload.

        Args:
            original_payload: Original JSON payload
            revision: Revision from daily revision

        Returns:
            Updated payload dict
        """
        updated = original_payload.copy()

        # Update summary if revised
        if revision.revised_summary:
            updated["summary"] = revision.revised_summary

        # Update entities with canonical names
        if revision.revised_entities:
            updated_entities = []
            for rev_entity in revision.revised_entities:
                updated_entities.append(
                    {
                        "name": rev_entity.canonical_name,
                        "type": rev_entity.type,
                        "confidence": rev_entity.confidence,
                    }
                )
            # Merge with existing entities (prefer revised versions)
            existing_names = {e["name"].lower() for e in updated_entities}
            for orig_entity in original_payload.get("entities", []):
                if orig_entity["name"].lower() not in existing_names:
                    updated_entities.append(orig_entity)
            updated["entities"] = updated_entities

        # Add additional context to summary if provided
        if revision.additional_context:
            # Append additional context to summary
            current_summary = updated.get("summary", "")
            if current_summary and not current_summary.endswith("."):
                current_summary += "."
            updated["summary"] = f"{current_summary} {revision.additional_context}"

        return updated

    def get_note_for_revision(self, note_id: str) -> dict | None:
        """
        Get a single note by ID for potential revision.

        Args:
            note_id: Note ID

        Returns:
            Note dict or None
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                FROM notes
                WHERE note_id = ?
                """,
                (note_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            start_ts = datetime.fromisoformat(row["start_ts"])
            return {
                "note_id": row["note_id"],
                "note_type": row["note_type"],
                "start_ts": start_ts,
                "end_ts": datetime.fromisoformat(row["end_ts"]),
                "file_path": row["file_path"],
                "json_payload": json.loads(row["json_payload"]),
                "hour": start_ts.hour,
            }

        finally:
            conn.close()


def load_hourly_notes_for_day(
    day: datetime,
    db_path: Path | str | None = None,
) -> list[dict]:
    """
    Load all hourly notes for a Trace day from the database.

    A Trace day runs from daily_revision_hour to daily_revision_hour the next day.
    For example, if daily_revision_hour=8:
    - "Jan 28 Trace day" = 8am Jan 28 to 8am Jan 29

    Utility function for building the daily revision prompt.

    Args:
        day: The Trace day to load notes for (uses date portion)
        db_path: Path to SQLite database

    Returns:
        List of note dicts suitable for daily revision prompt
    """
    from src.core.paths import get_trace_day_range

    db_path = Path(db_path) if db_path else DB_PATH

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Calculate Trace day boundaries
        trace_day = day.date() if isinstance(day, datetime) else day
        day_start, day_end = get_trace_day_range(trace_day)

        cursor.execute(
            """
            SELECT note_id, start_ts, file_path, json_payload
            FROM notes
            WHERE note_type = 'hour'
            AND start_ts >= ? AND start_ts < ?
            ORDER BY start_ts
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        notes = []
        for row in cursor.fetchall():
            start_ts = datetime.fromisoformat(row["start_ts"])
            notes.append(
                {
                    "note_id": row["note_id"],
                    "hour": start_ts.hour,
                    "file_path": row["file_path"],
                    "summary": json.loads(row["json_payload"]),
                }
            )

        return notes

    finally:
        conn.close()


if __name__ == "__main__":
    import fire

    def list_notes(day: str | None = None, db_path: str | None = None):
        """
        List hourly notes for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        notes = load_hourly_notes_for_day(target_day, db_path)

        return {
            "day": target_day.strftime("%Y-%m-%d"),
            "note_count": len(notes),
            "notes": [
                {
                    "note_id": n["note_id"][:8] + "...",
                    "hour": f"{n['hour']:02d}:00",
                    "summary_preview": n["summary"].get("summary", "")[:50] + "...",
                }
                for n in notes
            ],
        }

    def demo():
        """Show demo revision data."""
        from src.revise.schemas import DailyRevisionSchema, HourlyRevisionItem, RevisedEntityItem

        revision = DailyRevisionSchema(
            schema_version=1,
            day_summary="A productive day focused on coding.",
            hourly_revisions=[
                HourlyRevisionItem(
                    hour="10:00",
                    note_id="sample-note-001",
                    revised_summary="Deep work session on the Trace project.",
                    revised_entities=[
                        RevisedEntityItem(
                            original_name="VS Code",
                            canonical_name="visual studio code",
                            type="app",
                            confidence=0.95,
                        )
                    ],
                    additional_context="This was part of a larger morning coding session.",
                )
            ],
            entity_normalizations=[],
            graph_edges=[],
        )

        print("Sample revision schema:")
        print(json.dumps(revision.model_dump(), indent=2))

    fire.Fire(
        {
            "list": list_notes,
            "demo": demo,
        }
    )
