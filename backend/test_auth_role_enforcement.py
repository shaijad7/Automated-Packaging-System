"""
Hermetic regression tests for authentication role enforcement.
Verifies that /api/login fails closed when the role field is missing, invalid, or non-ADMIN,
and verifies that legitimate ADMIN accounts succeed.
Does not access MongoDB or any external network/database.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_password_hash

# Ensure test client never attempts database connections via lifespan
@asynccontextmanager
async def dummy_lifespan(_):
    yield

app.router.lifespan_context = dummy_lifespan

client = TestClient(app)



def test_login_valid_admin_role():
    """Valid ADMIN credentials with explicit role='ADMIN' must succeed."""
    mock_user = {
        "username": "superadmin",
        "hashed_password": get_password_hash("ValidAdminPass123!"),
        "role": "ADMIN",
        "is_active": True,
    }

    mock_db = {"users": AsyncMock()}
    mock_db["users"].find_one = AsyncMock(return_value=mock_user)

    with patch("app.api.routes.auth.get_db", return_value=mock_db):
        response = client.post(
            "/api/login",
            data={"username": "superadmin", "password": "ValidAdminPass123!"},
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_missing_role_fails_closed():
    """Valid credentials with missing 'role' field must fail closed with HTTP 403."""
    mock_user = {
        "username": "norole_user",
        "hashed_password": get_password_hash("SomePassword123!"),
        "is_active": True,
        # 'role' key intentionally omitted
    }

    mock_db = {"users": AsyncMock()}
    mock_db["users"].find_one = AsyncMock(return_value=mock_user)

    with patch("app.api.routes.auth.get_db", return_value=mock_db):
        response = client.post(
            "/api/login",
            data={"username": "norole_user", "password": "SomePassword123!"},
        )

    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    assert "valid ADMIN role required" in response.json().get("detail", "")
    assert "access_token" not in response.json()


def test_login_non_admin_role_fails_closed():
    """Valid credentials with role other than 'ADMIN' must fail closed with HTTP 403."""
    for forbidden_role in ["USER", "OPERATOR", "STAFF", "VIEWER", "", None]:
        mock_user = {
            "username": f"user_{forbidden_role}",
            "hashed_password": get_password_hash("SomePassword123!"),
            "role": forbidden_role,
            "is_active": True,
        }

        mock_db = {"users": AsyncMock()}
        mock_db["users"].find_one = AsyncMock(return_value=mock_user)

        with patch("app.api.routes.auth.get_db", return_value=mock_db):
            response = client.post(
                "/api/login",
                data={"username": f"user_{forbidden_role}", "password": "SomePassword123!"},
            )

        assert response.status_code == 403, f"Role {forbidden_role} should return 403, got {response.status_code}"
        assert "valid ADMIN role required" in response.json().get("detail", "")
        assert "access_token" not in response.json()


def test_login_inactive_user_fails():
    """Inactive user account with role='ADMIN' must still be rejected with HTTP 400."""
    mock_user = {
        "username": "inactive_admin",
        "hashed_password": get_password_hash("ValidPass123!"),
        "role": "ADMIN",
        "is_active": False,
    }

    mock_db = {"users": AsyncMock()}
    mock_db["users"].find_one = AsyncMock(return_value=mock_user)

    with patch("app.api.routes.auth.get_db", return_value=mock_db):
        response = client.post(
            "/api/login",
            data={"username": "inactive_admin", "password": "ValidPass123!"},
        )

    assert response.status_code == 400
    assert response.json().get("detail") == "Inactive user"


def test_login_wrong_password_fails():
    """Incorrect password must return HTTP 400 without revealing role information."""
    mock_user = {
        "username": "real_admin",
        "hashed_password": get_password_hash("CorrectPassword123!"),
        "role": "ADMIN",
        "is_active": True,
    }

    mock_db = {"users": AsyncMock()}
    mock_db["users"].find_one = AsyncMock(return_value=mock_user)

    with patch("app.api.routes.auth.get_db", return_value=mock_db):
        response = client.post(
            "/api/login",
            data={"username": "real_admin", "password": "WrongPassword!"},
        )

    assert response.status_code == 400
    assert response.json().get("detail") == "Incorrect username or password"


if __name__ == "__main__":
    test_login_valid_admin_role()
    test_login_missing_role_fails_closed()
    test_login_non_admin_role_fails_closed()
    test_login_inactive_user_fails()
    test_login_wrong_password_fails()
    print("ALL AUTH ROLE ENFORCEMENT REGRESSION TESTS PASSED.")
