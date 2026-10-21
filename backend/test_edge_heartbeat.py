import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.append(".")
from app.main import app
from app.core.config import settings
from app.core.security import create_access_token
from app.services.system_health import reset_edge_health, get_edge_health

client = TestClient(app)

ADMIN_TOKEN = create_access_token({"sub": "admin", "role": "ADMIN"})
NON_ADMIN_TOKEN = create_access_token({"sub": "operator", "role": "OPERATOR"})

ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
NON_ADMIN_HEADERS = {"Authorization": f"Bearer {NON_ADMIN_TOKEN}"}
VALID_EDGE_HEADERS = {"X-API-Key": settings.EDGE_NODE_API_KEY}
INVALID_EDGE_HEADERS = {"X-API-Key": "invalid_wrong_secret_key"}


def setup_function():
    reset_edge_health()


def test_missing_api_key_rejected():
    """Verify POST /api/edge/heartbeat without X-API-Key returns HTTP 401."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "model": "UP",
    }
    resp = client.post("/api/edge/heartbeat", json=payload)
    assert resp.status_code == 401
    assert "Missing API Key" in resp.json()["detail"]
    print("PASS: Missing API Key rejected with HTTP 401")


def test_invalid_api_key_rejected():
    """Verify POST /api/edge/heartbeat with invalid X-API-Key returns HTTP 401."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "model": "UP",
    }
    resp = client.post("/api/edge/heartbeat", json=payload, headers=INVALID_EDGE_HEADERS)
    assert resp.status_code == 401
    assert "Invalid API Key" in resp.json()["detail"]
    print("PASS: Invalid API Key rejected with HTTP 401")


def test_valid_heartbeat_accepted():
    """Verify POST /api/edge/heartbeat with valid key and payload returns HTTP 200."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "camera_details": "Camera stream active (1280x720 @ 30fps)",
        "model": "UP",
        "model_details": "Inference active (28.4 FPS)",
        "fps": 28.4,
        "last_frame_timestamp": datetime.now(timezone.utc).isoformat(),
        "last_inference_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"
    assert "timestamp" in data
    print("PASS: Valid heartbeat accepted with HTTP 200")


def test_malformed_payload_rejected():
    """Verify malformed payload or invalid status values return HTTP 422."""
    # Invalid camera status
    payload1 = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "ONLINE",  # Invalid literal
        "model": "UP",
    }
    resp1 = client.post("/api/edge/heartbeat", json=payload1, headers=VALID_EDGE_HEADERS)
    assert resp1.status_code == 422

    # Extra disallowed field
    payload2 = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "model": "UP",
        "unauthorized_field": "dangerous_data",
    }
    resp2 = client.post("/api/edge/heartbeat", json=payload2, headers=VALID_EDGE_HEADERS)
    assert resp2.status_code == 422

    # Negative FPS
    payload3 = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "model": "UP",
        "fps": -5.0,
    }
    resp3 = client.post("/api/edge/heartbeat", json=payload3, headers=VALID_EDGE_HEADERS)
    assert resp3.status_code == 422
    print("PASS: Malformed payloads and invalid statuses rejected with HTTP 422")


def test_no_heartbeat_returns_unknown():
    """Verify initial state without heartbeat returns UNKNOWN for camera and model."""
    reset_edge_health()
    resp = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["camera_status"] == "UNKNOWN"
    assert data["model_status"] == "UNKNOWN"
    assert data["is_stale"] is False
    assert data["last_heartbeat"] is None
    print("PASS: Initial state returns UNKNOWN without stale flag")


def test_fresh_healthy_telemetry():
    """Verify fresh heartbeat accurately updates camera and model status to UP."""
    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": ts,
        "camera": "UP",
        "camera_details": "Camera stream active (1280x720)",
        "model": "UP",
        "model_details": "Inference operational (29.2 FPS)",
        "fps": 29.2,
        "last_frame_timestamp": ts,
        "last_inference_timestamp": ts,
    }
    resp_post = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp_post.status_code == 200

    resp_get = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["camera_status"] == "UP"
    assert "Camera stream active" in data["camera_details"]
    assert data["model_status"] == "UP"
    assert "Inference operational" in data["model_details"]
    assert data["fps"] == 29.2
    assert data["is_stale"] is False
    assert data["age_seconds"] is not None
    assert data["age_seconds"] < 5.0
    print("PASS: Fresh healthy telemetry returns UP for camera and model")


def test_camera_and_model_failure_reflection():
    """Verify explicit DOWN/DEGRADED states from edge are reflected accurately."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "DOWN",
        "camera_details": "VideoCapture failed to open camera device 0",
        "model": "DEGRADED",
        "model_details": "Inference frame drops detected",
        "fps": 4.1,
    }
    resp_post = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp_post.status_code == 200

    resp_get = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["camera_status"] == "DOWN"
    assert "VideoCapture failed" in data["camera_details"]
    assert data["model_status"] == "DEGRADED"
    assert "Inference frame drops" in data["model_details"]
    print("PASS: Camera DOWN and model DEGRADED correctly reported")


def test_stale_heartbeat_handling():
    """Verify heartbeat older than threshold (60s) transitions to DOWN and is_stale=True."""
    import app.services.system_health as sh

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera": "UP",
        "camera_details": "Stream active",
        "model": "UP",
        "model_details": "Model active",
        "fps": 30.0,
    }
    client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)

    # Simulate passing 65 seconds by setting _received_at directly
    with sh._lock:
        sh._received_at = time.time() - 65.0

    resp_get = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["is_stale"] is True
    assert data["camera_status"] == "DOWN"
    assert data["model_status"] == "DOWN"
    assert "Heartbeat telemetry stale" in data["camera_details"]
    assert "65s ago" in data["camera_details"]
    print("PASS: Stale heartbeat (>60s) properly marked DOWN with is_stale=True")


def test_admin_authorization_enforced():
    """Verify /api/dashboard/system-health strictly requires ADMIN authorization."""
    # 1. Unauthenticated request -> 401
    resp_unauth = client.get("/api/dashboard/system-health")
    assert resp_unauth.status_code == 401

    # 2. Non-admin request -> 403 Forbidden
    resp_non_admin = client.get("/api/dashboard/system-health", headers=NON_ADMIN_HEADERS)
    assert resp_non_admin.status_code == 403

    # 3. Admin request -> 200 OK
    resp_admin = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp_admin.status_code == 200
    print("PASS: /api/dashboard/system-health strictly enforces ADMIN authorization")


def test_no_secrets_exposed():
    """Verify edge telemetry response never exposes secrets, tokens, or credentials."""
    resp = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    resp_text = resp.text
    assert settings.EDGE_NODE_API_KEY not in resp_text
    assert settings.JWT_SECRET_KEY not in resp_text
    assert settings.MONGODB_URI not in resp_text
    print("PASS: System health responses do not expose credentials or internal secrets")


def test_existing_health_route_unaffected():
    """Verify /api/health continues to report backend and database connectivity."""
    with patch("app.api.routes.health.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.command = AsyncMock(return_value={"ok": 1.0})
        mock_get_db.return_value = mock_db

        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
def test_recomputed_staleness_on_get_without_new_heartbeat():
    """Verify staleness is dynamically recomputed on GET even if no new heartbeat arrives."""
    import app.services.system_health as sh

    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": ts,
        "camera": "UP",
        "camera_details": "Camera stream active",
        "model": "UP",
        "model_details": "Inference operational",
        "last_frame_timestamp": ts,
        "last_inference_timestamp": ts,
    }
    resp1 = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp1.status_code == 200

    # First GET: fresh -> UP
    get1 = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert get1.json()["camera_status"] == "UP"
    assert get1.json()["is_stale"] is False

    # Simulate elapsed time without any new POST
    with sh._lock:
        sh._received_at = time.time() - 61.0

    # Second GET without new POST: must recompute and return DOWN
    get2 = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert get2.json()["camera_status"] == "DOWN"
    assert get2.json()["model_status"] == "DOWN"
    assert get2.json()["is_stale"] is True
    print("PASS: Staleness recomputed dynamically on GET without new heartbeat")


def test_stale_camera_frame_cannot_remain_up():
    """Verify camera stalls (>60s) transition to DOWN even while heartbeats continue arriving."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    stale_cam_time = (now - timedelta(seconds=75)).isoformat()
    fresh_time = now.isoformat()

    payload = {
        "timestamp": fresh_time,
        "camera": "UP",
        "camera_details": "Camera claimed UP",
        "model": "UP",
        "model_details": "Model claimed UP",
        "last_frame_timestamp": stale_cam_time,
        "last_inference_timestamp": fresh_time,
    }
    resp = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp.status_code == 200

    resp_get = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    data = resp_get.json()
    assert data["is_stale"] is False  # Heartbeat itself is fresh (<5s)
    assert data["camera_status"] == "DOWN"
    assert "stalled" in data["camera_details"]
    assert data["model_status"] == "UP"
    print("PASS: Stale camera frame transitions to DOWN even if heartbeat continues")


def test_stale_inference_cannot_remain_up():
    """Verify inference stalls (>60s) transition to DOWN even while heartbeats continue arriving."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    fresh_time = now.isoformat()
    stale_infer_time = (now - timedelta(seconds=80)).isoformat()

    payload = {
        "timestamp": fresh_time,
        "camera": "UP",
        "camera_details": "Camera claimed UP",
        "model": "UP",
        "model_details": "Model claimed UP",
        "last_frame_timestamp": fresh_time,
        "last_inference_timestamp": stale_infer_time,
    }
    resp = client.post("/api/edge/heartbeat", json=payload, headers=VALID_EDGE_HEADERS)
    assert resp.status_code == 200

    resp_get = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    data = resp_get.json()
    assert data["is_stale"] is False  # Heartbeat itself is fresh (<5s)
    assert data["camera_status"] == "UP"
    assert data["model_status"] == "DOWN"
    assert "stalled" in data["model_details"]
    print("PASS: Stale inference transitions to DOWN even if heartbeat continues")


def test_system_health_cache_control_headers():
    """Verify /api/dashboard/system-health returns strict no-cache headers."""
    resp = client.get("/api/dashboard/system-health", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    cache_control = resp.headers.get("cache-control", "")
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
    print("PASS: /api/dashboard/system-health returns strict Cache-Control headers")


if __name__ == "__main__":
    setup_function()
    test_missing_api_key_rejected()
    test_invalid_api_key_rejected()
    test_valid_heartbeat_accepted()
    test_malformed_payload_rejected()
    test_no_heartbeat_returns_unknown()
    test_fresh_healthy_telemetry()
    test_camera_and_model_failure_reflection()
    test_stale_heartbeat_handling()
    test_recomputed_staleness_on_get_without_new_heartbeat()
    test_stale_camera_frame_cannot_remain_up()
    test_stale_inference_cannot_remain_up()
    test_system_health_cache_control_headers()
    test_admin_authorization_enforced()
    test_no_secrets_exposed()
    test_existing_health_route_unaffected()
    print("\nALL BACKEND EDGE HEARTBEAT TESTS PASSED SUCCESSFULLY!")
