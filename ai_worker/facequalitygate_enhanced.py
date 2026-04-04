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
# 1. CORE CONFIGURATION
# ─────────────────────────────────────────
CONFIDENCE_GATE   = 0.50   # Matches POC det_thresh spirit
MATCH_THRESHOLD   = 0.50   # Milvus cosine similarity
DEDUP_WINDOW_SEC  = 60     # Global dedup window per person (seconds)

# --- NIGHT ENHANCEMENT CONFIG ---
ENABLE_NIGHT_MODE  = True  
DARKNESS_THRESHOLD = 60    # If avg brightness is below this, frame is "dark"
NIGHT_UPSCALE      = 1.0   

# --- QUALITY GATE CONFIG ---
MIN_FACE_SIZE = 40         # Captures elevated camera faces
MIN_SHARPNESS = 60.0       # Less aggressive, captures slightly softer faces
MAX_POSE_SKEW = 0.35       # Allows more natural head angles

# ─────────────────────────────────────────
# 2. CONNECTIONS
# ─────────────────────────────────────────
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Connecting to PostgreSQL...")
pg_conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

print("⏳ Connecting to Milvus Standalone...")
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "face_embeddings"

def ensure_collection_loaded():
    if not milvus_client.has_collection(COLLECTION_NAME):
        print(f"⚠️  Collection '{COLLECTION_NAME}' not found. Creating...")
        milvus_client.create_collection(collection_name=COLLECTION_NAME, dimension=512, metric_type="COSINE", auto_id=True)
        print(f"✅ Collection '{COLLECTION_NAME}' created.")
    milvus_client.load_collection(COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' loaded into memory.")

ensure_collection_loaded()

SAVE_FOLDER = "../4_backend_api/captured_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)

def get_person_folder(person_id: str) -> str:
    folder = os.path.join(SAVE_FOLDER, person_id)
    os.makedirs(folder, exist_ok=True)
    return folder

# ─────────────────────────────────────────
# 3. NIGHT ENHANCEMENT PIPELINE
# ─────────────────────────────────────────
def is_dark(frame, threshold=60):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return np.mean(gray) < threshold

def enhance_night_frame(frame):
    frame = cv2.bilateralFilter(frame, d=7, sigmaColor=50, sigmaSpace=50)
    inv_gamma = 1.0 / 1.5
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
    frame = cv2.LUT(frame, table)
    
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    merged = cv2.merge((cl, a, b))
    frame = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    
    if NIGHT_UPSCALE != 1.0:
        frame = cv2.resize(frame, None, fx=NIGHT_UPSCALE, fy=NIGHT_UPSCALE, interpolation=cv2.INTER_LANCZOS4)
    return frame

# ─────────────────────────────────────────
# 4. QUALITY GATE FUNCTIONS (The Bouncers)
# ─────────────────────────────────────────
def is_front_facing(kps, skew_threshold=0.35):
    if kps is None or len(kps) < 5: return False
    le, re, nose, lm, rm = kps 

    # Yaw Check
    left_dist = nose[0] - le[0]
    right_dist = re[0] - nose[0]
    if left_dist <= 0 or right_dist <= 0: return False
    yaw_ratio = min(left_dist, right_dist) / max(left_dist, right_dist)

    if yaw_ratio < skew_threshold: return False 

    # Pitch Check
    eye_y = (le[1] + re[1]) / 2
    mouth_y = (lm[1] + rm[1]) / 2
    nose_to_eye = nose[1] - eye_y
    mouth_to_nose = mouth_y - nose[1]
    if nose_to_eye <= 0 or mouth_to_nose <= 0: return False
    pitch_ratio = min(nose_to_eye, mouth_to_nose) / max(nose_to_eye, mouth_to_nose)

    if pitch_ratio < (skew_threshold - 0.2): return False
    return True

def is_sharp(face_crop, threshold=60.0):
    if face_crop.size == 0: return False
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance >= threshold

# ─────────────────────────────────────────
# 5. INITIALIZE AI MODEL
# ─────────────────────────────────────────
print("⏳ Loading AntelopeV2 AI model...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
# Using 1024x1024 for the A6000
face_app.prepare(ctx_id=0, det_thresh=0.45, det_size=(1024, 1024))
print("✅ Face Worker Online. Awaiting frames...")

# ─────────────────────────────────────────
# 6. MAIN WORKER LOOP
# ─────────────────────────────────────────
while True:
    try:
        # Pull from queue
        queue_name, msg = r.brpop("face_ready_queue", timeout=0)
        payload   = json.loads(msg.decode('utf-8'))
        cam_id    = payload['camera_id']
        timestamp = payload['timestamp']

        # Decode frame
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None: continue

        # ── NIGHT ENHANCEMENT ──
        processed_frame = frame
        frame_is_dark = False
        if ENABLE_NIGHT_MODE:
            frame_is_dark = is_dark(frame, DARKNESS_THRESHOLD)
            if frame_is_dark:
                processed_frame = enhance_night_frame(frame)

        # ── INFERENCE ──
        faces = face_app.get(processed_frame)
        if len(faces) == 0: continue

        for face in faces:
            # --- GATE 0: CONFIDENCE ---
            if face.det_score < CONFIDENCE_GATE: continue

            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1

            # --- GATE 1: SIZE ---
            if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE: continue
            
            # --- GATE 2: POSE / ANGLE ---
            if not is_front_facing(face.kps, MAX_POSE_SKEW): continue

            # --- GATE 3: SHARPNESS / BLUR ---
            y1, y2 = max(0, y1), min(processed_frame.shape[0], y2)
            x1, x2 = max(0, x1), min(processed_frame.shape[1], x2)
            face_crop = processed_frame[y1:y2, x1:x2]
            
            # Dynamically adjust sharpness threshold for night frames
            current_sharp_thresh = MIN_SHARPNESS * 0.7 if frame_is_dark else MIN_SHARPNESS
            if not is_sharp(face_crop, current_sharp_thresh): continue

            # ==========================================
            # ✅ FACE PASSED ALL GATES. PROCEED TO EMBED
            # ==========================================
            embedding = face.embedding.tolist()
            is_match  = False
            person_id = None

            # ── MILVUS SEARCH ──
            search_res = milvus_client.search(
                collection_name=COLLECTION_NAME,
                data=[embedding],
                limit=1,
                output_fields=["person_id"],
                search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
            )

            if search_res and len(search_res[0]) > 0:
                top   = search_res[0][0]
                dist  = top['distance']
                if dist > MATCH_THRESHOLD:
                    person_id = top['entity']['person_id']
                    is_match  = True

            if not person_id:
                person_id = f"P_{int(time.time() * 1000)}"

            # ── GLOBAL DEDUP ──
            cache_key = f"seen_global_{person_id}"
            if r.exists(cache_key): continue

            # ── SAVE & INSERT ──
            person_folder = get_person_folder(person_id)
            filename  = f"{cam_id}_{int(timestamp)}.jpg"
            filepath  = os.path.join(person_folder, filename)
            cv2.imwrite(filepath, face_crop)

            milvus_client.insert(collection_name=COLLECTION_NAME, data=[{"person_id": person_id, "embedding": embedding}])
            milvus_client.flush(collection_name=COLLECTION_NAME)

            relative_path = f"/captured_faces/{person_id}/{filename}"
            pg_cursor.execute(
                "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) VALUES (%s, %s, %s, %s)",
                (person_id, cam_id, timestamp, relative_path)
            )

            r.setex(cache_key, DEDUP_WINDOW_SEC, "1")

            # ── PUBLISH WEBSOCKET ALERT ──
            r.publish("live_face_alerts", json.dumps({
                "person_id":  person_id,
                "camera_id":  cam_id,
                "timestamp":  timestamp,
                "image_path": relative_path,
                "confidence": round(float(face.det_score), 3),
                "status":     "MATCH" if is_match else "NEW"
            }))

            status = "MATCH ✅" if is_match else "NEW 🆕"
            print(f"[{cam_id}] 💾 {status}: {person_id} (conf: {face.det_score:.2f}) → {person_folder}")

    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user.")
        break
    
    # ── SELF-HEALING BLOCK ──
    except Exception as e:
        error_msg = str(e)
        print(f"⚠️  Worker Error: {error_msg}")

        # Auto-recover: Milvus collection unloaded
        if "collection not loaded" in error_msg:
            print("🔄 Milvus collection unloaded. Reloading...")
            try:
                milvus_client.load_collection(COLLECTION_NAME)
                print("✅ Collection reloaded. Resuming...")
            except Exception as reload_err:
                print(f"❌ Reload failed: {reload_err}")
                time.sleep(5)

        # Auto-recover: PostgreSQL connection lost
        elif "connection" in error_msg.lower() or "cursor" in error_msg.lower():
            print("🔄 PostgreSQL connection lost. Reconnecting...")
            try:
                pg_conn = psycopg2.connect(
                    dbname="surveillance", user="admin", password="password", host="localhost", port="5432"
                )
                pg_conn.autocommit = True
                pg_cursor = pg_conn.cursor()
                print("✅ PostgreSQL reconnected.")
            except Exception as pg_err:
                print(f"❌ Reconnect failed: {pg_err}")
                time.sleep(5)
        else:
            time.sleep(0.1)

print("🧹 Cleaning up connections...")
pg_cursor.close()
pg_conn.close()
print("✅ Shutdown complete.")