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

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_duplicate_boxes")
settings.MONGODB_DB_NAME = TEST_DB_NAME

client = TestClient(app)
edge_headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}


async def run_duplicate_boxes_tests():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    now = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # 0. Seed Users for Auth Tests
    # -------------------------------------------------------------------------
    admin_hash = get_password_hash("AdminPass123!")
    user_hash = get_password_hash("UserPass123!")

    await database["users"].insert_one({
        "username": "dup_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "dup_user",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    admin_token = create_access_token(data={"sub": "dup_admin", "role": "ADMIN"})
    user_token = create_access_token(data={"sub": "dup_user", "role": "USER"})
    admin_auth = {"Authorization": f"Bearer {admin_token}"}
    user_auth = {"Authorization": f"Bearer {user_token}"}

    # -------------------------------------------------------------------------
    # Test 7: ADMIN access required for GET /api/dashboard/duplicate-boxes
    # -------------------------------------------------------------------------
    # 7a. Unauthenticated request -> 401
    resp_unauth = client.get("/api/dashboard/duplicate-boxes")
    assert resp_unauth.status_code == 401, f"Expected 401 unauth, got {resp_unauth.status_code}"
    print("PASS (Test 7a): Unauthenticated request returns HTTP 401 Unauthorized")

    # 7b. Non-admin user request -> 403
    resp_forbidden = client.get("/api/dashboard/duplicate-boxes", headers=user_auth)
    assert resp_forbidden.status_code == 403, f"Expected 403 non-admin, got {resp_forbidden.status_code}"
    print("PASS (Test 7b): Non-admin (USER) request returns HTTP 403 Forbidden")

    # 7c. Active Admin request -> 200
    resp_admin = client.get("/api/dashboard/duplicate-boxes", headers=admin_auth)
    assert resp_admin.status_code == 200, f"Expected 200 admin, got {resp_admin.status_code}"
    print("PASS (Test 7c): Admin request returns HTTP 200 OK")

    # -------------------------------------------------------------------------
    # Test 1 & 6: Empty duplicate results & No fabricated Box IDs
    # -------------------------------------------------------------------------
    empty_data = resp_admin.json()
    assert empty_data["summary"]["repeated_scans_count"] == 0
    assert empty_data["summary"]["id_conflicts_count"] == 0
    assert empty_data["summary"]["same_sku_groups_count"] == 0
    assert empty_data["summary"]["has_serialized_box_ids"] is False
    assert "INV|<SKU>" in empty_data["summary"]["schema_notice"]
    assert empty_data["repeated_scans_and_conflicts"] == []
    assert empty_data["same_sku_groups"] == []
    print("PASS (Test 1 & 6): Empty results handled correctly, schema notice present, zero fabricated Box IDs")

    # -------------------------------------------------------------------------
    # Test 2: Same event ID retry does not increment stock twice (idempotency)
    # -------------------------------------------------------------------------
    sku_1 = "DUP-TEST-SKU-01"
    await database["products"].insert_one({
        "sku": sku_1,
        "name": "Widget Alpha",
        "qr_code": f"INV|{sku_1}",
        "is_active": True,
        "created_at": now
    })
    await database["inventory"].insert_one({
        "sku": sku_1,
        "quantity": 0,
        "last_updated": now
    })

    evt_1_id = str(uuid.uuid4())
    event_payload_1 = {
        "event_id": evt_1_id,
        "timestamp": now.isoformat(),
        "track_id": 201,
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{sku_1}",
        "count_direction": "IN"
    }

    # First event ingestion
    resp_ingest_1 = client.post("/api/events/", json=event_payload_1, headers=edge_headers)
    assert resp_ingest_1.status_code == 200, f"Ingest 1 failed: {resp_ingest_1.text}"
    inv_doc = await database["inventory"].find_one({"sku": sku_1})
    assert inv_doc["quantity"] == 1, f"Expected quantity 1, got {inv_doc['quantity']}"

    # Retry same event_id
    resp_retry = client.post("/api/events/", json=event_payload_1, headers=edge_headers)
    assert resp_retry.status_code == 200, f"Retry failed: {resp_retry.text}"
    assert resp_retry.json()["msg"] == "Event already processed"
    inv_doc_after_retry = await database["inventory"].find_one({"sku": sku_1})
    assert inv_doc_after_retry["quantity"] == 1, f"Expected quantity 1 after retry, got {inv_doc_after_retry['quantity']}"
    print("PASS (Test 2): Same event ID retry is idempotent and does not increment stock twice")

    # -------------------------------------------------------------------------
    # Test 3: Different event IDs are not automatically considered the same box
    # -------------------------------------------------------------------------
    evt_2_id = str(uuid.uuid4())
    event_payload_2 = {
        "event_id": evt_2_id,
        "timestamp": (now + timedelta(seconds=10)).isoformat(),
        "track_id": 202,
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{sku_1}",
        "count_direction": "IN"
    }
    resp_ingest_2 = client.post("/api/events/", json=event_payload_2, headers=edge_headers)
    assert resp_ingest_2.status_code == 200
    inv_doc_2 = await database["inventory"].find_one({"sku": sku_1})
    assert inv_doc_2["quantity"] == 2, f"Expected quantity 2 for second box, got {inv_doc_2['quantity']}"

    # Check duplicate boxes endpoint
    resp_dup_check = client.get("/api/dashboard/duplicate-boxes", headers=admin_auth)
    dup_res = resp_dup_check.json()
    # Distinct event IDs are NOT flagged as invalid duplicate scans
    assert len(dup_res["repeated_scans_and_conflicts"]) == 0, (
        f"Expected 0 repeated scans/conflicts, got {dup_res['repeated_scans_and_conflicts']}"
    )
    print("PASS (Test 3): Different event IDs are not falsely flagged as repeated scans")

    # -------------------------------------------------------------------------
    # Test 4: Same SKU across distinct box observations forms a group, not duplicate inventory
    # -------------------------------------------------------------------------
    assert len(dup_res["same_sku_groups"]) == 1
    group = dup_res["same_sku_groups"][0]
    assert group["sku"] == sku_1
    assert group["product_name"] == "Widget Alpha"
    assert group["box_count"] == 2
    assert group["review_status"] == "VALID_INVENTORY_GROUP"
    assert "valid, separate inventory items" in group["reason"].lower()

    # Confirm inventory is still intact and not mutated
    inv_doc_final = await database["inventory"].find_one({"sku": sku_1})
    assert inv_doc_final["quantity"] == 2
    print("PASS (Test 4): Same-SKU observations correctly grouped as VALID_INVENTORY_GROUP without reducing stock")

    # -------------------------------------------------------------------------
    # Test 5: Same Box ID with conflicting SKU values is flagged without overwriting stock
    # -------------------------------------------------------------------------
    sku_a = "CONF-SKU-A"
    sku_b = "CONF-SKU-B"
    await database["products"].insert_one({"sku": sku_a, "name": "Conflicting Product A", "qr_code": f"INV|{sku_a}", "is_active": True})
    await database["products"].insert_one({"sku": sku_b, "name": "Conflicting Product B", "qr_code": f"INV|{sku_b}", "is_active": True})
    await database["inventory"].insert_one({"sku": sku_a, "quantity": 10, "last_updated": now})
    await database["inventory"].insert_one({"sku": sku_b, "quantity": 10, "last_updated": now})

    # Insert events that share a box_id with conflicting SKUs
    conflict_box_id = "BOX-SERIAL-999"
    await database["events"].insert_one({
        "event_id": str(uuid.uuid4()),
        "box_id": conflict_box_id,
        "track_id": 301,
        "timestamp": now - timedelta(minutes=5),
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{sku_a}",
        "sku": sku_a,
        "count_direction": "IN",
        "status": "SUCCESS"
    })
    await database["events"].insert_one({
        "event_id": str(uuid.uuid4()),
        "box_id": conflict_box_id,
        "track_id": 302,
        "timestamp": now,
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{sku_b}",
        "sku": sku_b,
        "count_direction": "IN",
        "status": "SUCCESS"
    })

    resp_conflict_check = client.get("/api/dashboard/duplicate-boxes", headers=admin_auth)
    conflict_data = resp_conflict_check.json()

    assert conflict_data["summary"]["id_conflicts_count"] == 1
    assert conflict_data["summary"]["has_serialized_box_ids"] is True

    conflict_items = [i for i in conflict_data["repeated_scans_and_conflicts"] if i["box_id"] == conflict_box_id]
    assert len(conflict_items) == 1
    conflict_item = conflict_items[0]
    assert conflict_item["category"] == "ID_CONFLICT"
    assert conflict_item["review_status"] == "NEEDS_REVIEW"
    assert sku_a in conflict_item["sku"] and sku_b in conflict_item["sku"]

    # Verify inventory was NOT overwritten or modified by the duplicate check
    inv_a = await database["inventory"].find_one({"sku": sku_a})
    inv_b = await database["inventory"].find_one({"sku": sku_b})
    assert inv_a["quantity"] == 10
    assert inv_b["quantity"] == 10
    print("PASS (Test 5): Box ID conflict flagged with NEEDS_REVIEW and conflicting SKUs without mutating inventory stock")

    # -------------------------------------------------------------------------
    # Clean up isolated test database
    # -------------------------------------------------------------------------
    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await db.client.close()
    print(f"Isolated test database {TEST_DB_NAME} dropped cleanly.")
    print("ALL PHASE 5.9 DUPLICATE BOXES REGRESSION TESTS PASSED!")


def test_duplicate_boxes_suite():
    asyncio.run(run_duplicate_boxes_tests())


if __name__ == "__main__":
    asyncio.run(run_duplicate_boxes_tests())
