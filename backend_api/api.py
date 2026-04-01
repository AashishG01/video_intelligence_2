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
from typing import Optional

# ==========================================
# SYSTEM SETUP
# ==========================================
app = FastAPI(title="C.O.R.E. Surveillance API", version="3.0 - Decoupled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount images EXACTLY as your frontend expects
SAVE_FOLDER = "../4_backend_api/captured_faces"
os.makedirs(SAVE_FOLDER, exist_ok=True)
app.mount("/images", StaticFiles(directory=SAVE_FOLDER), name="images")

# ==========================================
# INFRASTRUCTURE CONNECTIONS
# ==========================================
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

print("⏳ Connecting to Milvus Standalone...")
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "face_embeddings"

def get_pg_connection():
    return psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")

# ==========================================
# AI MODEL (STRICTLY FOR IMAGE SEARCH)
# ==========================================
print("⏳ Loading InsightFace (Upload Processor)...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_size=(640, 640))
print("✅ API Router Online.")

# ==========================================
# 1. LIVE VIDEO STREAMS (Sourced from Redis)
# ==========================================
def generate_mjpeg(cam_id):
    """Pulls the latest frame from Redis without blocking the AI workers."""
    while True:
        frame_b64 = r.get(f"latest_frame_{cam_id}")
        if not frame_b64:
            time.sleep(0.1)
            continue
            
        img_bytes = base64.b64decode(frame_b64)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')

@app.get("/api/stream/{cam_id}")
async def video_stream(cam_id: str):
    """Exact endpoint your React app uses for video feeds."""
    return StreamingResponse(
        generate_mjpeg(cam_id),
        media_type="multipart/x-mixed-replace;boundary=frame"
    )

# ==========================================
# 2. SYSTEM STATS (Sourced from Postgres)
# ==========================================
@app.get("/api/system/stats")
async def get_system_stats():
    """Matches your frontend's dashboard stats contract."""
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT COUNT(id) as total FROM sightings")
    total_records = cursor.fetchone()['total']
    
    if total_records == 0:
        return {"status": "ONLINE", "total_faces_captured": 0, "unique_suspects": 0, "active_cameras": 0, "camera_ids": [], "system_start_time": "Unknown"}

    cursor.execute("SELECT COUNT(DISTINCT person_id) as suspects FROM sightings")
    unique_suspects = cursor.fetchone()['suspects']
    
    cursor.execute("SELECT COUNT(DISTINCT camera_id) as cameras FROM sightings")
    active_cameras = cursor.fetchone()['cameras']
    
    cursor.execute("SELECT DISTINCT camera_id FROM sightings")
    camera_ids = [row['camera_id'] for row in cursor.fetchall()]
    
    cursor.execute("SELECT MIN(timestamp) as start_time FROM sightings")
    start_time = cursor.fetchone()['start_time']
    
    cursor.close()
    conn.close()

    return {
        "status": "ONLINE",
        "total_faces_captured": total_records,
        "unique_suspects": unique_suspects,
        "active_cameras": active_cameras,
        "camera_ids": camera_ids,
        "system_start_time": start_time
    }

# ==========================================
# 3. IMAGE SEARCH (Sourced from Milvus)
# ==========================================
@app.post("/api/investigate/search_by_image")
async def search_by_image(
    file: UploadFile = File(...),
    threshold: float = Query(0.60, description="Similarity threshold")
):
    """Matches your frontend's exact JSON return structure."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    faces = face_app.get(img)
    if not faces:
        raise HTTPException(status_code=404, detail="No face detected in uploaded image.")

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
        return {"message": "Database is empty.", "sightings": []}

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
                # We extract just the filename since React appends it to /images/
                filename = os.path.basename(record['image_path'])
                sightings.append({
                    "person_id": person_id,
                    "camera": record["camera_id"],
                    "timestamp": record["timestamp"],
                    "match_score": round(match['distance'], 4),
                    "image_url": f"/images/{filename}" 
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
# 4. PERSON DOSSIER (Sourced from Postgres)
# ==========================================
@app.get("/api/investigate/person/{person_id}")
async def get_person_dossier(person_id: str):
    """Matches the exact timeline tracker format your React UI requires."""
    conn = get_pg_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT camera_id, timestamp, image_path FROM sightings WHERE person_id = %s ORDER BY timestamp ASC", (person_id,))
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    if not records:
        raise HTTPException(status_code=404, detail="Person ID not found.")

    sightings = []
    for record in records:
        filename = os.path.basename(record['image_path'])
        sightings.append({
            "camera": record["camera_id"],
            "timestamp": record["timestamp"],
            "image_url": f"/images/{filename}"
        })

    return {
        "person_id": person_id,
        "total_sightings": len(sightings),
        "first_seen": sightings[0]["timestamp"],
        "last_seen": sightings[-1]["timestamp"],
        "locations": list(set(s["camera"] for s in sightings)),
        "timeline": sightings
    }

# ==========================================
# RUN
# uvicorn api:app --host 0.0.0.0 --port 8000 --reload
# ==========================================