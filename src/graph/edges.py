"""
Graph Edge Builder for Trace

Creates and manages typed edges in the relationship graph.
Edges represent relationships between entities with weights and evidence.

Edge types (from schema):
- ABOUT_TOPIC: Entity relates to a topic/concept
- WATCHED: User watched this video/media
- LISTENED_TO: User listened to this track/podcast
- USED_APP: Topic/project used this application
- VISITED_DOMAIN: Topic/project visited this domain
- DOC_REFERENCE: Document references another entity
- CO_OCCURRED_WITH: Entities appeared together
- STUDIED_WHILE: Learning activity paired with another activity

P6-05: Graph edge builder
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.revise.schemas import GraphEdgeItem

logger = logging.getLogger(__name__)

# Valid edge types
EDGE_TYPES = {
    "ABOUT_TOPIC",
    "WATCHED",
    "LISTENED_TO",
    "USED_APP",
    "VISITED_DOMAIN",
    "DOC_REFERENCE",
    "CO_OCCURRED_WITH",
    "STUDIED_WHILE",
}


@dataclass
class StoredEdge:
    """An edge stored in the database."""

    from_id: str
    to_id: str
    edge_type: str
    weight: float
    start_ts: datetime | None
    end_ts: datetime | None
    evidence_note_ids: list[str]
    created_ts: datetime


@dataclass
class EdgeCreationResult:
    """Result of creating an edge."""

    from_entity: str
    to_entity: str
    edge_type: str
    created: bool  # True if new, False if updated
    weight: float
    error: str | None = None


@dataclass
class EdgeBuildResult:
    """Result of building edges for a day."""

    day: str
    total_edges: int
    created_count: int
    updated_count: int
    failed_count: int
    edges: list[EdgeCreationResult]


class GraphEdgeBuilder:
    """
    Builds and manages graph edges between entities.

    Handles:
    - Creating edges from daily revision suggestions
    - Updating edge weights (accumulative)
    - Managing evidence links
    - Querying edges by entity or type
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the edge builder.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def build_edges_from_revision(
        self,
        edges: list[GraphEdgeItem],
        day: datetime,
        note_ids: list[str] | None = None,
    ) -> EdgeBuildResult:
        """
        Build graph edges from daily revision output.

        Args:
            edges: List of GraphEdgeItem from daily revision
            day: The day these edges are from
            note_ids: Optional list of note IDs as evidence

        Returns:
            EdgeBuildResult with status
        """
        results = []
        created_count = 0
        updated_count = 0
        failed_count = 0

        conn = get_connection(self.db_path)
        try:
            for edge in edges:
                result = self._create_or_update_edge(conn, edge, day, note_ids)
                results.append(result)

                if result.error:
                    failed_count += 1
                elif result.created:
                    created_count += 1
                else:
                    updated_count += 1

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to build edges: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

        return EdgeBuildResult(
            day=day.strftime("%Y-%m-%d"),
            total_edges=len(edges),
            created_count=created_count,
            updated_count=updated_count,
            failed_count=failed_count,
            edges=results,
        )

    def _create_or_update_edge(
        self,
        conn,
        edge: GraphEdgeItem,
        day: datetime,
        note_ids: list[str] | None,
    ) -> EdgeCreationResult:
        """
        Create or update a single edge.

        Args:
            conn: Database connection
            edge: GraphEdgeItem to create
            day: The day this edge is from
            note_ids: Optional evidence note IDs

        Returns:
            EdgeCreationResult
        """
        cursor = conn.cursor()

        try:
            # Get entity IDs for from and to entities
            from_id = self._get_entity_id(conn, edge.from_entity, edge.from_type)
            to_id = self._get_entity_id(conn, edge.to_entity, edge.to_type)

            if from_id is None:
                return EdgeCreationResult(
                    from_entity=edge.from_entity,
                    to_entity=edge.to_entity,
                    edge_type=edge.edge_type,
                    created=False,
                    weight=0,
                    error=f"From entity not found: {edge.from_entity}",
                )

            if to_id is None:
                return EdgeCreationResult(
                    from_entity=edge.from_entity,
                    to_entity=edge.to_entity,
                    edge_type=edge.edge_type,
                    created=False,
                    weight=0,
                    error=f"To entity not found: {edge.to_entity}",
                )

            # Validate edge type
            edge_type = edge.edge_type.upper()
            if edge_type not in EDGE_TYPES:
                edge_type = "CO_OCCURRED_WITH"

            # Check for existing edge
            cursor.execute(
                """
                SELECT weight, evidence_note_ids, start_ts, end_ts
                FROM edges
                WHERE from_id = ? AND to_id = ? AND edge_type = ?
                """,
                (from_id, to_id, edge_type),
            )
            existing = cursor.fetchone()

            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59)

            if existing:
                # Update existing edge
                old_weight = existing["weight"]
                old_evidence = (
                    json.loads(existing["evidence_note_ids"])
                    if existing["evidence_note_ids"]
                    else []
                )

                # Combine weights (use max or rolling average)
                new_weight = max(old_weight, edge.weight)

                # Merge evidence note IDs
                new_evidence = list(set(old_evidence + (note_ids or [])))

                # Expand time range if needed
                new_start = existing["start_ts"]
                new_end = existing["end_ts"]
                if new_start is None or day_start.isoformat() < new_start:
                    new_start = day_start.isoformat()
                if new_end is None or day_end.isoformat() > new_end:
                    new_end = day_end.isoformat()

                cursor.execute(
                    """
                    UPDATE edges
                    SET weight = ?, evidence_note_ids = ?, start_ts = ?, end_ts = ?
                    WHERE from_id = ? AND to_id = ? AND edge_type = ?
                    """,
                    (
                        new_weight,
                        json.dumps(new_evidence) if new_evidence else None,
                        new_start,
                        new_end,
                        from_id,
                        to_id,
                        edge_type,
                    ),
                )

                logger.debug(
                    f"Updated edge {from_id[:8]}->{to_id[:8]} ({edge_type}): "
                    f"{old_weight:.2f} -> {new_weight:.2f}"
                )

                return EdgeCreationResult(
                    from_entity=edge.from_entity,
                    to_entity=edge.to_entity,
                    edge_type=edge_type,
                    created=False,
                    weight=new_weight,
                )

            else:
                # Create new edge
                cursor.execute(
                    """
                    INSERT INTO edges
                    (from_id, to_id, edge_type, weight, start_ts, end_ts, evidence_note_ids, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        from_id,
                        to_id,
                        edge_type,
                        edge.weight,
                        day_start.isoformat(),
                        day_end.isoformat(),
                        json.dumps(note_ids) if note_ids else None,
                        datetime.now().isoformat(),
                    ),
                )

                logger.debug(
                    f"Created edge {from_id[:8]}->{to_id[:8]} ({edge_type}): {edge.weight:.2f}"
                )

                return EdgeCreationResult(
                    from_entity=edge.from_entity,
                    to_entity=edge.to_entity,
                    edge_type=edge_type,
                    created=True,
                    weight=edge.weight,
                )

        except Exception as e:
            logger.error(f"Failed to create edge: {e}")
            return EdgeCreationResult(
                from_entity=edge.from_entity,
                to_entity=edge.to_entity,
                edge_type=edge.edge_type,
                created=False,
                weight=0,
                error=str(e),
            )

    def _get_entity_id(
        self,
        conn,
        name: str,
        entity_type: str,
    ) -> str | None:
        """
        Get entity ID by name and type.

        Checks canonical name first, then aliases.

        Args:
            conn: Database connection
            name: Entity name
            entity_type: Entity type

        Returns:
            Entity ID or None
        """
        cursor = conn.cursor()

        # Normalize name
        normalized = name.lower().strip()

        # Check canonical name
        cursor.execute(
            """
            SELECT entity_id
            FROM entities
            WHERE entity_type = ? AND LOWER(canonical_name) = ?
            """,
            (entity_type, normalized),
        )
        row = cursor.fetchone()

        if row:
            return row["entity_id"]

        # Check aliases
        cursor.execute(
            """
            SELECT entity_id, aliases
            FROM entities
            WHERE entity_type = ?
            """,
            (entity_type,),
        )

        for row in cursor.fetchall():
            if row["aliases"]:
                aliases = json.loads(row["aliases"])
                for alias in aliases:
                    if alias.lower() == normalized:
                        return row["entity_id"]

        return None

    def get_edges_for_entity(
        self,
        entity_id: str,
        direction: str = "both",
        edge_type: str | None = None,
    ) -> list[StoredEdge]:
        """
        Get all edges connected to an entity.

        Args:
            entity_id: Entity ID
            direction: "from", "to", or "both"
            edge_type: Optional filter by edge type

        Returns:
            List of StoredEdge
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            edges = []

            if direction in ("from", "both"):
                if edge_type:
                    cursor.execute(
                        """
                        SELECT from_id, to_id, edge_type, weight, start_ts, end_ts,
                               evidence_note_ids, created_ts
                        FROM edges
                        WHERE from_id = ? AND edge_type = ?
                        """,
                        (entity_id, edge_type),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT from_id, to_id, edge_type, weight, start_ts, end_ts,
                               evidence_note_ids, created_ts
                        FROM edges
                        WHERE from_id = ?
                        """,
                        (entity_id,),
                    )

                for row in cursor.fetchall():
                    edges.append(self._row_to_stored_edge(row))

            if direction in ("to", "both"):
                if edge_type:
                    cursor.execute(
                        """
                        SELECT from_id, to_id, edge_type, weight, start_ts, end_ts,
                               evidence_note_ids, created_ts
                        FROM edges
                        WHERE to_id = ? AND edge_type = ?
                        """,
                        (entity_id, edge_type),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT from_id, to_id, edge_type, weight, start_ts, end_ts,
                               evidence_note_ids, created_ts
                        FROM edges
                        WHERE to_id = ?
                        """,
                        (entity_id,),
                    )

                for row in cursor.fetchall():
                    edge = self._row_to_stored_edge(row)
                    # Avoid duplicates for "both" direction
                    if not any(
                        e.from_id == edge.from_id
                        and e.to_id == edge.to_id
                        and e.edge_type == edge.edge_type
                        for e in edges
                    ):
                        edges.append(edge)

            return edges

        finally:
            conn.close()

    def get_edges_by_type(
        self,
        edge_type: str,
        limit: int = 100,
    ) -> list[StoredEdge]:
        """
        Get edges by type.

        Args:
            edge_type: Edge type to filter by
            limit: Maximum results

        Returns:
            List of StoredEdge
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT from_id, to_id, edge_type, weight, start_ts, end_ts,
                       evidence_note_ids, created_ts
                FROM edges
                WHERE edge_type = ?
                ORDER BY weight DESC
                LIMIT ?
                """,
                (edge_type, limit),
            )

            return [self._row_to_stored_edge(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_edge_counts(self) -> dict[str, int]:
        """Get count of edges by type."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT edge_type, COUNT(*) as count
                FROM edges
                GROUP BY edge_type
                """
            )

            counts = {}
            for row in cursor.fetchall():
                counts[row["edge_type"]] = row["count"]

            return counts

        finally:
            conn.close()

    def _row_to_stored_edge(self, row) -> StoredEdge:
        """Convert a database row to StoredEdge."""
        return StoredEdge(
            from_id=row["from_id"],
            to_id=row["to_id"],
            edge_type=row["edge_type"],
            weight=row["weight"],
            start_ts=datetime.fromisoformat(row["start_ts"]) if row["start_ts"] else None,
            end_ts=datetime.fromisoformat(row["end_ts"]) if row["end_ts"] else None,
            evidence_note_ids=(
                json.loads(row["evidence_note_ids"]) if row["evidence_note_ids"] else []
            ),
            created_ts=datetime.fromisoformat(row["created_ts"]),
        )


if __name__ == "__main__":
    import fire

    def build_demo():
        """Build demo edges."""
        edges = [
            GraphEdgeItem(
                from_entity="Python",
                from_type="topic",
                to_entity="Visual Studio Code",
                to_type="app",
                edge_type="USED_APP",
                weight=0.9,
                evidence="Wrote Python code in VS Code",
            ),
            GraphEdgeItem(
                from_entity="async programming",
                from_type="topic",
                to_entity="docs.python.org",
                to_type="domain",
                edge_type="VISITED_DOMAIN",
                weight=0.85,
                evidence="Read asyncio documentation",
            ),
            GraphEdgeItem(
                from_entity="Lofi Girl",
                from_type="artist",
                to_entity="coding",
                to_type="topic",
                edge_type="STUDIED_WHILE",
                weight=0.7,
                evidence="Listened to music while coding",
            ),
        ]

        print("Demo edges:")
        for e in edges:
            print(f"  {e.from_entity} --[{e.edge_type}]--> {e.to_entity} (weight: {e.weight})")

        return {"edge_count": len(edges)}

    def counts(db_path: str | None = None):
        """Get edge counts by type."""
        builder = GraphEdgeBuilder(db_path=db_path)
        return builder.get_edge_counts()

    def list_edges(edge_type: str, limit: int = 20, db_path: str | None = None):
        """List edges by type."""
        builder = GraphEdgeBuilder(db_path=db_path)
        edges = builder.get_edges_by_type(edge_type, limit)

        return [
            {
                "from": e.from_id[:8] + "...",
                "to": e.to_id[:8] + "...",
                "type": e.edge_type,
                "weight": f"{e.weight:.2f}",
            }
            for e in edges
        ]

    fire.Fire(
        {
            "demo": build_demo,
            "counts": counts,
            "list": list_edges,
        }
    )
