import cv2
import os
from detector import YoloDetector
from qr.qr_detector import NativeQRDetector
from qr.association import validate_qrs

def test_video_mode():
    video_path = "real_box_video.mp4"
    
    if not os.path.exists(video_path):
        print(f"\n[Video Mode] PENDING: No real video found at '{video_path}'.")
        print("Please supply your real physical box video with QR codes attached.")
        return
        
    print(f"\n--- Phase 7: Real Video Mode Test ({video_path}) ---")
    cap = cv2.VideoCapture(video_path)
    detector = YoloDetector("yolov8n.pt", 0.5)
    qr_detector = NativeQRDetector()
    
    frame_count = 0
    while cap.isOpened() and frame_count < 100:
        ret, frame = cap.read()
        if not ret: break
        
        _, _, active_tracks = detector.predict(frame)
        detected_qrs = qr_detector.detect(frame)
        res = validate_qrs(active_tracks, detected_qrs)
        
        if detected_qrs:
            print(f"Frame {frame_count}: Found {len(detected_qrs)} QRs.")
            
        frame_count += 1
        
    cap.release()
    print("Video processing complete.")

if __name__ == "__main__":
    test_video_mode()
