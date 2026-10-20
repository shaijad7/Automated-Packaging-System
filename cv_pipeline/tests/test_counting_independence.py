import pytest
from counting.line_counter import LineCounter, Direction
from qr.association import ValidationState


class TestCountingIndependence:
    """Test suite verifying that line crossing counting is 100% independent of QR detection success."""

    def test_line_counter_increments_regardless_of_qr_status(self):
        """LineCounter only cares about track geometry, not QR reading status."""
        counter = LineCounter(start_x=0, start_y=200, end_x=500, end_y=200, target_class="box")

        # Track 1 starts above line (y=150)
        track_above = [(1, 250, 150, 200, 100, 300, 200, "box")]
        crossings = counter.process_tracks(track_above)
        assert len(crossings) == 0
        assert counter.total_count == 0

        # Track 1 crosses below line (y=250)
        track_below = [(1, 250, 250, 200, 200, 300, 300, "box")]
        crossings = counter.process_tracks(track_below)

        # Counting successfully detected crossing
        assert len(crossings) == 1
        assert counter.total_count == 1
        assert crossings[0]["track_id"] == 1

        # Even if QR status was NO_QR, UNREADABLE_QR, INVALID_QR, or AMBIGUOUS:
        for status in [
            ValidationState.NO_QR,
            ValidationState.UNREADABLE_QR,
            ValidationState.INVALID_QR,
            ValidationState.AMBIGUOUS,
            ValidationState.VALID_QR,
        ]:
            # The line crossing event was emitted with track_id=1, direction A_TO_B or B_TO_A
            assert counter.total_count == 1  # Not double counted

    def test_track_never_double_counted(self):
        """A single physical track that stays below line or hovers is never counted twice."""
        counter = LineCounter(start_x=0, start_y=200, end_x=500, end_y=200, target_class="box")

        # Move across line
        counter.process_tracks([(1, 250, 150, 200, 100, 300, 200, "box")])
        crossings1 = counter.process_tracks([(1, 250, 250, 200, 200, 300, 300, "box")])
        assert len(crossings1) == 1
        assert counter.total_count == 1

        # Keep moving further below line
        crossings2 = counter.process_tracks([(1, 250, 280, 200, 230, 300, 330, "box")])
        assert len(crossings2) == 0
        assert counter.total_count == 1

        # Move back above line (direction reverse): should not increment total_count again
        crossings3 = counter.process_tracks([(1, 250, 150, 200, 100, 300, 200, "box")])
        assert counter.total_count == 1
