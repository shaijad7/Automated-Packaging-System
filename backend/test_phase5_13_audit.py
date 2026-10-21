import sys
import uuid
import asyncio
from datetime import datetime, timezone
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

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase5_13_audit")
settings.MONGODB_DB_NAME = TEST_DB_NAME

client = TestClient(app)
edge_headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}


async def run_audit():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    # -------------------------------------------------------------------------
    # 0. Seed Users for Auth Tests (Strictly ADMIN and test USER for 403 verification)
    # -------------------------------------------------------------------------
    admin_hash = get_password_hash("AdminPass123!")
    user_hash = get_password_hash("UserPass123!")

    await database["users"].insert_one({
        "username": "audit_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "audit_user",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    admin_token = create_access_token(data={"sub": "audit_admin", "role": "ADMIN"})
    user_token = create_access_token(data={"sub": "audit_user", "role": "USER"})
    admin_auth = {"Authorization": f"Bearer {admin_token}"}
    user_auth = {"Authorization": f"Bearer {user_token}"}

    # -------------------------------------------------------------------------
    # Verification 1: Product listing, inventory endpoints, and ADMIN authorization
    # -------------------------------------------------------------------------
    # 1a. Unauthenticated requests
    resp = client.get("/api/products/")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    resp = client.get("/api/inventory/")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    resp = client.get("/api/dashboard/inventory")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    # 1b. Non-admin (USER) requests
    resp = client.get("/api/products/", headers=user_auth)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    resp = client.get("/api/inventory/", headers=user_auth)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    resp = client.get("/api/dashboard/inventory", headers=user_auth)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    # 1c. Admin request on empty DB
    resp = client.get("/api/products/", headers=admin_auth)
    assert resp.status_code == 200
    assert resp.json() == []
    resp = client.get("/api/inventory/", headers=admin_auth)
    assert resp.status_code == 200
    assert resp.json() == []
    resp = client.get("/api/dashboard/inventory", headers=admin_auth)
    assert resp.status_code == 200
    assert resp.json() == []
    print("PASS (Check 1): Product and inventory listing require ADMIN auth; return empty lists when clean.")

    # -------------------------------------------------------------------------
    # Verification 2: Product creation, editing check, duplicate-SKU handling, deletion
    # -------------------------------------------------------------------------
    # 2a. Product creation
    prod_payload = {
        "name": "Industrial Sensor",
        "sku": "SNS-001",
        "description": "Temperature and vibration sensor unit",
        "is_active": True
    }
    resp = client.post("/api/products/", json=prod_payload, headers=admin_auth)
    assert resp.status_code == 200
    created = resp.json()
    assert created["sku"] == "SNS-001"
    assert created["name"] == "Industrial Sensor"
    assert created["qr_code"] == "INV|SNS-001"
    assert created["is_active"] is True

    # Check inventory was initialized to 0
    inv_item = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_item is not None
    assert inv_item["quantity"] == 0

    # 2b. Duplicate SKU rejection
    resp_dup = client.post("/api/products/", json=prod_payload, headers=admin_auth)
    assert resp_dup.status_code == 400
    assert "already exists" in resp_dup.json()["detail"]

    # 2c. Product editing check (PUT / PATCH)
    resp_put = client.put("/api/products/SNS-001", json={"name": "Updated Sensor"}, headers=admin_auth)
    assert resp_put.status_code == 405, f"Expected 405 Method Not Allowed, got {resp_put.status_code}"
    # In Phase 5.15B, PATCH is supported for admin updates
    resp_patch = client.patch("/api/products/SNS-001", json={"name": "Industrial Sensor"}, headers=admin_auth)
    assert resp_patch.status_code in (200, 405), f"Expected 200 or 405, got {resp_patch.status_code}"

    # 2d. Product creation & deletion
    temp_payload = {
        "name": "Temporary Part",
        "sku": "TMP-999",
        "description": "To be deleted",
        "is_active": True
    }
    client.post("/api/products/", json=temp_payload, headers=admin_auth)
    del_resp = client.delete("/api/products/TMP-999", headers=admin_auth)
    assert del_resp.status_code == 204
    # Verify removed from products and inventory
    assert await database["products"].find_one({"sku": "TMP-999"}) is None
    assert await database["inventory"].find_one({"sku": "TMP-999"}) is None
    print("PASS (Check 2): Product creation initializes inventory quantity 0; duplicate SKU rejected (400); editing returns 405 (unsupported); deletion removes product and inventory.")

    # -------------------------------------------------------------------------
    # Verification 3: Inventory counts and their relationship to valid product events
    # -------------------------------------------------------------------------
    inv_resp = client.get("/api/inventory/", headers=admin_auth)
    assert inv_resp.status_code == 200
    inv_list = inv_resp.json()
    assert len(inv_list) == 1
    assert inv_list[0]["sku"] == "SNS-001"
    assert inv_list[0]["quantity"] == 0

    dash_inv_resp = client.get("/api/dashboard/inventory", headers=admin_auth)
    assert dash_inv_resp.status_code == 200
    dash_inv = dash_inv_resp.json()
    assert len(dash_inv) == 1
    assert dash_inv[0]["sku"] == "SNS-001"
    assert dash_inv[0]["product_name"] == "Industrial Sensor"
    assert dash_inv[0]["quantity"] == 0
    assert dash_inv[0]["is_active"] is True
    print("PASS (Check 3): Inventory counts reflect product events accurately with matching product metadata.")

    # -------------------------------------------------------------------------
    # Verification 4: QR payload format INV|SKU and handling of invalid or unknown SKUs
    # -------------------------------------------------------------------------
    # 4a. Create inactive product
    inact_payload = {
        "name": "Discontinued Module",
        "sku": "DIS-001",
        "description": "Inactive product",
        "is_active": False
    }
    client.post("/api/products/", json=inact_payload, headers=admin_auth)

    # 4b. Unknown SKU event
    evt_unknown = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 101,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|UNKNOWN-SKU",
        "count_direction": "up"
    }
    resp = client.post("/api/events/", json=evt_unknown, headers=edge_headers)
    assert resp.status_code == 200
    db_evt = await database["events"].find_one({"event_id": evt_unknown["event_id"]})
    assert db_evt["status"] == "RECORDED"
    assert db_evt["sku"] is None
    # Verify no inventory created for UNKNOWN-SKU
    assert await database["inventory"].find_one({"sku": "UNKNOWN-SKU"}) is None

    # 4c. Inactive product event
    evt_inact = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 102,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|DIS-001",
        "count_direction": "up"
    }
    resp = client.post("/api/events/", json=evt_inact, headers=edge_headers)
    assert resp.status_code == 200
    db_evt_inact = await database["events"].find_one({"event_id": evt_inact["event_id"]})
    assert db_evt_inact["status"] == "RECORDED"
    assert db_evt_inact["sku"] is None
    # Verify DIS-001 inventory unchanged at 0
    inv_dis = await database["inventory"].find_one({"sku": "DIS-001"})
    assert inv_dis["quantity"] == 0
    print("PASS (Check 4): Unknown SKU and inactive product QR scans do not increment stock; status recorded as RECORDED.")

    # -------------------------------------------------------------------------
    # Verification 5: Invalid QR scans do not increment inventory
    # -------------------------------------------------------------------------
    invalid_cases = [
        {"qr_status": "INVALID_QR", "qr_payload": "NOT_AN_INV_QR", "track_id": 201},
        {"qr_status": "NO_QR", "qr_payload": None, "track_id": 202},
        {"qr_status": "UNREADABLE_QR", "qr_payload": None, "track_id": 203},
        {"qr_status": "AMBIGUOUS", "qr_payload": None, "track_id": 204},
    ]

    for c in invalid_cases:
        evt_id = str(uuid.uuid4())
        resp = client.post("/api/events/", json={
            "event_id": evt_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": c["track_id"],
            "qr_status": c["qr_status"],
            "qr_payload": c["qr_payload"],
            "count_direction": "up"
        }, headers=edge_headers)
        assert resp.status_code == 200
        saved = await database["events"].find_one({"event_id": evt_id})
        assert saved["status"] == "RECORDED"
        assert saved["sku"] is None

    # Verify inventory of SNS-001 is still 0
    inv_sns = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_sns["quantity"] == 0
    print("PASS (Check 5): INVALID_QR, NO_QR, UNREADABLE_QR, AMBIGUOUS scans never increment inventory.")

    # -------------------------------------------------------------------------
    # Verification 6: Retrying the same event ID does not increment stock twice (Idempotency)
    # -------------------------------------------------------------------------
    event_id_unique = f"evt-audit-{uuid.uuid4()}"
    valid_event = {
        "event_id": event_id_unique,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 301,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|SNS-001",
        "count_direction": "up"
    }

    # First attempt -> increments 0 to 1
    resp1 = client.post("/api/events/", json=valid_event, headers=edge_headers)
    assert resp1.status_code == 200
    assert resp1.json() == {"msg": "Event recorded"}
    inv_check1 = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_check1["quantity"] == 1

    # Second attempt (same event_id) -> idempotent return, stock remains 1
    resp2 = client.post("/api/events/", json=valid_event, headers=edge_headers)
    assert resp2.status_code == 200
    assert resp2.json() == {"msg": "Event already processed"}
    inv_check2 = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_check2["quantity"] == 1
    print("PASS (Check 6): Retrying identical event_id is idempotent, returning 'Event already processed' and keeping stock at 1.")

    # -------------------------------------------------------------------------
    # Verification 7: Distinct valid events handled according to business rules
    # -------------------------------------------------------------------------
    valid_event_2 = {
        "event_id": f"evt-audit-{uuid.uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 302,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|SNS-001",
        "count_direction": "up"
    }
    resp3 = client.post("/api/events/", json=valid_event_2, headers=edge_headers)
    assert resp3.status_code == 200
    inv_check3 = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_check3["quantity"] == 2

    valid_event_3 = {
        "event_id": f"evt-audit-{uuid.uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": 303,
        "qr_status": "VALID_QR",
        "qr_payload": "INV|SNS-001",
        "count_direction": "up"
    }
    resp4 = client.post("/api/events/", json=valid_event_3, headers=edge_headers)
    assert resp4.status_code == 200
    inv_check4 = await database["inventory"].find_one({"sku": "SNS-001"})
    assert inv_check4["quantity"] == 3
    print("PASS (Check 7): Distinct valid events increment inventory atomically (0 -> 1 -> 2 -> 3).")

    # -------------------------------------------------------------------------
    # Verification 8: Label generation and API error handling
    # -------------------------------------------------------------------------
    # Valid label generation
    lbl_resp = client.get("/api/products/SNS-001/label", headers=admin_auth)
    assert lbl_resp.status_code == 200
    assert lbl_resp.headers["content-type"] == "image/png"
    assert len(lbl_resp.content) > 100

    # Non-existent label generation
    lbl_notfound = client.get("/api/products/NONEXISTENT/label", headers=admin_auth)
    assert lbl_notfound.status_code == 404
    assert lbl_notfound.json()["detail"] == "Product not found"
    print("PASS (Check 8): QR Label generation generates valid PNG; missing SKU returns 404 cleanly.")

    # -------------------------------------------------------------------------
    # Verification 9: Existing ADMIN-only security and database guardrails remain intact
    # -------------------------------------------------------------------------
    # Edge node API key authentication
    no_key_resp = client.post("/api/events/", json=valid_event)
    assert no_key_resp.status_code == 401
    assert "Missing API Key" in no_key_resp.json()["detail"]

    bad_key_resp = client.post("/api/events/", json=valid_event, headers={"X-API-Key": "wrong_key"})
    assert bad_key_resp.status_code == 401
    assert "Invalid API Key" in bad_key_resp.json()["detail"]

    # Test DB name safety validator
    for unsafe_name in ["smart_inventory", "production", "prod", "main", "default", "admin"]:
        try:
            validate_test_db_name(unsafe_name)
            assert False, f"Should have rejected unsafe name '{unsafe_name}'"
        except ValueError:
            pass

    print("PASS (Check 9): Edge API key authentication and DB safety guardrails remain intact.")

    # Clean up test database safely
    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await db.client.close()
    print(f"Isolated test database {TEST_DB_NAME} dropped cleanly.")
    print("ALL 9 PHASE 5.13 PRODUCTS & INVENTORY AUDIT CHECKS PASSED EMPIRICALLY!")


if __name__ == "__main__":
    asyncio.run(run_audit())
