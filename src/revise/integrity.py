"""
Integrity Checkpoint for Trace Daily Revision

Validates all notes, embeddings, and edges before allowing deletion
of raw artifacts. Blocks deletion if integrity check fails.

P6-08: Integrity checkpoint
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection

logger = logging.getLogger(__name__)


@dataclass
class IntegrityIssue:
    """A single integrity issue found."""

    issue_type: str  # missing_file, missing_embedding, invalid_json, orphaned_entity
    entity_type: str  # note, entity, edge
    entity_id: str
    description: str
    severity: str  # error, warning


@dataclass
class IntegrityCheckResult:
    """Result of an integrity check."""

    day: str
    passed: bool
    total_notes: int
    total_entities: int
    total_edges: int
    issues: list[IntegrityIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0


class IntegrityChecker:
    """
    Validates data integrity before allowing raw artifact deletion.

    Checks:
    - All hourly notes exist and have valid JSON
    - All note files exist on disk
    - All notes have embeddings (if embeddings were computed)
    - All note-entity links reference valid entities
    - All edges reference valid entities
    - Daily note exists if hourly notes exist
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the checker.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def check_integrity(
        self,
        day: datetime,
        require_embeddings: bool = True,
        require_daily_note: bool = False,
    ) -> IntegrityCheckResult:
        """
        Run full integrity check for a day.

        Args:
            day: The day to check
            require_embeddings: If True, require all notes to have embeddings
            require_daily_note: If True, require daily note to exist

        Returns:
            IntegrityCheckResult with any issues found
        """
        issues = []
        total_notes = 0
        total_entities = 0
        total_edges = 0

        conn = get_connection(self.db_path)
        try:
            # Check hourly notes
            hourly_issues, note_count = self._check_hourly_notes(conn, day, require_embeddings)
            issues.extend(hourly_issues)
            total_notes += note_count

            # Check daily note
            daily_issues, has_daily = self._check_daily_note(conn, day, require_daily_note)
            issues.extend(daily_issues)
            if has_daily:
                total_notes += 1

            # Check entities referenced by notes
            entity_issues, entity_count = self._check_entities(conn, day)
            issues.extend(entity_issues)
            total_entities = entity_count

            # Check edges
            edge_issues, edge_count = self._check_edges(conn, day)
            issues.extend(edge_issues)
            total_edges = edge_count

            # Check note-entity links
            link_issues = self._check_note_entity_links(conn, day)
            issues.extend(link_issues)

        finally:
            conn.close()

        # Count issues by severity
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        return IntegrityCheckResult(
            day=day.strftime("%Y-%m-%d"),
            passed=error_count == 0,
            total_notes=total_notes,
            total_entities=total_entities,
            total_edges=total_edges,
            issues=issues,
            error_count=error_count,
            warning_count=warning_count,
        )

    def _check_hourly_notes(
        self,
        conn,
        day: datetime,
        require_embeddings: bool,
    ) -> tuple[list[IntegrityIssue], int]:
        """Check hourly notes for the day."""
        issues = []
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT note_id, start_ts, file_path, json_payload, embedding_id
            FROM notes
            WHERE note_type = 'hour'
            AND start_ts >= ? AND start_ts <= ?
            ORDER BY start_ts
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        note_count = 0
        for row in cursor.fetchall():
            note_count += 1
            note_id = row["note_id"]
            file_path = Path(row["file_path"])

            # Check file exists
            if not file_path.exists():
                issues.append(
                    IntegrityIssue(
                        issue_type="missing_file",
                        entity_type="note",
                        entity_id=note_id,
                        description=f"Note file not found: {file_path}",
                        severity="error",
                    )
                )

            # Check JSON is valid
            try:
                json.loads(row["json_payload"])
            except json.JSONDecodeError:
                issues.append(
                    IntegrityIssue(
                        issue_type="invalid_json",
                        entity_type="note",
                        entity_id=note_id,
                        description="Note has invalid JSON payload",
                        severity="error",
                    )
                )

            # Check embedding exists
            if require_embeddings and not row["embedding_id"]:
                issues.append(
                    IntegrityIssue(
                        issue_type="missing_embedding",
                        entity_type="note",
                        entity_id=note_id,
                        description="Note is missing embedding",
                        severity="warning",
                    )
                )

        return issues, note_count

    def _check_daily_note(
        self,
        conn,
        day: datetime,
        require_daily_note: bool,
    ) -> tuple[list[IntegrityIssue], bool]:
        """Check daily note exists and is valid."""
        issues = []
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT note_id, file_path, json_payload
            FROM notes
            WHERE note_type = 'day'
            AND start_ts >= ? AND start_ts <= ?
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        row = cursor.fetchone()

        if row is None:
            if require_daily_note:
                # Check if there are hourly notes that should have a daily note
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM notes
                    WHERE note_type = 'hour'
                    AND start_ts >= ? AND start_ts <= ?
                    """,
                    (day_start.isoformat(), day_end.isoformat()),
                )
                hourly_count = cursor.fetchone()["count"]

                if hourly_count > 0:
                    issues.append(
                        IntegrityIssue(
                            issue_type="missing_daily_note",
                            entity_type="note",
                            entity_id=day.strftime("%Y-%m-%d"),
                            description=f"Daily note missing but {hourly_count} hourly notes exist",
                            severity="warning",
                        )
                    )
            return issues, False

        # Daily note exists - check it
        note_id = row["note_id"]
        file_path = Path(row["file_path"])

        # Check file exists
        if not file_path.exists():
            issues.append(
                IntegrityIssue(
                    issue_type="missing_file",
                    entity_type="note",
                    entity_id=note_id,
                    description=f"Daily note file not found: {file_path}",
                    severity="error",
                )
            )

        # Check JSON is valid
        try:
            json.loads(row["json_payload"])
        except json.JSONDecodeError:
            issues.append(
                IntegrityIssue(
                    issue_type="invalid_json",
                    entity_type="note",
                    entity_id=note_id,
                    description="Daily note has invalid JSON payload",
                    severity="error",
                )
            )

        return issues, True

    def _check_entities(
        self,
        conn,
        day: datetime,
    ) -> tuple[list[IntegrityIssue], int]:
        """Check entities referenced by notes from this day."""
        issues = []
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Get all entities linked to notes from this day
        cursor.execute(
            """
            SELECT DISTINCT e.entity_id, e.canonical_name, e.entity_type
            FROM entities e
            JOIN note_entities ne ON e.entity_id = ne.entity_id
            JOIN notes n ON ne.note_id = n.note_id
            WHERE n.start_ts >= ? AND n.start_ts <= ?
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        entity_count = 0
        for _row in cursor.fetchall():
            entity_count += 1
            # Entities are checked implicitly - if they exist in the join, they're valid

        return issues, entity_count

    def _check_edges(
        self,
        conn,
        day: datetime,
    ) -> tuple[list[IntegrityIssue], int]:
        """Check edges with evidence from this day's notes."""
        issues = []
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Get edges that reference this day's time range
        cursor.execute(
            """
            SELECT from_id, to_id, edge_type, evidence_note_ids
            FROM edges
            WHERE (start_ts >= ? AND start_ts <= ?)
            OR (end_ts >= ? AND end_ts <= ?)
            """,
            (
                day_start.isoformat(),
                day_end.isoformat(),
                day_start.isoformat(),
                day_end.isoformat(),
            ),
        )

        edge_count = 0
        for row in cursor.fetchall():
            edge_count += 1

            # Check that from and to entities exist
            for entity_id, entity_role in [
                (row["from_id"], "from"),
                (row["to_id"], "to"),
            ]:
                cursor.execute(
                    """
                    SELECT entity_id FROM entities WHERE entity_id = ?
                    """,
                    (entity_id,),
                )
                if cursor.fetchone() is None:
                    issues.append(
                        IntegrityIssue(
                            issue_type="orphaned_edge",
                            entity_type="edge",
                            entity_id=f"{row['from_id'][:8]}→{row['to_id'][:8]}",
                            description=f"Edge references non-existent {entity_role} entity: {entity_id}",
                            severity="error",
                        )
                    )

        return issues, edge_count

    def _check_note_entity_links(
        self,
        conn,
        day: datetime,
    ) -> list[IntegrityIssue]:
        """Check note-entity links for this day's notes."""
        issues = []
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Find orphaned links
        cursor.execute(
            """
            SELECT ne.note_id, ne.entity_id
            FROM note_entities ne
            JOIN notes n ON ne.note_id = n.note_id
            WHERE n.start_ts >= ? AND n.start_ts <= ?
            AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.entity_id = ne.entity_id)
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        for row in cursor.fetchall():
            issues.append(
                IntegrityIssue(
                    issue_type="orphaned_link",
                    entity_type="note_entity",
                    entity_id=f"{row['note_id'][:8]}↔{row['entity_id'][:8]}",
                    description=f"Note-entity link references non-existent entity: {row['entity_id']}",
                    severity="error",
                )
            )

        return issues

    def is_safe_to_delete(self, day: datetime) -> bool:
        """
        Quick check if it's safe to delete raw artifacts for a day.

        Args:
            day: The day to check

        Returns:
            True if safe to delete (no errors)
        """
        result = self.check_integrity(day, require_embeddings=False)
        return result.passed


if __name__ == "__main__":
    import fire

    def check(
        day: str | None = None,
        require_embeddings: bool = True,
        require_daily: bool = False,
        db_path: str | None = None,
    ):
        """
        Run integrity check for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            require_embeddings: Require all notes to have embeddings
            require_daily: Require daily note to exist
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        checker = IntegrityChecker(db_path=db_path)
        result = checker.check_integrity(
            target_day,
            require_embeddings=require_embeddings,
            require_daily_note=require_daily,
        )

        output = {
            "day": result.day,
            "passed": result.passed,
            "total_notes": result.total_notes,
            "total_entities": result.total_entities,
            "total_edges": result.total_edges,
            "errors": result.error_count,
            "warnings": result.warning_count,
        }

        if result.issues:
            output["issues"] = [
                {
                    "type": i.issue_type,
                    "entity": i.entity_type,
                    "id": i.entity_id[:20] + "..." if len(i.entity_id) > 20 else i.entity_id,
                    "severity": i.severity,
                    "description": i.description[:50] + "..."
                    if len(i.description) > 50
                    else i.description,
                }
                for i in result.issues
            ]

        return output

    def safe_to_delete(day: str | None = None, db_path: str | None = None):
        """
        Check if it's safe to delete raw artifacts for a day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        checker = IntegrityChecker(db_path=db_path)
        safe = checker.is_safe_to_delete(target_day)

        return {
            "day": target_day.strftime("%Y-%m-%d"),
            "safe_to_delete": safe,
        }

    fire.Fire(
        {
            "check": check,
            "safe": safe_to_delete,
        }
    )
