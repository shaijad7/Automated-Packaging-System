# USB Webcam FOV / Zoom Test

## 1. Camera Configuration
- **Camera Index**: 1
- **Backend**: cv2.CAP_DSHOW
- **Resolution**: 1920x1080
- **Actual FPS**: ~29.6

## 2. Available Camera Controls
Using OpenCV's `CAP_PROP` property system, the camera driver was queried for standard hardware capabilities. The results are:
- **Zoom**: Unsupported/Fixed
- **Pan**: Unsupported/Fixed
- **Tilt**: Unsupported/Fixed
- **Autofocus**: Unsupported/Fixed
- **Focus**: Unsupported/Fixed
- **Exposure**: Supported (Current value: -5.0)

## 3. Actual FOV Behavior
The camera is returning the raw 1920x1080 stream. Because standard hardware zoom and pan/tilt controls are unsupported, OpenCV is receiving the full default field of view provided by the lens and driver combination. There is no OpenCV-level digital crop being applied.

## 4. Zoom Test
**Result:** N/A.
The `cv2.CAP_PROP_ZOOM` property is entirely unsupported by this hardware/driver in OpenCV. It is not possible to adjust the zoom level programmatically via standard OpenCV commands to achieve a wider field of view.

## 5. Auto-Framing Test
Because there are no hardware PTZ (Pan/Tilt/Zoom) capabilities exposed, if dynamic auto-framing is occurring (e.g., following your face when you move), it is being applied purely at the proprietary driver level or OS level (such as Windows Studio Effects/AI auto-framing). OpenCV has no API to disable driver-level auto-framing. If the view is consistently narrow regardless of who is in the frame, there is no auto-framing active.

## 6. Root Cause of Narrow View
The USB webcam is a **fixed-lens camera**. It does not have optical zoom, and its physical lens angle (Field of View) is simply too narrow for the distance at which it is currently mounted. Software cannot "zoom out" wider than the physical limits of the lens.

## 7. Recommended Production Setup
**C. Camera has fixed/narrow FOV; software cannot meaningfully zoom out.**

For a reliable production inventory system (Camera → YOLO → ByteTrack → LineCounter → QR → SKU), the camera must be strictly fixed and stable. Automatic zooming or auto-framing destroys the static coordinate geometry necessary for `LineCounter` and breaks `ByteTrack`'s velocity estimations due to background shifting.

## 8. Whether Camera Replacement/Wider FOV Is Needed
**Yes, hardware adjustments are required.**
To capture the necessary width of the conveyor belt, you must do one of the following:
1. **Physically move the camera higher** (increase the distance between the camera and the conveyor belt).
2. **Replace the camera** with a "Wide-Angle" USB webcam (e.g., 90° to 120° FOV) if moving the current camera higher is not physically possible in your setup. 

Do not attempt to use software or AI auto-framing to fix this; a static, wide physical view is mandatory for the CV pipeline to function correctly.
