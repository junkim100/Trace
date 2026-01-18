"""
Vector Storage and Search with sqlite-vec

This module provides sqlite-vec integration for storing and querying
1536-dimensional embeddings used by the Trace application.
"""

import logging
import sqlite3
import struct
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import sqlite_vec

logger = logging.getLogger(__name__)

# Default dimensions for OpenAI text-embedding-3-small
DEFAULT_DIMENSIONS = 1536

# Virtual table name for embeddings
VEC_TABLE_NAME = "vec_embeddings"


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """
    Load the sqlite-vec extension into a database connection.

    Args:
        conn: SQLite database connection
    """
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    logger.debug("sqlite-vec extension loaded successfully")


def serialize_float32(vector: list[float]) -> bytes:
    """
    Serialize a list of floats to a compact binary format for sqlite-vec.

    Args:
        vector: List of float values

    Returns:
        Bytes representing the vector in float32 format
    """
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_float32(data: bytes) -> list[float]:
    """
    Deserialize a binary vector back to a list of floats.

    Args:
        data: Bytes in float32 format

    Returns:
        List of float values
    """
    count = len(data) // 4  # 4 bytes per float32
    return list(struct.unpack(f"{count}f", data))


def init_vector_table(conn: sqlite3.Connection, dimensions: int = DEFAULT_DIMENSIONS) -> None:
    """
    Initialize the virtual table for vector storage.

    Creates the vec0 virtual table if it doesn't exist. The table stores
    embeddings with a rowid that can be joined with the embeddings metadata table.

    Args:
        conn: SQLite database connection (must have sqlite-vec loaded)
        dimensions: Number of dimensions for the embedding vectors
    """
    # Check if virtual table already exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (VEC_TABLE_NAME,),
    )
    if cursor.fetchone() is not None:
        logger.debug(f"Vector table '{VEC_TABLE_NAME}' already exists")
        return

    # Create the virtual table with the specified dimensions
    sql = f"""
        CREATE VIRTUAL TABLE {VEC_TABLE_NAME} USING vec0(
            embedding float[{dimensions}]
        )
    """
    conn.execute(sql)
    conn.commit()
    logger.info(f"Created vector table '{VEC_TABLE_NAME}' with {dimensions} dimensions")


def store_embedding(
    conn: sqlite3.Connection,
    source_type: Literal["note", "entity", "query"],
    source_id: str,
    embedding: list[float],
    model_name: str = "text-embedding-3-small",
) -> str:
    """
    Store an embedding vector in the database.

    This function:
    1. Generates a unique embedding_id
    2. Inserts the vector into the vec0 virtual table
    3. Creates a metadata record in the embeddings table

    Args:
        conn: SQLite database connection (must have sqlite-vec loaded)
        source_type: Type of source ('note', 'entity', 'query')
        source_id: ID of the source object
        embedding: List of float values representing the embedding
        model_name: Name of the embedding model used

    Returns:
        The embedding_id for the stored embedding
    """
    embedding_id = str(uuid.uuid4())
    dimensions = len(embedding)
    now = datetime.now().isoformat()

    # Serialize the embedding to binary format
    embedding_blob = serialize_float32(embedding)

    # Get the next rowid for the vector table
    cursor = conn.execute(f"SELECT COALESCE(MAX(rowid), 0) + 1 FROM {VEC_TABLE_NAME}")
    rowid = cursor.fetchone()[0]

    # Insert into the vector table
    conn.execute(
        f"INSERT INTO {VEC_TABLE_NAME}(rowid, embedding) VALUES (?, ?)",
        (rowid, embedding_blob),
    )

    # Insert metadata record with rowid reference
    # We store rowid in embedding_id for now, with actual embedding_id as TEXT
    conn.execute(
        """
        INSERT INTO embeddings (embedding_id, source_type, source_id, model_name, dimensions, created_ts)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (embedding_id, source_type, source_id, model_name, dimensions, now),
    )

    # Create a mapping table entry if it doesn't exist
    _ensure_rowid_mapping_table(conn)
    conn.execute(
        "INSERT INTO embedding_rowid_map (embedding_id, rowid) VALUES (?, ?)",
        (embedding_id, rowid),
    )

    conn.commit()
    logger.debug(f"Stored embedding {embedding_id} for {source_type}:{source_id}")
    return embedding_id


def _ensure_rowid_mapping_table(conn: sqlite3.Connection) -> None:
    """
    Ensure the rowid mapping table exists.

    This table maps embedding_id (TEXT) to rowid (INTEGER) for the vec0 table.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_rowid_map (
            embedding_id TEXT PRIMARY KEY,
            rowid INTEGER NOT NULL UNIQUE
        )
        """
    )


def query_similar(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    limit: int = 10,
    source_type: Literal["note", "entity", "query"] | None = None,
) -> list[dict]:
    """
    Query for similar embeddings using KNN search.

    Args:
        conn: SQLite database connection (must have sqlite-vec loaded)
        query_embedding: The query vector to find similar embeddings for
        limit: Maximum number of results to return
        source_type: Optional filter by source type

    Returns:
        List of dicts with keys: embedding_id, source_type, source_id, distance
    """
    query_blob = serialize_float32(query_embedding)

    # Perform KNN search on the vector table
    cursor = conn.execute(
        f"""
        SELECT rowid, distance
        FROM {VEC_TABLE_NAME}
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (query_blob, limit * 2 if source_type else limit),  # Fetch extra if filtering
    )

    results = []
    for row in cursor.fetchall():
        rowid, distance = row

        # Look up the embedding metadata via the mapping table
        meta_cursor = conn.execute(
            """
            SELECT e.embedding_id, e.source_type, e.source_id
            FROM embedding_rowid_map m
            JOIN embeddings e ON e.embedding_id = m.embedding_id
            WHERE m.rowid = ?
            """,
            (rowid,),
        )
        meta_row = meta_cursor.fetchone()

        if meta_row is None:
            logger.warning(f"No metadata found for rowid {rowid}")
            continue

        embedding_id, src_type, source_id = meta_row

        # Apply source_type filter if specified
        if source_type is not None and src_type != source_type:
            continue

        results.append(
            {
                "embedding_id": embedding_id,
                "source_type": src_type,
                "source_id": source_id,
                "distance": distance,
            }
        )

        if len(results) >= limit:
            break

    return results


def delete_embedding(conn: sqlite3.Connection, embedding_id: str) -> bool:
    """
    Delete an embedding from both the vector table and metadata.

    Args:
        conn: SQLite database connection (must have sqlite-vec loaded)
        embedding_id: The ID of the embedding to delete

    Returns:
        True if the embedding was deleted, False if not found
    """
    # Check if mapping table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_rowid_map'"
    )
    if cursor.fetchone() is None:
        return False

    # Look up the rowid
    cursor = conn.execute(
        "SELECT rowid FROM embedding_rowid_map WHERE embedding_id = ?",
        (embedding_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return False

    rowid = row[0]

    # Delete from vector table
    conn.execute(f"DELETE FROM {VEC_TABLE_NAME} WHERE rowid = ?", (rowid,))

    # Delete from mapping table
    conn.execute("DELETE FROM embedding_rowid_map WHERE embedding_id = ?", (embedding_id,))

    # Delete from metadata table
    conn.execute("DELETE FROM embeddings WHERE embedding_id = ?", (embedding_id,))

    conn.commit()
    logger.debug(f"Deleted embedding {embedding_id}")
    return True


def get_embedding_by_source(
    conn: sqlite3.Connection,
    source_type: Literal["note", "entity", "query"],
    source_id: str,
) -> dict | None:
    """
    Get embedding metadata by source type and ID.

    Args:
        conn: SQLite database connection
        source_type: Type of source
        source_id: ID of the source object

    Returns:
        Dict with embedding metadata, or None if not found
    """
    cursor = conn.execute(
        """
        SELECT embedding_id, source_type, source_id, model_name, dimensions, created_ts
        FROM embeddings
        WHERE source_type = ? AND source_id = ?
        """,
        (source_type, source_id),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    return {
        "embedding_id": row[0],
        "source_type": row[1],
        "source_id": row[2],
        "model_name": row[3],
        "dimensions": row[4],
        "created_ts": row[5],
    }


def get_embedding_vector(conn: sqlite3.Connection, embedding_id: str) -> list[float] | None:
    """
    Retrieve the actual embedding vector for a given embedding_id.

    Args:
        conn: SQLite database connection (must have sqlite-vec loaded)
        embedding_id: The ID of the embedding

    Returns:
        List of float values, or None if not found
    """
    # Check if mapping table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_rowid_map'"
    )
    if cursor.fetchone() is None:
        return None

    # Look up the rowid
    cursor = conn.execute(
        "SELECT rowid FROM embedding_rowid_map WHERE embedding_id = ?",
        (embedding_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    rowid = row[0]

    # Retrieve the vector from vec0 table
    cursor = conn.execute(
        f"SELECT embedding FROM {VEC_TABLE_NAME} WHERE rowid = ?",
        (rowid,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    return deserialize_float32(row[0])


def count_embeddings(conn: sqlite3.Connection) -> dict:
    """
    Get counts of embeddings by source type.

    Args:
        conn: SQLite database connection

    Returns:
        Dict with counts by source_type and total
    """
    cursor = conn.execute(
        """
        SELECT source_type, COUNT(*) as count
        FROM embeddings
        GROUP BY source_type
        """
    )

    counts = {}
    total = 0
    for row in cursor.fetchall():
        counts[row[0]] = row[1]
        total += row[1]

    counts["total"] = total
    return counts


class VectorStore:
    """
    High-level interface for vector storage and search.

    This class wraps the lower-level functions and manages the connection
    lifecycle for vector operations.
    """

    def __init__(self, db_path: Path | str, dimensions: int = DEFAULT_DIMENSIONS):
        """
        Initialize the vector store.

        Args:
            db_path: Path to the SQLite database file
            dimensions: Number of dimensions for embeddings
        """
        self.db_path = Path(db_path)
        self.dimensions = dimensions
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection with sqlite-vec loaded."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            load_sqlite_vec(self._conn)
            init_vector_table(self._conn, self.dimensions)
        return self._conn

    def store(
        self,
        source_type: Literal["note", "entity", "query"],
        source_id: str,
        embedding: list[float],
        model_name: str = "text-embedding-3-small",
    ) -> str:
        """Store an embedding vector."""
        conn = self._get_connection()
        return store_embedding(conn, source_type, source_id, embedding, model_name)

    def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        source_type: Literal["note", "entity", "query"] | None = None,
    ) -> list[dict]:
        """Search for similar embeddings."""
        conn = self._get_connection()
        return query_similar(conn, query_embedding, limit, source_type)

    def delete(self, embedding_id: str) -> bool:
        """Delete an embedding."""
        conn = self._get_connection()
        return delete_embedding(conn, embedding_id)

    def get_by_source(
        self,
        source_type: Literal["note", "entity", "query"],
        source_id: str,
    ) -> dict | None:
        """Get embedding metadata by source."""
        conn = self._get_connection()
        return get_embedding_by_source(conn, source_type, source_id)

    def get_vector(self, embedding_id: str) -> list[float] | None:
        """Get the raw embedding vector."""
        conn = self._get_connection()
        return get_embedding_vector(conn, embedding_id)

    def count(self) -> dict:
        """Get embedding counts by source type."""
        conn = self._get_connection()
        return count_embeddings(conn)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "VectorStore":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
