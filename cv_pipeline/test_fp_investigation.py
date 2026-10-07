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
        
    window_name = "False Positive Investigation"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)
    cv2.resizeWindow(window_name, 800, 600)
    
    scene_names = {
        '1': "1: Empty Scene",
        '2': "2: Person Only",
        '3': "3: Single Box",
        '4': "4: Two Boxes",
        '5': "5: Person Holding Box"
    }
    
    current_scene = None
    stats = {k: {"frames": 0, "frames_with_det": 0, "total_dets": 0, "confs": []} for k in scene_names.keys()}
    
    print("\n--- False Positive Investigation ---")
    for k, v in scene_names.items():
        print(f"Press '{k}' -> Start recording {v}")
    print("Press 'q' -> quit and print report")
    print("Currently NOT recording. Press 1-5 to start.")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        res = model.predict(frame, conf=0.5, imgsz=512, verbose=False)
        
        annotated = frame.copy()
        dets = 0
        confs = []
        for box in res[0].boxes:
            if int(box.cls[0]) == 0:
                dets += 1
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                confs.append(conf)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(annotated, f"box {conf:.2f}", (x1, max(y1-10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        if current_scene:
            stats[current_scene]["frames"] += 1
            if dets > 0:
                stats[current_scene]["frames_with_det"] += 1
                stats[current_scene]["total_dets"] += dets
                stats[current_scene]["confs"].extend(confs)
                
        status_text = f"Recording: {scene_names[current_scene]}" if current_scene else "NOT RECORDING - Press 1-5"
        color = (0, 255, 0) if current_scene else (0, 165, 255)
        
        cv2.putText(annotated, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(annotated, f"Dets: {dets}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.imshow(window_name, annotated)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Quitting...")
            break
        elif chr(key) in scene_names:
            current_scene = chr(key)
            print(f"Started recording {scene_names[current_scene]}")

    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "="*60)
    print("FALSE POSITIVE INVESTIGATION REPORT (imgsz=512)")
    print("="*60)
    for k, v in scene_names.items():
        s = stats[k]
        frames = s["frames"]
        if frames == 0:
            print(f"Scene {v}: No data recorded.")
            print("-" * 60)
            continue
            
        freq = (s["frames_with_det"] / frames) * 100
        avg_confs = sum(s["confs"]) / len(s["confs"]) if s["confs"] else 0.0
        max_conf = max(s["confs"]) if s["confs"] else 0.0
        min_conf = min(s["confs"]) if s["confs"] else 0.0
        
        print(f"Scene {v}:")
        print(f"  Frames recorded : {frames}")
        print(f"  Frames w/ det   : {s['frames_with_det']} ({freq:.1f}%)")
        print(f"  Total Detections: {s['total_dets']}")
        if s["confs"]:
            print(f"  Confidences     : min={min_conf:.2f}, max={max_conf:.2f}, avg={avg_confs:.2f}")
        else:
            print("  Confidences     : N/A")
        
        # Analyze false positives logically
        if k in ['1', '2']: # Expected 0
            if s['total_dets'] > 0:
                print(f"  => OBSERVATION: False positives occurred in {freq:.1f}% of frames!")
            else:
                print("  => OBSERVATION: Perfect. No false positives.")
        elif k == '3': # Expected 1
            if s['total_dets'] > frames:
                print("  => OBSERVATION: Extra/false boxes detected!")
        elif k == '4': # Expected 2
            if s['total_dets'] > frames * 2:
                print("  => OBSERVATION: Extra/false boxes detected!")
        elif k == '5': # Expected 1
            if s['total_dets'] > frames:
                print("  => OBSERVATION: Extra/false boxes detected!")
                
        print("-" * 60)

if __name__ == '__main__':
    main()
