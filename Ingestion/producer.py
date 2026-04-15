import cv2
import threading
import time
import redis
import json
import base64
import os

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

if __name__ == "__main__":
    # Your exact 4 cameras
    cameras = {
        "cam1": "rtsp://admin:admin@172.16.0.151:554/live.sdp",
        "cam2": "rtsp://admin:admin@172.16.0.152:554/live.sdp",
        "cam3": "rtsp://admin:123456@172.16.0.161:554/live.sdp",
        "cam4": "rtsp://admin:Admin@123@172.16.0.162:554/live.sdp"
    }
    
    threads = []
    try:
        print("🟢 Starting Camera Ingestion Engine...")
        for cam_id, url in cameras.items():
            t = CameraProducer(cam_id, url, fps_limit=1)
            t.start()
            threads.append(t)
            
        print("✅ Producers online. Pushing frames to AI Queue and Web Feed. Press Ctrl+C to stop.")
        
        # Keep main thread alive and monitor the queue
        while True:
            queue_size = r.llen("raw_frames_queue")
            print(f"Current Redis AI Queue Size: {queue_size} frames waiting", end='\r')
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down producers gracefully...")
        for t in threads:
            t.running = False
        for t in threads:
            t.join()
        print("✅ Shutdown complete.")