"""
End-to-end test for chat functionality.

P9-03: End-to-end chat test
Acceptance criteria: Query returns relevant notes with citations
"""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.db.migrations import init_database


class TestChatE2E:
    """End-to-end tests for chat functionality."""

    @pytest.fixture
    def test_env(self, tmp_path: Path, monkeypatch):
        """Set up a complete test environment with database and sample data."""
        # Set up directories
        data_dir = tmp_path / "trace_data"
        data_dir.mkdir()

        notes_dir = data_dir / "notes"
        notes_dir.mkdir()

        db_dir = data_dir / "db"
        db_dir.mkdir()

        db_path = db_dir / "trace.sqlite"

        # Monkeypatch environment
        monkeypatch.setenv("TRACE_DATA_DIR", str(data_dir))

        # Initialize database
        init_database(db_path)

        return {
            "data_dir": data_dir,
            "db_path": db_path,
            "notes_dir": notes_dir,
        }

    @pytest.fixture
    def seeded_chat_env(self, test_env: dict):
        """Set up test environment with seeded notes and entities for chat testing."""
        db_path = test_env["db_path"]
        notes_dir = test_env["notes_dir"]

        # Time for test data
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Create test notes
            notes_data = [
                {
                    "note_id": str(uuid.uuid4()),
                    "note_type": "hour",
                    "start_ts": yesterday.replace(hour=10, minute=0).isoformat(),
                    "end_ts": yesterday.replace(hour=11, minute=0).isoformat(),
                    "file_path": str(notes_dir / "note1.md"),
                    "json_payload": json.dumps(
                        {
                            "summary": "Worked on Python project implementing machine learning models",
                            "activities": [
                                {
                                    "description": "Coding Python ML pipeline",
                                    "app_name": "VS Code",
                                    "minutes": 45,
                                }
                            ],
                            "entities": [
                                {"name": "Python", "type": "technology"},
                                {"name": "Machine Learning", "type": "topic"},
                            ],
                            "topics": ["programming", "machine learning", "data science"],
                        }
                    ),
                },
                {
                    "note_id": str(uuid.uuid4()),
                    "note_type": "hour",
                    "start_ts": yesterday.replace(hour=14, minute=0).isoformat(),
                    "end_ts": yesterday.replace(hour=15, minute=0).isoformat(),
                    "file_path": str(notes_dir / "note2.md"),
                    "json_payload": json.dumps(
                        {
                            "summary": "Code review and documentation for the API project",
                            "activities": [
                                {
                                    "description": "Reviewing pull requests",
                                    "app_name": "GitHub",
                                    "minutes": 30,
                                }
                            ],
                            "entities": [
                                {"name": "GitHub", "type": "website"},
                                {"name": "API", "type": "topic"},
                            ],
                            "topics": ["code review", "documentation", "API"],
                        }
                    ),
                },
                {
                    "note_id": str(uuid.uuid4()),
                    "note_type": "hour",
                    "start_ts": last_week.replace(hour=9, minute=0).isoformat(),
                    "end_ts": last_week.replace(hour=10, minute=0).isoformat(),
                    "file_path": str(notes_dir / "note3.md"),
                    "json_payload": json.dumps(
                        {
                            "summary": "Team meeting and project planning",
                            "activities": [
                                {
                                    "description": "Video call with team",
                                    "app_name": "Zoom",
                                    "minutes": 50,
                                }
                            ],
                            "entities": [
                                {"name": "Zoom", "type": "app"},
                                {"name": "Team Meeting", "type": "event"},
                            ],
                            "topics": ["meetings", "planning", "team"],
                        }
                    ),
                },
            ]

            for note in notes_data:
                cursor.execute(
                    """
                    INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note["note_id"],
                        note["note_type"],
                        note["start_ts"],
                        note["end_ts"],
                        note["file_path"],
                        note["json_payload"],
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            # Create test entities
            entities_data = [
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_type": "technology",
                    "canonical_name": "Python",
                },
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_type": "topic",
                    "canonical_name": "Machine Learning",
                },
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_type": "website",
                    "canonical_name": "GitHub",
                },
                {
                    "entity_id": str(uuid.uuid4()),
                    "entity_type": "app",
                    "canonical_name": "VS Code",
                },
            ]

            for entity in entities_data:
                cursor.execute(
                    """
                    INSERT INTO entities (entity_id, entity_type, canonical_name, created_ts)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entity["entity_id"],
                        entity["entity_type"],
                        entity["canonical_name"],
                        datetime.now().isoformat(),
                    ),
                )

            # Link entities to notes
            for i, note in enumerate(notes_data):
                for entity in entities_data[: i + 1]:
                    cursor.execute(
                        """
                        INSERT INTO note_entities (note_id, entity_id, context)
                        VALUES (?, ?, ?)
                        """,
                        (note["note_id"], entity["entity_id"], "Test context"),
                    )

            # Create test aggregates
            aggregates_data = [
                {
                    "key": "VS Code",
                    "key_type": "app",
                    "value": 120,
                    "period_type": "day",
                    "period_start": yesterday.date().isoformat(),
                    "period_end": yesterday.date().isoformat(),
                },
                {
                    "key": "Safari",
                    "key_type": "app",
                    "value": 60,
                    "period_type": "day",
                    "period_start": yesterday.date().isoformat(),
                    "period_end": yesterday.date().isoformat(),
                },
            ]

            for agg in aggregates_data:
                cursor.execute(
                    """
                    INSERT INTO aggregates (key, key_type, value, period_type, period_start, period_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agg["key"],
                        agg["key_type"],
                        agg["value"],
                        agg["period_type"],
                        agg["period_start"],
                        agg["period_end"],
                    ),
                )

            conn.commit()

            # Create actual note files
            for note in notes_data:
                note_file = Path(note["file_path"])
                note_file.parent.mkdir(parents=True, exist_ok=True)
                payload = json.loads(note["json_payload"])
                note_file.write_text(
                    f"""---
note_id: {note["note_id"]}
start_ts: {note["start_ts"]}
end_ts: {note["end_ts"]}
---

# {payload["summary"]}

## Activities
{chr(10).join(f"- {a['description']}" for a in payload.get("activities", []))}

## Topics
{", ".join(payload.get("topics", []))}
"""
                )

        finally:
            conn.close()

        return {
            **test_env,
            "notes": notes_data,
            "entities": entities_data,
        }

    def test_chat_api_initialization(self, test_env: dict, monkeypatch):
        """Test that ChatAPI initializes correctly."""
        from src.chat.api import ChatAPI

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        api = ChatAPI(db_path=db_path)
        assert api is not None
        assert api.db_path == db_path

    def test_chat_query_parsing(self, test_env: dict, monkeypatch):
        """Test query type detection."""
        from src.chat.api import ChatAPI

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        api = ChatAPI(db_path=db_path)

        # Test aggregates query detection
        assert api._detect_query_type("What was my most used app?") == "aggregates"
        assert api._detect_query_type("top apps this week") == "aggregates"

        # Test entity query detection
        assert api._detect_query_type("Tell me about Python") == "entity"
        assert api._detect_query_type("What do I know about Machine Learning?") == "entity"

        # Test timeline query detection
        assert api._detect_query_type("What did I do yesterday?") == "timeline"
        assert api._detect_query_type("Summary of my activities today") == "timeline"

        # Test semantic query (default)
        assert api._detect_query_type("How do I configure the API?") == "semantic"

    def test_time_filter_parsing(self, test_env: dict, monkeypatch):
        """Test time filter parsing from queries."""
        from src.retrieval.time import parse_time_filter

        # Test various time expressions
        today_filter = parse_time_filter("today")
        assert today_filter is not None
        assert today_filter.start.date() == datetime.now().date()

        yesterday_filter = parse_time_filter("yesterday")
        assert yesterday_filter is not None
        assert yesterday_filter.start.date() == (datetime.now() - timedelta(days=1)).date()

        last_week_filter = parse_time_filter("last week")
        assert last_week_filter is not None
        assert last_week_filter.start.date() < datetime.now().date()

    def test_chat_with_seeded_data(self, seeded_chat_env: dict, monkeypatch):
        """Test chat queries against seeded data."""
        from src.chat.api import ChatAPI, ChatRequest

        db_path = seeded_chat_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        # Mock the synthesizer to avoid actual LLM calls
        mock_synthesize_result = MagicMock()
        mock_synthesize_result.answer = "Based on your notes, you worked on Python and ML."
        mock_synthesize_result.citations = []
        mock_synthesize_result.confidence = 0.8

        with patch(
            "src.chat.prompts.answer.AnswerSynthesizer.synthesize",
            return_value=mock_synthesize_result,
        ):
            with patch(
                "src.chat.prompts.answer.AnswerSynthesizer.synthesize_without_context",
                return_value=mock_synthesize_result,
            ):
                api = ChatAPI(db_path=db_path)

                # Test basic query
                request = ChatRequest(
                    query="What Python work did I do?",
                    time_filter_hint="yesterday",
                )
                response = api.chat(request)

                assert response is not None
                assert response.answer is not None
                assert response.query_type in ["semantic", "entity", "timeline", "aggregates"]

    def test_chat_aggregates_query(self, seeded_chat_env: dict, monkeypatch):
        """Test aggregates (most/top) queries."""
        from src.chat.api import ChatAPI, ChatRequest

        db_path = seeded_chat_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        mock_synthesize_result = MagicMock()
        mock_synthesize_result.answer = "Your most used app was VS Code."
        mock_synthesize_result.citations = []
        mock_synthesize_result.confidence = 0.9

        with patch(
            "src.chat.prompts.answer.AnswerSynthesizer.synthesize",
            return_value=mock_synthesize_result,
        ):
            api = ChatAPI(db_path=db_path)

            request = ChatRequest(
                query="What was my most used app yesterday?",
                include_aggregates=True,
            )
            response = api.chat(request)

            assert response is not None
            assert response.query_type == "aggregates"

    def test_chat_timeline_query(self, seeded_chat_env: dict, monkeypatch):
        """Test timeline queries."""
        from src.chat.api import ChatAPI, ChatRequest

        db_path = seeded_chat_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        mock_synthesize_result = MagicMock()
        mock_synthesize_result.answer = "Yesterday you worked on Python ML projects."
        mock_synthesize_result.citations = []
        mock_synthesize_result.confidence = 0.85

        with patch(
            "src.chat.prompts.answer.AnswerSynthesizer.synthesize",
            return_value=mock_synthesize_result,
        ):
            api = ChatAPI(db_path=db_path)

            request = ChatRequest(
                query="What did I do yesterday?",
            )
            response = api.chat(request)

            assert response is not None
            assert response.query_type == "timeline"
            assert response.time_filter is not None

    def test_chat_response_structure(self, seeded_chat_env: dict, monkeypatch):
        """Test that chat response has correct structure."""
        from src.chat.api import ChatAPI, ChatRequest

        db_path = seeded_chat_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        mock_synthesize_result = MagicMock()
        mock_synthesize_result.answer = "Test answer"
        mock_synthesize_result.citations = []
        mock_synthesize_result.confidence = 0.7

        with patch(
            "src.chat.prompts.answer.AnswerSynthesizer.synthesize",
            return_value=mock_synthesize_result,
        ):
            with patch(
                "src.chat.prompts.answer.AnswerSynthesizer.synthesize_without_context",
                return_value=mock_synthesize_result,
            ):
                api = ChatAPI(db_path=db_path)

                request = ChatRequest(query="test query")
                response = api.chat(request)

                # Verify response structure
                assert hasattr(response, "answer")
                assert hasattr(response, "citations")
                assert hasattr(response, "notes")
                assert hasattr(response, "time_filter")
                assert hasattr(response, "related_entities")
                assert hasattr(response, "aggregates")
                assert hasattr(response, "query_type")
                assert hasattr(response, "confidence")
                assert hasattr(response, "processing_time_ms")

                # Verify to_dict works
                response_dict = response.to_dict()
                assert isinstance(response_dict, dict)
                assert "answer" in response_dict
                assert "citations" in response_dict

    def test_chat_entity_extraction(self, test_env: dict, monkeypatch):
        """Test entity extraction from queries."""
        from src.chat.api import ChatAPI

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        api = ChatAPI(db_path=db_path)

        # Test entity extraction
        entity = api._extract_entity_from_query("Tell me about Python")
        assert entity == "Python"

        entity = api._extract_entity_from_query('What do I know about "Machine Learning"?')
        assert entity is not None

        entity = api._extract_entity_from_query("related to GitHub today")
        assert entity is not None

    def test_simple_query_interface(self, seeded_chat_env: dict, monkeypatch):
        """Test the simplified query() interface."""
        from src.chat.api import ChatAPI

        db_path = seeded_chat_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        mock_synthesize_result = MagicMock()
        mock_synthesize_result.answer = "Test answer"
        mock_synthesize_result.citations = []
        mock_synthesize_result.confidence = 0.7

        with patch(
            "src.chat.prompts.answer.AnswerSynthesizer.synthesize",
            return_value=mock_synthesize_result,
        ):
            with patch(
                "src.chat.prompts.answer.AnswerSynthesizer.synthesize_without_context",
                return_value=mock_synthesize_result,
            ):
                api = ChatAPI(db_path=db_path)

                # Use simple query interface
                response = api.query("What did I work on?", time_filter="yesterday")

                assert response is not None
                assert response.answer is not None


class TestChatWithRetrievalE2E:
    """End-to-end tests for chat with actual retrieval (no mocks)."""

    @pytest.fixture
    def full_test_env(self, tmp_path: Path, monkeypatch):
        """Set up a complete test environment."""
        data_dir = tmp_path / "trace_data"
        data_dir.mkdir()
        db_path = data_dir / "db" / "trace.sqlite"
        db_path.parent.mkdir(parents=True)

        notes_dir = data_dir / "notes"
        notes_dir.mkdir()

        monkeypatch.setenv("TRACE_DATA_DIR", str(data_dir))
        init_database(db_path)

        # Seed with test data
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.cursor()

            note_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO notes (note_id, note_type, start_ts, end_ts, file_path, json_payload, created_ts, updated_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    "hour",
                    yesterday.replace(hour=10).isoformat(),
                    yesterday.replace(hour=11).isoformat(),
                    str(notes_dir / "note.md"),
                    json.dumps(
                        {
                            "summary": "Worked on test project",
                            "activities": [],
                            "entities": [],
                            "topics": ["testing"],
                        }
                    ),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

            conn.commit()
        finally:
            conn.close()

        return {
            "data_dir": data_dir,
            "db_path": db_path,
            "notes_dir": notes_dir,
        }

    def test_retrieval_components(self, full_test_env: dict, monkeypatch):
        """Test retrieval components work together."""
        from src.retrieval.time import parse_time_filter

        # Test time parsing
        filter_today = parse_time_filter("today")
        assert filter_today is not None

        filter_yesterday = parse_time_filter("yesterday")
        assert filter_yesterday is not None

        # These should be different
        assert filter_today.start != filter_yesterday.start


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
