# USB Webcam Debug Report

## 1. Test Process Status
The initial camera test process was running normally in the background. It was successfully capturing frames continuously, but the OpenCV GUI window was completely invisible to the user desktop. The process has now been safely terminated.

## 2. USB Webcam Index
The USB webcam is confirmed at Index `1`.

## 3. Camera Open Result
SUCCESS: The camera successfully opens on Index 1 using the `cv2.CAP_DSHOW` (DirectShow) backend.

## 4. Real Frame Read Result
SUCCESS: The camera produces valid, real frames without errors.

## 5. Frame Diagnostics
- **Shape**: 1280x720 (720p HD)
- **Min Pixel**: 17.0
- **Max Pixel**: 254.0
- **Mean Pixel**: ~208.34
*(This confirms the camera is not returning a blank/black screen.)*

## 6. OpenCV GUI Support
- `opencv-python` version 5.0.0.93 is installed.
- `opencv-python-headless` is NOT installed.
- OpenCV's `getBuildInformation()` confirms `GUI: WIN32UI` and `Win32 UI: YES`.
- The GUI system is fully compiled into the current OpenCV package.

## 7. Windows Backend Results
The `cv2.CAP_DSHOW` backend successfully accesses the hardware and retrieves frames. 

## 8. Camera Ownership
The camera is correctly released. There are no dangling python processes holding the camera after tests complete.

## 9. Window Display Result
FAILED: `cv2.namedWindow()` and `cv2.imshow()` execute without throwing any Python or C++ exceptions. However, the window never renders on the user's visible desktop screen. This happens because the agent framework runs in an isolated Windows session or background service context (e.g., Session 0), meaning all child processes (like the test script) have their GUI elements rendered in a hidden desktop session.

## 10. Camera Release/Reacquisition
SUCCESS: The camera correctly releases its handle upon process exit and can be immediately reacquired by a new script.

## 11. Root Cause
The camera hardware, drivers, and OpenCV installation are fully functional. The root cause of the missing window is **Windows Session Isolation**; the background agent process does not have permission to draw GUI windows onto the interactive user's desktop session.

## 12. Required Fix
To see the native window, the test script must be executed directly by the user from their own interactive terminal (e.g., by opening PowerShell locally and running `python cv_pipeline/test_camera.py`), rather than being executed through the background AI agent environment. Alternatively, the video feed must be routed to a frontend web app or saved as an image artifact.

FAIL — native window/camera requires further fix
