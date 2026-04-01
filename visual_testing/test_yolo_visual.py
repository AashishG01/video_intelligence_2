import cv2
import numpy as np
import redis
import json
import base64
from ultralytics import YOLO

# Connect to the local Redis server
r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Loading YOLOv8 Model for Visual Debugging...")
model = YOLO('yolov8m.pt') 
print("✅ YOLOv8 Online. Waiting for frames from Producer...")

cv2.namedWindow("YOLO Visual Debugger", cv2.WINDOW_NORMAL)

while True:
    try:
        # Pull the next frame from the queue (Timeout=1 means it checks every second if empty)
        msg = r.brpop("raw_frames_queue", timeout=1)
        
        if not msg:
            continue # Queue is empty, keep waiting
            
        queue_name, data = msg
        payload = json.loads(data.decode('utf-8'))
        
        cam_id = payload['camera_id']
        
        # Decode the image back to OpenCV format
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # Run YOLO inference
        results = model(frame, classes=[0], verbose=False) # class 0 = Person
        
        # Draw bounding boxes
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                
                # Check our Indian Street Filter limits
                w, h = x2 - x1, y2 - y1
                if w < 40 or h < 60:
                    # Draw a RED box for people being ignored (too small)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)
                    cv2.putText(frame, "IGNORED", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    continue
                
                # Draw a THICK GREEN box for targets that will be sent to the Face AI
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                label = f"TARGET: {conf:.2f}"
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Display the camera name and frame
        cv2.putText(frame, f"FEED: {cam_id}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3)
        cv2.imshow("YOLO Visual Debugger", frame)
        
        # Press 'q' to quit the visualizer
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print(f"Error: {e}")

cv2.destroyAllWindows()