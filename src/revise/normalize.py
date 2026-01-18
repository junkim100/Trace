"""
Entity Normalization for Trace Daily Revision

Deduplicates and normalizes entity names across hourly notes.
Applies normalizations from LLM suggestions and updates the database.

P6-02: Entity normalization
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH
from src.db.migrations import get_connection
from src.revise.schemas import EntityNormalization

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """Result of an entity normalization operation."""

    original_name: str
    canonical_name: str
    entity_type: str
    entity_id: str
    merged_count: int  # Number of entities merged into this one


@dataclass
class NormalizationSummary:
    """Summary of all normalization operations for a day."""

    day: str
    total_normalizations: int
    total_entities_merged: int
    total_aliases_added: int
    normalizations: list[NormalizationResult]


class EntityNormalizer:
    """
    Normalizes entities across daily notes.

    Handles:
    - Applying LLM-suggested normalizations
    - Merging duplicate entities
    - Updating aliases
    - Maintaining referential integrity in note_entities
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the entity normalizer.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH

    def apply_normalizations(
        self,
        normalizations: list[EntityNormalization],
    ) -> NormalizationSummary:
        """
        Apply a list of entity normalizations to the database.

        For each normalization:
        1. Find or create the canonical entity
        2. Merge all variant entities into the canonical one
        3. Update note_entities to point to the canonical entity
        4. Add variants as aliases

        Args:
            normalizations: List of EntityNormalization from daily revision

        Returns:
            NormalizationSummary with results
        """
        results = []
        total_merged = 0
        total_aliases = 0

        conn = get_connection(self.db_path)
        try:
            for norm in normalizations:
                result = self._apply_single_normalization(conn, norm)
                if result:
                    results.append(result)
                    total_merged += result.merged_count
                    total_aliases += len(norm.original_names)

            conn.commit()

        except Exception as e:
            logger.error(f"Failed to apply normalizations: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

        return NormalizationSummary(
            day=datetime.now().strftime("%Y-%m-%d"),
            total_normalizations=len(results),
            total_entities_merged=total_merged,
            total_aliases_added=total_aliases,
            normalizations=results,
        )

    def _apply_single_normalization(
        self,
        conn,
        norm: EntityNormalization,
    ) -> NormalizationResult | None:
        """
        Apply a single normalization.

        Args:
            conn: Database connection
            norm: EntityNormalization to apply

        Returns:
            NormalizationResult or None if nothing to normalize
        """
        cursor = conn.cursor()

        # Normalize the canonical name
        canonical = self._normalize_name(norm.canonical_name)
        entity_type = norm.entity_type

        # Find or create the canonical entity
        cursor.execute(
            """
            SELECT entity_id, aliases
            FROM entities
            WHERE entity_type = ? AND canonical_name = ?
            """,
            (entity_type, canonical),
        )
        row = cursor.fetchone()

        if row:
            canonical_id = row["entity_id"]
            existing_aliases = json.loads(row["aliases"]) if row["aliases"] else []
        else:
            # Create the canonical entity
            import uuid

            canonical_id = str(uuid.uuid4())
            existing_aliases = []
            cursor.execute(
                """
                INSERT INTO entities (entity_id, entity_type, canonical_name, aliases, created_ts, updated_ts)
                VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (
                    canonical_id,
                    entity_type,
                    canonical,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            logger.debug(f"Created canonical entity {canonical_id}: {entity_type}/{canonical}")

        # Find all variant entities to merge
        merged_count = 0
        new_aliases = set(existing_aliases)

        for variant in norm.original_names:
            normalized_variant = self._normalize_name(variant)

            # Skip if this is the canonical name
            if normalized_variant == canonical:
                if variant != canonical:
                    new_aliases.add(variant)
                continue

            # Find the variant entity
            cursor.execute(
                """
                SELECT entity_id, aliases
                FROM entities
                WHERE entity_type = ? AND canonical_name = ?
                """,
                (entity_type, normalized_variant),
            )
            variant_row = cursor.fetchone()

            if variant_row and variant_row["entity_id"] != canonical_id:
                variant_id = variant_row["entity_id"]
                variant_aliases = (
                    json.loads(variant_row["aliases"]) if variant_row["aliases"] else []
                )

                # Add variant name and its aliases to canonical
                new_aliases.add(variant)
                new_aliases.add(normalized_variant)
                for alias in variant_aliases:
                    new_aliases.add(alias)

                # Merge note_entities references
                self._merge_note_entities(conn, variant_id, canonical_id)

                # Delete the variant entity
                cursor.execute(
                    """
                    DELETE FROM entities WHERE entity_id = ?
                    """,
                    (variant_id,),
                )
                logger.debug(f"Merged entity {variant_id} into {canonical_id}")
                merged_count += 1

            else:
                # Variant doesn't exist as separate entity, just add as alias
                new_aliases.add(variant)

        # Update aliases on canonical entity
        # Remove the canonical name from aliases
        new_aliases.discard(canonical)
        aliases_list = sorted(new_aliases)

        cursor.execute(
            """
            UPDATE entities
            SET aliases = ?, updated_ts = ?
            WHERE entity_id = ?
            """,
            (
                json.dumps(aliases_list) if aliases_list else None,
                datetime.now().isoformat(),
                canonical_id,
            ),
        )

        return NormalizationResult(
            original_name=norm.original_names[0] if norm.original_names else canonical,
            canonical_name=canonical,
            entity_type=entity_type,
            entity_id=canonical_id,
            merged_count=merged_count,
        )

    def _merge_note_entities(
        self,
        conn,
        from_entity_id: str,
        to_entity_id: str,
    ) -> int:
        """
        Merge note_entities references from one entity to another.

        Args:
            conn: Database connection
            from_entity_id: Entity being merged away
            to_entity_id: Entity to merge into

        Returns:
            Number of note_entities updated
        """
        cursor = conn.cursor()

        # Get all note_entities for the source entity
        cursor.execute(
            """
            SELECT note_id, strength, context
            FROM note_entities
            WHERE entity_id = ?
            """,
            (from_entity_id,),
        )
        source_links = cursor.fetchall()

        updated_count = 0
        for link in source_links:
            note_id = link["note_id"]
            strength = link["strength"]
            context = link["context"]

            # Check if target already has a link to this note
            cursor.execute(
                """
                SELECT strength, context
                FROM note_entities
                WHERE note_id = ? AND entity_id = ?
                """,
                (note_id, to_entity_id),
            )
            existing = cursor.fetchone()

            if existing:
                # Update with max strength and coalesce context
                new_strength = max(strength, existing["strength"])
                new_context = context or existing["context"]
                cursor.execute(
                    """
                    UPDATE note_entities
                    SET strength = ?, context = ?
                    WHERE note_id = ? AND entity_id = ?
                    """,
                    (new_strength, new_context, note_id, to_entity_id),
                )
            else:
                # Create new link to target
                cursor.execute(
                    """
                    INSERT INTO note_entities (note_id, entity_id, strength, context)
                    VALUES (?, ?, ?, ?)
                    """,
                    (note_id, to_entity_id, strength, context),
                )

            updated_count += 1

        # Delete all source note_entities
        cursor.execute(
            """
            DELETE FROM note_entities WHERE entity_id = ?
            """,
            (from_entity_id,),
        )

        return updated_count

    def _normalize_name(self, name: str) -> str:
        """
        Normalize an entity name for deduplication.

        - Lowercase
        - Trim whitespace
        - Collapse multiple spaces
        - Remove leading/trailing punctuation
        """
        # Lowercase
        normalized = name.lower()

        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        # Trim
        normalized = normalized.strip()

        # Remove leading/trailing punctuation (but keep internal)
        normalized = re.sub(r"^[^\w]+|[^\w]+$", "", normalized)

        return normalized

    def find_potential_duplicates(
        self,
        entity_type: str | None = None,
        similarity_threshold: float = 0.8,
    ) -> list[list[str]]:
        """
        Find potential duplicate entities that might need normalization.

        Uses simple string similarity to find candidates.

        Args:
            entity_type: Optional filter by entity type
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of entity name groups that might be duplicates
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            if entity_type:
                cursor.execute(
                    """
                    SELECT entity_id, canonical_name, aliases
                    FROM entities
                    WHERE entity_type = ?
                    ORDER BY canonical_name
                    """,
                    (entity_type,),
                )
            else:
                cursor.execute(
                    """
                    SELECT entity_id, entity_type, canonical_name, aliases
                    FROM entities
                    ORDER BY entity_type, canonical_name
                    """
                )

            entities = []
            for row in cursor.fetchall():
                names = [row["canonical_name"]]
                if row["aliases"]:
                    names.extend(json.loads(row["aliases"]))
                entities.append(
                    {
                        "entity_id": row["entity_id"],
                        "canonical_name": row["canonical_name"],
                        "all_names": names,
                    }
                )

            # Find potential duplicates using simple string matching
            duplicates = []
            processed = set()

            for i, e1 in enumerate(entities):
                if e1["entity_id"] in processed:
                    continue

                group = [e1["canonical_name"]]

                for _j, e2 in enumerate(entities[i + 1 :], i + 1):
                    if e2["entity_id"] in processed:
                        continue

                    # Check if any names are similar
                    for n1 in e1["all_names"]:
                        for n2 in e2["all_names"]:
                            if self._string_similarity(n1, n2) >= similarity_threshold:
                                group.append(e2["canonical_name"])
                                processed.add(e2["entity_id"])
                                break
                        else:
                            continue
                        break

                if len(group) > 1:
                    duplicates.append(group)
                    processed.add(e1["entity_id"])

            return duplicates

        finally:
            conn.close()

    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate simple string similarity between two strings.

        Uses normalized Levenshtein distance.
        """
        s1 = s1.lower()
        s2 = s2.lower()

        if s1 == s2:
            return 1.0

        # Check if one contains the other
        if s1 in s2 or s2 in s1:
            return 0.9

        # Simple character overlap
        set1 = set(s1.replace(" ", ""))
        set2 = set(s2.replace(" ", ""))
        intersection = set1 & set2
        union = set1 | set2

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def get_entity_by_name(
        self,
        name: str,
        entity_type: str,
    ) -> dict | None:
        """
        Get an entity by name (checking canonical name and aliases).

        Args:
            name: Entity name to search for
            entity_type: Entity type

        Returns:
            Entity dict or None
        """
        normalized = self._normalize_name(name)

        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # First check canonical name
            cursor.execute(
                """
                SELECT entity_id, canonical_name, aliases, created_ts, updated_ts
                FROM entities
                WHERE entity_type = ? AND canonical_name = ?
                """,
                (entity_type, normalized),
            )
            row = cursor.fetchone()

            if row:
                return {
                    "entity_id": row["entity_id"],
                    "canonical_name": row["canonical_name"],
                    "aliases": json.loads(row["aliases"]) if row["aliases"] else [],
                    "created_ts": row["created_ts"],
                    "updated_ts": row["updated_ts"],
                }

            # Check aliases (this is less efficient but handles edge cases)
            cursor.execute(
                """
                SELECT entity_id, canonical_name, aliases, created_ts, updated_ts
                FROM entities
                WHERE entity_type = ? AND aliases LIKE ?
                """,
                (entity_type, f'%"{name}"%'),
            )
            row = cursor.fetchone()

            if row:
                return {
                    "entity_id": row["entity_id"],
                    "canonical_name": row["canonical_name"],
                    "aliases": json.loads(row["aliases"]) if row["aliases"] else [],
                    "created_ts": row["created_ts"],
                    "updated_ts": row["updated_ts"],
                }

            return None

        finally:
            conn.close()


if __name__ == "__main__":
    import fire

    def apply(normalizations_json: str):
        """
        Apply normalizations from a JSON file.

        Args:
            normalizations_json: Path to JSON file with normalizations
        """
        with open(normalizations_json) as f:
            data = json.load(f)

        normalizations = [EntityNormalization.model_validate(n) for n in data]

        normalizer = EntityNormalizer()
        result = normalizer.apply_normalizations(normalizations)

        return {
            "total_normalizations": result.total_normalizations,
            "total_entities_merged": result.total_entities_merged,
            "total_aliases_added": result.total_aliases_added,
            "normalizations": [
                {
                    "original": n.original_name,
                    "canonical": n.canonical_name,
                    "merged": n.merged_count,
                }
                for n in result.normalizations
            ],
        }

    def find_duplicates(entity_type: str | None = None, threshold: float = 0.8):
        """Find potential duplicate entities."""
        normalizer = EntityNormalizer()
        duplicates = normalizer.find_potential_duplicates(entity_type, threshold)

        return {"potential_duplicates": duplicates, "count": len(duplicates)}

    def demo():
        """Demo normalization with sample data."""
        normalizations = [
            EntityNormalization(
                original_names=["VS Code", "VSCode", "Visual Studio Code"],
                canonical_name="visual studio code",
                entity_type="app",
                confidence=0.95,
            ),
            EntityNormalization(
                original_names=["Python 3", "Python3", "python"],
                canonical_name="python",
                entity_type="topic",
                confidence=0.9,
            ),
        ]

        print("Sample normalizations:")
        for n in normalizations:
            print(f"  {n.original_names} -> {n.canonical_name} ({n.entity_type})")

        return {
            "message": "Demo - no changes made to database",
            "normalizations_count": len(normalizations),
        }

    fire.Fire(
        {
            "apply": apply,
            "find-duplicates": find_duplicates,
            "demo": demo,
        }
    )
