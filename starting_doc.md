# C.O.R.E. Video Intelligence - Startup & Operations Guide

This document outlines the standard operating procedures for initializing, starting, stopping, and resetting the C.O.R.E. Video Intelligence system.

## 1. Automated Startup (Recommended)

The easiest way to launch the entire stack is by using the provided `start.sh` script.

**Prerequisites:**
- You must have a Python virtual environment created at `venv/`.
- You must have Docker Desktop running.

**Command:**
```bash
bash start.sh
```

**What this script does sequentially:**
1. **Verifies Environment:** Checks if your `venv/` exists and has Python.
2. **Starts Docker Infrastructure:** Runs `docker compose up -d` to launch PostgreSQL, Redis, Milvus, and MediaMTX. It pauses for 10 seconds to ensure databases are fully online.
3. **Initializes Database:** Runs `database_init/init_db.py` to ensure all PostgreSQL tables are created safely (using `IF NOT EXISTS` logic).
4. **Starts Application Services:** Uses `pm2` to launch the FastAPI backend, the React frontend, and the AI Worker concurrently based on `ecosystem.config.js`.
5. **Generates Report:** Prints the `pm2 status` table and the live URLs.

### To stop the system gracefully:
```bash
bash stop.sh
```

---

## 2. Manual Startup (Without `start.sh`)

If you need to debug specific components or prefer manual execution, follow this exact sequence:

### Step 1: Start Core Infrastructure
```bash
docker compose up -d
```

### Step 2: Initialize Database (First Time Only)
Ensure your `.env` file is populated, then run:
```bash
python database_init/init_db.py
```

### Step 3: Start FastAPI Backend
Open a terminal, activate your virtual environment, and run:
```bash
cd backend_api
uvicorn newapi:app --host 0.0.0.0 --port 8000 --reload
```

### Step 4: Start Live Camera Ingestion
Open a second terminal, activate your virtual environment, and run:
```bash
cd Ingestion
python producer.py
```

### Step 5: Start AI YOLO Worker (Object Detection)
Open a third terminal, activate your virtual environment, and run:
```bash
cd ai_worker
python worker_yolo.py
```

### Step 6: Start AI Face Worker (Biometrics)
Open a fourth terminal, activate your virtual environment, and run:
```bash
cd ai_worker
python worker_face.py --mode live
```

### Step 7: Start Notification Worker (Alerts & WebSockets)
Open a fifth terminal, activate your virtual environment, and run:
```bash
cd backend_api
python worker_notify.py
```

### Step 8: Start React Frontend
Open a sixth terminal and run:
```bash
cd frontend
npm run dev
```

---

## 3. Factory Reset (Nuking the System)

If your database states become corrupted during testing, or if you want to completely wipe all historical data (including extracted faces, Redis queues, and Milvus vectors), you can trigger a factory reset.

> **⚠️ WARNING:** This is a destructive operation. It will permanently delete all sightings, subjects, and saved images. However, it explicitly **does not** delete Admin users or system config settings (so you won't be locked out).

**Command:**
```bash
python nuke_system.py
```

**What `nuke_system.py` does:**
1. **Flushes Redis:** Drops all active messaging queues, locks, and temporary cache data.
2. **Drops Milvus Collections:** Completely deletes the `face_embeddings` and `watchlist_faces` vector spaces.
3. **Truncates PostgreSQL:** Drops all rows from `subjects`, `sightings`, and `cameras` via a `CASCADE` truncate.
4. **Wipes Hard Drive:** Recursively deletes the `captured_faces` directory and reconstructs an empty folder structure.

**Post-Nuke Requirement:**
You **must** restart the FastAPI backend and AI Worker after a nuke so that the system can automatically recreate the missing Milvus collections on startup.
