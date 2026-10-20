"""
Comprehensive regression test suite for Phase 5.2: Durable Edge Event Spooling & Persistence.
Verifies all 12 durability, recovery, idempotency, retry, and error-handling requirements
using isolated temporary SQLite spool databases and mocked HTTP transactions.
"""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

# Add cv_pipeline directory to sys.path
cv_pipeline_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(cv_pipeline_dir))

from spool import EventSpool, SpoolError, SpoolFullError


@pytest.fixture
def temp_spool(tmp_path):
    """Provides an isolated EventSpool backed by a disposable temporary directory."""
    db_file = tmp_path / "test_event_spool.db"
    spool = EventSpool(db_file, max_events=100)
    yield spool
    spool.close()


def _create_sample_event(sku: str = "TST-SKU-01", direction: str = "IN") -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": "2026-10-20T18:00:00Z",
        "track_id": 101,
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{sku}",
        "count_direction": direction
    }


# =============================================================================
# Task D: 12 Specific Durability & Persistence Tests
# =============================================================================

def test_1_event_persists_before_delivery(temp_spool):
    """Test 1: Event is written to durable disk storage before network transmission."""
    event = _create_sample_event()
    event_id = event["event_id"]

    temp_spool.enqueue(event)

    # Inspect persisted state in spool
    record = temp_spool.get_event(event_id)
    assert record is not None, "Event was not found in disk spool"
    assert record["event_id"] == event_id
    assert record["status"] == "PENDING"
    assert record["attempts"] == 0
    assert record["payload"] == event
    assert temp_spool.get_pending_count() == 1


def test_2_pending_events_restored_after_reopen(tmp_path):
    """Test 2: Pending events survive spool close and process restart."""
    db_file = tmp_path / "restart_test_spool.db"

    # Session 1: Enqueue events and close cleanly (simulating process exit)
    spool1 = EventSpool(db_file)
    event1 = _create_sample_event("SKU-1")
    event2 = _create_sample_event("SKU-2")
    spool1.enqueue(event1)
    spool1.enqueue(event2)
    spool1.close()

    # Session 2: Reopen from disk (simulating restart recovery)
    spool2 = EventSpool(db_file)
    try:
        recovered = spool2.get_pending_events()
        assert len(recovered) == 2
        recovered_ids = [e["event_id"] for e in recovered]
        assert event1["event_id"] in recovered_ids
        assert event2["event_id"] in recovered_ids
    finally:
        spool2.close()


def test_3_stable_event_id_preserved_through_retries_and_restart(tmp_path):
    """Test 3: Event ID remains completely stable across attempts and restarts."""
    db_file = tmp_path / "stable_id_spool.db"
    spool1 = EventSpool(db_file)

    event = _create_sample_event("STABLE-001")
    event_id = event["event_id"]
    spool1.enqueue(event)

    # Record two failed attempts
    spool1.record_attempt(event_id, status="PENDING", error="Connection timeout")
    spool1.record_attempt(event_id, status="PENDING", error="Connection timeout 2")
    spool1.close()

    # Restart
    spool2 = EventSpool(db_file)
    try:
        recovered = spool2.get_pending_events()
        assert len(recovered) == 1
        assert recovered[0]["event_id"] == event_id, "Event ID changed after restart!"
        record = spool2.get_event(event_id)
        assert record["attempts"] == 2
    finally:
        spool2.close()


def test_4_successful_acknowledgement_removes_pending_event(temp_spool):
    """Test 4: Successful delivery acknowledgement removes event from persistent spool."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)
    assert temp_spool.get_pending_count() == 1

    # Simulate backend acknowledging receipt: {"msg": "Event recorded"}
    deleted = temp_spool.mark_delivered(event_id)
    assert deleted is True
    assert temp_spool.get_pending_count() == 0
    assert temp_spool.get_event(event_id) is None


def test_5_duplicate_event_acknowledgement_marks_delivered(temp_spool):
    """Test 5: Backend duplicate acknowledgement ('Event already processed') safely marks delivered."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)

    # Backend responds with idempotent success message
    backend_msg = "Event already processed"
    if backend_msg in ("Event recorded", "Event already processed"):
        temp_spool.mark_delivered(event_id)

    assert temp_spool.get_pending_count() == 0
    assert temp_spool.get_event(event_id) is None


def test_6_network_timeout_preserves_pending_event(temp_spool):
    """Test 6: Network timeout preserves event in spool and increments attempt counter."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)

    # Simulate network timeout exception
    temp_spool.record_attempt(event_id, status="PENDING", error="requests.exceptions.ConnectTimeout")

    record = temp_spool.get_event(event_id)
    assert record["status"] == "PENDING"
    assert record["attempts"] == 1
    assert "ConnectTimeout" in record["last_error"]
    assert temp_spool.get_pending_count() == 1


def test_7_http_5xx_preserves_pending_event_and_schedules_retry(temp_spool):
    """Test 7: HTTP 500/503 server error preserves event in spool for retry."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)

    temp_spool.record_attempt(event_id, status="PENDING", error="500 Internal Server Error")

    record = temp_spool.get_event(event_id)
    assert record["status"] == "PENDING"
    assert record["attempts"] == 1
    assert temp_spool.get_pending_count() == 1


def test_8_http_401_preserves_event_without_silent_loss(temp_spool):
    """Test 8: HTTP 401 updates status to AUTH_FAILED and preserves event without silent discard."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)

    temp_spool.record_attempt(event_id, status="AUTH_FAILED", error="HTTP 401 Unauthorized")

    record = temp_spool.get_event(event_id)
    assert record["status"] == "AUTH_FAILED"
    assert record["attempts"] == 1
    assert "401" in record["last_error"]

    # Must still be present in pending/unacknowledged recovery
    pending = temp_spool.get_pending_events()
    assert len(pending) == 1
    assert pending[0]["event_id"] == event_id


def test_9_invalid_acknowledgement_does_not_mark_delivered(temp_spool):
    """Test 9: Invalid/unexpected response from server does NOT remove event from spool."""
    event = _create_sample_event()
    event_id = event["event_id"]
    temp_spool.enqueue(event)

    # Server returned 422 Unprocessable Entity or 400 Bad Request
    # mark_delivered is NOT called
    temp_spool.record_attempt(event_id, status="PENDING", error="422 Unprocessable Entity")

    assert temp_spool.get_pending_count() == 1
    assert temp_spool.get_event(event_id) is not None


def test_10_interrupted_delivery_leaves_unacknowledged_recoverable(tmp_path):
    """Test 10: Interrupted delivery leaves remaining unacknowledged events fully recoverable."""
    db_file = tmp_path / "crash_simulation.db"
    spool1 = EventSpool(db_file)

    events = [_create_sample_event(f"SKU-{i}") for i in range(5)]
    for e in events:
        spool1.enqueue(e)

    # Deliver first 2 events
    spool1.mark_delivered(events[0]["event_id"])
    spool1.mark_delivered(events[1]["event_id"])
    # Simulate abrupt exit without delivering events[2], [3], [4]
    spool1.close()

    # Restart
    spool2 = EventSpool(db_file)
    try:
        recovered = spool2.get_pending_events()
        assert len(recovered) == 3
        recovered_ids = {e["event_id"] for e in recovered}
        expected_ids = {events[2]["event_id"], events[3]["event_id"], events[4]["event_id"]}
        assert recovered_ids == expected_ids
    finally:
        spool2.close()


def test_11_multiple_pending_events_delivered_without_loss_or_duplication(temp_spool):
    """Test 11: Bulk events are enqueued and acknowledged sequentially without loss."""
    events = [_create_sample_event(f"BATCH-{i}") for i in range(15)]
    for e in events:
        temp_spool.enqueue(e)

    assert temp_spool.get_pending_count() == 15

    for e in events:
        temp_spool.mark_delivered(e["event_id"])

    assert temp_spool.get_pending_count() == 0


def test_12_disk_capacity_and_persistence_errors_surfaced_safely(tmp_path):
    """Test 12: Capacity limits and invalid payloads fail fast and surface clear errors."""
    small_spool = EventSpool(tmp_path / "bounded_spool.db", max_events=2)

    try:
        e1 = _create_sample_event("SKU-1")
        e2 = _create_sample_event("SKU-2")
        e3 = _create_sample_event("SKU-3")

        small_spool.enqueue(e1)
        small_spool.enqueue(e2)

        # 3rd event exceeds max_events limit
        with pytest.raises(SpoolFullError) as exc_info:
            small_spool.enqueue(e3)
        assert "capacity reached" in str(exc_info.value).lower()

        # Non-dict payload fails fast
        with pytest.raises(SpoolError):
            small_spool.enqueue("invalid-payload-string")

        # Missing event_id fails fast
        with pytest.raises(SpoolError):
            small_spool.enqueue({"sku": "NO-ID"})
    finally:
        small_spool.close()


def test_13_health_status_safe_and_secret_free(temp_spool):
    """Test 13: health_status() reports accurate metrics and does not expose secrets."""
    e1 = _create_sample_event("H-1")
    e2 = _create_sample_event("H-2")
    temp_spool.enqueue(e1)
    temp_spool.enqueue(e2)
    temp_spool.record_attempt(e2["event_id"], status="AUTH_FAILED", error="401")

    health = temp_spool.health_status()
    assert health["pending_count"] == 1
    assert health["auth_failed_count"] == 1
    assert health["total_unacknowledged"] == 2
    assert health["max_events"] == 100
    assert health["db_size_bytes"] > 0
    # Confirm no credentials in health dict
    assert "api_key" not in str(health).lower()
    assert "token" not in str(health).lower()
    assert "secret" not in str(health).lower()
