import sys
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
import certifi
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.append(".")
from app.main import app
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database
from app.core.config import settings

client = TestClient(app)
headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}


TEST_DB_NAME = validate_test_db_name("smart_inventory_test_ambiguous")
settings.MONGODB_DB_NAME = TEST_DB_NAME

async def run_ambiguous_tests():
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)
    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    # Seed test SKU in test database
    await database["products"].update_one(
        {"sku": "ADP-001"},
        {"$set": {"name": "Adapter", "qr_code": "INV|ADP-001", "is_active": True}},
        upsert=True
    )

    inv_before = await database["inventory"].find_one({"sku": "ADP-001"})
    count_before = inv_before["quantity"] if inv_before else 0

    # 1. AMBIGUOUS event test
    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 99,
        "qr_status": "AMBIGUOUS",
        "qr_payload": None,
        "count_direction": "A_TO_B"
    }

    response = client.post("/api/events/", json=payload, headers=headers)
    assert response.status_code == 200, f"Error: {response.text}"
    assert response.json() == {"msg": "Event recorded"}

    # Verify event is recorded in MongoDB with status RECORDED
    saved_event = await database["events"].find_one({"event_id": event_id})
    assert saved_event is not None
    assert saved_event["qr_status"] == "AMBIGUOUS"
    assert saved_event["status"] == "RECORDED"

    # Verify inventory was NOT incremented for ambiguous event
    inv_after = await database["inventory"].find_one({"sku": "ADP-001"})
    count_after = inv_after["quantity"] if inv_after else 0
    assert count_after == count_before
    print("PASS: AMBIGUOUS -> event persisted + inventory unchanged")

    # 2. Test HTTP 401 with wrong key
    wrong_headers = {"X-API-Key": "INCORRECT_KEY"}
    response_401 = client.post("/api/events/", json=payload, headers=wrong_headers)
    assert response_401.status_code == 401
    assert response_401.json() == {"detail": "Invalid API Key"}
    print("PASS: Invalid API key -> HTTP 401 returned")

    # 3. Test HTTP 401 with missing key
    response_missing = client.post("/api/events/", json=payload)
    assert response_missing.status_code == 401
    assert response_missing.json() == {"detail": "Missing API Key"}
    print("PASS: Missing API key -> HTTP 401 returned")

    if db.client:
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        await db.client.close()

    print("All Ambiguous and Auth backend tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(run_ambiguous_tests())
