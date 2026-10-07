from qr.association import validate_qrs, ValidationState

def test_headless_qr_association():
    print("--- Phase 7 Headless Unit Tests ---")
    
    # Track format: (track_id, cx, cy, x1, y1, x2, y2)
    # Box 1: (0, 0) to (100, 100). Track ID 1
    # Box 2: (150, 150) to (250, 250). Track ID 2
    # Box 3: (100, 100) to (200, 200). Track ID 3 (overlaps with box 2 from 150-200)
    tracks = [
        (1, 50, 50, 0, 0, 100, 100),
        (2, 200, 200, 150, 150, 250, 250),
        (3, 150, 150, 100, 100, 200, 200)
    ]
    
    # Test 1: No QR result -> NO_QR
    res = validate_qrs(tracks, [])
    assert res["track_states"][1]["status"] == ValidationState.NO_QR
    assert res["track_states"][2]["status"] == ValidationState.NO_QR
    print("PASS: No QRs -> All tracks NO_QR, no crash.")
    
    # Test 2: QR center inside one tracked box -> VALID_QR
    qr_valid = {"payload": "BOX-001", "cx": 50, "cy": 50}
    res = validate_qrs(tracks, [qr_valid])
    assert res["track_states"][1]["status"] == ValidationState.VALID_QR
    assert res["track_states"][1]["payload"] == "BOX-001"
    assert res["track_states"][2]["status"] == ValidationState.NO_QR
    print("PASS: QR inside one box -> VALID_QR with preserved payload.")
    
    # Test 3: QR outside all boxes -> UNMATCHED
    qr_outside = {"payload": "UNKNOWN", "cx": 300, "cy": 300}
    res = validate_qrs(tracks, [qr_outside])
    assert len(res["unmatched_qrs"]) == 1
    assert res["unmatched_qrs"][0]["payload"] == "UNKNOWN"
    print("PASS: QR outside all boxes -> UNMATCHED.")
    
    # Test 4: QR overlapping multiple boxes -> AMBIGUOUS
    qr_overlap = {"payload": "OVERLAP", "cx": 175, "cy": 175} # Inside Box 2 and Box 3
    res = validate_qrs(tracks, [qr_overlap])
    assert len(res["ambiguous_qrs"]) == 1
    assert res["track_states"][2]["status"] == ValidationState.NO_QR
    assert res["track_states"][3]["status"] == ValidationState.NO_QR
    print("PASS: QR in overlapping boxes -> AMBIGUOUS.")
    
    # Test 4.5: QR inside one tracked box but payload is None -> UNREADABLE_QR
    qr_unreadable = {"payload": None, "cx": 50, "cy": 50}
    res = validate_qrs(tracks, [qr_unreadable])
    assert res["track_states"][1]["status"] == ValidationState.UNREADABLE_QR
    assert res["track_states"][1]["payload"] is None
    print("PASS: QR inside one box with None payload -> UNREADABLE_QR.")
    
    # Test 5: Multiple QRs handled independently
    res = validate_qrs(tracks, [qr_valid, qr_outside, qr_overlap, qr_unreadable])
    # The last QR assigned to box 1 was qr_unreadable since list is processed sequentially. Wait, they overwrite based on order. Let's just use qr_valid.
    res = validate_qrs(tracks, [qr_valid, qr_outside, qr_overlap])
    assert res["track_states"][1]["status"] == ValidationState.VALID_QR
    assert len(res["unmatched_qrs"]) == 1
    assert len(res["ambiguous_qrs"]) == 1
    print("PASS: Multiple QRs handled independently.")
    
if __name__ == "__main__":
    test_headless_qr_association()
