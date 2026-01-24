"""Command-line interface for Trace."""

import logging
import os
import signal
import sys
import time
from pathlib import Path

import fire
from dotenv import load_dotenv

from src.trace_app.ipc.server import run_server

# Load .env file from project root
_project_root = Path(__file__).parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

logger = logging.getLogger(__name__)


class TraceCLI:
    """Trace CLI commands."""

    def serve(self) -> None:
        """Start the IPC server for Electron communication.

        This command starts the Python backend server that communicates with
        the Electron frontend via stdin/stdout JSON protocol.
        """
        run_server()

    def capture(self, interval: float = 1.0) -> None:
        """Start the capture daemon.

        This captures screenshots, foreground app info, and other activity data.

        Args:
            interval: Capture interval in seconds (default: 1.0)
        """
        from src.capture.daemon import CaptureDaemon
        from src.core.paths import DB_PATH, ensure_data_directories

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        ensure_data_directories()

        daemon = CaptureDaemon(db_path=DB_PATH, capture_interval=interval)

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Stopping capture daemon...")
            daemon.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info(f"Starting capture daemon (interval: {interval}s)")
        daemon.start()

        # Keep main thread alive
        try:
            while daemon._running:
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()

    def hourly(self, run_now: bool = False) -> None:
        """Start the hourly summarization scheduler.

        This runs every hour to generate notes from captured data.

        Args:
            run_now: If True, immediately run summarization for the previous hour
        """
        from src.core.paths import DB_PATH, ensure_data_directories
        from src.jobs.hourly import HourlyJobScheduler

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        ensure_data_directories()

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            sys.exit(1)

        scheduler = HourlyJobScheduler(db_path=DB_PATH, api_key=api_key)

        if run_now:
            logger.info("Running immediate hourly summarization...")
            result = scheduler.trigger_now()
            logger.info(f"Result: success={result.success}, note_id={result.note_id}")
        else:
            logger.info("Starting hourly job scheduler...")
            scheduler.start()

            # Keep running
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                scheduler.stop()

    def daily(self, run_now: bool = False) -> None:
        """Start the daily revision scheduler.

        This runs once per day to revise notes and build the graph.

        Args:
            run_now: If True, immediately run revision for yesterday
        """
        from src.core.paths import DB_PATH, ensure_data_directories
        from src.jobs.daily import DailyJobScheduler

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        ensure_data_directories()

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            sys.exit(1)

        scheduler = DailyJobScheduler(db_path=DB_PATH, api_key=api_key)

        if run_now:
            logger.info("Running immediate daily revision...")
            result = scheduler.trigger_now()
            logger.info(f"Result: success={result.success}, note_id={result.note_id}")
        else:
            logger.info("Starting daily job scheduler...")
            scheduler.start()

            # Keep running
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                scheduler.stop()

    def run_all(self) -> None:
        """Start all background services (capture + hourly + daily schedulers).

        This is the main command to run Trace in the background.
        Includes:
        - Capture daemon for screenshots and activity
        - Hourly summarization scheduler
        - Daily revision scheduler
        - Sleep/wake detection for immediate backfill
        - Startup backfill for any missing hours
        """
        from src.capture.daemon import CaptureDaemon
        from src.core.paths import DB_PATH, ensure_data_directories
        from src.jobs.backfill import BackfillDetector
        from src.jobs.daily import DailyJobScheduler
        from src.jobs.hourly import HourlyJobScheduler
        from src.platform.sleep_wake import SleepWakeDetector

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        ensure_data_directories()

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            sys.exit(1)

        # Start capture daemon
        capture_daemon = CaptureDaemon(db_path=DB_PATH, capture_interval=1.0)

        # Start schedulers
        hourly_scheduler = HourlyJobScheduler(db_path=DB_PATH, api_key=api_key)
        daily_scheduler = DailyJobScheduler(db_path=DB_PATH, api_key=api_key)

        # Initialize backfill detector
        backfill_detector = BackfillDetector(db_path=DB_PATH, api_key=api_key)

        # Initialize sleep/wake detector for immediate recovery
        sleep_wake_detector = SleepWakeDetector()

        def on_wake(wake_time, sleep_duration):
            """Handle system wake - trigger immediate backfill."""
            logger.info(
                f"System woke up after {sleep_duration:.1f}s sleep. Checking for missing notes..."
            )
            # Run backfill in a separate thread to not block the wake handler
            import threading

            def do_backfill():
                try:
                    result = backfill_detector.check_and_backfill(notify=True)
                    if result.hours_backfilled > 0:
                        logger.info(f"Wake recovery: backfilled {result.hours_backfilled} hours")
                except Exception as e:
                    logger.error(f"Wake recovery backfill failed: {e}")

            threading.Thread(target=do_backfill, daemon=True).start()

        sleep_wake_detector.add_wake_callback(on_wake)

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Shutting down all services...")
            sleep_wake_detector.stop()
            capture_daemon.stop()
            hourly_scheduler.stop()
            daily_scheduler.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Starting Trace services...")

        # Start all services
        capture_daemon.start()
        hourly_scheduler.start()
        daily_scheduler.start()
        sleep_wake_detector.start()

        logger.info("All services running. Press Ctrl+C to stop.")

        # Run startup backfill to catch any missing hours from before restart
        logger.info("Running startup backfill check...")
        try:
            startup_result = backfill_detector.check_and_backfill(notify=False)
            if startup_result.hours_backfilled > 0:
                logger.info(
                    f"Startup backfill: created {startup_result.hours_backfilled} missing notes"
                )
            elif startup_result.hours_missing == 0:
                logger.info("Startup backfill: no missing notes found")
        except Exception as e:
            logger.error(f"Startup backfill failed: {e}")

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(None, None)

    def status(self) -> dict:
        """Show current status of captured data."""
        import sqlite3

        from src.core.paths import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM screenshots")
        screenshots = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM events")
        events = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notes")
        notes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'pending'")
        pending_jobs = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(ts) FROM screenshots")
        last_capture = cursor.fetchone()[0]

        conn.close()

        return {
            "screenshots": screenshots,
            "events": events,
            "notes": notes,
            "pending_jobs": pending_jobs,
            "last_capture": last_capture,
        }


def main() -> None:
    """Main entry point for the Trace CLI."""
    fire.Fire(TraceCLI)


if __name__ == "__main__":
    main()
