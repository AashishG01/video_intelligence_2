import cv2
import numpy as np
import redis
import json
import base64
from ultralytics import YOLO

# Connect to the exact same Redis server
r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Loading YOLOv8 Model (Loading into GPU...)")
# Using the 'medium' model. It's the perfect balance of speed and accuracy for an A6000.
model = YOLO('yolov8m.pt') 
print("✅ YOLOv8 Online. Waiting for frames in the queue...")

while True:
    try:
        # brpop (Blocking Pop) pauses the script until a frame arrives. No 100% CPU spinning!
        # It pulls from the queue your producer.py is pushing to.
        queue_name, msg = r.brpop("raw_frames_queue", timeout=0)
        payload = json.loads(msg.decode('utf-8'))
        
        cam_id = payload['camera_id']
        timestamp = payload['timestamp']
        
        # 1. Decode the base64 string back into an OpenCV image
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # 2. Run Inference (Filter ONLY for class 0, which is 'Person')
        results = model(frame, classes=[0], verbose=False) 
        
        humans_found = 0
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                
                # ---------------------------------------------------------
                # THE INDIAN STREET FILTER: Ignore tiny people in the background
                # ---------------------------------------------------------
                w, h = x2 - x1, y2 - y1
                if w < 40 or h < 60: 
                    continue # Too far away for AntelopeV2 to see a face anyway
                    
                # 3. Crop the person out of the image
                crop = frame[y1:y2, x1:x2]
                
                # 4. Compress the crop and encode to Base64
                _, buffer = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                crop_b64 = base64.b64encode(buffer).decode('utf-8')
                
                # 5. Push the cropped human to the next Queue for Face Processing
                crop_payload = {
                    "camera_id": cam_id,
                    "timestamp": timestamp,
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(conf, 2),
                    "crop_data": crop_b64
                }
                r.lpush("person_crops_queue", json.dumps(crop_payload))
                humans_found += 1
        
        # Keep the person queue from exploding if the Face worker gets behind
        r.ltrim("person_crops_queue", 0, 5000)
        
        if humans_found > 0:
            print(f"[{cam_id}] Processed frame. Pushed {humans_found} usable human crops to the next queue.")

    except Exception as e:
        print(f"Error processing frame: {e}")