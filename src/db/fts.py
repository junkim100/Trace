"""
FTS5 Full-Text Search for Trace

Provides full-text search capabilities using SQLite FTS5 extension.
Used in combination with vector search for hybrid retrieval.
"""

import logging
from sqlite3 import Connection

logger = logging.getLogger(__name__)


def init_fts_table(conn: Connection) -> None:
    """
    Initialize the FTS5 table if it doesn't exist.

    Args:
        conn: SQLite database connection
    """
    cursor = conn.cursor()

    # Check if FTS table exists
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='notes_fts'
        """
    )

    if cursor.fetchone() is None:
        # Create FTS5 table
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                summary,
                categories,
                entities_text,
                content='',
                tokenize='porter unicode61'
            )
            """
        )
        conn.commit()
        logger.info("Created notes_fts table")


def index_note_fts(
    conn: Connection,
    rowid: int,
    summary: str,
    categories: list[str] | None = None,
    entities: list[dict] | None = None,
) -> None:
    """
    Add or update a note in the FTS index.

    Args:
        conn: SQLite database connection
        rowid: The rowid of the note in the notes table
        summary: Note summary text
        categories: List of category strings
        entities: List of entity dictionaries with 'name' keys
    """
    cursor = conn.cursor()

    # Convert categories and entities to searchable text
    categories_text = " ".join(categories) if categories else ""
    entities_text = " ".join(e.get("name", "") for e in (entities or []) if e.get("name"))

    # Delete existing entry if present
    cursor.execute("DELETE FROM notes_fts WHERE rowid = ?", (rowid,))

    # Insert new entry
    cursor.execute(
        """
        INSERT INTO notes_fts(rowid, summary, categories, entities_text)
        VALUES (?, ?, ?, ?)
        """,
        (rowid, summary, categories_text, entities_text),
    )

    conn.commit()


def delete_note_fts(conn: Connection, rowid: int) -> None:
    """
    Remove a note from the FTS index.

    Args:
        conn: SQLite database connection
        rowid: The rowid of the note to remove
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes_fts WHERE rowid = ?", (rowid,))
    conn.commit()


def search_fts(
    conn: Connection,
    query: str,
    limit: int = 50,
) -> list[dict]:
    """
    Perform FTS5 search with BM25 ranking.

    Args:
        conn: SQLite database connection
        query: Search query (supports FTS5 syntax)
        limit: Maximum number of results

    Returns:
        List of dicts with 'rowid', 'note_id', 'bm25_score', 'fts_score'
    """
    cursor = conn.cursor()

    # Escape special FTS5 characters and prepare query
    # FTS5 uses MATCH for full-text queries
    safe_query = _prepare_fts_query(query)

    if not safe_query:
        return []

    try:
        # bm25() returns negative values where lower (more negative) = better match
        # We join with notes table to get note_id
        cursor.execute(
            """
            SELECT
                notes_fts.rowid,
                n.note_id,
                bm25(notes_fts) as bm25_score
            FROM notes_fts
            JOIN notes n ON notes_fts.rowid = n.rowid
            WHERE notes_fts MATCH ?
            ORDER BY bm25_score
            LIMIT ?
            """,
            (safe_query, limit),
        )

        results = []
        for row in cursor.fetchall():
            bm25_score = row[2]
            # Normalize BM25 score to [0, 1] range
            # BM25 returns negative values, lower = better
            # Convert: fts_score = 1 / (1 + abs(bm25))
            fts_score = 1.0 / (1.0 + abs(bm25_score))

            results.append(
                {
                    "rowid": row[0],
                    "note_id": row[1],
                    "bm25_score": bm25_score,
                    "fts_score": fts_score,
                }
            )

        return results

    except Exception as e:
        logger.warning(f"FTS search failed for query '{query}': {e}")
        return []


def _prepare_fts_query(query: str) -> str:
    """
    Prepare a query string for FTS5 MATCH.

    Handles:
    - Removes FTS5 special operators for simple queries
    - Wraps multi-word queries appropriately

    Args:
        query: Raw search query

    Returns:
        FTS5-safe query string
    """
    if not query or not query.strip():
        return ""

    # Remove or escape FTS5 special characters for simple queries
    # Special chars: AND, OR, NOT, *, ^, NEAR, "
    query = query.strip()

    # For simple queries, just use the words
    # FTS5 will match any word by default (implicit OR)
    words = query.split()

    if not words:
        return ""

    # Quote each word to prevent interpretation as operators
    # and combine with implicit OR
    safe_words = []
    for word in words:
        # Remove special characters that could cause issues
        clean_word = "".join(c for c in word if c.isalnum() or c in "-_")
        if clean_word:
            safe_words.append(f'"{clean_word}"')

    if not safe_words:
        return ""

    # Join with OR for broader matching
    return " OR ".join(safe_words)


def rebuild_fts_index(conn: Connection) -> int:
    """
    Rebuild the entire FTS index from the notes table.

    Useful after bulk imports or to fix index corruption.

    Args:
        conn: SQLite database connection

    Returns:
        Number of notes indexed
    """
    cursor = conn.cursor()

    # Clear existing index
    cursor.execute("DELETE FROM notes_fts")

    # Repopulate from notes
    cursor.execute(
        """
        INSERT INTO notes_fts(rowid, summary, categories, entities_text)
        SELECT
            n.rowid,
            COALESCE(json_extract(n.json_payload, '$.summary'), ''),
            COALESCE(
                (SELECT GROUP_CONCAT(value, ' ')
                 FROM json_each(json_extract(n.json_payload, '$.categories'))),
                ''
            ),
            COALESCE(
                (SELECT GROUP_CONCAT(json_extract(value, '$.name'), ' ')
                 FROM json_each(json_extract(n.json_payload, '$.entities'))),
                ''
            )
        FROM notes n
        WHERE n.json_payload IS NOT NULL
        """
    )

    count = cursor.rowcount
    conn.commit()

    logger.info(f"Rebuilt FTS index with {count} notes")
    return count


def get_fts_stats(conn: Connection) -> dict:
    """
    Get statistics about the FTS index.

    Args:
        conn: SQLite database connection

    Returns:
        Dict with index statistics
    """
    cursor = conn.cursor()

    # Count entries
    cursor.execute("SELECT COUNT(*) FROM notes_fts")
    count = cursor.fetchone()[0]

    # Get total notes for comparison
    cursor.execute("SELECT COUNT(*) FROM notes")
    total_notes = cursor.fetchone()[0]

    return {
        "fts_entries": count,
        "total_notes": total_notes,
        "coverage": count / total_notes if total_notes > 0 else 0,
    }
