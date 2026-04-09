import cv2
import numpy as np
import redis
import json
import base64
import os
import time
import psycopg2
from pymilvus import MilvusClient
from insightface.app import FaceAnalysis

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
CONFIDENCE_GATE   = 0.60
MATCH_THRESHOLD   = 0.60 
DEDUP_WINDOW_SEC  = 60
COLLECTION_NAME   = "face_embeddings"
SAVE_FOLDER       = "../backend_api/captured_faces"

# 1. Connections (EK BAAR HI KAREIN - POOLING)
print("⏳ Connecting to all services...")
r = redis.Redis(host='localhost', port=6379, db=0)
# Persistent connection for publishing to avoid handshake overhead
r_pub = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

pg_conn = psycopg2.connect(
    dbname="surveillance", user="admin", password="password", 
    host="localhost", port="5432"
)
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

milvus_client = MilvusClient(uri="http://localhost:19530")
milvus_client.load_collection(COLLECTION_NAME)

os.makedirs(SAVE_FOLDER, exist_ok=True)

# 2. Initialize AI Model
print("⏳ Loading AntelopeV2...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.65, det_size=(1024, 1024))
print("✅ High-Performance Worker Online.")

# ─────────────────────────────────────────
# MAIN WORKER LOOP
# ─────────────────────────────────────────
while True:
    try:
        # Pull from queue
        res = r.brpop("face_ready_queue", timeout=1)
        if not res:
            continue
            
        # 📊 MONITORING: Check how many images are left in the queue
        queue_len = r.llen("face_ready_queue")
        
        payload   = json.loads(res[1].decode('utf-8'))
        cam_id    = payload['camera_id']
        timestamp = payload['timestamp']

        # Decode full frame
        img_bytes = base64.b64decode(payload['frame_data'])
        frame     = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

        if frame is None:
            continue

        # AI Detection & Recognition
        faces = face_app.get(frame)

        for face in faces:
            if face.det_score < CONFIDENCE_GATE:
                continue

            embedding = face.embedding.tolist()

            # ── Milvus Search ──
            search_res = milvus_client.search(
                collection_name=COLLECTION_NAME,
                data=[embedding],
                limit=1,
                output_fields=["person_id"],
                search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
            )

            is_match = False
            person_id = None

            if search_res and len(search_res[0]) > 0:
                top = search_res[0][0]
                if top['distance'] > MATCH_THRESHOLD:
                    person_id = top['entity']['person_id']
                    is_match = True

            if not person_id:
                person_id = f"P_{int(time.time() * 1000)}"

            # Dedup Check
            cache_key = f"seen_global_{person_id}"
            if r.exists(cache_key):
                continue

            # ── MARGIN CROP (25% Padding) ──
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            margin_x, margin_y = int(w * 0.25), int(h * 0.25)
            
            y1_m = max(0, y1 - margin_y)
            y2_m = min(frame.shape[0], y2 + margin_y)
            x1_m = max(0, x1 - margin_x)
            x2_m = min(frame.shape[1], x2 + margin_x)
            
            face_crop = frame[y1_m:y2_m, x1_m:x2_m]

            # ── SAVE & DATABASE OPS ──
            person_folder = os.path.join(SAVE_FOLDER, person_id)
            os.makedirs(person_folder, exist_ok=True)
            filename = f"{cam_id}_{int(timestamp)}.jpg"
            filepath = os.path.join(person_folder, filename)
            cv2.imwrite(filepath, face_crop)

            # Insert to Milvus (NO FLUSH - Background process handle karega)
            milvus_client.insert(
                collection_name=COLLECTION_NAME,
                data=[{"person_id": person_id, "embedding": embedding}]
            )

            # Insert to PostgreSQL
            relative_path = f"/captured_faces/{person_id}/{filename}"
            pg_cursor.execute(
                "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) "
                "VALUES (%s, %s, %s, %s)",
                (person_id, cam_id, timestamp, relative_path)
            )

            # Cache & Publish (Using pre-connected r_pub)
            r.setex(cache_key, DEDUP_WINDOW_SEC, "1")
            
            r_pub.publish("live_face_alerts", json.dumps({
                "person_id":  person_id,
                "camera_id":  cam_id,
                "timestamp":  timestamp,
                "image_path": relative_path,
                "confidence": round(float(face.det_score), 3),
                "status":     "MATCH" if is_match else "NEW"
            }))

            status_label = "MATCH ✅" if is_match else "NEW 🆕"
            print(f"[{cam_id}] {status_label}: {person_id} | Pending in Queue: {queue_len}")

    except Exception as e:
        print(f"⚠️ Worker Error: {e}")
        time.sleep(0.1)