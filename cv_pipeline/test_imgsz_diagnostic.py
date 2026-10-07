import cv2
import time
import os
from ultralytics import YOLO

def main():
    model_path = r"runs\phase9_training\weights\best.pt"
    if not os.path.exists(model_path):
        print(f"Model not found at {model_path}!")
        return
    
    print("Loading model...")
    model = YOLO(model_path)
    source = 1
    
    print(f"Opening camera {source}...")
    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Failed to open camera.")
        return
        
    window_name = "Visual Comparison Diagnostic"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
    cv2.resizeWindow(window_name, 800, 600)
    
    current_size = 640
    print("\n--- Interactive Visual Comparison ---")
    print("Press '1' -> imgsz=640")
    print("Press '2' -> imgsz=512")
    print("Press '3' -> imgsz=416")
    print("Press 'q' -> quit")
    
    stats = {
        640: {"frames": 0, "total_inf_time": 0.0, "total_dets": 0},
        512: {"frames": 0, "total_inf_time": 0.0, "total_dets": 0},
        416: {"frames": 0, "total_inf_time": 0.0, "total_dets": 0}
    }
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        inf_start = time.time()
        res = model.predict(frame, conf=0.5, imgsz=current_size, verbose=False)
        inf_time = time.time() - inf_start
        
        stats[current_size]["frames"] += 1
        stats[current_size]["total_inf_time"] += inf_time
        
        # Draw for user observation
        annotated = frame.copy()
        dets = 0
        for box in res[0].boxes:
            if int(box.cls[0]) == 0:
                dets += 1
                stats[current_size]["total_dets"] += 1
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"box {conf:.2f}", (x1, max(y1-10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # Overlay text
        cv2.putText(annotated, f"imgsz: {current_size} | Dets: {dets} | FPS: {1.0/(inf_time+0.001):.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
        cv2.putText(annotated, "Press 1(640) 2(512) 3(416) q(Quit)", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
        cv2.imshow(window_name, annotated)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Quitting...")
            break
        elif key == ord('1'):
            if current_size != 640:
                current_size = 640
                print("Switched to imgsz=640")
        elif key == ord('2'):
            if current_size != 512:
                current_size = 512
                print("Switched to imgsz=512")
        elif key == ord('3'):
            if current_size != 416:
                current_size = 416
                print("Switched to imgsz=416")

    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "="*50)
    print("VISUAL COMPARISON SUMMARY REPORT")
    print("="*50)
    for size in [640, 512, 416]:
        s = stats[size]
        avg_fps = s["frames"] / s["total_inf_time"] if s["total_inf_time"] > 0 else 0
        avg_dets = s["total_dets"] / s["frames"] if s["frames"] > 0 else 0
        print(f"Input Size: {size}")
        print(f"  Frames Processed : {s['frames']}")
        print(f"  Avg Inference FPS: {avg_fps:.2f}")
        print(f"  Total Detections : {s['total_dets']}")
        print(f"  Avg Dets / Frame : {avg_dets:.2f}")
        print("-" * 50)
    print("Window displayed successfully.")

if __name__ == '__main__':
    main()
