"""
QR-to-Track Geometric Association and Temporal Smoothing Module.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
import math
import numpy as np

from qr.payload_validator import validate_qr_payload


class ValidationState(Enum):
    VALID_QR = "VALID_QR"
    INVALID_QR = "INVALID_QR"
    NO_QR = "NO_QR"
    UNREADABLE_QR = "UNREADABLE_QR"
    AMBIGUOUS = "AMBIGUOUS"


class QRSmoother:
    """
    Maintains temporal stability of QR observations per Track ID.
    Avoids flickering by requiring consecutive consistent observations 
    and retaining valid states across short interruptions.
    """

    def __init__(self, history_size: int = 15, confirmation_thresh: int = 3, drop_thresh: int = 10):
        self.history = {}  # track_id -> list of raw observations
        self.confirmed_states = {}  # track_id -> {status, payload, polygon}
        self.confirmation_thresh = max(1, confirmation_thresh)  # frames of consistent status to confirm
        self.history_size = max(history_size, self.confirmation_thresh)
        self.drop_thresh = drop_thresh  # missed frames before dropping confirmed state
        self.missed_counts = {}  # track_id -> int (consecutive missed/mismatched observations)
        self.inactive_counts = {}  # track_id -> int (consecutive frames absent from active_tracks)

    def _purge_track(self, t_id: int):
        """Removes all stored state for an expired track."""
        self.history.pop(t_id, None)
        self.confirmed_states.pop(t_id, None)
        self.missed_counts.pop(t_id, None)
        self.inactive_counts.pop(t_id, None)

    def update(self, active_tracks: List[tuple], raw_track_states: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        """
        Updates smoother state with new frame observations.

        active_tracks: List of tuples (track_id, cx, cy, x1, y1, x2, y2, ...)
        raw_track_states: Dict mapping track_id -> {"status": ValidationState, "payload": Optional[str], "polygon": Optional[np.ndarray]}
        
        Returns:
            smoothed_states: Dict mapping track_id -> {"status": ValidationState, "payload": Optional[str], "polygon": Optional[np.ndarray]}
        """
        current_track_ids = set(t[0] for t in active_tracks)

        # Track inactivity and cleanup expired stale tracks
        for t_id in list(self.history.keys()):
            if t_id not in current_track_ids:
                self.inactive_counts[t_id] = self.inactive_counts.get(t_id, 0) + 1
                if self.inactive_counts[t_id] > self.drop_thresh:
                    self._purge_track(t_id)

        smoothed_states = {}

        for t_id in current_track_ids:
            raw = raw_track_states.get(t_id, {
                "status": ValidationState.NO_QR,
                "payload": None,
                "polygon": None
            })

            # Handle track initialization or reappearance
            is_new_or_reappeared = (t_id not in self.history) or (self.inactive_counts.get(t_id, 0) > 0)
            if t_id not in self.history:
                self.history[t_id] = []
                self.confirmed_states[t_id] = {
                    "status": ValidationState.NO_QR,
                    "payload": None,
                    "polygon": None
                }
                self.missed_counts[t_id] = 0
            elif is_new_or_reappeared:
                # Track reappeared after being absent: clear raw history to prevent stale
                # pre-disappearance frames from improperly confirming a new QR.
                self.history[t_id] = []

            self.inactive_counts[t_id] = 0
            self.history[t_id].append(raw)
            if len(self.history[t_id]) > self.history_size:
                self.history[t_id].pop(0)

            curr_confirmed = self.confirmed_states[t_id]
            raw_status = raw["status"]
            raw_payload = raw["payload"]
            raw_poly = raw["polygon"]

            # Helper: Check if the last N observations are strictly consecutive and identical to target
            def has_consecutive_observations(target_status: ValidationState, target_payload: Optional[str]) -> bool:
                if len(self.history[t_id]) < self.confirmation_thresh:
                    return False
                recent = self.history[t_id][-self.confirmation_thresh:]
                return all(
                    obs.get("status") == target_status and obs.get("payload") == target_payload
                    for obs in recent
                )

            # --- Readable Payload (VALID_QR or INVALID_QR) ---
            if raw_status in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                # Check if current observation matches what is already confirmed
                if (curr_confirmed["status"] == raw_status and 
                        curr_confirmed["payload"] == raw_payload):
                    # Sustained match: reset miss count, update polygon
                    self.missed_counts[t_id] = 0
                    if raw_poly is not None:
                        curr_confirmed["polygon"] = raw_poly
                else:
                    # Observation differs from current confirmed state (or unconfirmed)
                    # Requires strictly consecutive consistent observations to confirm/switch
                    if has_consecutive_observations(raw_status, raw_payload):
                        self.confirmed_states[t_id] = {
                            "status": raw_status,
                            "payload": raw_payload,
                            "polygon": raw_poly
                        }
                        self.missed_counts[t_id] = 0
                    else:
                        # Not yet confirmed!
                        # If we already had a confirmed VALID/INVALID state, count this mismatch as a miss
                        # but retain the previous confirmed state within drop_thresh
                        if curr_confirmed["status"] in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                            self.missed_counts[t_id] += 1
                            if self.missed_counts[t_id] > self.drop_thresh:
                                # Stale state expired
                                self.confirmed_states[t_id] = {
                                    "status": ValidationState.NO_QR,
                                    "payload": None,
                                    "polygon": None
                                }
                        elif raw_poly is not None:
                            curr_confirmed["polygon"] = raw_poly

            # --- UNREADABLE_QR ---
            elif raw_status == ValidationState.UNREADABLE_QR:
                if curr_confirmed["status"] in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                    # Missed decode for a previously confirmed QR: retain confirmed state within drop_thresh
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        # Exceeded drop threshold: drop to UNREADABLE_QR
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.UNREADABLE_QR,
                            "payload": None,
                            "polygon": raw_poly
                        }
                    else:
                        # Retain valid status, but track polygon motion
                        if raw_poly is not None:
                            curr_confirmed["polygon"] = raw_poly
                else:
                    # Not previously confirmed valid: require consecutive unreadable to confirm UNREADABLE_QR
                    if has_consecutive_observations(ValidationState.UNREADABLE_QR, None):
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.UNREADABLE_QR,
                            "payload": None,
                            "polygon": raw_poly
                        }
                    elif raw_poly is not None:
                        curr_confirmed["polygon"] = raw_poly

            # --- NO_QR ---
            elif raw_status == ValidationState.NO_QR:
                if curr_confirmed["status"] in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                    # Transient detection miss: retain confirmed state within drop_thresh
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.NO_QR,
                            "payload": None,
                            "polygon": None
                        }
                elif curr_confirmed["status"] != ValidationState.NO_QR:
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.NO_QR,
                            "payload": None,
                            "polygon": None
                        }

            # --- AMBIGUOUS ---
            elif raw_status == ValidationState.AMBIGUOUS:
                # Ambiguous observation should never count as a valid match
                if curr_confirmed["status"] in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.AMBIGUOUS,
                            "payload": None,
                            "polygon": None
                        }
                else:
                    if has_consecutive_observations(ValidationState.AMBIGUOUS, None):
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.AMBIGUOUS,
                            "payload": None,
                            "polygon": None
                        }

            smoothed_states[t_id] = dict(self.confirmed_states[t_id])

        return smoothed_states


def validate_qrs(active_tracks: List[tuple], detected_qrs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates and associates QR code candidates against YOLO bounding boxes using geometric association.

    active_tracks: List of tuples (track_id, cx, cy, x1, y1, x2, y2, ...)
    detected_qrs: List of dicts {"payload": str, "cx": int, "cy": int, "polygon": np.ndarray}

    Returns a dict containing:
        - "raw_track_states": dict mapping track_id -> {"status": ValidationState, "payload": str or None, "polygon": np.ndarray or None}
        - "track_states": alias to "raw_track_states" for backward compatibility
        - "unmatched_qrs": list of QR dicts that did not belong to any box
        - "ambiguous_qrs": list of QR dicts involved in ambiguous associations
    """
    raw_track_states: Dict[int, Dict[str, Any]] = {}
    for t in active_tracks:
        track_id = t[0]
        raw_track_states[track_id] = {
            "status": ValidationState.NO_QR,
            "payload": None,
            "polygon": None
        }

    unmatched_qrs: List[Dict[str, Any]] = []
    ambiguous_qrs: List[Dict[str, Any]] = []

    # Map tracking boxes
    track_boxes = {}
    for t in active_tracks:
        track_id, _, _, x1, y1, x2, y2 = t[:7]
        track_boxes[track_id] = (float(x1), float(y1), float(x2), float(y2))

    # Track to assigned QR candidates
    track_candidates: Dict[int, List[Dict[str, Any]]] = {t[0]: [] for t in active_tracks}
    # Tracks flagged with overlapping ambiguous candidate
    track_ambiguous_flags: Dict[int, bool] = {t[0]: False for t in active_tracks}

    pad = 20  # Margin to accommodate boundary edge QR codes

    # 1. First pass: Evaluate each QR candidate against all tracked boxes
    for qr in detected_qrs:
        qr_cx = qr.get("cx", 0)
        qr_cy = qr.get("cy", 0)

        containing_tracks = []
        for track_id, (x1, y1, x2, y2) in track_boxes.items():
            if (x1 - pad) <= qr_cx <= (x2 + pad) and (y1 - pad) <= qr_cy <= (y2 + pad):
                containing_tracks.append(track_id)

        if len(containing_tracks) == 0:
            # QR is outside every detected box
            unmatched_qrs.append(qr)
        elif len(containing_tracks) > 1:
            # QR is in the intersection of multiple boxes: ownership is ambiguous
            ambiguous_qrs.append(qr)
            for t_id in containing_tracks:
                track_ambiguous_flags[t_id] = True
        else:
            # Exactly one box contains this QR center
            matched_track_id = containing_tracks[0]
            track_candidates[matched_track_id].append(qr)

    # 2. Second pass: Evaluate association per track ID
    for t in active_tracks:
        t_id = t[0]
        candidates = track_candidates.get(t_id, [])
        has_ambiguous_overlap = track_ambiguous_flags.get(t_id, False)

        if len(candidates) == 0:
            if has_ambiguous_overlap:
                # Box overlapped with an ambiguous QR, and has no other clear candidate
                raw_track_states[t_id] = {
                    "status": ValidationState.AMBIGUOUS,
                    "payload": None,
                    "polygon": None
                }
            else:
                # Clean absence of QR
                raw_track_states[t_id] = {
                    "status": ValidationState.NO_QR,
                    "payload": None,
                    "polygon": None
                }

        elif len(candidates) == 1:
            qr = candidates[0]
            if has_ambiguous_overlap:
                # Conflict: box has a private candidate but also overlaps an ambiguous QR
                raw_track_states[t_id] = {
                    "status": ValidationState.AMBIGUOUS,
                    "payload": None,
                    "polygon": qr.get("polygon")
                }
                if qr not in ambiguous_qrs:
                    ambiguous_qrs.append(qr)
            else:
                # Unambiguous 1-to-1 match
                poly = qr.get("polygon")
                raw_payload = qr.get("payload")

                if raw_payload is None or raw_payload == "":
                    raw_track_states[t_id] = {
                        "status": ValidationState.UNREADABLE_QR,
                        "payload": None,
                        "polygon": poly
                    }
                else:
                    is_valid, norm_payload, sku = validate_qr_payload(raw_payload)
                    if is_valid:
                        raw_track_states[t_id] = {
                            "status": ValidationState.VALID_QR,
                            "payload": norm_payload,
                            "polygon": poly
                        }
                    else:
                        raw_track_states[t_id] = {
                            "status": ValidationState.INVALID_QR,
                            "payload": str(raw_payload),
                            "polygon": poly
                        }

        else:
            # Multiple candidates associated with one track (len > 1)
            # Check if all candidates are duplicate detections of the same physical QR
            unique_payloads = set(c.get("payload") for c in candidates)
            all_centers_close = True
            first_cx, first_cy = candidates[0].get("cx", 0), candidates[0].get("cy", 0)
            for other_c in candidates[1:]:
                dist = math.hypot(other_c.get("cx", 0) - first_cx, other_c.get("cy", 0) - first_cy)
                if dist > 30.0:  # Distance threshold for duplicate detection
                    all_centers_close = False
                    break

            if len(unique_payloads) == 1 and all_centers_close:
                # Deduplicated: multiple detections of the exact same QR
                qr = candidates[0]
                poly = qr.get("polygon")
                raw_payload = qr.get("payload")

                if raw_payload is None or raw_payload == "":
                    raw_track_states[t_id] = {
                        "status": ValidationState.UNREADABLE_QR,
                        "payload": None,
                        "polygon": poly
                    }
                else:
                    is_valid, norm_payload, sku = validate_qr_payload(raw_payload)
                    if is_valid:
                        raw_track_states[t_id] = {
                            "status": ValidationState.VALID_QR,
                            "payload": norm_payload,
                            "polygon": poly
                        }
                    else:
                        raw_track_states[t_id] = {
                            "status": ValidationState.INVALID_QR,
                            "payload": str(raw_payload),
                            "polygon": poly
                        }
            else:
                # Truly multiple distinct QR candidates inside this track!
                # Never silently choose the last candidate -> mark AMBIGUOUS explicitly
                for c in candidates:
                    if c not in ambiguous_qrs:
                        ambiguous_qrs.append(c)
                raw_track_states[t_id] = {
                    "status": ValidationState.AMBIGUOUS,
                    "payload": None,
                    "polygon": None
                }

    return {
        "raw_track_states": raw_track_states,
        "track_states": raw_track_states,  # Backward compatibility alias
        "unmatched_qrs": unmatched_qrs,
        "ambiguous_qrs": ambiguous_qrs
    }
