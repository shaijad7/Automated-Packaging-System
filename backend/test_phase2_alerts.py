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

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase2_alerts")
settings.MONGODB_DB_NAME = TEST_DB_NAME


async def run_phase2_alert_tests():
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)
    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    # Seed test users
    admin_hash = get_password_hash("AdminPass123")
    user_hash = get_password_hash("UserPass123")

    await database["users"].insert_one({
        "username": "phase2_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "phase2_non_admin",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    admin_token = create_access_token(data={"sub": "phase2_admin", "role": "ADMIN"})
    non_admin_token = create_access_token(data={"sub": "phase2_non_admin", "role": "USER"})

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    non_admin_headers = {"Authorization": f"Bearer {non_admin_token}"}

    client = TestClient(app)

    try:
        # -------------------------------------------------------------
        # 1. THRESHOLD BOUNDARY TESTS (<, ==, >)
        # -------------------------------------------------------------
        base_time = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)

        # 1a. One unit below threshold: 4 exceptions (threshold is 5)
        for i in range(4):
            await database["events"].insert_one({
                "event_id": f"bound-test-below-{i}",
                "timestamp": base_time,
                "track_id": -1,
                "qr_status": "UNREADABLE_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=base_time)
        alerts_below = await database["alerts"].find({"status": "OPEN"}).to_list(10)
        assert len(alerts_below) == 0, f"Expected 0 alerts for 4 exceptions, found {len(alerts_below)}"
        print("PASS: Threshold boundary - 4 exceptions (< 5) produces 0 alerts")

        # 1b. Exactly at threshold: 5th exception added
        await database["events"].insert_one({
            "event_id": "bound-test-exact-5",
            "timestamp": base_time,
            "track_id": -1,
            "qr_status": "NO_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=base_time)
        alerts_exact = await database["alerts"].find({"status": "OPEN"}).to_list(10)
        assert len(alerts_exact) == 1, f"Expected 1 alert for 5 exceptions, found {len(alerts_exact)}"
        active_alert = alerts_exact[0]
        assert active_alert["exception_count"] == 5
        assert active_alert["status"] == "OPEN"
        print("PASS: Threshold boundary - exactly 5 exceptions (== 5) triggers 1 OPEN alert")

        # 1c. One unit above threshold: 6th exception added
        await database["events"].insert_one({
            "event_id": "bound-test-above-6",
            "timestamp": base_time + timedelta(seconds=30),
            "track_id": -1,
            "qr_status": "INVALID_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=30))
        alerts_above = await database["alerts"].find({"status": "OPEN"}).to_list(10)
        assert len(alerts_above) == 1, f"Expected still 1 alert (updated in place), found {len(alerts_above)}"
        assert alerts_above[0]["exception_count"] == 6
        print("PASS: Threshold boundary - 6 exceptions (> 5) updates existing alert count to 6")

        # -------------------------------------------------------------
        # 2. CONCURRENT ALERT EVALUATION TEST
        # -------------------------------------------------------------
        # Concurrently fire 5 evaluations at the same timestamp
        await asyncio.gather(
            evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=45)),
            evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=45)),
            evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=45)),
            evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=45)),
            evaluate_qr_exception_alert(database, now=base_time + timedelta(seconds=45)),
        )
        alerts_concurrent = await database["alerts"].find({"status": "OPEN"}).to_list(10)
        assert len(alerts_concurrent) == 1, f"Concurrency race detected! Found {len(alerts_concurrent)} OPEN alerts"
        print("PASS: Concurrency test - 5 parallel evaluations produced exactly 1 active alert")

        # -------------------------------------------------------------
        # 3. OPEN AND ACKNOWLEDGED HANDLING
        # -------------------------------------------------------------
        alert_id = active_alert["alert_id"]

        # Acknowledge the alert
        ack_res = client.patch(f"/api/alerts/{alert_id}/acknowledge", headers=admin_headers)
        assert ack_res.status_code == 200
        alert_after_ack = await database["alerts"].find_one({"alert_id": alert_id})
        assert alert_after_ack["status"] == "ACKNOWLEDGED"

        # Another exception occurs while ACKNOWLEDGED
        await database["events"].insert_one({
            "event_id": "bound-test-ack-update-7",
            "timestamp": base_time + timedelta(minutes=1),
            "track_id": -1,
            "qr_status": "NO_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=base_time + timedelta(minutes=1))

        # Must not create a duplicate OPEN alert; must update ACKNOWLEDGED alert
        all_active = await database["alerts"].find({"status": {"$in": ["OPEN", "ACKNOWLEDGED"]}}).to_list(10)
        assert len(all_active) == 1, f"Expected 1 active alert, found {len(all_active)}"
        assert all_active[0]["status"] == "ACKNOWLEDGED", "ACKNOWLEDGED status was unexpectedly altered"
        assert all_active[0]["exception_count"] == 7
        print("PASS: ACKNOWLEDGED alert correctly preserved and updated in-place without duplicate creation")

        # -------------------------------------------------------------
        # 4. RESOLUTION & RE-ALERTING AFTER RESOLUTION
        # -------------------------------------------------------------
        res_res = client.patch(
            f"/api/alerts/{alert_id}/resolve",
            headers=admin_headers,
            json={"resolution_reason": "Conveyor optics cleaned", "resolution_note": "Camera lens wiped"}
        )
        assert res_res.status_code == 200
        resolved_alert = await database["alerts"].find_one({"alert_id": alert_id})
        assert resolved_alert["status"] == "RESOLVED"
        assert resolved_alert["resolved_by"] == "phase2_admin"
        assert resolved_alert["resolution_reason"] == "Conveyor optics cleaned"

        # Subsequent exceptions in a NEW window (20 minutes later)
        future_time = base_time + timedelta(minutes=20)
        for i in range(5):
            await database["events"].insert_one({
                "event_id": f"bound-test-new-window-{i}",
                "timestamp": future_time,
                "track_id": -1,
                "qr_status": "UNREADABLE_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=future_time)

        total_alerts = await database["alerts"].find().to_list(10)
        assert len(total_alerts) == 2, f"Expected 2 total alerts (1 RESOLVED, 1 new OPEN), got {len(total_alerts)}"
        resolved_count = sum(1 for a in total_alerts if a["status"] == "RESOLVED")
        open_count = sum(1 for a in total_alerts if a["status"] == "OPEN")
        assert resolved_count == 1
        assert open_count == 1
        print("PASS: Re-alerting after resolution creates clean new OPEN alert while preserving historical record")

        # -------------------------------------------------------------
        # 5. ADMIN-ONLY RBAC ENFORCEMENT ON ALL ALERT ENDPOINTS
        # -------------------------------------------------------------
        new_open_id = [a for a in total_alerts if a["status"] == "OPEN"][0]["alert_id"]

        # 5a. Unauthenticated requests must return 401
        assert client.get("/api/alerts/").status_code == 401
        assert client.get(f"/api/alerts/{new_open_id}").status_code == 401
        assert client.patch(f"/api/alerts/{new_open_id}/acknowledge").status_code == 401
        assert client.patch(f"/api/alerts/{new_open_id}/resolve").status_code == 401
        print("PASS: Unauthenticated requests to alert routes rejected with HTTP 401")

        # 5b. Authenticated NON-ADMIN requests must return 403 Forbidden
        r_list_user = client.get("/api/alerts/", headers=non_admin_headers)
        assert r_list_user.status_code == 403, f"Expected 403 for non-admin list, got {r_list_user.status_code}"

        r_get_user = client.get(f"/api/alerts/{new_open_id}", headers=non_admin_headers)
        assert r_get_user.status_code == 403, f"Expected 403 for non-admin get, got {r_get_user.status_code}"

        r_ack_user = client.patch(f"/api/alerts/{new_open_id}/acknowledge", headers=non_admin_headers)
        assert r_ack_user.status_code == 403, f"Expected 403 for non-admin ack, got {r_ack_user.status_code}"

        r_res_user = client.patch(f"/api/alerts/{new_open_id}/resolve", headers=non_admin_headers)
        assert r_res_user.status_code == 403, f"Expected 403 for non-admin resolve, got {r_res_user.status_code}"
        print("PASS: Authenticated non-admin requests strictly rejected with HTTP 403 Forbidden")

        # 5c. Authenticated ADMIN requests succeed (200)
        assert client.get("/api/alerts/", headers=admin_headers).status_code == 200
        assert client.get(f"/api/alerts/{new_open_id}", headers=admin_headers).status_code == 200
        assert client.patch(f"/api/alerts/{new_open_id}/acknowledge", headers=admin_headers).status_code == 200
        assert client.patch(f"/api/alerts/{new_open_id}/resolve", headers=admin_headers).status_code == 200
        print("PASS: Authenticated ADMIN requests succeed with HTTP 200")

    finally:
        # Final isolated test cleanup
        if db.client:
            await safe_drop_test_database(db.client, TEST_DB_NAME)
            await db.client.close()

    print("ALL PHASE 2 ALERT SAFETY AND CONSISTENCY TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_phase2_alert_tests())
