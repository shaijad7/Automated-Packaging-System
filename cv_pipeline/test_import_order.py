import cv2
print("Imported cv2")
from ultralytics import YOLO
print("Imported YOLO")
model = YOLO("runs/phase9_training/weights/best.pt")
print("DONE")
