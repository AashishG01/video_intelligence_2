# 🎯 Surat City Video Surveillance & Person Tracking System — Revised Project Plan v2

> **Revision Date:** March 26, 2026  
> **Revision Notes:** Consolidated plan incorporating original architecture, existing code audit, Indian street density analysis, and real client footage analysis. All compute estimates revised for ground reality.

---

## 1. Executive Summary

**Client:** Private company operating under contract with Surat Police  
**Objective:** Build an on-premise, end-to-end person tracking system integrated with 2000+ surveillance cameras across Surat  
**Timeline:** 6 Months (April 2026 – September 2026)  
**Lead Developer:** You (+ team of batchmates/juniors as needed)  
**Delivery Model:** Build & hand-off — client handles legal/operational matters

### What The System Does

1. **Upload a photo** of a missing/blacklisted person
2. **Search 30 days of stored footage** (30 PB on-premise) to find every appearance
3. **Track in real-time** across 2000+ live camera streams
4. **Build a city-wide person database** — embeddings of every detected person, searchable instantly
5. **Display movement timeline** — where the person was seen, when, on which camera, with map visualization

### Current Status (What's Already Built)

A validated proof-of-concept exists with:
- ✅ 4-camera RTSP ingestion with threaded readers
- ✅ GPU-accelerated face detection + 512-d embedding (InsightFace AntelopeV2)
- ✅ ChromaDB vector storage with cosine similarity + person clustering
- ✅ Accuracy tested on real Surat footage (86-90% at threshold 0.55-0.60)
- ✅ Night vision enhancement pipeline (CLAHE, gamma correction)
- ✅ GPU/CPU benchmarking scripts
- ✅ Basic Streamlit dashboard + Docker Compose

**What Remains:** ~85-90% of the production system (backend API, React dashboard, Milvus, Kafka, Triton, DeepStream, Kubernetes, auth, monitoring, and scaling to 2000 cameras).

---

## 2. Infrastructure Context

| Parameter | Detail |
|---|---|
| **Cameras** | 2000+ Verint Nextiva S5120 |
| **Resolution** | 1920×1080 @ 30fps, H.264, RTSP/RTP |
| **Bandwidth per camera** | Up to 8 Mbps (full) / 1-2 Mbps (ML sub-stream) |
| **Total raw bandwidth** | ~16 Gbps (full) / ~4 Gbps (ML sub-streams) |
| **Dual streaming** | ✅ Supported (low-res 480p for ML, high-res for storage) |
| **Storage** | ~30 PB on-premise, 30-day retention |
| **Network** | Fully air-gapped local network, no internet |
| **GPU available (dev)** | NVIDIA RTX A6000 |
| **GPU planned (prod)** | 4× NVIDIA A100 80GB (expandable to 8×) |
| **Prod server** | 2× AMD EPYC 9354 (32c each), 512GB–1TB DDR5, 8-16TB NVMe SSD RAID, 2×25GbE NICs |
| **Accuracy target** | 75–90% across the journey (not per-frame) |
| **Deployment** | On-premise only, no cloud |

---

## 3. Ground Reality — Indian Street Density Analysis

> **The most critical factor that shapes the entire architecture.** These are real observations from client footage.

### What The Cameras Actually See

| Location Type | Typical People/Frame | Usable Faces (>40px, frontal) | Face Yield |
|---|---|---|---|
| **Dense markets** (Mahidharpura) | 150-200+ | 8-12 | ~5-8% |
| **Major chaurahas** (Majura Gate) | 50-200 | 10-20 | ~10-15% |
| **Auto-rickshaw zones** | 12-15 | 3-4 | ~25% |
| **Moderate streets** | 6-10 | 4-6 | ~60-70% |
| **Vehicle-heavy roads** | 10-15 | 2-3 | ~15-20% |
| **Residential areas** | 5-10 | 3-5 | ~50% |

### Key Observations from Real Client Footage

1. **Auto-rickshaws block 30-50% of pedestrian visibility** — this is Surat's #1 occlusion problem
2. **Most faces in dense scenes are <30px** — too small for reliable embedding. Only near-camera faces are usable
3. **~30% of visible people are helmeted two-wheeler riders** — completely unmatchable by face
4. **People frequently look down at phones** — system must wait for them to look up in subsequent frames
5. **Some cameras are vehicle-dominated** — these should be treated differently (lower processing priority or ANPR focus)
6. **Proven by own data:** Mahidharpura test extracted 3,246 faces from ONE video with aggressive thresholds (MIN_FACE_SIZE=15px, CONFIDENCE=0.35)

### Revised Compute Estimates (Realistic)

```
NAIVE ESTIMATE (if processing every face):
  2000 cameras × 100 avg people × 3 FPS = 600,000 faces/sec → IMPOSSIBLE

REALISTIC ESTIMATE (after quality filtering + tiered processing):
  Usable high-quality embeddings/sec across 2000 cameras: ~8,000-15,000
  Daily new vectors stored (after temporal dedup): ~30-50 million
  30-day total vectors: ~1-1.5 billion → FEASIBLE with Milvus + proper indexing
```

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CAMERA NETWORK (2000+)                             │
│  Verint S5120 + potentially other models                               │
│  RTSP dual streams (1080p storage + 480p/CIF ML)                      │
│  Tiered by density: T1 (dense) / T2 (moderate) / T3 (light)          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ RTSP streams (480p sub-stream)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               STREAM INGESTION LAYER                                   │
│  NVIDIA DeepStream SDK / GStreamer pipelines                           │
│  ├── Hardware-accelerated decode (NVDEC on GPU)                       │
│  ├── Codec-agnostic: H.264, H.265, MJPEG auto-detected               │
│  ├── Tiered frame sampling:                                            │
│  │   ├── T1 Dense (chaurahas, stations): 1 FPS, faces >60px only     │
│  │   ├── T2 Moderate (main roads): 2 FPS, faces >40px               │
│  │   └── T3 Light (residential): 3 FPS, all faces >25px             │
│  ├── ROI-based detection (skip sky/road/buildings)                    │
│  ├── Motion detection pre-filter (skip static scenes)                 │
│  └── Output → Apache Kafka (partitioned by camera group)              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ Sampled frames (with motion + people)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│         NVIDIA TRITON INFERENCE SERVER (Multi-GPU Model Serving)       │
│  Dynamic batching, multi-model, hot-swapping, model versioning        │
│                                                                        │
│  ┌────────────────────── GPU 0-1 ──────────────────────┐              │
│  │  PERSON DETECTION: YOLOv8-L (TensorRT FP16)        │              │
│  │  Input: 640×640 | Output: person bboxes             │              │
│  │  Filter: class "person", conf > 0.5                 │              │
│  │  Adaptive: if >50 people, process nearest 30 only   │              │
│  └─────────────────────────────────────────────────────┘              │
│                          │ Cropped person images                       │
│                          ▼                                             │
│  ┌────────────────────── GPU 2 ────────────────────────┐              │
│  │  FACE DETECTION: RetinaFace (5-point landmark)      │              │
│  │  FACE QUALITY: blur, angle, occlusion scoring       │              │
│  │  FACE EMBEDDING: AdaFace (512-d vector)             │              │
│  │  (Face-only matching — no body Re-ID)               │              │
│  │  NIGHT ENHANCE: CLAHE + gamma (when needed)         │              │
│  └─────────────────────────────────────────────────────┘              │
│                          │                                             │
│  ┌── TEMPORAL DEDUPLICATION ──────────────────────────┐               │
│  │  Before storing: check if same person seen in last  │               │
│  │  30 sec on same camera. If yes → update last_seen   │               │
│  │  only. If no → store new embedding.                 │               │
│  │  Reduces storage by 90%+ for static/slow crowds.    │               │
│  └────────────────────────────────────────────────────┘               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ De-duplicated embeddings + metadata
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 VECTOR DATABASE LAYER (GPU 3)                          │
│  Milvus 2.x (GPU-accelerated) + FAISS backend                        │
│  ├── Primary collection: all face embeddings                          │
│  ├── Watchlist collection: hot in GPU memory for real-time matching   │
│  ├── Index: IVF_PQ (512-d → 64 bytes compressed)                    │
│  ├── Partitioned by day (30 partitions, drop day-31)                 │
│  └── Search: top-K ANN in <200ms at billion scale                    │
│                                                                        │
│  Metadata: PostgreSQL + TimescaleDB (time-series optimized)           │
│  Thumbnails/Crops: MinIO (on-premise S3-compatible)                   │
│  Video Clips: 30-sec clips from matched moments                       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐       │
│  │ REST API     │  │ WebSocket    │  │ Background Workers      │       │
│  │ (FastAPI)    │  │ (Real-time   │  │ (Celery + Redis)        │       │
│  │ - Upload     │  │  alerts)     │  │ - Batch processing      │       │
│  │ - Search     │  │ - Live       │  │ - Historical search     │       │
│  │ - Track      │  │   tracking   │  │ - Report generation     │       │
│  │ - Watchlist  │  │              │  │ - Video clip extract    │       │
│  │ - Reports    │  │              │  │ - Data cleanup          │       │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘       │
│                                                                        │
│  FALSE POSITIVE SAFEGUARDS:                                            │
│  ├── Confidence bands: GREEN (>0.85) / YELLOW (0.75-0.85) / RED      │
│  ├── Human-in-the-loop: operator MUST verify before escalating        │
│  ├── Multi-camera corroboration (2+ cameras = higher confidence)      │
│  └── False positive feedback loop → threshold tuning                   │
│                                                                        │
│  AUDIT & COMPLIANCE (DPDP Act 2023):                                   │
│  ├── Every query: officer_id + reason + timestamp + results logged    │
│  ├── RBAC: Admin / Operator / Viewer / Auditor                        │
│  ├── 30-day hard auto-purge (no admin override)                       │
│  └── Export watermarks (officer_id + timestamp on every PDF/CSV)      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FRONTEND DASHBOARD (React.js)                      │
│  ├── Photo upload & search with side-by-side comparison               │
│  ├── Interactive Surat city map (Leaflet/MapLibre GL)                 │
│  ├── Person movement timeline visualization                           │
│  ├── Real-time alert panel with human-in-the-loop confirmation        │
│  ├── Watchlist management                                              │
│  ├── 30-sec video clip playback from matched moments                  │
│  ├── PDF report export (court-ready investigation reports)            │
│  ├── Camera status monitoring                                          │
│  └── Festival Mode toggle (admin)                                      │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐
│        ORCHESTRATION LAYER            │
│  Kubernetes (on-prem) / Docker Swarm  │
│  ├── Service auto-scaling             │
│  ├── GPU resource management          │
│  ├── Health checks + auto-restart     │
│  └── Rolling updates (zero downtime)  │
└──────────────────────────────────────┘
```

### Database Schema (PostgreSQL + TimescaleDB)

| Table | Key Columns | Purpose |
|---|---|---|
| `cameras` | id, name, location_lat/lng, rtsp_url, status, zone, tier (T1/T2/T3), manufacturer, codec, roi_config | Camera registry with density tier + ROI |
| `persons` | id, embedding_ref, first_seen, last_seen, cluster_id, is_watchlisted, face_quality_avg | City-wide person database |
| `sightings` | id, person_id, camera_id, timestamp, bbox, confidence, thumbnail_path, video_clip_path | Hypertable (TimescaleDB), partitioned by time |
| `watchlist` | id, name, photo_path, embedding_ref, category [missing\|criminal\|vip], added_by, active | Active watchlist |
| `alerts` | id, watchlist_id, sighting_id, camera_id, timestamp, confidence, acknowledged, acknowledged_by, false_positive_flag, action_taken | Alert with human-in-the-loop tracking |
| `search_logs` | id, query_photo, results_count, searched_by, officer_id, reason, searched_at | DPDP Act audit trail |
| `model_versions` | id, model_name, version, deployed_at, accuracy_metrics, active | Triton hot-swap tracking |

---

## 5. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Stream Ingestion | **NVIDIA DeepStream SDK** + GStreamer | GPU-accelerated decode (NVDEC), codec-agnostic, multi-stream batching |
| Model Serving | **NVIDIA Triton Inference Server** | Dynamic batching, multi-model, hot-swap, model versioning |
| Message Queue | **Apache Kafka** | 2000+ stream partitions, fault-tolerant, replayable |
| Person Detection | **YOLOv8-L** (TensorRT FP16) | Best speed/accuracy trade-off. YOLOv8-nano for density counting |
| Face Detection | **RetinaFace** (InsightFace) | SOTA alignment, handles angles/occlusion |
| Face Embedding | **AdaFace** (512-d) | SOTA on surveillance-quality and low-light faces |

| Night Enhancement | **CLAHE + Gamma Correction** (proven in POC) | Tested on Surat night footage, improves detection |
| Vector Database | **Milvus 2.x** (GPU) + FAISS backend | Billion-scale ANN, GPU-accelerated. Daily partitions |
| Metadata DB | **PostgreSQL + TimescaleDB** | Time-series optimized sightings queries |
| Object Storage | **MinIO** | On-premise S3-compatible for thumbnails, clips |
| Cache | **Redis** | Watchlist cache, session management, pub/sub |
| Task Queue | **Celery + Redis** | Background jobs (historical search, reports, cleanup) |
| Backend API | **FastAPI** | Async, fast, Python ML ecosystem |
| Real-time | **WebSocket** (via FastAPI) | Instant alert push to dashboard |
| Frontend | **React.js** | Component-based, rich ecosystem |
| Maps | **Leaflet / MapLibre GL** | Open-source, no API costs |
| PDF Reports | **ReportLab / WeasyPrint** | Court-ready investigation reports |
| Containers | **Docker + Docker Compose** | Service isolation, reproducible deployment |
| Orchestration | **Kubernetes (on-prem)** | Auto-scaling, GPU scheduling, rolling updates |
| Monitoring | **Prometheus + Grafana** | System health, GPU utilization |
| Logging | **Loki + Grafana** or ELK | Centralized structured logging, audit trail |
| ML Optimization | **NVIDIA TensorRT** | 3-5× inference speedup, FP16 |

---

## 6. Indian Street Adaptations (Built Into Architecture)

### 6.1 Tiered Camera Processing

```
TIER 1 (Dense: chaurahas, stations, markets) — ~400 cameras
├── 1 FPS processing
├── Faces > 60px only (skip distant crowd)
├── Adaptive: if >50 people, process nearest 30 only
├── QUALITY over QUANTITY
└── Expected: 12,000 faces/sec from this tier

TIER 2 (Moderate: main roads, bus stops) — ~800 cameras
├── 2 FPS processing
├── Faces > 40px
├── Standard pipeline
└── Expected: 40,000 faces/sec from this tier

TIER 3 (Light: residential, highway) — ~800 cameras
├── 3 FPS processing
├── All faces > 25px
├── Most accurate (less occlusion)
└── Expected: 19,200 faces/sec from this tier
```

### 6.2 Five-Layer Filtering Pipeline

Every frame passes through these filters in order:

| # | Filter | What It Does | Compute Saved |
|---|---|---|---|
| 1 | **ROI masking** | Skip sky, road surface, known static zones | 30-50% |
| 2 | **Motion detection** | Skip frames with no movement | 20-40% |
| 3 | **YOLO person filter** | Only process frames with people | 60-80% |
| 4 | **Face quality gate** | Skip <40px, blurry, low-confidence, occluded | 40-60% of detections |
| 5 | **Temporal dedup** | Same person in last 30 sec on same camera → update, don't store | 90%+ storage reduction |

**Net effect:** A frame with 200 people produces ~15-25 new stored embeddings, not 200.

### 6.3 Festival Mode (Admin Toggle)

During Navratri, Diwali, Ganesh Chaturthi, Rath Yatra:

```
FESTIVAL MODE ON:
├── ALL cameras → Tier 1 processing (1 FPS, large faces only)
├── DISABLE general database building
├── ONLY watchlist matching (compare against known persons)
├── Increase alert confidence to 0.80
├── Require multi-camera corroboration (2+ cameras)
└── Purpose: find wanted persons, don't catalog the crowd
```

### 6.4 India-Specific Challenges & Solutions

| Challenge | Solution |
|---|---|
| **Auto-rickshaw occlusion** (blocks 30-50% of view) | Accept lower face yield from rickshaw-heavy cameras. Wait for person to emerge from behind vehicle — multi-frame tracking. |
| **Dupatta / Hijab / Chunni** (half-face) | AdaFace handles partial faces well. Upper face features (eyes, forehead) still usable. |
| **Helmeted two-wheeler riders** (~30% of people) | Cannot face-match. **Known limitation — document for client.** Catch them at destination when helmet is off. |
| **People looking at phones** (head down) | Multi-frame best-embedding: wait for look-up across 5-10 frames, keep best quality. |
| **Extreme heat haze** (40-45°C summer) | Image sharpening preprocessing. Adaptive confidence thresholds by season. |
| **Monsoon rain** (June-September) | Blur detection to skip useless frames. Camera cleaning SOP for client ops. |
| **Festival crowds** (10-50× normal) | Festival Mode (see 6.3). Watchlist-only matching. |
| **School uniforms / factory workers** | Face-only matching. Not an issue since system is face-based, not clothing-based. |
| **Street vendors / hawkers** (stationary hours) | Temporal dedup: 1 embedding per 30 minutes for stationary persons. |
| **Power cuts** | Stream health monitoring + exponential backoff reconnect. Gap markers in timeline. |
| **Pan/Gutka stains** (changes lip appearance) | AdaFace focuses on geometric features (eye distance, nose shape), not color. |

---

## 7. Existing Code Audit — What We're Building On

### Working Code (POC Validated)

| File | What It Does | Reusable? |
|---|---|---|
| `final_code_4cam.py` | 4-camera RTSP + face detect/embed + ChromaDB + person clustering | ✅ Logic reusable, rewrite for new arch |
| `extract_image.py` | Face extraction from stored .avi video files | ✅ Useful for batch processing |
| `test_accuracy.py` | Automated accuracy testing (query images vs DB) | ✅ **Gold — keep as validation suite** |
| `test_visual_audit.py` | Side-by-side visual comparison cards | ✅ **Gold — keep for QA** |
| `test_nightvid.py` | Night enhancement: CLAHE + gamma + glare + blur | ✅ Port `enhance_night_frame()` to new pipeline |
| `test_metrics.py` | GPU/CPU/RAM benchmark + camera capacity estimate | ✅ Results inform hardware sizing |
| `stream_viewer.py` | 2×2 RTSP grid viewer | ✅ Useful for debugging |
| `test_gpu.py` | CUDA provider verification | ✅ Keep for setup validation |
| `install_model.py` | AntelopeV2 model auto-downloader | ✅ Extend for all models |
| `view_db.py` | Streamlit ChromaDB browser | ⬜ Replace with React dashboard |
| `docker-compose.yml` | Dev-grade face-engine + Streamlit | ⬜ Replace with production compose |
| `live.py`, `live_embedding_gpu.py` | Earlier 2-camera versions | ⬜ Superseded by `final_code_4cam.py` |

### Proven Accuracy Results (from POC Testing on Real Surat Footage)

| Threshold | Accuracy | Verdict |
|---|---|---|
| 0.40 (strict) | 59.71% | ❌ Too many false negatives |
| 0.45 | 69.93% | ❌ Still too strict |
| 0.50 | 79.25% | ⚠️ Moderate |
| **0.55** | **86.48%** | **✅ Recommended sweet spot** |
| 0.57-0.58 | ~87-88% | ✅ Visual audit confirmed |
| 0.60 (loose) | 90.73% | ⚠️ Higher false positive risk |
| 0.55 (extreme low-res) | 83.98% | ✅ Acceptable for poor quality |

### Critical Gaps to Close (POC → Production)

| Current | Required | Priority |
|---|---|---|
| OpenCV `VideoCapture` | NVIDIA DeepStream / GStreamer + NVDEC | 🔴 Critical |
| ChromaDB (~1M vectors) | Milvus 2.x + FAISS (billion-scale) | 🔴 Critical |
| InsightFace bundled model | Separate RetinaFace + AdaFace | 🟡 High |
| No person detection filter | YOLOv8 first (saves 60-80% compute) | 🟡 High |

| No API backend | FastAPI with all endpoints | 🔴 Critical |
| Streamlit UI | React.js production dashboard | 🟡 High |
| No watchlist / alerts | Real-time matching + WebSocket alerts | 🔴 Critical |
| No Kafka | Apache Kafka for pipeline decoupling | 🟡 High |
| No Triton | NVIDIA Triton for model serving | 🟡 High |
| No auth / audit | JWT + RBAC + DPDP audit logging | 🟡 High |
| No monitoring | Prometheus + Grafana | 🟠 Medium |
| Hardcoded camera URLs | Database-driven camera registry | 🟠 Medium |
| Dev Docker Compose | Production Dockerfiles + K8s manifests | 🟠 Medium |

---

## 8. Phase Breakdown — 6 Months (Revised)

---

### PHASE 1: Foundation & Infrastructure (Weeks 1–4)

> **Goal:** Set up production architecture, establish the ML pipeline, validate with real RTSP streams.

#### Week 1: Project Setup & Environment

- [ ] Git repo with branching strategy (main, develop, feature/*)
- [ ] Production project structure:

```
surat-surveillance/
├── docker-compose.yml / docker-compose.prod.yml
├── services/
│   ├── stream-ingestion/       # DeepStream/GStreamer + Kafka
│   ├── detection/              # YOLO person detection
│   ├── embedding/              # RetinaFace + AdaFace
│   ├── vector-store/           # Milvus client layer
│   ├── api/                    # FastAPI backend
│   ├── worker/                 # Celery background tasks
│   └── frontend/               # React dashboard
├── scripts/                    # setup, benchmark, TensorRT convert
├── configs/                    # Kafka, Milvus, Prometheus, Grafana
├── tests/                      # unit, integration, load, accuracy
├── poc/                        # Existing POC code (preserved)
│   ├── final_code_4cam.py
│   ├── test_accuracy.py
│   ├── test_visual_audit.py
│   ├── test_nightvid.py
│   └── test_metrics.py
└── docs/
```

- [ ] Docker Compose with: PostgreSQL + TimescaleDB, Redis, Milvus (CPU dev / GPU prod), Kafka + Zookeeper, MinIO
- [ ] Install CUDA toolkit + cuDNN on RTX A6000

#### Week 2: ML Pipeline — Core Models

- [ ] Download & test YOLOv8-L for person detection (<15ms/frame on A6000)
- [ ] Download & test RetinaFace for face detection + alignment (<5ms/face)
- [ ] Download & test AdaFace for face embedding (512-d, <3ms/face)

- [ ] Port `enhance_night_frame()` from POC as preprocessing module
- [ ] Convert all models: PyTorch → ONNX → TensorRT FP16
- [ ] Benchmark: TensorRT vs current ONNX (expect 3-5× speedup)
- [ ] Single-image end-to-end test: image → YOLO → RetinaFace → AdaFace → Milvus → search

#### Week 3: Stream Ingestion Pipeline

- [ ] GStreamer RTSP reader with NVDEC hardware decode
- [ ] Dual-stream logic (1080p → storage, 480p → ML pipeline)
- [ ] Kafka producer with camera-group partitioning
- [ ] Kafka consumer group for detection service
- [ ] Tiered frame sampling (T1/T2/T3 configurable per camera)
- [ ] ROI configuration (per-camera static zones to skip)
- [ ] Stream health monitoring + auto-reconnect (exponential backoff)
- [ ] Test: 1 live RTSP → 10 simulated streams

#### Week 4: Integration & Small-Scale Validation

- [ ] Full pipeline: RTSP → GStreamer → Kafka → YOLO → RetinaFace → AdaFace → Milvus
- [ ] Temporal deduplication module (30-sec window per camera)
- [ ] Test with 5 live RTSP streams from client cameras
- [ ] Measure latency: frame → embedding stored (<500ms target)
- [ ] Measure throughput on A6000
- [ ] Re-run accuracy tests (POC test suite) against new Milvus backend
- [ ] **Milestone: POC v2 demo — show client the production-grade pipeline**

---

### PHASE 2: Core Backend Development (Weeks 5–10)

> **Goal:** Complete backend — API, search, watchlist, real-time alerts, historical search.

#### Week 5–6: Database & API Foundation

- [ ] Finalize PostgreSQL + TimescaleDB schema (hypertable for sightings, 30-day retention)
- [ ] FastAPI application with camera management CRUD API
- [ ] Milvus client wrapper (insert, search, delete, partition management)
- [ ] Person clustering logic (distance-based, threshold 0.55-0.57)
- [ ] Camera registry (database-driven, not hardcoded — tier, ROI, zone)

#### Week 7–8: Search & Tracking APIs

- [ ] `POST /api/search` — upload photo → face detect → embed → Milvus search → return matches with metadata
- [ ] `GET /api/track/{person_id}/timeline` — chronological sighting list
- [ ] `GET /api/track/{person_id}/heatmap` — location frequency data
- [ ] Watchlist CRUD: `POST/GET/PUT/DELETE /api/watchlist`
- [ ] **Real-time watchlist matching:** every new embedding compared against watchlist collection → WebSocket alert
- [ ] Alert management with human-in-the-loop confirmation workflow

#### Week 9–10: Historical Search & Background Processing

- [ ] Historical search engine (Celery workers, Milvus partition-scoped queries)
- [ ] `POST /api/search/historical` → async job → WebSocket notification on complete
- [ ] Data lifecycle: daily cron purges embeddings + sightings older than 30 days (Milvus partition drop + TimescaleDB chunk drop)
- [ ] WebSocket connection manager (channels: alerts, search_results, system_status)
- [ ] Festival Mode API toggle (`POST /api/admin/festival-mode`)

---

### PHASE 3: Frontend Dashboard (Weeks 11–14)

> **Goal:** Professional, operator-grade React dashboard.

#### Week 11–12: Core Dashboard

- [ ] React.js project (Vite), responsive layout for monitoring screens
- [ ] **Search Page:** drag-and-drop upload, results grid with thumbnails, side-by-side comparison, confidence scores, date/camera filters, video clip playback, PDF export
- [ ] **Live Monitoring:** camera grid view, real-time detection overlays, camera status
- [ ] **Watchlist Page:** add/edit/deactivate entries, view alert history per person

#### Week 13–14: Map & Timeline

- [ ] **Map View:** Interactive Surat map (Leaflet), camera markers (color-coded by status/tier), person movement path, heatmap overlay, zone management
- [ ] **Person Timeline:** vertical timeline of all sightings, thumbnail + camera + timestamp, playback controls, synchronized map view
- [ ] **Alerts Dashboard:** real-time WebSocket feed, human-in-the-loop confirm/dismiss with notes, multi-camera corroboration badge, 30-sec video clip, false positive marking, audio/visual notifications
- [ ] **Admin Page:** camera management, system health (Grafana embed), Festival Mode toggle, user management

---

### PHASE 4: Scale Engineering (Weeks 15–18)

> **Goal:** Scale from "works with 10 cameras" to "handles 2000+ in production."

#### Week 15–16: Pipeline Optimization

- [ ] TensorRT FP16 engines for all models on A100
- [ ] Dynamic batching: accumulate frames across cameras, optimal batch size per model
- [ ] Multi-GPU assignment: GPU 0-1 (YOLO detection), GPU 2 (face embedding), GPU 3 (Milvus + watchlist)
- [ ] CUDA stream pipelining + NVIDIA DALI preprocessing
- [ ] Kafka tuning: partitions, consumer groups, message TTL, lag monitoring
- [ ] Intelligent frame sampling: adaptive FPS (increase when person detected, decrease when idle)

#### Week 17–18: Scale Testing

- [ ] Simulate 2000 RTSP streams (FFmpeg loop playback)
- [ ] Target: all 2000 cameras at tiered FPS with <2 sec latency
- [ ] Milvus scale test: 1B+ vectors with daily partitions, IVF_PQ index, <200ms search
- [ ] Stress test: 2000 cameras + 10 concurrent searches + 5 watchlist alerts simultaneously
- [ ] 48-hour continuous run (memory leak detection, failure recovery)
- [ ] Profile and optimize hot paths

---

### PHASE 5: Production Hardening (Weeks 19–22)

> **Goal:** Production-ready — reliable, monitored, secure, deployable.

#### Week 19–20: Reliability & Monitoring

- [ ] Docker restart policies, health checks, watchdog processes
- [ ] Graceful degradation (GPU failure → redistribute load)
- [ ] Prometheus metrics: FPS/camera, detection count, embedding throughput, Milvus latency, Kafka lag, GPU temp/utilization/memory
- [ ] Grafana dashboards: system overview, GPU, pipeline, alerts
- [ ] Centralized logging (Loki/ELK), structured JSON format, audit log retention

#### Week 21–22: Security & Deployment

- [ ] JWT authentication + RBAC (Admin, Operator, Viewer, Auditor)
- [ ] API rate limiting, internal-only network communication
- [ ] DPDP Act compliance: mandatory audit logging, export watermarks, 30-day hard purge
- [ ] Production Dockerfiles (baked dependencies, multi-stage builds)
- [ ] Kubernetes manifests (nvidia-device-plugin for GPU scheduling)
- [ ] Database migrations (Alembic), backup strategy (daily PG dumps, Milvus snapshots)
- [ ] Complete documentation: architecture, API, deployment guide, runbook, user manual

---

### PHASE 6: Integration, Testing & Handoff (Weeks 23–26)

> **Goal:** Deploy on client infrastructure, staged rollout, handoff.

#### Week 23–24: Client Site Deployment

- [ ] Hardware setup at client data center (GPU servers, NVMe RAID, 25GbE networking)
- [ ] Staged rollout:
  - Phase A: 50 cameras → 48 hours validation
  - Phase B: 500 cameras → 1 week validation
  - Phase C: 2000 cameras → 1 week validation
- [ ] Camera-by-camera tier assignment (T1/T2/T3 based on location density)
- [ ] ROI configuration for high-occlusion cameras
- [ ] Map camera GPS coordinates, integrate with client naming convention

#### Week 25–26: Acceptance Testing & Handoff

- [ ] Real-world accuracy testing: known persons across cameras, day vs night, frontal vs side, near vs far, occluded
- [ ] Alert latency verification: detection → dashboard <5 seconds
- [ ] Festival Mode dry run
- [ ] Client training: operators (dashboard), IT team (admin, troubleshooting)
- [ ] Source code + documentation transfer
- [ ] 2-week post-deployment support window

---

## 9. Risk Register (Revised)

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **False positive → wrongful arrest** | **Critical** | **Medium** | **Human-in-the-loop mandatory. Multi-camera corroboration. Never auto-act.** |
| Accuracy below 75% on real footage | High | Medium | Already proven 86% in POC. Upgrade to AdaFace for higher. Multi-frame best-embedding helps. |
| **Indian crowd density overwhelms GPU** | **High** | **High** | **Tiered processing + temporal dedup + ROI filtering. Start 4×A100, scale to 8×.** |
| Auto-rickshaw occlusion drops face yield | High | High | Accept 5-25% face yield on vehicle-heavy cameras. Catch person at next camera. |
| Helmeted riders unmatchable (30% of people) | Medium | High | Document as known limitation. Face matching only works on unhelmeted persons. |
| Milvus can't handle billion-scale | High | Medium | Benchmark in Phase 1. Fallback: FAISS sharded by zone. Daily partition pruning. |
| Festival crowds crash system | High | Medium | Festival Mode: watchlist-only, 1 FPS, skip DB building. |
| Monsoon/heat degrades accuracy | Medium | High | Night enhancement pipeline proven. Seasonal confidence adjustment. |
| ChromaDB → Milvus migration issues | Medium | Low | Clean break — new system, POC test suite validates new backend. |
| **Legal/compliance audit (DPDP Act)** | **High** | **Medium** | **Built-in: audit logging, RBAC, retention, export watermarks.** |
| Model drift over time | Medium | Low | Triton versioning + A/B testing in shadow mode. |
| Power cuts at camera sites | Medium | High | Stream health monitor + exponential backoff reconnect + timeline gap markers. |
| Client network can't handle bandwidth | High | Low | Dual-stream (480p ML = ~4 Gbps total, within capacity). |
| Timeline overrun | Medium | High | Ship MVP at month 4 (live pipeline + basic dashboard). Polish months 5-6. |
| Team members unavailable | Medium | Medium | Document everything. Modular architecture. Can handle core solo. |

---

## 10. Budget Estimate (Revised for Indian Density)

| Item | Spec | Quantity | Est. Cost (INR) |
|---|---|---|---|
| GPU Server (Starter) | 4× A100 80GB + 2× EPYC 9354 + 512GB RAM | 1 | ₹1.8–2.5 Cr |
| GPU Server (Scale-up) | 4× A100 80GB (expansion if needed) | 1 | ₹1.5–2.0 Cr |
| NVMe Storage | 16TB NVMe SSD RAID (revised up) | 1 set | ₹8–12 Lakh |
| RAM Upgrade | 512GB → 1TB DDR5 (if needed for Milvus index) | 1 set | ₹3–5 Lakh |
| Network Cards | 25GbE NIC | 2 | ₹1–2 Lakh |
| Network Switch | 25GbE switch | 1 | ₹3–5 Lakh |
| **Total (Starter: 4×A100)** | | | **₹1.9–2.7 Cr** |
| **Total (Scaled: 8×A100)** | | | **₹3.5–5.0 Cr** |

Software cost: ₹0 (entire stack is open-source).

> **Recommended approach:** Start with 4× A100 + aggressive filtering (tiered processing, temporal dedup, ROI). This handles 80% of the workload. Scale to 8× A100 only if load testing in Phase 4 proves it necessary.

---

## 11. Success Criteria

| Metric | Target | How to Measure |
|---|---|---|
| Face recognition accuracy | 75–90% across journey | Test with known persons across multiple cameras |
| End-to-end latency (live) | < 5 seconds | Timestamp at capture → alert on dashboard |
| Historical search time | < 5 minutes for 30-day search | Measure search job completion |
| System uptime | > 99.5% | Prometheus monitoring over 1 month |
| Cameras processed | All 2000+ at tiered FPS | Dashboard camera status page |
| Alert delivery | < 3 seconds from detection | WebSocket delivery measurement |
| Storage growth (daily) | < 50M new vectors/day (after dedup) | Milvus collection stats |
| False positive rate on alerts | < 5% confirmed false positives | Operator feedback tracking |

---

## 12. Month-by-Month Summary

| Month | Phase | Key Milestone |
|---|---|---|
| **Month 1** | Foundation | POC v2 — production ML pipeline with 5 cameras, TensorRT, Milvus |
| **Month 2** | Core Backend (Part 1) | Full API — search, watchlist, real-time alerts working |
| **Month 3** | Core Backend (Part 2) + Frontend Start | Historical search + basic React dashboard |
| **Month 4** | Frontend Complete | Full dashboard with maps, timeline, alerts — **Internal MVP** |
| **Month 5** | Scale + Hardening | Handles 2000 cameras at tiered FPS, monitored, secured — **Client staging** |
| **Month 6** | Integration + Handoff | Deployed on client infra, tested, trained — **GO LIVE** |

---

## 13. Strategic Principles

1. **Ship live pipeline first, historical search second.** Client gets immediate value from real-time watchlist alerts.

2. **Quality over quantity.** Don't try to catalog every person in Surat — focus on high-quality faces (>40px, >0.55 confidence, temporally deduplicated). A person walking through the city passes 10+ cameras; you only need 2-3 good captures.

3. **Human-in-the-loop is non-negotiable.** The system NEVER auto-acts on alerts. An innocent person's freedom depends on this.

4. **The existing POC is validated proof, not production code.** Start fresh with microservices architecture. Port proven logic (accuracy thresholds, night enhancement, clustering) into the new system.

5. **Communicate limitations honestly.** Helmeted riders (~30% of people) cannot be face-matched. Dense crowd cameras have 5-8% face yield. Night accuracy is lower. These are physics constraints, not bugs.

6. **Build for India, not for a textbook.** Auto-rickshaws, dupattas, pan stains, monsoon rain, festival crowds, power cuts — all accounted for in the architecture.

---

> **This plan is a living document. Update it as you progress through each phase, encounter new challenges, or receive additional client requirements.**
