print("STARTING")
import time
t0 = time.time()
try:
    print("IMPORTING ultralytics...")
    import ultralytics
    print(f"IMPORTED ultralytics in {time.time()-t0:.2f}s")
    
    t1 = time.time()
    print("IMPORTING YOLO...")
    from ultralytics import YOLO
    print(f"IMPORTED YOLO in {time.time()-t1:.2f}s")
    
    t2 = time.time()
    print("LOADING MODEL...")
    model = YOLO("runs/phase9_training/weights/best.pt")
    print(f"YOLO MODEL LOADED in {time.time()-t2:.2f}s")
except Exception as e:
    print(f"EXCEPTION: {e}")
