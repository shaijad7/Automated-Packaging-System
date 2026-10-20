import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from detector import YoloDetector
from camera import CameraManager


class TestModelAndCameraHonesty:
    """Test suite ensuring honest error handling for missing models, empty detections, and camera sources."""

    def test_missing_model_honesty(self):
        """When a model file does not exist, YoloDetector reports is_available=False and handles predictions safely."""
        detector = YoloDetector("non_existent_model_path_9999.pt", 0.5)
        assert detector.is_available is False
        assert detector.model is None

        blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_out, fps, track_ids = detector.predict(blank_frame)

        assert np.array_equal(frame_out, blank_frame)
        assert fps == 0.0
        assert track_ids == []

    def test_trained_model_box_class(self):
        """The trained model at models/best.pt must load with class 0: 'box'."""
        detector = YoloDetector("models/best.pt", 0.5)
        assert detector.is_available is True
        assert detector.model is not None
        assert detector.model.names[0] == "box"

        # Blank frame prediction should yield no false positive tracks
        blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_out, fps, track_ids = detector.predict(blank_frame)
        assert frame_out.shape == blank_frame.shape
        assert isinstance(fps, float)
        assert track_ids == []

    @patch("cv2.VideoCapture")
    def test_camera_manager_failed_open(self, mock_videocapture):
        """When the camera device fails to open, CameraManager returns False and does not pretend to stream."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_videocapture.return_value = mock_cap

        cam = CameraManager(camera_source=99)
        success = cam._init_camera()
        assert success is False

    def test_camera_manager_thread_control(self):
        """CameraManager cleanly sets and clears stop_event."""
        cam = CameraManager(camera_source=99)
        assert not cam.stop_event.is_set()
        cam.stop()
        assert cam.stop_event.is_set()
