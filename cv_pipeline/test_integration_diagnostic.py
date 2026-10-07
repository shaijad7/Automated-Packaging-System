import cv2
import time
import os
from ultralytics import YOLO
import numpy as np

def main():
    model_path = r"runs\phase9_training\weights\best.pt"
    if not os.path.exists(model_path):
        print(f"Model not found at {model_path}!")
        return
        
    print("Loading model...")
    model = YOLO(model_path)
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    qr_detector = cv2.QRCodeDetector()
    
    print("--- INTEGRATION DIAGNOSTIC ---")
    print("1. Move the box slowly across the scene and line.")
    print("2. Move the box from close -> medium -> far to test QR.")
    print("Press 'q' to quit and save the log.")
    
    log_data = []
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_count += 1
        
        # YOLO inference
        results = model.track(frame, conf=0.5, persist=True, tracker="bytetrack.yaml", verbose=False)
        
        # QR inference
        qr_ret, decoded_info, points, _ = qr_detector.detectAndDecodeMulti(frame)
        
        annotated = frame.copy()
        
        # Log Boxes
        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                if int(box.cls[0]) != 0: continue
                tid = int(box.id[0]) if box.id is not None else -1
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                
                log_msg = f"Frame {frame_count:04d} | YOLO: YES | ID: {tid:2d} | Conf: {conf:.2f} | BBox: {w}x{h}"
                log_data.append(log_msg)
                print(log_msg)
                
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0,255,0), 2)
                cv2.putText(annotated, f"ID: {tid}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
        else:
            log_msg = f"Frame {frame_count:04d} | YOLO: NO"
            log_data.append(log_msg)
            # print(log_msg) # Suppress empty frame logs slightly to avoid spam
            
        # Log QR
        if qr_ret and points is not None:
            for i, p in enumerate(decoded_info):
                poly = points[i].astype(int)
                qr_area = cv2.contourArea(poly)
                payload = p if p else "UNREADABLE"
                
                qr_msg = f"   -> QR Detected! Payload: '{payload}' | QR Area: {qr_area:.1f}"
                log_data.append(qr_msg)
                print(qr_msg)
                
                cv2.polylines(annotated, [poly], True, (255,0,255), 2)
                
        cv2.imshow("Diagnostic", annotated)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    
    with open("diagnostic_log.txt", "w") as f:
        f.write("\n".join(log_data))
    print("\nSaved diagnostic_log.txt")

if __name__ == '__main__':
    main()
