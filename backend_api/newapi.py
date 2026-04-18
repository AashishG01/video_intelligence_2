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
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from insightface.app import FaceAnalysis
from datetime import datetime
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from auth import verify_password, get_password_hash, create_access_token, get_current_user, require_admin
from pydantic import BaseModel as PydanticBaseModel
from typing import List, Optional # Add this to your imports
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, Form, Depends
import psycopg2

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
    name: str = Query("Unknown Suspect", description="Name of the suspect"),
    admin_user: dict = Depends(require_admin) # <-- ADD THIS LINE
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
async def remove_from_watchlist(
    watchlist_id: str,
    admin_user: dict = Depends(require_admin) # <-- ADD THIS LINE
):
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

class CategoryData(PydanticBaseModel):
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
               -- Aggregate categories into a JSON array for the frontend
               json_agg(json_build_object('name', c.name, 'color', c.color_code)) as categories,
               '/images/watchlist/' || s.subject_uuid || '.jpg' as image_url
        FROM subjects s
        JOIN watchlist_members wm ON s.id = wm.subject_id
        JOIN watchlist_categories c ON wm.category_id = c.id
        WHERE wm.is_active = TRUE
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


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
    milvus_client.flush(collection_name=WATCHLIST_COLLECTION)

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
            milvus_client.flush(collection_name=WATCHLIST_COLLECTION)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close(); conn.close()

    return {"status": "Subject Updated Successfully", "uuid": subject_uuid}

# Add this near your other endpoints in newapi.py
from pydantic import BaseModel

class SystemStatus(BaseModel):
    is_armed: bool

@app.get("/api/system/status")
async def get_system_status():
    # If key doesn't exist, assume system is Armed (True) by default
    status = redis_client.get("system_armed")
    if status is None:
        return {"is_armed": True}
    return {"is_armed": status.decode('utf-8') == "1"}

@app.post("/api/system/toggle")
async def toggle_system(status: SystemStatus, admin_user: dict = Depends(require_admin)):
    # Save as "1" for Armed, "0" for Disarmed
    redis_client.set("system_armed", "1" if status.is_armed else "0")
    return {"status": "System Armed" if status.is_armed else "System Disarmed", "is_armed": status.is_armed}

# ==========================================
# RUN
# uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload
# ==========================================