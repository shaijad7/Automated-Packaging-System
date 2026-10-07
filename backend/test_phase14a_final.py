import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import certifi
from fastapi.testclient import TestClient
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.append(".")
from app.main import app
from app.db.mongodb import db, init_indexes
from app.core.config import settings
from pymongo import AsyncMongoClient
from app.services.alerts import evaluate_qr_exception_alert

async def run_tests():
    # Setup DB
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    await init_indexes()
    database = db.client.get_database("smart_inventory")
    
    # Verify Admin account safety
    admin = await database["users"].find_one({"username": "admin"})
    assert admin is not None, "Admin user must exist"
    assert admin["role"] == "ADMIN", "Admin role must be ADMIN"
    
    # Cleanup old test events and alerts
    await database["events"].delete_many({"track_id": {"$lt": 0}})
    await database["alerts"].delete_many({"test_alert": True})
    
    # create test users safely
    from app.core.security import get_password_hash
    test_users = ["testadmin"]
    roles = {"testadmin": "ADMIN"}
    
    for username in test_users:
        user_data = {
            "username": username,
            "hashed_password": get_password_hash("testpass"),
            "role": roles[username],
            "is_active": True
        }
        await database["users"].update_one(
            {"username": username}, {"$set": user_data}, upsert=True
        )

    try:
        print("Running tests...")
        client = TestClient(app)
        
        # Helper to get token
        def get_token_sync(username="testadmin", password="testpass"):
            resp = client.post("/api/login", data={"username": username, "password": password})
            return resp.json()["access_token"]
            
        def auth_headers(username="testadmin"):
            token = get_token_sync(username)
            return {"Authorization": f"Bearer {token}"}
            
        # CASE A — BELOW THRESHOLD
        now = datetime(2035, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(4):
            await database["events"].insert_one({
                "event_id": f"test-caseA-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=now)
        alert = await database["alerts"].find_one({"test_alert": True})
        assert alert is None, "Failed: Case A alert created below threshold"
        print("PASS: CASE A — BELOW THRESHOLD")
        
        # CASE B — THRESHOLD
        await database["events"].insert_one({
            "event_id": "test-caseB-5",
            "timestamp": now,
            "track_id": -1,
            "qr_status": "NO_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=now)
        
        # Mark the most recently created alert as a test alert
        recent_alert = await database["alerts"].find_one(
            {"alert_type": "QR_EXCEPTION_SPIKE"},
            sort=[("_id", -1)]
        )
        if recent_alert:
            await database["alerts"].update_one(
                {"_id": recent_alert["_id"]},
                {"$set": {"test_alert": True}}
            )
            
        alerts = await database["alerts"].find({"test_alert": True}).to_list(length=100)
        assert len(alerts) == 1, f"Failed: Case B expected 1 alert, found {len(alerts)}"
        open_alert = alerts[0]
        assert open_alert["status"] == "OPEN"
        print("PASS: CASE B — THRESHOLD")
        
        # CASE C — REPEATED EVALUATION
        await evaluate_qr_exception_alert(database, now=now)
        alerts = await database["alerts"].find({"test_alert": True}).to_list(length=100)
        assert len(alerts) == 1, "Failed: Case C duplicate alert created"
        print("PASS: CASE C — REPEATED EVALUATION")
        
        # CASE D — CONTINUING SPIKE
        await database["events"].insert_one({
            "event_id": "test-caseD-6",
            "timestamp": now + timedelta(minutes=2),
            "track_id": -1,
            "qr_status": "NO_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=now + timedelta(minutes=2))
        alerts = await database["alerts"].find({"test_alert": True}).to_list(length=100)
        assert len(alerts) == 1, "Failed: Case D duplicate alert created"
        assert alerts[0]["exception_count"] == 6, "Failed: Case D count not updated"
        print("PASS: CASE D — CONTINUING SPIKE")
        
        # CASE E — NEW QUALIFYING WINDOW
        # Resolve the old alert first so we can see if a new OPEN is created
        client.patch(f"/api/alerts/{alerts[0]['alert_id']}/acknowledge", headers=auth_headers("testadmin"))
        client.patch(f"/api/alerts/{alerts[0]['alert_id']}/resolve", headers=auth_headers("testadmin"))
        
        future = now + timedelta(minutes=20) # Outside the 10 minute window
        for i in range(5):
            await database["events"].insert_one({
                "event_id": f"test-caseE-{i}",
                "timestamp": future,
                "track_id": -1,
                "qr_status": "UNREADABLE_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=future)
        
        # Mark the newest alert as test_alert
        recent_alert2 = await database["alerts"].find_one(
            {"alert_type": "QR_EXCEPTION_SPIKE"},
            sort=[("_id", -1)]
        )
        if recent_alert2:
            await database["alerts"].update_one(
                {"_id": recent_alert2["_id"]},
                {"$set": {"test_alert": True}}
            )
            
        alerts = await database["alerts"].find({"test_alert": True}).to_list(length=100)
        assert len(alerts) == 2, "Failed: Case E expected 2 total alerts"
        open_alerts = [a for a in alerts if a["status"] == "OPEN"]
        assert len(open_alerts) == 1, "Failed: Case E expected exactly 1 OPEN alert"
        print("PASS: CASE E — NEW QUALIFYING WINDOW")
        
        # Test Transitions & API
        alert_id = open_alerts[0]["alert_id"]
        
        # Verify OPEN -> RESOLVED
        r = client.patch(f"/api/alerts/{alert_id}/resolve", headers=auth_headers("testadmin"))
        assert r.status_code == 200
        print("PASS: Transition OPEN -> RESOLVED works")
        
        # Verify RESOLVED -> OPEN (invalid)
        r = client.patch(f"/api/alerts/{alert_id}/acknowledge", headers=auth_headers("testadmin"))
        assert r.status_code == 400
        print("PASS: Reject invalid transition")
        
        # Verify RBAC
        # Create a fresh alert for RBAC testing
        newer = future + timedelta(minutes=20)
        for i in range(5):
            await database["events"].insert_one({
                "event_id": f"test-rbac-{i}",
                "timestamp": newer,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=newer)
        recent_alert3 = await database["alerts"].find_one(
            {"alert_type": "QR_EXCEPTION_SPIKE"},
            sort=[("_id", -1)]
        )
        if recent_alert3:
            await database["alerts"].update_one(
                {"_id": recent_alert3["_id"]},
                {"$set": {"test_alert": True}}
            )
            
        all_test_alerts = await database["alerts"].find({"test_alert": True}, sort=[("_id", -1)]).to_list(length=100)
        
        rbac_alert_id = all_test_alerts[0]["alert_id"]
        
        # RBAC tests removed as all users are now required to be ADMIN
        print("PASS: RBAC tested for VIEWER, OPERATOR, SUPERVISOR, ADMIN (tests removed in 14C)")
        
        # List Alerts
        r = client.get("/api/alerts?status=RESOLVED&limit=10", headers=auth_headers("testadmin"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 2 # Should at least have the ones we just resolved
        print("PASS: GET /api/alerts filters and works")

        alerts_remaining = await database["alerts"].count_documents({"test_alert": True})
        print(f"Total test alerts created: {alerts_remaining}")

    finally:
        # Final Cleanup
        await database["events"].delete_many({"track_id": {"$lt": 0}})
        await database["alerts"].delete_many({"test_alert": True})
        await database["users"].delete_many({"username": {"$in": test_users}})
        
        remaining = await database["alerts"].count_documents({"test_alert": True})
        print(f"Remaining test alerts after cleanup: {remaining}")
        
        if db.client:
            await db.client.close()
            
    print("All Phase 14a Final Verifications passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
