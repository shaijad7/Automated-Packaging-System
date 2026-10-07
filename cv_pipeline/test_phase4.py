import os
import time
import cv2
import numpy as np
from detector import YoloDetector

def test_missing_model():
    print("\n--- Test 1: Missing Model ---")
    detector = YoloDetector("invalid_model.pt", 0.5)
    
    if not detector.is_available:
        print("PASS: Detector correctly identified model as unavailable.")
    else:
        print("FAIL: Detector loaded an invalid model??")
        
    # Simulate a frame pass-through
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    out_frame, fps, _ = detector.predict(dummy_frame)
    if out_frame is dummy_frame and fps == 0.0:
        print("PASS: Missing model gracefully returns unmodified frame and 0.0 FPS.")
    else:
        print("FAIL: Missing model modified frame or returned non-zero FPS.")

def test_valid_model():
    print("\n--- Test 2: Valid Model (yolov8n.pt) ---")
    
    if not os.path.exists("yolov8n.pt"):
        print("SKIPPING: yolov8n.pt not found. Ensure it was downloaded.")
        return
        
    detector = YoloDetector("yolov8n.pt", 0.5)
    
    if detector.is_available:
        print("PASS: Detector loaded valid model.")
    else:
        print("FAIL: Detector failed to load valid model.")
        return
        
    # Generate a dummy frame with some noise/shapes so YOLO has something to look at (even if it finds nothing)
    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(dummy_frame, (100, 100), (300, 300), (255, 255, 255), -1) # White box
    
    # Warmup
    print("Warming up model...")
    for _ in range(3):
        detector.predict(dummy_frame)
        
    # Measure inference FPS
    print("Measuring inference performance (10 iterations)...")
    fps_list = []
    for _ in range(10):
        _, fps, _ = detector.predict(dummy_frame)
        fps_list.append(fps)
        
    avg_fps = sum(fps_list) / len(fps_list)
    print(f"PASS: Inference successful. Average Inference Performance: {avg_fps:.2f} FPS")
    print(f"      (Inference Time per frame: {1000.0/avg_fps:.1f} ms)")

if __name__ == "__main__":
    test_missing_model()
    test_valid_model()
