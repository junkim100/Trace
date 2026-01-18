"""
Tests for sqlite-vec vector storage and search.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.db.migrations import init_database
from src.db.vectors import (
    DEFAULT_DIMENSIONS,
    VEC_TABLE_NAME,
    VectorStore,
    count_embeddings,
    delete_embedding,
    deserialize_float32,
    get_embedding_by_source,
    get_embedding_vector,
    init_vector_table,
    load_sqlite_vec,
    query_similar,
    serialize_float32,
    store_embedding,
)


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def initialized_db(temp_db: Path) -> sqlite3.Connection:
    """Create and initialize a temporary database with migrations."""
    conn = init_database(temp_db)
    yield conn
    conn.close()


@pytest.fixture
def vec_db(initialized_db: sqlite3.Connection) -> sqlite3.Connection:
    """Database connection with sqlite-vec loaded and vector table initialized."""
    load_sqlite_vec(initialized_db)
    init_vector_table(initialized_db, DEFAULT_DIMENSIONS)
    return initialized_db


def make_embedding(seed: float = 0.0, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Generate a deterministic test embedding vector."""
    return [seed + (i / dimensions) for i in range(dimensions)]


class TestSerialization:
    """Tests for vector serialization/deserialization."""

    def test_serialize_float32(self):
        """Test serializing a float list to binary."""
        vector = [1.0, 2.0, 3.0, 4.0]
        blob = serialize_float32(vector)

        assert isinstance(blob, bytes)
        assert len(blob) == 16  # 4 floats * 4 bytes each

    def test_deserialize_float32(self):
        """Test deserializing binary back to float list."""
        original = [1.0, 2.0, 3.0, 4.0]
        blob = serialize_float32(original)
        restored = deserialize_float32(blob)

        assert len(restored) == len(original)
        for orig, rest in zip(original, restored, strict=True):
            assert abs(orig - rest) < 1e-6

    def test_roundtrip_1536_dimensions(self):
        """Test roundtrip with 1536 dimensions (OpenAI embedding size)."""
        original = make_embedding(0.1)
        blob = serialize_float32(original)
        restored = deserialize_float32(blob)

        assert len(restored) == DEFAULT_DIMENSIONS
        for orig, rest in zip(original, restored, strict=True):
            assert abs(orig - rest) < 1e-6


class TestLoadExtension:
    """Tests for loading the sqlite-vec extension."""

    def test_load_sqlite_vec(self, initialized_db: sqlite3.Connection):
        """Test that sqlite-vec extension loads successfully."""
        load_sqlite_vec(initialized_db)

        # Verify vec functions are available
        cursor = initialized_db.execute("SELECT vec_version()")
        version = cursor.fetchone()[0]
        assert version is not None

    def test_vec_length_function(self, initialized_db: sqlite3.Connection):
        """Test that vec_length function works."""
        load_sqlite_vec(initialized_db)

        vector = [1.0, 2.0, 3.0, 4.0]
        blob = serialize_float32(vector)

        cursor = initialized_db.execute("SELECT vec_length(?)", (blob,))
        length = cursor.fetchone()[0]
        assert length == 4


class TestInitVectorTable:
    """Tests for vector table initialization."""

    def test_init_creates_table(self, initialized_db: sqlite3.Connection):
        """Test that init_vector_table creates the virtual table."""
        load_sqlite_vec(initialized_db)
        init_vector_table(initialized_db, DEFAULT_DIMENSIONS)

        cursor = initialized_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (VEC_TABLE_NAME,),
        )
        assert cursor.fetchone() is not None

    def test_init_idempotent(self, initialized_db: sqlite3.Connection):
        """Test that calling init_vector_table twice is safe."""
        load_sqlite_vec(initialized_db)
        init_vector_table(initialized_db, DEFAULT_DIMENSIONS)
        init_vector_table(initialized_db, DEFAULT_DIMENSIONS)  # Should not raise


class TestStoreEmbedding:
    """Tests for storing embeddings."""

    def test_store_embedding(self, vec_db: sqlite3.Connection):
        """Test storing an embedding."""
        embedding = make_embedding(0.1)
        embedding_id = store_embedding(
            vec_db,
            source_type="note",
            source_id="note-123",
            embedding=embedding,
            model_name="text-embedding-3-small",
        )

        assert embedding_id is not None
        assert len(embedding_id) == 36  # UUID format

    def test_store_creates_metadata(self, vec_db: sqlite3.Connection):
        """Test that storing creates a metadata record."""
        embedding = make_embedding(0.1)
        embedding_id = store_embedding(
            vec_db,
            source_type="note",
            source_id="note-456",
            embedding=embedding,
        )

        cursor = vec_db.execute(
            "SELECT source_type, source_id, model_name, dimensions FROM embeddings WHERE embedding_id = ?",
            (embedding_id,),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "note"
        assert row[1] == "note-456"
        assert row[2] == "text-embedding-3-small"
        assert row[3] == DEFAULT_DIMENSIONS

    def test_store_multiple_embeddings(self, vec_db: sqlite3.Connection):
        """Test storing multiple embeddings."""
        ids = []
        for i in range(5):
            embedding = make_embedding(i * 0.1)
            eid = store_embedding(
                vec_db,
                source_type="note",
                source_id=f"note-{i}",
                embedding=embedding,
            )
            ids.append(eid)

        assert len(set(ids)) == 5  # All unique


class TestQuerySimilar:
    """Tests for KNN similarity search."""

    def test_query_similar_basic(self, vec_db: sqlite3.Connection):
        """Test basic similarity query."""
        # Store some embeddings
        embeddings = []
        for i in range(3):
            emb = make_embedding(i * 0.5)
            store_embedding(vec_db, "note", f"note-{i}", emb)
            embeddings.append(emb)

        # Query with the first embedding - should return itself as closest
        results = query_similar(vec_db, embeddings[0], limit=3)

        assert len(results) == 3
        assert results[0]["source_id"] == "note-0"
        assert results[0]["distance"] == 0.0  # Exact match

    def test_query_similar_ordering(self, vec_db: sqlite3.Connection):
        """Test that results are ordered by distance."""
        # Store embeddings with known distances
        base = make_embedding(0.0)
        close = make_embedding(0.1)  # Close to base
        far = make_embedding(1.0)  # Far from base

        store_embedding(vec_db, "note", "close", close)
        store_embedding(vec_db, "note", "far", far)

        results = query_similar(vec_db, base, limit=2)

        assert len(results) == 2
        assert results[0]["source_id"] == "close"
        assert results[1]["source_id"] == "far"
        assert results[0]["distance"] < results[1]["distance"]

    def test_query_similar_filter_source_type(self, vec_db: sqlite3.Connection):
        """Test filtering results by source type."""
        embedding = make_embedding(0.1)

        store_embedding(vec_db, "note", "note-1", embedding)
        store_embedding(vec_db, "entity", "entity-1", make_embedding(0.2))
        store_embedding(vec_db, "note", "note-2", make_embedding(0.3))

        # Query only notes
        results = query_similar(vec_db, embedding, limit=10, source_type="note")

        assert all(r["source_type"] == "note" for r in results)

    def test_query_similar_limit(self, vec_db: sqlite3.Connection):
        """Test that limit is respected."""
        for i in range(10):
            store_embedding(vec_db, "note", f"note-{i}", make_embedding(i * 0.1))

        results = query_similar(vec_db, make_embedding(0.0), limit=3)
        assert len(results) == 3


class TestDeleteEmbedding:
    """Tests for deleting embeddings."""

    def test_delete_existing(self, vec_db: sqlite3.Connection):
        """Test deleting an existing embedding."""
        embedding = make_embedding(0.1)
        embedding_id = store_embedding(vec_db, "note", "note-123", embedding)

        success = delete_embedding(vec_db, embedding_id)
        assert success is True

        # Verify it's gone from metadata
        cursor = vec_db.execute(
            "SELECT COUNT(*) FROM embeddings WHERE embedding_id = ?",
            (embedding_id,),
        )
        assert cursor.fetchone()[0] == 0

    def test_delete_nonexistent(self, vec_db: sqlite3.Connection):
        """Test deleting a non-existent embedding returns False."""
        success = delete_embedding(vec_db, "nonexistent-id")
        assert success is False


class TestGetEmbedding:
    """Tests for retrieving embeddings."""

    def test_get_by_source(self, vec_db: sqlite3.Connection):
        """Test getting embedding metadata by source."""
        embedding = make_embedding(0.1)
        store_embedding(vec_db, "note", "note-123", embedding)

        result = get_embedding_by_source(vec_db, "note", "note-123")

        assert result is not None
        assert result["source_type"] == "note"
        assert result["source_id"] == "note-123"
        assert result["dimensions"] == DEFAULT_DIMENSIONS

    def test_get_by_source_not_found(self, vec_db: sqlite3.Connection):
        """Test getting non-existent embedding returns None."""
        result = get_embedding_by_source(vec_db, "note", "nonexistent")
        assert result is None

    def test_get_vector(self, vec_db: sqlite3.Connection):
        """Test retrieving the actual vector."""
        original = make_embedding(0.5)
        embedding_id = store_embedding(vec_db, "note", "note-123", original)

        retrieved = get_embedding_vector(vec_db, embedding_id)

        assert retrieved is not None
        assert len(retrieved) == len(original)
        for orig, ret in zip(original, retrieved, strict=True):
            assert abs(orig - ret) < 1e-6

    def test_get_vector_not_found(self, vec_db: sqlite3.Connection):
        """Test getting vector for non-existent ID returns None."""
        result = get_embedding_vector(vec_db, "nonexistent")
        assert result is None


class TestCountEmbeddings:
    """Tests for counting embeddings."""

    def test_count_empty(self, vec_db: sqlite3.Connection):
        """Test counting with no embeddings."""
        counts = count_embeddings(vec_db)
        assert counts["total"] == 0

    def test_count_by_type(self, vec_db: sqlite3.Connection):
        """Test counting by source type."""
        store_embedding(vec_db, "note", "note-1", make_embedding(0.1))
        store_embedding(vec_db, "note", "note-2", make_embedding(0.2))
        store_embedding(vec_db, "entity", "entity-1", make_embedding(0.3))

        counts = count_embeddings(vec_db)

        assert counts["note"] == 2
        assert counts["entity"] == 1
        assert counts["total"] == 3


class TestVectorStore:
    """Tests for the VectorStore class."""

    def test_context_manager(self, temp_db: Path):
        """Test VectorStore as context manager."""
        # First initialize the database schema
        conn = init_database(temp_db)
        conn.close()

        with VectorStore(temp_db) as store:
            embedding = make_embedding(0.1)
            eid = store.store("note", "note-123", embedding)
            assert eid is not None

    def test_store_and_search(self, temp_db: Path):
        """Test storing and searching via VectorStore."""
        conn = init_database(temp_db)
        conn.close()

        with VectorStore(temp_db) as store:
            # Store embeddings
            emb1 = make_embedding(0.1)
            emb2 = make_embedding(0.5)

            store.store("note", "note-1", emb1)
            store.store("note", "note-2", emb2)

            # Search
            results = store.search(emb1, limit=2)

            assert len(results) == 2
            assert results[0]["source_id"] == "note-1"

    def test_delete(self, temp_db: Path):
        """Test deleting via VectorStore."""
        conn = init_database(temp_db)
        conn.close()

        with VectorStore(temp_db) as store:
            embedding = make_embedding(0.1)
            eid = store.store("note", "note-123", embedding)

            success = store.delete(eid)
            assert success is True

            # Verify it's gone
            result = store.get_by_source("note", "note-123")
            assert result is None

    def test_count(self, temp_db: Path):
        """Test counting via VectorStore."""
        conn = init_database(temp_db)
        conn.close()

        with VectorStore(temp_db) as store:
            store.store("note", "note-1", make_embedding(0.1))
            store.store("entity", "entity-1", make_embedding(0.2))

            counts = store.count()
            assert counts["total"] == 2
            assert counts["note"] == 1
            assert counts["entity"] == 1

    def test_get_vector(self, temp_db: Path):
        """Test getting vector via VectorStore."""
        conn = init_database(temp_db)
        conn.close()

        with VectorStore(temp_db) as store:
            original = make_embedding(0.3)
            eid = store.store("note", "note-123", original)

            retrieved = store.get_vector(eid)
            assert retrieved is not None
            assert len(retrieved) == len(original)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_zero_embedding(self, vec_db: sqlite3.Connection):
        """Test with zero vector."""
        zero_embedding = [0.0] * DEFAULT_DIMENSIONS
        eid = store_embedding(vec_db, "note", "zero-note", zero_embedding)

        retrieved = get_embedding_vector(vec_db, eid)
        assert all(v == 0.0 for v in retrieved)

    def test_negative_values(self, vec_db: sqlite3.Connection):
        """Test with negative values."""
        embedding = [-0.5 + (i / DEFAULT_DIMENSIONS) for i in range(DEFAULT_DIMENSIONS)]
        eid = store_embedding(vec_db, "note", "neg-note", embedding)

        retrieved = get_embedding_vector(vec_db, eid)
        assert retrieved is not None
        for orig, ret in zip(embedding, retrieved, strict=True):
            assert abs(orig - ret) < 1e-6

    def test_small_dimensions(self, initialized_db: sqlite3.Connection):
        """Test with smaller dimension vectors."""
        load_sqlite_vec(initialized_db)
        init_vector_table(initialized_db, dimensions=8)

        small_embedding = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        eid = store_embedding(
            initialized_db,
            "note",
            "small-note",
            small_embedding,
        )

        retrieved = get_embedding_vector(initialized_db, eid)
        assert len(retrieved) == 8
