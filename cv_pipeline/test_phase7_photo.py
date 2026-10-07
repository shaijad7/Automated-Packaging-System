import cv2
import os
from detector import YoloDetector
from qr.qr_detector import NativeQRDetector
from qr.association import validate_qrs

def test_photo_mode():
    photo_path = "real_box_photo.jpg"
    
    if not os.path.exists(photo_path):
        print(f"\n[Photo Mode] PENDING: No real photo found at '{photo_path}'.")
        print("Please supply your real physical box photos with QR codes attached.")
        return
        
    print(f"\n--- Phase 7: Real Photo Mode Test ({photo_path}) ---")
    frame = cv2.imread(photo_path)
    
    # Run Detector
    detector = YoloDetector("yolov8n.pt", 0.5)
    annotated_frame, _, active_tracks = detector.predict(frame)
    
    # Run QR
    qr_detector = NativeQRDetector()
    detected_qrs = qr_detector.detect(frame)
    
    # Validate
    validation_result = validate_qrs(active_tracks, detected_qrs)
    track_states = validation_result["track_states"]
    
    print(f"Total Tracks Found: {len(active_tracks)}")
    print(f"Total QRs Found: {len(detected_qrs)}")
    
    for qr in detected_qrs:
        print(f" - Detected QR Payload: {qr['payload']} at ({qr['cx']}, {qr['cy']})")
        
    for t_id, state in track_states.items():
        print(f" - Track {t_id} Validation: {state['status'].value} (Payload: {state['payload']})")
        
if __name__ == "__main__":
    test_photo_mode()
