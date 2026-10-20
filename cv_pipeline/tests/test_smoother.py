import pytest
import numpy as np
from qr.association import QRSmoother, ValidationState


class TestQRSmoother:
    """Test suite for Phase 2: QRSmoother temporal confirmation and stabilization."""

    @pytest.fixture
    def smoother(self):
        return QRSmoother(history_size=10, confirmation_thresh=3, drop_thresh=5)

    def test_confirmation_requires_exact_threshold_count(self, smoother):
        """With confirmation_thresh=3, 1 and 2 observations must NOT confirm."""
        track = (1, 100, 100, 50, 50, 150, 150)
        active_tracks = [track]

        # Observation 1
        obs1 = {1: {"status": ValidationState.VALID_QR, "payload": "INV|BOX-1", "polygon": np.zeros((4, 2))}}
        res1 = smoother.update(active_tracks, obs1)
        assert res1[1]["status"] == ValidationState.NO_QR
        assert res1[1]["payload"] is None

        # Observation 2
        obs2 = {1: {"status": ValidationState.VALID_QR, "payload": "INV|BOX-1", "polygon": np.zeros((4, 2))}}
        res2 = smoother.update(active_tracks, obs2)
        assert res2[1]["status"] == ValidationState.NO_QR
        assert res2[1]["payload"] is None

        # Observation 3 -> exactly 3 consecutive consistent observations -> CONFIRMED!
        obs3 = {1: {"status": ValidationState.VALID_QR, "payload": "INV|BOX-1", "polygon": np.zeros((4, 2))}}
        res3 = smoother.update(active_tracks, obs3)
        assert res3[1]["status"] == ValidationState.VALID_QR
        assert res3[1]["payload"] == "INV|BOX-1"

    def test_inconsistent_payloads_do_not_confirm(self, smoother):
        """Alternating observations (A, B, A) must not achieve consecutive confirmation."""
        track = (1, 100, 100, 50, 50, 150, 150)
        active_tracks = [track]

        # Frame 1: INV|A
        res1 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})
        assert res1[1]["status"] == ValidationState.NO_QR

        # Frame 2: INV|B
        res2 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|B", "polygon": None}})
        assert res2[1]["status"] == ValidationState.NO_QR

        # Frame 3: INV|A
        res3 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})
        # Not consecutive (only 1 consecutive of A)
        assert res3[1]["status"] == ValidationState.NO_QR

    def test_intermittent_miss_preserves_confirmed_state(self, smoother):
        """Once confirmed, transient detection gaps (UNREADABLE or NO_QR) must be tolerated within drop_thresh."""
        track = (1, 100, 100, 50, 50, 150, 150)
        active_tracks = [track]

        # Confirm INV|A with 3 frames
        for _ in range(3):
            smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})

        assert smoother.confirmed_states[1]["status"] == ValidationState.VALID_QR

        # Frame 4: Temporary NO_QR miss (miss count = 1 <= drop_thresh=5)
        res4 = smoother.update(active_tracks, {1: {"status": ValidationState.NO_QR, "payload": None, "polygon": None}})
        assert res4[1]["status"] == ValidationState.VALID_QR
        assert res4[1]["payload"] == "INV|A"

        # Frame 5: Temporary UNREADABLE_QR miss (miss count = 2 <= drop_thresh=5)
        res5 = smoother.update(active_tracks, {1: {"status": ValidationState.UNREADABLE_QR, "payload": None, "polygon": None}})
        assert res5[1]["status"] == ValidationState.VALID_QR
        assert res5[1]["payload"] == "INV|A"

        # Frame 6: Re-detected INV|A -> resets missed_counts to 0
        res6 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})
        assert res6[1]["status"] == ValidationState.VALID_QR
        assert smoother.missed_counts[1] == 0

    def test_state_expiration_after_sustained_misses(self, smoother):
        """After drop_thresh consecutive misses, the confirmed state must expire."""
        track = (1, 100, 100, 50, 50, 150, 150)
        active_tracks = [track]

        # Confirm INV|A (3 frames)
        for _ in range(3):
            smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})

        # Send drop_thresh (5) consecutive NO_QR misses
        for i in range(5):
            res = smoother.update(active_tracks, {1: {"status": ValidationState.NO_QR, "payload": None, "polygon": None}})
            assert res[1]["status"] == ValidationState.VALID_QR, f"Miss {i+1} should still be retained"

        # Miss 6 (> drop_thresh=5) -> EXPIRES to NO_QR
        res_exp = smoother.update(active_tracks, {1: {"status": ValidationState.NO_QR, "payload": None, "polygon": None}})
        assert res_exp[1]["status"] == ValidationState.NO_QR
        assert res_exp[1]["payload"] is None

    def test_payload_switch_requires_consecutive_confirmation(self, smoother):
        """When payload changes from INV|A to INV|B, INV|B must achieve confirmation_thresh consecutive frames."""
        track = (1, 100, 100, 50, 50, 150, 150)
        active_tracks = [track]

        # Confirm INV|A
        for _ in range(3):
            smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})

        # Now raw observations switch to INV|B
        # Frame 1 of B -> retained A
        res1 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|B", "polygon": None}})
        assert res1[1]["status"] == ValidationState.VALID_QR
        assert res1[1]["payload"] == "INV|A"

        # Frame 2 of B -> retained A
        res2 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|B", "polygon": None}})
        assert res2[1]["status"] == ValidationState.VALID_QR
        assert res2[1]["payload"] == "INV|A"

        # Frame 3 of B -> 3 consecutive consistent B observations -> SWITCHES to B!
        res3 = smoother.update(active_tracks, {1: {"status": ValidationState.VALID_QR, "payload": "INV|B", "polygon": None}})
        assert res3[1]["status"] == ValidationState.VALID_QR
        assert res3[1]["payload"] == "INV|B"

    def test_track_disappearance_and_expiration(self, smoother):
        """Tracks absent beyond drop_thresh are purged completely."""
        track1 = (1, 100, 100, 50, 50, 150, 150)
        # Confirm track 1
        for _ in range(3):
            smoother.update([track1], {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})

        assert 1 in smoother.confirmed_states

        # Track 1 disappears from active_tracks for drop_thresh + 1 frames
        for _ in range(6):
            smoother.update([], {})

        # Track 1 must be purged
        assert 1 not in smoother.history
        assert 1 not in smoother.confirmed_states

    def test_reappearing_track_does_not_use_stale_history(self, smoother):
        """A track that disappeared for a few frames cannot combine pre-disappearance frames for instant confirmation."""
        track1 = (1, 100, 100, 50, 50, 150, 150)

        # Frame 1 and 2 with INV|A (not confirmed yet)
        smoother.update([track1], {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})
        smoother.update([track1], {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})

        # Track disappears for 2 frames
        smoother.update([], {})
        smoother.update([], {})

        # Track reappears with frame 1 of INV|A
        res = smoother.update([track1], {1: {"status": ValidationState.VALID_QR, "payload": "INV|A", "polygon": None}})
        # Must NOT confirm on 1st frame after reappearance!
        assert res[1]["status"] == ValidationState.NO_QR
