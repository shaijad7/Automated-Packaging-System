from counting.line_counter import LineCounter, Direction

def test_headless_counter():
    print("--- Phase 6 Headless Unit Tests ---")
    
    try:
        LineCounter(10, 10, 10, 10)
        print("FAIL: LineCounter allowed zero-length line.")
    except ValueError:
        print("PASS: Zero-length line properly rejected.")
        
    counter = LineCounter(0, 100, 100, 100, target_class=None) # Horizontal line at y=100
    
    # Test 1: Empty detections
    crossings = counter.process_tracks([])
    assert len(crossings) == 0
    assert counter.total_count == 0
    print("PASS: Empty tracks -> 0 count.")
    
    # Test 2: No cross (moving parallel)
    counter.process_tracks([(1, 50, 50)]) # Above line
    crossings = counter.process_tracks([(1, 60, 50)]) # Still above
    assert counter.total_count == 0
    print("PASS: No cross -> 0 count.")
    
    # Test 3: Real cross A->B
    crossings = counter.process_tracks([(1, 50, 150)]) # Below line (Crossed)
    assert counter.total_count == 1
    assert crossings[0]["track_id"] == 1
    print("PASS: Real cross -> 1 count.")
    
    # Test 4: No duplicate
    crossings = counter.process_tracks([(1, 50, 50)]) # Cross back
    assert counter.total_count == 1 # Still 1!
    print("PASS: No duplicate counting.")
    
    # Test 5: Exact 0 cross product
    # Line is y=100.
    counter.process_tracks([(2, 50, 50)]) # Start above
    counter.process_tracks([(2, 50, 100)]) # Exactly on line
    assert counter.total_count == 1 # Hasn't crossed yet
    counter.process_tracks([(2, 50, 150)]) # Now below line
    assert counter.total_count == 2 # Crossed!
    print("PASS: Exact zero cross product handled safely.")
    
    # Test 6: Disappearance cleanup
    counter.process_tracks([(3, 50, 50)])
    assert 3 in counter.previous_states
    counter.process_tracks([]) # Empty room
    assert 3 not in counter.previous_states
    assert 1 in counter.counted_tracks # Counted tracks persists
    print("PASS: Stale states cleaned up, counted tracks persist.")

if __name__ == "__main__":
    test_headless_counter()
