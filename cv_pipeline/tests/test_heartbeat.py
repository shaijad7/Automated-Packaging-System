import time
from unittest.mock import patch, MagicMock
import pytest
import requests

from heartbeat import EdgeHealthTracker, HeartbeatSender


def test_initial_tracker_state_is_unknown():
    tracker = EdgeHealthTracker()
    telemetry = tracker.get_telemetry()
    assert telemetry["camera"] == "UNKNOWN"
    assert telemetry["model"] == "UNKNOWN"
    assert telemetry["fps"] is None
    assert telemetry["last_frame_timestamp"] is None
    assert telemetry["last_inference_timestamp"] is None


def test_camera_runtime_lifecycle():
    tracker = EdgeHealthTracker()

    # Successful frame read -> camera UP
    tracker.record_frame_read(True)
    telemetry = tracker.get_telemetry()
    assert telemetry["camera"] == "UP"
    assert "Camera stream active" in telemetry["camera_details"]
    assert telemetry["last_frame_timestamp"] is not None

    # Single failure -> DEGRADED
    tracker.record_frame_read(False, error="Single frame drop")
    telemetry_deg = tracker.get_telemetry()
    assert telemetry_deg["camera"] == "DEGRADED"

    # 3 consecutive failures -> DOWN
    tracker.record_frame_read(False, error="Device disconnected")
    tracker.record_frame_read(False, error="Device disconnected")
    telemetry_down = tracker.get_telemetry()
    assert telemetry_down["camera"] == "DOWN"
    assert "Device disconnected" in telemetry_down["camera_details"]

    # Recovery on subsequent successful frame -> UP
    tracker.record_frame_read(True)
    telemetry_rec = tracker.get_telemetry()
    assert telemetry_rec["camera"] == "UP"


def test_camera_stall_becomes_down():
    tracker = EdgeHealthTracker()
    tracker.record_frame_read(True)

    # Simulate 16 seconds elapsed since last frame
    with patch("time.time", return_value=time.time() + 16.0):
        telemetry = tracker.get_telemetry()
        assert telemetry["camera"] == "DOWN"
        assert "stream stalled" in telemetry["camera_details"]


def test_model_runtime_lifecycle():
    tracker = EdgeHealthTracker()

    # 1. Model failed to load -> DOWN
    tracker.record_model_loaded(False, error="Weights file not found")
    telemetry = tracker.get_telemetry()
    assert telemetry["model"] == "DOWN"
    assert "Weights file not found" in telemetry["model_details"]

    # 2. Model loaded, no inference yet -> UNKNOWN
    tracker.record_model_loaded(True)
    telemetry_loaded = tracker.get_telemetry()
    assert telemetry_loaded["model"] == "UNKNOWN"
    assert "awaiting initial frame" in telemetry_loaded["model_details"]

    # 3. Successful inference -> UP with FPS
    tracker.record_inference(True, fps=27.5)
    telemetry_up = tracker.get_telemetry()
    assert telemetry_up["model"] == "UP"
    assert "27.5 FPS" in telemetry_up["model_details"]
    assert telemetry_up["fps"] == 27.5
    assert telemetry_up["last_inference_timestamp"] is not None

    # 4. 3 consecutive inference failures -> DOWN
    tracker.record_inference(False, error="CUDA out of memory")
    tracker.record_inference(False, error="CUDA out of memory")
    tracker.record_inference(False, error="CUDA out of memory")
    telemetry_down = tracker.get_telemetry()
    assert telemetry_down["model"] == "DOWN"
    assert "CUDA out of memory" in telemetry_down["model_details"]

    # 5. Recovery -> UP
    tracker.record_inference(True, fps=30.0)
    assert tracker.get_telemetry()["model"] == "UP"


def test_model_stall_becomes_down():
    tracker = EdgeHealthTracker()
    tracker.record_model_loaded(True)
    tracker.record_inference(True, fps=25.0)

    # Simulate 16 seconds elapsed without inference
    with patch("time.time", return_value=time.time() + 16.0):
        telemetry = tracker.get_telemetry()
        assert telemetry["model"] == "DOWN"
        assert "Inference stalled" in telemetry["model_details"]


def test_heartbeat_sender_send_one_success():
    tracker = EdgeHealthTracker()
    tracker.record_frame_read(True)
    tracker.record_model_loaded(True)
    tracker.record_inference(True, fps=30.0)

    sender = HeartbeatSender(
        tracker=tracker,
        backend_url="http://testbackend:8000",
        api_key="secret-api-key-123",
        interval=10.0,
        timeout=5.0,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "recorded"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = sender.send_one()
        assert success is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://testbackend:8000/api/edge/heartbeat"
        assert kwargs["headers"] == {"X-API-Key": "secret-api-key-123"}
        assert kwargs["timeout"] == 5.0
        payload = kwargs["json"]
        assert payload["camera"] == "UP"
        assert payload["model"] == "UP"
        assert payload["fps"] == 30.0


def test_heartbeat_sender_network_failure_resilience():
    tracker = EdgeHealthTracker()
    sender = HeartbeatSender(
        tracker=tracker,
        backend_url="http://testbackend:8000",
        api_key="key",
    )

    # When network fails, sender returns False and does NOT raise
    with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout("Connection timed out")):
        success = sender.send_one()
        assert success is False

    with patch("requests.post", side_effect=requests.exceptions.HTTPError("500 Internal Server Error")):
        success = sender.send_one()
        assert success is False


def test_heartbeat_sender_thread_lifecycle():
    tracker = EdgeHealthTracker()
    sender = HeartbeatSender(
        tracker=tracker,
        backend_url="http://testbackend:8000",
        api_key="key",
        interval=2.0,
    )

    with patch.object(sender, "send_one", return_value=True) as mock_send, \
         patch.object(sender, "send_shutdown_heartbeat", return_value=True) as mock_shutdown:
        sender.start()
        assert sender.thread is not None
        assert sender.thread.is_alive()
        # Wait slightly to ensure loop runs
        time.sleep(1.2)
        sender.stop()
        assert not sender.thread.is_alive()
        mock_send.assert_called()
        mock_shutdown.assert_called_once()


def test_tracker_record_shutdown():
    tracker = EdgeHealthTracker()
    tracker.record_frame_read(True)
    tracker.record_model_loaded(True)
    tracker.record_inference(True, fps=30.0)
    assert tracker.get_telemetry()["camera"] == "UP"
    assert tracker.get_telemetry()["model"] == "UP"

    tracker.record_shutdown("Pipeline stopped by operator")
    telemetry = tracker.get_telemetry()
    assert telemetry["camera"] == "DOWN"
    assert telemetry["model"] == "DOWN"
    assert "Pipeline stopped by operator" in telemetry["camera_details"]
    assert "Pipeline stopped by operator" in telemetry["model_details"]


def test_camera_opened_without_frames_is_unknown():
    tracker = EdgeHealthTracker()
    tracker.record_camera_opened(True)
    telemetry = tracker.get_telemetry()
    assert telemetry["camera"] == "UNKNOWN"
    assert "initial frame" in telemetry["camera_details"].lower()


def test_send_shutdown_heartbeat_payload_and_resilience():
    tracker = EdgeHealthTracker()
    tracker.record_frame_read(True)
    tracker.record_model_loaded(True)
    tracker.record_inference(True, fps=30.0)
    tracker.record_shutdown("CV pipeline shut down")

    sender = HeartbeatSender(
        tracker=tracker,
        backend_url="http://testbackend:8000",
        api_key="secret-key",
    )

    # 1. Successful shutdown heartbeat sends DOWN
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = sender.send_shutdown_heartbeat()
        assert success is True
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["camera"] == "DOWN"
        assert kwargs["json"]["model"] == "DOWN"
        assert kwargs["timeout"] == 1.5

    # 2. Network error on shutdown does not throw or block
    with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout):
        success = sender.send_shutdown_heartbeat()
        assert success is False
