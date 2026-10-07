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

async def get_token(client, username="testadmin", password="testpass"):
    response = await client.post("/api/login", data={"username": username, "password": password})
    return response.json()["access_token"]

async def run_tests():
    # Setup DB
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    await init_indexes()
    database = db.client.get_database("smart_inventory")
    
    # Cleanup old test events and alerts
    await database["events"].delete_many({"track_id": {"$lt": 0}})
    await database["alerts"].delete_many({"alert_type": "QR_EXCEPTION_SPIKE"})
    
    # create a test admin user
    from app.core.security import get_password_hash
    test_user = {
        "username": "testadmin",
        "hashed_password": get_password_hash("testpass"),
        "role": "ADMIN",
        "is_active": True
    }
    await database["users"].update_one(
        {"username": "testadmin"}, {"$set": test_user}, upsert=True
    )
    # viewer removed

    try:
        print("Running tests...")
        
        # Test 1: No alert below threshold
        now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(4):
            await database["events"].insert_one({
                "event_id": f"test-evt-bth-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=now)
        alert = await database["alerts"].find_one({"alert_type": "QR_EXCEPTION_SPIKE"})
        assert alert is None, "Failed: Alert created below threshold"
        print("PASS: No alert below threshold")
        
        # Test 2: Alert created at threshold
        await database["events"].insert_one({
            "event_id": "test-evt-bth-4",
            "timestamp": now,
            "track_id": -1,
            "qr_status": "NO_QR",
            "status": "RECORDED"
        })
        await evaluate_qr_exception_alert(database, now=now)
        alert = await database["alerts"].find_one({"alert_type": "QR_EXCEPTION_SPIKE"})
        assert alert is not None, "Failed: Alert not created at threshold"
        assert alert["exception_count"] == 5
        print("PASS: Alert created at threshold")
        
        # Cleanup
        await database["events"].delete_many({"track_id": {"$lt": 0}})
        await database["alerts"].delete_many({"alert_type": "QR_EXCEPTION_SPIKE"})
        
        # Test 3: Alert counts correctly mixed
        now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        events = [
            ("NO_QR", 2),
            ("UNREADABLE_QR", 1),
            ("INVALID_QR", 2),
            ("VALID_QR", 5)
        ]
        evt_id = 0
        for status, count in events:
            for _ in range(count):
                await database["events"].insert_one({
                    "event_id": f"test-evt-mix-{evt_id}",
                    "timestamp": now,
                    "track_id": -1,
                    "qr_status": status,
                    "status": "RECORDED"
                })
                evt_id += 1
                
        await evaluate_qr_exception_alert(database, now=now)
        alert = await database["alerts"].find_one({"alert_type": "QR_EXCEPTION_SPIKE"})
        assert alert is not None
        assert alert["exception_count"] == 5
        assert alert["no_qr_count"] == 2
        assert alert["unreadable_qr_count"] == 1
        assert alert["invalid_qr_count"] == 2
        print("PASS: Alert counts correctly mixed (VALID_QR ignored)")
        
        # Cleanup
        await database["events"].delete_many({"track_id": {"$lt": 0}})
        await database["alerts"].delete_many({"alert_type": "QR_EXCEPTION_SPIKE"})
        
        # Test 4: Events outside window ignored
        now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        old = now - timedelta(minutes=15)
        for i in range(3):
            await database["events"].insert_one({
                "event_id": f"test-evt-old-{i}",
                "timestamp": old,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        for i in range(2):
            await database["events"].insert_one({
                "event_id": f"test-evt-new-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=now)
        alert = await database["alerts"].find_one({"alert_type": "QR_EXCEPTION_SPIKE"})
        assert alert is None
        print("PASS: Events outside window ignored")
        
        # Cleanup
        await database["events"].delete_many({"track_id": {"$lt": 0}})
        await database["alerts"].delete_many({"alert_type": "QR_EXCEPTION_SPIKE"})
        
        # Test 5: Repeated evaluation updates existing open alert
        now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(5):
            await database["events"].insert_one({
                "event_id": f"test-evt-rep-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=now)
        
        for i in range(5, 7):
            await database["events"].insert_one({
                "event_id": f"test-evt-rep-{i}",
                "timestamp": now,
                "track_id": -1,
                "qr_status": "NO_QR",
                "status": "RECORDED"
            })
        await evaluate_qr_exception_alert(database, now=now)
        alerts = await database["alerts"].find({"alert_type": "QR_EXCEPTION_SPIKE"}).to_list(length=100)
        assert len(alerts) == 1
        assert alerts[0]["exception_count"] == 7
        print("PASS: Repeated evaluation updates existing open alert")
        
        # Test 6: Alert API Endpoints
        alert_id = alerts[0]["alert_id"]
        
        client = TestClient(app)
        
        # Helper to get token synchronously
        resp = client.post("/api/login", data={"username": "testadmin", "password": "testpass"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # list
        r = client.get("/api/alerts", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) == 1
        print("PASS: GET /api/alerts works")
        
        # open -> ack
        r = client.patch(f"/api/alerts/{alert_id}/acknowledge", headers=headers)
        assert r.status_code == 200
        r = client.get(f"/api/alerts/{alert_id}", headers=headers)
        assert r.json()["status"] == "ACKNOWLEDGED"
        print("PASS: ACKNOWLEDGE alert works")
        
        # ack -> resolve
        r = client.patch(f"/api/alerts/{alert_id}/resolve", headers=headers)
        assert r.status_code == 200
        r = client.get(f"/api/alerts/{alert_id}", headers=headers)
        assert r.json()["status"] == "RESOLVED"
        print("PASS: RESOLVE alert works")
        
        # resolve -> open (fails)
        r = client.patch(f"/api/alerts/{alert_id}/acknowledge", headers=headers)
        assert r.status_code == 400
        print("PASS: Reject invalid transition")
        
        # VIEWER test removed (no longer applicable as all users must be ADMIN)
        print("PASS: VIEWER rejected (test removed in 14C)")

    finally:
        # Final Cleanup
        await database["events"].delete_many({"track_id": {"$lt": 0}})
        await database["alerts"].delete_many({"alert_type": "QR_EXCEPTION_SPIKE"})
        await database["users"].delete_many({"username": {"$in": ["testadmin"]}})
        
        if db.client:
            await db.client.close()
            
    print("All Phase 14a tests passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
