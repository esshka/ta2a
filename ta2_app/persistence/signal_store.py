"""Signal persistence layer for audit trails and replay capabilities."""

import hashlib
import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class StoredSignal:
    """Stored signal with metadata."""
    id: int
    plan_id: str
    state: str
    protocol_version: str
    timestamp: str
    signal_data: dict[str, Any]
    created_at: str
    delivery_attempts: int = 0
    last_delivery_attempt: Optional[str] = None
    delivery_status: Optional[str] = None


class SignalStore:
    """SQLite-based signal persistence layer."""

    def __init__(self, db_path: str = "signals.db"):
        self.db_path = Path(db_path)
        self.logger = logging.getLogger("signal.store")
        self._lock = threading.Lock()

        # Create database and tables
        self._init_database()

    def _generate_signal_hash(self, signal: dict[str, Any]) -> str:
        """Generate unique hash for signal deduplication."""
        # Use plan_id, state, and timestamp for uniqueness
        key_data = f"{signal.get('plan_id')}:{signal.get('state')}:{signal.get('timestamp')}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def _init_database(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Check if signal_hash column exists
            cursor = conn.execute("PRAGMA table_info(signals)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'signal_hash' not in columns:
                # Create new table with enhanced schema
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS signals_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        protocol_version TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        signal_data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        delivery_attempts INTEGER DEFAULT 0,
                        last_delivery_attempt TEXT,
                        delivery_status TEXT,
                        signal_hash TEXT,
                        UNIQUE(plan_id, state, timestamp)
                    )
                """)

                # Copy existing data if table exists
                try:
                    conn.execute("""
                        INSERT INTO signals_new (
                            id, plan_id, state, protocol_version, timestamp,
                            signal_data, created_at, delivery_attempts,
                            last_delivery_attempt, delivery_status
                        )
                        SELECT
                            id, plan_id, state, protocol_version, timestamp,
                            signal_data, created_at, delivery_attempts,
                            last_delivery_attempt, delivery_status
                        FROM signals
                    """)

                    # Drop old table and rename new one
                    conn.execute("DROP TABLE signals")
                    conn.execute("ALTER TABLE signals_new RENAME TO signals")

                except Exception:
                    # If old table doesn't exist, just rename new table
                    conn.execute("ALTER TABLE signals_new RENAME TO signals")
            else:
                # Table already has signal_hash column, just ensure it exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        protocol_version TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        signal_data TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        delivery_attempts INTEGER DEFAULT 0,
                        last_delivery_attempt TEXT,
                        delivery_status TEXT,
                        signal_hash TEXT,
                        UNIQUE(plan_id, state, timestamp)
                    )
                """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_plan_id ON signals(plan_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_state ON signals(state)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_hash ON signals(signal_hash)
            """)

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def store_signal(self, signal: dict[str, Any]) -> Optional[int]:
        """
        Store a signal in the database.

        Args:
            signal: Signal dictionary to store

        Returns:
            Signal ID if stored successfully, None otherwise
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    now = datetime.now(timezone.utc).isoformat()

                    signal_hash = self._generate_signal_hash(signal)

                    cursor = conn.execute("""
                        INSERT OR REPLACE INTO signals (
                            plan_id, state, protocol_version, timestamp,
                            signal_data, created_at, signal_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        signal.get("plan_id"),
                        signal.get("state"),
                        signal.get("protocol_version", "unknown"),
                        signal.get("timestamp", now),
                        json.dumps(signal),
                        now,
                        signal_hash
                    ))

                    conn.commit()
                    signal_id = cursor.lastrowid

                    self.logger.info(
                        "Signal stored",
                        plan_id=signal.get("plan_id"),
                        state=signal.get("state"),
                        signal_id=signal_id
                    )

                    return signal_id

            except Exception as e:
                self.logger.error(
                    "Failed to store signal",
                    plan_id=signal.get("plan_id"),
                    state=signal.get("state"),
                    error=str(e)
                )
                return None

    def store_signals(self, signals: list[dict[str, Any]]) -> list[Optional[int]]:
        """
        Store multiple signals in the database.

        Args:
            signals: List of signal dictionaries to store

        Returns:
            List of signal IDs (None for failed stores)
        """
        results = []
        for signal in signals:
            result = self.store_signal(signal)
            results.append(result)
        return results

    def get_signal(self, signal_id: int) -> Optional[StoredSignal]:
        """Get a signal by ID."""
        try:
            with self._get_connection() as conn:
                row = conn.execute("""
                    SELECT * FROM signals WHERE id = ?
                """, (signal_id,)).fetchone()

                if row:
                    return self._row_to_stored_signal(row)
                return None

        except Exception as e:
            self.logger.error(f"Failed to get signal {signal_id}: {str(e)}")
            return None

    def get_signals_by_plan(self, plan_id: str) -> list[StoredSignal]:
        """Get all signals for a specific plan."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM signals WHERE plan_id = ? ORDER BY created_at
                """, (plan_id,)).fetchall()

                return [self._row_to_stored_signal(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get signals for plan {plan_id}: {str(e)}")
            return []

    def get_signals_by_state(self, state: str, limit: int = 100) -> list[StoredSignal]:
        """Get signals by state."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM signals WHERE state = ?
                    ORDER BY created_at DESC LIMIT ?
                """, (state, limit)).fetchall()

                return [self._row_to_stored_signal(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get signals by state {state}: {str(e)}")
            return []

    def get_signals_by_time_range(
        self,
        start_time: str,
        end_time: str,
        limit: int = 1000
    ) -> list[StoredSignal]:
        """Get signals within a time range."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM signals
                    WHERE timestamp BETWEEN ? AND ?
                    ORDER BY timestamp LIMIT ?
                """, (start_time, end_time, limit)).fetchall()

                return [self._row_to_stored_signal(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get signals by time range: {str(e)}")
            return []

    def update_delivery_status(
        self,
        signal_id: int,
        status: str,
        increment_attempts: bool = True
    ) -> bool:
        """Update delivery status for a signal."""
        try:
            with self._get_connection() as conn:
                now = datetime.now(timezone.utc).isoformat()

                if increment_attempts:
                    conn.execute("""
                        UPDATE signals SET
                            delivery_attempts = delivery_attempts + 1,
                            last_delivery_attempt = ?,
                            delivery_status = ?
                        WHERE id = ?
                    """, (now, status, signal_id))
                else:
                    conn.execute("""
                        UPDATE signals SET
                            last_delivery_attempt = ?,
                            delivery_status = ?
                        WHERE id = ?
                    """, (now, status, signal_id))

                conn.commit()
                return True

        except Exception as e:
            self.logger.error(f"Failed to update delivery status: {str(e)}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        try:
            with self._get_connection() as conn:
                # Total signals
                total_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

                # Signals by state
                state_counts = {}
                for row in conn.execute("""
                    SELECT state, COUNT(*) as count FROM signals GROUP BY state
                """):
                    state_counts[row[0]] = row[1]

                # Recent activity (last 24 hours)
                recent_cutoff = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).isoformat()

                recent_count = conn.execute("""
                    SELECT COUNT(*) FROM signals WHERE created_at >= ?
                """, (recent_cutoff,)).fetchone()[0]

                return {
                    "total_signals": total_count,
                    "signals_by_state": state_counts,
                    "recent_24h": recent_count
                }

        except Exception as e:
            self.logger.error(f"Failed to get stats: {str(e)}")
            return {}

    def cleanup_old_signals(self, older_than_days: int = 30) -> int:
        """Remove signals older than specified days."""
        try:
            cutoff_date = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - older_than_days)
            cutoff_str = cutoff_date.isoformat()

            with self._get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM signals WHERE created_at < ?
                """, (cutoff_str,))

                conn.commit()
                deleted_count = cursor.rowcount

                self.logger.info(f"Cleaned up {deleted_count} old signals")
                return deleted_count

        except Exception as e:
            self.logger.error(f"Failed to cleanup old signals: {str(e)}")
            return 0

    def is_signal_duplicate(self, plan_id: str, state: str, timestamp: str) -> bool:
        """Check if signal already exists with same key attributes."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT COUNT(*) FROM signals
                        WHERE plan_id = ? AND state = ? AND timestamp = ?
                    """, (plan_id, state, timestamp))

                    count = cursor.fetchone()[0]
                    return count > 0

            except Exception as e:
                self.logger.error(f"Error checking duplicate signal: {e}")
                return False

    def _row_to_stored_signal(self, row: sqlite3.Row) -> StoredSignal:
        """Convert database row to StoredSignal object."""
        return StoredSignal(
            id=row["id"],
            plan_id=row["plan_id"],
            state=row["state"],
            protocol_version=row["protocol_version"],
            timestamp=row["timestamp"],
            signal_data=json.loads(row["signal_data"]),
            created_at=row["created_at"],
            delivery_attempts=row["delivery_attempts"],
            last_delivery_attempt=row["last_delivery_attempt"],
            delivery_status=row["delivery_status"]
        )
