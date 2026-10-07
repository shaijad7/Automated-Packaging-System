import time
from camera import CameraManager

def main():
    print("Initializing CameraManager for minimal verification...")
    # Initialize CameraManager using source 0
    cam_manager = CameraManager(camera_source=0)
    
    print("\n--- Starting Camera ---")
    cam_manager.start()
    
    # Wait for the camera loop to initialize and attempt capture
    time.sleep(3.0)
    
    frame = cam_manager.get_latest_frame()
    if frame is not None:
        print(f"\nSuccessfully captured frame of shape: {frame.shape}")
    else:
        print("\nFailed to capture frame from CameraManager.")
        
    print("\n--- Stopping Camera ---")
    cam_manager.stop()
    print("Camera stopped successfully.")

if __name__ == "__main__":
    main()
