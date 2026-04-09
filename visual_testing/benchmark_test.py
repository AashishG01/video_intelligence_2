import cv2
import time
import os
import psycopg2
from ultralytics import YOLO
from pymilvus import MilvusClient
from insightface.app import FaceAnalysis

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
VIDEO_PATH = "/home/user/Desktop/Video Surveillence ETE/samplefootage/zampabazzar.avi" # Yahan apni bheed wali video daal
SAVE_FOLDER = "./captured_faces_benchmark"
COLLECTION_NAME = "face_embeddings"

CONFIDENCE_GATE = 0.60
MATCH_THRESHOLD = 0.60

os.makedirs(SAVE_FOLDER, exist_ok=True)

# ==========================================
# 🔌 INITIALIZATION (Setup Time)
# ==========================================
print("⏳ Booting up Benchmark Environment...")

# 1. DB Connections
pg_conn = psycopg2.connect(dbname="surveillance", user="admin", password="password", host="localhost", port="5432")
pg_conn.autocommit = True
pg_cursor = pg_conn.cursor()

milvus_client = MilvusClient(uri="http://localhost:19530")
milvus_client.load_collection(COLLECTION_NAME)

# 2. AI Models
print("⏳ Loading YOLOv8m...")
yolo_model = YOLO('yolov8m.pt')

print("⏳ Loading AntelopeV2...")
face_app = FaceAnalysis(name='antelopev2', providers=['CUDAExecutionProvider'])
face_app.prepare(ctx_id=0, det_thresh=0.65, det_size=(1024, 1024))

print("✅ All Systems GO! Starting Benchmark...\n")
print("-" * 80)
print(f"{'FRAME':<8} | {'YOLO (ms)':<10} | {'FACES':<6} | {'INSIGHT (ms)':<12} | {'MILVUS (ms)':<12} | {'DB (ms)':<8} | {'TOTAL (ms)':<10}")
print("-" * 80)

# ==========================================
# 🚀 THE BENCHMARK LOOP
# ==========================================
cap = cv2.VideoCapture(VIDEO_PATH)
frame_count = 0
total_pipeline_time = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
        
    frame_count += 1
    
    # We are processing EVERY frame here to stress test the GPU
    # If you want to simulate real-world, add: if frame_count % 5 != 0: continue

    # ⏱️ Start Pipeline Timer
    t_start_pipeline = time.time()

    # -------------------------------------------------
    # STEP 1: YOLO INFERENCE
    # -------------------------------------------------
    t0 = time.time()
    results = yolo_model(frame, classes=[0], verbose=False)
    t_yolo = (time.time() - t0) * 1000

    people_found = False
    for result in results:
        for box in result.boxes:
            conf = float(box.conf[0])
            w, h = box.xyxy[0][2] - box.xyxy[0][0], box.xyxy[0][3] - box.xyxy[0][1]
            if conf > 0.7 and w > 150 and h > 250:
                people_found = True
                break
        if people_found: break

    t_insight = 0
    t_milvus_total = 0
    t_db_total = 0
    faces_detected = 0

    if people_found:
        # -------------------------------------------------
        # STEP 2: INSIGHTFACE (Detection + Embedding)
        # -------------------------------------------------
        t1 = time.time()
        faces = face_app.get(frame)
        t_insight = (time.time() - t1) * 1000
        
        valid_faces = [f for f in faces if f.det_score >= CONFIDENCE_GATE]
        faces_detected = len(valid_faces)

        for face in valid_faces:
            embedding = face.embedding.tolist()

            # -------------------------------------------------
            # STEP 3: MILVUS SEARCH
            # -------------------------------------------------
            t2 = time.time()
            search_res = milvus_client.search(
                collection_name=COLLECTION_NAME, data=[embedding], limit=1,
                output_fields=["person_id"], search_params={"metric_type": "COSINE", "params": {"nprobe": 10}}
            )
            t_milvus_total += (time.time() - t2) * 1000

            person_id = f"P_{int(time.time() * 1000)}" # Simplified for benchmark
            
            # Pro Margin Cropping
            x1, y1, x2, y2 = face.bbox.astype(int)
            mx, my = int((x2-x1)*0.25), int((y2-y1)*0.25)
            y1_m, y2_m = max(0, y1-my), min(frame.shape[0], y2+my)
            x1_m, x2_m = max(0, x1-mx), min(frame.shape[1], x2+mx)
            
            # -------------------------------------------------
            # STEP 4: DB INSERTS (Postgres)
            # -------------------------------------------------
            t3 = time.time()
            relative_path = f"/captured_faces_benchmark/test.jpg"
            pg_cursor.execute(
                "INSERT INTO sightings (person_id, camera_id, timestamp, image_path) VALUES (%s, %s, %s, %s)",
                (person_id, "benchmark_cam", time.time(), relative_path)
            )
            t_db_total += (time.time() - t3) * 1000

    # ⏱️ End Pipeline Timer
    t_end_pipeline = (time.time() - t_start_pipeline) * 1000
    total_pipeline_time += t_end_pipeline

    # 🖨️ Print Dashboard Row
    # Only print frames where people were actually processed to see the heavy load
    if people_found:
        print(f"#{frame_count:<7} | {t_yolo:<10.1f} | {faces_detected:<6} | {t_insight:<12.1f} | {t_milvus_total:<12.1f} | {t_db_total:<8.1f} | {t_end_pipeline:<10.1f}")

cap.release()
print("-" * 80)
print("🏁 BENCHMARK COMPLETE")
print(f"Total Frames Processed: {frame_count}")
print(f"Average Pipeline Latency (when people present): {total_pipeline_time/frame_count:.1f} ms")