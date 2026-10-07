import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_active_admin, get_current_user
from app.models.user import TokenData

client = TestClient(app)

# Mock dependencies
def override_get_current_active_admin():
    return TokenData(username="admin", role="ADMIN")
    
def override_get_current_user():
    return TokenData(username="user", role="USER")

# Test 1: Non-admin cannot create product
def test_non_admin_cannot_create():
    app.dependency_overrides[get_current_active_admin] = override_get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    response = client.post("/api/products/", json={
        "sku": "REAL-123",
        "name": "Real Product"
    })
    # Fastapi depends raises 403 usually for custom role checks if we wrote it, 
    # but wait, the override returns a USER role. In our mock we need to simulate the dependency raising an error if it expects ADMIN.
    # Actually, deps.py checks `if current_user.role != "ADMIN": raise HTTPException(403)`.
    # Since we are overriding `get_current_active_admin`, the override function itself doesn't raise the error unless we make it.
    pass

# A better way is to just override `get_current_user` and let `get_current_active_admin` run.
def override_get_user_role_user():
    return TokenData(username="user", role="USER")

def override_get_user_role_admin():
    return TokenData(username="admin", role="ADMIN")

def test_full_flow():
    with TestClient(app) as client:
        # 1. Test Non-Admin Rejection
        app.dependency_overrides[get_current_user] = override_get_user_role_user
        response = client.post("/api/products/", json={"sku": "TST-001", "name": "Test Product"})
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"

        # 2. Test Admin Creation
        app.dependency_overrides[get_current_user] = override_get_user_role_admin
        # Ensure cleanup first
        client.delete("/api/products/TST-001")
        
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
        
        # Cleanup
        client.delete("/api/products/TST-001")
        print("All backend tests passed successfully!")

if __name__ == "__main__":
    test_full_flow()
