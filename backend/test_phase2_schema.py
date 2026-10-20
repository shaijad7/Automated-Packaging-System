import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import certifi
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.append(".")
from app.main import app
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database
from app.core.config import settings
from app.core.security import get_password_hash, create_access_token
from app.services.alerts import evaluate_qr_exception_alert

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase2_schema")
settings.MONGODB_DB_NAME = TEST_DB_NAME


async def run_phase2_schema_tests():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    # Ensure clean slate
    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    # Seed test users: Admin and Non-Admin
    admin_hash = get_password_hash("AdminPass123")
    user_hash = get_password_hash("UserPass123")

    await database["users"].insert_one({
        "username": "phase2_schema_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "phase2_schema_user",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    admin_token = create_access_token(data={"sub": "phase2_schema_admin", "role": "ADMIN"})
    user_token = create_access_token(data={"sub": "phase2_schema_user", "role": "USER"})

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    client = TestClient(app)

    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=15)

        # -------------------------------------------------------------
        # Test 1: Alert with non-zero ambiguous_qr_count returns value
        # -------------------------------------------------------------
        alert_with_ambiguous_id = str(uuid.uuid4())
        alert_with_ambiguous_doc = {
            "alert_id": alert_with_ambiguous_id,
            "alert_type": "QR_EXCEPTION_SPIKE",
            "severity": "WARNING",
            "status": "OPEN",
            "exception_count": 8,
            "no_qr_count": 2,
            "unreadable_qr_count": 1,
            "invalid_qr_count": 2,
            "ambiguous_qr_count": 3,
            "window_start": start_time,
            "window_end": now,
            "created_at": now,
            "updated_at": now
        }
        await database["alerts"].insert_one(alert_with_ambiguous_doc)

        # GET single alert
        res1 = client.get(f"/api/alerts/{alert_with_ambiguous_id}", headers=admin_headers)
        assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
        data1 = res1.json()
        assert "ambiguous_qr_count" in data1, "ambiguous_qr_count missing from single alert response"
        assert data1["ambiguous_qr_count"] == 3, f"Expected ambiguous_qr_count == 3, got {data1['ambiguous_qr_count']}"

        # GET list alerts
        res1_list = client.get("/api/alerts/", headers=admin_headers)
        assert res1_list.status_code == 200, f"Expected 200, got {res1_list.status_code}: {res1_list.text}"
        alerts_list1 = res1_list.json()
        matched_alert1 = next((a for a in alerts_list1 if a["alert_id"] == alert_with_ambiguous_id), None)
        assert matched_alert1 is not None, "Created alert not found in alert list"
        assert matched_alert1["ambiguous_qr_count"] == 3, f"Expected 3 in list, got {matched_alert1['ambiguous_qr_count']}"
        print("PASS: Test 1 - Non-zero ambiguous_qr_count returned in single and list API responses")

        # -------------------------------------------------------------
        # Test 2: Legacy alert without the field returns default 0
        # -------------------------------------------------------------
        # Resolve the first alert so it does not collide with the second under unique_active_alert_per_type
        await database["alerts"].update_one(
            {"alert_id": alert_with_ambiguous_id},
            {"$set": {"status": "RESOLVED"}}
        )

        legacy_alert_id = str(uuid.uuid4())
        legacy_alert_doc = {
            "alert_id": legacy_alert_id,
            "alert_type": "QR_EXCEPTION_SPIKE",
            "severity": "WARNING",
            "status": "OPEN",
            "exception_count": 5,
            "no_qr_count": 2,
            "unreadable_qr_count": 2,
            "invalid_qr_count": 1,
            # Notice: ambiguous_qr_count is intentionally omitted (simulating older database records)
            "window_start": start_time,
            "window_end": now,
            "created_at": now,
            "updated_at": now
        }
        await database["alerts"].insert_one(legacy_alert_doc)

        res2 = client.get(f"/api/alerts/{legacy_alert_id}", headers=admin_headers)
        assert res2.status_code == 200, f"Expected 200, got {res2.status_code}: {res2.text}"
        data2 = res2.json()
        assert "ambiguous_qr_count" in data2, "ambiguous_qr_count should be present with default value"
        assert data2["ambiguous_qr_count"] == 0, f"Expected default 0 for legacy alert, got {data2['ambiguous_qr_count']}"

        # GET list alerts with legacy record included
        res2_list = client.get("/api/alerts/", headers=admin_headers)
        assert res2_list.status_code == 200
        matched_alert2 = next((a for a in res2_list.json() if a["alert_id"] == legacy_alert_id), None)
        assert matched_alert2 is not None, "Legacy alert not found in alert list"
        assert matched_alert2["ambiguous_qr_count"] == 0, f"Expected 0 in list, got {matched_alert2['ambiguous_qr_count']}"
        print("PASS: Test 2 - Older alert document without the field returns default 0")

        # -------------------------------------------------------------
        # Test 3: Existing alert fields remain present and unchanged
        # -------------------------------------------------------------
        expected_fields = [
            "alert_id", "alert_type", "severity", "status",
            "exception_count", "no_qr_count", "unreadable_qr_count", "invalid_qr_count",
            "ambiguous_qr_count", "window_start", "window_end", "created_at", "updated_at",
            "resolved_by", "resolved_at", "resolution_note", "resolution_reason"
        ]
        for field in expected_fields:
            assert field in data1, f"Missing field in alert response: {field}"
            assert field in data2, f"Missing field in legacy alert response: {field}"

        assert data1["alert_id"] == alert_with_ambiguous_id
        assert data1["alert_type"] == "QR_EXCEPTION_SPIKE"
        assert data1["severity"] == "WARNING"
        assert data1["status"] == "OPEN"
        assert data1["exception_count"] == 8
        assert data1["no_qr_count"] == 2
        assert data1["unreadable_qr_count"] == 1
        assert data1["invalid_qr_count"] == 2
        print("PASS: Test 3 - All existing alert fields remain present and unchanged")

        # -------------------------------------------------------------
        # Test 4: ADMIN-only endpoint access remains strictly enforced
        # -------------------------------------------------------------
        # 4a. Unauthenticated -> 401
        res_unauth_list = client.get("/api/alerts/")
        assert res_unauth_list.status_code == 401, f"Expected 401, got {res_unauth_list.status_code}"

        res_unauth_get = client.get(f"/api/alerts/{alert_with_ambiguous_id}")
        assert res_unauth_get.status_code == 401, f"Expected 401, got {res_unauth_get.status_code}"

        res_unauth_ack = client.patch(f"/api/alerts/{alert_with_ambiguous_id}/acknowledge")
        assert res_unauth_ack.status_code == 401, f"Expected 401, got {res_unauth_ack.status_code}"

        res_unauth_res = client.patch(f"/api/alerts/{alert_with_ambiguous_id}/resolve")
        assert res_unauth_res.status_code == 401, f"Expected 401, got {res_unauth_res.status_code}"

        # 4b. Authenticated Non-Admin (role: USER) -> 403 Forbidden
        res_user_list = client.get("/api/alerts/", headers=user_headers)
        assert res_user_list.status_code == 403, f"Expected 403, got {res_user_list.status_code}"

        res_user_get = client.get(f"/api/alerts/{alert_with_ambiguous_id}", headers=user_headers)
        assert res_user_get.status_code == 403, f"Expected 403, got {res_user_get.status_code}"

        res_user_ack = client.patch(f"/api/alerts/{alert_with_ambiguous_id}/acknowledge", headers=user_headers)
        assert res_user_ack.status_code == 403, f"Expected 403, got {res_user_ack.status_code}"

        res_user_res = client.patch(f"/api/alerts/{alert_with_ambiguous_id}/resolve", headers=user_headers)
        assert res_user_res.status_code == 403, f"Expected 403, got {res_user_res.status_code}"

        # 4c. Authenticated ADMIN -> 200 OK
        res_admin_list = client.get("/api/alerts/", headers=admin_headers)
        assert res_admin_list.status_code == 200, f"Expected 200, got {res_admin_list.status_code}"

        res_admin_get = client.get(f"/api/alerts/{alert_with_ambiguous_id}", headers=admin_headers)
        assert res_admin_get.status_code == 200, f"Expected 200, got {res_admin_get.status_code}"
        print("PASS: Test 4 - ADMIN-only access enforced: 401 unauth, 403 non-admin, 200 admin")

        # -------------------------------------------------------------
        # Test 5: End-to-end evaluation with AMBIGUOUS events -> API
        # -------------------------------------------------------------
        # Resolve legacy alert before evaluating new spike
        await database["alerts"].update_one(
            {"alert_id": legacy_alert_id},
            {"$set": {"status": "RESOLVED"}}
        )

        eval_time = datetime(2030, 6, 1, 12, 0, tzinfo=timezone.utc)
        # Seed 6 exception events including 2 AMBIGUOUS
        test_events = [
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=2), "qr_status": "NO_QR"},
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=3), "qr_status": "UNREADABLE_QR"},
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=4), "qr_status": "INVALID_QR"},
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=5), "qr_status": "AMBIGUOUS"},
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=6), "qr_status": "AMBIGUOUS"},
            {"event_id": str(uuid.uuid4()), "timestamp": eval_time - timedelta(minutes=7), "qr_status": "NO_QR"},
        ]
        await database["events"].insert_many(test_events)

        eval_result = await evaluate_qr_exception_alert(database, now=eval_time)
        assert eval_result is not None, "Expected alert creation/update"
        eval_alert_id = eval_result["alert_id"]

        res_eval = client.get(f"/api/alerts/{eval_alert_id}", headers=admin_headers)
        assert res_eval.status_code == 200
        eval_alert_data = res_eval.json()
        assert eval_alert_data["exception_count"] == 6
        assert eval_alert_data["no_qr_count"] == 2
        assert eval_alert_data["unreadable_qr_count"] == 1
        assert eval_alert_data["invalid_qr_count"] == 1
        assert eval_alert_data["ambiguous_qr_count"] == 2, f"Expected ambiguous_qr_count 2, got {eval_alert_data['ambiguous_qr_count']}"
        print("PASS: Test 5 - End-to-end evaluation with AMBIGUOUS events correctly exposed via API")

    finally:
        # Safe cleanup of the isolated test database
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        print(f"Isolated test database {TEST_DB_NAME} dropped cleanly.")


if __name__ == "__main__":
    asyncio.run(run_phase2_schema_tests())
    print("\nALL PHASE 2.3 SCHEMA & REGRESSION TESTS PASSED SUCCESSFULLY!")
