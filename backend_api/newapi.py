from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import cv2
import numpy as np
import redis
import base64
import time
import asyncio
import json
import psycopg2
import shutil
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from pymilvus import MilvusClient, connections, utility
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from insightface.app import FaceAnalysis
from datetime import datetime
from typing import List, Optional
from auth import verify_password, get_password_hash, create_access_token, get_current_user, require_admin
from contextlib import asynccontextmanager

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ==========================================
# 1. SYSTEM SETUP
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_db_check()
    yield

app = FastAPI(title="C.O.R.E. Surveillance API", version="3.1", lifespan=lifespan)

# Allow React frontend to communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⚠️ IMPORTANT: Folder Mounting for Images
SAVE_FOLDER = "captured_faces" 
os.makedirs(SAVE_FOLDER, exist_ok=True)

# 1. Mount the main Watchlist folder (from our earlier steps)
WATCHLIST_FOLDER = os.path.join(SAVE_FOLDER, "watchlist")
os.makedirs(WATCHLIST_FOLDER, exist_ok=True)
app.mount("/images/watchlist", StaticFiles(directory=WATCHLIST_FOLDER), name="watchlist_images")

# 2. Mount the new Sightings folder (for live camera captures)
SIGHTINGS_FOLDER = os.path.join(SAVE_FOLDER, "sightings")
os.makedirs(SIGHTINGS_FOLDER, exist_ok=True)
app.mount("/images/sightings", StaticFiles(directory=SIGHTINGS_FOLDER), name="sightings_images")

# 3. Mount the general images folder (Keep this last as a fallback)
app.mount("/images", StaticFiles(directory=SAVE_FOLDER), name="images")


# --- Add this right below your SIGHTINGS_FOLDER mount ---
AUDIO_FOLDER = "custom_audio"
os.makedirs(AUDIO_FOLDER, exist_ok=True)
app.mount("/audio", StaticFiles(directory=AUDIO_FOLDER), name="custom_audio")

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

# ==========================================
# PostgreSQL CONNECTION POOL
# ==========================================
# Opens a fixed pool of persistent connections at startup.
# Each request borrows one connection and returns it when done —
# no TCP handshake overhead per request, no risk of exhausting
# PostgreSQL's max_connections limit under concurrent load.
#
# minconn=2  — always keep 2 connections warm (instant availability)
# maxconn=10 — hard ceiling; requests block if all 10 are in use
#              rather than spawning unlimited raw connections.
#
# ⚠️ DB credentials below should also be moved to env vars
#    (see notes.md § Known Issues #5 / BUG-005 tracking item).
_PG_DSN = dict(
    dbname="surveillance",
    user="admin",
    password="password",
    host="localhost",
    port="5432",
)

print("⏳ Initialising PostgreSQL connection pool (2–10 connections)...")
_pg_pool = ThreadedConnectionPool(minconn=2, maxconn=10, **_PG_DSN)
print("✅ PostgreSQL pool ready.")

print("⏳ Loading InsightFace AI model for FastAPI Enrollment...")
# 🎯 Absolute Path Fix: Dynamically track the 'models' folder at the project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MODEL_ROOT = os.path.join(PROJECT_ROOT, "models")
face_app = FaceAnalysis(name='antelopev2', root=MODEL_ROOT, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_size=(640, 640))
print("✅ FastAPI InsightFace ready.")


class _PooledConn:
    """
    Thin wrapper around a psycopg2 connection borrowed from _pg_pool.

    Calling .close() on this object returns the connection to the pool
    rather than destroying it, so all existing `conn.close()` call sites
    throughout the file work correctly with zero modifications.

    Also supports the context-manager protocol:
        with get_pg_connection() as conn:
            cursor = conn.cursor()
            ...
    The connection is returned to the pool automatically on exit,
    with rollback on exception.
    """

    def __init__(self, conn):
        self._conn = conn

    # ── Core connection methods ──
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def close(self):
        """Return this connection to the pool (does NOT destroy it)."""
        _pg_pool.putconn(self._conn)

    # ── Context-manager support ──
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            try:
                self._conn.rollback()
            except Exception:
                pass
        self.close()
        return False  # do not suppress exceptions

    # ── Forward any other attribute access to the real connection ──
    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_pg_connection() -> _PooledConn:
    """Borrow a connection from the pool. Always call conn.close() when done."""
    return _PooledConn(_pg_pool.getconn())

# ==========================================
# 3. AI MODEL (FOR UPLOAD SEARCH ONLY)
# ==========================================
print("⏳ Loading InsightFace for Search API...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.10, det_size=(640, 640))
# face_app.prepare(ctx_id=0, det_thresh=0.45, det_size=(1024, 1024))
print("✅ API Router Online.")


# ==========================================
# AUTHENTICATION & RBAC ROUTES
# ==========================================
class UserCreate(BaseModel):
    username: str
    password: str
    role: str

@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s", (form_data.username,))
    user_record = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user_record or not verify_password(form_data.password, user_record['hashed_password']):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user_record['username'], "role": user_record['role']})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user_record['role']
    }

@app.post("/api/auth/register_operator")
async def create_operator(
    user_data: UserCreate, 
    admin_user: dict = Depends(require_admin) # 🛑 BOUNCER: Only Admins can hit this!
):
    if user_data.role not in ['admin', 'user']:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'user'.")
    
    hashed_pw = get_password_hash(user_data.password)
    
    try:
        conn = get_pg_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, hashed_password, role) VALUES (%s, %s, %s)", 
            (user_data.username, hashed_pw, user_data.role)
        )
        cursor.close()
        conn.close()
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")

    return {"message": f"Operator '{user_data.username}' successfully created."}

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
    finally:
        pubsub.unsubscribe()
        pubsub.close()

# ==========================================
# 5. LIVE VIDEO STREAM ROUTE
# ==========================================
async def generate_mjpeg(cam_id):
    """Pulls the latest frame from Redis for the UI."""
    while True:
        frame_b64 = r_bytes.get(f"latest_frame_{cam_id}")
        if not frame_b64:
            await asyncio.sleep(0.1)
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
    
    cursor.execute("SELECT COUNT(id) as cameras FROM cameras WHERE is_active = TRUE")
    active_cameras = cursor.fetchone()['cameras']
    
    cursor.execute("SELECT camera_id FROM cameras WHERE is_active = TRUE")
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

def startup_db_check():
    """Ensures that PostgreSQL tables and Milvus collections exist on startup."""
    print("⏳ Running Auto-Database Check...")
    
    # 1. PostgreSQL Check
    try:
        conn = get_pg_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cameras (
                id SERIAL PRIMARY KEY,
                camera_id VARCHAR(50) UNIQUE NOT NULL,
                camera_name VARCHAR(100) NOT NULL,
                place VARCHAR(100),
                rtsp_url TEXT NOT NULL,
                fps_limit INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sightings (
                id SERIAL PRIMARY KEY,
                person_id VARCHAR(100) NOT NULL,
                camera_id VARCHAR(50) NOT NULL,
                timestamp FLOAT NOT NULL,
                image_path TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_person_id ON sightings(person_id);")

        # Auto-migrate Latitude/Longitude columns if they don't exist
        try:
            cursor.execute("ALTER TABLE cameras ADD COLUMN latitude FLOAT;")
            cursor.execute("ALTER TABLE cameras ADD COLUMN longitude FLOAT;")
            print("✅ Auto-migrated cameras table (Added latitude/longitude).")
        except Exception:
            pass # Columns already exist

        # Auto-migrate NVR columns if they don't exist
        try:
            cursor.execute("ALTER TABLE cameras ALTER COLUMN rtsp_url DROP NOT NULL;")
            cursor.execute("ALTER TABLE cameras ADD COLUMN nvr_brand VARCHAR(50);")
            cursor.execute("ALTER TABLE cameras ADD COLUMN nvr_ip VARCHAR(50);")
            cursor.execute("ALTER TABLE cameras ADD COLUMN nvr_user VARCHAR(50);")
            cursor.execute("ALTER TABLE cameras ADD COLUMN nvr_pass VARCHAR(50);")
            cursor.execute("ALTER TABLE cameras ADD COLUMN nvr_channel INTEGER;")
            print("✅ Auto-migrated cameras table (Added NVR support).")
        except Exception:
            pass # Columns already exist

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_alerts (
                id SERIAL PRIMARY KEY,
                status VARCHAR(50),
                camera_id VARCHAR(50),
                person_id VARCHAR(100),
                timestamp FLOAT,
                live_image TEXT,
                confidence FLOAT,
                is_armed BOOLEAN,
                full_name VARCHAR(100),
                risk_level VARCHAR(50),
                reference_image TEXT
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_alerts_ts ON live_alerts(timestamp DESC);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_jobs (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(100) UNIQUE NOT NULL,
                camera_id VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'IN_PROGRESS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Legacy watchlist table removed to prevent Split-Brain Architecture
        
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

# Legacy /api/watchlist/* endpoints have been permanently deleted.
# The system now strictly uses the enterprise /api/subjects/* endpoints.

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
    except Exception as e:
        print(f"⚠️ Milvus search error: {e}")
        raise HTTPException(status_code=500, detail="Database search failed.")

    if not search_res or len(search_res[0]) == 0:
        return {"suspect_found": False, "total_sightings": 0, "sightings": []}

    sightings = []
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    for match in search_res[0]:
        # Convert UI Similarity % (e.g. 0.75) to Milvus Max Allowed Distance (0.25)
        max_allowed_distance = 1.0 - threshold
        if match['distance'] <= max_allowed_distance:
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
# 8.5 NVR TIME MACHINE SEARCH
# ==========================================
import uuid
import subprocess
from fastapi import BackgroundTasks

class NVRSearchRequest(BaseModel):
    camera_id: str
    start_time: int
    end_time: int

def run_nvr_historic_extraction(camera_id: str, start_time: int, end_time: int, session_id: str):
    script_path = os.path.join("..", "Ingestion", "producer_historic.py")
    subprocess.run([
        "python", script_path,
        "--camera_id", camera_id,
        "--start", str(start_time),
        "--end", str(end_time),
        "--session", session_id
    ])

@app.post("/api/investigate/nvr_search")
async def start_nvr_search(req: NVRSearchRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO historical_jobs (session_id, camera_id, status)
            VALUES (%s, %s, 'IN_PROGRESS')
        """, (session_id, req.camera_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

    background_tasks.add_task(run_nvr_historic_extraction, req.camera_id, req.start_time, req.end_time, session_id)
    return {"status": "success", "session_id": session_id}

@app.get("/api/investigate/status/{session_id}")
async def get_nvr_search_status(session_id: str):
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT status FROM historical_jobs WHERE session_id = %s", (session_id,))
    job = cursor.fetchone()
    cursor.close()
    conn.close()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": job['status']}


# ==========================================
# SUBJECTS & WATCHLIST CATEGORY ENDPOINTS
# ==========================================

@app.get("/api/watchlist/categories")
async def get_categories(current_user: dict = Depends(get_current_user)):
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, name, color_code, description FROM watchlist_categories ORDER BY id")
    cats = cursor.fetchall()
    cursor.close(); conn.close()
    return cats

class CategoryData(BaseModel):
    name: str
    color_code: str = "#3b82f6"
    description: str = ""

@app.post("/api/watchlist/categories/add")
async def add_category(cat: CategoryData, admin_user: dict = Depends(require_admin)):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO watchlist_categories (name, color_code, description)
            VALUES (%s, %s, %s) RETURNING id
        """, (cat.name, cat.color_code, cat.description))
        conn.commit()
        return {"status": "Category Created"}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail="A watchlist with this exact name already exists.")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close(); conn.close()

@app.delete("/api/watchlist/categories/remove/{cat_id}")
async def remove_category(cat_id: int, admin_user: dict = Depends(require_admin)):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        # Note: Because of ON DELETE CASCADE in our SQL schema, deleting a category 
        # will automatically remove the tags from any subjects assigned to it.
        cursor.execute("DELETE FROM watchlist_categories WHERE id = %s", (cat_id,))
        conn.commit()
        return {"status": "Category Removed"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close(); conn.close()

@app.get("/api/subjects/list")
async def list_subjects(current_user: dict = Depends(get_current_user)):
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT s.id, s.subject_uuid, s.full_name, s.age, s.gender,
               s.occupation, s.physical_description as description,
               s.risk_level, s.created_at,
               COALESCE(
                   json_agg(
                       json_build_object('name', c.name, 'color', c.color_code)
                   ) FILTER (WHERE c.id IS NOT NULL), 
                   '[]'
               ) as categories,
               '/images/watchlist/' || s.subject_uuid || '.jpg' as image_url
        FROM subjects s
        LEFT JOIN watchlist_members wm ON s.id = wm.subject_id AND wm.is_active = TRUE
        LEFT JOIN watchlist_categories c ON wm.category_id = c.id
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def flush_milvus_collection(collection_name: str):
    """Forces Milvus to flush memory buffers to the index for instant searchability."""
    try:
        connections.connect("default", uri="http://localhost:19530")
        utility.flush([collection_name])
        print(f"✅ Milvus Force-Flush Complete: {collection_name}")
    except Exception as e:
        print(f"⚠️ Warning: Milvus flush failed: {e}")

@app.post("/api/subjects/enroll")
async def enroll_subject(
    full_name: str = Form(...),          # Changed Query to Form
    age: int = Form(None),               # Changed Query to Form
    gender: str = Form("Unknown"),       # Changed Query to Form
    occupation: str = Form(None),        # Changed Query to Form
    category_ids: List[int] = Form(...), # Changed Query to Form
    risk_level: str = Form("Low"),       # Changed Query to Form
    description: str = Form(None),       # Changed Query to Form
    notes: str = Form(None),             # Changed Query to Form
    file: UploadFile = File(...),
    admin_user: dict = Depends(require_admin)
):
    # 1. AI Vectorization
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    faces = face_app.get(img)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in the uploaded image.")

    # Pick the largest detected face
    faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
    embedding = faces[0].embedding.tolist()

    subject_uuid = f"SUB_{int(time.time() * 1000)}"

    # 2. Save image to disk
    filename = f"{subject_uuid}.jpg"
    filepath = os.path.join(WATCHLIST_FOLDER, filename)
    cv2.imwrite(filepath, img)

    # 3. Insert vector into Milvus
    try:
        milvus_client.load_collection(WATCHLIST_COLLECTION)
    except Exception:
        pass
    milvus_client.insert(
        collection_name=WATCHLIST_COLLECTION,
        data=[{"watchlist_id": subject_uuid, "embedding": embedding}]
    )

    # 4. Insert into PostgreSQL
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        # Insert Subject Master Record (Once)
        cursor.execute("""
            INSERT INTO subjects (subject_uuid, full_name, age, gender, occupation, physical_description, risk_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (subject_uuid, full_name, age, gender, occupation, description, risk_level))
        new_id = cursor.fetchone()[0]

        # NEW: Loop through every category ID provided and link them
        for cat_id in category_ids:
            cursor.execute("""
                INSERT INTO watchlist_members (subject_id, category_id, added_by, notes)
                VALUES (%s, %s, %s, %s)
            """, (new_id, cat_id, admin_user['username'], notes))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close(); conn.close()

    # Absolute Synchronization: Flush to disk so AI Worker can search it instantly
    flush_milvus_collection(WATCHLIST_COLLECTION)

    return {"status": "Subject Enrolled in Multiple Lists", "uuid": subject_uuid}


@app.delete("/api/subjects/remove/{subject_uuid}")
async def remove_subject(subject_uuid: str, admin_user: dict = Depends(require_admin)):
    # Remove from Milvus
    try:
        milvus_client.load_collection(WATCHLIST_COLLECTION)
        milvus_client.delete(
            collection_name=WATCHLIST_COLLECTION,
            filter=f'watchlist_id == "{subject_uuid}"'
        )
    except Exception as e:
        print(f"Milvus delete warning: {e}")

    # Remove from PostgreSQL (cascade handles watchlist_members)
    conn = get_pg_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subjects WHERE subject_uuid = %s", (subject_uuid,))
    conn.commit()
    cursor.close(); conn.close()

    # Remove image from disk
    img_path = os.path.join(WATCHLIST_FOLDER, f"{subject_uuid}.jpg")
    if os.path.exists(img_path):
        os.remove(img_path)

    # Absolute Synchronization: Flush so AI Worker immediately stops matching
    flush_milvus_collection(WATCHLIST_COLLECTION)

    return {"status": "Subject Removed", "uuid": subject_uuid}

@app.put("/api/subjects/update/{subject_uuid}")
async def update_subject(
    subject_uuid: str,
    full_name: str = Form(...),
    age: int = Form(None),
    gender: str = Form("Unknown"),
    occupation: str = Form(None),
    category_ids: List[int] = Form(...),
    risk_level: str = Form("Low"),
    description: str = Form(None),
    notes: str = Form(None),
    file: Optional[UploadFile] = File(None), # Notice this is optional now!
    admin_user: dict = Depends(require_admin)
):
    conn = get_pg_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Update PostgreSQL Identity Data
        cursor.execute("""
            UPDATE subjects 
            SET full_name=%s, age=%s, gender=%s, occupation=%s, physical_description=%s, risk_level=%s
            WHERE subject_uuid=%s RETURNING id
        """, (full_name, age, gender, occupation, description, risk_level, subject_uuid))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subject not found")
        subject_id = row[0]

        # 2. Update Watchlist Categories (Delete old, Insert new)
        cursor.execute("DELETE FROM watchlist_members WHERE subject_id = %s", (subject_id,))
        for cat_id in category_ids:
            cursor.execute("""
                INSERT INTO watchlist_members (subject_id, category_id, added_by, notes)
                VALUES (%s, %s, %s, %s)
            """, (subject_id, cat_id, admin_user['username'], notes))

        # 3. Process New Image (Only if uploaded)
        if file:
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            faces = face_app.get(img)
            
            if not faces:
                raise HTTPException(status_code=400, detail="No face detected in new image.")
            
            # Save new image (overwrites old one)
            filepath = os.path.join(WATCHLIST_FOLDER, f"{subject_uuid}.jpg")
            cv2.imwrite(filepath, img)

            # Update Milvus (Delete old vector, Insert new)
            faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
            embedding = faces[0].embedding.tolist()
            
            milvus_client.load_collection(WATCHLIST_COLLECTION)
            milvus_client.delete(collection_name=WATCHLIST_COLLECTION, filter=f'watchlist_id == "{subject_uuid}"')
            milvus_client.insert(collection_name=WATCHLIST_COLLECTION, data=[{"watchlist_id": subject_uuid, "embedding": embedding}])

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close(); conn.close()

    # Absolute Synchronization: Flush to disk so AI Worker searches new photo instantly
    if file:
        flush_milvus_collection(WATCHLIST_COLLECTION)

    return {"status": "Subject Updated Successfully", "uuid": subject_uuid}

# Add this near your other endpoints in newapi.py
from pydantic import BaseModel

class SystemStatus(BaseModel):
    is_armed: bool

@app.get("/api/system/status")
async def get_system_status():
    # If key doesn't exist, assume system is Armed (True) by default
    status = r.get("system_armed")
    if status is None:
        return {"is_armed": True}
    if isinstance(status, bytes):
        status = status.decode('utf-8')
    return {"is_armed": status == "1"}

@app.post("/api/system/toggle")
async def toggle_system(status: SystemStatus, admin_user: dict = Depends(require_admin)):
    # Save as "1" for Armed, "0" for Disarmed
    r.set("system_armed", "1" if status.is_armed else "0")
    return {"status": "System Armed" if status.is_armed else "System Disarmed", "is_armed": status.is_armed}



from pydantic import BaseModel
from typing import List
import json

# ==========================================
# PYDANTIC MODELS FOR SETTINGS
# ==========================================
class AlertSettingsConfig(BaseModel):
    match_threshold: float
    alert_sound_type: str
    notify_emails: List[str]
    notify_phones: List[str]


# ==========================================
# GET: FETCH CURRENT SETTINGS
# ==========================================
@app.get("/api/settings/alerts")
def get_alert_settings():
    try:
        # ✅ Correctly opening DB connection
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT match_threshold, alert_sound_type, notify_emails, notify_phones FROM system_alert_settings WHERE id = 1"
        )
        row = cursor.fetchone()
        
        cursor.close()
        conn.close()

        if row:
            # 👈 FETCH CUSTOM AUDIO URL FROM REDIS (Fallback to default if not set)
            custom_audio_raw = r.get("GLOBAL_CUSTOM_AUDIO_URL")
            custom_audio_url = custom_audio_raw if custom_audio_raw else "/audio/custom_alert.mp3"
            
            return {
                "match_threshold": row[0],
                "alert_sound_type": row[1],
                "notify_emails": row[2] if isinstance(row[2], list) else json.loads(row[2]),
                "notify_phones": row[3] if isinstance(row[3], list) else json.loads(row[3]),
                "custom_audio_url": custom_audio_url # 👈 NEW LINE ADDED
            }
        return {"error": "Configuration not found"}
    except Exception as e:
        print(f"❌ Error fetching settings: {e}")
        return {"error": str(e)}

# ==========================================
# POST: UPDATE SETTINGS & SYNC TO REDIS
# ==========================================
@app.post("/api/settings/alerts")
def update_alert_settings(settings: AlertSettingsConfig):
    try:
        print(f"📥 Received settings from UI: {settings.dict()}")
        
        # 1. PEHLE REDIS UPDATE KARO (Taaki Worker turant chal jaye)
        try:
            r.set("GLOBAL_MATCH_THRESHOLD", settings.match_threshold)
            r.set("GLOBAL_ALERT_SOUND", settings.alert_sound_type)
            r.set("GLOBAL_NOTIFY_EMAILS", json.dumps(settings.notify_emails))
            r.set("GLOBAL_NOTIFY_PHONES", json.dumps(settings.notify_phones))
            print("✅ Redis Updated Successfully!")
        except Exception as redis_err:
            print(f"❌ Redis Update Failed: {redis_err}")
            raise HTTPException(status_code=500, detail="Failed to update cache settings")

        # 2. PHIR POSTGRES MEIN SAVE KARO (Permanent storage)
        try:
            # ✅ Correctly opening DB connection
            conn = get_pg_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO system_alert_settings (id, match_threshold, alert_sound_type, notify_emails, notify_phones, updated_at)
                VALUES (1, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET 
                    match_threshold = EXCLUDED.match_threshold,
                    alert_sound_type = EXCLUDED.alert_sound_type,
                    notify_emails = EXCLUDED.notify_emails,
                    notify_phones = EXCLUDED.notify_phones,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    settings.match_threshold, 
                    settings.alert_sound_type, 
                    json.dumps(settings.notify_emails), 
                    json.dumps(settings.notify_phones)
                )
            )
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Postgres Updated Successfully!")
        except Exception as pg_err:
            print(f"❌ Postgres Update Failed: {pg_err}")
            raise HTTPException(status_code=500, detail="Failed to update database settings")

        return {"message": "Configuration deployed successfully", "status": "success"}
    
    except HTTPException:
        # Let FastAPI handle these with the correct status code (e.g. 500)
        raise
    except Exception as e:
        print(f"❌ Critical API Error in Alert Settings: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
    
# ==========================================
# POST: UPLOAD CUSTOM AUDIO FILE
# ==========================================
# CAMERA MANAGEMENT APIs
# ==========================================
from pydantic import BaseModel, Field
import psycopg2
import requests as http_requests

MEDIAMTX_API = "http://localhost:9997"

import os
import yaml
import subprocess

def get_mediamtx_yml_path():
    """Dynamically get the absolute path to mediamtx.yml at the project root."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "mediamtx.yml")

def append_to_mediamtx_yml(camera_id: str, rtsp_url: str):
    """Fallback: Physically edits the mediamtx.yml file if the API is locked."""
    try:
        yml_path = get_mediamtx_yml_path()
        with open(yml_path, "r") as f:
            config = yaml.safe_load(f) or {}
            
        if "paths" not in config:
            config["paths"] = {}
            
        config["paths"][camera_id] = {
            "source": rtsp_url,
            "rtspTransport": "tcp",
            "sourceOnDemand": False
        }
        
        with open(yml_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
            
        print(f"✅ FILE SYNC: '{camera_id}' automatically written to mediamtx.yml!")
        print("🔄 Automating Docker Restart for core_mediamtx...")
        subprocess.run(["docker", "restart", "core_mediamtx"], check=False)
        print("✅ MediaMTX Restarted successfully.")
    except Exception as e:
        print(f"❌ FILE SYNC FAILED: Could not edit mediamtx.yml manually. Error: {e}")

def remove_from_mediamtx_yml(camera_id: str):
    """Fallback: Physically removes the camera from mediamtx.yml."""
    try:
        yml_path = get_mediamtx_yml_path()
        with open(yml_path, "r") as f:
            config = yaml.safe_load(f) or {}
            
        if "paths" in config and camera_id in config["paths"]:
            del config["paths"][camera_id]
            with open(yml_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)
            print(f"🗑️ FILE SYNC: '{camera_id}' removed from mediamtx.yml")
            print("🔄 Automating Docker Restart for core_mediamtx...")
            subprocess.run(["docker", "restart", "core_mediamtx"], check=False)
            print("✅ MediaMTX Restarted successfully.")
    except Exception as e:
        print(f"❌ FILE SYNC FAILED: Could not delete from mediamtx.yml manually. Error: {e}")

def sync_camera_to_mediamtx(camera_id: str, rtsp_url: str):
    """Tell MediaMTX to start routing this RTSP stream via WebRTC."""
    payload = {
        "source": rtsp_url,
        "rtspTransport": "tcp"
    }
    print(f"📡 Sending command to MediaMTX for '{camera_id}'...")
    try:
        res = http_requests.post(f"{MEDIAMTX_API}/v3/config/paths/{camera_id}", json=payload, timeout=3)
        if res.status_code == 200:
            print(f"✅ MediaMTX: Route created for '{camera_id}'")
            return
        elif res.status_code == 401:
            print("⚠️ API is locked (401). Falling back to direct file edit...")
            append_to_mediamtx_yml(camera_id, rtsp_url)
        else:
            print(f"❌ MediaMTX REJECTED! Code: {res.status_code}. Falling back to file edit...")
            append_to_mediamtx_yml(camera_id, rtsp_url)
    except Exception as e:
        print("⚠️ API Unreachable. Falling back to direct file edit...")
        append_to_mediamtx_yml(camera_id, rtsp_url)

def remove_camera_from_mediamtx(camera_id: str):
    """Tell MediaMTX to stop routing this camera's stream."""
    print(f"🗑️ Removing '{camera_id}' from MediaMTX...")
    try:
        res = http_requests.delete(f"{MEDIAMTX_API}/v3/config/paths/{camera_id}", timeout=3)
        if res.status_code == 200:
            print(f"✅ MediaMTX: Route deleted for '{camera_id}'")
        elif res.status_code == 401:
            print("⚠️ API is locked (401). Falling back to direct file edit...")
            remove_from_mediamtx_yml(camera_id)
        else:
            print(f"❌ MediaMTX delete failed! Code: {res.status_code}. Falling back to file edit...")
            remove_from_mediamtx_yml(camera_id)
    except Exception as e:
        print("⚠️ API Unreachable. Falling back to direct file edit...")
        remove_from_mediamtx_yml(camera_id)

class CameraConfig(BaseModel):
    camera_id: str
    camera_name: str
    place: str = ""
    rtsp_url: Optional[str] = None
    fps_limit: int = Field(default=1, ge=1, le=30, description="Frames per second limit (1-30)")
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    nvr_brand: Optional[str] = None
    nvr_ip: Optional[str] = None
    nvr_user: Optional[str] = None
    nvr_pass: Optional[str] = None
    nvr_channel: Optional[int] = None

@app.get("/api/cameras")
async def get_cameras():
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT id, camera_id, camera_name, place, rtsp_url, fps_limit, is_active, latitude, longitude, nvr_brand, nvr_ip, nvr_user, nvr_pass, nvr_channel FROM cameras ORDER BY created_at DESC")
        cameras = cursor.fetchall()
        
        # Cross-reference with MediaMTX to determine true stream health
        try:
            res = http_requests.get(f"{MEDIAMTX_API}/v3/paths/list", timeout=2)
            if res.status_code == 200:
                data = res.json()
                active_paths = {item.get("name") for item in data.get("items", []) if item.get("ready") == True}
                
                # Override DB flag with true live status
                for cam in cameras:
                    cam['is_active'] = cam['camera_id'] in active_paths
        except Exception as e:
            print(f"⚠️ Could not verify stream health from MediaMTX: {e}")
            
        return cameras
    finally:
        cursor.close()
        conn.close()

@app.post("/api/cameras/add")
async def add_camera(cam: CameraConfig, admin_user: dict = Depends(require_admin)):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        # We explicitly do NOT use ON CONFLICT DO UPDATE to prevent silent overwrites.
        cursor.execute("""
            INSERT INTO cameras (camera_id, camera_name, place, rtsp_url, fps_limit, is_active, latitude, longitude, nvr_brand, nvr_ip, nvr_user, nvr_pass, nvr_channel)
            VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s)
        """, (cam.camera_id, cam.camera_name, cam.place, cam.rtsp_url, cam.fps_limit, cam.latitude, cam.longitude, cam.nvr_brand, cam.nvr_ip, cam.nvr_user, cam.nvr_pass, cam.nvr_channel))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail="Camera ID already exists. Please use a unique ID or delete the existing one first.")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
    
    # Calculate effective RTSP URL for MediaMTX
    active_rtsp_url = cam.rtsp_url
    if not active_rtsp_url and cam.nvr_brand == 'uniview':
        import urllib.parse
        encoded_pass = urllib.parse.quote(cam.nvr_pass or "")
        active_rtsp_url = f"rtsp://{cam.nvr_user}:{encoded_pass}@{cam.nvr_ip}:554/unicast/c{cam.nvr_channel}/s1/live"
        
    # Dynamically program MediaMTX to start routing this RTSP stream
    if active_rtsp_url:
        sync_camera_to_mediamtx(cam.camera_id, active_rtsp_url)
    
    return {"status": "success", "message": "Camera enrolled and video route created"}

@app.put("/api/cameras/edit/{camera_id}")
async def edit_camera(camera_id: str, cam: CameraConfig, admin_user: dict = Depends(require_admin)):
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT rtsp_url FROM cameras WHERE camera_id = %s", (camera_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        old_rtsp = existing['rtsp_url']
        
        cursor.execute("""
            UPDATE cameras
            SET camera_name = %s, place = %s, rtsp_url = %s, fps_limit = %s, latitude = %s, longitude = %s, nvr_brand = %s, nvr_ip = %s, nvr_user = %s, nvr_pass = %s, nvr_channel = %s
            WHERE camera_id = %s
        """, (cam.camera_name, cam.place, cam.rtsp_url, cam.fps_limit, cam.latitude, cam.longitude, cam.nvr_brand, cam.nvr_ip, cam.nvr_user, cam.nvr_pass, cam.nvr_channel, camera_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
        
    # Calculate effective new RTSP URL for MediaMTX
    active_rtsp_url = cam.rtsp_url
    if not active_rtsp_url and cam.nvr_brand == 'uniview':
        import urllib.parse
        encoded_pass = urllib.parse.quote(cam.nvr_pass or "")
        active_rtsp_url = f"rtsp://{cam.nvr_user}:{encoded_pass}@{cam.nvr_ip}:554/unicast/c{cam.nvr_channel}/s1/live"

    # Only restart MediaMTX if the video stream URL actually changed
    old_active_rtsp_url = old_rtsp
    # Try to guess the old active rtsp url if it was an nvr. We might not have it in `existing`, but old_rtsp is what was stored in the db.
    # Actually, it's safer to always sync if there's a possibility it changed.
    # We will just sync it if active_rtsp_url is not None
    if active_rtsp_url:
        sync_camera_to_mediamtx(camera_id, active_rtsp_url)
        
    return {"status": "success", "message": "Camera updated successfully"}

@app.get("/api/alerts/recent")
async def get_recent_alerts():
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            SELECT status, camera_id, person_id, timestamp, live_image, confidence, is_armed, full_name, risk_level, reference_image 
            FROM live_alerts 
            WHERE status = 'WATCHLIST_MATCH'
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/cameras/remove/{camera_id}")
async def remove_camera(camera_id: str, admin_user: dict = Depends(require_admin)):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM cameras WHERE camera_id = %s", (camera_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    
    # Dynamically remove the route from MediaMTX
    remove_camera_from_mediamtx(camera_id)
    
    return {"status": "success", "message": f"Camera {camera_id} deleted and video route removed"}

# ==========================================
@app.post("/api/settings/upload_audio")
async def upload_custom_audio(file: UploadFile = File(...)):
    try:
        # Validate extension
        ext = file.filename.split('.')[-1].lower()
        if ext not in ['mp3', 'wav', 'ogg']:
            return {"error": "Invalid file format. Use MP3, WAV, or OGG."}

        # Clear old audio files to prevent storage bloat
        for old_file in os.listdir(AUDIO_FOLDER):
            if old_file.startswith("custom_alert"):
                os.remove(os.path.join(AUDIO_FOLDER, old_file))

        # Save new file
        file_path = os.path.join(AUDIO_FOLDER, f"custom_alert.{ext}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Save the path in Redis so Dashboard knows exactly what to fetch
        r.set("GLOBAL_CUSTOM_AUDIO_URL", f"/audio/custom_alert.{ext}")
        
        return {"status": "success", "url": f"/audio/custom_alert.{ext}"}
    except Exception as e:
        print(f"❌ Audio Upload Error: {e}")
        return {"error": "Failed to upload audio"}

# ==========================================
# RUN
# uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload
# ==========================================