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

# ==========================================
# 7. LIVE TARGET MANAGEMENT
# ==========================================
@app.post("/api/target/set")
async def set_live_target(file: UploadFile = File(...)):
    """Sets the given image as the active live target in Redis for instant worker matching."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    faces = face_app.get(img)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in target image.")

    # Sort faces by bounding box area to get the largest prominent face
    faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
    target_embedding = faces[0].embedding.tolist()

    target_id = f"TARGET_{int(time.time())}"
    filename = f"{target_id}.jpg"
    
    # Save directly to images folder for UI rendering
    filepath = os.path.join(SAVE_FOLDER, filename)
    cv2.imwrite(filepath, img)

    # Register in Redis for the Python Worker `worker_face.py` to instantly check
    r.set("LIVE_TARGET_EMBEDDING", json.dumps(target_embedding))
    r.set("LIVE_TARGET_IMAGE", f"/images/{filename}")
    r.set("LIVE_TARGET_ID", target_id)

    return {
        "status": "Target Set", 
        "target_id": target_id,
        "target_image": f"/images/{filename}"
    }

@app.delete("/api/target/clear")
async def clear_live_target():
    """Removes the active live target."""
    r.delete("LIVE_TARGET_EMBEDDING")
    r.delete("LIVE_TARGET_IMAGE")
    r.delete("LIVE_TARGET_ID")
    return {"status": "Target Cleared"}

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