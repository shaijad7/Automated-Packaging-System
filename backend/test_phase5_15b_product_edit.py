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

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_p5_15b")
settings.MONGODB_DB_NAME = TEST_DB_NAME

client = TestClient(app)
edge_headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}


async def run_tests():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    passed_count = 0

    try:
        # ---------------------------------------------------------------------
        # 0. Seed Users for Auth Tests
        # ---------------------------------------------------------------------
        admin_hash = get_password_hash("AdminPass123!")
        user_hash = get_password_hash("UserPass123!")

        await database["users"].insert_one({
            "username": "p515b_admin",
            "hashed_password": admin_hash,
            "role": "ADMIN",
            "is_active": True
        })
        await database["users"].insert_one({
            "username": "p515b_user",
            "hashed_password": user_hash,
            "role": "USER",
            "is_active": True
        })

        admin_token = create_access_token(data={"sub": "p515b_admin", "role": "ADMIN"})
        user_token = create_access_token(data={"sub": "p515b_user", "role": "USER"})
        admin_auth = {"Authorization": f"Bearer {admin_token}"}
        user_auth = {"Authorization": f"Bearer {user_token}"}

        # Seed initial product and inventory
        test_sku = "PROD-EDIT-001"
        test_qr = f"INV|{test_sku}"
        await database["products"].insert_one({
            "sku": test_sku,
            "name": "Original Product Name",
            "description": "Original Description",
            "is_active": True,
            "qr_code": test_qr,
        })
        await database["inventory"].insert_one({
            "sku": test_sku,
            "quantity": 42
        })

        # Seed an event document to verify event history remains untouched
        event_id = str(uuid.uuid4())
        await database["events"].insert_one({
            "event_id": event_id,
            "sku": test_sku,
            "event_type": "CHECK_IN",
            "quantity": 42,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "PROCESSED"
        })

        print("\n--- 1. Authentication & Authorization Guardrails ---")
        # 1a. Missing Authentication -> 401
        res = client.patch(f"/api/products/{test_sku}", json={"name": "New Name"})
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("[PASS] Missing authentication rejected with 401 Unauthorized")
        passed_count += 1

        # 1b. Non-admin Authentication -> 403
        res = client.patch(f"/api/products/{test_sku}", json={"name": "New Name"}, headers=user_auth)
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"
        print("[PASS] Authenticated non-admin rejected with 403 Forbidden")
        passed_count += 1

        print("\n--- 2. Route & Target Validation ---")
        # 2a. Unknown SKU -> 404
        res = client.patch("/api/products/NONEXISTENT-SKU", json={"name": "New Name"}, headers=admin_auth)
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"
        assert res.json()["detail"] == "Product not found"
        print("[PASS] Unknown SKU returned 404 Product not found")
        passed_count += 1

        # 2b. Empty PATCH -> 400 Bad Request
        res = client.patch(f"/api/products/{test_sku}", json={}, headers=admin_auth)
        assert res.status_code == 400, f"Expected 400, got {res.status_code}"
        assert "Empty patch" in res.json()["detail"]
        print("[PASS] Empty PATCH rejected with 400 Bad Request")
        passed_count += 1

        print("\n--- 3. Immutability & Rejection of Forbidden / Invalid Fields ---")
        # 3a. Reject attempts to edit SKU -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"sku": "NEW-SKU-999"}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for sku, got {res.status_code}"
        print("[PASS] Attempt to mutate SKU rejected with 422 Unprocessable Entity")
        passed_count += 1

        # 3b. Reject attempts to edit qr_code -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"qr_code": "INV|FORGED"}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for qr_code, got {res.status_code}"
        print("[PASS] Attempt to mutate qr_code rejected with 422 Unprocessable Entity")
        passed_count += 1

        # 3c. Reject unknown fields -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"price": 19.99}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for extra field, got {res.status_code}"
        print("[PASS] Unknown fields rejected with 422 Unprocessable Entity")
        passed_count += 1

        # 3d. Reject empty/blank product name -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"name": ""}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for empty name, got {res.status_code}"
        res_ws = client.patch(f"/api/products/{test_sku}", json={"name": "   \t  "}, headers=admin_auth)
        assert res_ws.status_code == 422, f"Expected 422 for whitespace name, got {res_ws.status_code}"
        print("[PASS] Blank and whitespace-only name rejected with 422")
        passed_count += 1

        # 3e. Reject null product name -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"name": None}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for null name, got {res.status_code}"
        print("[PASS] Null name rejected with 422")
        passed_count += 1

        # 3f. Reject name > 120 chars -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"name": "A" * 121}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for name > 120 chars, got {res.status_code}"
        print("[PASS] Name exceeding 120 characters rejected with 422")
        passed_count += 1

        # 3g. Reject description > 500 chars -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"description": "D" * 501}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for description > 500 chars, got {res.status_code}"
        print("[PASS] Description exceeding 500 characters rejected with 422")
        passed_count += 1

        # 3h. Reject null is_active -> 422
        res = client.patch(f"/api/products/{test_sku}", json={"is_active": None}, headers=admin_auth)
        assert res.status_code == 422, f"Expected 422 for null is_active, got {res.status_code}"
        print("[PASS] Null is_active rejected with 422")
        passed_count += 1

        print("\n--- 4. Valid ADMIN Updates & Field Behaviors ---")
        # 4a. Update name with trimming
        res = client.patch(f"/api/products/{test_sku}", json={"name": "  Updated Widget Pro  "}, headers=admin_auth)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        body = res.json()
        assert body["name"] == "Updated Widget Pro", f"Expected trimmed name, got {body['name']}"
        assert body["sku"] == test_sku
        assert body["qr_code"] == test_qr
        assert body["description"] == "Original Description"
        assert body["is_active"] is True
        print("[PASS] Name updated with automatic trimming; other fields preserved")
        passed_count += 1

        # 4b. Update description
        res = client.patch(f"/api/products/{test_sku}", json={"description": "New Updated Description"}, headers=admin_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["description"] == "New Updated Description"
        assert body["name"] == "Updated Widget Pro"
        print("[PASS] Description updated successfully")
        passed_count += 1

        # 4c. Set description to null (allowed by product schema)
        res = client.patch(f"/api/products/{test_sku}", json={"description": None}, headers=admin_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["description"] is None
        print("[PASS] Description set to None successfully")
        passed_count += 1

        # 4d. Explicitly update is_active: false
        res = client.patch(f"/api/products/{test_sku}", json={"is_active": False}, headers=admin_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["is_active"] is False, f"Expected False, got {body['is_active']}"
        print("[PASS] is_active set to False successfully")
        passed_count += 1

        # 4e. Explicitly update is_active: true
        res = client.patch(f"/api/products/{test_sku}", json={"is_active": True}, headers=admin_auth)
        assert res.status_code == 200
        body = res.json()
        assert body["is_active"] is True
        print("[PASS] is_active set to True successfully")
        passed_count += 1

        # 4f. Update multiple fields simultaneously
        res = client.patch(
            f"/api/products/{test_sku}",
            json={"name": "Final Pro Name", "description": "Final Description", "is_active": False},
            headers=admin_auth
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Final Pro Name"
        assert body["description"] == "Final Description"
        assert body["is_active"] is False
        assert body["sku"] == test_sku
        assert body["qr_code"] == test_qr
        print("[PASS] Multiple fields updated simultaneously; SKU and qr_code remain unchanged")
        passed_count += 1

        print("\n--- 5. Invariant Checks: Inventory and Historical Events Untouched ---")
        # 5a. Check inventory quantity in DB
        inv_doc = await database["inventory"].find_one({"sku": test_sku})
        assert inv_doc is not None, "Inventory document should exist"
        assert inv_doc["quantity"] == 42, f"Inventory quantity was mutated! Expected 42, got {inv_doc['quantity']}"
        print("[PASS] Inventory quantity completely unchanged (still 42)")
        passed_count += 1

        # 5b. Check events collection
        events = await database["events"].find().to_list(100)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        assert events[0]["event_id"] == event_id
        assert events[0]["quantity"] == 42
        assert events[0]["sku"] == test_sku
        print("[PASS] Historical event collection and event documents completely unchanged")
        passed_count += 1

        print("\n--- 6. Idempotency & Ingestion Regression Check ---")
        # Ingest an edge event with idempotency key
        edge_event_id = str(uuid.uuid4())
        event_payload = {
            "event_id": edge_event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": 101,
            "qr_status": "VALID_QR",
            "qr_payload": test_qr,
            "count_direction": "IN"
        }
        res_first = client.post("/api/events/", json=event_payload, headers=edge_headers)
        assert res_first.status_code == 200, f"Expected 200 for edge event, got {res_first.status_code}: {res_first.text}"
        assert res_first.json().get("msg") == "Event recorded"

        # Ingest duplicate event
        res_dup = client.post("/api/events/", json=event_payload, headers=edge_headers)
        assert res_dup.status_code == 200, f"Expected 200 for duplicate, got {res_dup.status_code}: {res_dup.text}"
        assert res_dup.json().get("msg") == "Event already processed"
        print("[PASS] Duplicate event idempotency handling remains fully functional")
        passed_count += 1

        print("\n--- 7. Existing QR Label Endpoint & Auth Regression Check ---")
        # 7a. Unauthenticated label request -> 401
        res = client.get(f"/api/products/{test_sku}/label")
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("[PASS] GET label without auth rejected with 401")
        passed_count += 1

        # 7b. Authenticated label request -> 200 PNG
        res = client.get(f"/api/products/{test_sku}/label", headers=admin_auth)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert res.headers["content-type"] == "image/png"
        assert len(res.content) > 100
        print("[PASS] GET label with Bearer auth returned valid PNG image")
        passed_count += 1

        print(f"\n==========================================")
        print(f"ALL {passed_count} BACKEND PRODUCT EDIT REGRESSION TESTS PASSED!")
        print(f"==========================================")

    finally:
        print(f"\nCleaning up isolated test database: {TEST_DB_NAME}...")
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        await db.client.close()
        print("Test database safely dropped and connection closed.")


if __name__ == "__main__":
    asyncio.run(run_tests())
