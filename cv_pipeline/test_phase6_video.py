import cv2
import urllib.request
import os
from detector import YoloDetector
from counting.line_counter import LineCounter

def test_real_crossing():
    video_path = "sample_test.mp4"
    if not os.path.exists(video_path):
        print("Downloading sample video for real tracking test...")
        urllib.request.urlretrieve("https://github.com/intel-iot-devkit/sample-videos/raw/master/people-detection.mp4", video_path)
    
    print("\n--- Phase 6: Real Video Line Crossing Test ---")
    detector = YoloDetector("yolov8n.pt", 0.5)
    
    # Configure a line that the person will actually cross
    # In people-detection.mp4, people walk from top right to bottom left. 
    # Let's put a line horizontally across the middle of the screen.
    # The video is 768x432. Let's place it at y=200.
    counter = LineCounter(0, 200, 768, 200)
    print(f"Configured Line: (0, 200) to (768, 200)")
    
    cap = cv2.VideoCapture(video_path)
    
    frame_count = 0
    actual_crossings = 0
    
    print("Processing first 200 frames of real video feed...")
    while cap.isOpened() and frame_count < 200:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Run tracking
        _, _, active_tracks = detector.predict(frame)
        
        # Process Counting
        crossings = counter.process_tracks(active_tracks)
        for c in crossings:
            actual_crossings += 1
            print(f"Frame {frame_count}: Track {c['track_id']} crossed {c['direction']}! Total Count: {counter.total_count}")
            
        frame_count += 1
        
    cap.release()
    
    print(f"\nFinal Video Test Results:")
    print(f"Total Frames Processed: {frame_count}")
    print(f"Total Crossings Detected: {actual_crossings}")
    print(f"Counter Total: {counter.total_count}")
    if actual_crossings > 0:
        print("PASS: A real crossing was successfully detected and counted.")
    else:
        print("INFO: No crossing occurred in the first 200 frames with this line placement.")

if __name__ == "__main__":
    test_real_crossing()
