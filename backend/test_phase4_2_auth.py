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

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase4_2")
settings.MONGODB_DB_NAME = TEST_DB_NAME


async def run_phase4_2_tests():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    now = datetime.now(timezone.utc)

    # 1. Seed Users (Admin and Non-Admin)
    admin_hash = get_password_hash("AdminPass123!")
    user_hash = get_password_hash("UserPass123!")

    await database["users"].insert_one({
        "username": "phase4_admin",
        "hashed_password": admin_hash,
        "role": "ADMIN",
        "is_active": True
    })
    await database["users"].insert_one({
        "username": "phase4_user",
        "hashed_password": user_hash,
        "role": "USER",
        "is_active": True
    })

    # 2. Seed Sample Product, Inventory, Event, and Alert for Fixtures
    test_sku = "PH4-TEST-001"
    await database["products"].insert_one({
        "sku": test_sku,
        "name": "Phase 4 Test Product",
        "qr_code": f"INV|{test_sku}",
        "is_active": True,
        "created_at": now
    })
    await database["inventory"].insert_one({
        "sku": test_sku,
        "quantity": 25,
        "last_updated": now
    })
    await database["events"].insert_one({
        "event_id": str(uuid.uuid4()),
        "track_id": 101,
        "timestamp": now,
        "qr_status": "VALID_QR",
        "qr_payload": f"INV|{test_sku}",
        "sku": test_sku,
        "count_direction": "IN",
        "status": "SUCCESS"
    })
    test_alert_id = str(uuid.uuid4())
    await database["alerts"].insert_one({
        "alert_id": test_alert_id,
        "alert_type": "QR_EXCEPTION_SPIKE",
        "severity": "WARNING",
        "status": "OPEN",
        "exception_count": 5,
        "no_qr_count": 2,
        "unreadable_qr_count": 2,
        "invalid_qr_count": 1,
        "ambiguous_qr_count": 0,
        "window_start": now - timedelta(minutes=10),
        "window_end": now,
        "created_at": now,
        "updated_at": now
    })

    admin_token = create_access_token(data={"sub": "phase4_admin", "role": "ADMIN"})
    user_token = create_access_token(data={"sub": "phase4_user", "role": "USER"})

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}
    edge_headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}

    client = TestClient(app)

    try:
        # =====================================================================
        # 1. VERIFY ALL 11 REMEDIATED ENDPOINTS: 401 unauth, 403 non-admin, 200 admin
        # =====================================================================
        endpoints_to_test = [
            ("GET", "/api/products/"),
            ("GET", f"/api/products/{test_sku}/label"),
            ("GET", "/api/inventory/"),
            ("GET", "/api/events/"),
            ("GET", "/api/dashboard/summary"),
            ("GET", "/api/dashboard/inventory"),
            ("GET", "/api/dashboard/events"),
            ("GET", "/api/dashboard/analytics"),
            ("GET", "/api/dashboard/reports"),
            ("GET", "/api/dashboard/reports/export.csv"),
            ("GET", "/api/dashboard/reports/export.pdf"),
        ]

        for method, path in endpoints_to_test:
            # 1a. Unauthenticated -> 401
            res_unauth = client.get(path)
            assert res_unauth.status_code == 401, (
                f"Expected 401 Unauthenticated for {path}, got {res_unauth.status_code}"
            )

            # 1b. Authenticated Non-Admin (role: "USER") -> 403 Forbidden
            res_non_admin = client.get(path, headers=user_headers)
            assert res_non_admin.status_code == 403, (
                f"Expected 403 Forbidden for {path} with role: USER, got {res_non_admin.status_code}"
            )

            # 1c. Authenticated Admin (role: "ADMIN") -> 200 OK
            res_admin = client.get(path, headers=admin_headers)
            assert res_admin.status_code == 200, (
                f"Expected 200 OK for {path} with role: ADMIN, got {res_admin.status_code}: {res_admin.text}"
            )
            print(f"PASS: {method} {path} strictly rejects unauth (401), non-admin (403), and succeeds for admin (200)")

        # =====================================================================
        # 2. VERIFY MUTATION & ALERT ENDPOINTS REMAIN STRICTLY ADMIN-ONLY
        # =====================================================================
        # 2a. Product Creation & Deletion
        new_prod_sku = "NEW-PROD-999"
        res_user_create = client.post("/api/products/", json={"sku": new_prod_sku, "name": "New"}, headers=user_headers)
        assert res_user_create.status_code == 403, "Non-admin should not be allowed to create products"

        res_admin_create = client.post("/api/products/", json={"sku": new_prod_sku, "name": "New"}, headers=admin_headers)
        assert res_admin_create.status_code == 200, "Admin should successfully create product"

        res_user_delete = client.delete(f"/api/products/{new_prod_sku}", headers=user_headers)
        assert res_user_delete.status_code == 403, "Non-admin should not be allowed to delete products"

        res_admin_delete = client.delete(f"/api/products/{new_prod_sku}", headers=admin_headers)
        assert res_admin_delete.status_code == 204, "Admin should successfully delete product"
        print("PASS: Product creation/deletion remain strictly ADMIN-only")

        # 2b. Alerts Endpoints
        res_user_alert = client.get("/api/alerts/", headers=user_headers)
        assert res_user_alert.status_code == 403
        res_admin_alert = client.get("/api/alerts/", headers=admin_headers)
        assert res_admin_alert.status_code == 200

        res_user_ack = client.patch(f"/api/alerts/{test_alert_id}/acknowledge", headers=user_headers)
        assert res_user_ack.status_code == 403

        res_admin_ack = client.patch(f"/api/alerts/{test_alert_id}/acknowledge", headers=admin_headers)
        assert res_admin_ack.status_code == 200

        res_user_resolve = client.patch(f"/api/alerts/{test_alert_id}/resolve", headers=user_headers)
        assert res_user_resolve.status_code == 403

        res_admin_resolve = client.patch(f"/api/alerts/{test_alert_id}/resolve", headers=admin_headers)
        assert res_admin_resolve.status_code == 200
        print("PASS: All Alert routes remain strictly ADMIN-only")

        # =====================================================================
        # 3. VERIFY EDGE-NODE INGESTION AUTHENTICATION (POST /api/events/)
        # =====================================================================
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "timestamp": now.isoformat(),
            "track_id": 999,
            "qr_status": "NO_QR",
            "count_direction": "IN"
        }
        # 3a. Missing API key -> 401
        res_no_key = client.post("/api/events/", json=event_payload)
        assert res_no_key.status_code == 401

        # 3b. Invalid API key -> 401
        res_bad_key = client.post("/api/events/", json=event_payload, headers={"X-API-Key": "WRONG_KEY"})
        assert res_bad_key.status_code == 401

        # 3c. Valid API key -> 200
        res_good_key = client.post("/api/events/", json=event_payload, headers=edge_headers)
        assert res_good_key.status_code == 200
        print("PASS: POST /api/events/ correctly preserves edge-node API key authentication")

        # =====================================================================
        # 4. VERIFY PUBLIC ENDPOINTS (/api/health and /api/login)
        # =====================================================================
        # 4a. Health probe
        res_health = client.get("/api/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"

        # 4b. Login with valid credentials
        res_login_ok = client.post("/api/login", data={"username": "phase4_admin", "password": "AdminPass123!"})
        assert res_login_ok.status_code == 200
        assert "access_token" in res_login_ok.json()

        # 4c. Login with invalid password
        res_login_bad = client.post("/api/login", data={"username": "phase4_admin", "password": "WrongPassword"})
        assert res_login_bad.status_code == 400
        print("PASS: Public endpoints (/api/health, /api/login) preserve intended public behavior")

    finally:
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        print(f"Isolated test database {TEST_DB_NAME} dropped cleanly.")


if __name__ == "__main__":
    asyncio.run(run_phase4_2_tests())
    print("\nALL PHASE 4.2 ADMIN AUTHORIZATION TESTS PASSED SUCCESSFULLY!")
