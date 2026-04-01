import cv2
from ultralytics import YOLO

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Put the path to one of your Surat city test videos here
VIDEO_PATH = "/home/user/Desktop/Video Surveillence ETE/samplefootage/zampabazzar.avi"

# Load the YOLO model (using nano/small for fast testing)
print("⏳ Loading YOLOv8 model...")
model = YOLO('yolov8m.pt') 

# ==========================================
# 2. VIDEO SETUP
# ==========================================
cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print(f"❌ Error: Could not open video at {VIDEO_PATH}")
    exit()

print("✅ Video loaded. Press 'q' to quit the visualizer.")

# ==========================================
# 3. TRACKING LOOP
# ==========================================
while True:
    ret, frame = cap.read()
    if not ret:
        print("🎬 Video finished.")
        break
    
    # Resize for display purposes so it fits on your screen
    display_frame = cv2.resize(frame, (1024, 576))

    # Run YOLO + ByteTrack
    # persist=True is CRITICAL. It tells the tracker to remember IDs from the last frame.
    # classes=[0] ensures it ONLY tracks people (class 0 in COCO dataset), ignoring cars/dogs.
    results = model.track(
        display_frame, 
        persist=True, 
        tracker="bytetrack.yaml", 
        classes=[0],
        verbose=False # Hides the spammy terminal output
    )

    # results[0].plot() automatically draws the bounding boxes and Track IDs on the frame!
    annotated_frame = results[0].plot()

    # Show the frame on your screen
    cv2.imshow("ByteTrack Visualizer - Press 'q' to quit", annotated_frame)

    # Press 'q' to exit early
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()