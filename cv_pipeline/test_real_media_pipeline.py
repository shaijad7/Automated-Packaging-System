"""
Real Video Pipeline Verification Script.
Evaluates custom YOLO model + ByteTrack + NativeQRDetector + QRSmoother on the real video dataset.
"""

import os
import cv2
import time
import numpy as np

from detector import YoloDetector
from counting.line_counter import LineCounter
from qr.qr_detector import NativeQRDetector
from qr.association import validate_qrs, ValidationState, QRSmoother


def run_real_video_test(video_path: str = "dataset/production_additional/VID20260910114925.mp4", max_frames: int = 150):
    if not os.path.exists(video_path):
        print(f"[SKIP] Real video not found at: {video_path}")
        return None

    print(f"\n========================================================")
    print(f"RUNNING REAL VIDEO PIPELINE TEST: {video_path}")
    print(f"========================================================")

    cap = cv2.VideoCapture(video_path)
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Video Info: {width}x{height} @ {video_fps:.1f} FPS, total frames: {total_video_frames}")

    # Use existing best.pt weights
    weights_path = "runs/phase9_training/weights/best.pt"
    if not os.path.exists(weights_path):
        weights_path = "yolov8n.pt"

    detector = YoloDetector(weights_path, conf_threshold=0.4)

    qr_detector = NativeQRDetector(min_area=36.0)
    smoother = QRSmoother(history_size=15, confirmation_thresh=3, drop_thresh=10)

    # Position counting line at the vertical center of the frame
    line_y = height // 2
    counter = LineCounter(0, line_y, width, line_y, target_class="box")

    frames_processed = 0
    qr_detected_frames = 0
    confirmed_valid_frames = 0
    total_qrs_decoded = 0
    unique_payloads_found = set()
    total_line_crossings = 0
    track_status_distribution = {}

    start_time = time.time()

    while cap.isOpened() and frames_processed < max_frames:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        # 1. Box detector inference
        annotated_frame, inf_fps, active_tracks = detector.predict(frame)

        # 2. Line counter
        crossings = counter.process_tracks(active_tracks)
        total_line_crossings += len(crossings)

        # 3. QR Detector on unannotated frame
        detected_qrs = qr_detector.detect(frame, bounding_boxes=active_tracks)
        if len(detected_qrs) > 0:
            qr_detected_frames += 1
            for q in detected_qrs:
                p = q.get("payload")
                if p:
                    total_qrs_decoded += 1
                    unique_payloads_found.add(p)

        # 4. Association
        validation_res = validate_qrs(active_tracks, detected_qrs)
        raw_states = validation_res["raw_track_states"]

        # 5. Temporal Smoothing
        smoothed_states = smoother.update(active_tracks, raw_states)

        # Record distribution
        for t_id, st in smoothed_states.items():
            status_val = st["status"].value
            track_status_distribution[status_val] = track_status_distribution.get(status_val, 0) + 1
            if st["status"] == ValidationState.VALID_QR:
                confirmed_valid_frames += 1

        frames_processed += 1
        if frames_processed % 30 == 0:
            print(f"Processed {frames_processed}/{min(max_frames, total_video_frames)} frames... "
                  f"Active tracks: {len(active_tracks)}, QRs seen: {len(detected_qrs)}")

    cap.release()
    elapsed = time.time() - start_time
    fps = frames_processed / elapsed if elapsed > 0 else 0

    print(f"\n--- REAL VIDEO TEST RESULTS ---")
    print(f"Frames processed: {frames_processed}")
    print(f"Processing time: {elapsed:.2f}s ({fps:.1f} FPS)")
    print(f"Frames with QR detected: {qr_detected_frames}/{frames_processed} ({qr_detected_frames/frames_processed*100:.1f}%)")
    print(f"Total QR decodes: {total_qrs_decoded}")
    print(f"Unique QR payloads: {list(unique_payloads_found)}")
    print(f"Total physical box line crossings: {counter.total_count}")
    print(f"Smoothed Track Status Distribution: {track_status_distribution}")
    print(f"========================================================\n")

    return {
        "frames_processed": frames_processed,
        "fps": fps,
        "qr_detected_frames": qr_detected_frames,
        "unique_payloads": list(unique_payloads_found),
        "total_line_crossings": counter.total_count,
        "status_distribution": track_status_distribution
    }


if __name__ == "__main__":
    run_real_video_test()
