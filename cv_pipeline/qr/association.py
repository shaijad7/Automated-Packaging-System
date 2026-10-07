from enum import Enum
from typing import List, Dict, Any

class ValidationState(Enum):
    VALID_QR = "VALID_QR"
    INVALID_QR = "INVALID_QR"
    NO_QR = "NO_QR"
    UNREADABLE_QR = "UNREADABLE_QR"
    AMBIGUOUS = "AMBIGUOUS"

class QRSmoother:
    """
    Maintains temporal stability of QR observations per Track ID.
    Avoids flickering by requiring a few consistent observations 
    and retaining valid states across short interruptions.
    """
    def __init__(self, history_size=15, confirmation_thresh=3, drop_thresh=10):
        self.history = {} # track_id -> list of raw observations
        self.confirmed_states = {} # track_id -> {status, payload, polygon}
        self.history_size = history_size
        self.confirmation_thresh = confirmation_thresh # frames of new status to switch
        self.drop_thresh = drop_thresh # missed frames before dropping VALID
        self.missed_counts = {}

    def update(self, active_tracks, raw_track_states):
        """
        raw_track_states: output of original validation for this frame.
        returns: smoothed track_states (dict mapping track_id -> {status, payload, polygon})
        """
        current_track_ids = set([t[0] for t in active_tracks])
        
        # Cleanup stale tracks
        for t_id in list(self.history.keys()):
            if t_id not in current_track_ids:
                del self.history[t_id]
                if t_id in self.confirmed_states:
                    del self.confirmed_states[t_id]
                if t_id in self.missed_counts:
                    del self.missed_counts[t_id]

        smoothed_states = {}

        for t_id in current_track_ids:
            raw = raw_track_states.get(t_id, {"status": ValidationState.NO_QR, "payload": None, "polygon": None})
            
            if t_id not in self.history:
                self.history[t_id] = []
                self.confirmed_states[t_id] = {"status": ValidationState.NO_QR, "payload": None, "polygon": None}
                self.missed_counts[t_id] = 0
                
            self.history[t_id].append(raw)
            if len(self.history[t_id]) > self.history_size:
                self.history[t_id].pop(0)
                
            curr_confirmed = self.confirmed_states[t_id]
            
            if raw["status"] == ValidationState.VALID_QR or raw["status"] == ValidationState.INVALID_QR:
                # We have a readable payload
                # Reset missed count since we saw something readable
                self.missed_counts[t_id] = 0
                
                # Check if we should switch to this new payload/status
                recent_similar = sum(1 for obs in self.history[t_id][-self.confirmation_thresh:] 
                                   if obs["payload"] == raw["payload"])
                                   
                if recent_similar >= min(self.confirmation_thresh, len(self.history[t_id])):
                    self.confirmed_states[t_id] = {
                        "status": raw["status"],
                        "payload": raw["payload"],
                        "polygon": raw["polygon"] # update polygon if valid
                    }
                else:
                    # Keep old confirmed state but update polygon if we have one
                    if raw["polygon"] is not None:
                        self.confirmed_states[t_id]["polygon"] = raw["polygon"]
                        
            elif raw["status"] == ValidationState.UNREADABLE_QR:
                # Saw a QR shape but no payload
                # If we were previously VALID, tolerate a few missed decodes
                if curr_confirmed["status"] in (ValidationState.VALID_QR, ValidationState.INVALID_QR):
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        # Drop to UNREADABLE after too many missed decodes
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.UNREADABLE_QR,
                            "payload": None,
                            "polygon": raw["polygon"]
                        }
                    else:
                        # Keep confirmed VALID state, but update the drawn polygon to track its movement
                        if raw["polygon"] is not None:
                            self.confirmed_states[t_id]["polygon"] = raw["polygon"]
                else:
                    # Weren't valid anyway, update to unreadable and update polygon
                    recent_unreadable = sum(1 for obs in self.history[t_id][-self.confirmation_thresh:] 
                                          if obs["status"] == ValidationState.UNREADABLE_QR)
                    if recent_unreadable >= min(self.confirmation_thresh, len(self.history[t_id])):
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.UNREADABLE_QR,
                            "payload": None,
                            "polygon": raw["polygon"]
                        }
                    else:
                        if raw["polygon"] is not None:
                            self.confirmed_states[t_id]["polygon"] = raw["polygon"]

            elif raw["status"] == ValidationState.NO_QR:
                # No QR shape seen at all
                if curr_confirmed["status"] != ValidationState.NO_QR:
                    self.missed_counts[t_id] += 1
                    if self.missed_counts[t_id] > self.drop_thresh:
                        self.confirmed_states[t_id] = {
                            "status": ValidationState.NO_QR,
                            "payload": None,
                            "polygon": None
                        }
                else:
                    self.confirmed_states[t_id] = {
                        "status": ValidationState.NO_QR,
                        "payload": None,
                        "polygon": None
                    }
                    
            smoothed_states[t_id] = dict(self.confirmed_states[t_id])

        return smoothed_states

def validate_qrs(active_tracks: List[tuple], detected_qrs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates QR codes against YOLO bounding boxes using geometric association.
    
    active_tracks: List of tuples (track_id, cx, cy, x1, y1, x2, y2)
    detected_qrs: List of dicts {"payload": str, "cx": int, "cy": int, "polygon": [...]}
    
    Returns a dict containing:
        - "raw_track_states": dict mapping track_id -> {"status": ValidationState, "payload": str or None, "polygon": [...]}
        - "unmatched_qrs": list of QR dicts that did not belong to any box
        - "ambiguous_qrs": list of QR dicts that fell into multiple boxes
    """
    
    raw_track_states = {}
    for t in active_tracks:
        track_id = t[0]
        raw_track_states[track_id] = {"status": ValidationState.NO_QR, "payload": None, "polygon": None}
        
    unmatched_qrs = []
    ambiguous_qrs = []
    
    # Evaluate each QR independently
    for qr in detected_qrs:
        qr_cx = qr["cx"]
        qr_cy = qr["cy"]
        
        containing_boxes = []
        for t in active_tracks:
            track_id, _, _, x1, y1, x2, y2 = t[:7]
            # Use a slightly expanded box to catch QRs on the edge
            pad = 20
            if (x1-pad) <= qr_cx <= (x2+pad) and (y1-pad) <= qr_cy <= (y2+pad):
                containing_boxes.append(track_id)
                
        if len(containing_boxes) == 0:
            unmatched_qrs.append(qr)
        elif len(containing_boxes) > 1:
            ambiguous_qrs.append(qr)
        else:
            # Exactly 1 match
            matched_track_id = containing_boxes[0]
            raw_track_states[matched_track_id]["polygon"] = qr["polygon"]
            
            if qr["payload"] is None:
                raw_track_states[matched_track_id]["status"] = ValidationState.UNREADABLE_QR
            else:
                # Phase 10B check integrated directly into validation
                if qr["payload"].startswith("INV|"):
                    raw_track_states[matched_track_id]["status"] = ValidationState.VALID_QR
                else:
                    raw_track_states[matched_track_id]["status"] = ValidationState.INVALID_QR
                raw_track_states[matched_track_id]["payload"] = qr["payload"]
            
    return {
        "raw_track_states": raw_track_states,
        "unmatched_qrs": unmatched_qrs,
        "ambiguous_qrs": ambiguous_qrs
    }
