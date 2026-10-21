import sys
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

sys.path.append(".")
from app.main import app

client = TestClient(app)


def test_health_route_healthy():
    """Verify healthy response returns 200 and connected database status."""
    with patch("app.api.routes.health.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.command = AsyncMock(return_value={"ok": 1.0})
        mock_get_db.return_value = mock_db

        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        print("PASS: /api/health healthy check returns HTTP 200 with status=healthy, database=connected")


def test_health_route_database_disconnected():
    """Verify that when database ping raises an exception, 503 is returned without leaking exceptions."""
    with patch("app.api.routes.health.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.command = AsyncMock(side_effect=Exception("Database cluster unreachable at mongodb://user:secret@prod.internal:27017"))
        mock_get_db.return_value = mock_db

        resp = client.get("/api/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert data["detail"] == "Database connection failed"
        # Confirm no credentials or raw exception messages leaked
        assert "secret" not in resp.text
        assert "prod.internal" not in resp.text
        print("PASS: /api/health db disconnected returns HTTP 503 without leaking credentials or raw exceptions")


def test_health_route_timeout():
    """Verify that database ping timeout safely fails closed with 503."""
    async def slow_ping(*args, **kwargs):
        await asyncio.sleep(5.0)
        return {"ok": 1.0}

    with patch("app.api.routes.health.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.command = slow_ping
        mock_get_db.return_value = mock_db

        # Replace timeout temporarily with 0.1s for test speed
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            resp = client.get("/api/health")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            print("PASS: /api/health database timeout safely returns HTTP 503 disconnected")


if __name__ == "__main__":
    test_health_route_healthy()
    test_health_route_database_disconnected()
    test_health_route_timeout()
    print("ALL HEALTH ROUTE TESTS PASSED SUCCESSFULLY!")
