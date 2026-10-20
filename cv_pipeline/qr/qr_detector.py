"""
Native OpenCV QR Code Detector Module with Staged Fallbacks and Deduplication.
"""

import logging
import cv2
import numpy as np

logger = logging.getLogger("cv_pipeline.qr_detector")


def is_valid_qr_polygon(pts, roi_w: int, roi_h: int, min_area: float = 36.0) -> bool:
    """
    Validates that detected points form a non-degenerate, finite quadrilateral
    of reasonable size within the ROI bounds.
    """
    if pts is None:
        return False

    try:
        pts = np.asarray(pts)
        if pts.ndim == 3 and pts.shape[0] == 1:
            pts = pts[0]
        if pts.ndim != 2 or pts.shape[0] != 4 or pts.shape[1] != 2:
            return False

        if not np.all(np.isfinite(pts)):
            return False

        # Calculate area using contourArea (handles convex and non-convex quadrilaterals)
        area = cv2.contourArea(pts.astype(np.float32))

        if area < min_area:
            return False

        if roi_w > 0 and roi_h > 0 and area > (roi_w * roi_h):
            return False

        return True
    except Exception as e:
        logger.debug("Polygon validation exception: %s", e)
        return False


class NativeQRDetector:
    """
    Native OpenCV QR detector with staged decoding fallbacks,
    adaptive preprocessing, and duplicate suppression across ROI crops.
    """

    def __init__(self, min_area: float = 36.0):
        self.detector = cv2.QRCodeDetector()
        self.min_area = min_area

    def _decode_crop_patch(self, patch: np.ndarray) -> tuple[str | None, str | None]:
        """
        Applies staged preprocessing fallbacks on an isolated QR patch.
        Returns (payload, fallback_method_used).
        """
        if patch is None or patch.size == 0:
            return None, None

        h, w = patch.shape[:2]
        if h < 8 or w < 8:
            return None, None

        # 1. Direct single-code decode on patch
        payload, _, _ = self.detector.detectAndDecode(patch)
        if payload and payload.strip():
            return payload.strip(), "patch_direct"

        # Convert to grayscale for image processing fallbacks
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if len(patch.shape) == 3 else patch

        # 2. Contrast enhancement via CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)
        payload, _, _ = self.detector.detectAndDecode(enhanced)
        if payload and payload.strip():
            return payload.strip(), "patch_clahe"

        # 3. Adaptive Gaussian Thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        payload, _, _ = self.detector.detectAndDecode(thresh)
        if payload and payload.strip():
            return payload.strip(), "patch_adaptive_thresh"

        # 4. Otsu Binarization
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        payload, _, _ = self.detector.detectAndDecode(otsu)
        if payload and payload.strip():
            return payload.strip(), "patch_otsu"

        # 5. Morphological closing (for dotted/textured QR codes)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed_img = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        payload, _, _ = self.detector.detectAndDecode(closed_img)
        if payload and payload.strip():
            return payload.strip(), "patch_morph_close"

        return None, None

    def _decode_with_preprocessing(self, img: np.ndarray, pts: np.ndarray) -> tuple[str | None, str | None]:
        """
        Decodes a QR code polygon that was located but returned an empty payload.
        First attempts isolated patch extraction with staged preprocessing.
        """
        try:
            pts_2d = pts.reshape(-1, 2).astype(int)
            x_min = max(0, int(np.min(pts_2d[:, 0])))
            y_min = max(0, int(np.min(pts_2d[:, 1])))
            x_max = min(img.shape[1], int(np.max(pts_2d[:, 0])))
            y_max = min(img.shape[0], int(np.max(pts_2d[:, 1])))

            # Add 15% margin around the polygon for finder pattern context
            w = x_max - x_min
            h = y_max - y_min
            pad_x = max(6, int(w * 0.15))
            pad_y = max(6, int(h * 0.15))

            crop_x1 = max(0, x_min - pad_x)
            crop_y1 = max(0, y_min - pad_y)
            crop_x2 = min(img.shape[1], x_max + pad_x)
            crop_y2 = min(img.shape[0], y_max + pad_y)

            patch = img[crop_y1:crop_y2, crop_x1:crop_x2]
            payload, fallback = self._decode_crop_patch(patch)
            if payload:
                return payload, fallback

            # Direct OpenCV decode with float32 polygon
            poly_float = pts.reshape(1, 4, 2).astype(np.float32)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            payload, _ = self.detector.decode(gray, poly_float)
            if payload and payload.strip():
                return payload.strip(), "direct_decode_gray"

        except Exception as e:
            logger.debug("Error during preprocessed decoding: %s", e)

        return None, None

    def detect(self, frame: np.ndarray, bounding_boxes=None) -> list[dict]:
        """
        Detects and decodes QR codes in a frame using OpenCV's native detector.
        If bounding_boxes is provided, it crops the frame to each box's ROI first to improve reliability.
        Returns a list of dictionaries: [{"payload": str or None, "polygon": np.ndarray, "cx": int, "cy": int}]
        """
        raw_candidates = []
        if frame is None or frame.size == 0:
            return []

        try:
            H, W = frame.shape[:2]

            def process_image(img, offset_x=0, offset_y=0):
                roi_h, roi_w = img.shape[:2]
                if roi_h < 10 or roi_w < 10:
                    return

                # 1. Multi-QR detection
                points = None
                decoded_info = None
                try:
                    retval, decoded_info, points, _ = self.detector.detectAndDecodeMulti(img)
                except Exception as e:
                    logger.debug("detectAndDecodeMulti exception: %s", e)

                # 2. Single-QR fallback if multi returned nothing
                if points is None or len(points) == 0:
                    try:
                        single_payload, single_points, _ = self.detector.detectAndDecode(img)
                        if single_points is not None:
                            if len(single_points.shape) == 2:
                                points = [single_points]
                            elif len(single_points.shape) == 3 and single_points.shape[0] == 1:
                                points = [single_points[0]]
                            else:
                                points = single_points
                            decoded_info = [single_payload] if single_payload else [""]
                    except Exception as e:
                        logger.debug("Single-QR fallback exception: %s", e)

                if points is not None:
                    for i in range(len(points)):
                        poly = points[i]

                        if not is_valid_qr_polygon(poly, roi_w, roi_h, min_area=self.min_area):
                            logger.debug("Discarded invalid QR polygon at offset (%d, %d)", offset_x, offset_y)
                            continue

                        payload = None
                        if decoded_info is not None and i < len(decoded_info):
                            raw_p = decoded_info[i]
                            if raw_p and str(raw_p).strip():
                                payload = str(raw_p).strip()

                        # 3. If polygon was detected but payload was empty, trigger staged fallback
                        if not payload:
                            recovered, fallback_name = self._decode_with_preprocessing(img, poly)
                            if recovered:
                                payload = recovered
                                logger.debug("Recovered QR payload via %s: %s", fallback_name, payload)

                        poly_int = poly.reshape(-1, 2).astype(int)
                        poly_int[:, 0] += offset_x
                        poly_int[:, 1] += offset_y

                        cx = int(np.mean(poly_int[:, 0]))
                        cy = int(np.mean(poly_int[:, 1]))

                        raw_candidates.append({
                            "payload": payload,
                            "polygon": poly_int,
                            "cx": cx,
                            "cy": cy
                        })

            # Process bounding boxes if provided
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

                    # Padding to ensure QR near edge is captured
                    px1 = max(0, x1 - 25)
                    py1 = max(0, y1 - 25)
                    px2 = min(W, x2 + 25)
                    py2 = min(H, y2 + 25)

                    roi = frame[py1:py2, px1:px2]
                    process_image(roi, offset_x=px1, offset_y=py1)
            else:
                process_image(frame)

        except Exception as e:
            logger.warning("Warning during QR detection: %s", e)

        # 4. Deduplicate candidates across overlapping crops
        deduped_candidates = []
        for cand in raw_candidates:
            c_cx = cand["cx"]
            c_cy = cand["cy"]
            matched_idx = -1

            for idx, existing in enumerate(deduped_candidates):
                dist = ((existing["cx"] - c_cx) ** 2 + (existing["cy"] - c_cy) ** 2) ** 0.5
                if dist < 25.0:
                    matched_idx = idx
                    break

            if matched_idx >= 0:
                # Merge duplicate: prefer candidate with decoded payload
                existing = deduped_candidates[matched_idx]
                if existing.get("payload") is None and cand.get("payload") is not None:
                    deduped_candidates[matched_idx] = cand
            else:
                deduped_candidates.append(cand)

        return deduped_candidates
