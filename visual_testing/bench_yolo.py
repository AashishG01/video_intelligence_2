import cv2
import numpy as np
import redis
import json
import base64
from ultralytics import YOLO

r = redis.Redis(host='localhost', port=6379, db=0)
model = YOLO('yolov8m.pt')

print("✅ Benchmark YOLO Filter Online.")

while True:
    res = r.brpop("bench_raw_frames", timeout=0)
    payload = json.loads(res[1].decode('utf-8'))

    # POISON PILL CHECK
    if payload.get("status") == "EOF":
        print("☠️ EOF received. Forwarding to Face Workers and shutting down YOLO...")
        r.lpush("bench_face_ready", json.dumps(payload))
        break

    img_bytes = base64.b64decode(payload['frame_data'])
    frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

    results = model(frame, classes=[0], verbose=False)
    
    found = False
    for result in results:
        for box in result.boxes:
            conf = float(box.conf[0])
            w, h = box.xyxy[0][2] - box.xyxy[0][0], box.xyxy[0][3] - box.xyxy[0][1]
            if conf > 0.6 and w > 100 and h > 150:
                found = True; break
        if found: break

    if found:
        r.lpush("bench_face_ready", json.dumps(payload))
        q_len = r.llen("bench_raw_frames")
        print(f"👁️ [{payload['camera_id']}] Person Found! | YOLO Queue Backlog: {q_len}")

print("🏁 YOLO Filter Shutdown Complete.")