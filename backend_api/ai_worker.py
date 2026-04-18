import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis
import psycopg2
from psycopg2.extras import RealDictCursor
from pymilvus import MilvusClient
import redis
import json
import time
import os

# ==========================================
# 1. CONFIGURATION & CONNECTIONS
# ==========================================
CAMERA_ID = "CAM-01 (Main Gate)"
# Use 0 for laptop webcam, or an RTSP URL like "rtsp://admin:pass@192.168.1.50/stream"
VIDEO_SOURCE = 0  

# Ensure the sightings folder exists for live captures
SIGHTINGS_FOLDER = os.path.join("captured_faces", "sightings")
os.makedirs(SIGHTINGS_FOLDER, exist_ok=True)

print("⏳ Initializing AI Models (This takes a few seconds)...")
face_app = FaceAnalysis(name='antelopev2', root='./models')
face_app.prepare(ctx_id=0, det_size=(640, 640)) # ctx_id=0 uses GPU if available, else CPU

print("⏳ Connecting to Databases...")
milvus_client = MilvusClient(uri="http://localhost:19530")
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def get_pg_connection():
    return psycopg2.connect(
        dbname="surveillance",
        user="admin", # Update with your DB user
        password="password", # Update with your DB password
        host="localhost",
        port="5432"
    )

# Cooldown dictionary to prevent spamming the frontend 30 times a second
alert_cooldowns = {}
COOLDOWN_SECONDS = 10 

# ==========================================
# 2. THE SURVEILLANCE LOOP
# ==========================================
print(f"🎥 Starting surveillance feed on {CAMERA_ID}...")
cap = cv2.VideoCapture(VIDEO_SOURCE)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera feed lost. Retrying...")
        time.sleep(1)
        cap = cv2.VideoCapture(VIDEO_SOURCE)
        continue

    # 1. Detect Faces in the live frame
    faces = face_app.get(frame)
    
    for face in faces:
        embedding = face.embedding.tolist()
        
        # 2. Search Milvus Watchlist Collection
        try:
            search_res = milvus_client.search(
                collection_name="watchlist_faces",
                data=[embedding],
                limit=1,
                output_fields=["watchlist_id"],
                search_params={"metric_type": "COSINE", "params": {"nprobe": 128}}
            )
        except Exception as e:
            print(f"Milvus Search Error: {e}")
            continue

        if not search_res or not search_res[0]:
            continue

        best_match = search_res[0][0]
        confidence = best_match['distance'] # Cosine similarity score
        subject_uuid = best_match['entity']['watchlist_id']

        # 3. Threshold Check (e.g., > 45% confidence for Cosine. Adjust based on your model)
        if confidence > 0.45:
            
            # 4. Spam Prevention (Cooldown Check)
            last_alert = alert_cooldowns.get(subject_uuid, 0)
            if time.time() - last_alert < COOLDOWN_SECONDS:
                continue # Skip if we just alerted about this person

            print(f"🚨 MATCH DETECTED! Subject: {subject_uuid} (Conf: {confidence:.2f})")
            
            # 5. Get Subject Dossier from PostgreSQL
            conn = get_pg_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT full_name, risk_level 
                FROM subjects 
                WHERE subject_uuid = %s
            """, (subject_uuid,))
            subject_data = cursor.fetchone()
            cursor.close(); conn.close()

            if not subject_data:
                continue # Orphaned Milvus record, skip

            # 6. Save the Live Frame for the UI
            timestamp = int(time.time() * 1000)
            live_filename = f"live_{subject_uuid}_{timestamp}.jpg"
            live_filepath = os.path.join(SIGHTINGS_FOLDER, live_filename)
            
            # Optional: Crop the face or save the full frame. We'll save the full frame for context.
            cv2.imwrite(live_filepath, frame)

            # 7. Construct the Contract Payload
            payload = {
                "status": "MATCH",
                "camera_id": CAMERA_ID,
                "person_id": subject_uuid,
                "full_name": subject_data['full_name'],
                "risk_level": subject_data['risk_level'],
                "confidence": confidence,
                "live_image": f"/images/sightings/{live_filename}",
                "reference_image": f"/images/watchlist/{subject_uuid}.jpg"
            }

            # 8. FIRE THE ALERT TO REDIS (FastAPI WebSocket picks this up)
            redis_client.publish("live_alerts", json.dumps(payload))
            
            # Update cooldown
            alert_cooldowns[subject_uuid] = time.time()

    # Press 'q' to stop the worker
    cv2.imshow("Surveillance AI Worker (Dev Mode)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()