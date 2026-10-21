import time
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger("cv_pipeline.heartbeat")


class EdgeHealthTracker:
    """
    Thread-safe tracker for CV pipeline runtime camera and model health evidence.
    Derives authoritative status (UP, DOWN, DEGRADED, UNKNOWN) strictly from actual
    runtime frames and inference execution, never from configuration alone.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # General state
        self.is_stopped: bool = False

        # Camera telemetry state
        self.camera_opened: bool = False
        self.camera_error: Optional[str] = None
        self.last_frame_read_time: Optional[float] = None
        self.last_frame_iso: Optional[str] = None
        self.total_frames_read: int = 0
        self.consecutive_frame_failures: int = 0

        # AI model telemetry state
        self.model_loaded: bool = False
        self.model_load_error: Optional[str] = None
        self.last_inference_time: Optional[float] = None
        self.last_inference_iso: Optional[str] = None
        self.total_inferences: int = 0
        self.consecutive_inference_failures: int = 0
        self.inference_error: Optional[str] = None
        self.last_fps: float = 0.0

    def record_camera_opened(self, success: bool = True, error: Optional[str] = None) -> None:
        with self._lock:
            self.camera_opened = success
            self.camera_error = error if not success else None

    def record_frame_read(self, success: bool, error: Optional[str] = None) -> None:
        with self._lock:
            now = time.time()
            if success:
                self.last_frame_read_time = now
                self.last_frame_iso = datetime.now(timezone.utc).isoformat()
                self.total_frames_read += 1
                self.consecutive_frame_failures = 0
                self.camera_opened = True
                self.camera_error = None
            else:
                self.consecutive_frame_failures += 1
                if error:
                    self.camera_error = str(error)[:150]

    def record_model_loaded(self, success: bool, error: Optional[str] = None) -> None:
        with self._lock:
            self.model_loaded = success
            self.model_load_error = str(error)[:150] if not success and error else None

    def record_inference(self, success: bool, fps: float = 0.0, error: Optional[str] = None) -> None:
        with self._lock:
            now = time.time()
            if success:
                self.last_inference_time = now
                self.last_inference_iso = datetime.now(timezone.utc).isoformat()
                self.total_inferences += 1
                self.consecutive_inference_failures = 0
                self.last_fps = float(fps)
                self.inference_error = None
            else:
                self.consecutive_inference_failures += 1
                if error:
                    self.inference_error = str(error)[:150]

    def record_shutdown(self, reason: str = "CV pipeline stopped") -> None:
        """Explicitly records that the pipeline runtime has terminated."""
        with self._lock:
            self.is_stopped = True
            self.camera_opened = False
            self.camera_error = reason
            self.model_loaded = False
            self.model_load_error = reason
            self.last_frame_read_time = None
            self.last_inference_time = None

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            iso_now = datetime.now(timezone.utc).isoformat()

            if self.is_stopped:
                return {
                    "timestamp": iso_now,
                    "camera": "DOWN",
                    "camera_details": self.camera_error or "CV pipeline stopped",
                    "model": "DOWN",
                    "model_details": self.model_load_error or "CV pipeline stopped",
                    "fps": None,
                    "last_frame_timestamp": self.last_frame_iso,
                    "last_inference_timestamp": self.last_inference_iso,
                }

            # 1. Determine Camera Status
            # Must have opened AND read at least one frame recently
            if not self.camera_opened or self.total_frames_read == 0 or self.last_frame_read_time is None:
                if self.camera_error:
                    camera_status = "DOWN"
                    camera_details = f"Camera failed: {self.camera_error}"
                else:
                    camera_status = "UNKNOWN"
                    camera_details = "Awaiting camera initialization and initial frames"
            elif self.consecutive_frame_failures >= 3:
                camera_status = "DOWN"
                camera_details = self.camera_error or f"Camera disconnected ({self.consecutive_frame_failures} consecutive frame read failures)"
            elif (now - self.last_frame_read_time) > 15.0:
                camera_status = "DOWN"
                camera_details = f"Camera stream stalled (no frames for {int(now - self.last_frame_read_time)}s)"
            elif self.consecutive_frame_failures > 0 or (now - self.last_frame_read_time) > 5.0:
                camera_status = "DEGRADED"
                camera_details = "Intermittent frame drops or latency detected"
            else:
                camera_status = "UP"
                camera_details = "Camera stream active and delivering frames"

            # 2. Determine Model Status
            # Must have loaded AND run at least one inference recently
            if not self.model_loaded:
                if self.model_load_error:
                    model_status = "DOWN"
                    model_details = f"Model load failed: {self.model_load_error}"
                else:
                    model_status = "UNKNOWN"
                    model_details = "Model initialization pending"
            elif self.total_inferences == 0 or self.last_inference_time is None:
                model_status = "UNKNOWN"
                model_details = "Model loaded; awaiting initial frame for inference"
            elif self.consecutive_inference_failures >= 3:
                model_status = "DOWN"
                model_details = self.inference_error or f"Inference failing ({self.consecutive_inference_failures} consecutive failures)"
            elif (now - self.last_inference_time) > 15.0:
                model_status = "DOWN"
                model_details = f"Inference stalled (no inference for {int(now - self.last_inference_time)}s)"
            elif self.consecutive_inference_failures > 0 or (now - self.last_inference_time) > 5.0:
                model_status = "DEGRADED"
                model_details = "Intermittent inference drops"
            else:
                model_status = "UP"
                fps_val = round(self.last_fps, 1)
                model_details = f"Inference active ({fps_val} FPS)" if fps_val > 0 else "Inference active"

            fps_report = round(self.last_fps, 1) if self.last_fps > 0 else None

            return {
                "timestamp": iso_now,
                "camera": camera_status,
                "camera_details": camera_details[:200],
                "model": model_status,
                "model_details": model_details[:200],
                "fps": fps_report,
                "last_frame_timestamp": self.last_frame_iso,
                "last_inference_timestamp": self.last_inference_iso,
            }


class HeartbeatSender:
    """
    Background sender that periodically posts runtime telemetry to the backend.
    Failures in heartbeat delivery never crash, block, or delay the CV pipeline.
    """

    def __init__(
        self,
        tracker: EdgeHealthTracker,
        backend_url: str,
        api_key: str,
        interval: float = 10.0,
        timeout: float = 5.0,
    ):
        self.tracker = tracker
        self.backend_url = backend_url.rstrip("/")
        self.api_key = api_key
        self.interval = max(2.0, interval)
        self.timeout = timeout
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._last_log_time: float = 0.0

    def start(self) -> None:
        """Starts the background heartbeat sender thread."""
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, name="HeartbeatSender", daemon=True)
        self.thread.start()
        logger.info("[Heartbeat] Sender started (interval: %.1fs).", self.interval)

    def send_shutdown_heartbeat(self) -> bool:
        """
        Sends one final authenticated DOWN heartbeat on normal shutdown.
        Uses a short timeout (1.5s) so shutdown never hangs if network is unavailable.
        """
        try:
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "camera": "DOWN",
                "camera_details": "CV pipeline process terminated",
                "model": "DOWN",
                "model_details": "CV pipeline process terminated",
                "fps": None,
                "last_frame_timestamp": self.tracker.last_frame_iso,
                "last_inference_timestamp": self.tracker.last_inference_iso,
            }
            url = f"{self.backend_url}/api/edge/heartbeat"
            headers = {"X-API-Key": self.api_key}
            resp = requests.post(url, json=payload, headers=headers, timeout=1.5)
            if resp.status_code == 200:
                logger.info("[Heartbeat] Final shutdown heartbeat sent (DOWN).")
                return True
            return False
        except Exception as e:
            logger.debug("[Heartbeat] Could not send shutdown heartbeat: %s", e)
            return False

    def stop(self, timeout: float = 3.0) -> None:
        """Stops the background sender cleanly, attempting one final shutdown heartbeat."""
        self.stop_event.set()
        # Attempt quick shutdown notification (non-blocking if server unreachable)
        self.send_shutdown_heartbeat()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
        logger.info("[Heartbeat] Sender stopped.")

    def send_one(self) -> bool:
        """Transmits a single heartbeat payload. Returns True if accepted, False otherwise."""
        payload = self.tracker.get_telemetry()
        url = f"{self.backend_url}/api/edge/heartbeat"
        headers = {"X-API-Key": self.api_key}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                logger.debug(
                    "[Heartbeat] Telemetry sent: camera=%s, model=%s",
                    payload.get("camera"), payload.get("model")
                )
                return True
            else:
                now = time.time()
                if now - self._last_log_time > 30.0:
                    logger.warning(
                        "[Heartbeat] Server returned HTTP %d on heartbeat: %s",
                        resp.status_code, resp.text[:100]
                    )
                    self._last_log_time = now
                return False
        except Exception as e:
            now = time.time()
            if now - self._last_log_time > 30.0:
                logger.warning("[Heartbeat] Delivery failed (will retry): %s", e)
                self._last_log_time = now
            return False

    def _run_loop(self) -> None:
        # Initial slight delay so camera/model can start before the very first heartbeat
        self.stop_event.wait(1.0)
        while not self.stop_event.is_set():
            self.send_one()
            self.stop_event.wait(self.interval)
