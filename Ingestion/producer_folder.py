import os
import cv2
import threading
import time
import redis
import json
import base64
import math

# Connect to local Redis
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0)

class VideoFileProducer(threading.Thread):
    def __init__(self, filepath, process_every_n_seconds=1):
        """
        process_every_n_seconds: Agar 1 hai, toh har 1 second ke video mein se 1 frame uthayega.
        Baaki ke frames ko super-fast skip kar dega bina CPU/RAM par load dale.
        """
        threading.Thread.__init__(self)
        self.filepath = filepath
        
        # --- THE SAFETY CATCH ---
        # Extract filename, replace spaces, and force a max length of 45 characters.
        # This absolutely guarantees it will never crash the Postgres VARCHAR(50) limit.
        raw_name = os.path.splitext(os.path.basename(filepath))[0].replace(" ", "_")
        self.camera_id = raw_name[:45] 
        
        self.process_every_n_seconds = process_every_n_seconds
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.filepath)
        
        # 1. Get the actual FPS of the video
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Fallback if OpenCV fails to read FPS
        if video_fps <= 0 or math.isnan(video_fps): 
            video_fps = 25.0 
            
        frames_to_skip = int(video_fps * self.process_every_n_seconds)
        
        print(f"[{self.camera_id}] 🎬 Starting Full-Speed Ingestion...")
        print(f"[{self.camera_id}] ⚡ Video FPS: {video_fps:.1f} | Processing 1 frame every {frames_to_skip} frames.")
        
        frame_counter = 0
        
        while self.running:
            # Read frame at maximum possible disk speed
            ret, frame = cap.read()
            if not ret:
                print(f"[{self.camera_id}] ✅ Video Finished. Thread exiting.")
                break 
                
            frame_counter += 1
            
            # --------------------------------------------------
            # THE ACCELERATOR: FRAME SKIPPING LOGIC
            # --------------------------------------------------
            if frame_counter % frames_to_skip != 0:
                continue # Skip all other frames instantly
            
            # --------------------------------------------------
            # TASK 1: Feed the AI Workers (High Quality, 720p/1080p)
            # --------------------------------------------------
            ai_frame = cv2.resize(frame, (1280, 720))
            _, ai_buffer = cv2.imencode('.jpg', ai_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            ai_base64 = base64.b64encode(ai_buffer).decode('utf-8')
            
            payload = {
                "camera_id": self.camera_id,
                "timestamp": time.time(),
                "frame_data": ai_base64
            }
            
            # Push to the AI queue
            r.lpush("raw_frames_queue", json.dumps(payload))
            # Prevent RAM explosion if AI workers are processing slower than Producer
            r.ltrim("raw_frames_queue", 0, 1000) 
            
            # --------------------------------------------------
            # TASK 2: Feed the React Dashboard (Low Bandwidth, 360p)
            # --------------------------------------------------
            web_frame = cv2.resize(frame, (640, 360))
            _, web_buffer = cv2.imencode('.jpg', web_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            web_base64 = base64.b64encode(web_buffer).decode('utf-8')
            
            # Overwrite the latest frame for the UI video player
            r.set(f"latest_frame_{self.camera_id}", web_base64)

        cap.release()

if __name__ == "__main__":
    # ========================================================
    # 🎯 SET YOUR FOLDER PATH HERE
    # ========================================================
    FOLDER_PATH = "/home/user/Desktop/Video Surveillence ETE/samplefootage"
    
    # Valid video extensions
    valid_exts = ('.mp4', '.avi', '.mkv', '.mov')
    
    if not os.path.exists(FOLDER_PATH):
        print(f"❌ Error: Folder '{FOLDER_PATH}' does not exist.")
        exit(1)

    # Find all video files in the folder
    video_files = [os.path.join(FOLDER_PATH, f) for f in os.listdir(FOLDER_PATH) if f.lower().endswith(valid_exts)]
    
    if not video_files:
        print(f"⚠️ No video files found in {FOLDER_PATH}")
        exit(1)
        
    print(f"📂 Found {len(video_files)} video files. Booting threads...")

    threads = []
    try:
        for filepath in video_files:
            # ----------------------------------------------------
            # ⚙️ SET FRAME SKIP HERE (Currently set to 1 second)
            # ----------------------------------------------------
            t = VideoFileProducer(filepath, process_every_n_seconds=1)
            t.start()
            threads.append(t)
            
        print("✅ All video threads running at FULL DISK SPEED. Press Ctrl+C to stop.")
        
        # Dashboard loop to monitor queue
        while any(t.is_alive() for t in threads):
            queue_size = r.llen("raw_frames_queue")
            print(f"🔥 Redis AI Queue: {queue_size} frames waiting to be processed...", end='\r')
            time.sleep(0.5)
            
        print("\n🏁 All videos finished processing.")
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down video playback...")
        for t in threads:
            t.running = False
        for t in threads:
            t.join()
        print("✅ Shutdown complete.")