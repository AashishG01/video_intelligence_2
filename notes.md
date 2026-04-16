# 📋 Project Notes — Full Audit & Status Report
> **Date:** April 16, 2026  
> **Project:** Surat City Video Surveillance & Person Tracking System  
> **Reference:** [`ProjectPlan_v2.md`](file:///c:/Users/Hp/Desktop/video_intelligence_2/ProjectPlan_v2.md)

---

## 1. Project Directory Structure (Complete)

```
video_intelligence_2/
├── docker-compose.yml          ← 6 containers (Milvus, etcd, MinIO, Redis, Postgres, MediaMTX)
├── mediamtx.yml                ← RTSP→WebRTC bridge config (4 cameras hardcoded)
├── ProjectPlan_v2.md           ← Master architecture doc (665 lines)
├── notes.md                    ← THIS FILE
├── benchmark.md                ← Empty (unused)
├── frontend&backendnotes.md    ← Old MJPEG vs WebRTC discussion notes
├── README.md                   ← Project readme
├── .gitignore
│
├── database_init/
│   └── init_db.py              ← Creates PostgreSQL tables + Milvus collections
│
├── Ingestion/
│   ├── producer.py             ← Live RTSP camera → Redis queue (4 cameras)
│   └── producer_folder.py      ← Offline video files → Redis queue (batch mode)
│
├── ai_worker/
│   ├── worker_face.py          ← ★ MAIN WORKER — Watchlist + general face matching
│   ├── optimized_face.py       ← Simpler worker variant (no watchlist, no quality gates)
│   ├── facequalitygate_enhanced.py ← Worker with night vision + blur/angle quality gates
│   ├── worker_yolo.py          ← YOLOv8m pre-filter (person detection gate)
│   └── yolov8m.pt              ← YOLOv8 Medium model weights (52MB)
│
├── tracker/
│   ├── worker_yolo.py          ← YOLOv8 + ByteTrack multi-person tracker
│   ├── worker_face.py          ← Face worker using ByteTrack IDs for best-frame selection
│   ├── test_tracker.py         ← Visual ByteTrack test script (OpenCV window)
│   └── yolov8m.pt              ← Duplicate YOLOv8 weights
│
├── visual_testing/
│   ├── benchmark_test.py       ← End-to-end pipeline benchmark (YOLO→InsightFace→Milvus→Postgres)
│   ├── bench_producer.py       ← Benchmark frame producer
│   ├── bench_worker.py         ← Benchmark face worker
│   ├── bench_yolo.py           ← Benchmark YOLO-only speed
│   ├── bench_monitor.py        ← Queue size monitor during benchmarks
│   ├── clean_bench.py          ← Cleanup script for benchmark data
│   ├── test_yolo_visual.py     ← YOLO visual debugging tool
│   ├── benchmark_hardware_report.csv ← GPU performance results
│   └── yolov8m.pt              ← Duplicate YOLOv8 weights
│
├── backend_api/
│   ├── api.py                  ← ★ LEGACY API (MJPEG streams, search, dossier)
│   └── newapi.py               ← ★ CURRENT API (WebSocket, Watchlist CRUD, search)
│
└── frontend/src/
    ├── main.jsx                ← React entry point
    ├── App.jsx                 ← Root component (WebSocket manager, routing)
    ├── App.css                 ← fadeIn animation keyframes
    ├── index.css               ← Tailwind imports + Inter font + base styles
    ├── config.js               ← BACKEND_URL, WS_URL, MEDIAMTX_URL + getImageUrl helper
    │
    ├── components/
    │   ├── Sidebar.jsx         ← Left navigation bar ("C.O.R.E.")
    │   ├── StatCard.jsx        ← Reusable stat display card
    │   ├── SightingCard.jsx    ← Search result: face thumbnail + match score + camera
    │   ├── TimelineCard.jsx    ← Chronological sighting entry for a person
    │   ├── WatchlistPanel.jsx  ← ★ NEW: Suspect enrollment, grid selection, activate/stop search
    │   └── LiveAlertBar.jsx    ← ★ NEW: Red top-of-screen banner for watchlist match alerts
    │
    └── views/
        ├── LiveMonitorView.jsx ← 4-camera WebRTC grid + WatchlistPanel sidebar + live captures
        ├── InvestigatorView.jsx← Upload a photo → Milvus search → sightings + person timeline
        ├── SystemStatusView.jsx← Live stats from PostgreSQL (total captures, unique suspects, cameras)
        └── EventFeedView.jsx   ← Terminal-style WebSocket log stream
```

---

## 2. Infrastructure (Docker Compose)

6 containers run via `docker-compose.yml`:

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `milvus-standalone` | `milvusdb/milvus:v2.3.0` | 19530 | Vector database for face embeddings |
| `milvus-etcd` | `coreos/etcd:v3.5.0` | — | Milvus metadata store |
| `milvus-minio` | `minio/minio` | 9000, 9001 | Milvus blob storage backend |
| `core_redis` | `redis:latest` | 6379 | Message queue + cache + pub/sub |
| `core_postgres` | `postgres:15` | 5432 | Sighting logs + watchlist metadata |
| `core_mediamtx` | `bluenviron/mediamtx` | 8554, 8889, 8189/udp | RTSP→WebRTC bridge |

**Volumes:** `etcd_data`, `minio_data`, `postgres_data` (persistent across restarts, NOT across `docker-compose down -v`)

---

## 3. Database Layer (`database_init/init_db.py`)

### PostgreSQL Tables
| Table | Columns | Purpose |
|-------|---------|---------|
| `sightings` | `id`, `person_id` (VARCHAR 100), `camera_id` (VARCHAR 50), `timestamp` (FLOAT), `image_path` (TEXT) | Every face detection log |
| `watchlist` | `id`, `watchlist_id` (VARCHAR 100, UNIQUE), `name`, `threat_level`, `image_path`, `created_at` | Enrolled suspect metadata |

Indexes: `idx_timestamp`, `idx_person_id`, `idx_watchlist_id`

### Milvus Collections
| Collection | Fields | Index | Purpose |
|------------|--------|-------|---------|
| `face_embeddings` | `id` (auto), `person_id` (VARCHAR), `embedding` (512-d FLOAT_VECTOR) | IVF_FLAT, COSINE, nlist=128 | All civilian face embeddings |
| `watchlist_faces` | `id` (auto), `watchlist_id` (VARCHAR), `embedding` (512-d FLOAT_VECTOR) | IVF_FLAT, COSINE, nlist=128 | Enrolled suspect embeddings |

⚠️ **`init_db.py` DROPS and recreates collections on every run.** This is destructive — existing data is wiped.

---

## 4. Ingestion Layer (`Ingestion/`)

### `producer.py` — Live RTSP Camera Producer
- Spawns 1 thread per camera (4 cameras hardcoded with lab RTSP URLs)
- Reads frames via `cv2.VideoCapture` with RTSP/TCP transport
- Resizes to 720p, JPEG encodes at quality 75, base64 encodes
- Pushes JSON payload `{camera_id, timestamp, frame_data}` to Redis list `raw_frames_queue`
- `ltrim` caps queue at 1000 entries (prevents RAM overflow if workers lag)
- FPS configurable per camera (default: 1 FPS)
- Auto-reconnect on stream drop (5 second backoff)
- Note: Old "Task 2" (MJPEG web feed via Redis) was deleted — frontend now uses WebRTC

### `producer_folder.py` — Offline Video File Producer
- Scans a folder for `.mp4/.avi/.mkv/.mov` files
- 1 thread per video file
- Uses frame-skip logic: computes `frames_to_skip = video_fps × process_every_n_seconds`
- Same Redis queue (`raw_frames_queue`) as live producer
- Still has old MJPEG "Task 2" code (`r.set("latest_frame_..."`) — NOT needed if using WebRTC
- Camera ID = filename (truncated to 45 chars to prevent Postgres VARCHAR(50) overflow)

---

## 5. AI Worker Layer (`ai_worker/`)

### `worker_face.py` — ★ CURRENT MAIN WORKER (328 lines)
The production worker that runs in the main pipeline. Key features:
- **Queue:** `face_ready_queue` (not `raw_frames_queue` — expects YOLO pre-filtered frames)
- **Model:** InsightFace `antelopev2` (RetinaFace + ArcFace bundled, 512-d embeddings)
- **Confidence Gate:** 0.60
- **Match Threshold:** 0.60
- **Margin Crop:** 25% padding on bounding box for passport-style face saves
- **Empty Crop Guard:** Skips if `face_crop.size == 0` to prevent `cv2.imwrite` crashes
- **Watchlist Search:** Checks Redis `ACTIVE_WATCHLIST` on every face → if active, searches `watchlist_faces` Milvus collection → if similarity > 0.55, fires `WATCHLIST_MATCH` alert
- **General Search:** If no watchlist match, searches `face_embeddings` collection → `MATCH` or `NEW`
- **Deduplication:** 60-second `setex` cache with key `seen_global_{person_id}`. Watchlist matches bypass dedup so alerts always fire.
- **Postgres Insert:** Logs every detection to `sightings` table
- **Redis Pub/Sub:** Publishes JSON alert to `live_face_alerts` channel (picked up by WebSocket in API)
- **Self-Healing:** Catches PostgreSQL connection drops and reconnects automatically

### `optimized_face.py` — Simplified Worker (154 lines)
- No watchlist logic
- No quality gates (blur/angle/night)
- No self-healing
- Uses separate `r_pub` Redis connection for publish (avoids handshake overhead)
- Higher det_size (1024×1024) = more accurate but slower
- Good for batch processing offline videos

### `facequalitygate_enhanced.py` — Quality-Gated Worker (277 lines)
- **Night Enhancement:** `is_dark()` checks mean brightness, `enhance_night_frame()` applies CLAHE + gamma correction
- **Quality Gates:**
  - Gate 0: Confidence (0.60)
  - Gate 1: Size (face width ≥ 40px)
  - Gate 2: Front-facing check (landmark skew threshold 0.35)
  - Gate 3: Sharpness/blur (Laplacian variance ≥ 60.0, relaxed to 30.0 for dark frames)
- No watchlist logic
- Has self-healing PostgreSQL reconnect
- This worker represents the most "quality-conscious" variant but is NOT the one currently in production

### `worker_yolo.py` — YOLOv8 Pre-Filter (72 lines)
- Reads from `raw_frames_queue`, runs YOLOv8m (person class=0 only)
- Filters: conf > 0.7, bbox width > 150px, height > 250px (large enough for usable face)
- If passed: forwards original payload to `face_ready_queue`
- If rejected: drops frame (saves InsightFace compute)
- Tracks pass/reject counters per session

---

## 6. Tracker Module (`tracker/`)

An **experimental** ByteTrack-based person tracking pipeline. NOT currently used in production.

### `tracker/worker_yolo.py` — YOLO + ByteTrack Tracker
- Uses `model.track()` with `persist=True` and `bytetrack.yaml` for stable person IDs across frames
- Forwards tracked bounding boxes + track IDs alongside the frame to `face_ready_queue`

### `tracker/worker_face.py` — ByteTrack-Aware Face Worker (287 lines)
- Receives YOLO track IDs from the tracker
- Uses `get_track_id_for_face()` to associate an InsightFace bbox with a YOLO person bbox (IoU-based)
- **Best-Frame Buffer:** Accumulates faces per track_id, only flushes to DB when the track expires (TRACK_TIMEOUT = 5 seconds)
- On flush, saves the single best-quality face (highest `det_score × laplacian_variance`)
- Has night enhancement pipeline + face quality gates
- Most sophisticated worker variant but currently idle/experimental

### `tracker/test_tracker.py` — Visual Tester
- Opens a video file, runs ByteTrack, draws annotated bounding boxes on screen via `cv2.imshow`

---

## 7. Visual Testing & Benchmarks (`visual_testing/`)

| File | Purpose |
|------|---------|
| `benchmark_test.py` | Full pipeline benchmark: YOLO → InsightFace → Milvus → Postgres. Prints per-frame latency table. |
| `bench_producer.py` | Simulated frame producer for benchmarks |
| `bench_worker.py` | Isolated face worker benchmark |
| `bench_yolo.py` | YOLO-only latency test |
| `bench_monitor.py` | Monitors Redis queue sizes during benchmarks |
| `clean_bench.py` | Cleans up benchmark data from DB |
| `test_yolo_visual.py` | Visual YOLO debugging (draws boxes) |
| `benchmark_hardware_report.csv` | GPU performance results (CSV data) |

---

## 8. Backend API Layer (`backend_api/`)

### `api.py` — ★ LEGACY API (220 lines)
The original FastAPI server. Still functional but superseded by `newapi.py`. Features:
- `GET /api/stream/{cam_id}` — MJPEG streaming from Redis `latest_frame_{cam_id}` (replaced by WebRTC)
- `GET /api/system/stats` — Total captures, unique suspects, active cameras from Postgres
- `POST /api/investigate/search_by_image` — Upload a face photo → InsightFace embed → Milvus search → return sightings
- `GET /api/investigate/person/{person_id}` — Full timeline dossier for a person ID
- Mounts `/images` → `../4_backend_api/captured_faces` (note: wrong relative path, doesn't match project structure)

### `newapi.py` — ★ CURRENT PRODUCTION API (~304 lines)
The active FastAPI server. Contains everything from `api.py` plus:
- `WebSocket /ws/live_alerts` — Subscribes to Redis `live_face_alerts` pub/sub channel. Manages multiple WebSocket connections. Broadcasts every detection to all connected frontends.
- **Watchlist CRUD:**
  - `POST /api/watchlist/add?name=X&threat_level=Y` — Upload face image, embed with InsightFace, insert to Postgres `watchlist` table + Milvus `watchlist_faces` collection
  - `GET /api/watchlist/list` — Returns all enrolled suspects with metadata
  - `DELETE /api/watchlist/remove/{watchlist_id}` — Deletes from Postgres + Milvus
  - `POST /api/watchlist/activate` — Accepts JSON array of watchlist IDs, writes to Redis `ACTIVE_WATCHLIST`
  - `DELETE /api/watchlist/deactivate` — Clears `ACTIVE_WATCHLIST` from Redis
- Mounts `/images` → `./captured_faces` (correct relative path)
- Run: `uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload`

---

## 9. Frontend Dashboard (`frontend/`)

**Stack:** React (Vite 4.5), Tailwind CSS, Lucide Icons, Inter font

### Root
| File | Purpose |
|------|---------|
| `main.jsx` | React DOM render |
| `App.jsx` | Root component: manages WebSocket, `liveAlerts[]`, `systemLogs[]`, navigation routing |
| `config.js` | Exports `BACKEND_URL` (8000), `WS_URL` (ws://...8000/ws/live_alerts), `MEDIAMTX_URL` (8889), `getImageUrl()` |
| `index.css` | Tailwind directives + Inter font import |
| `App.css` | `fadeIn` keyframe animation |

### Views (4 Pages)

| View | Description |
|------|-------------|
| **LiveMonitorView** | 2×2 WebRTC camera grid (custom `WebRTCPlayer` using WHEP protocol to MediaMTX). Right sidebar has `WatchlistPanel` + Live Captures feed. Top-level `LiveAlertBar` for watchlist alarms. |
| **InvestigatorView** | Two tabs: (1) Upload photo → search → sighting cards. (2) Enter person ID → fetch timeline/dossier. |
| **SystemStatusView** | Auto-refreshing stats from `GET /api/system/stats` — total captures, unique suspects, active cameras, system start time. |
| **EventFeedView** | Terminal-style (dark background, mono font) real-time log of all WebSocket events. |

### Components (6 Reusable)

| Component | Description |
|-----------|-------------|
| `Sidebar.jsx` | Left nav with C.O.R.E. branding. 4 nav items. |
| `StatCard.jsx` | Icon + value + label card for dashboard stats |
| `SightingCard.jsx` | Person sighting result: face thumbnail, match score, camera, timestamp |
| `TimelineCard.jsx` | Simpler timeline entry: face, camera, timestamp |
| `WatchlistPanel.jsx` | ★ Full suspect enrollment: upload form (name, threat level), photo grid with selection, activate/stop live search buttons |
| `LiveAlertBar.jsx` | ★ Fixed red banner at top of screen showing suspect name, camera, timestamp, confidence on WATCHLIST_MATCH |

### Video Streaming
- **WebRTCPlayer:** Custom component inside `LiveMonitorView.jsx`
- Uses WHEP (WebRTC HTTP Egress Protocol) to connect to MediaMTX
- Creates `RTCPeerConnection`, sends SDP offer to `http://localhost:8889/{camId}/whep`, receives SDP answer
- Auto-retry 3 times (5s delay), then marks camera offline
- Zero-latency, sub-100ms compared to old MJPEG approach

---

## 10. How the System Actually Runs (Data Flow)

```
[4 RTSP Cameras]
       │
       ├──→ [MediaMTX Docker Container] ──→ WebRTC ──→ [React LiveMonitorView]
       │         (zero-latency video)
       │
       └──→ [producer.py] ── cv2.VideoCapture → base64 encode → Redis lpush
                                                                    │
                                                            "raw_frames_queue"
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    │ (Optional YOLO Pre-Filter)     │
                                                    │   worker_yolo.py               │
                                                    │   Drops empty frames           │
                                                    └───────────────┬───────────────┘
                                                                    │
                                                            "face_ready_queue"
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    │  worker_face.py (MAIN)         │
                                                    │  1. InsightFace → 512-d embed  │
                                                    │  2. Check ACTIVE_WATCHLIST      │
                                                    │     → Milvus watchlist_faces    │
                                                    │  3. Milvus face_embeddings      │
                                                    │  4. Dedup (60s Redis cache)     │
                                                    │  5. Save crop to disk           │
                                                    │  6. Insert Postgres sightings   │
                                                    │  7. Publish Redis live_face_alerts
                                                    └───────────────┬───────────────┘
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    │  newapi.py (FastAPI + WS)      │
                                                    │  Subscribes to live_face_alerts │
                                                    │  Broadcasts to all WebSocket    │
                                                    │  clients                        │
                                                    └───────────────┬───────────────┘
                                                                    │
                                                    ┌───────────────┴───────────────┐
                                                    │  React Frontend                │
                                                    │  App.jsx WebSocket handler     │
                                                    │  → LiveAlertBar (WATCHLIST)    │
                                                    │  → Live Captures sidebar       │
                                                    │  → EventFeedView logs          │
                                                    └───────────────────────────────┘
```

---

## 11. Comparison with ProjectPlan_v2.md — What We Skipped

### ❌ NVIDIA DeepStream SDK + GStreamer Pipelines
| Plan | Reality |
|------|---------|
| GPU-accelerated RTSP decode via NVDEC | OpenCV `cv2.VideoCapture` (CPU-decoded) |
| Hardware H.264/H.265 decoding on GPU | Software decoding via FFmpeg backend |
| Multi-stream batching | 1 thread per camera, no batching |

**Impact:** CPU decode + base64 encoding + Redis serialization works for 4-10 cameras. Will hit a hard wall at ~50+ cameras (CPU bottleneck, Redis memory bloat). DeepStream is needed before scaling to 2000.

### ❌ Apache Kafka
| Plan | Reality |
|------|---------|
| Kafka topics partitioned by camera group | Redis `lpush`/`brpop` as a basic FIFO queue |
| Fault-tolerant, replayable message bus | Redis queue with `ltrim` (drops old frames when full) |
| Consumer groups for parallel workers | Single worker pulling from single queue |

**Impact:** Redis works perfectly for a single-worker, 4-camera setup. Kafka allows multiple consumer groups (e.g., one for face detection, one for ANPR, one for analytics), message replay after crashes, and partitioning by camera tier.

### ❌ NVIDIA Triton Inference Server
| Plan | Reality |
|------|---------|
| Dedicated GPU model server with dynamic batching | InsightFace loaded directly in worker process memory |
| Hot-swap models, A/B testing, versioning | Single model hardcoded |
| Multi-model serving (YOLO + RetinaFace + AdaFace) | Worker loads models on startup, dies = models unload |

**Impact:** Triton enables processing 16-32 faces in a single GPU batch call. Our current approach processes 1 frame at a time. For 2000 cameras, Triton's batching is essential to max out GPU utilization.

### ❌ YOLOv8 Person Detection (as mandatory pipeline stage)
| Plan | Reality |
|------|---------|
| YOLO runs on every frame before face detection | YOLO pre-filter exists (`worker_yolo.py`) but NOT mandatory in current pipeline |
| Saves 60-80% compute by discarding empty frames | `worker_face.py` currently reads from `face_ready_queue` (assumes YOLO already ran), but `producer.py` pushes to `raw_frames_queue` |

**Note:** The YOLO worker exists and works. The queue names are set up correctly (`raw_frames_queue` → YOLO → `face_ready_queue` → Face Worker). However, in practice, you can also run `worker_face.py` directly on `raw_frames_queue` by changing one line. The pipeline is designed but not enforced.

### ❌ TimescaleDB (time-series extension for PostgreSQL)
| Plan | Reality |
|------|---------|
| `sightings` as a hypertable partitioned by time | Standard PostgreSQL table |
| Automatic chunk-based retention (drop 30-day old data) | No retention policy implemented |

**Impact:** Standard Postgres handles millions of rows fine. At 30M+ inserts/day (2000 cameras), TimescaleDB's automatic partitioning and chunk-based deletion become essential.

### ❌ Separate RetinaFace + AdaFace Models
| Plan | Reality |
|------|---------|
| Separate RetinaFace (detection) + AdaFace (embedding) | InsightFace `antelopev2` bundles both (detection + recognition) |

**Impact:** Low. The bundled `antelopev2` model works well. Separating would only matter if we need to swap individual components (e.g., upgrade face recognizer only). This is a "nice to have," not a blocker.

### ❌ Additional Features Not Yet Built
| Feature | Status |
|---------|--------|
| Interactive Surat City Map (Leaflet/MapLibre) | Not started |
| Person Movement Timeline on Map | Not started |
| PDF Report Export (court-ready) | Not started |
| Historical Search (Celery background jobs) | Not started |
| Festival Mode toggle | Not started |
| JWT Authentication + RBAC | Not started |
| DPDP Act audit logging | Not started |
| Prometheus + Grafana monitoring | Not started |
| Camera Registry (database-driven, not hardcoded) | Cameras still hardcoded in `mediamtx.yml` and `producer.py` |
| 30-day auto-purge | Not started |
| Multi-camera corroboration | Not started |
| Video clip extraction (30-sec clips) | Not started |
| Kubernetes/Docker Swarm orchestration | Not started |

---

## 12. What IS Working & Production-Ready

| Component | Status | Notes |
|-----------|--------|-------|
| Docker Infrastructure (6 containers) | ✅ Working | Milvus + Redis + Postgres + MediaMTX all stable |
| Database Schema + Init Script | ✅ Working | Both Postgres tables + both Milvus collections |
| Live RTSP Ingestion (4 cameras) | ✅ Working | `producer.py` with auto-reconnect |
| AI Face Detection + Embedding | ✅ Working | InsightFace antelopev2, 512-d vectors |
| Milvus Vector Search | ✅ Working | COSINE similarity, IVF_FLAT index |
| Face Deduplication (60s window) | ✅ Working | Prevents database flooding |
| WebRTC Live Streaming | ✅ Working | MediaMTX WHEP protocol, near-zero latency |
| WebSocket Real-Time Alerts | ✅ Working | Redis pub/sub → FastAPI WS → React |
| React Dashboard (4 views) | ✅ Working | Modular, TailwindCSS, Lucide icons |
| Image Search (upload → find matches) | ✅ Working | InvestigatorView → Milvus → sighting cards |
| Person ID Timeline/Dossier | ✅ Working | All sightings for a person across cameras |
| Multi-Person Watchlist | ✅ Working | Enroll, select, activate, detect, alert |
| YOLO Pre-Filter | ✅ Working | Exists and tested, used optionally |
| ByteTrack Person Tracker | ✅ Working | Tested, but currently experimental/unused |
| Night Vision Enhancement | ✅ Working | CLAHE + gamma in `facequalitygate_enhanced.py` |
| Face Quality Gates | ✅ Working | Size, blur, angle, confidence in quality worker |
| Full Pipeline Benchmark Suite | ✅ Working | YOLO → InsightFace → Milvus → Postgres timing |

---

## 13. How to Run the Whole System

```bash
# Step 1: Start infrastructure
docker-compose up -d

# Step 2: Initialize databases (⚠️ DESTRUCTIVE — drops existing data)
cd database_init && python init_db.py

# Step 3: Start the camera ingestion 
cd Ingestion && python producer.py          # Live cameras
# OR: python producer_folder.py             # Offline video files

# Step 4 (Optional): Start YOLO pre-filter
cd ai_worker && python worker_yolo.py

# Step 5: Start the AI face worker
cd ai_worker && python worker_face.py

# Step 6: Start the backend API
cd backend_api && uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload

# Step 7: Start the frontend
cd frontend && npm run dev
```

---

## 14. Known Issues & Technical Debt

1. **3 copies of `yolov8m.pt`** (52MB each) in `ai_worker/`, `tracker/`, `visual_testing/` — should be centralized
2. **`init_db.py` is destructive** — drops Milvus collections on every run. Needs a safe "create-if-not-exists" mode.
3. **`api.py` vs `newapi.py`** — two API files exist. `api.py` is legacy and should be deleted or archived.
4. **`producer_folder.py`** still has old MJPEG Task 2 code (writes to `latest_frame_` Redis key) — dead code since WebRTC migration.
5. **Hardcoded credentials** — Postgres (`admin/password`), Redis (no auth), RTSP camera passwords all in plaintext.
6. **No `.env` file** — All config (URLs, ports, credentials) scattered across multiple Python files.
7. **Face worker reads from `face_ready_queue`** but producer pushes to `raw_frames_queue` — you MUST run `worker_yolo.py` in between, OR change the queue name in the face worker.