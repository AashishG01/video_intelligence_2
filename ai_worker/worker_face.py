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
# CONFIGURATION — Tune these values
# ─────────────────────────────────────────
CONFIDENCE_GATE   = 0.75   # Min face detection confidence from InsightFace
# ⚠️  COSINE DISTANCE threshold — NOT a similarity score.
# Milvus COSINE distance: 0.0 = identical faces, 1.0 = completely different.
# A LOWER value = stricter matching (higher confidence a face belongs to a known person).
# 0.35 distance  ≈  65%+ cosine similarity  →  tight, production-safe default.
# The UI slider writes to Redis key GLOBAL_MATCH_THRESHOLD and overrides this at runtime.
MATCH_THRESHOLD   = 0.35   # DEFAULT Milvus Cosine DISTANCE threshold (overridden by Redis/UI)
DEDUP_WINDOW_SEC  = 60     # Global dedup window per person (seconds) to prevent spamming the DB

# ─────────────────────────────────────────
# 1. Connections
# ─────────────────────────────────────────
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)
# Dedicated publisher connection to prevent blocking
r_pub = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

print("⏳ Connecting to PostgreSQL...")
pg_conn = psycopg2.connect(
    dbname="surveillance",
    user="admin",        # Update with your actual DB credentials
    password="password", # Update with your actual DB credentials
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

    try:
        if milvus_client.has_collection(WATCHLIST_COLLECTION):
            milvus_client.load_collection(WATCHLIST_COLLECTION)
            print(f"✅ Collection '{WATCHLIST_COLLECTION}' loaded into memory.")
        else:
            print(f"⚠️  Watchlist collection not found. Make sure your FastAPI backend initialized it.")
    except Exception as wl_err:
        print(f"⚠️  Watchlist load warning: {wl_err}")

ensure_collection_loaded()

# ─────────────────────────────────────────
# 3. Setup Save Directory
# ─────────────────────────────────────────
SAVE_FOLDER = "../backend_api/captured_faces" 
os.makedirs(SAVE_FOLDER, exist_ok=True)

def get_person_folder(person_id: str) -> str:
    folder = os.path.join(SAVE_FOLDER, person_id)
    os.makedirs(folder, exist_ok=True)
    return folder

# ─────────────────────────────────────────
# 4. Initialize AI Model
# ─────────────────────────────────────────
print("⏳ Loading AntelopeV2 AI model...")
face_app = FaceAnalysis(
    name='antelopev2',
    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
)
# Worker needs high precision for live crowds
face_app.prepare(ctx_id=0, det_thresh=0.65, det_size=(1024, 1024))
print("✅ Face Worker Online. Awaiting frames from YOLO pre-filter...")

# ─────────────────────────────────────────
# 5. Main Worker Loop
# ─────────────────────────────────────────
while True:
    try:
        # 1. Pull from Redis Queue
        queue_name, msg = r.brpop("face_ready_queue", timeout=0)
        payload   = json.loads(msg.decode('utf-8'))
        cam_id    = payload['camera_id']
        timestamp = payload['timestamp']

        # 2. Decode full frame
        img_bytes = base64.b64decode(payload['frame_data'])
        np_arr    = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            continue

        # 3. Extract Faces
        faces = face_app.get(frame)
        if len(faces) == 0:
            continue

        # ==========================================================
        # 🎛️ DYNAMIC THRESHOLD SYNC
        # Fetch the latest threshold from Redis (set by React UI)
        # ==========================================================
        raw_thresh = r.get("GLOBAL_MATCH_THRESHOLD")
        CURRENT_MATCH_THRESHOLD = float(raw_thresh) if raw_thresh else MATCH_THRESHOLD

        for face in faces:
            # Drop low confidence faces (blurry, side profiles)
            if face.det_score < CONFIDENCE_GATE:
                continue

            embedding = face.embedding.tolist()

            # ==========================================================
            # 🎨 MARGIN CROPPING (Creates natural-looking UI captures)
            # ==========================================================
            x1, y1, x2, y2 = face.bbox.astype(int)
            w, h = x2 - x1, y2 - y1
            
            # Add 25% padding
            margin_x, margin_y = int(w * 0.25), int(h * 0.25)
            
            y1 = max(0, y1 - margin_y)
            y2 = min(frame.shape[0], y2 + margin_y)
            x1 = max(0, x1 - margin_x)
            x2 = min(frame.shape[1], x2 + margin_x)
            
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue
            # ==========================================================

            is_watchlist_match = False
            matched_watchlist_id = None
            matched_suspect_name = None
            matched_risk_level = "UNKNOWN"
            person_id = None
            final_match_distance = 1.0 # Default max distance

            # ────────────────────────────────────────────────────────
            # 🎯 STAGE 1: WATCHLIST HUNTING (Global "Always-On" Scan)
            # ────────────────────────────────────────────────────────
            if milvus_client.has_collection(WATCHLIST_COLLECTION):
                try:
                    # No Redis check anymore. We ALWAYS search the entire Watchlist collection.
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
                        
                        # ✅ USING DYNAMIC THRESHOLD FROM UI
                        # COSINE DISTANCE: match when dist is LOW (faces are similar).
                        # e.g. dist=0.20 means ~80% similar → strong watchlist hit.
                        if wl_dist < CURRENT_MATCH_THRESHOLD:  # dist < 0.35 by default
                            is_watchlist_match = True
                            matched_watchlist_id = wl_id
                            person_id = wl_id
                            final_match_distance = wl_dist
                            
                            # Fetch suspect real name & risk level from PostgreSQL
                            # NOTE: DB errors are intentionally NOT caught here — they
                            # must propagate to the outer loop's auto-recovery handler
                            # so that a dead PG connection triggers reconnection logic.
                            try:
                                pg_cursor.execute("SELECT full_name, risk_level FROM subjects WHERE subject_uuid = %s", (wl_id,))
                                row = pg_cursor.fetchone()
                                if row:
                                    matched_suspect_name = row[0]
                                    matched_risk_level = row[1]
                                else:
                                    # Subject deleted from Postgres but ghost remains in Milvus?
                                    matched_suspect_name = wl_id
                                    matched_risk_level = "UNKNOWN"
                            except Exception as db_err:
                                matched_suspect_name = wl_id
                                print(f"⚠️  Database Fetch Error: {db_err}")
                                raise  # Propagate past the watchlist handler for auto-recovery
                                
                            print(f"[{cam_id}] 🚨 WATCHLIST HIT: {matched_suspect_name} (Distance: {wl_dist:.4f} | Thresh: {CURRENT_MATCH_THRESHOLD})")
                except (psycopg2.Error, OSError) as db_propagated_err:
                    # DB/connection errors must NOT be swallowed — re-raise so the
                    # outer loop's self-healing block can reconnect to PostgreSQL.
                    raise
                except Exception as wl_err:
                    print(f"⚠️ Watchlist search error: {wl_err}")

            # ────────────────────────────────────────────────────────
            # 👥 STAGE 2: GENERAL DB SEARCH (If not a wanted suspect)
            # ────────────────────────────────────────────────────────
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
                        
                        # ✅ USING DYNAMIC THRESHOLD FROM UI
                        # COSINE DISTANCE: match when dist is LOW (faces are similar).
                        if dist < CURRENT_MATCH_THRESHOLD:  # dist < 0.35 by default
                            person_id = top['entity']['person_id']
                            is_match = True
                            final_match_distance = dist
                except Exception as search_err:
                    print(f"⚠️ Milvus search error: {search_err}")
                    continue

            # If completely new face, generate a new ID
            if not person_id:
                person_id = f"P_{int(time.time() * 1000)}"

            # ==========================================================
            # ⏱️ SPLIT ANTI-SPAM COOLDOWNS (DB vs Alerts)
            # ==========================================================
            system_status = r.get("system_armed")
            is_armed = system_status is None or system_status.decode('utf-8') == "1"

            # 1. DB Deduplication Lock (Always runs)
            # Prevents saving the same person's face to Postgres/Milvus 30 times a second.
            db_cooldown_key = f"db_cooldown_{person_id}"
            if r.exists(db_cooldown_key):
                continue 
            r.setex(db_cooldown_key, DEDUP_WINDOW_SEC, "1")

            # 2. Alert Deduplication Lock (Only locks if Armed)
            # If the system is Disarmed, we DON'T set the alert lock. 
            # This ensures that the very next frame after the Admin clicks "Arm System",
            # the system immediately triggers the red modal.
            alert_cooldown_key = f"alert_cooldown_{person_id}"
            if is_armed:
                if r.exists(alert_cooldown_key):
                    # We only skip the WS broadcast if the alert lock is active AND we are armed
                    pass
                else:
                    r.setex(alert_cooldown_key, DEDUP_WINDOW_SEC, "1")
            # ==========================================================

            # ── SAVE IMAGE TO DISK ──
            person_folder = get_person_folder(str(person_id))
            filename  = f"{cam_id}_{int(timestamp)}.jpg"
            filepath  = os.path.join(person_folder, filename)
            cv2.imwrite(filepath, face_crop)
            
            # Format path for React/FastAPI to serve (/images/...)
            relative_path = f"/images/{person_id}/{filename}"

            # ── SAVE TO DATABASE ──
            # Milvus: Only store non-watchlist people (watchlist is already stored in a separate collection)
            if not is_watchlist_match:
                milvus_client.insert(
                    collection_name=COLLECTION_NAME,
                    data=[{"person_id": person_id, "embedding": embedding}]
                )
                # Removed per-frame milvus_client.flush() to prevent severe performance bottlenecks

            # PostgreSQL: ALWAYS store the physical sighting (for timelines/investigation)
            db_path = f"/captured_faces/{person_id}/{filename}"
            pg_cursor.execute(
                "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) "
                "VALUES (%s, %s, %s, %s)",
                (person_id, cam_id, timestamp, db_path)
            )

            # ────────────────────────────────────────────────────────
            # 🚀 STAGE 3: PUSH TO REACT WEBSOCKETS
            # ────────────────────────────────────────────────────────
            ws_status = "NEW"
            if is_watchlist_match:
                ws_status = "WATCHLIST_MATCH"
            elif is_match:
                ws_status = "MATCH"

            # Convert Cosine Distance (0.0 to 1.0) into a Confidence % (1.0 to 0.0) for the UI
            ui_confidence = float(face.det_score) 
            if is_watchlist_match or is_match:
                ui_confidence = 1.0 - final_match_distance

            # ✅ STRICT API CONTRACT PAYLOAD FOR REACT 
            alert_payload = {
                "status": ws_status,  
                "camera_id": cam_id,
                "person_id": str(person_id),
                "timestamp": timestamp,
                "live_image": relative_path,
                "confidence": round(ui_confidence, 3),
                "is_armed": is_armed
            }
            
            if is_watchlist_match:
                alert_payload["full_name"] = matched_suspect_name 
                alert_payload["risk_level"] = matched_risk_level 
                alert_payload["reference_image"] = f"/images/watchlist/{matched_watchlist_id}.jpg" 

            # ALWAYS broadcast to React UI so the Sidebar "Live Intel Feed" keeps updating.
            # We ONLY broadcast if the alert lock wasn't already active for this person.
            if not is_armed or r.ttl(alert_cooldown_key) == DEDUP_WINDOW_SEC:
                r_pub.publish("live_face_alerts", json.dumps(alert_payload))
                
            if is_armed:
                if is_watchlist_match:
                    print(f"[{cam_id}] 🚨 ARMED WATCHLIST: {matched_suspect_name} ({matched_risk_level} RISK)")
                else:
                    status_log = "MATCH ✅" if is_match else "NEW 🆕"
                    print(f"[{cam_id}] 💾 ARMED {status_log}: {person_id} → {person_folder}")
            else:
                if is_watchlist_match:
                    print(f"[{cam_id}] 🔕 DISARMED WATCHLIST: {matched_suspect_name} (UI Silent)")
                else:
                    status_log = "🔕 DISARMED MATCH ✅" if is_match else "🔕 DISARMED NEW 🆕"
                    print(f"[{cam_id}] {status_log}: {person_id} → {person_folder}")

    except KeyboardInterrupt:
        print("\n🛑 Worker stopped by user.")
        break

    except Exception as e:
        error_msg = str(e)
        print(f"⚠️ Worker Error: {error_msg}")

        # Auto-recover
        if "collection not loaded" in error_msg:
            print("🔄 Milvus collection unloaded. Reloading...")
            try:
                milvus_client.load_collection(COLLECTION_NAME)
            except Exception:
                time.sleep(5)

        elif "connection" in error_msg.lower() or "cursor" in error_msg.lower():
            print("🔄 PostgreSQL connection lost. Reconnecting...")
            try:
                pg_conn = psycopg2.connect(
                    dbname="surveillance", user="admin", password="password", host="localhost", port="5432"
                )
                pg_conn.autocommit = True
                pg_cursor = pg_conn.cursor()
            except Exception:
                time.sleep(5)
        else:
            time.sleep(0.1)

print("🧹 Cleaning up connections...")
pg_cursor.close()
pg_conn.close()
r_pub.close()
print("✅ Shutdown complete.")