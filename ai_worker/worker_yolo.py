import cv2
import numpy as np
import redis
import json
import base64
from ultralytics import YOLO

r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Loading YOLOv8...")
model = YOLO('yolov8m.pt')
print("✅ YOLO Online.")

while True:
    try:
        queue_name, msg = r.brpop("raw_frames_queue", timeout=0)
        payload = json.loads(msg.decode('utf-8'))

        cam_id = payload['camera_id']

        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # YOLO as pre-filter only
        results = model(frame, classes=[0], verbose=False)

        people_found = False
        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w, h = x2 - x1, y2 - y1
                # only count people large enough to have a usable face
                if conf > 0.5 and w > 40 and h > 80:
                    people_found = True
                    break
            if people_found:
                break

        if people_found:
            # Push FULL FRAME to face worker, not crops
            r.lpush("face_ready_queue", json.dumps(payload))
            r.ltrim("face_ready_queue", 0, 500)
            print(f"[{cam_id}] 👤 People detected — frame queued for face analysis.")

    except Exception as e:
        print(f"⚠️ YOLO Error: {e}")