import cv2
import os
import glob
from detector import YoloDetector
from qr.qr_detector import NativeQRDetector
from qr.association import validate_qrs

def run_photo_tests():
    photo_dir = "test_media/photos"
    if not os.path.exists(photo_dir):
        print(f"Directory {photo_dir} does not exist.")
        return

    # Gather all images
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(photo_dir, ext)))
        
    image_paths = list(set(image_paths))
    image_paths.sort()

    print(f"\n--- Phase 7: Real Photo Mode Test (Found {len(image_paths)} photos) ---")
    
    # Initialize Detectors
    detector = YoloDetector("yolov8n.pt", 0.5)
    qr_detector = NativeQRDetector()

    for idx, path in enumerate(image_paths, 1):
        print(f"\n[{idx}/{len(image_paths)}] Testing {os.path.basename(path)}")
        frame = cv2.imread(path)
        if frame is None:
            print("Failed to read image.")
            continue
            
        # YOLO Detection
        annotated_frame, _, active_tracks = detector.predict(frame)
        print(f"YOLO boxes detected: {len(active_tracks) > 0} ({len(active_tracks)} boxes)")
        
        # QR Detection
        detected_qrs = qr_detector.detect(frame)
        print(f"QR detected: {'YES' if detected_qrs else 'NO'}")
        
        for qr in detected_qrs:
            print(f"  - Payload: {qr['payload']}")
            print(f"  - Center: ({qr['cx']}, {qr['cy']})")
            print(f"  - Polygon: {qr['polygon'].tolist()}")
            
        # Association
        if active_tracks and detected_qrs:
            validation_result = validate_qrs(active_tracks, detected_qrs)
            track_states = validation_result["track_states"]
            unmatched = validation_result["unmatched_qrs"]
            ambiguous = validation_result["ambiguous_qrs"]
            
            print(f"Association Results:")
            for t_id, state in track_states.items():
                print(f"  - Track {t_id} Validation: {state['status'].value}")
            for u in unmatched:
                print(f"  - UNMATCHED QR: {u['payload']}")
            for a in ambiguous:
                print(f"  - AMBIGUOUS QR: {a['payload']}")
        else:
            if detected_qrs and not active_tracks:
                print("Association Results:")
                for qr in detected_qrs:
                    print(f"  - UNMATCHED QR: {qr['payload']} (No YOLO boxes)")
            elif not detected_qrs and active_tracks:
                print("Association Results:")
                for track in active_tracks:
                    print(f"  - Track {track[0]} Validation: MISSING (No QRs detected)")

if __name__ == "__main__":
    run_photo_tests()
