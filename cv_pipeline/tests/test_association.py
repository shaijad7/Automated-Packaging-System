import pytest
import numpy as np
from qr.association import validate_qrs, ValidationState


class TestQRAssociation:
    """Test suite for Phase 3: QR-to-Object Geometric Association."""

    def test_no_qr_found_for_tracked_box(self):
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = []

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert 1 in states
        assert states[1]["status"] == ValidationState.NO_QR
        assert states[1]["payload"] is None
        assert states[1]["polygon"] is None
        assert len(result["unmatched_qrs"]) == 0
        assert len(result["ambiguous_qrs"]) == 0

    def test_one_valid_qr_inside_one_box(self):
        poly = np.array([[90, 90], [110, 90], [110, 110], [90, 110]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [{"payload": "INV|ADP-001", "cx": 100, "cy": 100, "polygon": poly}]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.VALID_QR
        assert states[1]["payload"] == "INV|ADP-001"
        assert np.array_equal(states[1]["polygon"], poly)
        assert len(result["unmatched_qrs"]) == 0
        assert len(result["ambiguous_qrs"]) == 0

    def test_unreadable_qr_inside_box(self):
        poly = np.array([[90, 90], [110, 90], [110, 110], [90, 110]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [{"payload": None, "cx": 100, "cy": 100, "polygon": poly}]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.UNREADABLE_QR
        assert states[1]["payload"] is None
        assert np.array_equal(states[1]["polygon"], poly)
        assert len(result["unmatched_qrs"]) == 0

    def test_invalid_payload_inside_box(self):
        poly = np.array([[90, 90], [110, 90], [110, 110], [90, 110]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [{"payload": "NOT_AN_INV_QR", "cx": 100, "cy": 100, "polygon": poly}]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.INVALID_QR
        assert states[1]["payload"] == "NOT_AN_INV_QR"
        assert len(result["unmatched_qrs"]) == 0

    def test_qr_outside_every_box(self):
        poly = np.array([[500, 500], [520, 500], [520, 520], [500, 520]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [{"payload": "INV|BOX-99", "cx": 510, "cy": 510, "polygon": poly}]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.NO_QR
        assert len(result["unmatched_qrs"]) == 1
        assert result["unmatched_qrs"][0]["payload"] == "INV|BOX-99"

    def test_qr_inside_multiple_overlapping_boxes(self):
        """When 1 QR is inside the intersection of Box 1 and Box 2, both boxes and the QR are ambiguous."""
        poly = np.array([[120, 120], [140, 120], [140, 140], [120, 140]])
        # Track 1: [50, 50, 150, 150] -> contains (130, 130)
        # Track 2: [120, 120, 220, 220] -> contains (130, 130)
        active_tracks = [
            (1, 100, 100, 50, 50, 150, 150),
            (2, 170, 170, 120, 120, 220, 220),
        ]
        detected_qrs = [{"payload": "INV|SHARED", "cx": 130, "cy": 130, "polygon": poly}]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        # Neither box should falsely claim ownership
        assert states[1]["status"] == ValidationState.AMBIGUOUS
        assert states[2]["status"] == ValidationState.AMBIGUOUS
        assert len(result["ambiguous_qrs"]) == 1
        assert result["ambiguous_qrs"][0]["payload"] == "INV|SHARED"

    def test_multiple_distinct_qrs_inside_one_box(self):
        """Never silently pick the last QR candidate when 2 distinct QRs are in 1 box."""
        poly1 = np.array([[60, 60], [80, 60], [80, 80], [60, 80]])
        poly2 = np.array([[110, 110], [130, 110], [130, 130], [110, 130]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [
            {"payload": "INV|CANDIDATE-A", "cx": 70, "cy": 70, "polygon": poly1},
            {"payload": "INV|CANDIDATE-B", "cx": 120, "cy": 120, "polygon": poly2},
        ]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.AMBIGUOUS
        assert states[1]["payload"] is None
        assert len(result["ambiguous_qrs"]) == 2

    def test_duplicate_identical_qrs_inside_box_are_deduplicated(self):
        """Duplicate detections of the exact same physical QR at the same position are handled safely."""
        poly1 = np.array([[90, 90], [110, 90], [110, 110], [90, 110]])
        poly2 = np.array([[91, 91], [111, 91], [111, 111], [91, 111]])
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        detected_qrs = [
            {"payload": "INV|SAME-SKU", "cx": 100, "cy": 100, "polygon": poly1},
            {"payload": "INV|SAME-SKU", "cx": 101, "cy": 101, "polygon": poly2},
        ]

        result = validate_qrs(active_tracks, detected_qrs)
        states = result["raw_track_states"]

        assert states[1]["status"] == ValidationState.VALID_QR
        assert states[1]["payload"] == "INV|SAME-SKU"
        assert len(result["ambiguous_qrs"]) == 0

    def test_backward_compatibility_alias(self):
        """Result dictionary must provide both 'raw_track_states' and 'track_states'."""
        active_tracks = [(1, 100, 100, 50, 50, 150, 150)]
        result = validate_qrs(active_tracks, [])

        assert "raw_track_states" in result
        assert "track_states" in result
        assert result["raw_track_states"] is result["track_states"]
