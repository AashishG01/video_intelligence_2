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
# CONFIGURATION — tune these values
# ─────────────────────────────────────────
CONFIDENCE_GATE   = 0.60   # min face detection confidence
MATCH_THRESHOLD   = 0.60   # milvus cosine similarity (VIP Strictness)
DEDUP_WINDOW_SEC  = 60     # global dedup window per person (seconds)

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
WATCHLIST_COLLECTION = "watchlist_faces"

# ─────────────────────────────────────────
# 2. Ensure Milvus Collections Exist & Loaded
# ─────────────────────────────────────────
def ensure_collection_loaded():
    if not milvus_client.has_collection(COLLECTION_NAME):
        print(f"⚠️  Collection '{COLLECTION_NAME}' not found. Creating...")
        milvus_client.create_collection(
            collection_name=COLLECTION_NAME,
            dimension=512,
            metric_type="COSINE",
            auto_id=True,
        )
        print(f"✅ Collection '{COLLECTION_NAME}' created.")
    milvus_client.load_collection(COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' loaded into memory.")

    # Also load watchlist collection
    try:
        if milvus_client.has_collection(WATCHLIST_COLLECTION):
            milvus_client.load_collection(WATCHLIST_COLLECTION)
            print(f"✅ Collection '{WATCHLIST_COLLECTION}' loaded into memory.")
        else:
            print(f"⚠️  Watchlist collection not found. Skipping (run init_db.py).")
    except Exception as wl_err:
        print(f"⚠️  Watchlist load warning: {wl_err}")

ensure_collection_loaded()

# ─────────────────────────────────────────
# 3. Setup Save Directory
# ─────────────────────────────────────────
SAVE_FOLDER = "../backend_api/captured_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# ─────────────────────────────────────────
# 4. Helper — Per-Person Subfolder
# ─────────────────────────────────────────
def get_person_folder(person_id: str) -> str:
    """
    Returns path to this person's subfolder, creating it if needed.
    """
    folder = os.path.join(SAVE_FOLDER, person_id)
    os.makedirs(folder, exist_ok=True)
    return folder

# ─────────────────────────────────────────
# 5. Initialize AI Model
# ─────────────────────────────────────────
print("⏳ Loading AntelopeV2 AI model...")
face_app = FaceAnalysis(
    name='antelopev2',
    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
)
# Worker is the "Guard" - Needs big eyes and strict rules
face_app.prepare(ctx_id=0, det_thresh=0.65, det_size=(1024, 1024))
print("✅ Face Worker Online. Awaiting frames...")

# ─────────────────────────────────────────
# 6. Main Worker Loop
# ─────────────────────────────────────────
while True:
    try:
        # Pull from face_ready_queue (full frames, YOLO pre-filtered)
        queue_name, msg = r.brpop("face_ready_queue", timeout=0)
        payload   = json.loads(msg.decode('utf-8'))
        cam_id    = payload['camera_id']
        timestamp = payload['timestamp']

        # Decode full frame
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            print(f"[{cam_id}] ⚠️  Failed to decode frame. Skipping.")
            continue

        # Run InsightFace on full frame — finds ALL faces in the scene
        faces = face_app.get(frame)

        if len(faces) == 0:
            continue

        for face in faces:

            # ── CONFIDENCE GATE ──
            if face.det_score < CONFIDENCE_GATE:
                continue

            embedding = face.embedding.tolist()

            # ==========================================================
            # 🚀 PRO LEVEL FIX: MARGIN CROPPING (No more "Creepy Masks")
            # ==========================================================
            x1, y1, x2, y2 = face.bbox.astype(int)
            
            w = x2 - x1
            h = y2 - y1
            
            # Add 25% padding around the face for context (hair, shoulders, background)
            margin_x = int(w * 0.25)
            margin_y = int(h * 0.25)
            
            # Boundary checks so crop doesn't go outside the image frame
            y1 = max(0, y1 - margin_y)
            y2 = min(frame.shape[0], y2 + margin_y)
            x1 = max(0, x1 - margin_x)
            x2 = min(frame.shape[1], x2 + margin_x)
            
            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size == 0:
                continue
            # ==========================================================

            # ── WATCHLIST MATCHING (Multi-Target) ──
            is_watchlist_match = False
            matched_watchlist_id = None
            matched_suspect_name = None
            person_id = None

            active_raw = r.get("ACTIVE_WATCHLIST")
            if active_raw:
                try:
                    active_ids = json.loads(active_raw.decode('utf-8') if isinstance(active_raw, bytes) else active_raw)
                    if len(active_ids) > 0 and milvus_client.has_collection(WATCHLIST_COLLECTION):
                        wl_results = milvus_client.search(
                            collection_name=WATCHLIST_COLLECTION,
                            data=[embedding],
                            limit=1,
                            output_fields=["watchlist_id"],
                            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
                        )
                        if wl_results and len(wl_results[0]) > 0:
                            top_wl = wl_results[0][0]
                            wl_dist = top_wl['distance']
                            wl_id = top_wl['entity']['watchlist_id']
                            # Only alert if this ID is in the active search list AND above threshold
                            if wl_dist > MATCH_THRESHOLD and wl_id in active_ids:
                                is_watchlist_match = True
                                matched_watchlist_id = wl_id
                                person_id = wl_id
                                # Fetch suspect name from PostgreSQL
                                try:
                                    pg_cursor.execute("SELECT name FROM watchlist WHERE watchlist_id = %s", (wl_id,))
                                    row = pg_cursor.fetchone()
                                    matched_suspect_name = row[0] if row else wl_id
                                except Exception:
                                    matched_suspect_name = wl_id
                                print(f"[{cam_id}] 🎯 WATCHLIST HIT: {matched_suspect_name} (sim: {wl_dist:.4f})")
                except Exception as wl_err:
                    print(f"⚠️  Watchlist search error: {wl_err}")

            # ── Milvus general similarity search (only if no watchlist match) ──
            is_match = False

            if not is_watchlist_match:
                try:
                    search_res = milvus_client.search(
                        collection_name=COLLECTION_NAME,
                        data=[embedding],
                        limit=1,
                        output_fields=["person_id"],
                        search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
                    )
                    if search_res and len(search_res[0]) > 0:
                        top  = search_res[0][0]
                        dist = top['distance']
                        if dist > MATCH_THRESHOLD:
                            person_id = top['entity']['person_id']
                            is_match = True
                except Exception as search_err:
                    print(f"⚠️  Milvus search error: {search_err}")
                    continue

            if not person_id:
                person_id = f"P_{int(time.time() * 1000)}"

            # ── WATCHLIST_MATCH: Skip dedup so alarm ALWAYS fires ──
            if not is_watchlist_match:
                cache_key = f"seen_global_{person_id}"
                if r.exists(cache_key):
                    continue

            # ── Get or create person's subfolder ──
            person_folder = get_person_folder(str(person_id))

            # ── Save face crop ──
            filename  = f"{cam_id}_{int(timestamp)}.jpg"
            filepath  = os.path.join(person_folder, filename)
            cv2.imwrite(filepath, face_crop)

            relative_path = f"/captured_faces/{person_id}/{filename}"

            # ── For regular faces: Insert into DB. Watchlist matches skip DB pollution ──
            if not is_watchlist_match:
                milvus_client.insert(
                    collection_name=COLLECTION_NAME,
                    data=[{"person_id": person_id, "embedding": embedding}]
                )
                milvus_client.flush(collection_name=COLLECTION_NAME)

                pg_cursor.execute(
                    "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) "
                    "VALUES (%s, %s, %s, %s)",
                    (person_id, cam_id, timestamp, relative_path)
                )
                cache_key = f"seen_global_{person_id}"
                r.setex(cache_key, DEDUP_WINDOW_SEC, "1")

            # ── Publish real-time alert to dashboard ──
            r_pub = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

            ws_status = "NEW"
            if is_watchlist_match:
                ws_status = "WATCHLIST_MATCH"
            elif is_match:
                ws_status = "MATCH"

            alert_payload = {
                "person_id":  str(person_id),
                "camera_id":  cam_id,
                "timestamp":  timestamp,
                "image_path": relative_path,
                "confidence": round(float(face.det_score), 3),
                "status":     ws_status
            }
            if is_watchlist_match:
                alert_payload["suspect_name"] = matched_suspect_name
                alert_payload["watchlist_id"] = matched_watchlist_id

            r_pub.publish("live_face_alerts", json.dumps(alert_payload))
            r_pub.close()

            if is_watchlist_match:
                status_log = f"🚨 WATCHLIST: {matched_suspect_name}"
            else:
                status_log = "MATCH ✅" if is_match else "NEW 🆕"

            print(f"[{cam_id}] 💾 {status_log}: {person_id} "
                  f"(conf: {face.det_score:.2f}) → {person_folder}")

    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user.")
        break

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
        elif "connection" in error_msg.lower():
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
                print(f"❌ Reconnect failed: {pg_err}")
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