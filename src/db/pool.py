"""
SQLite Connection Pool for Trace

Provides thread-safe connection pooling for SQLite database access.
This reduces connection overhead and improves performance for
high-frequency database operations.

P13-09: Connection pooling
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from src.core.paths import DB_PATH

logger = logging.getLogger(__name__)


@dataclass
class PoolStats:
    """Statistics about the connection pool."""

    pool_size: int
    available: int
    in_use: int
    total_connections_created: int
    total_acquisitions: int
    total_releases: int
    wait_timeouts: int


class ConnectionPool:
    """
    Thread-safe connection pool for SQLite.

    Features:
    - Configurable pool size
    - Connection reuse
    - Automatic connection validation
    - Thread-local connection tracking
    - Statistics collection
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        pool_size: int = 5,
        max_overflow: int = 10,
        timeout: float = 5.0,
        check_on_borrow: bool = True,
    ):
        """
        Initialize the connection pool.

        Args:
            db_path: Path to SQLite database
            pool_size: Number of connections to keep in pool
            max_overflow: Maximum connections beyond pool_size when busy
            timeout: Seconds to wait for available connection
            check_on_borrow: Whether to validate connections when borrowed
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.timeout = timeout
        self.check_on_borrow = check_on_borrow

        # Pool storage
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()

        # Track connections in use
        self._in_use: set[int] = set()  # Connection id() values

        # Statistics
        self._total_created = 0
        self._total_acquisitions = 0
        self._total_releases = 0
        self._wait_timeouts = 0

        # Initialize pool with connections
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Pre-create connections for the pool."""
        for _ in range(self.pool_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn)
            except Exception as e:
                logger.warning(f"Failed to pre-create connection: {e}")

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,  # Allow connection sharing between threads
            timeout=30.0,  # Wait up to 30s for locks
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better concurrent access
        conn.row_factory = sqlite3.Row

        with self._lock:
            self._total_created += 1

        logger.debug(f"Created new database connection (total: {self._total_created})")
        return conn

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """
        Check if a connection is still valid.

        Args:
            conn: Connection to validate

        Returns:
            True if connection is valid
        """
        try:
            conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def acquire(self) -> sqlite3.Connection:
        """
        Acquire a connection from the pool.

        Returns:
            Database connection

        Raises:
            TimeoutError: If no connection available within timeout
        """
        with self._lock:
            self._total_acquisitions += 1

        start_time = time.time()

        while True:
            try:
                # Try to get from pool
                conn = self._pool.get(timeout=0.1)

                # Validate if configured
                if self.check_on_borrow and not self._validate_connection(conn):
                    logger.debug("Discarding invalid connection from pool")
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = self._create_connection()

                with self._lock:
                    self._in_use.add(id(conn))

                return conn

            except Empty:
                elapsed = time.time() - start_time

                # Check if we can create overflow connection
                with self._lock:
                    current_total = len(self._in_use) + self._pool.qsize()
                    can_overflow = current_total < self.pool_size + self.max_overflow

                if can_overflow:
                    conn = self._create_connection()
                    with self._lock:
                        self._in_use.add(id(conn))
                    return conn

                # Check timeout
                if elapsed >= self.timeout:
                    with self._lock:
                        self._wait_timeouts += 1
                    raise TimeoutError(
                        f"Could not acquire connection within {self.timeout}s"
                    ) from None

    def release(self, conn: sqlite3.Connection) -> None:
        """
        Return a connection to the pool.

        Args:
            conn: Connection to return
        """
        with self._lock:
            self._total_releases += 1
            self._in_use.discard(id(conn))

            # Return to pool if not at capacity
            if self._pool.qsize() < self.pool_size:
                try:
                    self._pool.put_nowait(conn)
                    return
                except Exception:
                    pass

        # Close overflow connections
        try:
            conn.close()
        except Exception:
            pass

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for acquiring and releasing connections.

        Usage:
            with pool.connection() as conn:
                cursor = conn.execute("SELECT ...")

        Yields:
            Database connection
        """
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)

    def get_stats(self) -> PoolStats:
        """Get current pool statistics."""
        with self._lock:
            return PoolStats(
                pool_size=self.pool_size,
                available=self._pool.qsize(),
                in_use=len(self._in_use),
                total_connections_created=self._total_created,
                total_acquisitions=self._total_acquisitions,
                total_releases=self._total_releases,
                wait_timeouts=self._wait_timeouts,
            )

    def close_all(self) -> int:
        """
        Close all connections in the pool.

        Returns:
            Number of connections closed
        """
        closed = 0

        # Close pooled connections
        while True:
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                    closed += 1
                except Exception:
                    pass
            except Empty:
                break

        logger.info(f"Closed {closed} pooled connections")
        return closed


# Global connection pool instance
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool(db_path: Path | str | None = None) -> ConnectionPool:
    """
    Get the global connection pool instance.

    Creates the pool on first call.

    Args:
        db_path: Database path (only used on first call)

    Returns:
        Connection pool instance
    """
    global _pool

    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(db_path=db_path)
            logger.info("Initialized global connection pool")
        return _pool


def close_pool() -> None:
    """Close the global connection pool."""
    global _pool

    with _pool_lock:
        if _pool is not None:
            _pool.close_all()
            _pool = None
            logger.info("Closed global connection pool")


@contextmanager
def get_connection(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Get a connection from the pool.

    This is the recommended way to get database connections.

    Usage:
        with get_connection() as conn:
            cursor = conn.execute("SELECT ...")

    Args:
        db_path: Database path (only used on first pool creation)

    Yields:
        Database connection
    """
    pool = get_pool(db_path)
    with pool.connection() as conn:
        yield conn


if __name__ == "__main__":
    import fire

    def stats(db_path: str | None = None):
        """Show pool statistics."""
        pool = get_pool(db_path)
        return pool.get_stats().__dict__

    def test(iterations: int = 100, db_path: str | None = None):
        """Test the connection pool."""
        pool = get_pool(db_path)

        start = time.time()
        for _ in range(iterations):
            with pool.connection() as conn:
                conn.execute("SELECT 1")

        elapsed = time.time() - start
        stats = pool.get_stats()

        return {
            "iterations": iterations,
            "elapsed_seconds": round(elapsed, 3),
            "avg_ms_per_iteration": round((elapsed / iterations) * 1000, 3),
            "stats": stats.__dict__,
        }

    def close():
        """Close the pool."""
        close_pool()
        return {"closed": True}

    fire.Fire(
        {
            "stats": stats,
            "test": test,
            "close": close,
        }
    )
