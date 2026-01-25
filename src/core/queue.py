"""
Offline Operation Queue for Trace

Provides a persistent queue for operations when the OpenAI API is unavailable.
Operations are queued and processed when connectivity is restored.

P13-04: Offline/fallback mode
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from src.core.paths import DB_PATH

logger = logging.getLogger(__name__)


class OperationType(str, Enum):
    """Types of operations that can be queued."""

    HOURLY_SUMMARIZE = "hourly_summarize"
    DAILY_REVISION = "daily_revision"
    EMBEDDING_COMPUTE = "embedding_compute"
    CHAT_QUERY = "chat_query"


class QueueStatus(str, Enum):
    """Status of queued operations."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedOperation:
    """Represents a queued operation."""

    operation_id: str
    operation_type: OperationType
    payload: dict
    status: QueueStatus
    priority: int
    attempts: int
    max_attempts: int
    last_error: str | None
    created_ts: datetime
    scheduled_ts: datetime | None
    completed_ts: datetime | None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "payload": self.payload,
            "status": self.status.value,
            "priority": self.priority,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "created_ts": self.created_ts.isoformat() if self.created_ts else None,
            "scheduled_ts": self.scheduled_ts.isoformat() if self.scheduled_ts else None,
            "completed_ts": self.completed_ts.isoformat() if self.completed_ts else None,
        }


class OfflineQueue:
    """
    Persistent queue for operations when API is unavailable.

    Features:
    - SQLite-backed persistence
    - Priority-based processing
    - Retry with backoff
    - Connectivity monitoring
    """

    # Schema for offline queue table
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS offline_queue (
        operation_id TEXT PRIMARY KEY,
        operation_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        priority INTEGER NOT NULL DEFAULT 5,
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        last_error TEXT,
        created_ts TEXT NOT NULL DEFAULT (datetime('now')),
        scheduled_ts TEXT,
        completed_ts TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_queue_status ON offline_queue(status);
    CREATE INDEX IF NOT EXISTS idx_queue_priority ON offline_queue(priority, created_ts);
    CREATE INDEX IF NOT EXISTS idx_queue_type ON offline_queue(operation_type);
    """

    def __init__(self, db_path: Path | str | None = None):
        """
        Initialize the offline queue.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._online = True
        self._last_connectivity_check = datetime.min
        self._connectivity_check_interval = timedelta(seconds=30)
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize the queue table."""
        conn = self._get_connection()
        try:
            conn.executescript(self.SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def is_online(self) -> bool:
        """
        Check if API connectivity is available.

        Uses cached result within connectivity check interval.

        Returns:
            True if online, False otherwise
        """
        now = datetime.now()
        if now - self._last_connectivity_check < self._connectivity_check_interval:
            return self._online

        self._last_connectivity_check = now
        self._online = self._check_connectivity()
        return self._online

    def _check_connectivity(self) -> bool:
        """
        Actually check API connectivity.

        Returns:
            True if API is reachable
        """
        try:
            import httpx

            # Quick check to OpenAI API
            response = httpx.head(
                "https://api.openai.com/v1/models",
                timeout=5.0,
            )
            return response.status_code in (
                200,
                401,
                403,
            )  # 401/403 means reachable but auth failed
        except Exception:
            return False

    def set_online_status(self, online: bool) -> None:
        """
        Manually set online status.

        Useful for testing or when connectivity is known.

        Args:
            online: Online status
        """
        with self._lock:
            self._online = online
            self._last_connectivity_check = datetime.now()

    def enqueue(
        self,
        operation_type: OperationType,
        payload: dict,
        priority: int = 5,
        max_attempts: int = 3,
        scheduled_ts: datetime | None = None,
    ) -> str:
        """
        Add an operation to the queue.

        Args:
            operation_type: Type of operation
            payload: Operation payload data
            priority: Priority (1=highest, 10=lowest)
            max_attempts: Maximum retry attempts
            scheduled_ts: When to process (None = immediately)

        Returns:
            Operation ID
        """
        operation_id = str(uuid.uuid4())

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO offline_queue
                (operation_id, operation_type, payload, status, priority,
                 attempts, max_attempts, created_ts, scheduled_ts)
                VALUES (?, ?, ?, 'pending', ?, 0, ?, ?, ?)
                """,
                (
                    operation_id,
                    operation_type.value,
                    json.dumps(payload),
                    priority,
                    max_attempts,
                    datetime.now().isoformat(),
                    scheduled_ts.isoformat() if scheduled_ts else None,
                ),
            )
            conn.commit()

            logger.info(f"Queued operation {operation_id} ({operation_type.value})")
            return operation_id

        finally:
            conn.close()

    def get_pending(
        self,
        operation_type: OperationType | None = None,
        limit: int = 100,
    ) -> list[QueuedOperation]:
        """
        Get pending operations ready for processing.

        Args:
            operation_type: Filter by type (None = all)
            limit: Maximum operations to return

        Returns:
            List of pending operations
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            if operation_type:
                cursor.execute(
                    """
                    SELECT * FROM offline_queue
                    WHERE status = 'pending'
                    AND operation_type = ?
                    AND (scheduled_ts IS NULL OR scheduled_ts <= ?)
                    AND attempts < max_attempts
                    ORDER BY priority ASC, created_ts ASC
                    LIMIT ?
                    """,
                    (operation_type.value, now, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM offline_queue
                    WHERE status = 'pending'
                    AND (scheduled_ts IS NULL OR scheduled_ts <= ?)
                    AND attempts < max_attempts
                    ORDER BY priority ASC, created_ts ASC
                    LIMIT ?
                    """,
                    (now, limit),
                )

            return [self._row_to_operation(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_operation(self, operation_id: str) -> QueuedOperation | None:
        """Get a specific operation by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM offline_queue WHERE operation_id = ?",
                (operation_id,),
            )
            row = cursor.fetchone()
            return self._row_to_operation(row) if row else None
        finally:
            conn.close()

    def mark_processing(self, operation_id: str) -> bool:
        """
        Mark an operation as currently processing.

        Returns:
            True if successfully marked
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offline_queue
                SET status = 'processing', attempts = attempts + 1
                WHERE operation_id = ? AND status = 'pending'
                """,
                (operation_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def mark_completed(self, operation_id: str, result: Any = None) -> None:
        """Mark an operation as completed."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offline_queue
                SET status = 'completed', completed_ts = ?
                WHERE operation_id = ?
                """,
                (datetime.now().isoformat(), operation_id),
            )
            conn.commit()
            logger.info(f"Operation {operation_id} completed")
        finally:
            conn.close()

    def mark_failed(
        self,
        operation_id: str,
        error: str,
        retry_delay: timedelta | None = None,
    ) -> None:
        """
        Mark an operation as failed.

        If retry is possible, schedules for later. Otherwise marks as failed.

        Args:
            operation_id: Operation ID
            error: Error message
            retry_delay: Delay before retry (None = no retry)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get current attempts
            cursor.execute(
                "SELECT attempts, max_attempts FROM offline_queue WHERE operation_id = ?",
                (operation_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return

            if row["attempts"] >= row["max_attempts"]:
                # Max attempts reached, mark as failed
                cursor.execute(
                    """
                    UPDATE offline_queue
                    SET status = 'failed', last_error = ?, completed_ts = ?
                    WHERE operation_id = ?
                    """,
                    (error, datetime.now().isoformat(), operation_id),
                )
                logger.warning(f"Operation {operation_id} failed permanently: {error}")
            elif retry_delay:
                # Schedule retry
                scheduled_ts = datetime.now() + retry_delay
                cursor.execute(
                    """
                    UPDATE offline_queue
                    SET status = 'pending', last_error = ?, scheduled_ts = ?
                    WHERE operation_id = ?
                    """,
                    (error, scheduled_ts.isoformat(), operation_id),
                )
                logger.info(f"Operation {operation_id} scheduled for retry at {scheduled_ts}")
            else:
                # Return to pending for immediate retry
                cursor.execute(
                    """
                    UPDATE offline_queue
                    SET status = 'pending', last_error = ?
                    WHERE operation_id = ?
                    """,
                    (error, operation_id),
                )

            conn.commit()

        finally:
            conn.close()

    def cancel(self, operation_id: str) -> bool:
        """
        Cancel a pending operation.

        Returns:
            True if cancelled
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offline_queue
                SET status = 'cancelled', completed_ts = ?
                WHERE operation_id = ? AND status = 'pending'
                """,
                (datetime.now().isoformat(), operation_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_queue_stats(self) -> dict:
        """Get queue statistics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            stats = {
                "total": 0,
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
                "by_type": {},
            }

            # Count by status
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM offline_queue
                GROUP BY status
                """
            )
            for row in cursor.fetchall():
                stats[row["status"]] = row["count"]
                stats["total"] += row["count"]

            # Count by type
            cursor.execute(
                """
                SELECT operation_type, COUNT(*) as count
                FROM offline_queue
                WHERE status = 'pending'
                GROUP BY operation_type
                """
            )
            for row in cursor.fetchall():
                stats["by_type"][row["operation_type"]] = row["count"]

            return stats

        finally:
            conn.close()

    def cleanup_old(self, days: int = 7) -> int:
        """
        Remove old completed/failed/cancelled operations.

        Args:
            days: Remove operations older than this

        Returns:
            Number of operations removed
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM offline_queue
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_ts < ?
                """,
                (cutoff,),
            )
            count = cursor.rowcount
            conn.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} old queue entries")

            return count

        finally:
            conn.close()

    def _row_to_operation(self, row: sqlite3.Row) -> QueuedOperation:
        """Convert a database row to QueuedOperation."""
        return QueuedOperation(
            operation_id=row["operation_id"],
            operation_type=OperationType(row["operation_type"]),
            payload=json.loads(row["payload"]),
            status=QueueStatus(row["status"]),
            priority=row["priority"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            last_error=row["last_error"],
            created_ts=datetime.fromisoformat(row["created_ts"]) if row["created_ts"] else None,
            scheduled_ts=datetime.fromisoformat(row["scheduled_ts"])
            if row["scheduled_ts"]
            else None,
            completed_ts=datetime.fromisoformat(row["completed_ts"])
            if row["completed_ts"]
            else None,
        )


class QueueProcessor:
    """
    Background processor for the offline queue.

    Monitors connectivity and processes queued operations
    when the API becomes available.
    """

    def __init__(
        self,
        queue: OfflineQueue,
        check_interval: float = 30.0,
        batch_size: int = 10,
    ):
        """
        Initialize the queue processor.

        Args:
            queue: OfflineQueue instance
            check_interval: Seconds between connectivity checks
            batch_size: Operations to process per batch
        """
        self.queue = queue
        self.check_interval = check_interval
        self.batch_size = batch_size

        self._running = False
        self._thread: threading.Thread | None = None
        self._handlers: dict[OperationType, callable] = {}

    def register_handler(
        self,
        operation_type: OperationType,
        handler: callable,
    ) -> None:
        """
        Register a handler for an operation type.

        The handler should accept (payload: dict) and return success: bool.

        Args:
            operation_type: Type of operation to handle
            handler: Handler function
        """
        self._handlers[operation_type] = handler

    def start(self) -> None:
        """Start the background processor."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info("Queue processor started")

    def stop(self) -> None:
        """Stop the background processor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Queue processor stopped")

    def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                if self.queue.is_online():
                    self._process_batch()
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

            time.sleep(self.check_interval)

    def _process_batch(self) -> int:
        """
        Process a batch of pending operations.

        Returns:
            Number of operations processed
        """
        operations = self.queue.get_pending(limit=self.batch_size)
        processed = 0

        for op in operations:
            if not self._running:
                break

            handler = self._handlers.get(op.operation_type)
            if not handler:
                logger.warning(f"No handler for operation type: {op.operation_type}")
                continue

            if not self.queue.mark_processing(op.operation_id):
                continue  # Already being processed

            try:
                result = handler(op.payload)
                if result:
                    self.queue.mark_completed(op.operation_id, result)
                else:
                    self.queue.mark_failed(
                        op.operation_id,
                        "Handler returned False",
                        retry_delay=timedelta(minutes=5),
                    )
                processed += 1

            except Exception as e:
                logger.error(f"Operation {op.operation_id} failed: {e}")
                self.queue.mark_failed(
                    op.operation_id,
                    str(e),
                    retry_delay=timedelta(minutes=5),
                )

        return processed

    def process_now(self) -> int:
        """
        Process pending operations immediately.

        Returns:
            Number of operations processed
        """
        total = 0
        while True:
            processed = self._process_batch()
            if processed == 0:
                break
            total += processed
        return total


if __name__ == "__main__":
    import fire

    def stats(db_path: str | None = None):
        """Show queue statistics."""
        queue = OfflineQueue(db_path=db_path)
        return queue.get_queue_stats()

    def pending(db_path: str | None = None, limit: int = 10):
        """Show pending operations."""
        queue = OfflineQueue(db_path=db_path)
        operations = queue.get_pending(limit=limit)
        return [op.to_dict() for op in operations]

    def enqueue(
        operation_type: str,
        payload: str,
        priority: int = 5,
        db_path: str | None = None,
    ):
        """
        Enqueue an operation.

        Args:
            operation_type: Type (hourly_summarize, daily_revision, etc.)
            payload: JSON payload string
            priority: Priority (1-10)
            db_path: Path to database
        """
        queue = OfflineQueue(db_path=db_path)
        op_type = OperationType(operation_type)
        payload_dict = json.loads(payload)
        op_id = queue.enqueue(op_type, payload_dict, priority=priority)
        return {"operation_id": op_id}

    def cleanup(days: int = 7, db_path: str | None = None):
        """Clean up old operations."""
        queue = OfflineQueue(db_path=db_path)
        count = queue.cleanup_old(days=days)
        return {"removed": count}

    def check_online(db_path: str | None = None):
        """Check API connectivity."""
        queue = OfflineQueue(db_path=db_path)
        return {"online": queue.is_online()}

    fire.Fire(
        {
            "stats": stats,
            "pending": pending,
            "enqueue": enqueue,
            "cleanup": cleanup,
            "online": check_online,
        }
    )
