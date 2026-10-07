import cv2
import time
import sys
from ultralytics import YOLO

# Import the existing production CameraManager
from camera import CameraManager

def main():
    print("Loading Phase 9 YOLOv8 model (best.pt)...")
    try:
        model = YOLO(r"c:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\runs\phase9_training\weights\best.pt")
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Failed to load model: {e}")
        sys.exit(1)

    # Initialize CameraManager using configured camera source from settings (.env)
    print("Initializing CameraManager on configured camera source...")
    cam_manager = CameraManager()
    cam_manager.start()

    print("\n" + "="*50)
    print("Starting YOLO Evaluation Test")
    print("Press 'q' in the video window to exit.")
    print("="*50 + "\n")

    frames = 0
    start_time = time.time()
    
    last_inference_time = 0
    inference_fps = 0.0

    try:
        while True:
            # Block until a frame is available from CameraManager
            frame = cam_manager.get_latest_frame()
            if frame is None:
                continue

            # FPS Calculation (Camera Feed)
            frames += 1
            elapsed = time.time() - start_time
            camera_fps = frames / elapsed if elapsed > 0 else 0.0
            
            h, w = frame.shape[:2]

            # Run YOLO Inference
            inf_start = time.time()
            results = model.predict(frame, conf=0.5, verbose=False)
            inf_time = time.time() - inf_start
            
            # Simple moving average for inference FPS
            curr_inf_fps = 1.0 / inf_time if inf_time > 0 else 0.0
            inference_fps = 0.9 * inference_fps + 0.1 * curr_inf_fps

            # Draw Detections
            for box in results[0].boxes:
                # We expect only class 0 (box)
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                
                if cls_id == 0:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Draw bounding box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # Draw label and confidence
                    label = f"box: {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Draw Stats Overlay
            cv2.putText(frame, f"Resolution: {w}x{h}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Camera FPS: {camera_fps:.1f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Inference FPS: {inference_fps:.1f}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, "Press 'q' to exit", (10, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Show Native Window
            cv2.imshow("SMART INVENTORY - YOLO EVALUATION", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Exit requested by user.")
                break

    except KeyboardInterrupt:
        print("\nExit requested via Ctrl+C.")
    finally:
        cam_manager.stop()
        cv2.destroyAllWindows()
        print("\nEvaluation successfully closed.")

if __name__ == "__main__":
    main()
