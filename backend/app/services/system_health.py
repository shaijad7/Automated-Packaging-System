import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.models.health import EdgeHeartbeatPayload

_lock = threading.Lock()
_latest_heartbeat: Optional[EdgeHeartbeatPayload] = None
_received_at: Optional[float] = None


def record_edge_heartbeat(payload: EdgeHeartbeatPayload) -> Dict[str, Any]:
    """
    Stores the most recently received edge heartbeat telemetry in memory.
    Thread-safe and does not perform database writes or mutate inventory.
    """
    global _latest_heartbeat, _received_at
    with _lock:
        _latest_heartbeat = payload
        _received_at = time.time()
    return {
        "status": "recorded",
        "timestamp": payload.timestamp.isoformat(),
    }


def get_edge_health(stale_threshold_seconds: float = 60.0) -> Dict[str, Any]:
    """
    Evaluates current edge health status dynamically on every call based on server time,
    heartbeat receipt age, and independent camera/model runtime progress evidence.

    Status Semantics:
    - UNKNOWN: No heartbeat has ever been received since backend startup or evidence pending.
    - UP: Fresh heartbeat received within threshold with active camera/model evidence.
    - DEGRADED: Intermittent failures or degraded performance reported in fresh heartbeat.
    - DOWN: Camera/model failure explicitly reported, heartbeat timed out (>60s), or runtime progress stalled.
    """
    global _latest_heartbeat, _received_at
    with _lock:
        heartbeat = _latest_heartbeat
        received_at = _received_at

    if heartbeat is None or received_at is None:
        return {
            "camera_status": "UNKNOWN",
            "camera_details": "No edge heartbeat received",
            "model_status": "UNKNOWN",
            "model_details": "No edge heartbeat received",
            "last_heartbeat": None,
            "age_seconds": None,
            "is_stale": False,
            "fps": None,
            "last_frame_timestamp": None,
            "last_inference_timestamp": None,
        }

    now = time.time()
    age_seconds = max(0.0, round(now - received_at, 1))

    # 1. Edge node disconnection / heartbeat timeout
    if age_seconds > stale_threshold_seconds:
        stale_msg = f"Heartbeat telemetry stale (last received {int(age_seconds)}s ago)"
        return {
            "camera_status": "DOWN",
            "camera_details": stale_msg,
            "model_status": "DOWN",
            "model_details": stale_msg,
            "last_heartbeat": heartbeat.timestamp.isoformat(),
            "age_seconds": age_seconds,
            "is_stale": True,
            "fps": heartbeat.fps,
            "last_frame_timestamp": heartbeat.last_frame_timestamp,
            "last_inference_timestamp": heartbeat.last_inference_timestamp,
        }

    # 2. Fresh heartbeat received - evaluate reported status and independent runtime progress
    camera_status = heartbeat.camera
    camera_details = heartbeat.camera_details or ("Active stream" if heartbeat.camera == "UP" else "Unavailable")
    model_status = heartbeat.model
    model_details = heartbeat.model_details or ("Inference operational" if heartbeat.model == "UP" else "Unavailable")

    now_dt = datetime.now(timezone.utc)

    # Independent camera progress check:
    if camera_status == "UP":
        if heartbeat.last_frame_timestamp:
            try:
                frame_dt = datetime.fromisoformat(heartbeat.last_frame_timestamp.replace("Z", "+00:00"))
                frame_age = (now_dt - frame_dt).total_seconds()
                if frame_age > stale_threshold_seconds:
                    camera_status = "DOWN"
                    camera_details = f"Camera frame stream stalled (last frame {int(frame_age)}s ago)"
            except Exception:
                pass
        else:
            camera_status = "UNKNOWN"
            camera_details = "Awaiting initial frame acquisition evidence"

    # Independent model progress check:
    if model_status == "UP":
        if heartbeat.last_inference_timestamp:
            try:
                infer_dt = datetime.fromisoformat(heartbeat.last_inference_timestamp.replace("Z", "+00:00"))
                infer_age = (now_dt - infer_dt).total_seconds()
                if infer_age > stale_threshold_seconds:
                    model_status = "DOWN"
                    model_details = f"Inference stalled (last inference {int(infer_age)}s ago)"
            except Exception:
                pass
        else:
            model_status = "UNKNOWN"
            model_details = "Awaiting initial inference evidence"

    return {
        "camera_status": camera_status,
        "camera_details": camera_details,
        "model_status": model_status,
        "model_details": model_details,
        "last_heartbeat": heartbeat.timestamp.isoformat(),
        "age_seconds": age_seconds,
        "is_stale": False,
        "fps": heartbeat.fps,
        "last_frame_timestamp": heartbeat.last_frame_timestamp,
        "last_inference_timestamp": heartbeat.last_inference_timestamp,
    }


def reset_edge_health() -> None:
    """Testing helper to reset in-memory edge health state."""
    global _latest_heartbeat, _received_at
    with _lock:
        _latest_heartbeat = None
        _received_at = None
