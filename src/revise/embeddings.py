"""
Embedding Refresh for Trace Daily Revision

Recomputes embeddings for revised notes to ensure search accuracy
after daily revision updates.

P6-06: Embedding refresh
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.summarize.embeddings import EmbeddingComputer, EmbeddingResult
from src.summarize.schemas import HourlySummarySchema

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingRefreshResult:
    """Result of refreshing embeddings for a day."""

    day: str
    total_notes: int
    refreshed_count: int
    failed_count: int
    skipped_count: int
    results: list[EmbeddingResult]


class EmbeddingRefresher:
    """
    Refreshes embeddings for revised notes.

    After daily revision updates note summaries and entities,
    embeddings must be recomputed to maintain search accuracy.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the refresher.

        Args:
            db_path: Path to SQLite database
            api_key: OpenAI API key
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.computer = EmbeddingComputer(api_key=api_key, db_path=self.db_path)

    def refresh_embeddings_for_day(
        self,
        day: datetime,
        force: bool = False,
    ) -> EmbeddingRefreshResult:
        """
        Refresh embeddings for all notes from a specific day.

        Args:
            day: The day to refresh embeddings for
            force: If True, refresh even if embedding already exists

        Returns:
            EmbeddingRefreshResult with status
        """
        results = []
        refreshed_count = 0
        failed_count = 0
        skipped_count = 0

        conn = get_connection(self.db_path)
        try:
            # Get all notes for the day (both hourly and daily)
            notes = self._get_notes_for_day(conn, day)

            for note in notes:
                note_id = note["note_id"]

                # Check if embedding already exists and we're not forcing
                if not force and note["embedding_id"]:
                    logger.debug(f"Skipping note {note_id}: embedding exists")
                    skipped_count += 1
                    continue

                # Recompute embedding
                result = self._refresh_single_note(note)
                results.append(result)

                if result.success:
                    refreshed_count += 1
                else:
                    failed_count += 1

        finally:
            conn.close()

        return EmbeddingRefreshResult(
            day=day.strftime("%Y-%m-%d"),
            total_notes=len(notes),
            refreshed_count=refreshed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            results=results,
        )

    def refresh_all_revised_notes(
        self,
        note_ids: list[str],
    ) -> EmbeddingRefreshResult:
        """
        Refresh embeddings for a specific list of note IDs.

        Args:
            note_ids: List of note IDs to refresh

        Returns:
            EmbeddingRefreshResult with status
        """
        results = []
        refreshed_count = 0
        failed_count = 0

        conn = get_connection(self.db_path)
        try:
            for note_id in note_ids:
                note = self._get_note_by_id(conn, note_id)

                if note is None:
                    logger.warning(f"Note not found: {note_id}")
                    results.append(
                        EmbeddingResult(
                            embedding_id="",
                            source_type="note",
                            source_id=note_id,
                            dimensions=0,
                            model="",
                            success=False,
                            error="Note not found",
                        )
                    )
                    failed_count += 1
                    continue

                result = self._refresh_single_note(note)
                results.append(result)

                if result.success:
                    refreshed_count += 1
                else:
                    failed_count += 1

        finally:
            conn.close()

        return EmbeddingRefreshResult(
            day=datetime.now().strftime("%Y-%m-%d"),
            total_notes=len(note_ids),
            refreshed_count=refreshed_count,
            failed_count=failed_count,
            skipped_count=0,
            results=results,
        )

    def _get_notes_for_day(
        self,
        conn,
        day: datetime,
    ) -> list[dict]:
        """
        Get all notes for a specific day.

        Args:
            conn: Database connection
            day: The day to get notes for

        Returns:
            List of note dicts
        """
        cursor = conn.cursor()

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        cursor.execute(
            """
            SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload, embedding_id
            FROM notes
            WHERE start_ts >= ? AND start_ts <= ?
            ORDER BY start_ts
            """,
            (day_start.isoformat(), day_end.isoformat()),
        )

        notes = []
        for row in cursor.fetchall():
            notes.append(
                {
                    "note_id": row["note_id"],
                    "note_type": row["note_type"],
                    "start_ts": datetime.fromisoformat(row["start_ts"]),
                    "end_ts": datetime.fromisoformat(row["end_ts"]),
                    "file_path": row["file_path"],
                    "json_payload": json.loads(row["json_payload"]),
                    "embedding_id": row["embedding_id"],
                }
            )

        return notes

    def _get_note_by_id(
        self,
        conn,
        note_id: str,
    ) -> dict | None:
        """
        Get a single note by ID.

        Args:
            conn: Database connection
            note_id: Note ID

        Returns:
            Note dict or None
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT note_id, note_type, start_ts, end_ts, file_path, json_payload, embedding_id
            FROM notes
            WHERE note_id = ?
            """,
            (note_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "note_id": row["note_id"],
            "note_type": row["note_type"],
            "start_ts": datetime.fromisoformat(row["start_ts"]),
            "end_ts": datetime.fromisoformat(row["end_ts"]),
            "file_path": row["file_path"],
            "json_payload": json.loads(row["json_payload"]),
            "embedding_id": row["embedding_id"],
        }

    def _refresh_single_note(self, note: dict) -> EmbeddingResult:
        """
        Refresh embedding for a single note.

        Args:
            note: Note dict

        Returns:
            EmbeddingResult
        """
        note_id = note["note_id"]
        payload = note["json_payload"]
        hour_start = note["start_ts"]

        try:
            # Create summary schema from payload
            # Handle both hourly and daily notes
            if note["note_type"] == "hour":
                summary = HourlySummarySchema.model_validate(payload)
                return self.computer.compute_for_note(note_id, summary, hour_start)
            else:
                # For daily notes, build embedding text differently
                return self._compute_daily_embedding(note_id, payload, hour_start)

        except Exception as e:
            logger.error(f"Failed to refresh embedding for note {note_id}: {e}")
            return EmbeddingResult(
                embedding_id="",
                source_type="note",
                source_id=note_id,
                dimensions=self.computer.dimensions,
                model=self.computer.model,
                success=False,
                error=str(e),
            )

    def _compute_daily_embedding(
        self,
        note_id: str,
        payload: dict,
        day_start: datetime,
    ) -> EmbeddingResult:
        """
        Compute embedding for a daily note.

        Args:
            note_id: Note ID
            payload: Daily revision payload
            day_start: Start of the day

        Returns:
            EmbeddingResult
        """
        # Build text representation for daily note
        parts = []

        # Time context
        parts.append(f"Date: {day_start.strftime('%A, %B %d, %Y')}")

        # Day summary
        if "day_summary" in payload:
            parts.append(f"Summary: {payload['day_summary']}")

        # Primary focus
        if payload.get("primary_focus"):
            parts.append(f"Primary focus: {payload['primary_focus']}")

        # Accomplishments
        if payload.get("accomplishments"):
            parts.append(f"Accomplishments: {', '.join(payload['accomplishments'][:5])}")

        # Top entities
        top = payload.get("top_entities", {})
        if top.get("topics"):
            topic_names = [t.get("name", "") for t in top["topics"][:5]]
            parts.append(f"Topics: {', '.join(topic_names)}")

        if top.get("apps"):
            app_names = [a.get("name", "") for a in top["apps"][:5]]
            parts.append(f"Apps: {', '.join(app_names)}")

        if top.get("domains"):
            domain_names = [d.get("name", "") for d in top["domains"][:5]]
            parts.append(f"Websites: {', '.join(domain_names)}")

        if top.get("media"):
            media_names = [m.get("name", "") for m in top["media"][:5]]
            parts.append(f"Media: {', '.join(media_names)}")

        # Patterns
        if payload.get("patterns"):
            parts.append(f"Patterns: {'; '.join(payload['patterns'][:3])}")

        # Location
        if payload.get("location_summary"):
            parts.append(f"Location: {payload['location_summary']}")

        text = "\n".join(parts)

        # Compute embedding using the computer's method
        try:
            embedding = self.computer._compute_embedding(text)
        except Exception as e:
            logger.error(f"Failed to compute embedding: {e}")
            return EmbeddingResult(
                embedding_id="",
                source_type="note",
                source_id=note_id,
                dimensions=self.computer.dimensions,
                model=self.computer.model,
                success=False,
                error=str(e),
            )

        # Store embedding
        from src.db.vectors import (
            delete_embedding,
            get_embedding_by_source,
            init_vector_table,
            load_sqlite_vec,
            store_embedding,
        )

        conn = get_connection(self.db_path)
        try:
            load_sqlite_vec(conn)
            init_vector_table(conn, self.computer.dimensions)

            # Check for existing embedding and delete if present
            existing = get_embedding_by_source(conn, "note", note_id)
            if existing:
                delete_embedding(conn, existing["embedding_id"])

            # Store new embedding
            embedding_id = store_embedding(
                conn,
                source_type="note",
                source_id=note_id,
                embedding=embedding,
                model_name=self.computer.model,
            )

            # Update notes table with embedding_id
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE notes
                SET embedding_id = ?, updated_ts = ?
                WHERE note_id = ?
                """,
                (embedding_id, datetime.now().isoformat(), note_id),
            )
            conn.commit()

            logger.info(f"Computed and stored embedding {embedding_id} for daily note {note_id}")

            return EmbeddingResult(
                embedding_id=embedding_id,
                source_type="note",
                source_id=note_id,
                dimensions=self.computer.dimensions,
                model=self.computer.model,
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            conn.rollback()
            return EmbeddingResult(
                embedding_id="",
                source_type="note",
                source_id=note_id,
                dimensions=self.computer.dimensions,
                model=self.computer.model,
                success=False,
                error=str(e),
            )
        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def refresh_day(day: str | None = None, force: bool = False, db_path: str | None = None):
        """
        Refresh embeddings for a specific day.

        Args:
            day: Date in YYYY-MM-DD format (defaults to today)
            force: Force refresh even if embedding exists
            db_path: Path to database
        """
        if day:
            target_day = datetime.strptime(day, "%Y-%m-%d")
        else:
            target_day = datetime.now()

        refresher = EmbeddingRefresher(db_path=db_path)
        result = refresher.refresh_embeddings_for_day(target_day, force)

        return {
            "day": result.day,
            "total_notes": result.total_notes,
            "refreshed": result.refreshed_count,
            "failed": result.failed_count,
            "skipped": result.skipped_count,
        }

    def refresh_notes(note_ids: str, db_path: str | None = None):
        """
        Refresh embeddings for specific note IDs.

        Args:
            note_ids: Comma-separated list of note IDs
            db_path: Path to database
        """
        ids = [n.strip() for n in note_ids.split(",")]

        refresher = EmbeddingRefresher(db_path=db_path)
        result = refresher.refresh_all_revised_notes(ids)

        return {
            "total": result.total_notes,
            "refreshed": result.refreshed_count,
            "failed": result.failed_count,
        }

    fire.Fire(
        {
            "day": refresh_day,
            "notes": refresh_notes,
        }
    )
