import os
import time
import cv2

class YoloDetector:
    def __init__(self, model_path: str, conf_threshold: float):
        self.is_available = False
        self.conf_threshold = conf_threshold
        self.model = None

        if not os.path.exists(model_path):
            print(f"[Detector] Model unavailable: File '{model_path}' not found on disk.")
            return
            
        try:
            os.environ["YOLO_VERBOSE"] = "False"
            os.environ["YOLO_OFFLINE"] = "True"
            
            from ultralytics import settings as yolo_settings
            yolo_settings.update({"sync": False})
            
            # Import ultralytics here to ensure it doesn't crash if missing
            import torch
            from ultralytics import YOLO
            torch.set_num_threads(1)
            self.model = YOLO(model_path)
            self.is_available = True
            print(f"[Detector] Model loaded successfully from {model_path}.")
        except Exception as e:
            print(f"[Detector] Model unavailable: Failed to load '{model_path}': {e}")

    def predict(self, frame):
        """
        Runs YOLOv8 tracking inference if the model is available.
        Returns: (annotated_frame, inference_fps, track_ids)
        """
        if not self.is_available or self.model is None:
            return frame, 0.0, []

        start_time = time.perf_counter()
        
        # Run tracking inference
        results = self.model.track(frame, conf=self.conf_threshold, persist=True, tracker="bytetrack.yaml", verbose=False)
        
        # Calculate purely the inference time
        end_time = time.perf_counter()
        inference_time = end_time - start_time
        inference_fps = 1.0 / inference_time if inference_time > 0 else 0.0
        
        # Draw bounding boxes and labels
        annotated_frame = frame.copy()
        
        active_track_ids = []
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                # Get coordinates
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                
                # Get confidence
                conf = float(box.conf[0].cpu().numpy())
                
                # Get class
                cls_id = int(box.cls[0].cpu().numpy())
                if cls_id != 0:
                    continue  # Strictly enforce only class 0 (box)
                cls_name = self.model.names[cls_id]
                
                # Get track ID
                track_id = int(box.id[0].cpu().numpy()) if box.id is not None else None
                if track_id is not None:
                    # Calculate centroid
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    active_track_ids.append((track_id, cx, cy, x1, y1, x2, y2, cls_name))
                
                # Draw box
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label
                label = f"{cls_name} {conf:.2f}"
                if track_id is not None:
                    label = f"ID:{track_id} {label}"
                cv2.putText(annotated_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return annotated_frame, inference_fps, active_track_ids
