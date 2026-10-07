import cv2
import threading
import queue
import time
from config import settings

class CameraManager:
    def __init__(self, camera_source=settings.CAMERA_SOURCE):
        self.camera_source = camera_source
        self.frame_queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.cap = None

    def start(self):
        """Starts the background capture thread."""
        self.stop_event.clear()
        self.capture_thread.start()

    def stop(self):
        """Signals the capture thread to stop and cleans up resources."""
        self.stop_event.set()
        if self.capture_thread.is_alive():
            self.capture_thread.join(timeout=3.0)
        # We do not release self.cap here anymore to prevent threading deadlocks on Windows

    def _init_camera(self):
        """Attempts to open the camera and set desired properties."""
        print(f"[CameraManager] Attempting to connect to camera source: {self.camera_source}")
        
        if self.cap is not None:
            self.cap.release()
            
        import os
        if os.name == 'nt':
            self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self.camera_source)
        
        if not self.cap.isOpened():
            print(f"[CameraManager] ERROR: Failed to open camera source: {self.camera_source}")
            return False
            
        # Request configured properties
        print(f"[CameraManager] Requesting configured properties -> Resolution: {settings.CAMERA_WIDTH}x{settings.CAMERA_HEIGHT}, FPS: {settings.CAMERA_FPS}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS)
            
        # Verify actual settings
        actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        print(f"[CameraManager] Connected to source {self.camera_source}.")
        print(f"[CameraManager] Actual Properties applied by driver -> Resolution: {int(actual_w)}x{int(actual_h)}, FPS: {actual_fps}")
        return True

    def _capture_loop(self):
        """Background thread loop to pull the latest frames."""
        reconnect_delay = 2.0
        
        try:
            while not self.stop_event.is_set():
                if self.cap is None or not self.cap.isOpened():
                    success = self._init_camera()
                    if not success:
                        print(f"[CameraManager] Retrying connection in {reconnect_delay} seconds...")
                        for _ in range(int(reconnect_delay * 10)):
                            if self.stop_event.is_set():
                                break
                            time.sleep(0.1)
                        continue
                
                ret, frame = self.cap.read()
                
                if not ret or frame is None:
                    print(f"[CameraManager] WARNING: Frame read failed or camera disconnected. Forcing reconnect to {self.camera_source}...")
                    if self.cap:
                        self.cap.release()
                    self.cap = None
                    for _ in range(int(reconnect_delay * 10)):
                        if self.stop_event.is_set():
                            break
                        time.sleep(0.1)
                    continue
                    
                # Maintain newest-frame-only queue
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait() # Remove old frame
                    except queue.Empty:
                        pass
                    try:
                        self.frame_queue.put_nowait(frame) # Push newest frame
                    except queue.Full:
                        pass
        finally:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            print("[CameraManager] Capture thread exited and camera released.")

    def get_latest_frame(self):
        """Retrieves the most recent frame from the queue, blocking until available."""
        try:
            return self.frame_queue.get(timeout=1.0)
        except queue.Empty:
            return None
