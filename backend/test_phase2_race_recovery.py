import sys
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pymongo.errors import DuplicateKeyError
import certifi
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

sys.path.append(".")
from app.main import app
from app.core.config import settings
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database
from app.services.alerts import evaluate_qr_exception_alert
from app.core.security import get_password_hash, create_access_token

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase2_recovery")
settings.MONGODB_DB_NAME = TEST_DB_NAME

def make_mock_db(events_list):
    mock_db = {}
    mock_events = MagicMock()
    cursor = AsyncMock()
    cursor.to_list = AsyncMock(return_value=events_list)
    mock_events.find = MagicMock(return_value=cursor)
    mock_alerts = AsyncMock()
    mock_db["events"] = mock_events
    mock_db["alerts"] = mock_alerts
    return mock_db, mock_alerts


async def test_duplicate_key_normal_collision_mock():
    """1. Normal collision: insert hits DuplicateKeyError, active alert exists, fallback updates it."""
    events = [{"qr_status": "NO_QR"} for _ in range(5)]
    mock_db, mock_alerts = make_mock_db(events)

    # Initial find_one returns None (triggers insert attempt)
    # Subsequent fallback find_one returns existing active alert
    existing_active = {"_id": "active-1", "alert_id": "alert-active-1", "status": "OPEN"}
    mock_alerts.find_one.side_effect = [None, existing_active]
    mock_alerts.insert_one.side_effect = DuplicateKeyError("Duplicate active alert key")

    res = await evaluate_qr_exception_alert(mock_db)
    assert res is not None
    assert res["action"] == "updated_on_collision"
    assert res["alert_id"] == "alert-active-1"
    mock_alerts.update_one.assert_called_once()
    print("PASS: test_duplicate_key_normal_collision_mock")


async def test_competing_alert_resolved_single_retry_mock():
    """2 & 3. Collision occurs, competing alert resolved before fallback, single retry inserts fresh alert."""
    events = [{"qr_status": "UNREADABLE_QR"} for _ in range(5)]
    mock_db, mock_alerts = make_mock_db(events)

    # First find_one: None (tries insert)
    # Fallback find_one: None (competing alert was resolved in microsecond before query)
    mock_alerts.find_one.side_effect = [None, None]

    # First insert_one: DuplicateKeyError
    # Second (retry) insert_one: Succeeds!
    mock_alerts.insert_one.side_effect = [DuplicateKeyError("First collision"), None]

    res = await evaluate_qr_exception_alert(mock_db)
    assert res is not None
    assert res["action"] == "retry_created"
    assert "alert_id" in res
    assert mock_alerts.insert_one.call_count == 2
    print("PASS: test_competing_alert_resolved_single_retry_mock")


async def test_retry_collides_again_updates_second_winner_mock():
    """4. Retry collides again (second DuplicateKeyError), safely finds second winner and updates."""
    events = [{"qr_status": "INVALID_QR"} for _ in range(5)]
    mock_db, mock_alerts = make_mock_db(events)

    # 1st find_one: None
    # 2nd find_one (first fallback): None
    # 3rd find_one (second fallback after retry collision): finds second active alert
    second_active = {"_id": "active-2", "alert_id": "alert-active-2", "status": "OPEN"}
    mock_alerts.find_one.side_effect = [None, None, second_active]

    # Both inserts fail with DuplicateKeyError
    mock_alerts.insert_one.side_effect = [
        DuplicateKeyError("First collision"),
        DuplicateKeyError("Second collision")
    ]

    res = await evaluate_qr_exception_alert(mock_db)
    assert res is not None
    assert res["action"] == "retry_updated"
    assert res["alert_id"] == "alert-active-2"
    assert mock_alerts.insert_one.call_count == 2
    mock_alerts.update_one.assert_called_once()
    print("PASS: test_retry_collides_again_updates_second_winner_mock")


async def test_double_collision_persistent_failure_raises():
    """5. Extreme churn: collided twice and no active alert found -> raises RuntimeError without silent loss."""
    events = [{"qr_status": "NO_QR"} for _ in range(5)]
    mock_db, mock_alerts = make_mock_db(events)

    # All find_one calls return None
    mock_alerts.find_one.side_effect = [None, None, None]

    # Both inserts fail
    mock_alerts.insert_one.side_effect = [
        DuplicateKeyError("First collision"),
        DuplicateKeyError("Second collision")
    ]

    try:
        await evaluate_qr_exception_alert(mock_db)
        assert False, "Should have raised RuntimeError on persistent unresolvable collision"
    except RuntimeError as e:
        assert "persistent collision on active alert state" in str(e)
    print("PASS: test_double_collision_persistent_failure_raises")


async def test_integration_against_isolated_database():
    """6. Integration verification in isolated disposable test database."""
    client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    db.client = client
    database = client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(client, TEST_DB_NAME)
    await init_indexes()

    # Seed test users
    admin_hash = get_password_hash("AdminPass123")
    user_hash = get_password_hash("UserPass123")
    await database["users"].insert_one({
        "username": "recovery_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "recovery_user",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    admin_token = create_access_token(data={"sub": "recovery_admin", "role": "ADMIN"})
    user_token = create_access_token(data={"sub": "recovery_user", "role": "USER"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    test_client = TestClient(app)

    try:
        now = datetime(2032, 5, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(5):
            await database["events"].insert_one({
                "event_id": f"recov-event-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })

        # Test initial creation
        res1 = await evaluate_qr_exception_alert(database, now=now)
        assert res1["action"] == "created"
        initial_id = res1["alert_id"]

        # Test update of existing active alert
        res2 = await evaluate_qr_exception_alert(database, now=now + timedelta(seconds=10))
        assert res2["action"] == "updated"
        assert res2["alert_id"] == initial_id

        # Verify Admin-only security on alert routes
        # Unauthenticated: 401
        assert test_client.get("/api/alerts/").status_code == 401
        assert test_client.patch(f"/api/alerts/{initial_id}/acknowledge").status_code == 401
        assert test_client.patch(f"/api/alerts/{initial_id}/resolve").status_code == 401

        # Non-admin (USER): 403 Forbidden
        assert test_client.get("/api/alerts/", headers=user_headers).status_code == 403
        assert test_client.patch(f"/api/alerts/{initial_id}/acknowledge", headers=user_headers).status_code == 403
        assert test_client.patch(f"/api/alerts/{initial_id}/resolve", headers=user_headers).status_code == 403

        # Admin: 200 OK
        ack_res = test_client.patch(f"/api/alerts/{initial_id}/acknowledge", headers=admin_headers)
        assert ack_res.status_code == 200

        res_res = test_client.patch(
            f"/api/alerts/{initial_id}/resolve",
            headers=admin_headers,
            json={"resolution_reason": "Resolved in test", "resolution_note": "Verified"}
        )
        assert res_res.status_code == 200

        print("PASS: test_integration_against_isolated_database")

    finally:
        await safe_drop_test_database(client, TEST_DB_NAME)
        await client.close()


async def main():
    print("Running Phase 2.2 DuplicateKeyError race recovery tests...")
    await test_duplicate_key_normal_collision_mock()
    await test_competing_alert_resolved_single_retry_mock()
    await test_retry_collides_again_updates_second_winner_mock()
    await test_double_collision_persistent_failure_raises()
    await test_integration_against_isolated_database()
    print("ALL PHASE 2.2 RACE RECOVERY TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
