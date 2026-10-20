"""
Durable local disk-backed event spool for the CV edge pipeline.
Persists unacknowledged outbound events in SQLite with WAL mode to prevent event loss across process crashes, power failures, or network outages.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("cv_pipeline.spool")


class SpoolError(Exception):
    """Base exception for event spooling errors."""
    pass


class SpoolFullError(SpoolError):
    """Raised when the event spool has reached its maximum configured capacity."""
    pass


class EventSpool:
    """
    Thread-safe SQLite-backed durable event spool.
    Guarantees that events are written to persistent storage before delivery attempts,
    and are only removed once the backend confirms successful recording or idempotent duplicate reception.
    """

    def __init__(self, db_path: str | Path, max_events: int = 10000):
        self.db_path = Path(db_path).resolve()
        self.max_events = max_events
        self._lock = threading.Lock()

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initializes WAL mode and creates the outbound spool table and indexes."""
        with self._lock, self._conn:
            cursor = self._conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA busy_timeout = 5000;")
            cursor.execute("PRAGMA synchronous = NORMAL;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outbound_spool (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spool_status_created 
                ON outbound_spool(status, created_at);
            """)

    def enqueue(self, payload: Dict[str, Any]) -> str:
        """
        Durably persists an event into the spool before it is dispatched to the network.
        Raises SpoolFullError if capacity is exceeded, or SpoolError on disk/write failures.
        """
        if not isinstance(payload, dict):
            raise SpoolError("Payload must be a dictionary")

        event_id = payload.get("event_id")
        if not event_id or not isinstance(event_id, str):
            raise SpoolError("Payload must contain a non-empty string 'event_id'")

        now = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload)

        with self._lock:
            try:
                # Capacity guard
                cursor = self._conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM outbound_spool WHERE status IN ('PENDING', 'AUTH_FAILED')")
                current_count = cursor.fetchone()[0]

                if current_count >= self.max_events:
                    raise SpoolFullError(
                        f"Event spool capacity reached ({current_count}/{self.max_events}). "
                        "Cannot enqueue new event until pending events are delivered or cleared."
                    )

                with self._conn:
                    cursor.execute("""
                        INSERT INTO outbound_spool (event_id, payload_json, status, attempts, created_at, updated_at)
                        VALUES (?, ?, 'PENDING', 0, ?, ?)
                        ON CONFLICT(event_id) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            updated_at = excluded.updated_at
                    """, (event_id, payload_str, now, now))

                logger.debug("[Spool] Enqueued and durably persisted event_id: %s", event_id)
                return event_id
            except SpoolFullError:
                raise
            except Exception as e:
                logger.error("[Spool] Failed to enqueue event %s: %s", event_id, e)
                raise SpoolError(f"Persistence error enqueuing event {event_id}: {e}") from e

    def get_pending_events(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieves unacknowledged pending and auth-failed events ordered by creation timestamp.
        Used on startup for automatic recovery of undelivered events.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT payload_json FROM outbound_spool
                WHERE status IN ('PENDING', 'AUTH_FAILED')
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        events = []
        for r in rows:
            try:
                events.append(json.loads(r["payload_json"]))
            except Exception as e:
                logger.warning("[Spool] Corrupted JSON in spool entry: %s", e)
        return events

    def get_pending_count(self) -> int:
        """Returns the total number of unacknowledged events in the spool."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM outbound_spool WHERE status IN ('PENDING', 'AUTH_FAILED')")
            return cursor.fetchone()[0]

    def mark_delivered(self, event_id: str) -> bool:
        """
        Removes an event from the persistent spool once the backend acknowledges receipt.
        Treats both 'Event recorded' (new) and 'Event already processed' (duplicate) as delivered.
        """
        with self._lock:
            try:
                with self._conn:
                    cursor = self._conn.cursor()
                    cursor.execute("DELETE FROM outbound_spool WHERE event_id = ?", (event_id,))
                    deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug("[Spool] Event %s acknowledged by backend and removed from spool.", event_id)
                return deleted
            except Exception as e:
                logger.error("[Spool] Error removing delivered event %s: %s", event_id, e)
                raise SpoolError(f"Error marking event delivered {event_id}: {e}") from e

    def record_attempt(self, event_id: str, status: str = "PENDING", error: Optional[str] = None) -> None:
        """
        Increments the delivery attempt counter and records diagnostic error info.
        Status can be updated to 'AUTH_FAILED' on 401 or kept 'PENDING' on network/5xx errors.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                with self._conn:
                    cursor = self._conn.cursor()
                    cursor.execute("""
                        UPDATE outbound_spool
                        SET attempts = attempts + 1,
                            status = ?,
                            last_error = ?,
                            updated_at = ?
                        WHERE event_id = ?
                    """, (status, str(error)[:500] if error else None, now, event_id))
            except Exception as e:
                logger.warning("[Spool] Failed to record attempt for event %s: %s", event_id, e)

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw spool metadata for a specific event (useful for diagnostic inspection)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                SELECT event_id, status, attempts, created_at, updated_at, last_error, payload_json
                FROM outbound_spool
                WHERE event_id = ?
            """, (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "event_id": row["event_id"],
                "status": row["status"],
                "attempts": row["attempts"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_error": row["last_error"],
                "payload": json.loads(row["payload_json"])
            }

    def health_status(self) -> Dict[str, Any]:
        """
        Returns safe, secret-free health statistics about the spool for operators.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM outbound_spool GROUP BY status")
            counts = dict(cursor.fetchall())
            
            size_bytes = 0
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size

        return {
            "spool_path": str(self.db_path),
            "pending_count": counts.get("PENDING", 0),
            "auth_failed_count": counts.get("AUTH_FAILED", 0),
            "total_unacknowledged": counts.get("PENDING", 0) + counts.get("AUTH_FAILED", 0),
            "max_events": self.max_events,
            "db_size_bytes": size_bytes
        }

    def close(self) -> None:
        """Closes the underlying SQLite database connection cleanly."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
