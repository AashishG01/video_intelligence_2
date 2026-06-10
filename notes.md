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

---

## 15. Bug Fixes Log

> Tracks confirmed bugs that have been identified and patched. Each entry records the file, the root cause, and the fix applied.

---

### ✅ BUG-001 — `tracker/worker_face.py` : Inverted Cosine Distance Comparison
**Date Fixed:** 2026-05-21  
**File:** `tracker/worker_face.py` — `flush_track_to_database()`, line 123  
**Severity:** 🔴 Critical

#### Root Cause
Milvus returns a **cosine distance** value, where:
- `0.0` = vectors are identical (perfect face match)
- `1.0` = vectors are completely dissimilar (different person)

The original code used `>` to check for a match:

```python
# ❌ WRONG — passes when distance is HIGH (dissimilar faces)
if top['distance'] > MATCH_THRESHOLD:
```

This is completely inverted. It was treating **strangers as known people** (high distance → "match") and **known people as new unknowns** (low distance → "no match"). Every face in the database was effectively being misidentified.

#### Reference
The sibling file `ai_worker/worker_face.py` (line 223) has the correct logic using `<`:
```python
if dist < CURRENT_MATCH_THRESHOLD:  # ✅ Correct in ai_worker
```

#### Fix Applied
```python
# ✅ FIXED — passes when distance is LOW (similar faces = real match)
if top['distance'] < MATCH_THRESHOLD:
```

#### Impact
- **Before fix:** Every face lookup in the ByteTrack pipeline produced wrong results. Known faces were always registered as new unknowns, bloating Milvus and Postgres with duplicate entries. Strangers with a high cosine distance (> 0.50) were incorrectly matched to existing person IDs.
- **After fix:** Face matching in `tracker/worker_face.py` now correctly identifies returning individuals and deduplications work as designed.

---

### ✅ BUG-002 — `ai_worker/worker_face.py` : Wrong Cosine Distance Threshold Value
**Date Fixed:** 2026-05-21  
**File:** `ai_worker/worker_face.py` — configuration block, line 16; usage at lines 177, 223  
**Severity:** 🔴 Critical

#### Root Cause
Milvus `metric_type="COSINE"` returns a **distance** value, not a similarity score:

| Value | Meaning |
|-------|---------|
| `0.0` | Identical faces (perfect match) |
| `0.35` | ~65% cosine similarity — strong match |
| `0.60` | ~40% cosine similarity — barely related |
| `1.0` | Completely different faces |

The original code set:
```python
MATCH_THRESHOLD = 0.60   # Treated as if 0.60 = "60% confident"
```

Because the comparison direction (`<`) is correct for distance, this did *not* invert results — but the **value `0.60` is far too permissive**. It would accept any two faces whose cosine distance is below `0.60`, meaning faces that are only ~40% similar could trigger a watchlist alert. In a busy crowd this produces significant **false positives** — innocent bystanders flagged as watchlist suspects.

The intent was clearly a "60% confident" threshold (treating it like similarity), but the actual cosine distance for 60% similarity is **`0.40`**, and for the recommended stricter surveillance threshold (~65% similarity) it is **`0.35`**.

#### Comparison: Similarity ↔ Distance

```
Similarity  →  Cosine Distance
   50%      →     0.50
   60%      →     0.40
   65%      →     0.35  ← new default (good watchlist gate)
   70%      →     0.30
   80%      →     0.20  ← very strict (few false positives)
```

#### Fix Applied

```python
# ❌ BEFORE — semantically wrong value (too permissive, causes false positives)
MATCH_THRESHOLD = 0.60

# ✅ AFTER — correct cosine DISTANCE value for ~65% similarity gate
# 0.35 distance ≈ 65%+ cosine similarity → tight, production-safe default
MATCH_THRESHOLD = 0.35
```

Clarifying inline comments were also added at both usage sites (watchlist search line 177 and general search line 223) to prevent this mistake recurring.

#### Note on UI Slider
The React settings UI lets operators adjust `GLOBAL_MATCH_THRESHOLD` at runtime via Redis. **If an operator previously saved a threshold of `0.60` via the UI, that Redis value will override the corrected `0.35` default.** The Redis key should be manually reset:
```bash
redis-cli SET GLOBAL_MATCH_THRESHOLD 0.35
```

#### Impact
- **Before fix:** Threshold `0.60` accepted faces with only ~40% cosine similarity, producing false watchlist alerts on faces that only vaguely resembled enrolled suspects.
- **After fix:** Threshold `0.35` requires at least ~65% cosine similarity before triggering a match, dramatically reducing false positives while still catching genuine re-identifications.

---

### ✅ BUG-003 — `backend_api/worker_notify.py` : Plaintext SMTP Password in Source Code
**Date Fixed:** 2026-05-21  
**File:** `backend_api/worker_notify.py` — lines 13–14 (original)  
**Severity:** 🔴 Critical (Security Vulnerability)

#### Root Cause
The Gmail sender address and 16-character App Password were hardcoded directly in the source file:

```python
# ❌ BEFORE — credentials committed to source
SENDER_EMAIL    = "driveblade7@gmail.com"
SENDER_PASSWORD = "rbol hixn fntu rrpy"
```

Any developer with read access to the repository — or anyone who ever sees a git log, a GitHub PR, a pastebinned snippet — immediately has full access to send email from that account. Even if the password is later rotated, it remains in `git log` history permanently unless the repo is force-scrubbed.

#### Fix Applied
Credentials are now loaded exclusively from **environment variables**. The script performs a fast-fail check at startup and refuses to run if either variable is missing, giving a clear error message instead of silently sending from a wrong or empty address.

```python
# ✅ AFTER — credentials from environment, never in source
SENDER_EMAIL    = os.environ.get("SMTP_SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SMTP_APP_PASSWORD")

if not SENDER_EMAIL or not SENDER_PASSWORD:
    raise EnvironmentError("SMTP credentials not set! Set SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD.")
```

#### How to Set Credentials Before Running

**Option A — Export in terminal (session-scoped)**
```bash
# Linux / macOS
export SMTP_SENDER_EMAIL="you@gmail.com"
export SMTP_APP_PASSWORD="xxxx xxxx xxxx xxxx"
python worker_notify.py

# Windows CMD
set SMTP_SENDER_EMAIL=you@gmail.com
set SMTP_APP_PASSWORD=xxxx xxxx xxxx xxxx
python worker_notify.py

# Windows PowerShell
$env:SMTP_SENDER_EMAIL="you@gmail.com"
$env:SMTP_APP_PASSWORD="xxxx xxxx xxxx xxxx"
python worker_notify.py
```

**Option B — `.env` file (recommended for local dev)**
1. Install `python-dotenv`: `pip install python-dotenv`
2. Create a `.env` file in the project root (already in `.gitignore`):
```
SMTP_SENDER_EMAIL=you@gmail.com
SMTP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```
3. Add at the top of `worker_notify.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```

**Option C — PM2 / ecosystem.config.js (production)**  
Add the variables to the `env` block in [`ecosystem.config.js`](file:///c:/Users/Hp/Desktop/video_intelligence_2/ecosystem.config.js):
```js
env: {
  SMTP_SENDER_EMAIL: "you@gmail.com",
  SMTP_APP_PASSWORD: "xxxx xxxx xxxx xxxx"
}
```
> [!CAUTION]  
> Do NOT commit `ecosystem.config.js` with real credentials. Use PM2's `--env` flag or a secrets manager instead.

#### Action Required
1. **Revoke the leaked App Password immediately** in your Google Account → Security → App Passwords.
2. Generate a new App Password and set it via environment variable as shown above.
3. If this repo was ever pushed to GitHub (public or private), assume the old password is compromised.

#### Impact
- **Before fix:** Gmail App Password visible to anyone reading the source file. Could be used to send phishing/spam email from the account.
- **After fix:** No credentials exist anywhere in source code or git history (from this point forward). The process fails loudly at startup if credentials are missing, preventing silent misconfiguration.

---

### ✅ BUG-004 — `backend_api/auth.py` : Hardcoded JWT Secret Key
**Date Fixed:** 2026-05-21  
**File:** `backend_api/auth.py` — line 8 (original)  
**Severity:** 🔴 Critical (Security Vulnerability)

#### Root Cause
The JWT signing key was hardcoded as a string literal in source code:

```python
# ❌ BEFORE — key committed to source
SECRET_KEY = "core_surveillance_absolute_zero_trust_key"
```

JWT tokens are signed with this key. Anyone who knows the key can **forge valid tokens** for any username and role (including `admin`) without ever logging in. Because the key was in source code:
- Every developer with repo access knows it
- Every git clone, fork, or GitHub mirror permanently contains it
- Static analysis tools and secret scanners would flag it instantly

#### Fix Applied
`SECRET_KEY` is now read exclusively from the `JWT_SECRET_KEY` environment variable. The module raises `RuntimeError` at **import time** if the variable is missing — meaning `uvicorn` will refuse to start rather than serve an API with a broken or known-weak signing key.

```python
# ✅ AFTER — key from environment, never in source
import os

SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set! ..."
    )
```

#### Generating a Strong Secret Key
The old key was a plain English phrase — easy to guess and not cryptographically random. Use Python's `secrets` module to generate a proper 256-bit key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Example output: a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8
```

#### How to Set the Key Before Running

**Option A — Export in terminal**
```bash
# Linux / macOS
export JWT_SECRET_KEY="a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8"
uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload

# Windows CMD
set JWT_SECRET_KEY=a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8
uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload

# Windows PowerShell
$env:JWT_SECRET_KEY="a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8"
uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload
```

**Option B — `.env` file (recommended for local dev)**
```
# .env  (this file must be in .gitignore)
JWT_SECRET_KEY=a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8
SMTP_SENDER_EMAIL=you@gmail.com
SMTP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```
Add `from dotenv import load_dotenv; load_dotenv()` at the top of `newapi.py`.

**Option C — PM2 `ecosystem.config.js` (production)**
```js
env: {
  JWT_SECRET_KEY: "a3f9c2e1b7d4082f6a1c3e5d9f2b4a6c8e0d2f4b6a8c0e2d4f6b8a0c2e4f6b8"
}
```

#### ⚠️ Important: Token Invalidation Side-Effect
Changing the secret key **immediately invalidates all existing JWT tokens**. Every logged-in operator will be logged out and must re-authenticate. This is expected and correct behaviour — it also invalidates any tokens that may have been forged using the old key.

#### Impact
- **Before fix:** Any person who reads the source file can craft a valid admin JWT token and gain full API access — including enrolling watchlist suspects, deleting data, and arming/disarming the system.
- **After fix:** The key is never stored in source. The API refuses to boot without it. Tokens cannot be forged without access to the runtime secret.

---

### ✅ BUG-005 — `backend_api/newapi.py` : New DB Connection Per Request (No Pooling)
**Date Fixed:** 2026-05-21  
**File:** `backend_api/newapi.py` — lines 76–77 (original)  
**Severity:** 🔴 Critical (Performance / Reliability)

#### Root Cause
Every API endpoint called a bare `psycopg2.connect()` that opened a fresh TCP connection to PostgreSQL and closed it when the request finished:

```python
# ❌ BEFORE — full TCP handshake on every single request
def get_pg_connection():
    return psycopg2.connect(
        dbname="surveillance", user="admin",
        password="password", host="localhost", port="5432"
    )
```

Under concurrent load this causes two compounding problems:

| Problem | Detail |
|---------|--------|
| **Latency** | Each request pays ~5–20 ms for a TCP + PostgreSQL auth handshake before executing any SQL |
| **Connection exhaustion** | PostgreSQL's default `max_connections = 100`. With 50 concurrent API requests each holding a connection, plus the psycopg2 workers in the AI pipeline, the limit is hit and new connections fail with `FATAL: remaining connection slots are reserved for non-replication superuser connections` |

#### Fix Applied
A `psycopg2.pool.ThreadedConnectionPool` is now initialised once at module startup. A thin `_PooledConn` wrapper class intercepts `.close()` to **return** the connection to the pool instead of destroying it — meaning **every existing `conn.close()` call site** across all 18+ endpoints continues to work with **zero modifications**.

```python
# ✅ AFTER — persistent pool, borrowed per request
from psycopg2.pool import ThreadedConnectionPool

_pg_pool = ThreadedConnectionPool(minconn=2, maxconn=10, **_PG_DSN)

class _PooledConn:
    def close(self):                           # returns to pool, doesn't destroy
        _pg_pool.putconn(self._conn)
    def __enter__(self): return self
    def __exit__(self, exc_type, *_):
        if exc_type: self._conn.rollback()
        self.close()
    def __getattr__(self, name):               # forwards cursor(), commit(), etc.
        return getattr(self._conn, name)

def get_pg_connection() -> _PooledConn:
    return _PooledConn(_pg_pool.getconn())
```

#### Pool Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `minconn` | `2` | Always keep 2 connections warm — first requests after idle don't pay handshake cost |
| `maxconn` | `10` | Hard ceiling — requests queue instead of spawning unlimited connections. Leaves headroom for AI workers and direct `psql` sessions. |

Tune `maxconn` higher if you add more concurrent workers, but always ensure `total connections across all processes < PostgreSQL max_connections`.

#### Why `ThreadedConnectionPool` and not `asyncpg`?
`newapi.py` uses synchronous `psycopg2` throughout (`RealDictCursor`, `conn.autocommit`, etc.). Migrating to `asyncpg` would require rewriting every query. `ThreadedConnectionPool` achieves the primary goal — no new TCP connection per request — with zero call-site changes, making it the safe incremental fix.

#### Context-Manager Bonus
`_PooledConn` also supports `with get_pg_connection() as conn:` for automatic rollback + pool-return on exceptions. New endpoints should prefer this pattern.

#### Impact
- **Before fix:** Every request opened and tore down a raw TCP connection to PostgreSQL, adding 5–20 ms latency and risking connection limit exhaustion under concurrent load.
- **After fix:** The pool keeps 2–10 connections alive permanently. Requests borrow a connection in microseconds and return it atomically on `conn.close()` or context-manager exit.

---

### ✅ BUG-006 — System Disarm Silences UI Sidebar & Backend Email Worker
**Date Fixed:** 2026-05-21  
**Files:** `ai_worker/worker_face.py`, `frontend/src/pages/Dashboard.jsx`, `backend_api/worker_notify.py`  
**Severity:** 🟡 High (UX / Functional)

#### Root Cause
When the system was "Disarmed" via the Kill Switch in the UI, the backend (`ai_worker/worker_face.py`) would completely stop publishing events to the `live_face_alerts` Redis channel:

```python
# ❌ BEFORE: Disarming stopped all WebSocket broadcasts
if is_armed:
    r_pub.publish("live_face_alerts", json.dumps(alert_payload))
```

This successfully silenced the flashing red modal and sirens, **but** it also caused the "Live Intel Feed" sidebar in the UI to freeze, making it look like the cameras/AI had stopped working. Additionally, the email worker (`worker_notify.py`) wasn't checking the armed state itself; it relied entirely on the fact that `worker_face.py` wasn't sending messages.

#### Fix Applied
The architecture was changed so that `worker_face.py` **always** publishes to the WebSocket (keeping the sidebar feed alive), but it now explicitly includes an `"is_armed"` boolean in the JSON payload. The downstream consumers (the UI and the email worker) now read this flag to decide whether to trigger the aggressive alerts.

**1. `ai_worker/worker_face.py`**
```python
# ✅ AFTER: Always broadcast, but tell the UI the system state
alert_payload = {
    ...
    "is_armed": is_armed
}
r_pub.publish("live_face_alerts", json.dumps(alert_payload))
```

**2. `frontend/src/pages/Dashboard.jsx`**
```javascript
// ✅ AFTER: Only trigger the full-screen modal & siren if armed
if (data.status === "WATCHLIST_MATCH" && data.is_armed === true) {
    setCriticalAlert(data);
    ...
}
```

**3. `backend_api/worker_notify.py`**
```python
# ✅ AFTER: Skip sending emails if the system is disarmed
if alert.get('status') == 'WATCHLIST_MATCH':
    if not alert.get('is_armed', True):
        continue # Skip email
```

#### Impact
- **Before fix:** Disarming the system froze the "Live Intel Feed" sidebar in the UI.
- **After fix:** The Live Intel Feed continues to scroll with all detected faces (including Watchlist suspects), but the full-screen flashing red modal, sirens, and email notifications remain strictly disabled while the system is disarmed.

---

### ✅ BUG-007 — Cooldown Race Condition Allowed Suspects to Bypass Red Alert
**Date Fixed:** 2026-05-21  
**Files:** `ai_worker/worker_face.py`  
**Severity:** 🔴 Critical (Security Loophole)

#### Root Cause
The AI worker had a single, universal 60-second cooldown lock (`alert_cooldown_{person_id}`) placed at the very beginning of the face processing loop (before the armed/disarmed check). 

If a Watchlist suspect walked past a camera while the system was **Disarmed**:
1. The system acquired the 60-second cooldown lock.
2. It saved the image and silently pushed to the UI sidebar.
3. 10 seconds later, an Admin clicked **ARM SYSTEM**.
4. 5 seconds later, the suspect was still standing in front of the camera.
5. The AI worker detected the face again, but the 60-second cooldown lock was still active (45s remaining).
6. The system **completely skipped processing**. It didn't trigger the red modal, didn't sound the siren, and didn't send an email.

The operator would completely miss a critical suspect because the suspect happened to trigger a "silent" cooldown while the system was disarmed.

#### Fix Applied
The single cooldown was split into two logically distinct locks:

**1. DB Deduplication Lock (`db_cooldown_{person_id}`)**
- **Always runs** regardless of armed state.
- Prevents saving the exact same person to PostgreSQL and Milvus 30 times a second.

**2. Alert Deduplication Lock (`alert_cooldown_{person_id}`)**
- **Only locks if the system is ARMED.**
- If the system is Disarmed, it intentionally skips acquiring this lock.

```python
# ✅ AFTER: Alert lock only applies when armed
system_status = r.get("system_armed")
is_armed = system_status is None or system_status.decode('utf-8') == "1"

# 1. DB Deduplication (Always)
if r.exists(f"db_cooldown_{person_id}"): continue 
r.setex(f"db_cooldown_{person_id}", 60, "1")

# 2. Alert Deduplication (Armed Only)
if is_armed:
    if r.exists(f"alert_cooldown_{person_id}"):
        pass # Skip broadcast
    else:
        r.setex(f"alert_cooldown_{person_id}", 60, "1")
```

#### Impact
- **Before fix:** A suspect seen while the system was disarmed would be "invisible" to alarms for 60 seconds, even if the system was re-armed immediately.
- **After fix:** Re-arming the system provides **immediate** protection. If a suspect is in frame the millisecond the "Arm System" button is clicked, the red modal and sirens will trigger instantly.

---

### ✅ BUG-008 — Missing Sighting Insert for Watchlist Matches
**Date Fixed:** 2026-05-21  
**Files:** `ai_worker/worker_face.py`  
**Severity:** 🟡 High (Data Missing)

#### Root Cause
The PostgreSQL `INSERT INTO sightings` statement was nested inside the `if not is_watchlist_match:` block. When a Watchlist match was detected, their face embedding correctly skipped the general DB, but their physical sighting record (camera ID, timestamp, image path) was skipped as well. This made Watchlist suspects completely invisible in the frontend Investigator timeline.

#### Fix Applied
Moved the PostgreSQL `INSERT` block outside the `if not is_watchlist_match:` block, ensuring that every detected face—whether known or unknown—gets a timestamped sighting record in the database.

---

### ✅ BUG-009 — Milvus flush() Called Per-Frame Caused Performance Bottleneck
**Date Fixed:** 2026-05-21  
**Files:** `ai_worker/worker_face.py`  
**Severity:** 🔴 Critical (Performance)

#### Root Cause
`milvus_client.flush(collection_name=COLLECTION_NAME)` was being called explicitly after every single face insertion. Flushing forces Milvus to seal segments and persist data to disk immediately. Doing this per-frame blocked the worker for hundreds of milliseconds per face, causing massive queue build-ups and stream lag.

#### Fix Applied
Removed the `flush()` call entirely. Milvus handles background flushing automatically when segments reach their configured sizes or time limits, which provides orders-of-magnitude higher ingestion throughput.

---

### ✅ BUG-010 — Tracker Worker Crashed on Empty Queue Timeout
**Date Fixed:** 2026-05-21  
**Files:** `tracker/worker_face.py`  
**Severity:** 🔴 Critical (Crash loop)

#### Root Cause
The tracker used `queue_name, msg = r.brpop("face_ready_queue", timeout=1)`. When the queue was empty and the 1-second timeout expired, Redis returned `None`. Python threw a `TypeError: cannot unpack non-iterable NoneType object`, crashing the worker entirely.

#### Fix Applied
Changed the logic to first capture the return value into a single variable, check if it's truthy, and only then unpack it:
```python
result = r.brpop("face_ready_queue", timeout=1)
if result:
    queue_name, msg = result
```

---

### ✅ BUG-011 — WebSocket Memory Leak (Unclosed PubSub)
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 High (Memory Leak)

#### Root Cause
In the `/ws/live_alerts` route, `pubsub.unsubscribe()` was only called if a specific `WebSocketDisconnect` exception was raised. If the connection dropped due to any other exception (network reset, Redis timeout, server error), the `pubsub` connection was never closed. Over time, this leaks Redis pubsub subscriptions, eventually exhausting Redis memory or connection limits.

#### Fix Applied
Wrapped the unsubscription logic in a `finally` block to guarantee it runs regardless of how the connection ends, and added `pubsub.close()` to ensure the underlying socket is released back to the system.
```python
finally:
    pubsub.unsubscribe()
    pubsub.close()
```

---

### ✅ BUG-012 — Frame Skip Division by Zero
**Date Fixed:** 2026-05-21  
**Files:** `ingestion/producer_folder.py`  
**Severity:** 🔴 Critical (Crash)

#### Root Cause
The formula `frames_to_skip = int(video_fps * self.process_every_n_seconds)` could evaluate to `0` for low-framerate videos (e.g., `0.5 FPS * 1 sec = 0.5 -> int(0.5) = 0`). This caused a `ZeroDivisionError` on the very next line (`if frame_counter % frames_to_skip != 0:`), instantly crashing the ingestion thread for that video.

#### Fix Applied
Added a `max(1, ...)` ceiling to ensure `frames_to_skip` is never less than 1. This guarantees that modulo operations are always safe, even for sub-1 FPS video files.
```python
frames_to_skip = max(1, int(video_fps * self.process_every_n_seconds))
```

---

### ✅ BUG-013 — Duplicate & Cluttered Imports
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟢 Low (Code Quality)

#### Root Cause
`newapi.py` had multiple duplicate imports scattered across the top of the file (e.g., `psycopg2` imported twice, `fastapi` imported twice with different submodules). This can lead to silent overrides or missing modules if developers clean up one import line but not the other.

#### Fix Applied
Cleaned up lines 1–26 of `newapi.py`. Consolidated all `fastapi` and `psycopg2` imports into single statements, and removed the duplicate `pydantic` lines. The import block is now clean and maintainable.

---

### ✅ BUG-014 — Synchronous Generator Blocked Async Event Loop
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 High (Performance)

#### Root Cause
The `generate_mjpeg` function, which streams the latest video frames from Redis to the frontend via HTTP MJPEG, was a synchronous generator that used `time.sleep(0.1)` while waiting for new frames. Because it was wrapped directly in a `StreamingResponse` inside an `async def video_stream` endpoint without offloading to a threadpool correctly, the 100ms blocking sleep choked the main FastAPI event loop, causing the API to hang and drop requests during stream buffering.

#### Fix Applied
Converted `generate_mjpeg` into a native asynchronous generator (`async def`) and replaced the blocking `time.sleep(0.1)` with the non-blocking `await asyncio.sleep(0.1)`. The stream now yields execution back to the event loop, completely restoring API concurrency.

---

### ✅ BUG-015 — Deprecated `@app.on_event("startup")` Used for DB Checks
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟢 Low (Tech Debt / Deprecation)

#### Root Cause
The `startup_db_check` function (which ensures PostgreSQL tables exist) used the `@app.on_event("startup")` decorator. This lifecycle decorator was heavily deprecated in FastAPI `v0.93.0` and can cause instability or warnings in modern deployments.

#### Fix Applied
Refactored the application lifecycle to use the modern `lifespan` async context manager.
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_db_check()
    yield

app = FastAPI(title="C.O.R.E. Surveillance API", version="3.1", lifespan=lifespan)
```

---

### ✅ BUG-016 — DB Connection Drop Silently Swallowed by AI Worker
**Date Fixed:** 2026-05-21  
**Files:** `ai_worker/worker_face.py`  
**Severity:** 🟡 High (Auto-Recovery Failure)

#### Root Cause
If the AI worker lost connection to PostgreSQL while fetching a Watchlist suspect's name, the `try/except` block simply printed a warning, set the name to the ID, and continued processing. Because the exception was "swallowed," the main outer loop's auto-healing mechanism (`elif "connection" in error_msg.lower()`) was never triggered. The worker would stay online but permanently fail to fetch suspect names.

#### Fix Applied
Added a `raise db_err` statement inside the inner exception block. Now, if the database drops, the exception propagates up to the main loop, triggering the automatic connection rebuild process.

---

### ✅ BUG-017 — Tracker Worker Saved to Orphaned `4_backend_api` Folder
**Date Fixed:** 2026-05-21  
**Files:** `tracker/worker_face.py`  
**Severity:** 🟢 Low (Path Error)

#### Root Cause
`SAVE_FOLDER` was hardcoded to `../4_backend_api/captured_faces`. However, the actual backend directory is named `backend_api`. The tracker was silently creating an orphaned directory and saving all images there, meaning the FastAPI server couldn't serve them to the frontend.

#### Fix Applied
Updated the path to `../backend_api/captured_faces` to correctly map to the shared volume.

---

### ✅ BUG-018 — Image Search API Silently Hid Milvus Crashes
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 High (Silent Failure)

#### Root Cause
The `/api/investigate/search_by_image` endpoint caught all Milvus search exceptions and returned `{"suspect_found": False...}`. The frontend user had no way to distinguish between "this person was never seen" and "the Milvus vector database is completely down."

#### Fix Applied
Replaced the silent fallback with a proper `raise HTTPException(status_code=500, detail="Database search failed.")`. The React UI will now show an actual system error instead of lying to the user.

---

### ✅ BUG-019 — Settings API Returned 200 Success on Failed Database Updates
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 Medium (False Positive)

#### Root Cause
The `/api/settings/alerts` route explicitly ignored PostgreSQL and Redis update exceptions (`pass`) and always returned `{"status": "success"}`. The user would believe their settings (like notification emails or siren triggers) were saved when they actually failed.

#### Fix Applied
Removed the `pass` statements. If either the Redis cache or PostgreSQL permanent storage fails to update, the API now immediately raises an HTTP 500 error, ensuring the frontend reflects the failure.

---

### ✅ BUG-020 — `list_subjects` Hid Newly Enrolled Subjects 
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🔴 Critical (UI Data Missing)

#### Root Cause
The SQL query used `INNER JOIN` for `watchlist_members` and `watchlist_categories`, along with `WHERE wm.is_active = TRUE`. This meant that any subject who wasn't currently assigned to an active category was entirely excluded from the results. You could enroll a suspect, but if you didn't check a category box, they disappeared from the UI list.

### ✅ BUG-021 — Notification Worker Redis Crash Loop
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/worker_notify.py`  
**Severity:** 🔴 Critical (Notification Outage)

#### Root Cause
The `pubsub.listen()` loop did not have an outer `try/except` block protecting the Redis connection. If the Redis server briefly restarted or the TCP connection dropped, the script would throw a `redis.ConnectionError`, completely crash, and exit. This would silently disable all threat emails until an admin noticed and manually restarted the script.

#### Fix Applied
Moved the Redis connection initialization inside a `while True` loop and wrapped the `pubsub.listen()` block in a `try/except` clause. If the connection drops, the worker will now gracefully catch the error, wait 5 seconds, and automatically reconnect to Redis to resume listening for alerts.

### ✅ BUG-022 — Inaccurate "Active Cameras" Stat
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 Moderate (Data Inaccuracy)

#### Root Cause
The `/api/system/stats` endpoint was calculating the number of active cameras by counting unique `camera_id`s in the historical `sightings` table. This meant new cameras wouldn't appear in the stats until they detected a face, and deleted cameras would continue to inflate the number forever.

#### Fix Applied
Updated the SQL query to pull directly from the new `cameras` table using `SELECT COUNT(id) FROM cameras WHERE is_active = TRUE`. The UI now perfectly reflects the actual number of online RTSP streams.

### ✅ BUG-023 — Split-Brain Watchlist (Ghost Suspects)
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`, `ai_worker/worker_face.py`  
**Severity:** 🔴 Critical (Data Integrity)

#### Root Cause
The system had two separate Watchlist tables (`watchlist` and `subjects`). The legacy `/api/watchlist/add` endpoints were never deleted, and the AI worker had fallback logic to check the old table. This allowed ghosts to exist in the system and trigger alarms without appearing in the Admin Dashboard.

#### Fix Applied
Permanently deleted all legacy `/api/watchlist/*` endpoints, removed the old table creation from the database bootstrapper, and stripped the fallback query out of the AI worker. The system now strictly relies on the new Enterprise `subjects` table.

### ✅ BUG-024 — Unvalidated Camera Limits (Infinite FPS Exploit)
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 High (Denial of Service)

#### Root Cause
The Camera addition API blindly accepted any integer for `fps_limit`. An operator entering `0` or `99999` would cause the ingestion engine to crash via a divide-by-zero or max out the system CPU.

#### Fix Applied
Implemented a Pydantic `CameraConfig` model with strict bounds: `fps_limit` is now strictly enforced to be an integer between 1 and 30.

### ✅ BUG-025 — Silent Overwrite on Camera Enrollments
**Date Fixed:** 2026-05-21  
**Files:** `backend_api/newapi.py`  
**Severity:** 🟡 High (Data Loss)

#### Root Cause
The `/api/cameras/add` endpoint used `ON CONFLICT DO UPDATE` in its SQL statement. If an operator accidentally typed the ID of an existing camera while trying to add a new one, the backend would silently overwrite the existing feed, breaking the historical sighting map without throwing an error.

#### Fix Applied
Changed the SQL statement to a standard `INSERT` and added a `try/except` block to catch `psycopg2.IntegrityError`. The API now safely returns a `400 Bad Request: Camera ID already exists` error, completely preventing accidental overwrites.




The ghost embeddings are still physically sitting inside your Milvus watchlist_faces collection. The fix above just ignores them at runtime. To permanently purge them, you still need to run python nuke_system.py on your lab machine. That will drop the entire Milvus collection and give you a completely clean slate.

### 🐛 BUG-026 — Milvus Cosine Metric Inversion Bug
**Date Fixed:** 2026-06-10  
**Files:** `backend_api/newapi.py`  
**Severity:** 🔴 High (False Positives / Logic Error)

#### Root Cause
When Milvus is configured with `metric_type="COSINE"`, the `distance` field returned in the search results is actually the **Cosine Similarity** (where higher is better, ranging up to 1.0), not the Cosine Distance (where smaller is better). 

The `/api/investigate/search_by_image` endpoint was incorrectly treating the result as a true distance. The filter logic `match['distance'] <= (1.0 - threshold)` actively filtered OUT high-similarity matches and ONLY returned faces with a similarity score below 0.40 (i.e. terrible matches). When mapping this score to the UI, the frontend displayed these terrible matches as "High Matches" due to an inverted math correction (`1.0 - distance`), leading to completely mismatched suspect faces showing 80% similarity.

#### Fix Applied
Rewrote the threshold filtering logic in `newapi.py` to natively use the similarity metric: `if match['distance'] >= threshold:`. The raw similarity score is now correctly passed directly to the `match_score` field without inversion, allowing the `InvestigatorView` to accurately label and display matches.
