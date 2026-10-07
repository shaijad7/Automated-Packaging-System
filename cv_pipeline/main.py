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
from qr.association import validate_qrs, ValidationState

import os
os.environ["YOLO_VERBOSE"] = "False"
os.environ["YOLO_OFFLINE"] = "True"
from detector import YoloDetector

# Global flag for graceful shutdown
running = True
event_queue = queue.Queue(maxsize=1000)

def signal_handler(sig, frame):
    global running
    print("\n[Main] Shutdown signal received (Ctrl+C). Terminating gracefully...")
    running = False

def event_worker():
    while running:
        try:
            event_payload = event_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        success = False
        while running and not success:
            try:
                headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}
                response = requests.post(f"{settings.BACKEND_API_URL}/api/events/", json=event_payload, headers=headers, timeout=5.0)
                response.raise_for_status()
                success = True
                print(f"[Worker] Event {event_payload['event_id']} sent successfully.")
            except Exception as e:
                print(f"[Worker] HTTP Error sending event {event_payload['event_id']}: {e}. Retrying in 2s...")
                time.sleep(2.0)
        event_queue.task_done()

def main():
    global running
    
    # Start background worker for HTTP requests
    worker_thread = threading.Thread(target=event_worker, daemon=True)
    worker_thread.start()
    
    print("[Main] Initializing YOLOv8 Detector...")
    detector = YoloDetector(settings.YOLO_MODEL_PATH, settings.YOLO_CONFIDENCE_THRESHOLD)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"[Main] Initializing LineCounter from ({settings.LINE_START_X}, {settings.LINE_START_Y}) to ({settings.LINE_END_X}, {settings.LINE_END_Y})...")
    try:
        target_class = getattr(settings, "TARGET_CLASS_NAME", "box")
        counter = LineCounter(settings.LINE_START_X, settings.LINE_START_Y, settings.LINE_END_X, settings.LINE_END_Y, target_class=target_class)
    except ValueError as e:
        print(f"[Main] Fatal Error: {e}")
        return
        
    print("[Main] Initializing QR Detector...")
    qr_detector = NativeQRDetector()
    
    print("[Main] Initializing Camera Manager...")
    cam_manager = CameraManager()
    cam_manager.start()
    
    print("[Main] Starting processing loop. Press 'q' or 'Ctrl+C' to exit.")
    
    try:
        while running:
            frame = cam_manager.get_latest_frame()
            
            if frame is None:
                print("[Main] Camera frame unavailable")
                # Must still pump events and check for quit even when disconnected
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("[Main] 'q' pressed. Initiating shutdown...")
                    running = False
                    break
                continue
                
            # Run YOLO tracking inference
            annotated_frame, inference_fps, active_tracks = detector.predict(frame)
            
            # Process counting
            crossings = counter.process_tracks(active_tracks)
            
            # Process QR Detection
            detected_qrs = qr_detector.detect(frame, bounding_boxes=active_tracks)
            validation_result = validate_qrs(active_tracks, detected_qrs)
            track_states = validation_result["track_states"]
            
            # Phase 10B: Basic format validation (let backend verify if product is active/real)
            for t_id, state in track_states.items():
                if state.get("status") == ValidationState.INVALID_QR:
                    payload = state.get("payload")
                    if payload and payload.startswith("INV|"):
                        state["status"] = ValidationState.VALID_QR
            
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
                    event_queue.put_nowait(event_payload)
                    print(f"  -> [Phase 10B] Queued event_id: {event_id}")
                except queue.Full:
                    print(f"[Warning] Event Queue FULL. Dropping event: {event_id}")
            
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
        print("[Main] Stopping Camera Manager...")
        cam_manager.stop()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        print("[Main] Shutdown complete. Resources released.")

if __name__ == "__main__":
    main()
