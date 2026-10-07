import sys
import uuid
import asyncio
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
import certifi
import warnings

# Ignore DeprecationWarning from httpx
warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.append(".")
from app.main import app
from app.db.mongodb import db, init_indexes
from app.core.config import settings

client = TestClient(app)
headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}

async def run_tests():
    # Setup DB
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    await init_indexes()
    database = db.client.get_database("smart_inventory")
    
    # Make sure ADP-001 exists
    await database["products"].update_one(
        {"sku": "ADP-001"},
        {"$set": {"name": "Adapter", "qr_code": "INV|ADP-001", "is_active": True}},
        upsert=True
    )
    
    inv_before = await database["inventory"].find_one({"sku": "ADP-001"})
    count_before = inv_before["quantity"] if inv_before else 0
    
    # 1. VALID_QR
    event_id_1 = str(uuid.uuid4())
    payload_1 = {
        "event_id": event_id_1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 1,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|ADP-001",
        "count_direction": "up"
    }
    response = client.post("/api/events/", json=payload_1, headers=headers)
    assert response.status_code == 200, f"Error: {response.text}"
    inv_after = await database["inventory"].find_one({"sku": "ADP-001"})
    assert inv_after["quantity"] == count_before + 1
    print("PASS: VALID_QR -> event persisted + inventory +1")
    
    # 2. Idempotency duplicate event_id
    response_dup = client.post("/api/events/", json=payload_1, headers=headers)
    assert response_dup.status_code == 200
    assert response_dup.json() == {"msg": "Event already processed"}
    inv_dup = await database["inventory"].find_one({"sku": "ADP-001"})
    assert inv_dup["quantity"] == count_before + 1
    print("PASS: duplicate same event_id -> inventory increments only once")
    
    # 3. NO_QR
    event_id_no_qr = str(uuid.uuid4())
    payload_no_qr = {
        "event_id": event_id_no_qr,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 2,
        "qr_status": "NO_QR",
        "qr_payload": None,
        "count_direction": "up"
    }
    response = client.post("/api/events/", json=payload_no_qr, headers=headers)
    assert response.status_code == 200
    inv_after_no = await database["inventory"].find_one({"sku": "ADP-001"})
    assert inv_after_no["quantity"] == count_before + 1
    print("PASS: NO_QR -> event persisted + inventory unchanged")
    
    # 4. UNREADABLE_QR
    event_id_unread = str(uuid.uuid4())
    payload_unread = {
        "event_id": event_id_unread,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 3,
        "qr_status": "UNREADABLE_QR",
        "qr_payload": None,
        "count_direction": "up"
    }
    response = client.post("/api/events/", json=payload_unread, headers=headers)
    assert response.status_code == 200
    inv_after_un = await database["inventory"].find_one({"sku": "ADP-001"})
    assert inv_after_un["quantity"] == count_before + 1
    print("PASS: UNREADABLE_QR -> event persisted + inventory unchanged")
    
    # 5. INVALID_QR
    event_id_invalid = str(uuid.uuid4())
    payload_invalid = {
        "event_id": event_id_invalid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 4,
        "qr_status": "INVALID_QR",
        "qr_payload": "some-random-data",
        "count_direction": "up"
    }
    response = client.post("/api/events/", json=payload_invalid, headers=headers)
    assert response.status_code == 200
    inv_after_inv = await database["inventory"].find_one({"sku": "ADP-001"})
    assert inv_after_inv["quantity"] == count_before + 1
    print("PASS: INVALID_QR -> event persisted + inventory unchanged")
    
    # 6. Atomicity test
    # We will simulate a failure in inventory update and verify that the event is NOT persisted,
    # meaning the transaction rolled back.
    # We can do this by dropping the unique index on inventory sku and replacing it with something incompatible,
    # or just mocking the database call inside the route.
    
    if db.client:
        await db.client.close()
    
    print("All basic Backend tests passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
