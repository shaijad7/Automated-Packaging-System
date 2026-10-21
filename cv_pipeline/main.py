import cv2
import signal
import sys
import time
import queue
import threading
import requests
import uuid
from datetime import datetime, timezone

from camera import CameraManager
from config import settings
from counting.line_counter import LineCounter
from qr.qr_detector import NativeQRDetector
from qr.association import validate_qrs, ValidationState, QRSmoother

import os
os.environ["YOLO_VERBOSE"] = "False"
os.environ["YOLO_OFFLINE"] = "True"
from detector import YoloDetector

from pathlib import Path
from spool import EventSpool
from heartbeat import EdgeHealthTracker, HeartbeatSender

# Global flag for graceful shutdown
running = True
event_queue = queue.Queue(maxsize=1000)
preserved_events = []
MAX_AUTH_RETRIES = 3

_CV_DIR = Path(__file__).resolve().parent
_spool_db = _CV_DIR / settings.EVENT_SPOOL_PATH if not Path(settings.EVENT_SPOOL_PATH).is_absolute() else Path(settings.EVENT_SPOOL_PATH)
spool = EventSpool(_spool_db, max_events=settings.EVENT_SPOOL_MAX_SIZE)

def signal_handler(sig, frame):
    global running
    print("\n[Main] Shutdown signal received (Ctrl+C). Terminating gracefully...")
    running = False

def validate_acknowledgement(response):
    """Validate backend HTTP response and JSON acknowledgement body.

    Requires a successful HTTP status and a JSON object whose 'msg' field is
    exactly 'Event recorded' or 'Event already processed'.
    Raises requests.exceptions.RequestException on invalid status or body.
    """
    response.raise_for_status()
    try:
        resp_json = response.json()
    except Exception as json_err:
        raise requests.exceptions.RequestException(
            f"Invalid JSON in backend response: {json_err}",
            response=response
        ) from json_err

    if not isinstance(resp_json, dict) or resp_json.get("msg") not in (
        "Event recorded",
        "Event already processed",
    ):
        msg_preview = str(resp_json)[:100] if isinstance(resp_json, dict) else type(resp_json).__name__
        raise requests.exceptions.RequestException(
            f"Unexpected acknowledgement body from backend: {msg_preview}",
            response=response
        )
    return resp_json


def event_worker():
    while running:
        try:
            event_payload = event_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        success = False
        consecutive_auth_errors = 0
        try:
            while running and not success:
                try:
                    headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}
                    response = requests.post(f"{settings.BACKEND_API_URL}/api/events/", json=event_payload, headers=headers, timeout=5.0)
                    if response.status_code == 401:
                        consecutive_auth_errors += 1
                        if "event_id" in event_payload:
                            spool.record_attempt(event_payload["event_id"], status="AUTH_FAILED", error="HTTP 401 Unauthorized")
                        print(f"[Worker] HTTP 401 Unauthorized: Backend rejected EDGE_NODE_API_KEY (Attempt {consecutive_auth_errors}/{MAX_AUTH_RETRIES}). Verify .env.")
                        if consecutive_auth_errors >= MAX_AUTH_RETRIES:
                            print(f"[Worker] Max auth retries reached for event {event_payload.get('event_id')}. Preserving event in persistent spool.")
                            preserved_events.append(event_payload)
                            break
                        for _ in range(15):
                            if not running:
                                break
                            time.sleep(0.2)
                        continue
                    validate_acknowledgement(response)
                    # Event was safely recorded or duplicate recognized by backend
                    if "event_id" in event_payload:
                        spool.mark_delivered(event_payload["event_id"])
                    success = True
                    consecutive_auth_errors = 0
                    print(f"[Worker] Event {event_payload.get('event_id')} sent successfully.")
                except requests.exceptions.RequestException as e:
                    status_code = getattr(getattr(e, 'response', None), 'status_code', None)
                    if status_code == 401:
                        consecutive_auth_errors += 1
                        if "event_id" in event_payload:
                            spool.record_attempt(event_payload["event_id"], status="AUTH_FAILED", error="HTTP 401 Unauthorized")
                        print(f"[Worker] HTTP 401 Unauthorized: Backend rejected key (Attempt {consecutive_auth_errors}/{MAX_AUTH_RETRIES}).")
                        if consecutive_auth_errors >= MAX_AUTH_RETRIES:
                            preserved_events.append(event_payload)
                            break
                    else:
                        if "event_id" in event_payload:
                            spool.record_attempt(event_payload["event_id"], status="PENDING", error=str(e))
                        print(f"[Worker] Network/HTTP Error sending event {event_payload.get('event_id')}: {e}. Retrying in 2s...")
                    for _ in range(10):
                        if not running:
                            break
                        time.sleep(0.2)
                except Exception as e:
                    if "event_id" in event_payload:
                        spool.record_attempt(event_payload["event_id"], status="PENDING", error=str(e))
                    print(f"[Worker] Error sending event {event_payload.get('event_id')}: {e}. Retrying in 2s...")
                    for _ in range(10):
                        if not running:
                            break
                        time.sleep(0.2)
            if not success and event_payload not in preserved_events:
                preserved_events.append(event_payload)
        finally:
            event_queue.task_done()


def main():
    global running
    
    # Recover unacknowledged pending events from durable spool on startup
    pending_events = spool.get_pending_events()
    if pending_events:
        print(f"[Main] Recovering {len(pending_events)} pending events from durable spool on startup.")
        for pe in pending_events:
            try:
                event_queue.put_nowait(pe)
            except queue.Full:
                print("[Main] Event queue full during recovery; remaining events stay in spool.")
                break

    # Start background worker for HTTP requests
    worker_thread = threading.Thread(target=event_worker, daemon=True)
    worker_thread.start()
    
    # Initialize edge health tracking and background heartbeat sender
    health_tracker = EdgeHealthTracker()
    heartbeat_sender = HeartbeatSender(
        tracker=health_tracker,
        backend_url=settings.BACKEND_API_URL,
        api_key=settings.EDGE_NODE_API_KEY,
        interval=10.0,
    )
    heartbeat_sender.start()

    print("[Main] Initializing YOLOv8 Detector...")
    detector = YoloDetector(settings.YOLO_MODEL_PATH, settings.YOLO_CONFIDENCE_THRESHOLD)
    if detector.is_available:
        health_tracker.record_model_loaded(True)
    else:
        health_tracker.record_model_loaded(False, error="YOLO model unavailable or file not found")
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"[Main] Initializing LineCounter from ({settings.LINE_START_X}, {settings.LINE_START_Y}) to ({settings.LINE_END_X}, {settings.LINE_END_Y})...")
    try:
        target_class = getattr(settings, "TARGET_CLASS_NAME", "box")
        counter = LineCounter(settings.LINE_START_X, settings.LINE_START_Y, settings.LINE_END_X, settings.LINE_END_Y, target_class=target_class)
    except ValueError as e:
        print(f"[Main] Fatal Error: {e}")
        heartbeat_sender.stop()
        return
        
    print("[Main] Initializing QR Detector...")
    qr_detector = NativeQRDetector()
    
    print("[Main] Initializing QR Smoother...")
    qr_smoother = QRSmoother(history_size=15, confirmation_thresh=3, drop_thresh=10)

    print("[Main] Initializing Camera Manager...")
    cam_manager = CameraManager()
    cam_manager.start()
    health_tracker.record_camera_opened(True)
    
    print("[Main] Starting processing loop. Press 'q' or 'Ctrl+C' to exit.")
    
    try:
        while running:
            frame = cam_manager.get_latest_frame()
            
            if frame is None:
                health_tracker.record_frame_read(False, error="Camera frame unavailable")
                print("[Main] Camera frame unavailable")
                # Must still pump events and check for quit even when disconnected
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("[Main] 'q' pressed. Initiating shutdown...")
                    running = False
                    break
                continue

            health_tracker.record_frame_read(True)

            # Run YOLO tracking inference
            try:
                annotated_frame, inference_fps, active_tracks = detector.predict(frame)
                if detector.is_available:
                    health_tracker.record_inference(True, fps=inference_fps)
                else:
                    health_tracker.record_inference(False, error="YOLO model unavailable")
            except Exception as infer_err:
                annotated_frame, inference_fps, active_tracks = frame, 0.0, []
                health_tracker.record_inference(False, error=str(infer_err))
            
            # Process counting
            crossings = counter.process_tracks(active_tracks)
            
            # Process QR Detection
            detected_qrs = qr_detector.detect(frame, bounding_boxes=active_tracks)
            validation_result = validate_qrs(active_tracks, detected_qrs)
            raw_track_states = validation_result["raw_track_states"]
            
            # Apply Temporal Smoothing
            track_states = qr_smoother.update(active_tracks, raw_track_states)

            
            # Draw Counting Line
            cv2.line(annotated_frame, 
                     (settings.LINE_START_X, settings.LINE_START_Y), 
                     (settings.LINE_END_X, settings.LINE_END_Y), 
                     (0, 0, 255), 3)
                     
            # Draw Centroids & QR States
            for track in active_tracks:
                t_id, cx, cy, x1, y1, x2, y2 = track[:7]
                cv2.circle(annotated_frame, (cx, cy), 5, (0, 0, 255), -1)
                
                # Retrieve QR state for this track
                state = track_states.get(t_id, {})
                status = state.get("status", ValidationState.NO_QR)
                payload = state.get("payload", None)
                
                if status == ValidationState.VALID_QR:
                    cv2.putText(annotated_frame, f"QR: {status.value}", (int(x1), int(y2) + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    cv2.putText(annotated_frame, f"QR Data: {payload}", (int(x1), int(y2) + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                else:
                    cv2.putText(annotated_frame, f"QR: {status.value}", (int(x1), int(y2) + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            
            # Draw QRs independent of tracks
            for qr in detected_qrs:
                poly = qr["polygon"]
                # Draw polygon
                cv2.polylines(annotated_frame, [poly], True, (255, 0, 255), 2)
                cv2.circle(annotated_frame, (qr["cx"], qr["cy"]), 3, (255, 0, 255), -1)
            
            # Draw Global Count
            cv2.putText(annotated_frame, f"Overall Boxes: {counter.total_count}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
            
            # Process Recent Crossings
            for c in crossings:
                t_id = c['track_id']
                direction = c['direction']
                state = track_states.get(t_id, {})
                qr_status = state.get("status", ValidationState.NO_QR).value
                qr_payload = state.get("payload", None)
                
                print(f"[Event] Overall Count: {counter.total_count} | track_id: {t_id} | qr_status: {qr_status} | direction: {direction}")
                
                # Phase 10B: Prepare and queue event payload
                event_id = str(uuid.uuid4())
                event_payload = {
                    "event_id": event_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "track_id": t_id,
                    "qr_status": qr_status,
                    "qr_payload": qr_payload,
                    "count_direction": direction
                }
                
                try:
                    spool.enqueue(event_payload)
                    event_queue.put_nowait(event_payload)
                    print(f"  -> [Spool] Persisted and queued event_id: {event_id}")
                except queue.Full:
                    print(f"[Warning] Event Queue FULL. Event {event_id} remains preserved in persistent spool.")
                except Exception as e:
                    print(f"[Error] Critical persistence failure for event {event_id}: {e}")
            
            # Overlay Inference FPS if available
            if detector.is_available:
                fps_text = f"Inference: {inference_fps:.1f} FPS"
                cv2.putText(annotated_frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            else:
                cv2.putText(annotated_frame, "YOLO Model Unavailable", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
            # Render the frame safely
            try:
                cv2.imshow("SMART INVENTORY - AI PROCESSING", annotated_frame)
            except cv2.error as e:
                print(f"[Main] Warning: Could not display frame (Headless/GUI error): {e}")
            
            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Main] 'q' pressed. Initiating shutdown...")
                running = False
                break
                
    except Exception as e:
        print(f"[Main] Unhandled exception in main loop: {e}")
    finally:
        health_tracker.record_shutdown("CV pipeline shut down")
        print("[Main] Stopping Heartbeat Sender...")
        heartbeat_sender.stop()
        print("[Main] Stopping Camera Manager...")
        cam_manager.stop()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        spool.close()
        print("[Main] Shutdown complete. Resources released.")

if __name__ == "__main__":
    main()
