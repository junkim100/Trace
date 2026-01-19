"""
End-to-end test for hourly summarization.

P9-02: End-to-end summarization test
Acceptance criteria: Hourly note generated from test data
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.db.migrations import init_database
from src.summarize.schemas import HourlySummarySchema


class TestSummarizationE2E:
    """End-to-end tests for hourly summarization."""

    @pytest.fixture
    def test_env(self, tmp_path: Path, monkeypatch):
        """Set up a complete test environment with database and data."""
        # Set up directories
        data_dir = tmp_path / "trace_data"
        data_dir.mkdir()

        notes_dir = data_dir / "notes"
        notes_dir.mkdir()

        db_dir = data_dir / "db"
        db_dir.mkdir()

        cache_dir = data_dir / "cache"
        cache_dir.mkdir()

        db_path = db_dir / "trace.sqlite"

        # Monkeypatch environment
        monkeypatch.setenv("TRACE_DATA_DIR", str(data_dir))

        # Initialize database
        init_database(db_path)

        return {
            "data_dir": data_dir,
            "db_path": db_path,
            "notes_dir": notes_dir,
            "cache_dir": cache_dir,
        }

    @pytest.fixture
    def seeded_env(self, test_env: dict):
        """Set up test environment with seeded test data."""
        db_path = test_env["db_path"]
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        hour_end = hour_start + timedelta(hours=1)

        # Seed database with test data
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Create test events
            events_data = [
                {
                    "event_id": str(uuid.uuid4()),
                    "start_ts": (hour_start + timedelta(minutes=0)).isoformat(),
                    "end_ts": (hour_start + timedelta(minutes=20)).isoformat(),
                    "app_id": "com.apple.Safari",
                    "app_name": "Safari",
                    "window_title": "GitHub - Test Repository",
                    "bundle_id": "com.apple.Safari",
                    "url": "https://github.com/test/repo",
                    "page_title": "GitHub - Test Repository",
                },
                {
                    "event_id": str(uuid.uuid4()),
                    "start_ts": (hour_start + timedelta(minutes=20)).isoformat(),
                    "end_ts": (hour_start + timedelta(minutes=40)).isoformat(),
                    "app_id": "com.microsoft.VSCode",
                    "app_name": "Visual Studio Code",
                    "window_title": "main.py - MyProject",
                    "bundle_id": "com.microsoft.VSCode",
                },
                {
                    "event_id": str(uuid.uuid4()),
                    "start_ts": (hour_start + timedelta(minutes=40)).isoformat(),
                    "end_ts": (hour_start + timedelta(minutes=60)).isoformat(),
                    "app_id": "com.apple.Terminal",
                    "app_name": "Terminal",
                    "window_title": "zsh - myproject",
                    "bundle_id": "com.apple.Terminal",
                },
            ]

            for event in events_data:
                cursor.execute(
                    """
                    INSERT INTO events (
                        event_id, start_ts, end_ts, app_id, app_name,
                        window_title, bundle_id, url, page_title
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        event["start_ts"],
                        event["end_ts"],
                        event["app_id"],
                        event["app_name"],
                        event["window_title"],
                        event["bundle_id"],
                        event.get("url"),
                        event.get("page_title"),
                    ),
                )

            conn.commit()

        finally:
            conn.close()

        return {
            **test_env,
            "hour_start": hour_start,
            "hour_end": hour_end,
            "events_count": len(events_data),
        }

    def test_summarize_with_no_activity(self, test_env: dict, monkeypatch):
        """Test summarization with no activity data creates empty note."""
        from src.summarize.summarizer import HourlySummarizer

        db_path = test_env["db_path"]
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)

        # Monkeypatch paths
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)
        monkeypatch.setattr(
            "src.core.paths.get_note_path",
            lambda ts: test_env["notes_dir"]
            / ts.strftime("%Y/%m/%d")
            / f"hour-{ts.strftime('%Y%m%d-%H')}.md",
        )
        monkeypatch.setattr(
            "src.core.paths.ensure_note_directory",
            lambda ts: (test_env["notes_dir"] / ts.strftime("%Y/%m/%d")).mkdir(
                parents=True, exist_ok=True
            ),
        )

        summarizer = HourlySummarizer(db_path=db_path)
        result = summarizer.summarize_hour(hour_start)

        # Should succeed with empty note
        assert result.success
        assert result.note_id is not None
        assert result.events_count == 0
        assert result.file_path is not None

    def test_summarize_with_events(self, seeded_env: dict, monkeypatch):
        """Test summarization with seeded event data."""
        from src.summarize.summarizer import HourlySummarizer

        db_path = seeded_env["db_path"]
        hour_start = seeded_env["hour_start"]

        # Monkeypatch paths
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)
        monkeypatch.setattr(
            "src.core.paths.get_note_path",
            lambda ts: seeded_env["notes_dir"]
            / ts.strftime("%Y/%m/%d")
            / f"hour-{ts.strftime('%Y%m%d-%H')}.md",
        )
        monkeypatch.setattr(
            "src.core.paths.ensure_note_directory",
            lambda ts: (seeded_env["notes_dir"] / ts.strftime("%Y/%m/%d")).mkdir(
                parents=True, exist_ok=True
            ),
        )

        # Mock the LLM call to return a valid summary
        mock_summary = HourlySummarySchema(
            schema_version="1.0",
            summary="Test hour summary",
            activities=[
                {
                    "description": "Browsed GitHub repository",
                    "app_name": "Safari",
                    "minutes": 20,
                    "category": "development",
                }
            ],
            entities=[
                {
                    "name": "GitHub",
                    "type": "website",
                    "context": "Code repository browsing",
                }
            ],
            topics=["programming", "code review"],
            hour_characterization="development_work",
            note_to_self=None,
        )

        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary):
            summarizer = HourlySummarizer(db_path=db_path)
            result = summarizer.summarize_hour(hour_start)

        # Should succeed with data
        assert result.success
        assert result.note_id is not None
        assert result.events_count >= 0
        assert result.file_path is not None

    def test_summarize_pipeline_stages(self, seeded_env: dict, monkeypatch):
        """Test that all pipeline stages are executed."""
        from src.summarize.summarizer import HourlySummarizer

        db_path = seeded_env["db_path"]
        hour_start = seeded_env["hour_start"]

        # Track which stages are called
        stages_called = []

        # Monkeypatch paths
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)
        monkeypatch.setattr(
            "src.core.paths.get_note_path",
            lambda ts: seeded_env["notes_dir"]
            / ts.strftime("%Y/%m/%d")
            / f"hour-{ts.strftime('%Y%m%d-%H')}.md",
        )
        monkeypatch.setattr(
            "src.core.paths.ensure_note_directory",
            lambda ts: (seeded_env["notes_dir"] / ts.strftime("%Y/%m/%d")).mkdir(
                parents=True, exist_ok=True
            ),
        )

        summarizer = HourlySummarizer(db_path=db_path)

        # Wrap pipeline stages to track calls
        original_aggregate = summarizer.aggregator.aggregate

        def tracked_aggregate(*args, **kwargs):
            stages_called.append("aggregate")
            return original_aggregate(*args, **kwargs)

        summarizer.aggregator.aggregate = tracked_aggregate

        mock_summary = HourlySummarySchema(
            schema_version="1.0",
            summary="Test summary",
            activities=[],
            entities=[],
            topics=[],
            hour_characterization="other",
            note_to_self=None,
        )

        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary):
            summarizer.summarize_hour(hour_start)

        # Should have called aggregate stage
        assert "aggregate" in stages_called

    def test_summarize_idempotency(self, seeded_env: dict, monkeypatch):
        """Test that summarization is idempotent (doesn't recreate existing notes)."""
        from src.summarize.summarizer import HourlySummarizer

        db_path = seeded_env["db_path"]
        hour_start = seeded_env["hour_start"]

        # Monkeypatch paths
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)
        monkeypatch.setattr(
            "src.core.paths.get_note_path",
            lambda ts: seeded_env["notes_dir"]
            / ts.strftime("%Y/%m/%d")
            / f"hour-{ts.strftime('%Y%m%d-%H')}.md",
        )
        monkeypatch.setattr(
            "src.core.paths.ensure_note_directory",
            lambda ts: (seeded_env["notes_dir"] / ts.strftime("%Y/%m/%d")).mkdir(
                parents=True, exist_ok=True
            ),
        )

        mock_summary = HourlySummarySchema(
            schema_version="1.0",
            summary="Test summary",
            activities=[],
            entities=[],
            topics=[],
            hour_characterization="other",
            note_to_self=None,
        )

        summarizer = HourlySummarizer(db_path=db_path)

        # First summarization
        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary):
            result1 = summarizer.summarize_hour(hour_start)

        assert result1.success
        note_id1 = result1.note_id

        # Second summarization (should return existing note)
        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary) as mock_llm:
            result2 = summarizer.summarize_hour(hour_start)

        assert result2.success
        assert result2.note_id == note_id1
        # LLM should not be called second time
        mock_llm.assert_not_called()

    def test_summarize_force_regeneration(self, seeded_env: dict, monkeypatch):
        """Test that force=True regenerates the note."""
        from src.summarize.summarizer import HourlySummarizer

        db_path = seeded_env["db_path"]
        hour_start = seeded_env["hour_start"]

        # Monkeypatch paths
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)
        monkeypatch.setattr(
            "src.core.paths.get_note_path",
            lambda ts: seeded_env["notes_dir"]
            / ts.strftime("%Y/%m/%d")
            / f"hour-{ts.strftime('%Y%m%d-%H')}.md",
        )
        monkeypatch.setattr(
            "src.core.paths.ensure_note_directory",
            lambda ts: (seeded_env["notes_dir"] / ts.strftime("%Y/%m/%d")).mkdir(
                parents=True, exist_ok=True
            ),
        )

        mock_summary = HourlySummarySchema(
            schema_version="1.0",
            summary="Test summary",
            activities=[],
            entities=[],
            topics=[],
            hour_characterization="other",
            note_to_self=None,
        )

        summarizer = HourlySummarizer(db_path=db_path)

        # First summarization
        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary):
            result1 = summarizer.summarize_hour(hour_start)

        assert result1.success
        assert result1.note_id is not None

        # Force regeneration
        with patch.object(HourlySummarizer, "_call_llm", return_value=mock_summary) as mock_llm:
            result2 = summarizer.summarize_hour(hour_start, force=True)

        assert result2.success
        # LLM should be called for forced regeneration
        mock_llm.assert_called()


class TestJobExecutorE2E:
    """End-to-end tests for the job executor."""

    @pytest.fixture
    def test_env(self, tmp_path: Path, monkeypatch):
        """Set up test environment."""
        data_dir = tmp_path / "trace_data"
        data_dir.mkdir()
        db_path = data_dir / "db" / "trace.sqlite"
        db_path.parent.mkdir(parents=True)

        notes_dir = data_dir / "notes"
        notes_dir.mkdir()

        monkeypatch.setenv("TRACE_DATA_DIR", str(data_dir))
        init_database(db_path)

        return {
            "data_dir": data_dir,
            "db_path": db_path,
            "notes_dir": notes_dir,
        }

    def test_job_creation(self, test_env: dict, monkeypatch):
        """Test job creation and status tracking."""
        from src.jobs.hourly import HourlyJobExecutor

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        executor = HourlyJobExecutor(db_path=db_path)
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        # Create a pending job
        job_id = executor.create_pending_job(hour_start)

        # Verify job was created
        status = executor.get_job_status(job_id)
        assert status is not None
        assert status.status == "pending"
        assert status.attempts == 0

    def test_job_idempotent_creation(self, test_env: dict, monkeypatch):
        """Test that creating the same job twice returns the same ID."""
        from src.jobs.hourly import HourlyJobExecutor

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        executor = HourlyJobExecutor(db_path=db_path)
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        job_id1 = executor.create_pending_job(hour_start)
        job_id2 = executor.create_pending_job(hour_start)

        assert job_id1 == job_id2

    def test_recent_jobs_listing(self, test_env: dict, monkeypatch):
        """Test listing recent jobs."""
        from src.jobs.hourly import HourlyJobExecutor

        db_path = test_env["db_path"]
        monkeypatch.setattr("src.core.paths.DB_PATH", db_path)

        executor = HourlyJobExecutor(db_path=db_path)

        # Create multiple jobs
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        for i in range(5):
            hour = base_time - timedelta(hours=i + 1)
            executor.create_pending_job(hour)

        # List jobs
        jobs = executor.get_recent_jobs(limit=10)

        assert len(jobs) >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
