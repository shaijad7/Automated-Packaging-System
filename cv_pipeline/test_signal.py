import signal
def handler(s, f): pass
signal.signal(signal.SIGINT, handler)
print("Signal registered")
from ultralytics import YOLO
print("YOLO imported")
model = YOLO("runs/phase9_training/weights/best.pt")
print("DONE")
