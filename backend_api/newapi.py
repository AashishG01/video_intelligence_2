import os
import cv2
import numpy as np
import redis
import base64
import time
import asyncio
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pymilvus import MilvusClient
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from insightface.app import FaceAnalysis
from datetime import datetime

# ==========================================
# 1. SYSTEM SETUP
# ==========================================
app = FastAPI(title="C.O.R.E. Surveillance API", version="3.1")

# Allow React frontend to communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⚠️ IMPORTANT: Folder Mounting for Images
# Agar tumhara API aur 'captured_faces' folder same jagah hain toh "captured_faces" likho.
# Agar folder ek step piche hai toh "../4_backend_api/captured_faces" likho.
SAVE_FOLDER = "captured_faces" 
os.makedirs(SAVE_FOLDER, exist_ok=True)
app.mount("/images", StaticFiles(directory=SAVE_FOLDER), name="images")

# ==========================================
# 2. INFRASTRUCTURE CONNECTIONS
# ==========================================
print("⏳ Connecting to Redis...")
# Do alag connections: text alerts ke liye (r), aur video frames ke liye (r_bytes)
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
r_bytes = redis.Redis(host='localhost', port=6379, db=0) 

print("⏳ Connecting to Milvus...")
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "face_embeddings"

def get_pg_connection():
    return psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")

# ==========================================
# 3. AI MODEL (FOR UPLOAD SEARCH ONLY)
# ==========================================
print("⏳ Loading InsightFace for Search API...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.10, det_size=(640, 640))
# face_app.prepare(ctx_id=0, det_thresh=0.45, det_size=(1024, 1024))
print("✅ API Router Online.")

# ==========================================
# 4. WEBSOCKET FOR REAL-TIME ALERTS
# ==========================================
@app.websocket("/ws/live_alerts")
async def live_alerts_websocket(websocket: WebSocket):
    """React frontend will connect here for real-time face pop-ups."""
    await websocket.accept()
    pubsub = r.pubsub()
    pubsub.subscribe("live_face_alerts")
    
    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                await websocket.send_text(message['data'])
            await asyncio.sleep(0.05) 
    except WebSocketDisconnect:
        print("Frontend disconnected from WebSocket.")
        pubsub.unsubscribe()

# ==========================================
# 5. LIVE VIDEO STREAM ROUTE
# ==========================================
def generate_mjpeg(cam_id):
    """Pulls the latest frame from Redis for the UI."""
    while True:
        frame_b64 = r_bytes.get(f"latest_frame_{cam_id}")
        if not frame_b64:
            time.sleep(0.1)
            continue
        img_bytes = base64.b64decode(frame_b64)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')

@app.get("/api/stream/{cam_id}")
async def video_stream(cam_id: str):
    """Endpoint for React <img src="..." /> to display live video."""
    return StreamingResponse(generate_mjpeg(cam_id), media_type="multipart/x-mixed-replace;boundary=frame")

# ==========================================
# 6. DASHBOARD STATISTICS
# ==========================================
@app.get("/api/system/stats")
async def get_system_stats():
    """Perfectly matches the React SystemStatusView variables."""
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT COUNT(id) as total FROM sightings")
    total_records = cursor.fetchone()['total']
    
    if total_records == 0:
        return {"status": "ONLINE", "total_faces_captured": 0, "unique_suspects": 0, "active_cameras": 0, "camera_ids": [], "system_start_time": "N/A"}

    cursor.execute("SELECT COUNT(DISTINCT person_id) as suspects FROM sightings")
    unique_suspects = cursor.fetchone()['suspects']
    
    cursor.execute("SELECT COUNT(DISTINCT camera_id) as cameras FROM sightings")
    active_cameras = cursor.fetchone()['cameras']
    
    cursor.execute("SELECT DISTINCT camera_id FROM sightings")
    camera_ids = [row['camera_id'] for row in cursor.fetchall()]
    
    cursor.execute("SELECT MIN(timestamp) as start_time FROM sightings")
    start_time_raw = cursor.fetchone()['start_time']
    # Format timestamp for UI
    start_time_str = datetime.fromtimestamp(start_time_raw).strftime("%Y-%m-%d %H:%M") if start_time_raw else "N/A"
    
    cursor.close()
    conn.close()

    return {
        "status": "ONLINE",
        "total_faces_captured": total_records,
        "unique_suspects": unique_suspects,
        "active_cameras": active_cameras,
        "camera_ids": camera_ids,
        "system_start_time": start_time_str
    }

@app.on_event("startup")
def startup_db_check():
    """Ensures that PostgreSQL tables and Milvus collections exist on startup."""
    print("⏳ Running Auto-Database Check...")
    
    # 1. PostgreSQL Check
    try:
        conn = get_pg_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sightings (
                id SERIAL PRIMARY KEY,
                person_id VARCHAR(100) NOT NULL,
                camera_id VARCHAR(50) NOT NULL,
                timestamp FLOAT NOT NULL,
                image_path TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON sightings(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_person_id ON sightings(person_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id SERIAL PRIMARY KEY,
                watchlist_id VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                image_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_id ON watchlist(watchlist_id);")
        
        cursor.close()
        conn.close()
        print("✅ PostgreSQL Tables Verified.")
    except Exception as e:
        print(f"⚠️ Warning: Auto-DB PostgreSQL Init failed: {e}")

    # 2. Milvus Check
    try:
        from pymilvus import DataType
        if not milvus_client.has_collection(COLLECTION_NAME):
            schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=False)
            schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
            schema.add_field(field_name="person_id", datatype=DataType.VARCHAR, max_length=100)
            schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)
            milvus_client.create_collection(collection_name=COLLECTION_NAME, schema=schema)
            
            index_params = milvus_client.prepare_index_params()
            index_params.add_index(field_name="embedding", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})
            milvus_client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
            print(f"✅ Created missing Milvus collection: {COLLECTION_NAME}")

        WATCHLIST_COLLECTION = "watchlist_faces"
        if not milvus_client.has_collection(WATCHLIST_COLLECTION):
            wl_schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=False)
            wl_schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
            wl_schema.add_field(field_name="watchlist_id", datatype=DataType.VARCHAR, max_length=100)
            wl_schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)
            milvus_client.create_collection(collection_name=WATCHLIST_COLLECTION, schema=wl_schema)
            
            wl_index = milvus_client.prepare_index_params()
            wl_index.add_index(field_name="embedding", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})
            milvus_client.create_index(collection_name=WATCHLIST_COLLECTION, index_params=wl_index)
            print(f"✅ Created missing Milvus collection: {WATCHLIST_COLLECTION}")
    except Exception as e:
         print(f"⚠️ Warning: Auto-DB Milvus Init failed: {e}")

# ==========================================
# 7. WATCHLIST MANAGEMENT (Enrollment + Activation)
# ==========================================
WATCHLIST_COLLECTION = "watchlist_faces"

# Save watchlist images in a subfolder
WATCHLIST_FOLDER = os.path.join(SAVE_FOLDER, "watchlist")
os.makedirs(WATCHLIST_FOLDER, exist_ok=True)

@app.post("/api/watchlist/add")
async def add_to_watchlist(
    file: UploadFile = File(...),
    name: str = Query("Unknown Suspect", description="Name of the suspect")
):
    """Enrolls a new suspect into the Watchlist (Milvus + PostgreSQL)."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    faces = face_app.get(img)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in uploaded image.")

    # Pick the largest face
    faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
    suspect_embedding = faces[0].embedding.tolist()

    watchlist_id = f"WL_{int(time.time() * 1000)}"
    filename = f"{watchlist_id}.jpg"
    filepath = os.path.join(WATCHLIST_FOLDER, filename)
    cv2.imwrite(filepath, img)

    # Insert embedding into Milvus watchlist collection
    try:
        milvus_client.load_collection(WATCHLIST_COLLECTION)
    except Exception:
        pass
    milvus_client.insert(
        collection_name=WATCHLIST_COLLECTION,
        data=[{"watchlist_id": watchlist_id, "embedding": suspect_embedding}]
    )
    milvus_client.flush(collection_name=WATCHLIST_COLLECTION)

    # Insert metadata into PostgreSQL
    conn = get_pg_connection()
    cursor = conn.cursor()
    image_path = f"/images/watchlist/{filename}"
    cursor.execute(
        "INSERT INTO watchlist (watchlist_id, name, image_path) VALUES (%s, %s, %s)",
        (watchlist_id, name, image_path)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "status": "Suspect Enrolled",
        "watchlist_id": watchlist_id,
        "name": name,
        "image_url": image_path
    }

@app.get("/api/watchlist/list")
async def list_watchlist():
    """Returns all enrolled suspects from the Watchlist."""
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT watchlist_id, name, image_path, created_at FROM watchlist ORDER BY created_at DESC")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    suspects = []
    for rec in records:
        suspects.append({
            "watchlist_id": rec["watchlist_id"],
            "name": rec["name"],
            "image_url": rec["image_path"],
            "created_at": str(rec["created_at"])
        })

    return {"total": len(suspects), "suspects": suspects}

@app.delete("/api/watchlist/remove/{watchlist_id}")
async def remove_from_watchlist(watchlist_id: str):
    """Removes a suspect from both Milvus and PostgreSQL."""
    # Remove from PostgreSQL
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE watchlist_id = %s", (watchlist_id,))
    conn.commit()
    cursor.close()
    conn.close()

    # Remove from Milvus
    try:
        milvus_client.load_collection(WATCHLIST_COLLECTION)
        milvus_client.delete(
            collection_name=WATCHLIST_COLLECTION,
            filter=f'watchlist_id == "{watchlist_id}"'
        )
    except Exception as e:
        print(f"⚠️ Milvus delete warning: {e}")

    # Deactivate if this ID was in the active list
    active_raw = r.get("ACTIVE_WATCHLIST")
    if active_raw:
        try:
            active_ids = json.loads(active_raw)
            if watchlist_id in active_ids:
                active_ids.remove(watchlist_id)
                r.set("ACTIVE_WATCHLIST", json.dumps(active_ids))
        except Exception:
            pass

    return {"status": "Suspect Removed", "watchlist_id": watchlist_id}

@app.post("/api/watchlist/activate")
async def activate_watchlist_search(ids: list[str]):
    """Writes the selected suspect IDs to Redis for the AI Worker to scan against."""
    r.set("ACTIVE_WATCHLIST", json.dumps(ids))
    return {"status": "Search Activated", "active_targets": ids, "count": len(ids)}

@app.delete("/api/watchlist/deactivate")
async def deactivate_watchlist_search():
    """Clears the active search."""
    r.delete("ACTIVE_WATCHLIST")
    return {"status": "Search Deactivated"}

# ==========================================
# 8. SEARCH BY IMAGE
# ==========================================
@app.post("/api/investigate/search_by_image")
async def search_by_image(
    file: UploadFile = File(...),
    threshold: float = Query(0.50, description="Similarity threshold")
):
    """Searches Milvus and formats the DB image paths correctly for the React UI."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    faces = face_app.get(img)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in the uploaded image.")

    suspect_embedding = faces[0].embedding.tolist()

    try:
        search_res = milvus_client.search(
            collection_name=COLLECTION_NAME,
            data=[suspect_embedding],
            limit=20,
            output_fields=["person_id"],
            search_params={"metric_type": "COSINE"}
        )
    except Exception:
        return {"suspect_found": False, "total_sightings": 0, "sightings": []}

    if not search_res or len(search_res[0]) == 0:
        return {"suspect_found": False, "total_sightings": 0, "sightings": []}

    sightings = []
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    for match in search_res[0]:
        if match['distance'] >= threshold:
            person_id = match['entity']['person_id']
            cursor.execute("SELECT camera_id, timestamp, image_path FROM sightings WHERE person_id = %s", (person_id,))
            pg_records = cursor.fetchall()
            
            for record in pg_records:
                # FIX APPLIED HERE: Format URL string to preserve P_XXX folder structure
                # DB gives us "/captured_faces/P_123/cam1.jpg"
                # We turn it into "/images/P_123/cam1.jpg" so React can find it
                formatted_image_url = record['image_path'].replace("/captured_faces/", "/images/")
                
                # Format timestamp
                readable_time = datetime.fromtimestamp(record['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                
                sightings.append({
                    "person_id": person_id,
                    "camera": record["camera_id"],
                    "timestamp": readable_time,
                    "match_score": round(match['distance'], 4),
                    "image_url": formatted_image_url
                })

    cursor.close()
    conn.close()
    sightings.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "suspect_found": len(sightings) > 0,
        "total_sightings": len(sightings),
        "sightings": sightings
    }

# ==========================================
# 8. DOSSIER / TIMELINE SEARCH
# ==========================================
@app.get("/api/investigate/person/{person_id}")
async def get_person_timeline(person_id: str):
    """Pulls Dossier and formats paths correctly for React UI Timeline."""
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT camera_id, timestamp, image_path FROM sightings WHERE person_id = %s ORDER BY timestamp ASC", 
        (person_id,)
    )
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        raise HTTPException(status_code=404, detail="Person ID not found.")

    timeline = []
    locations = set()
    
    for record in records:
        # FIX APPLIED HERE: Preserve P_XXX folder structure
        formatted_image_url = record['image_path'].replace("/captured_faces/", "/images/")
        
        readable_time = datetime.fromtimestamp(record['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
        locations.add(record["camera_id"])
        
        timeline.append({
            "camera": record["camera_id"],
            "timestamp": readable_time,
            "image_url": formatted_image_url
        })

    return {
        "person_id": person_id,
        "total_sightings": len(timeline),
        "first_seen": timeline[0]["timestamp"],
        "last_seen": timeline[-1]["timestamp"],
        "locations": list(locations),
        "timeline": timeline
    }

# ==========================================
# RUN
# uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload
# ==========================================