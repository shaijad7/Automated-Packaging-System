import cv2
import numpy as np

def is_valid_qr_polygon(pts, roi_w, roi_h):
    if pts is None or len(pts) != 4:
        return False
    
    # Check for degenerate shape (collinear points, very small area)
    # Using surveyor's formula for polygon area
    x = pts[:, 0]
    y = pts[:, 1]
    area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    
    if area < 100: # Too small to be a real QR code in our resolution
        return False
        
    if area > (roi_w * roi_h): # Unreasonably large
        return False
        
    # Check if coords are finite and within reasonable bounds
    if not np.all(np.isfinite(pts)):
        return False
        
    return True

class NativeQRDetector:
    def __init__(self):
        self.detector = cv2.QRCodeDetector()
        
    def _decode_with_preprocessing(self, img, pts):
        # 1. Original
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Isolate this specific polygon for the decode API
        single_pts = np.expand_dims(pts, axis=0)
        
        # 2. Contrast stretching
        p2, p98 = np.percentile(gray, (2, 98))
        if p98 > p2:
            stretched = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
            payload, _ = self.detector.decode(stretched, single_pts)
            if payload: return payload

        # 3. Morphological close (for dotted QRs)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed_img = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        payload, _ = self.detector.decode(closed_img, single_pts)
        if payload: return payload
        
        # 4. Adaptive thresholding
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        payload, _ = self.detector.decode(thresh, single_pts)
        if payload: return payload
        
        return None

    def detect(self, frame, bounding_boxes=None):
        """
        Detects and decodes QR codes in a frame using OpenCV's native detector.
        If bounding_boxes is provided, it crops the frame to each box's ROI first to improve reliability.
        Returns a list of dictionaries: [{"payload": str, "polygon": [...], "cx": int, "cy": int}]
        """
        results = []
        try:
            H, W = frame.shape[:2]

            def process_image(img, offset_x=0, offset_y=0):
                roi_h, roi_w = img.shape[:2]
                if roi_h < 10 or roi_w < 10:
                    return

                retval, decoded_info, points, _ = self.detector.detectAndDecodeMulti(img)
                
                if points is None or len(points) == 0:
                    single_payload, single_points, _ = self.detector.detectAndDecode(img)
                    if single_points is not None:
                        if len(single_points.shape) == 2:
                            points = [single_points]
                        else:
                            points = single_points
                        decoded_info = [single_payload]
                
                if points is not None:
                    for i in range(len(points)):
                        poly = points[i]
                        
                        if not is_valid_qr_polygon(poly, roi_w, roi_h):
                            continue
                            
                        payload = None
                        if decoded_info is not None and i < len(decoded_info):
                            payload = decoded_info[i]
                            
                        if not payload:
                            try:
                                payload = self._decode_with_preprocessing(img, poly)
                            except Exception:
                                pass
                                
                        poly = poly.astype(int)
                        poly[:, 0] += offset_x
                        poly[:, 1] += offset_y
                        
                        cx = int(np.mean(poly[:, 0]))
                        cy = int(np.mean(poly[:, 1]))
                        
                        results.append({
                            "payload": payload,
                            "polygon": poly,
                            "cx": cx,
                            "cy": cy
                        })

            if bounding_boxes and len(bounding_boxes) > 0:
                for bbox in bounding_boxes:
                    if len(bbox) >= 7:
                        x1, y1, x2, y2 = bbox[3:7]
                    elif len(bbox) == 4:
                        x1, y1, x2, y2 = bbox
                    else:
                        continue
                        
                    x1 = max(0, int(x1))
                    y1 = max(0, int(y1))
                    x2 = min(W, int(x2))
                    y2 = min(H, int(y2))
                    
                    if x2 <= x1 or y2 <= y1:
                        continue
                        
                    # Add a small padding to ROI to ensure QR isn't cut off
                    px1 = max(0, x1 - 20)
                    py1 = max(0, y1 - 20)
                    px2 = min(W, x2 + 20)
                    py2 = min(H, y2 + 20)
                    
                    roi = frame[py1:py2, px1:px2]
                    process_image(roi, offset_x=px1, offset_y=py1)
            else:
                process_image(frame)
                
        except Exception as e:
            print(f"[QRDetector] Warning during detection: {e}")
            
        return results
