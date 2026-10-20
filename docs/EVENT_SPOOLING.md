# Durable Edge Event Spooling & Persistence Guide

## 1. Overview
The Computer Vision Edge Pipeline features a local, crash-resilient SQLite-backed event spool implemented in `cv_pipeline/spool.py`.

Prior to Phase 5.2, events were buffered exclusively in volatile process memory (`queue.Queue`), introducing a risk of event loss during power outages, machine crashes, or unexpected process termination. The durable event spool eliminates this vulnerability by persisting all outbound inventory line-crossing events to disk **before** attempting network delivery.

---

## 2. Configuration & Spool Location

The spool database location and capacity limits are configured in `cv_pipeline/.env` or via environment variables:

| Variable | Default Value | Description |
|---|---|---|
| `EVENT_SPOOL_PATH` | `data/event_spool.db` | Relative (to `cv_pipeline/`) or absolute filesystem path to the SQLite spool database file. |
| `EVENT_SPOOL_MAX_SIZE` | `10000` | Maximum number of pending/unacknowledged events allowed before rejecting new events (`SpoolFullError`). |

### Example `.env` Configuration
```bash
# In cv_pipeline/.env
EVENT_SPOOL_PATH=data/event_spool.db
EVENT_SPOOL_MAX_SIZE=10000
```

---

## 3. Storage Architecture & Durability Guarantees

1. **Write-Ahead Logging (WAL Mode):**
   The spool operates with `PRAGMA journal_mode = WAL;` and `PRAGMA synchronous = NORMAL;`. This provides:
   - Atomic multi-statement writes.
   - Immediate visibility across concurrent threads.
   - Durability against sudden process crashes.
2. **Schema:**
   - Table `outbound_spool` contains:
     - `event_id` (TEXT PRIMARY KEY, UUIDv4)
     - `payload_json` (TEXT NOT NULL, complete event payload)
     - `status` (TEXT NOT NULL, `PENDING` or `AUTH_FAILED`)
     - `attempts` (INTEGER NOT NULL, delivery attempt count)
     - `created_at` (TEXT NOT NULL, ISO 8601 UTC timestamp)
     - `updated_at` (TEXT NOT NULL, ISO 8601 UTC timestamp)
     - `last_error` (TEXT, truncated error message for diagnostics)
3. **No Secrets in Spool:**
   Event payloads contain only inventory tracking metadata (`event_id`, `timestamp`, `track_id`, `qr_status`, `qr_payload`, `count_direction`). The `EDGE_NODE_API_KEY` is **never** written to the database.

---

## 4. Lifecycle & Delivery Behavior

### A. Enqueue Before Transmission
When a box crosses the detection line, the pipeline generates a stable UUIDv4 `event_id` and persists the payload into `outbound_spool` before dispatching it to the background delivery worker. If disk persistence fails, the event is visibly logged as an error and not claimed as queued.

### B. Confirmed Delivery & Deduplication
- Upon receiving `HTTP 200` with `{"msg": "Event recorded"}` from the backend, the event is removed from the spool.
- If the event was previously received but the acknowledgement was lost in transit, the backend's duplicate detection catches `DuplicateKeyError` and responds with `HTTP 200 {"msg": "Event already processed"}`. The spool treats this as successful delivery and removes the event. Inventory is never double-counted.

### C. Transient Network & Server Errors
- Connection timeouts, DNS failures, and HTTP 5xx responses do not discard the event.
- The spool increments `attempts`, logs a sanitized warning, updates `last_error`, and retries with backoff.

### D. Authentication Errors (`HTTP 401`)
- If the backend rejects `EDGE_NODE_API_KEY`, the event is marked `status = 'AUTH_FAILED'` and `last_error = 'HTTP 401 Unauthorized'`.
- The worker does not loop endlessly. It retries up to `MAX_AUTH_RETRIES` (3 times) with backoff before preserving the event and advancing the queue.
- The event remains safely stored in the database. Once `.env` is corrected and the pipeline is restarted, the event is automatically recovered and delivered.

### E. Startup Recovery
On pipeline launch, `spool.get_pending_events()` queries all unacknowledged events (`status IN ('PENDING', 'AUTH_FAILED')`) ordered by `created_at ASC` and feeds them into the delivery queue before processing live camera frames.

---

## 5. Operator Health Inspection (Secret-Free)

Operators can check spool health from the Python CLI or a monitoring script without exposing credentials:

```python
from cv_pipeline.config import settings
from cv_pipeline.spool import EventSpool

spool = EventSpool(settings.EVENT_SPOOL_PATH)
status = spool.health_status()
print(status)
# Output example:
# {
#     "spool_path": "C:\\...\\cv_pipeline\\data\\event_spool.db",
#     "pending_count": 0,
#     "auth_failed_count": 0,
#     "total_unacknowledged": 0,
#     "max_events": 10000,
#     "db_size_bytes": 32768
# }
```

---

## 6. Backup & Capacity Considerations

- **Database Size:** In steady state, events are deleted upon delivery, keeping `outbound_spool` virtually empty and database file size minimal (typically under 100 KB).
- **Network Outage Backlog:** If the backend is unreachable for an extended period, the spool buffers up to `EVENT_SPOOL_MAX_SIZE` (10,000 events by default, consuming ~5 MB of disk space).
- **Backup:** If backing up an edge node machine while running, use SQLite online backup API (`sqlite3.Connection.backup`) or snapshot the database while the pipeline is stopped.

---

## 7. Safe Maintenance & Spool Clearing Procedures

> [!CAUTION]
> Never delete `event_spool.db` casually while unacknowledged events are pending. Doing so will result in permanent loss of unrecorded inventory counts.

### Verification Before Maintenance
1. Check `spool.get_pending_count()`. If `pending_count == 0`, the spool is completely clean and all events have been safely recorded by the backend.
2. If `pending_count > 0`, investigate why events are not delivering:
   - Check backend health: `GET /api/health`.
   - Check edge node key: verify `EDGE_NODE_API_KEY` in `cv_pipeline/.env` matches `backend/.env`.
   - Start `run_pipeline.py` or inspect logs to allow pending events to drain.

### Re-initializing Spool (Only If Database File Corrupted)
1. Stop the pipeline process (`Ctrl+C`).
2. Rename the database file for forensics:
   ```powershell
   Move-Item cv_pipeline\data\event_spool.db cv_pipeline\data\event_spool_corrupt_backup.db
   ```
3. Restart `cv_pipeline`. The spool module will automatically initialize a fresh `event_spool.db` with proper tables and WAL journal mode.
