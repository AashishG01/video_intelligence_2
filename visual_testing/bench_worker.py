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
r = redis.Redis(host='localhost', port=6379, db=0)
COLLECTION_NAME = "bench_embeddings"
SAVE_FOLDER = "../backend_api/benchmark_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# 1. Database Connections
print("⏳ Connecting to Services...")
pg_conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

# Ensure table exists
pg_cursor.execute("""
    CREATE TABLE IF NOT EXISTS bench_sightings (
        id SERIAL PRIMARY KEY, person_id VARCHAR(50), 
        camera_id VARCHAR(50), timestamp FLOAT, image_path TEXT
    )
""")

milvus_client = MilvusClient(uri="http://localhost:19530")

# 2. Milvus Schema Fix
# Agar purani galat collection hai toh use uda do (sirf benchmark ke liye)
if milvus_client.has_collection(COLLECTION_NAME):
    # milvus_client.drop_collection(COLLECTION_NAME) # Un-comment if error persists
    pass

if not milvus_client.has_collection(COLLECTION_NAME):
    milvus_client.create_collection(
        collection_name=COLLECTION_NAME,
        dimension=512,
        metric_type="COSINE",
        auto_id=True
    )
milvus_client.load_collection(COLLECTION_NAME)

# 3. Initialize AI Model
print("⏳ Loading AntelopeV2...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.60, det_size=(1024, 1024))

print(f"🚀 Benchmark Worker Online. Listening to 'bench_face_ready'...")

# 📊 METRICS TRACKING
total_frames = 0
total_faces = 0
start_bench_time = time.time()

try:
    while True:
        res = r.brpop("bench_face_ready", timeout=0)
        payload = json.loads(res[1].decode('utf-8'))

        # ☠️ POISON PILL CHECK
        if payload.get("status") == "EOF":
            print("\n☠️ EOF Received! Shutting down and reporting...")
            # Forward poison pill to other workers
            r.lpush("bench_face_ready", json.dumps({"status": "EOF"}))
            break

        cam_id = payload['camera_id']
        timestamp = payload['timestamp']
        img_bytes = base64.b64decode(payload['frame_data'])
        frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

        if frame is None: continue

        t_start = time.time()
        
        # AI Detection & Embedding
        faces = face_app.get(frame)
        
        for face in faces:
            if face.det_score < 0.60: continue
            
            total_faces += 1
            embedding = face.embedding.tolist()
            
            # SEARCH (Using 'vector' field name)
            search_res = milvus_client.search(
                collection_name=COLLECTION_NAME,
                data=[embedding],
                limit=1,
                output_fields=["person_id"],
                search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
            )

            person_id = f"B_{int(time.time() * 1000)}" # Simplified for bench
            
            # Margin Cropping
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            mx, my = int(w * 0.25), int(h * 0.25)
            face_crop = frame[max(0, y1-my):min(frame.shape[0], y2+my), 
                             max(0, x1-mx):min(frame.shape[1], x2+mx)]
            
            # Disk Save
            filepath = os.path.join(SAVE_FOLDER, f"{person_id}.jpg")
            cv2.imwrite(filepath, face_crop)
            
            # INSERT (Key must be 'vector')
            milvus_client.insert(
                collection_name=COLLECTION_NAME, 
                data=[{"person_id": person_id, "vector": embedding}]
            )

            # SQL Log
            pg_cursor.execute(
                "INSERT INTO bench_sightings (person_id, camera_id, timestamp, image_path) VALUES (%s, %s, %s, %s)",
                (person_id, cam_id, timestamp, filepath)
            )

        total_frames += 1
        latency = (time.time() - t_start) * 1000
        q_len = r.llen("bench_face_ready")
        
        if total_frames % 10 == 0:
            print(f"⚡ [{cam_id}] Latency: {latency:.1f}ms | Faces: {len(faces)} | Q: {q_len}")

except KeyboardInterrupt:
    print("🛑 Stopped by user.")

# ==========================================
# 📈 FINAL BENCHMARK REPORT
# ==========================================
total_time = time.time() - start_bench_time
print("\n" + "="*50)
print("📊 WORKER BENCHMARK RESULTS")
print("="*50)
print(f"Total Test Duration:  {total_time:.2f} seconds")
print(f"Total Frames:         {total_frames}")
print(f"Total Faces Found:    {total_faces}")
if total_frames > 0:
    print(f"Avg Worker FPS:       {total_frames / total_time:.2f} FPS")
    print(f"Avg Latency/Frame:    {(total_time / total_frames) * 1000:.1f} ms")
print("="*50)