import cv2
import sys

def main():
    print("Testing if camera can be acquired...")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("FAIL: Camera could not be opened.")
        sys.exit(1)
        
    ret, frame = cap.read()
    if ret and frame is not None:
        print("SUCCESS: Camera acquired and read frame successfully.")
    else:
        print("FAIL: Camera opened but could not read frame.")
        
    cap.release()

if __name__ == "__main__":
    main()
