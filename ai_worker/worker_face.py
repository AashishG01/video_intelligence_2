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
# 1. Connections
# ─────────────────────────────────────────

print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Connecting to PostgreSQL...")
pg_conn = psycopg2.connect(
    dbname="surveillance",
    user="admin",
    password="password",
    host="localhost",
    port="5432"
)
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

print("⏳ Connecting to Milvus Standalone...")
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "face_embeddings"

# ─────────────────────────────────────────
# 2. Ensure Milvus Collection Exists & Is Loaded
# ─────────────────────────────────────────

def ensure_collection_loaded():
    """Create collection if missing, then load it into memory."""
    if not milvus_client.has_collection(COLLECTION_NAME):
        print(f"⚠️  Collection '{COLLECTION_NAME}' not found. Creating it...")
        milvus_client.create_collection(
            collection_name=COLLECTION_NAME,
            dimension=512,          # AntelopeV2 = 512-dim embeddings
            metric_type="COSINE",
            auto_id=True,
        )
        print(f"✅ Collection '{COLLECTION_NAME}' created.")

    milvus_client.load_collection(COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' loaded into memory.")

ensure_collection_loaded()

# ─────────────────────────────────────────
# 3. Setup Save Directory
# ─────────────────────────────────────────

# Root folder — per-person subfolders will be created inside this
SAVE_FOLDER = "../backend_api/captured_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# ─────────────────────────────────────────
# 4. Helper — Get or Create Person Folder
# ─────────────────────────────────────────

def get_person_folder(person_id: str) -> str:
    """
    Returns the folder path for a given person_id.
    Creates the folder if it doesn't exist yet.

    Structure:
        captured_faces/
            P_1743047823000/
                cam1_1743047823.jpg
                cam2_1743047900.jpg
            P_1743047999000/
                cam1_1743047999.jpg
    """
    folder = os.path.join(SAVE_FOLDER, person_id)
    os.makedirs(folder, exist_ok=True)
    return folder

# ─────────────────────────────────────────
# 5. Initialize Face AI Model
# ─────────────────────────────────────────

print("⏳ Loading AntelopeV2 AI model...")
face_app = FaceAnalysis(
    name='antelopev2',
    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
)
face_app.prepare(ctx_id=0, det_thresh=0.45, det_size=(320, 320))
print("✅ Face Worker Online. Awaiting human crops...")

# ─────────────────────────────────────────
# 6. Main Worker Loop
# ─────────────────────────────────────────

while True:
    try:
        # ── Pull job from Redis queue (blocks until message arrives) ──
        queue_name, msg = r.brpop("person_crops_queue", timeout=0)
        payload = json.loads(msg.decode('utf-8'))

        cam_id    = payload['camera_id']
        timestamp = payload['timestamp']

        # ── Decode base64 image ──
        img_bytes = base64.b64decode(payload['crop_data'])
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        crop_img  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if crop_img is None:
            print(f"[{cam_id}] ⚠️  Failed to decode image. Skipping.")
            continue

        # ── Run face detection & embedding ──
        faces = face_app.get(crop_img)

        if len(faces) == 0:
            # No face detected in the crop — skip silently
            continue

        face      = faces[0]
        embedding = face.embedding.tolist()

        # ── Search Milvus for existing match ──
        search_res = milvus_client.search(
            collection_name=COLLECTION_NAME,
            data=[embedding],
            limit=1,
            output_fields=["person_id"],
            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
        )

        # ── Threshold check (cosine similarity > 0.60 = known person) ──
        is_match  = False
        person_id = None

        if search_res and len(search_res[0]) > 0:
            top_match = search_res[0][0]
            if top_match['distance'] > 0.60:
                person_id = top_match['entity']['person_id']
                is_match  = True

        if not is_match:
            person_id = f"P_{int(time.time() * 1000)}"

        # ── Camera-specific dedup: skip if seen in last 30 seconds ──
        cache_key = f"seen_{cam_id}_{person_id}"
        if r.exists(cache_key):
            continue

        # ── Get (or create) this person's folder ──
        person_folder = get_person_folder(person_id)

        # ── Save face image into person's folder ──
        filename = f"{cam_id}_{int(timestamp)}.jpg"
        filepath = os.path.join(person_folder, filename)
        cv2.imwrite(filepath, crop_img)

        # ── Insert embedding into Milvus ──
        milvus_client.insert(
            collection_name=COLLECTION_NAME,
            data=[{"person_id": person_id, "embedding": embedding}]
        )

        # ── Insert sighting record into PostgreSQL ──
        # Store relative path so backend can serve it easily
        relative_path = f"/captured_faces/{person_id}/{filename}"
        pg_cursor.execute(
            "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) VALUES (%s, %s, %s, %s)",
            (person_id, cam_id, timestamp, relative_path)
        )

        # ── Mark this person as recently seen on this camera ──
        r.setex(cache_key, 30, "1")

        status = "MATCH ✅" if is_match else "NEW 🆕"
        print(f"[{cam_id}] 💾 {status}: {person_id} → saved to {person_folder}")

    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user.")
        break

    except Exception as e:
        error_msg = str(e)
        print(f"⚠️  Worker Error: {error_msg}")

        # ── Auto-recover if Milvus collection got unloaded mid-run ──
        if "collection not loaded" in error_msg:
            print("🔄 Milvus collection unloaded. Attempting reload...")
            try:
                milvus_client.load_collection(COLLECTION_NAME)
                print("✅ Collection reloaded successfully. Resuming...")
            except Exception as reload_err:
                print(f"❌ Failed to reload collection: {reload_err}")
                print("⏳ Waiting 5 seconds before retrying...")
                time.sleep(5)

        # ── Auto-recover lost PostgreSQL connection ──
        elif "connection" in error_msg.lower() and "postgres" in error_msg.lower():
            print("🔄 PostgreSQL connection lost. Reconnecting...")
            try:
                pg_conn = psycopg2.connect(
                    dbname="surveillance",
                    user="admin",
                    password="password",
                    host="localhost",
                    port="5432"
                )
                pg_conn.autocommit = True
                pg_cursor = pg_conn.cursor()
                print("✅ PostgreSQL reconnected.")
            except Exception as pg_err:
                print(f"❌ PostgreSQL reconnect failed: {pg_err}")
                time.sleep(5)

        else:
            time.sleep(0.1)

# ─────────────────────────────────────────
# 7. Cleanup on Exit
# ─────────────────────────────────────────

print("🧹 Cleaning up connections...")
pg_cursor.close()
pg_conn.close()
print("✅ Shutdown complete.")


## Kya Badla:

# **Folder structure** ab aisi hogi:
# ```
# captured_faces/
#     P_1743047823000/          ← Person 1 ka folder
#         cam1_1743047823.jpg
#         cam1_1743047900.jpg
#         cam2_1743047950.jpg
    
#     P_1743047999000/          ← Person 2 ka folder
#         cam1_1743047999.jpg
    
#     P_1743048100000/          ← Person 3 ka folder
#         cam2_1743048100.jpg
#         cam2_1743048200.jpg