import cv2

def discover_cameras(max_tests=5):
    """
    Probes camera indexes from 0 to max_tests-1 and prints their basic capabilities.
    """
    print(f"Probing OpenCV camera indexes 0 to {max_tests-1}...\n")
    available_cameras = []
    
    for i in range(max_tests):
        cap = cv2.VideoCapture(i, cv2.CAP_ANY)
        if cap is None or not cap.isOpened():
            print(f"Index {i}: No camera found or failed to open.")
            if cap is not None:
                cap.release()
            continue
            
        # Successfully opened
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        print(f"Index {i}: SUCCESS")
        print(f"  -> Default Resolution: {int(width)}x{int(height)}")
        print(f"  -> Default FPS: {fps}")
        
        # Test grabbing a frame
        ret, frame = cap.read()
        if ret and frame is not None:
            print("  -> Frame capture test: SUCCESS")
        else:
            print("  -> Frame capture test: FAILED (Cannot read frame)")
            
        available_cameras.append(i)
        cap.release()
        print("-" * 30)
        
    print(f"\nDiscovery complete. Valid camera indexes: {available_cameras}")

if __name__ == "__main__":
    discover_cameras()
