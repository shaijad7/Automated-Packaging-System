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

def main():
    print("Starting YOLO load...")
    det = YoloDetector("runs/phase9_training/weights/best.pt", 0.5)
    print("Done")

if __name__ == "__main__":
    main()
