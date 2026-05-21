import cv2
import threading
import time
import redis
import json
import base64
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# ==========================================
# SYSTEM OPTIMIZATIONS
# ==========================================
# Force TCP for RTSP to prevent UDP packet loss (Carried over from your POC)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Connect to local Redis
r = redis.Redis(host='localhost', port=6379, db=0)

class CameraProducer(threading.Thread):
    def __init__(self, camera_id, rtsp_url, fps_limit=1):
        threading.Thread.__init__(self)
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fps_limit = fps_limit
        self.running = True
        self.daemon = True # Allows thread to exit safely when main script is killed

    def run(self):
        print(f"[{self.camera_id}] ⏳ Connecting to stream...")
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        # Keep buffer tiny so we only grab the absolute freshest frame
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        while self.running:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                print(f"[{self.camera_id}] ⚠️ Stream dropped. Reconnecting in 5s...")
                cap.release()
                time.sleep(5)
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
                continue
            
            # --------------------------------------------------
            # TASK 1: Feed the AI Workers (High Quality, 720p)
            # --------------------------------------------------
            ai_frame = cv2.resize(frame, (1280, 720))
            _, ai_buffer = cv2.imencode('.jpg', ai_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            ai_base64 = base64.b64encode(ai_buffer).decode('utf-8')
            
            payload = {
                "camera_id": self.camera_id,
                "timestamp": time.time(),
                "frame_data": ai_base64
            }
            
            # Push to the AI queue
            r.lpush("raw_frames_queue", json.dumps(payload))
            # Prevent RAM explosion if AI crashes
            r.ltrim("raw_frames_queue", 0, 1000) 
            
            # TASK 2 (Web Feed) IS DELETED! 🚀 Frontend is handling it natively via WebRTC!
            
            # --------------------------------------------------
            # Enforce Indian Street Density FPS Limits (Tier 1 = 1 FPS)
            # --------------------------------------------------
            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self.fps_limit) - elapsed)
            time.sleep(sleep_time)

        cap.release()

def get_active_cameras():
    """Fetch active cameras from the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname="surveillance",
            user="admin",
            password="password",
            host="localhost",
            port="5432"
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT camera_id, rtsp_url, fps_limit FROM cameras WHERE is_active = TRUE")
        cameras = cursor.fetchall()
        cursor.close()
        conn.close()
        return {cam['camera_id']: cam for cam in cameras}
    except Exception as e:
        print(f"⚠️ Failed to fetch cameras from DB: {e}")
        return None

if __name__ == "__main__":
    active_threads = {}  # {camera_id: CameraProducer_Thread}
    
    try:
        print("🟢 Starting Dynamic Camera Ingestion Engine...")
        print("✅ Polling database for camera configurations...")
        
        # Keep main thread alive, monitor the queue, and sync cameras dynamically
        last_sync_time = 0
        SYNC_INTERVAL = 5  # Check DB every 5 seconds
        
        while True:
            current_time = time.time()
            
            # --- DYNAMIC CAMERA SYNC ---
            if current_time - last_sync_time >= SYNC_INTERVAL:
                db_cameras = get_active_cameras()
                
                if db_cameras is not None:
                    db_camera_ids = set(db_cameras.keys())
                    running_camera_ids = set(active_threads.keys())
                    
                    # 1. Start new cameras
                    for cam_id in db_camera_ids - running_camera_ids:
                        cam_info = db_cameras[cam_id]
                        print(f"\n🎥 [NEW CAMERA DETECTED] Starting {cam_id}...")
                        t = CameraProducer(cam_id, cam_info['rtsp_url'], fps_limit=cam_info['fps_limit'])
                        t.start()
                        active_threads[cam_id] = t
                        
                    # 2. Stop deleted/deactivated cameras
                    for cam_id in running_camera_ids - db_camera_ids:
                        print(f"\n🛑 [CAMERA REMOVED] Stopping {cam_id}...")
                        active_threads[cam_id].running = False
                        # We don't join() immediately to avoid blocking the sync loop
                        del active_threads[cam_id]
                        
                    # 3. Check for config changes (RTSP URL or FPS limit changed)
                    for cam_id in db_camera_ids.intersection(running_camera_ids):
                        cam_info = db_cameras[cam_id]
                        running_thread = active_threads[cam_id]
                        
                        if running_thread.rtsp_url != cam_info['rtsp_url'] or running_thread.fps_limit != cam_info['fps_limit']:
                            print(f"\n⚙️ [CONFIG CHANGED] Restarting {cam_id}...")
                            running_thread.running = False
                            
                            t = CameraProducer(cam_id, cam_info['rtsp_url'], fps_limit=cam_info['fps_limit'])
                            t.start()
                            active_threads[cam_id] = t
                            
                last_sync_time = current_time

            # --- MONITOR QUEUE ---
            queue_size = r.llen("raw_frames_queue")
            print(f"Current Redis AI Queue Size: {queue_size} frames waiting | Active Cameras: {len(active_threads)}", end='\r')
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down producers gracefully...")
        for t in active_threads.values():
            t.running = False
        for t in active_threads.values():
            t.join()
        print("✅ Shutdown complete.")