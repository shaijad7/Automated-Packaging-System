import cv2
import urllib.request
import os
from detector import YoloDetector

def test_real_tracking():
    video_path = "sample_test.mp4"
    if not os.path.exists(video_path):
        print("Downloading sample video for real tracking test...")
        urllib.request.urlretrieve("https://github.com/intel-iot-devkit/sample-videos/raw/master/people-detection.mp4", video_path)
    
    print("\n--- Test 3, 4, 5: Real Object Tracking ---")
    detector = YoloDetector("yolov8n.pt", 0.5)
    cap = cv2.VideoCapture(video_path)
    
    frame_count = 0
    active_history = {}
    
    print("Processing first 150 frames of real video feed...")
    while cap.isOpened() and frame_count < 150:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Run tracking
        _, _, track_ids = detector.predict(frame)
        
        # Log active IDs
        for tid in track_ids:
            if tid not in active_history:
                active_history[tid] = []
            active_history[tid].append(frame_count)
            
        frame_count += 1
        
    cap.release()
    
    print("\nTracking ID Observational Results:")
    for tid, frames in active_history.items():
        start = frames[0]
        end = frames[-1]
        missed = (end - start + 1) - len(frames)
        print(f"Track ID {tid}: Active from frame {start} to {end} (Missed {missed} frames in between)")
        
if __name__ == "__main__":
    test_real_tracking()
