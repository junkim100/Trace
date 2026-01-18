"""
Tests for database schema and migrations.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.db.migrations import (
    MigrationRunner,
    get_connection,
    get_current_version,
    init_database,
    verify_schema,
)


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def initialized_db(temp_db: Path) -> sqlite3.Connection:
    """Create and initialize a temporary database."""
    conn = init_database(temp_db)
    yield conn
    conn.close()


class TestMigrationRunner:
    """Tests for the MigrationRunner class."""

    def test_get_pending_migrations_empty_db(self, temp_db: Path):
        """Test that all migrations are pending for a new database."""
        runner = MigrationRunner(temp_db)
        pending = runner.get_pending_migrations()

        assert len(pending) > 0
        assert pending[0][0] == 1  # First migration is version 1

    def test_run_migrations(self, temp_db: Path):
        """Test running all migrations."""
        runner = MigrationRunner(temp_db)
        count = runner.run_migrations()

        assert count >= 1

        with get_connection(temp_db) as conn:
            version = get_current_version(conn)
            assert version >= 1

    def test_no_pending_after_migration(self, temp_db: Path):
        """Test that no migrations are pending after running."""
        runner = MigrationRunner(temp_db)
        runner.run_migrations()

        pending = runner.get_pending_migrations()
        assert len(pending) == 0

    def test_get_status(self, temp_db: Path):
        """Test getting migration status."""
        runner = MigrationRunner(temp_db)
        status = runner.get_status()

        assert "current_version" in status
        assert "pending_migrations" in status
        assert "pending_files" in status
        assert "database_path" in status


class TestSchema:
    """Tests for the database schema."""

    def test_all_tables_created(self, initialized_db: sqlite3.Connection):
        """Test that all expected tables are created."""
        result = verify_schema(initialized_db)

        assert result["valid"], f"Missing tables: {result['missing']}"
        assert len(result["missing"]) == 0

    def test_notes_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the notes table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(notes)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "note_id",
            "note_type",
            "start_ts",
            "end_ts",
            "file_path",
            "json_payload",
            "embedding_id",
            "created_ts",
            "updated_ts",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_entities_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the entities table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(entities)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "entity_id",
            "entity_type",
            "canonical_name",
            "aliases",
            "created_ts",
            "updated_ts",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_edges_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the edges table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(edges)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "from_id",
            "to_id",
            "edge_type",
            "weight",
            "start_ts",
            "end_ts",
            "evidence_note_ids",
            "created_ts",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_events_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the events table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(events)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "event_id",
            "start_ts",
            "end_ts",
            "app_id",
            "app_name",
            "window_title",
            "focused_monitor",
            "url",
            "page_title",
            "file_path",
            "location_text",
            "now_playing_json",
            "evidence_ids",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_screenshots_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the screenshots table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(screenshots)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "screenshot_id",
            "ts",
            "monitor_id",
            "path",
            "fingerprint",
            "diff_score",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_text_buffers_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the text_buffers table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(text_buffers)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "text_id",
            "ts",
            "source_type",
            "ref",
            "compressed_text",
            "token_estimate",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_jobs_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the jobs table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(jobs)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "job_id",
            "job_type",
            "window_start_ts",
            "window_end_ts",
            "status",
            "attempts",
            "last_error",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_aggregates_table_structure(self, initialized_db: sqlite3.Connection):
        """Test the aggregates table has expected columns."""
        cursor = initialized_db.execute("PRAGMA table_info(aggregates)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        expected_columns = [
            "agg_id",
            "period_type",
            "period_start_ts",
            "period_end_ts",
            "key_type",
            "key",
            "value_num",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"


class TestConstraints:
    """Tests for database constraints."""

    def test_note_type_constraint(self, initialized_db: sqlite3.Connection):
        """Test that note_type only accepts valid values."""
        # Valid types should work
        initialized_db.execute(
            """
            INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload)
            VALUES ('test1', 'hour', '2025-01-01T00:00:00', '2025-01-01T01:00:00', '/test.md', '{}')
            """
        )
        initialized_db.commit()

        # Invalid type should fail
        with pytest.raises(sqlite3.IntegrityError):
            initialized_db.execute(
                """
                INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload)
                VALUES ('test2', 'invalid', '2025-01-01T00:00:00', '2025-01-01T01:00:00', '/test.md', '{}')
                """
            )

    def test_edge_type_constraint(self, initialized_db: sqlite3.Connection):
        """Test that edge_type only accepts valid values."""
        # Valid type should work
        initialized_db.execute(
            """
            INSERT INTO edges (from_id, to_id, edge_type, weight)
            VALUES ('a', 'b', 'ABOUT_TOPIC', 0.8)
            """
        )
        initialized_db.commit()

        # Invalid type should fail
        with pytest.raises(sqlite3.IntegrityError):
            initialized_db.execute(
                """
                INSERT INTO edges (from_id, to_id, edge_type, weight)
                VALUES ('c', 'd', 'INVALID_TYPE', 0.5)
                """
            )

    def test_job_status_constraint(self, initialized_db: sqlite3.Connection):
        """Test that job status only accepts valid values."""
        # Valid status should work
        initialized_db.execute(
            """
            INSERT INTO jobs (job_id, job_type, window_start_ts, window_end_ts, status)
            VALUES ('job1', 'hourly', '2025-01-01T00:00:00', '2025-01-01T01:00:00', 'pending')
            """
        )
        initialized_db.commit()

        # Invalid status should fail
        with pytest.raises(sqlite3.IntegrityError):
            initialized_db.execute(
                """
                INSERT INTO jobs (job_id, job_type, window_start_ts, window_end_ts, status)
                VALUES ('job2', 'hourly', '2025-01-01T00:00:00', '2025-01-01T01:00:00', 'invalid')
                """
            )

    def test_strength_range_constraint(self, initialized_db: sqlite3.Connection):
        """Test that note_entities strength is between 0 and 1."""
        # First create a note and entity
        initialized_db.execute(
            """
            INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload)
            VALUES ('note1', 'hour', '2025-01-01T00:00:00', '2025-01-01T01:00:00', '/test.md', '{}')
            """
        )
        initialized_db.execute(
            """
            INSERT INTO entities (entity_id, entity_type, canonical_name)
            VALUES ('entity1', 'topic', 'Test Topic')
            """
        )
        initialized_db.commit()

        # Valid strength should work
        initialized_db.execute(
            """
            INSERT INTO note_entities (note_id, entity_id, strength)
            VALUES ('note1', 'entity1', 0.75)
            """
        )
        initialized_db.commit()

        # Strength > 1 should fail
        with pytest.raises(sqlite3.IntegrityError):
            initialized_db.execute(
                """
                INSERT INTO note_entities (note_id, entity_id, strength)
                VALUES ('note1', 'entity1', 1.5)
                """
            )


class TestForeignKeys:
    """Tests for foreign key constraints."""

    def test_note_entities_foreign_key(self, initialized_db: sqlite3.Connection):
        """Test that note_entities requires valid note_id."""
        # Creating without valid note should fail
        with pytest.raises(sqlite3.IntegrityError):
            initialized_db.execute(
                """
                INSERT INTO note_entities (note_id, entity_id, strength)
                VALUES ('nonexistent', 'entity1', 0.5)
                """
            )

    def test_cascade_delete_note_entities(self, initialized_db: sqlite3.Connection):
        """Test that deleting a note cascades to note_entities."""
        # Create note and entity
        initialized_db.execute(
            """
            INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload)
            VALUES ('note1', 'hour', '2025-01-01T00:00:00', '2025-01-01T01:00:00', '/test.md', '{}')
            """
        )
        initialized_db.execute(
            """
            INSERT INTO entities (entity_id, entity_type, canonical_name)
            VALUES ('entity1', 'topic', 'Test')
            """
        )
        initialized_db.execute(
            """
            INSERT INTO note_entities (note_id, entity_id, strength)
            VALUES ('note1', 'entity1', 0.5)
            """
        )
        initialized_db.commit()

        # Delete the note
        initialized_db.execute("DELETE FROM notes WHERE note_id = 'note1'")
        initialized_db.commit()

        # Check that note_entity is also deleted
        cursor = initialized_db.execute(
            "SELECT COUNT(*) FROM note_entities WHERE note_id = 'note1'"
        )
        count = cursor.fetchone()[0]
        assert count == 0


class TestIndexes:
    """Tests for database indexes."""

    def test_indexes_exist(self, initialized_db: sqlite3.Connection):
        """Test that expected indexes are created."""
        cursor = initialized_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = [
            "idx_notes_type",
            "idx_notes_time",
            "idx_entities_type",
            "idx_edges_from",
            "idx_edges_to",
            "idx_events_time",
            "idx_screenshots_ts",
            "idx_jobs_type_status",
        ]

        for idx in expected_indexes:
            assert idx in indexes, f"Missing index: {idx}"
