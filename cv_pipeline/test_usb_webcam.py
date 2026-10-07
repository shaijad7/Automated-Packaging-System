import cv2
import time
import sys

def main():
    # Index 1 was confirmed as the USB webcam in prior diagnostics
    camera_index = 1
    
    print(f"Opening USB webcam at index {camera_index}...")
    # Using CAP_DSHOW as verified in the diagnostic report
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print(f"Error: Could not open camera at index {camera_index}.")
        sys.exit(1)
        
    # Request 1080p resolution and 30 FPS
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    # Read actual values
    actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    
    print(f"Actual Resolution: {int(actual_width)}x{int(actual_height)}")
    print("Press 'q' in the video window to exit.")
    
    frames = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Error: Failed to read frame from camera.")
                break
                
            frames += 1
            elapsed = time.time() - start_time
            fps = frames / elapsed if elapsed > 0 else 0.0
            
            # Display text on the frame
            cv2.putText(frame, f"Resolution: {int(actual_width)}x{int(actual_height)}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, "Press 'q' to exit", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
            # Open native window
            cv2.imshow("SMART INVENTORY - CAMERA TEST", frame)
            
            # Wait for 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\nUser requested exit ('q' pressed).")
                break
                
    except KeyboardInterrupt:
        print("\nExit requested via Ctrl+C.")
    finally:
        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        print("Camera released cleanly and windows destroyed.")
        
    # Reacquisition Test
    print("\nStarting Reacquisition Test...")
    time.sleep(1) # Brief pause to let OS completely free the handle
    cap_retest = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if cap_retest.isOpened():
        ret, _ = cap_retest.read()
        if ret:
            print(f"Reacquisition PASS: Camera {camera_index} successfully reopened and read a frame.")
        else:
            print(f"Reacquisition FAIL: Camera {camera_index} opened, but failed to read a frame.")
        cap_retest.release()
    else:
        print(f"Reacquisition FAIL: Could not reopen camera {camera_index}.")

if __name__ == "__main__":
    main()
