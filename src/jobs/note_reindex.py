"""
Note Re-indexer for Trace

Scans the notes directory for existing markdown files and indexes them
into the SQLite database. This is useful when:
- Database was corrupted/recreated
- Notes were manually created
- Migrating from an older version

The re-indexer:
1. Finds all .md files in the notes directory
2. Parses YAML frontmatter for metadata
3. Upserts note records into the database
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.paths import DB_PATH, NOTES_DIR
from src.db.migrations import get_connection
from src.summarize.render import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class ReindexResult:
    """Result of note re-indexing operation."""

    files_scanned: int = 0
    notes_indexed: int = 0
    notes_skipped: int = 0
    notes_failed: int = 0
    indexed_details: list[dict] = field(default_factory=list)
    failed_details: list[dict] = field(default_factory=list)


class NoteReindexer:
    """
    Re-indexes note files from disk into the database.

    This handles cases where:
    - Database was recreated/corrupted
    - Notes were manually created on disk
    - Migration from older version
    """

    def __init__(self, db_path: Path | str | None = None, notes_dir: Path | str | None = None):
        """
        Initialize the re-indexer.

        Args:
            db_path: Path to SQLite database
            notes_dir: Path to notes directory
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.notes_dir = Path(notes_dir) if notes_dir else NOTES_DIR

    def find_note_files(self) -> list[Path]:
        """
        Find all note markdown files in the notes directory.

        Returns:
            List of paths to note files
        """
        if not self.notes_dir.exists():
            logger.warning(f"Notes directory does not exist: {self.notes_dir}")
            return []

        # Find all .md files matching our naming patterns
        hourly_files = list(self.notes_dir.glob("**/hour-*.md"))
        daily_files = list(self.notes_dir.glob("**/day-*.md"))

        return sorted(hourly_files + daily_files)

    def parse_note_file(self, file_path: Path) -> dict | None:
        """
        Parse a note file and extract metadata.

        Args:
            file_path: Path to the note markdown file

        Returns:
            Dict with note metadata or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)

            if not frontmatter:
                logger.warning(f"No frontmatter in {file_path}")
                return None

            # Required fields
            note_id = frontmatter.get("id")
            note_type = frontmatter.get("type")
            start_time = frontmatter.get("start_time")
            end_time = frontmatter.get("end_time")

            if not all([note_id, note_type, start_time, end_time]):
                logger.warning(f"Missing required fields in {file_path}")
                return None

            return {
                "note_id": note_id,
                "note_type": note_type,
                "start_ts": start_time,
                "end_ts": end_time,
                "file_path": str(file_path),
                "frontmatter": frontmatter,
                "body": body,
            }

        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return None

    def index_note(self, note_data: dict) -> bool:
        """
        Index a single note into the database.

        Args:
            note_data: Dict with note metadata from parse_note_file

        Returns:
            True if indexed successfully
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.cursor()

            # Check if note already exists
            cursor.execute(
                "SELECT note_id FROM notes WHERE note_id = ?",
                (note_data["note_id"],),
            )
            existing = cursor.fetchone()

            now = datetime.now().isoformat()

            # Build a minimal json_payload from frontmatter for recovery purposes
            frontmatter = note_data.get("frontmatter", {})
            json_payload = json.dumps(
                {
                    "summary": note_data.get("body", "").split("\n\n")[0][:500]
                    if note_data.get("body")
                    else "",
                    "categories": frontmatter.get("categories", []),
                    "entities": frontmatter.get("entities", []),
                    "location": frontmatter.get("location"),
                    "schema_version": frontmatter.get("schema_version", 3),
                }
            )

            if existing:
                # Update existing record
                cursor.execute(
                    """
                    UPDATE notes
                    SET file_path = ?, updated_ts = ?
                    WHERE note_id = ?
                    """,
                    (note_data["file_path"], now, note_data["note_id"]),
                )
                logger.debug(f"Updated existing note {note_data['note_id']}")
            else:
                # Insert new record
                cursor.execute(
                    """
                    INSERT INTO notes
                    (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note_data["note_id"],
                        note_data["note_type"],
                        note_data["start_ts"],
                        note_data["end_ts"],
                        note_data["file_path"],
                        json_payload,
                        now,
                        now,
                    ),
                )
                logger.debug(f"Indexed new note {note_data['note_id']}")

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to index note {note_data['note_id']}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def reindex_all(self) -> ReindexResult:
        """
        Find all note files and index them into the database.

        Returns:
            ReindexResult with statistics
        """
        result = ReindexResult()

        # Find all note files
        note_files = self.find_note_files()
        result.files_scanned = len(note_files)

        if not note_files:
            logger.info("No note files found to index")
            return result

        logger.info(f"Found {len(note_files)} note files to index")

        for file_path in note_files:
            # Parse the file
            note_data = self.parse_note_file(file_path)
            if not note_data:
                result.notes_skipped += 1
                continue

            # Index into database
            success = self.index_note(note_data)

            if success:
                result.notes_indexed += 1
                result.indexed_details.append(
                    {
                        "note_id": note_data["note_id"],
                        "note_type": note_data["note_type"],
                        "file_path": str(file_path),
                    }
                )
            else:
                result.notes_failed += 1
                result.failed_details.append(
                    {
                        "note_id": note_data["note_id"],
                        "file_path": str(file_path),
                    }
                )

        logger.info(
            f"Re-indexing complete: {result.notes_indexed} indexed, "
            f"{result.notes_skipped} skipped, {result.notes_failed} failed"
        )

        return result


if __name__ == "__main__":
    import fire

    logging.basicConfig(level=logging.INFO)

    def status(db_path: str | None = None, notes_dir: str | None = None):
        """
        Check how many note files exist vs indexed in database.

        Args:
            db_path: Path to database
            notes_dir: Path to notes directory

        Returns:
            Dict with status info
        """
        reindexer = NoteReindexer(db_path=db_path, notes_dir=notes_dir)
        note_files = reindexer.find_note_files()

        conn = get_connection(reindexer.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM notes")
            row = cursor.fetchone()
            db_count = row["count"] if row else 0
        finally:
            conn.close()

        return {
            "files_on_disk": len(note_files),
            "notes_in_database": db_count,
            "needs_reindex": len(note_files) > db_count,
        }

    def reindex(db_path: str | None = None, notes_dir: str | None = None):
        """
        Re-index all note files from disk into the database.

        Args:
            db_path: Path to database
            notes_dir: Path to notes directory

        Returns:
            Dict with reindex statistics
        """
        reindexer = NoteReindexer(db_path=db_path, notes_dir=notes_dir)
        result = reindexer.reindex_all()

        return {
            "files_scanned": result.files_scanned,
            "notes_indexed": result.notes_indexed,
            "notes_skipped": result.notes_skipped,
            "notes_failed": result.notes_failed,
        }

    fire.Fire({"status": status, "reindex": reindex})
