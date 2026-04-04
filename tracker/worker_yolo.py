import cv2
import numpy as np
import redis
import json
import base64
import time
from ultralytics import YOLO

# ─────────────────────────────────────────
# 1. CONNECTIONS & SETUP
# ─────────────────────────────────────────
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)

# Upgraded to Medium model for RTX A6000
print("⏳ Loading YOLOv8m AI model...")
model = YOLO('yolov8m.pt') 
print("✅ YOLOv8 Tracker Online. Awaiting raw frames...")

# ─────────────────────────────────────────
# 2. MAIN TRACKING LOOP
# ─────────────────────────────────────────
while True:
    try:
        # Pull raw frame from camera producer
        queue_name, msg = r.brpop("raw_frames_queue", timeout=0)
        payload = json.loads(msg.decode('utf-8'))
        
        cam_id = payload['camera_id']
        timestamp = payload['timestamp']
        
        # Decode frame
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            continue

        # --- BYTETRACK CORE ---
        # persist=True keeps IDs stable across frames
        results = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], verbose=False)
        
        tracked_persons = []
        
        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            for box in boxes:
                # If tracker hasn't confidently assigned an ID yet, skip
                if box.id is None:
                    continue
                    
                track_id = int(box.id.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                tracked_persons.append({
                    "track_id": track_id,
                    "bbox": [x1, y1, x2, y2]
                })

        # --- FORWARD DATA ---
        # Only send to Face Worker if we actually tracked people
        if len(tracked_persons) > 0:
            next_payload = {
                "camera_id": cam_id,
                "timestamp": timestamp,
                "frame_data": payload['frame_data'], # Pass original frame
                "tracked_persons": tracked_persons   # Pass ByteTrack data
            }
            
            r.lpush("face_ready_queue", json.dumps(next_payload))
            r.ltrim("face_ready_queue", 0, 1000)

    except KeyboardInterrupt:
        print("\n🛑 YOLO Worker stopped.")
        break
    except Exception as e:
        print(f"⚠️ YOLO Worker Error: {e}")
        time.sleep(0.1)