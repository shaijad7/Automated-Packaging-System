import pytest
from unittest.mock import MagicMock
import numpy as np
from qr.qr_detector import NativeQRDetector, is_valid_qr_polygon


class TestQRDetectorUnit:
    """Test suite for Phase 5: NativeQRDetector improvements, validation, and fallback mechanisms."""

    def test_polygon_validation_valid_and_invalid_shapes(self):
        roi_w, roi_h = 200, 200

        # 1. Valid quadrilateral
        valid_quad = np.array([[20, 20], [80, 20], [80, 80], [20, 80]])
        assert is_valid_qr_polygon(valid_quad, roi_w, roi_h) is True

        # 2. Valid with shape (1, 4, 2)
        valid_quad_3d = valid_quad.reshape(1, 4, 2)
        assert is_valid_qr_polygon(valid_quad_3d, roi_w, roi_h) is True

        # 3. None or wrong number of points
        assert is_valid_qr_polygon(None, roi_w, roi_h) is False
        assert is_valid_qr_polygon(np.array([[10, 10], [20, 20]]), roi_w, roi_h) is False
        assert is_valid_qr_polygon(np.array([[10, 10], [20, 20], [30, 30], [40, 40], [50, 50]]), roi_w, roi_h) is False

        # 4. Degenerate collinear points (zero area)
        collinear = np.array([[10, 10], [20, 20], [30, 30], [40, 40]])
        assert is_valid_qr_polygon(collinear, roi_w, roi_h) is False

        # 5. Extremely tiny area (< 36)
        tiny = np.array([[0, 0], [4, 0], [4, 4], [0, 4]])  # area 16
        assert is_valid_qr_polygon(tiny, roi_w, roi_h, min_area=36) is False

        # 6. Area exceeding ROI
        huge = np.array([[0, 0], [300, 0], [300, 300], [0, 300]])
        assert is_valid_qr_polygon(huge, roi_w, roi_h) is False

        # 7. Non-finite values (NaN / Inf)
        with_nan = np.array([[0, 0], [np.nan, 20], [20, 20], [0, 20]])
        assert is_valid_qr_polygon(with_nan, roi_w, roi_h) is False

        with_inf = np.array([[0, 0], [np.inf, 20], [20, 20], [0, 20]])
        assert is_valid_qr_polygon(with_inf, roi_w, roi_h) is False

    def test_single_code_fallback_when_multi_returns_empty(self):
        detector = NativeQRDetector()
        mock_cv_detector = MagicMock()

        # Multi returns points=None, single returns valid QR
        poly = np.array([[30, 30], [80, 30], [80, 80], [30, 80]], dtype=np.float32)
        mock_cv_detector.detectAndDecodeMulti.return_value = (False, None, None, None)
        mock_cv_detector.detectAndDecode.return_value = ("INV|RECOVERED", poly, None)

        detector.detector = mock_cv_detector

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        results = detector.detect(frame)

        assert len(results) == 1
        assert results[0]["payload"] == "INV|RECOVERED"
        assert results[0]["cx"] == 55
        assert results[0]["cy"] == 55

    def test_crop_roi_offset_calculation(self):
        detector = NativeQRDetector()
        mock_cv_detector = MagicMock()

        # Local ROI points: [10, 10] to [40, 40]
        local_poly = np.array([[10, 10], [40, 10], [40, 40], [10, 40]], dtype=np.float32)
        mock_cv_detector.detectAndDecodeMulti.return_value = (True, ["INV|ROI-TEST"], [local_poly], None)
        detector.detector = mock_cv_detector

        frame = np.zeros((500, 500, 3), dtype=np.uint8)
        # Bbox from (100, 100) to (200, 200). Padding is 25, so crop starts at px1=75, py1=75
        bbox = (1, 150, 150, 100, 100, 200, 200)

        results = detector.detect(frame, bounding_boxes=[bbox])

        assert len(results) == 1
        # Offset should be px1 = 75, py1 = 75
        expected_poly_x = local_poly[:, 0] + 75
        expected_poly_y = local_poly[:, 1] + 75
        res_poly = results[0]["polygon"]

        assert np.allclose(res_poly[:, 0], expected_poly_x)
        assert np.allclose(res_poly[:, 1], expected_poly_y)
        assert results[0]["cx"] == int(np.mean(expected_poly_x))
        assert results[0]["cy"] == int(np.mean(expected_poly_y))

    def test_duplicate_suppression_across_overlapping_crops(self):
        detector = NativeQRDetector()
        mock_cv_detector = MagicMock()

        # Both ROIs detect the same QR at global position approx (150, 150)
        # ROI 1: offset px1=50, py1=50 -> local [90, 90] to [110, 110] -> global center (150, 150)
        # ROI 2: offset px1=100, py1=100 -> local [40, 40] to [60, 60] -> global center (150, 150)
        def mock_multi(img):
            h, w = img.shape[:2]
            # Return identical global center QR for any ROI
            poly = np.array([[40, 40], [60, 40], [60, 60], [40, 60]], dtype=np.float32)
            return True, ["INV|DEDUP"], [poly], None

        mock_cv_detector.detectAndDecodeMulti.side_effect = mock_multi
        detector.detector = mock_cv_detector

        frame = np.zeros((400, 400, 3), dtype=np.uint8)
        # Two overlapping boxes
        box1 = (1, 150, 150, 100, 100, 200, 200)
        box2 = (2, 160, 160, 110, 110, 210, 210)

        results = detector.detect(frame, bounding_boxes=[box1, box2])

        # Even though both bounding boxes produced detections, they must be deduplicated
        assert len(results) == 1
        assert results[0]["payload"] == "INV|DEDUP"
