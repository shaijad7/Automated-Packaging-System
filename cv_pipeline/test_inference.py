import os
import sys
import time
import cv2
import torch
import ultralytics

print("========================================")
print("1. ENVIRONMENT INFO")
print(f"Python version: {sys.version.split(' ')[0]}")
print(f"PyTorch version: {torch.__version__}")
print(f"Ultralytics version: {ultralytics.__version__}")
print(f"OpenCV version: {cv2.__version__}")
print(f"PyTorch threads: {torch.get_num_threads()}")
try:
    print("Testing CPU tensor operation...")
    x = torch.rand(10, 10).cpu()
    y = torch.matmul(x, x.T)
    print("CPU tensor operation: SUCCESS")
except Exception as e:
    print(f"CPU tensor operation: FAILED ({e})")
print("========================================")

print("\n2. CAPTURING FRAME")
# Turn off ultralytics sync
os.environ["YOLO_VERBOSE"] = "True"
os.environ["YOLO_OFFLINE"] = "True"
from ultralytics import settings as yolo_settings
yolo_settings.update({"sync": False})

cap = cv2.VideoCapture(1) # As per .env
ret, frame = cap.read()
cap.release()
if not ret or frame is None:
    print("Failed to capture frame from camera. Creating dummy frame.")
    import numpy as np
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
else:
    print("Captured real frame from camera.")
print("========================================")

print("\n3. LOADING MODEL")
from ultralytics import YOLO
model_path = "runs/phase9_training/weights/best.pt"
try:
    model = YOLO(model_path)
    print(f"Model loaded successfully from {model_path}.")
except Exception as e:
    print(f"Model load FAILED: {e}")
    sys.exit(1)
print("========================================")

print("\n4. TESTING model.predict()")
try:
    start = time.time()
    results = model.predict(source=frame, device="cpu", verbose=True)
    print(f"model.predict() SUCCESS in {time.time() - start:.3f}s")
except Exception as e:
    print(f"model.predict() FAILED: {e}")
print("========================================")

print("\n5. TESTING model.track()")
try:
    start = time.time()
    results = model.track(source=frame, device="cpu", persist=True, tracker="bytetrack.yaml", verbose=True)
    print(f"model.track() SUCCESS in {time.time() - start:.3f}s")
except Exception as e:
    print(f"model.track() FAILED: {e}")
print("========================================")

print("\nTEST COMPLETED.")
