# C.O.R.E. — City Operations & Recognition Engine
### AI-Powered Video Surveillance System — Surat Police Project
**Version:** 3.0 (Async Python + Redis + Milvus Architecture)

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Prerequisites](#2-prerequisites)
3. [Project Structure](#3-project-structure)
4. [One-Time Setup](#4-one-time-setup)
5. [Starting the Engine](#5-starting-the-engine)
6. [Running with Live Cameras](#6-running-with-live-cameras)
7. [Running with Sample Footage](#7-running-with-sample-footage)
8. [Verifying the System is Working](#8-verifying-the-system-is-working)
9. [Stopping the Engine](#9-stopping-the-engine)
10. [Resetting the Database](#10-resetting-the-database)
11. [Tuning & Configuration](#11-tuning--configuration)
12. [Troubleshooting](#12-troubleshooting)
13. [Architecture Reference](#13-architecture-reference)

---

## 1. System Overview

C.O.R.E. is a real-time person tracking and face recognition system built for city-scale surveillance. It processes live RTSP camera streams or recorded footage, detects and embeds every visible face, and stores them in a searchable vector database.

**How data flows through the system:**

```
RTSP Cameras / Video Files
        ↓
  producer.py / producer_folder.py
  (Reads frames, pushes to Redis)
        ↓
     Redis Queue: raw_frames_queue
        ↓
  worker_yolo.py
  (YOLOv8 pre-filter — only passes frames that contain people)
        ↓
     Redis Queue: face_ready_queue
        ↓
  worker_face.py
  (InsightFace AntelopeV2 — detects faces, extracts 512D embeddings,
   deduplicates, saves to Milvus + PostgreSQL + disk)
        ↓
  Milvus (vectors) + PostgreSQL (metadata) + /captured_faces (images)
        ↓
  FastAPI backend + React dashboard
```

**Key design principle:** Each component is completely independent. If the face worker crashes, cameras keep feeding Redis. If you need more throughput, just run another worker in a new terminal.

---

## 2. Prerequisites

### Hardware Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA RTX 3060 | NVIDIA RTX A6000 / A100 |
| RAM | 16 GB | 64 GB |
| Storage | 100 GB free | 1 TB NVMe SSD |
| CPU | 8 cores | 32+ cores (AMD EPYC) |

### Software Requirements

**Operating System:** Ubuntu 20.04 LTS or newer (required for Milvus)

**Install the following before proceeding:**

#### 1. NVIDIA Drivers + CUDA Toolkit
```bash
# Check if NVIDIA driver is installed
nvidia-smi

# If not installed, install CUDA 11.8 or 12.x
# Follow: https://developer.nvidia.com/cuda-downloads
```

#### 2. Docker + Docker Compose Plugin
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (avoids sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

#### 3. Python 3.10 or 3.11
```bash
python3 --version
# Should show 3.10.x or 3.11.x
```

#### 4. Conda or venv (recommended)
```bash
# Create a dedicated environment
conda create -n core_surveillance python=3.11
conda activate core_surveillance

# OR using venv
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Project Structure

```
surat_core_surveillance/
│
├── docker-compose.yml              ← Boots Redis, PostgreSQL, Milvus
├── .env                            ← Environment variables (DB passwords, thresholds)
├── README.md                       ← This file
│
├── ingestion_engine/
│   ├── producer.py                 ← Live RTSP camera ingestion
│   ├── producer_folder.py          ← Batch video folder processing
│   └── camera_registry.json        ← Camera URLs and tier assignments
│
├── ai_worker/
│   ├── worker_yolo.py              ← YOLOv8 person detection pre-filter
│   ├── worker_face.py              ← InsightFace embedding + DB storage
│   └── models/                     ← YOLOv8 weights go here
│
├── database_init/
│   └── init_db.py                  ← Creates PostgreSQL tables + Milvus collection
│
├── backend_api/
│   ├── main.py                     ← FastAPI server
│   └── captured_faces/             ← Saved face crop images (auto-created)
│
├── frontend_dashboard/
│   └── (React app)
│
├── sample_footages/                ← Put test video files here
│
└── visual_tests/
    └── test_yolo_visual.py         ← Visual debugger (shows YOLO boxes live)
```

---

## 4. One-Time Setup

Do this once when setting up on a new machine. You do not need to repeat these steps.

### Step 1 — Clone the repo and activate environment
```bash
cd ~/Desktop
# Navigate to your project folder
cd "Video Surveillence ETE"
conda activate core_surveillance   # or: source venv/bin/activate
```

### Step 2 — Install Python dependencies
```bash
pip install opencv-python-headless
pip install redis
pip install ultralytics              # YOLOv8
pip install insightface
pip install onnxruntime-gpu          # GPU inference for InsightFace
pip install pymilvus
pip install psycopg2-binary
pip install fastapi uvicorn
pip install python-multipart         # required for FastAPI file uploads
```

> **Note:** If `onnxruntime-gpu` conflicts with `onnxruntime`, uninstall the CPU version first:
> ```bash
> pip uninstall onnxruntime
> pip install onnxruntime-gpu
> ```

### Step 3 — Download AI Models

#### YOLOv8 (auto-downloads on first run, but you can pre-download):
```bash
cd ai_worker/
python3 -c "from ultralytics import YOLO; YOLO('yolov8m.pt')"
# Downloads ~52MB yolov8m.pt into current directory
```

#### InsightFace AntelopeV2 (auto-downloads on first run):
```bash
python3 -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='antelopev2', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1, det_size=(640,640))
print('AntelopeV2 downloaded successfully')
"
# Downloads ~500MB of ONNX models to ~/.insightface/models/antelopev2/
```

### Step 4 — Start the infrastructure containers
```bash
# From the project root (where docker-compose.yml is)
docker compose up -d

# Verify all 5 containers are running
docker compose ps
```

You should see these containers running:
```
NAME                STATUS
core_redis          running
core_postgres       running
milvus-etcd         running
milvus-minio        running
milvus-standalone   running
```

Wait ~30 seconds for Milvus to fully initialize before the next step.

### Step 5 — Initialize the databases
```bash
cd database_init/
python3 init_db.py
```

Expected output:
```
⏳ Connecting to PostgreSQL...
✅ PostgreSQL 'sightings' table ready.

⏳ Connecting to Milvus Standalone (Docker)...
✅ Milvus collection 'face_embeddings' created with COSINE index.
✅ Collection loaded into memory.

🚀 Database Infrastructure Fully Initialized!
```

> **Run init_db.py only once.** Running it again will drop and recreate the Milvus collection, deleting all stored embeddings.

---

## 5. Starting the Engine

The engine requires **3 terminals running simultaneously.** Open them side by side.

### Terminal 1 — Start the YOLO Pre-Filter Worker
```bash
conda activate core_surveillance
cd ai_worker/
python3 worker_yolo.py
```

Wait until you see:
```
✅ YOLO Online. Waiting for frames in the queue...
```

### Terminal 2 — Start the Face Embedding Worker
```bash
conda activate core_surveillance
cd ai_worker/
python3 worker_face.py
```

Wait until you see:
```
✅ Collection 'face_embeddings' loaded into memory.
✅ Face Worker Online. Awaiting frames...
```

### Terminal 3 — Start the Camera Ingestion (choose one option below)

**Option A: Live RTSP cameras**
```bash
conda activate core_surveillance
cd ingestion_engine/
python3 producer.py
```

**Option B: Sample video folder**
```bash
conda activate core_surveillance
cd ingestion_engine/
python3 producer_folder.py
```

### Terminal 4 (optional) — Start the API Server
```bash
conda activate core_surveillance
cd backend_api/
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 6. Running with Live Cameras

### Configure camera URLs

Edit `ingestion_engine/producer.py` and update the cameras dictionary:

```python
cameras = {
    "cam1": "rtsp://admin:admin@172.16.0.151:554/live.sdp",
    "cam2": "rtsp://admin:admin@172.16.0.152:554/live.sdp",
    "cam3": "rtsp://admin:123456@172.16.0.161:554/live.sdp",
    "cam4": "rtsp://admin:Admin@123@172.16.0.162:554/live.sdp",
}
```

### Camera tier assignment (controls FPS)

| Tier | Location Type | FPS | Face Size Min |
|------|--------------|-----|---------------|
| T1 | Dense markets, chaurahas, stations | 1 FPS | 60px+ |
| T2 | Main roads, bus stops | 2 FPS | 40px+ |
| T3 | Residential, highways | 3 FPS | 25px+ |

Change a camera's FPS by editing `fps_limit` in producer.py:
```python
t = CameraProducer(cam_id, url, fps_limit=1)  # T1
t = CameraProducer(cam_id, url, fps_limit=2)  # T2
t = CameraProducer(cam_id, url, fps_limit=3)  # T3
```

### Test if a camera is reachable
```bash
# Quick RTSP connectivity test
python3 -c "
import cv2
cap = cv2.VideoCapture('rtsp://admin:admin@172.16.0.151:554/live.sdp')
ret, frame = cap.read()
print('CONNECTED' if ret else 'FAILED — check IP/credentials')
cap.release()
"
```

---

## 7. Running with Sample Footage

### Setup
1. Create a folder called `sample_footages/` in the project root
2. Drop your `.mp4`, `.avi`, or `.mkv` files into it
3. Edit `FOLDER_PATH` in `ingestion_engine/producer_folder.py`:

```python
FOLDER_PATH = "/home/user/Desktop/Video Surveillence ETE/sample_footages"
```

### Run
```bash
cd ingestion_engine/
python3 producer_folder.py
```

The system will:
- Auto-detect all video files in the folder
- Spawn one thread per video (parallel processing)
- Use the filename as the Camera ID (truncated to 45 chars)
- Process at 1 FPS (throttled — prevents Redis RAM overflow)
- Stop automatically when all videos finish

### Naming convention for video files
Name your files after the location for clean camera IDs in the database:
```
Mahidharpura_Market.mp4       → cam_id: "Mahidharpura_Market"
Majura_Gate_Chauraha.mp4      → cam_id: "Majura_Gate_Chauraha"
Railway_Station_Gate.avi      → cam_id: "Railway_Station_Gate"
Gopi_Talav_Night.mp4          → cam_id: "Gopi_Talav_Night"
```

---

## 8. Verifying the System is Working

### Check 1 — Redis queue is receiving frames
In any terminal:
```bash
redis-cli llen raw_frames_queue
# Should show a number > 0 while producer is running

redis-cli llen face_ready_queue
# Should show a number > 0 while YOLO worker is running
```

### Check 2 — YOLO worker output
Terminal 1 should show:
```
[Mahidharpura_Market] 👤 People detected — frame queued for face analysis.
[Railway_Station_Gate] 👤 People detected — frame queued for face analysis.
```

### Check 3 — Face worker output
Terminal 2 should show:
```
🔍 [Mahidharpura_Market] Closest match distance: 0.3821 (threshold: 0.50)
❌ NO MATCH: 0.3821 < 0.50. New person.
[Mahidharpura_Market] 💾 NEW 🆕: P_1774563826633 (conf: 0.87)

🔍 [Railway_Station_Gate] Closest match distance: 0.7234 (threshold: 0.50)
✅ MATCH: P_1774563826633
[Railway_Station_Gate] 💾 MATCH ✅: P_1774563826633 (conf: 0.79)
```

### Check 4 — Images are being saved
```bash
ls backend_api/captured_faces/
# Should show .jpg files named like: P_1774563826633_1774563826.jpg
```

### Check 5 — PostgreSQL has records
```bash
docker exec -it core_postgres psql -U admin -d surveillance -c \
  "SELECT person_id, camera_id, timestamp FROM sightings ORDER BY timestamp DESC LIMIT 10;"
```

### Check 6 — Milvus has vectors
```bash
python3 -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='http://localhost:19530')
stats = c.get_collection_stats('face_embeddings')
print('Total vectors stored:', stats['row_count'])
"
```

### Check 7 — API is responding
```bash
curl http://localhost:8000/api/sightings/recent
# Should return JSON with sightings list

curl http://localhost:8000/api/system/stats
# Should return total_faces_captured, unique_suspects, etc.
```

---

## 9. Stopping the Engine

### Graceful shutdown (recommended)
Press `Ctrl+C` in each terminal in this order:
1. Terminal 3 (producer) — stop new frames entering
2. Terminal 1 (YOLO worker) — let queue drain first
3. Terminal 2 (face worker) — let queue drain first
4. Terminal 4 (API server)

### Stop Docker containers (when done for the day)
```bash
docker compose stop
# Containers stop but data is preserved

# To completely remove containers (data still preserved in volumes)
docker compose down
```

### Stop Docker containers and wipe ALL data (full reset)
```bash
docker compose down -v
# WARNING: This deletes all Milvus vectors, PostgreSQL records, and Redis data
```

---

## 10. Resetting the Database

### Reset only the face embeddings (keep PostgreSQL sightings)
```bash
python3 -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='http://localhost:19530')
c.drop_collection('face_embeddings')
print('Collection dropped. Run init_db.py to recreate.')
"
python3 database_init/init_db.py
```

### Reset everything (fresh start)
```bash
# 1. Stop all workers (Ctrl+C in each terminal)

# 2. Wipe Docker volumes
docker compose down -v

# 3. Delete saved face images
rm -rf backend_api/captured_faces/*

# 4. Restart infrastructure
docker compose up -d
sleep 30  # wait for Milvus to initialize

# 5. Reinitialize databases
python3 database_init/init_db.py
```

---

## 11. Tuning & Configuration

All key thresholds are at the top of `ai_worker/worker_face.py`:

```python
CONFIDENCE_GATE = 0.60    # Min face detection confidence (0.0 - 1.0)
                          # Lower = catch more faces but more noise
                          # Higher = only high-quality faces
                          # Recommended range: 0.55 - 0.65

MATCH_THRESHOLD = 0.50    # Milvus cosine similarity for person matching (0.0 - 1.0)
                          # Lower = stricter matching (more NEW persons, fewer false matches)
                          # Higher = looser matching (fewer NEW persons, more false matches)
                          # Recommended range: 0.45 - 0.60
                          # Your POC validated: 0.50 sweet spot for Surat footage

DEDUP_WINDOW_SEC = 60     # Seconds before same person can be logged again
                          # Set lower (30s) for faster tracking
                          # Set higher (120s) for less database spam
```

### Threshold reference from POC testing on real Surat footage:

| Milvus Similarity | Accuracy | Notes |
|-------------------|----------|-------|
| > 0.40 | ~59% | Too strict — many false new IDs |
| > 0.45 | ~70% | Still too strict |
| > 0.50 | ~79% | Moderate — good starting point |
| > 0.55 | ~86% | ✅ Recommended sweet spot |
| > 0.57 | ~87-88% | ✅ Visually verified on Surat footage |
| > 0.60 | ~91% | High false positive risk — same person = different ID |

### Night footage tuning

For low-light / night cameras, lower the confidence gate slightly:
```python
CONFIDENCE_GATE = 0.50   # Night mode — catch more faces
MATCH_THRESHOLD = 0.48   # Slightly looser — night embeddings are less crisp
```

---

## 12. Troubleshooting

### Problem: `collection not loaded` error in worker_face.py
```bash
# Milvus container restarted and unloaded the collection. Fix:
python3 -c "
from pymilvus import MilvusClient
c = MilvusClient(uri='http://localhost:19530')
c.load_collection('face_embeddings')
print('Collection reloaded.')
"
```

### Problem: `value too long for type character varying(50)`
```bash
# Run this once to expand the column size
docker exec -it core_postgres psql -U admin -d surveillance -c \
  "ALTER TABLE sightings ALTER COLUMN camera_id TYPE VARCHAR(255);"
```

### Problem: Same person keeps getting new IDs
- Lower `MATCH_THRESHOLD` from 0.50 to 0.45 in worker_face.py
- Check that `milvus_client.flush()` is being called after every insert
- Check that the `DEDUP_WINDOW_SEC` Redis cache is working:
```bash
redis-cli keys "seen_global_*"  # Should show person IDs in cache
```

### Problem: GPU not being used (running on CPU)
```bash
# Verify CUDA is available
python3 -c "import onnxruntime; print(onnxruntime.get_available_providers())"
# Should show: ['CUDAExecutionProvider', 'CPUExecutionProvider']

# If only CPUExecutionProvider shows:
pip uninstall onnxruntime
pip install onnxruntime-gpu
```

### Problem: Redis queue grows infinitely (workers too slow)
```bash
# Check queue sizes
redis-cli llen raw_frames_queue
redis-cli llen face_ready_queue

# If > 500, start a second face worker in a new terminal:
# Terminal 5:
conda activate core_surveillance
cd ai_worker/
python3 worker_face.py   # Second worker auto-shares the queue
```

### Problem: Milvus container keeps restarting
```bash
# Check logs
docker logs milvus-standalone --tail 50

# Usually caused by insufficient disk space. Check:
df -h

# Or insufficient RAM for index. Check:
free -h
```

### Problem: RTSP stream keeps dropping
The producer already handles auto-reconnect. But if drops are frequent:
```bash
# Test TCP stability (add to producer.py if not already there)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
```

### Problem: `No module named 'pkg_resources'` with Milvus Lite
You're using Milvus Standalone via Docker — you don't need Milvus Lite. Make sure your code connects to `http://localhost:19530`, not a local `.db` file.

### Problem: InsightFace `FutureWarning` about `estimate`
This is a harmless warning from the `scikit-image` library inside InsightFace. It does not affect accuracy or functionality. Suppress it with:
```python
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
```

---

## 13. Architecture Reference

### Data Flow Diagram
```
┌─────────────────────┐     ┌─────────────────────┐
│   producer.py       │     │  producer_folder.py  │
│   (Live RTSP)       │     │  (Video files)       │
└──────────┬──────────┘     └──────────┬───────────┘
           │                           │
           └──────────┬────────────────┘
                      ↓
            Redis: raw_frames_queue
            (Max 1000 frames, TTL auto-expire)
                      ↓
            ┌─────────────────┐
            │  worker_yolo.py │
            │  YOLOv8 filter  │
            │  "Any people?"  │
            └────────┬────────┘
                     │ YES — full frame forwarded
                     ↓
            Redis: face_ready_queue
            (Max 500 frames)
                     ↓
            ┌─────────────────────────┐
            │     worker_face.py      │
            │  InsightFace det+embed  │
            │  Confidence gate ≥0.60  │
            │  Milvus similarity search│
            │  Global dedup (60s)     │
            │  flush() after insert   │
            └────────┬────────────────┘
                     │
          ┌──────────┼──────────────┐
          ↓          ↓              ↓
      Milvus      PostgreSQL    /captured_faces/
    (512D vectors) (metadata)   (face .jpg images)
          │          │
          └──────────┘
                ↓
         FastAPI backend
         (REST + WebSocket)
                ↓
        React Dashboard
```

### Port Reference
| Service | Port | Purpose |
|---------|------|---------|
| Redis | 6379 | Frame queues + pub/sub alerts |
| PostgreSQL | 5432 | Sightings metadata |
| Milvus | 19530 | Vector search |
| MinIO | 9000, 9001 | Milvus internal storage |
| FastAPI | 8000 | REST API + WebSocket |
| React | 5173 | Dashboard (Vite dev server) |

### Redis Key Reference
| Key | Type | Purpose |
|-----|------|---------|
| `raw_frames_queue` | List | RTSP frames waiting for YOLO |
| `face_ready_queue` | List | Frames with people, waiting for face worker |
| `latest_frame_{cam_id}` | String | Latest frame for MJPEG web stream |
| `seen_global_{person_id}` | String (TTL) | Dedup cache — expires in 60s |
| `live_face_alerts` | Pub/Sub channel | Real-time alerts to FastAPI WebSocket |

---

## Quick Start Cheatsheet

```bash
# 1. Start infrastructure
docker compose up -d

# 2. (First time only) Initialize databases
python3 database_init/init_db.py

# 3. Open 3 terminals and run:

# Terminal 1
conda activate core_surveillance && cd ai_worker && python3 worker_yolo.py

# Terminal 2
conda activate core_surveillance && cd ai_worker && python3 worker_face.py

# Terminal 3 — choose one:
conda activate core_surveillance && cd ingestion_engine && python3 producer.py
# OR
conda activate core_surveillance && cd ingestion_engine && python3 producer_folder.py

# Terminal 4 (optional — API server)
conda activate core_surveillance && cd backend_api && uvicorn main:app --host 0.0.0.0 --port 8000

# To stop everything:
# Ctrl+C in each terminal, then:
docker compose stop
```

---

*C.O.R.E. — Built for Surat. Engineered for scale.*
