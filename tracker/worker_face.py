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
CONFIDENCE_GATE   = 0.50   
MATCH_THRESHOLD   = 0.50   
DEDUP_WINDOW_SEC  = 60     

# --- NIGHT ENHANCEMENT CONFIG ---
ENABLE_NIGHT_MODE  = True  
DARKNESS_THRESHOLD = 60    
NIGHT_UPSCALE      = 1.0   

# --- QUALITY GATE CONFIG ---
MIN_FACE_SIZE = 40         
MIN_SHARPNESS = 60.0       
MAX_POSE_SKEW = 0.35       

# --- BYTETRACK BUFFER CONFIG ---
TRACK_TIMEOUT_SEC = 3.0    # Flush to DB if person is unseen for 3 seconds
active_tracks = {}         # The "Waiting Room" RAM Buffer

# ─────────────────────────────────────────
# 2. CONNECTIONS
# ─────────────────────────────────────────
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)

print("⏳ Connecting to PostgreSQL...")
pg_conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

print("⏳ Connecting to Milvus...")
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "face_embeddings"

if not milvus_client.has_collection(COLLECTION_NAME):
    milvus_client.create_collection(collection_name=COLLECTION_NAME, dimension=512, metric_type="COSINE", auto_id=True)
milvus_client.load_collection(COLLECTION_NAME)

SAVE_FOLDER = "../4_backend_api/captured_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# ─────────────────────────────────────────
# 3. HELPER FUNCTIONS
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

def is_front_facing(kps, skew_threshold=0.35):
    if kps is None or len(kps) < 5: return False
    le, re, nose, lm, rm = kps 
    left_dist, right_dist = nose[0] - le[0], re[0] - nose[0]
    if left_dist <= 0 or right_dist <= 0: return False
    if min(left_dist, right_dist) / max(left_dist, right_dist) < skew_threshold: return False 
    eye_y, mouth_y = (le[1] + re[1]) / 2, (lm[1] + rm[1]) / 2
    nose_to_eye, mouth_to_nose = nose[1] - eye_y, mouth_y - nose[1]
    if nose_to_eye <= 0 or mouth_to_nose <= 0: return False
    if min(nose_to_eye, mouth_to_nose) / max(nose_to_eye, mouth_to_nose) < (skew_threshold - 0.2): return False
    return True

def get_track_id_for_face(face_bbox, tracked_persons):
    """Finds which YOLO person box contains this InsightFace face box."""
    fx1, fy1, fx2, fy2 = face_bbox
    face_center_x = (fx1 + fx2) / 2
    face_center_y = (fy1 + fy2) / 2
    for person in tracked_persons:
        px1, py1, px2, py2 = person['bbox']
        if px1 <= face_center_x <= px2 and py1 <= face_center_y <= py2:
            return person['track_id']
    return None

# ─────────────────────────────────────────
# 4. DATABASE FLUSH PIPELINE (Called on Timeout)
# ─────────────────────────────────────────
def flush_track_to_database(track_data):
    """Saves the absolute best face from the buffer into the database."""
    global pg_cursor, pg_conn, milvus_client, r
    
    embedding = track_data['embedding']
    cam_id    = track_data['cam_id']
    timestamp = track_data['timestamp']
    face_crop = track_data['face_crop']
    det_score = track_data['det_score']

    is_match  = False
    person_id = None

    # 1. Search Milvus
    search_res = milvus_client.search(
        collection_name=COLLECTION_NAME, data=[embedding], limit=1, output_fields=["person_id"],
        search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
    )
    if search_res and len(search_res[0]) > 0:
        top = search_res[0][0]
        if top['distance'] > MATCH_THRESHOLD:
            person_id = top['entity']['person_id']
            is_match  = True

    if not person_id:
        person_id = f"P_{int(time.time() * 1000)}"

    # 2. Redis Dedup Check
    cache_key = f"seen_global_{person_id}"
    if r.exists(cache_key): return

    # 3. Save Image
    person_folder = os.path.join(SAVE_FOLDER, person_id)
    os.makedirs(person_folder, exist_ok=True)
    filename  = f"{cam_id}_{int(timestamp)}.jpg"
    filepath  = os.path.join(person_folder, filename)
    cv2.imwrite(filepath, face_crop)

    # 4. Insert Milvus
    milvus_client.insert(collection_name=COLLECTION_NAME, data=[{"person_id": person_id, "embedding": embedding}])
    milvus_client.flush(collection_name=COLLECTION_NAME)

    # 5. Insert Postgres
    relative_path = f"/captured_faces/{person_id}/{filename}"
    pg_cursor.execute(
        "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) VALUES (%s, %s, %s, %s)",
        (person_id, cam_id, timestamp, relative_path)
    )

    # 6. Set Dedup & Publish
    r.setex(cache_key, DEDUP_WINDOW_SEC, "1")
    r.publish("live_face_alerts", json.dumps({
        "person_id":  person_id,
        "camera_id":  cam_id,
        "timestamp":  timestamp,
        "image_path": relative_path,
        "confidence": round(float(det_score), 3),
        "status":     "MATCH" if is_match else "NEW"
    }))

    status = "MATCH ✅" if is_match else "NEW 🆕"
    print(f"[{cam_id}] 💾 FLUSHED {status}: {person_id} (Best Score: {track_data['score']:.0f})")

# ─────────────────────────────────────────
# 5. INITIALIZE AI MODEL
# ─────────────────────────────────────────
print("⏳ Loading AntelopeV2 AI model...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.45, det_size=(1024, 1024))
print("✅ Face Worker Online. Awaiting tracked frames...")

# ─────────────────────────────────────────
# 6. MAIN WORKER LOOP
# ─────────────────────────────────────────
while True:
    try:
        # Pull from queue
        queue_name, msg = r.brpop("face_ready_queue", timeout=1)
        
        # If queue is empty, still check for timeouts, then loop
        if msg:
            payload   = json.loads(msg.decode('utf-8'))
            cam_id    = payload['camera_id']
            timestamp = payload['timestamp']
            tracked_persons = payload.get('tracked_persons', [])

            img_bytes = base64.b64decode(payload['frame_data'])
            np_arr    = np.frombuffer(img_bytes, np.uint8)
            frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is not None:
                # ── NIGHT ENHANCEMENT ──
                processed_frame = frame
                frame_is_dark = False
                if ENABLE_NIGHT_MODE:
                    frame_is_dark = is_dark(frame, DARKNESS_THRESHOLD)
                    if frame_is_dark:
                        processed_frame = enhance_night_frame(frame)

                # ── INFERENCE ──
                faces = face_app.get(processed_frame)
                
                for face in faces:
                    if face.det_score < CONFIDENCE_GATE: continue

                    x1, y1, x2, y2 = face.bbox.astype(int)
                    w, h = x2 - x1, y2 - y1
                    if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE: continue
                    if not is_front_facing(face.kps, MAX_POSE_SKEW): continue

                    y1, y2 = max(0, y1), min(processed_frame.shape[0], y2)
                    x1, x2 = max(0, x1), min(processed_frame.shape[1], x2)
                    face_crop = processed_frame[y1:y2, x1:x2]
                    
                    # Calculate Sharpness Variance
                    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
                    
                    current_sharp_thresh = MIN_SHARPNESS * 0.7 if frame_is_dark else MIN_SHARPNESS
                    if variance < current_sharp_thresh: continue

                    # ── TRACK ASSOCIATION ──
                    track_id = get_track_id_for_face(face.bbox, tracked_persons)
                    
                    if track_id is not None:
                        # Combine confidence and sharpness for a total quality score
                        quality_score = face.det_score * variance
                        global_track_id = f"{cam_id}_{track_id}"
                        
                        # ── BUFFER UPDATE LOGIC ──
                        if global_track_id not in active_tracks or quality_score > active_tracks[global_track_id]['score']:
                            # New track OR better face found!
                            active_tracks[global_track_id] = {
                                "score": quality_score,
                                "embedding": face.embedding.tolist(),
                                "face_crop": face_crop.copy(),
                                "last_seen": time.time(),
                                "timestamp": timestamp,
                                "cam_id": cam_id,
                                "det_score": face.det_score
                            }
                        else:
                            # Face was worse, just keep the track alive
                            active_tracks[global_track_id]['last_seen'] = time.time()

        # ==========================================
        # ── THE FLUSH CHECK ── (Runs every loop)
        # ==========================================
        current_time = time.time()
        expired_tracks = []

        # Find tracks that haven't been seen in 3 seconds
        for gid, data in active_tracks.items():
            if current_time - data['last_seen'] > TRACK_TIMEOUT_SEC:
                expired_tracks.append(gid)

        # Flush them to Milvus/Postgres
        for gid in expired_tracks:
            flush_track_to_database(active_tracks[gid])
            del active_tracks[gid]

    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user.")
        break
    
    # ── SELF-HEALING BLOCK ──
    except Exception as e:
        error_msg = str(e)
        print(f"⚠️  Worker Error: {error_msg}")
        if "collection not loaded" in error_msg:
            try: milvus_client.load_collection(COLLECTION_NAME)
            except: time.sleep(5)
        elif "connection" in error_msg.lower() or "cursor" in error_msg.lower():
            try:
                pg_conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
                pg_conn.autocommit = True
                pg_cursor = pg_conn.cursor()
            except: time.sleep(5)
        else:
            time.sleep(0.1)

print("🧹 Cleaning up connections...")
pg_cursor.close()
pg_conn.close()
print("✅ Shutdown complete.")