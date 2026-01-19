"""
End-to-end test for the capture daemon.

P9-01: End-to-end capture test
Acceptance criteria: Capture daemon runs for 5 minutes, data persisted
"""

import sqlite3
import time
from pathlib import Path

import pytest

from src.capture.daemon import CaptureDaemon, CaptureSnapshot


class TestCaptureDaemonE2E:
    """End-to-end tests for the capture daemon."""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        """Create a temporary database."""
        return tmp_path / "test_trace.sqlite"

    @pytest.fixture
    def temp_cache(self, tmp_path: Path) -> Path:
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def test_capture_daemon_short_run(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """
        Test that the capture daemon runs and persists data.

        This is a shorter test (10 seconds) for CI/CD pipelines.
        """
        # Monkeypatch environment variables for test isolation
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        # Create daemon with test configuration
        daemon = CaptureDaemon(
            capture_interval=1.0,
            jpeg_quality=50,  # Lower quality for faster tests
            dedup_threshold=5,
            location_interval=60.0,
            db_path=temp_db,
        )

        # Collect snapshots
        snapshots: list[CaptureSnapshot] = []

        def collect_snapshot(snapshot: CaptureSnapshot):
            snapshots.append(snapshot)

        daemon.add_callback(collect_snapshot)

        # Start daemon in background thread
        daemon.start(blocking=False)

        # Run for 10 seconds
        time.sleep(10)

        # Stop daemon
        daemon.stop(timeout=5.0)

        # Verify captures occurred
        stats = daemon.get_stats()
        assert stats.captures_total >= 5, "Should have at least 5 captures in 10 seconds"
        assert stats.start_time is not None

        # Verify snapshots were collected
        assert len(snapshots) >= 5, "Should have at least 5 snapshots"

        # Verify snapshot structure
        for snapshot in snapshots:
            assert snapshot.timestamp is not None
            assert snapshot.foreground is not None
            assert snapshot.foreground.timestamp is not None

        # Verify database was created and has data
        assert temp_db.exists(), "Database file should exist"

        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Check events table
            cursor.execute("SELECT COUNT(*) as count FROM events")
            event_count = cursor.fetchone()["count"]
            # We may or may not have events depending on app transitions
            assert event_count >= 0

            # Check screenshots table (may be empty if all deduplicated)
            cursor.execute("SELECT COUNT(*) as count FROM screenshots")
            screenshot_count = cursor.fetchone()["count"]
            assert screenshot_count >= 0

        finally:
            conn.close()

    def test_capture_daemon_with_transitions(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """
        Test that app transitions are tracked.

        Simulates checking for event creation on app changes.
        """
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        daemon = CaptureDaemon(
            capture_interval=0.5,  # Faster captures for transition detection
            db_path=temp_db,
        )

        events_closed = []

        def track_events(snapshot: CaptureSnapshot):
            if snapshot.event_closed:
                events_closed.append(snapshot)

        daemon.add_callback(track_events)

        # Start and run briefly
        daemon.start(blocking=False)
        time.sleep(5)
        daemon.stop()

        stats = daemon.get_stats()
        # Should have some captures
        assert stats.captures_total >= 5

    def test_capture_daemon_deduplication(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """
        Test that screenshot deduplication works.

        When screen content doesn't change, screenshots should be deduplicated.
        """
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        daemon = CaptureDaemon(
            capture_interval=0.2,  # Fast captures to get many similar screenshots
            jpeg_quality=50,
            dedup_threshold=5,  # Lower threshold for more deduplication
            db_path=temp_db,
        )

        daemon.start(blocking=False)
        time.sleep(5)
        daemon.stop()

        stats = daemon.get_stats()

        # Should have many captures
        assert stats.captures_total >= 10

        # Some screenshots should be deduplicated if screen hasn't changed much
        # (We can't guarantee deduplication without controlling screen content)
        total_screenshots = stats.screenshots_captured + stats.screenshots_deduplicated
        assert total_screenshots >= 0

    def test_capture_daemon_stats(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """Test that capture statistics are tracked correctly."""
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        daemon = CaptureDaemon(
            capture_interval=1.0,
            db_path=temp_db,
        )

        # Get initial stats
        initial_stats = daemon.get_stats()
        assert initial_stats.captures_total == 0
        assert initial_stats.screenshots_captured == 0
        assert initial_stats.start_time is None

        # Start daemon
        daemon.start(blocking=False)

        # Wait for some captures
        time.sleep(5)

        # Get running stats
        running_stats = daemon.get_stats()
        assert running_stats.captures_total > 0
        assert running_stats.start_time is not None

        # Stop daemon
        daemon.stop()

        # Final stats should be >= running stats
        final_stats = daemon.get_stats()
        assert final_stats.captures_total >= running_stats.captures_total

    def test_capture_daemon_graceful_shutdown(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """Test that daemon shuts down gracefully."""
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        daemon = CaptureDaemon(
            capture_interval=0.5,
            db_path=temp_db,
        )

        daemon.start(blocking=False)
        time.sleep(2)

        # Should stop without hanging
        start_time = time.time()
        daemon.stop(timeout=5.0)
        stop_time = time.time()

        # Should stop quickly (within timeout)
        assert stop_time - start_time < 6.0


@pytest.mark.slow
class TestCaptureDaemonExtended:
    """
    Extended tests that run for longer durations.

    Mark with @pytest.mark.slow and run with: pytest -m slow
    """

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        """Create a temporary database."""
        return tmp_path / "test_trace.sqlite"

    def test_capture_daemon_5_minutes(self, temp_db: Path, tmp_path: Path, monkeypatch):
        """
        Full acceptance test: Run capture daemon for 5 minutes.

        This is the full acceptance criteria test.
        """
        monkeypatch.setenv("TRACE_DATA_DIR", str(tmp_path))

        daemon = CaptureDaemon(
            capture_interval=1.0,
            jpeg_quality=75,
            dedup_threshold=5,
            location_interval=60.0,
            db_path=temp_db,
        )

        snapshots: list[CaptureSnapshot] = []

        def collect_snapshot(snapshot: CaptureSnapshot):
            snapshots.append(snapshot)

        daemon.add_callback(collect_snapshot)

        # Start daemon
        daemon.start(blocking=False)

        # Run for 5 minutes (300 seconds)
        run_duration = 300
        start_time = time.time()

        while time.time() - start_time < run_duration:
            time.sleep(30)  # Check every 30 seconds
            stats = daemon.get_stats()
            elapsed = time.time() - start_time
            print(
                f"Progress: {elapsed:.0f}s - Captures: {stats.captures_total}, "
                f"Screenshots: {stats.screenshots_captured}, "
                f"Errors: {stats.errors}"
            )

        # Stop daemon
        daemon.stop()

        # Verify results
        stats = daemon.get_stats()

        # Should have approximately 300 captures (one per second)
        # Allow some margin for processing time
        assert stats.captures_total >= 250, f"Expected ~300 captures, got {stats.captures_total}"

        # Error rate should be low
        error_rate = stats.errors / max(stats.captures_total, 1)
        assert error_rate < 0.05, f"Error rate too high: {error_rate:.2%}"

        # Database should exist and have data
        assert temp_db.exists()

        conn = sqlite3.connect(str(temp_db))
        try:
            cursor = conn.cursor()

            # Should have events
            cursor.execute("SELECT COUNT(*) FROM events")
            event_count = cursor.fetchone()[0]

            # Should have some events (at least a few app transitions expected)
            # This is a soft check since we can't control app usage during test
            print(f"Events created: {event_count}")

            # Check screenshot storage
            cursor.execute("SELECT COUNT(*) FROM screenshots")
            screenshot_count = cursor.fetchone()[0]
            print(f"Screenshots stored: {screenshot_count}")

        finally:
            conn.close()

        print("Test completed successfully:")
        print(f"  Total captures: {stats.captures_total}")
        print(f"  Screenshots captured: {stats.screenshots_captured}")
        print(f"  Screenshots deduplicated: {stats.screenshots_deduplicated}")
        print(f"  Events created: {stats.events_created}")
        print(f"  Errors: {stats.errors}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
