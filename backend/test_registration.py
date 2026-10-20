import pytest
import asyncio
import certifi
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from app.main import app
from app.api.deps import get_current_user
from app.models.user import TokenData
from app.core.config import settings
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database

# Mock dependencies
def override_get_user_role_user():
    return TokenData(username="test_viewer", role="USER")

def override_get_user_role_admin():
    return TokenData(username="test_admin", role="ADMIN")

async def setup_test_db():
    test_db_name = validate_test_db_name("smart_inventory_test_reg")
    settings.MONGODB_DB_NAME = test_db_name
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    await safe_drop_test_database(db.client, test_db_name)
    await init_indexes()
    return test_db_name

async def teardown_test_db(test_db_name):
    temp_client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    try:
        await safe_drop_test_database(temp_client, test_db_name)
    finally:
        await temp_client.close()

def test_full_flow():
    test_db_name = asyncio.run(setup_test_db())
    try:
        with TestClient(app) as client:
            # 1. Test Non-Admin Rejection (403 Forbidden)
            app.dependency_overrides[get_current_user] = override_get_user_role_user
            response = client.post("/api/products/", json={"sku": "TST-001", "name": "Test Product"})
            assert response.status_code == 403, f"Expected 403, got {response.status_code}"

            # 2. Test Admin Creation
            app.dependency_overrides[get_current_user] = override_get_user_role_admin

            payload = {
                "sku": "TST-001",
                "name": "Test Product",
                "description": "A test product",
                "is_active": True
            }
            response = client.post("/api/products/", json=payload)
            assert response.status_code == 200, f"Failed to create: {response.text}"

            data = response.json()
            assert data["sku"] == "TST-001"
            assert data["qr_code"] == "INV|TST-001", "QR payload not correctly generated!"

            # 3. Test Duplicate Rejection
            response_dup = client.post("/api/products/", json=payload)
            assert response_dup.status_code == 400, "Duplicate SKU was not rejected!"

            # 4. Test Label Generation (Any valid user can read)
            response_label = client.get("/api/products/TST-001/label")
            assert response_label.status_code == 200, f"Label endpoint failed: {response_label.text}"
            assert response_label.headers["content-type"] == "image/png", "Response is not PNG"

            # Ensure it's a valid PNG (magic bytes)
            assert response_label.content.startswith(b'\x89PNG'), "Not a valid PNG image!"

            print("All product registration tests passed successfully!")
    finally:
        app.dependency_overrides.clear()
        asyncio.run(teardown_test_db(test_db_name))

if __name__ == "__main__":
    test_full_flow()
