import cv2
import signal
import sys
import time
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

def signal_handler(sig, frame):
    global running
    print("\n[Main] Shutdown signal received (Ctrl+C). Terminating gracefully...")
    running = False

def main():
    global running
    print("[Main] Initializing YOLOv8 Detector...")
    detector = YoloDetector(settings.YOLO_MODEL_PATH, settings.YOLO_CONFIDENCE_THRESHOLD)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"[Main] Initializing LineCounter from ({settings.LINE_START_X}, {settings.LINE_START_Y}) to ({settings.LINE_END_X}, {settings.LINE_END_Y})...")
    
if __name__ == "__main__":
    main()
