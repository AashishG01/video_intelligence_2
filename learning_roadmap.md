# 🎓 C.O.R.E. Codebase — Learning Roadmap

> **Goal:** Understand every piece of the video surveillance system, from cameras to the React dashboard.
> **Estimated time:** 6–8 focused sessions (2–3 hours each)

---

## How This Roadmap Works

The codebase has **7 layers** that data flows through sequentially. You'll learn them **in the order data travels** — from cameras all the way to the user's screen. This way, every new file you open already has context from the previous one.

```
📹 Camera → 📦 Redis Queue → 🧠 AI Workers → 🗄️ Databases → ⚡ API → ⚛️ React UI → 📧 Email
```

---

## Phase 1: The Foundation (Read Only — No Code Yet)

> **Goal:** Understand the big picture before touching any code.

### Session 1: Architecture & Infrastructure

| Order | Read This | What You'll Learn |
|-------|-----------|-------------------|
| 1 | [architecture_flow.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/architecture_flow.md) | The complete system design — all 7 layers, data flows, and design decisions. **Start here.** Read the whole thing, study every Mermaid diagram. |
| 2 | [docker-compose.yml](file:///c:/Users/Hp/Desktop/video_intelligence_2/docker-compose.yml) | What infrastructure runs in Docker (Redis, PostgreSQL, Milvus, MediaMTX) and how they connect |
| 3 | [ecosystem.config.js](file:///c:/Users/Hp/Desktop/video_intelligence_2/ecosystem.config.js) | How PM2 orchestrates the 5 Python/Node processes |
| 4 | [mediamtx.yml](file:///c:/Users/Hp/Desktop/video_intelligence_2/mediamtx.yml) | How RTSP camera streams get converted to WebRTC for the browser |

> [!TIP]
> **Key concepts to nail down:**
> - What is Redis used for? (Answer: 3 things — message queue, cache/dedup, pub/sub)
> - What is Milvus? (Answer: vector database for face similarity search)
> - What is the difference between PostgreSQL and Milvus in this system?
> - Why are there TWO Redis queues (`raw_frames_queue` and `face_ready_queue`)?

---

## Phase 2: Data Pipeline (Follow the Frame)

> **Goal:** Trace a single camera frame from capture to database storage.

### Session 2: Camera Ingestion

| Order | File | Lines | What You'll Learn |
|-------|------|-------|-------------------|
| 1 | [producer.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/Ingestion/producer.py) | 159 | How RTSP frames are captured, resized, encoded, and pushed to Redis. How threads work. How cameras auto-sync from DB. |

**Study focus:**
- `CameraProducer` class — one thread per camera
- `get_active_cameras()` — polls PostgreSQL every 5 seconds
- The main loop (line 107–151) — how new cameras are started, removed cameras stopped
- `lpush` + `ltrim` — Redis queue management (push + cap)

**Concepts to Google if unfamiliar:**
- OpenCV `cv2.VideoCapture` with RTSP
- Python `threading.Thread`
- Base64 encoding (why we do it)
- Redis Lists (`lpush`, `brpop`, `ltrim`)

---

### Session 3: AI Pipeline — YOLO Pre-Filter

| Order | File | Lines | What You'll Learn |
|-------|------|-------|-------------------|
| 1 | [worker_yolo.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_yolo.py) | 75 | How YOLO acts as a gatekeeper — only frames with people get forwarded |

**Study focus:**
- `brpop("raw_frames_queue")` — blocking pop (waits for data)
- YOLOv8 inference — `model(frame, classes=[0])` means "detect persons only"
- The size gate — `w > 150 and h > 250` (why? → too small = no usable face)
- `lpush("face_ready_queue")` — forwards to face worker

**Key insight:** This file is only 75 lines but saves 60–80% of GPU compute by dropping empty frames.

---

### Session 4: AI Pipeline — Face Recognition (THE CORE)

> [!IMPORTANT]
> This is the most important file in the entire project. Spend the most time here.

| Order | File | Lines | What You'll Learn |
|-------|------|-------|-------------------|
| 1 | [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py) | 378 | Face detection, embedding extraction, watchlist matching, general matching, dedup, image saving, WebSocket alerts |

**Read it in 6 blocks:**

1. **Configuration & Connections** (lines 1–73)
   - `MATCH_THRESHOLD = 0.35` — what does cosine distance mean?
   - Two Redis connections, one PG, one Milvus
   - Two Milvus collections: `face_embeddings` (civilians) vs `watchlist_faces` (suspects)

2. **Face Detection & Cropping** (lines 117–152)
   - InsightFace `face_app.get(frame)` → returns faces with bounding boxes + embeddings
   - `det_score` filtering, margin cropping (25% padding)

3. **Stage 1: Watchlist Hunting** (lines 164–215)
   - Milvus `search()` against `watchlist_faces`
   - If distance < threshold → it's a wanted person
   - Fetch name + risk level from PostgreSQL `subjects` table

4. **Stage 2: General Population Search** (lines 213–239)
   - Milvus `search()` against `face_embeddings`
   - Match → existing person. No match → generate new `P_timestamp` ID.

5. **Anti-Spam System** (lines 242–265)
   - `db_cooldown` — always prevents DB spam
   - `alert_cooldown` — only active when Armed (clever trick for instant re-arm)

6. **Output: Save + Broadcast** (lines 267–339)
   - Image saved to disk, path stored in PostgreSQL
   - JSON payload published to Redis → WebSocket → React

**Concepts to Google if unfamiliar:**
- Cosine distance vs cosine similarity
- Vector databases (how Milvus search works)
- Face embeddings (512-dimensional float arrays)
- Redis Pub/Sub pattern

---

## Phase 3: Database Layer

> **Goal:** Understand what data is stored and how tables relate.

### Session 5: Database Schema & Initialization

| Order | File | Lines | What You'll Learn |
|-------|------|-------|-------------------|
| 1 | [init_db.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/database_init/init_db.py) | ~140 | All 7 PostgreSQL tables, 2 Milvus collections, seed data |

**Study focus:**
- **7 PG tables:** `users`, `cameras`, `sightings`, `subjects`, `watchlist_categories`, `watchlist_members`, `system_alert_settings`
- **2 Milvus collections:** `face_embeddings`, `watchlist_faces`
- Foreign keys: `watchlist_members` links `subjects` ↔ `watchlist_categories` (many-to-many)
- `ON DELETE CASCADE` — deleting a category auto-removes all member links

**Draw this on paper:**
```
subjects ←──(watchlist_members)──→ watchlist_categories
                                        
sightings ← worker_face.py writes here every detection
cameras   ← producer.py reads from here
users     ← auth.py validates against here
```

---

## Phase 4: Backend API

> **Goal:** Understand how the React frontend talks to the Python backend.

### Session 6: FastAPI Backend

| Order | File | Lines | What You'll Learn |
|-------|------|-------|-------------------|
| 1 | [auth.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/auth.py) | 72 | JWT tokens, password hashing, role-based access (admin vs user) |
| 2 | [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py) | 1077 | All 20+ API endpoints, WebSocket, connection pool, image serving |
| 3 | [worker_notify.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/worker_notify.py) | 183 | Email alerts on watchlist match, cooldown system |

**Read `newapi.py` in sections (it's big!):**

| Section | Lines | What It Does |
|---------|-------|--------------|
| Setup & Connection Pool | 1–168 | App config, CORS, folder mounts, `ThreadedConnectionPool`, `_PooledConn` wrapper |
| Auth Routes | 183–231 | Login, register operator |
| WebSocket | 236–253 | Real-time alerts from Redis pub/sub → React |
| Video Stream | 258–271 | Async MJPEG generator (legacy fallback) |
| Dashboard Stats | 276–312 | Aggregate queries for the stats page |
| Startup Check | 314–385 | Auto-creates tables and collections on boot |
| Subject CRUD | 565–756 | Enroll, list, update, delete watchlist subjects |
| Settings | 789–886 | Read/write alert config (Redis + PostgreSQL) |
| Camera CRUD | 891–1042 | Add/remove cameras, sync to MediaMTX |

**Concepts to Google if unfamiliar:**
- FastAPI decorators (`@app.get`, `@app.post`, `@app.websocket`)
- Pydantic `BaseModel` for request validation
- `Depends()` for dependency injection (auth middleware)
- Connection pooling (`psycopg2.pool.ThreadedConnectionPool`)
- `StreamingResponse` for video streaming

---

## Phase 5: Frontend

> **Goal:** Understand the React dashboard — auth, routing, WebSocket, and all 8 views.

### Session 7: React Core

| Order | File | What You'll Learn |
|-------|------|-------------------|
| 1 | [config.js](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/config.js) | Backend URLs, WebSocket URL, image path helper |
| 2 | [api.js](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/api.js) | Axios instance with JWT Bearer token interceptor |
| 3 | [AuthContext.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/context/AuthContext.jsx) | React Context for login state, token storage |
| 4 | [App.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/App.jsx) | Route definitions, ProtectedRoute wrapper |
| 5 | [Login.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/pages/Login.jsx) | Login form → API call → store JWT → redirect |

### Session 8: Dashboard & Views

| Order | File | Why This Order |
|-------|------|----------------|
| 1 | [Dashboard.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/pages/Dashboard.jsx) | **Read first** — contains the WebSocket connection, sidebar, view router, and kill switch. Everything flows through here. |
| 2 | [LiveMonitorView.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/views/LiveMonitorView.jsx) | WebRTC camera grid + live intel feed. Learn the WHEP protocol handshake. |
| 3 | [InvestigatorView.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/views/InvestigatorView.jsx) | Image upload search + person timeline |
| 4 | [WatchlistManager.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/views/WatchlistManager.jsx) | Subject enrollment, editing, categories |
| 5 | [EventFeedView.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/views/EventFeedView.jsx) | Real-time terminal-style log stream |
| 6 | [AlertSettingsView.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/views/AlertSettingsView.jsx) | Threshold slider, sound picker, email config |
| 7 | [ThreatAlertModal.jsx](file:///c:/Users/Hp/Desktop/video_intelligence_2/frontend/src/components/ThreatAlertModal.jsx) | The dramatic red popup on watchlist detection |
| 8 | Remaining views & components | SystemStatusView, CameraSettingsView, AdminPanel, Sidebar, etc. |

**Concepts to Google if unfamiliar:**
- React Hooks (`useState`, `useEffect`, `useRef`, `useContext`)
- WebSocket API in JavaScript (`new WebSocket(url)`)
- WebRTC + WHEP protocol (the `RTCPeerConnection` flow)
- TailwindCSS utility classes

---

## Phase 6: Advanced / Optional

### Session 9: Tracker Pipeline (Experimental)

| Order | File | What You'll Learn |
|-------|------|-------------------|
| 1 | [tracker/worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/tracker/worker_face.py) | ByteTrack integration — buffers faces per track ID, only saves the sharpest frame per person visit. Night vision, pose gating, quality scoring. |

### Session 10: Documentation & Planning

| File | Purpose |
|------|---------|
| [ProjectPlan_v2.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/ProjectPlan_v2.md) | Original design document with full architecture decisions |
| [notes.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/notes.md) | 1155-line project audit with all known issues |
| [bug_report.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/bug_report.md) | 23 tracked bugs (you already know these!) |
| [scalability_guide.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/scalability_guide.md) | How to scale from 4 cameras to 100+ |
| [futurework.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/futurework.md) | Planned features and improvements |

---

## 🧠 Learning Tips

### 1. Trace the Data, Don't Read Randomly
Follow a single **detection event** through the entire system:
```
Camera frame → producer.py → Redis → worker_yolo.py → Redis → worker_face.py 
→ Milvus search → PostgreSQL insert → Redis publish → newapi.py WebSocket 
→ Dashboard.jsx → LiveMonitorView sidebar → ThreatAlertModal (if watchlist)
→ worker_notify.py → Gmail
```

### 2. Use Print Statements
Add `print("🔥 HERE:", variable)` at key points and run the system. Watch the terminal output flow through the pipeline.

### 3. Start the System and Watch
```bash
docker-compose up -d          # Infrastructure
pm2 start ecosystem.config.js # All workers
```
Then open the React dashboard and watch the Live Intel Feed. Every card that appears = one complete trip through the entire codebase.

### 4. Draw the Database Relationships
Sketch the 7 PostgreSQL tables on paper with arrows showing foreign keys. This makes the API endpoints click instantly.

### 5. Read the Redis Keys
Open a Redis CLI (`redis-cli`) and run:
```bash
KEYS *                    # See all active keys
LLEN raw_frames_queue     # How many frames waiting for YOLO
LLEN face_ready_queue     # How many frames waiting for face worker  
GET system_armed          # Is the system armed?
GET GLOBAL_MATCH_THRESHOLD # Current face match sensitivity
```

---

## Quick Reference: File Importance Ranking

| Priority | File | Why |
|----------|------|-----|
| ⭐⭐⭐⭐⭐ | `ai_worker/worker_face.py` | The brain — face detection, matching, and alerting |
| ⭐⭐⭐⭐⭐ | `backend_api/newapi.py` | The spine — all API endpoints |
| ⭐⭐⭐⭐ | `frontend/src/pages/Dashboard.jsx` | The face — WebSocket, layout, alert system |
| ⭐⭐⭐⭐ | `Ingestion/producer.py` | The eyes — camera capture |
| ⭐⭐⭐ | `ai_worker/worker_yolo.py` | The filter — person pre-detection |
| ⭐⭐⭐ | `backend_api/auth.py` | The lock — JWT authentication |
| ⭐⭐⭐ | `database_init/init_db.py` | The skeleton — schema definition |
| ⭐⭐ | `frontend/src/views/*.jsx` | The skin — individual UI pages |
| ⭐⭐ | `backend_api/worker_notify.py` | The voice — email alerts |
| ⭐ | `docker-compose.yml` | The ground — infrastructure |
