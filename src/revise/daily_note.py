"""
Daily Summary Note Generation for Trace

Generates the optional day-YYYYMMDD.md summary note from daily revision output.

P6-04: Daily summary note generation
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH, get_note_path
from src.db.migrations import get_connection
from src.revise.schemas import DailyRevisionSchema

logger = logging.getLogger(__name__)


@dataclass
class DailyNoteResult:
    """Result of generating a daily summary note."""

    note_id: str
    file_path: Path
    success: bool
    error: str | None = None


class DailyNoteGenerator:
    """
    Generates daily summary notes from daily revision output.

    Creates a day-YYYYMMDD.md file with:
    - Day-level summary
    - Top entities and accomplishments
    - Patterns observed
    - Open loops consolidated from all hours
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the generator.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def generate(
        self,
        day: datetime,
        revision: DailyRevisionSchema,
    ) -> DailyNoteResult:
        """
        Generate a daily summary note.

        Args:
            day: The day being summarized
            revision: DailyRevisionSchema from LLM

        Returns:
            DailyNoteResult with status
        """
        note_id = str(uuid.uuid4())
        file_path = get_note_path(day, note_type="day")

        try:
            # Render the daily note
            content = self._render_daily_note(day, revision, note_id)

            # Ensure directory exists and write file
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Store in database
            self._store_note_in_db(day, note_id, file_path, revision)

            logger.info(f"Generated daily note {note_id} at {file_path}")

            return DailyNoteResult(
                note_id=note_id,
                file_path=file_path,
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to generate daily note: {e}")
            return DailyNoteResult(
                note_id=note_id,
                file_path=file_path,
                success=False,
                error=str(e),
            )

    def _render_daily_note(
        self,
        day: datetime,
        revision: DailyRevisionSchema,
        note_id: str,
    ) -> str:
        """
        Render the daily note to Markdown.

        Args:
            day: The day being summarized
            revision: DailyRevisionSchema
            note_id: Note ID

        Returns:
            Complete Markdown content
        """
        lines = []

        # Frontmatter
        lines.append("---")
        lines.extend(self._build_frontmatter(day, revision, note_id))
        lines.append("---")
        lines.append("")

        # Title
        date_str = day.strftime("%A, %B %d, %Y")
        lines.append(f"# Daily Summary: {date_str}")
        lines.append("")

        # Day summary
        lines.append("## Overview")
        lines.append("")
        lines.append(revision.day_summary)
        lines.append("")

        # Primary focus
        if revision.primary_focus:
            lines.append(f"**Primary Focus**: {revision.primary_focus}")
            lines.append("")

        # Accomplishments
        if revision.accomplishments:
            lines.append("## Accomplishments")
            lines.append("")
            for acc in revision.accomplishments:
                lines.append(f"- [x] {acc}")
            lines.append("")

        # Top entities
        top = revision.top_entities
        has_top = top.topics or top.apps or top.domains or top.media

        if has_top:
            lines.append("## Top Activities")
            lines.append("")

            if top.topics:
                lines.append("### Topics")
                lines.append("")
                for item in top.topics[:5]:
                    lines.append(f"- **{item.name}** ({item.total_minutes}m)")
                lines.append("")

            if top.apps:
                lines.append("### Applications")
                lines.append("")
                for item in top.apps[:5]:
                    lines.append(f"- **{item.name}** ({item.total_minutes}m)")
                lines.append("")

            if top.domains:
                lines.append("### Websites")
                lines.append("")
                for item in top.domains[:5]:
                    lines.append(f"- **{item.name}** ({item.total_minutes}m)")
                lines.append("")

            if top.media:
                lines.append("### Media")
                lines.append("")
                for item in top.media[:5]:
                    media_type = f" [{item.type}]" if item.type else ""
                    lines.append(f"- *{item.name}*{media_type} ({item.total_minutes}m)")
                lines.append("")

        # Patterns
        if revision.patterns:
            lines.append("## Patterns")
            lines.append("")
            for pattern in revision.patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        # Hourly breakdown
        if revision.hourly_revisions:
            lines.append("## Hourly Breakdown")
            lines.append("")
            lines.append("| Hour | Summary |")
            lines.append("|------|---------|")
            for hr in sorted(revision.hourly_revisions, key=lambda x: x.hour):
                # Truncate summary for table
                summary = hr.revised_summary
                if len(summary) > 60:
                    summary = summary[:57] + "..."
                lines.append(f"| {hr.hour} | {summary} |")
            lines.append("")

        # Location
        if revision.location_summary:
            lines.append("---")
            lines.append(f"*Location: {revision.location_summary}*")
            lines.append("")

        return "\n".join(lines)

    def _build_frontmatter(
        self,
        day: datetime,
        revision: DailyRevisionSchema,
        note_id: str,
    ) -> list[str]:
        """Build YAML frontmatter lines."""
        lines = []

        # Basic metadata
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59)

        lines.append(f"id: {note_id}")
        lines.append("type: day")
        lines.append(f"date: {day.strftime('%Y-%m-%d')}")
        lines.append(f"start_time: {day_start.isoformat()}")
        lines.append(f"end_time: {day_end.isoformat()}")

        # Primary focus
        if revision.primary_focus:
            focus_escaped = revision.primary_focus.replace('"', '\\"')
            lines.append(f'primary_focus: "{focus_escaped}"')
        else:
            lines.append("primary_focus: null")

        # Location
        if revision.location_summary:
            loc_escaped = revision.location_summary.replace('"', '\\"')
            lines.append(f'location: "{loc_escaped}"')
        else:
            lines.append("location: null")

        # Accomplishments count
        lines.append(f"accomplishments_count: {len(revision.accomplishments)}")

        # Hours covered
        lines.append(f"hours_covered: {len(revision.hourly_revisions)}")

        # Schema version
        lines.append(f"schema_version: {revision.schema_version}")

        return lines

    def _store_note_in_db(
        self,
        day: datetime,
        note_id: str,
        file_path: Path,
        revision: DailyRevisionSchema,
    ) -> None:
        """
        Store the daily note in the database.

        Args:
            day: The day being summarized
            note_id: Note ID
            file_path: Path to the Markdown file
            revision: DailyRevisionSchema
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59)

            # Check for existing daily note
            cursor.execute(
                """
                SELECT note_id FROM notes
                WHERE note_type = 'day'
                AND start_ts >= ? AND start_ts <= ?
                """,
                (day_start.isoformat(), day_end.isoformat()),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing
                cursor.execute(
                    """
                    UPDATE notes
                    SET file_path = ?, json_payload = ?, updated_ts = ?
                    WHERE note_id = ?
                    """,
                    (
                        str(file_path),
                        json.dumps(revision.model_dump()),
                        datetime.now().isoformat(),
                        existing["note_id"],
                    ),
                )
                logger.debug(f"Updated existing daily note {existing['note_id']}")
            else:
                # Insert new
                cursor.execute(
                    """
                    INSERT INTO notes
                    (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                    VALUES (?, 'day', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note_id,
                        day_start.isoformat(),
                        day_end.isoformat(),
                        str(file_path),
                        json.dumps(revision.model_dump()),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to store daily note in database: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_daily_note(self, day: datetime) -> dict | None:
        """
        Get the daily note for a specific day.

        Args:
            day: The day to get

        Returns:
            Note dict or None
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59)

            cursor.execute(
                """
                SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload
                FROM notes
                WHERE note_type = 'day'
                AND start_ts >= ? AND start_ts <= ?
                """,
                (day_start.isoformat(), day_end.isoformat()),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "note_id": row["note_id"],
                "note_type": row["note_type"],
                "start_ts": row["start_ts"],
                "end_ts": row["end_ts"],
                "file_path": row["file_path"],
                "json_payload": json.loads(row["json_payload"]),
            }

        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def demo():
        """Generate a demo daily note."""
        from src.revise.schemas import (
            DailyRevisionSchema,
            GraphEdgeItem,
            HourlyRevisionItem,
            TopEntitiesSection,
            TopEntityItem,
        )

        revision = DailyRevisionSchema(
            schema_version=1,
            day_summary="A highly productive day focused on implementing the Trace application. Made significant progress on the daily revision module and entity normalization features. Spent quality time in deep work mode with minimal interruptions.",
            primary_focus="coding",
            accomplishments=[
                "Completed entity normalization module",
                "Implemented daily revision prompt",
                "Fixed 3 bugs in the capture daemon",
                "Reviewed and merged 2 pull requests",
            ],
            hourly_revisions=[
                HourlyRevisionItem(
                    hour="09:00",
                    note_id="note-001",
                    revised_summary="Morning standup and planning session.",
                ),
                HourlyRevisionItem(
                    hour="10:00",
                    note_id="note-002",
                    revised_summary="Deep work on entity normalization module.",
                ),
                HourlyRevisionItem(
                    hour="11:00",
                    note_id="note-003",
                    revised_summary="Continued coding, integrated with database layer.",
                ),
                HourlyRevisionItem(
                    hour="14:00",
                    note_id="note-004",
                    revised_summary="Afternoon coding session on daily revision.",
                ),
                HourlyRevisionItem(
                    hour="15:00",
                    note_id="note-005",
                    revised_summary="Code review and bug fixes.",
                ),
            ],
            entity_normalizations=[],
            graph_edges=[
                GraphEdgeItem(
                    from_entity="Python",
                    from_type="topic",
                    to_entity="visual studio code",
                    to_type="app",
                    edge_type="USED_APP",
                    weight=0.9,
                )
            ],
            top_entities=TopEntitiesSection(
                topics=[
                    TopEntityItem(name="Python", total_minutes=180),
                    TopEntityItem(name="Database design", total_minutes=45),
                ],
                apps=[
                    TopEntityItem(name="Visual Studio Code", total_minutes=240),
                    TopEntityItem(name="Safari", total_minutes=60),
                ],
                domains=[
                    TopEntityItem(name="github.com", total_minutes=45),
                    TopEntityItem(name="docs.python.org", total_minutes=30),
                ],
                media=[
                    TopEntityItem(name="Lofi Girl - Study Beats", type="track", total_minutes=120),
                ],
            ),
            patterns=[
                "Most productive during morning hours (9-12)",
                "Deep work sessions averaged 90 minutes",
                "Music listening correlates with coding sessions",
            ],
            location_summary="Home office",
        )

        generator = DailyNoteGenerator()
        content = generator._render_daily_note(
            datetime.now(),
            revision,
            "demo-note-001",
        )

        print(content)

    def get(day: str | None = None, db_path: str | None = None):
        """
        Get the daily note for a specific day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        generator = DailyNoteGenerator(db_path=db_path)
        note = generator.get_daily_note(target_day)

        if note is None:
            return {"found": False, "day": target_day.strftime("%Y-%m-%d")}

        return {
            "found": True,
            "note_id": note["note_id"][:8] + "...",
            "file_path": note["file_path"],
            "day_summary": note["json_payload"].get("day_summary", "")[:100] + "...",
        }

    fire.Fire(
        {
            "demo": demo,
            "get": get,
        }
    )
