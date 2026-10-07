from enum import Enum
from typing import Dict, Tuple, Set

class Direction(Enum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"

class LineCounter:
    def __init__(self, start_x: int, start_y: int, end_x: int, end_y: int, target_class: str = "box"):
        if start_x == end_x and start_y == end_y:
            raise ValueError("Invalid line configuration: Line length cannot be zero.")
            
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.target_class = target_class
        
        # State
        self.previous_states: Dict[int, int] = {}  # track_id -> side (1 for positive, -1 for negative)
        self.counted_tracks: Set[int] = set()
        
        self.total_count = 0
        
    def _get_side(self, cx: float, cy: float) -> int:
        """
        Computes the cross product to determine the side of the line.
        Returns 1 for positive, -1 for negative, 0 for exactly on the line.
        """
        cross_product = (self.end_x - self.start_x) * (cy - self.start_y) - (self.end_y - self.start_y) * (cx - self.start_x)
        if cross_product > 0:
            return 1
        elif cross_product < 0:
            return -1
        return 0
        
    def process_tracks(self, active_tracks) -> list:
        current_active_ids = set()
        crossings = []
        
        for track in active_tracks:
            track_id, cx, cy = track[0], track[1], track[2]
            cls_name = track[7] if len(track) > 7 else None
            
            current_active_ids.add(track_id)
            current_side = self._get_side(cx, cy)
            
            # If the point is exactly on the line, we don't change its physical side memory
            if current_side == 0 and track_id in self.previous_states:
                current_side = self.previous_states[track_id]
            elif current_side == 0:
                # First time seeing it and it's exactly on the line? Just skip until it moves off
                continue
                
            if track_id in self.previous_states:
                previous_side = self.previous_states[track_id]
                
                # Check for a side transition
                if current_side != previous_side:
                    direction = Direction.B_TO_A if current_side == 1 else Direction.A_TO_B
                    
                    if track_id not in self.counted_tracks:
                        self.counted_tracks.add(track_id)
                        # Only increment total_count if it matches the target class (or if target_class is empty)
                        if not self.target_class or cls_name == self.target_class:
                            self.total_count += 1
                        
                        crossings.append({
                            "track_id": track_id, 
                            "direction": direction.value,
                            "cls_name": cls_name
                        })
                        
            # Update history
            self.previous_states[track_id] = current_side
            
        # Cleanup stale tracks from active memory (but NOT from counted_tracks)
        stale_ids = set(self.previous_states.keys()) - current_active_ids
        for sid in stale_ids:
            del self.previous_states[sid]
            
        return crossings
