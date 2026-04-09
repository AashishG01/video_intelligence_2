import os
import cv2
import threading
import time
import redis
import json
import base64

# ⚙️ CONFIGURATION
FOLDER_PATH = "/home/user/Desktop/Video Surveillence ETE/samplefootage" # ⚠️ Apni 8 videos ka folder yahan daal
PROCESS_EVERY_N_SEC = 1       # Stress Test: 2 frames per second per camera

r = redis.Redis(host='localhost', port=6379, db=0)

class VideoProducer(threading.Thread):
    def __init__(self, filepath):
        threading.Thread.__init__(self)
        self.filepath = filepath
        self.camera_id = "bench_" + os.path.splitext(os.path.basename(filepath))[0][:20]

    def run(self):
        cap = cv2.VideoCapture(self.filepath)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frames_to_skip = int(fps * PROCESS_EVERY_N_SEC)
        frame_counter = 0

        print(f"🎬 [{self.camera_id}] Started.")
        while True:
            ret, frame = cap.read()
            if not ret: break
            frame_counter += 1
            
            if frame_counter % frames_to_skip != 0: continue

            # Resize slightly to simulate typical CCTV stream
            frame = cv2.resize(frame, (1280, 720))
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            b64_data = base64.b64encode(buffer).decode('utf-8')

            payload = {"camera_id": self.camera_id, "timestamp": time.time(), "frame_data": b64_data, "status": "LIVE"}
            r.lpush("bench_raw_frames", json.dumps(payload))

        cap.release()
        print(f"✅ [{self.camera_id}] Finished.")

if __name__ == "__main__":
    print("🧹 Clearing old benchmark queues...")
    r.delete("bench_raw_frames", "bench_face_ready")

    videos = [os.path.join(FOLDER_PATH, f) for f in os.listdir(FOLDER_PATH) if f.endswith(('.mp4', '.avi'))]
    threads = []
    
    for vid in videos:
        t = VideoProducer(vid)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # THE POISON PILL: Tell the workers to stop
    print("☠️ All videos sent. Sending POISON PILL to stop workers...")
    r.lpush("bench_raw_frames", json.dumps({"status": "EOF"}))
    print("🏁 Producer Shutdown Complete.")