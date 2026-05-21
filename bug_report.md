# 🐛 Bug Report — video_intelligence_2

---

## 🔴 CRITICAL Bugs

### 1. `tracker/worker_face.py` — Wrong Milvus Match Comparison (Logic Inverted)
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/tracker/worker_face.py#L123)  
**Line:** 123

```python
# BUG: Using > for COSINE DISTANCE (lower = more similar)
if top['distance'] > MATCH_THRESHOLD:
```

**Problem:** Milvus returns **cosine distance** (0.0 = identical, 1.0 = totally different). A match means the distance is **LOW**, not high. This logic is **completely inverted** — it will identify strangers as known people and known people as strangers. The `ai_worker/worker_face.py` (line 223) correctly uses `< CURRENT_MATCH_THRESHOLD`, but this file has it backwards.

**Fix:**
```python
if top['distance'] < MATCH_THRESHOLD:
```

---

### 2. `ai_worker/worker_face.py` — Wrong Cosine Distance Threshold Logic for Watchlist
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py#L177)  
**Line:** 177

```python
# BUG: Cosine DISTANCE threshold is < 0.60, but this means low similarity
if wl_dist < CURRENT_MATCH_THRESHOLD:  # MATCH_THRESHOLD = 0.60
```

**Problem:** With `metric_type="COSINE"`, Milvus returns a **distance** (0 = perfect match, 1 = no match). So a value of `0.60` being treated as a match threshold for `<` means only very similar faces (close to 0.0) are flagged. However, `MATCH_THRESHOLD = 0.60` in the code is actually configured as if it were a **similarity score** (where 0.60 means "60% confident"). The threshold value is semantically wrong for a distance metric — it should be a low value (e.g., `0.30` distance ≈ `0.70` similarity). This is a conceptual bug that will cause false negatives or false positives depending on the actual data distribution.

> [!WARNING]
> The watchlist threshold for distance should be a small number (e.g., 0.35), not 0.60, unless you intend it as cosine distance. Audit and align the threshold with actual cosine distance semantics.

---

### 3. `backend_api/worker_notify.py` — Plaintext SMTP Password in Source Code
**File:** [worker_notify.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/worker_notify.py#L14)  
**Line:** 14

```python
SENDER_PASSWORD = "rbol hixn fntu rrpy"  # Hardcoded Gmail App Password
```

**Problem:** A real Gmail app password is hardcoded in plaintext in the source file. This is a **critical security vulnerability** — anyone with access to the repo (or if it's ever pushed to GitHub) will have credentials to send email from this account.

**Fix:** Load from environment variable:
```python
import os
SENDER_PASSWORD = os.environ.get("SMTP_APP_PASSWORD")
```

---

### 4. `backend_api/auth.py` — Hardcoded Secret Key
**File:** [auth.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/auth.py#L8)  
**Line:** 8

```python
SECRET_KEY = "core_surveillance_absolute_zero_trust_key"
```

**Problem:** The JWT signing key is hardcoded. If this is committed to source control, all tokens can be forged by anyone who reads the code.

**Fix:**
```python
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable not set")
```

---

### 5. `backend_api/newapi.py` — Global DB Connections Never Made — Race on Startup
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L76-L77)  
**Lines:** 76–77

```python
def get_pg_connection():
    return psycopg2.connect(...)
```

**Problem:** Every single API endpoint calls `get_pg_connection()`, which opens a **brand-new database connection** on every request and closes it at the end. Under any real concurrency load, this will:
- Exhaust PostgreSQL's `max_connections` limit
- Cause significant latency from TCP connection setup on every request

**Fix:** Use a connection pool (`psycopg2.pool.ThreadedConnectionPool` or `asyncpg` with `asyncio`).

---

## 🟠 HIGH Severity Bugs

### 6. `ai_worker/worker_face.py` — Missing Sighting Insert for Watchlist Matches
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py#L258-L271)  
**Lines:** 258–271

```python
# ── SAVE TO DATABASE (Only for non-watchlist sightings) ──
if not is_watchlist_match:
    milvus_client.insert(...)
    pg_cursor.execute("INSERT INTO sightings ...")
```

**Problem:** When a **watchlist match** is detected, the sighting is **never written to the `sightings` PostgreSQL table**. This means watchlist hits are invisible in the investigation/timeline views. The face image is saved to disk, but there's no DB record. The investigation API (`/api/investigate/person/{person_id}`) will return 404 for watchlist suspects.

**Fix:** Also insert into `sightings` for watchlist matches (after saving the image).

---

### 7. `ai_worker/worker_face.py` — Milvus `flush()` Called Per-Frame (Performance Killer)
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py#L263)  
**Line:** 263

```python
milvus_client.flush(collection_name=COLLECTION_NAME)
```

**Problem:** `flush()` forces Milvus to seal segments and persist data immediately. Calling this on **every single face detection** is extremely slow and will bottleneck the entire pipeline. The worker will stall for hundreds of milliseconds per face.

**Fix:** Remove the per-frame flush. Milvus auto-flushes. Or flush periodically (e.g., every 100 inserts).

---

### 8. `tracker/worker_face.py` — `brpop` with `timeout=1` Returns `None` When Queue Empty
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/tracker/worker_face.py#L180-L183)  
**Lines:** 180–183

```python
queue_name, msg = r.brpop("face_ready_queue", timeout=1)

# If queue is empty, still check for timeouts, then loop
if msg:
```

**Problem:** When `brpop` times out (queue empty), it returns `None`, not a tuple. The unpacking `queue_name, msg = r.brpop(...)` will **crash with `TypeError: cannot unpack non-iterable NoneType object`** when the queue is empty.

**Fix:**
```python
result = r.brpop("face_ready_queue", timeout=1)
if result:
    queue_name, msg = result
    # ... process msg
```

---

### 9. `backend_api/newapi.py` — WebSocket Memory Leak (pubsub not closed on error)
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L152-L160)  
**Lines:** 152–160

```python
try:
    while True:
        ...
except WebSocketDisconnect:
    pubsub.unsubscribe()
```

**Problem:** If any **other exception** (network error, Redis failure, etc.) is raised inside the `while True` loop, the `pubsub` connection is never unsubscribed/closed. This leaks Redis pubsub subscriptions on every unexpected disconnect.

**Fix:**
```python
try:
    while True:
        ...
except WebSocketDisconnect:
    pass
finally:
    pubsub.unsubscribe()
    pubsub.close()
```

---

### 10. `Ingestion/producer_folder.py` — Frame Skip Division by Zero
**File:** [producer_folder.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/Ingestion/producer_folder.py#L42-L61)  
**Lines:** 42, 61

```python
frames_to_skip = int(video_fps * self.process_every_n_seconds)
# ...
if frame_counter % frames_to_skip != 0:
```

**Problem:** If `video_fps = 0.5` and `process_every_n_seconds = 1`, then `frames_to_skip = int(0.5 * 1) = 0`. A modulo by zero (`frame_counter % 0`) raises `ZeroDivisionError`. The `math.isnan` fallback only covers NaN, not very low but valid FPS values.

**Fix:**
```python
frames_to_skip = max(1, int(video_fps * self.process_every_n_seconds))
```

---

### 11. `backend_api/newapi.py` — Duplicate Imports
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L12-L24)  
**Lines:** 12, 23, 24

```python
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends  # line 12
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, WebSocket, Form, Depends  # line 23
import psycopg2  # line 9 and line 24 (duplicate)
from pydantic import BaseModel  # imported at line 18, again at line 784, again at line 807
import json  # line 8 and line 809
from typing import List  # line 22 and line 808
```

**Problem:** Multiple duplicate imports scattered throughout the file. While Python handles this without crashing, it indicates the code has been haphazardly assembled, `Form` is only imported in the second `fastapi` import (line 23), and if the first import is ever cleaned up and the second removed, `Form` is lost.

---

## 🟡 MEDIUM Severity Bugs

### 12. `backend_api/newapi.py` — `generate_mjpeg` is a Sync Generator in Async Context
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L165-L178)  
**Lines:** 165–178

```python
def generate_mjpeg(cam_id):  # Sync generator
    while True:
        frame_b64 = r_bytes.get(...)
        time.sleep(0.1)  # Blocking sleep in sync generator!
        ...

@app.get("/api/stream/{cam_id}")
async def video_stream(cam_id: str):
    return StreamingResponse(generate_mjpeg(cam_id), ...)
```

**Problem:** `generate_mjpeg` uses `time.sleep()` (blocking) inside a synchronous generator that's run by an async FastAPI endpoint. This **blocks the entire event loop thread** for 100ms every time a frame isn't ready, making the server unresponsive to other requests during that time.

**Fix:** Use an async generator with `asyncio.sleep`:
```python
async def generate_mjpeg(cam_id):
    while True:
        frame_b64 = r_bytes.get(f"latest_frame_{cam_id}")
        if not frame_b64:
            await asyncio.sleep(0.1)
            continue
        img_bytes = base64.b64decode(frame_b64)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
```

---

### 13. `backend_api/newapi.py` — `startup_db_check` uses deprecated `@app.on_event`
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L221)  
**Line:** 221

```python
@app.on_event("startup")
def startup_db_check():
```

**Problem:** `@app.on_event("startup")` is **deprecated** in FastAPI (since v0.93). Modern FastAPI uses `lifespan` context managers.

**Fix:**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_db_check()
    yield

app = FastAPI(lifespan=lifespan, ...)
```

---

### 14. `ai_worker/worker_face.py` — DB Error Silently Swallowed, Processing Continues
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py#L197-L199)  
**Lines:** 197–199

```python
except Exception as db_err:
    matched_suspect_name = wl_id  # Falls back to ID as name
    print(f"⚠️  Database Fetch Error: {db_err}")
```

**Problem:** If the PostgreSQL connection is dead, the worker silently continues without knowing the suspect's name or risk level. The alert is still sent with `risk_level = "UNKNOWN"`. However, the outer loop's auto-recovery on line 341 (`elif "connection" in error_msg.lower()`) will **never trigger** for this inner error because it is caught here. A DB connection loss won't be auto-healed.

---

### 15. `tracker/worker_face.py` — Wrong SAVE_FOLDER Path
**File:** [worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/tracker/worker_face.py#L52)  
**Line:** 52

```python
SAVE_FOLDER = "../4_backend_api/captured_faces"
```

**Problem:** The folder name `4_backend_api` does not match the actual directory name `backend_api`. This path is wrong and will create a new orphaned directory `4_backend_api` rather than writing to the shared `backend_api/captured_faces` folder that the FastAPI server mounts.

**Fix:**
```python
SAVE_FOLDER = "../backend_api/captured_faces"
```

---

### 16. `backend_api/newapi.py` — `/api/investigate/search_by_image` Silently Returns Wrong Results on DB Error
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L451-L452)  
**Lines:** 451–452

```python
except Exception:
    return {"suspect_found": False, "total_sightings": 0, "sightings": []}
```

**Problem:** Any Milvus search exception (collection not loaded, connection error, etc.) silently returns a "not found" response. The client has no way to distinguish between "genuinely no results" and "the vector DB crashed". This masks real errors.

**Fix:** Return an HTTP 500 or log the error and re-raise.

---

### 17. `backend_api/newapi.py` — `update_alert_settings` always returns 200 even on failure
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L907)  
**Line:** 907

```python
return {"message": "Configuration deployed successfully", "status": "success"}
```

**Problem:** Even if Redis update fails AND Postgres update fails, the API still returns `{"status": "success"}` to the client. The client will believe settings were saved when they weren't.

---

### 18. `backend_api/newapi.py` — `list_subjects` Only Returns Subjects With Active Watchlist Membership
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L597-L613)  
**Lines:** 605–607

```python
JOIN watchlist_members wm ON s.id = wm.subject_id
JOIN watchlist_categories c ON wm.category_id = c.id
WHERE wm.is_active = TRUE
```

**Problem:** This is an `INNER JOIN`, so any subject who has **no active watchlist membership** (e.g., newly enrolled, or membership deactivated) will be **completely invisible** in the list. The `GROUP BY s.id` without all non-aggregated columns will also fail on strict PostgreSQL configs (missing `s.subject_uuid`, `s.full_name`, etc. in GROUP BY).

---

## 🔵 LOW Severity / Code Quality Issues

### 19. `Ingestion/producer.py` — Hardcoded Camera Credentials in Source
**File:** [producer.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/Ingestion/producer.py#L77-L80)  
**Lines:** 77–80

```python
"cam3": "rtsp://admin:admin@202.71.0.244:554/live.sdp",
"cam4": "rtsp://admin:Admin@123@172.16.0.162:554/live.sdp"
```

**Problem:** Camera RTSP credentials (including what appears to be a real public IP `202.71.0.244`) are hardcoded in source. Should be loaded from environment variables or a config file that is gitignored.

---

### 20. `ai_worker/worker_yolo.py` — No `KeyboardInterrupt` Handling
**File:** [worker_yolo.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_yolo.py#L71)  
**Line:** 71

```python
except Exception as e:
    print(f"⚠️ YOLO Error: {e}")
```

**Problem:** Unlike `worker_face.py`, the YOLO worker has no `except KeyboardInterrupt` clause. Pressing Ctrl+C will cause the exception to be caught by the generic `except Exception`, printed, and the loop will continue indefinitely. The only way to actually stop it is to kill the process.

**Fix:** Add `except KeyboardInterrupt: break` before `except Exception`.

---

### 21. `backend_api/worker_notify.py` — Email CSS Typo (`max-w` instead of `max-width`)
**File:** [worker_notify.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/worker_notify.py#L45)  
**Line:** 45

```html
<div style="max-w: 600px; ...">
```

**Problem:** `max-w` is not a valid CSS property. The correct property is `max-width`. This means the email container will have no max-width constraint and may render incorrectly in email clients.

**Fix:**
```html
<div style="max-width: 600px; ...">
```

---

### 22. `backend_api/newapi.py` — CORS Wildcard (`allow_origins=["*"]`) with Credentials
**File:** [newapi.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/backend_api/newapi.py#L33-L38)  
**Lines:** 33–38

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    ...
)
```

**Problem:** According to the CORS specification, browsers will **reject** `allow_credentials=True` when `allow_origins=["*"]`. In practice, FastAPI/Starlette may handle this differently, but it's a misconfiguration — you cannot use wildcard origins with credentials. Set explicit allowed origins for production.

---

### 23. `Ingestion/producer_folder.py` — Hardcoded Linux Path
**File:** [producer_folder.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/Ingestion/producer_folder.py#L98)  
**Line:** 98

```python
FOLDER_PATH = "/home/user/Desktop/Video Surveillence ETE/samplefootage"
```

**Problem:** Hardcoded Linux absolute path. Will immediately fail on Windows with "folder does not exist." Also contains a typo: "Surveillence" should be "Surveillance".

---

## Summary Table

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | 🔴 Critical | `tracker/worker_face.py:123` | Cosine distance comparison inverted — match logic backwards |
| 2 | 🔴 Critical | `ai_worker/worker_face.py:177` | Threshold semantics confusion (distance vs similarity) |
| 3 | 🔴 Critical | `worker_notify.py:14` | Plaintext SMTP password hardcoded |
| 4 | 🔴 Critical | `auth.py:8` | JWT secret key hardcoded |
| 5 | 🔴 Critical | `newapi.py:76` | New DB connection per request — no connection pooling |
| 6 | 🟠 High | `ai_worker/worker_face.py:258` | Watchlist sightings never written to PostgreSQL |
| 7 | 🟠 High | `ai_worker/worker_face.py:263` | `milvus.flush()` called per-frame — severe performance bottleneck |
| 8 | 🟠 High | `tracker/worker_face.py:180` | `brpop` timeout crash — unpacking `None` |
| 9 | 🟠 High | `newapi.py:158` | WebSocket pubsub leak on unexpected disconnect |
| 10 | 🟠 High | `producer_folder.py:42` | Division by zero in frame skip when FPS < 1 |
| 11 | 🟠 High | `newapi.py:12-24` | Duplicate/fragmented imports — missing `Form` if cleaned |
| 12 | 🟡 Medium | `newapi.py:165` | Sync blocking `time.sleep()` in streaming response blocks event loop |
| 13 | 🟡 Medium | `newapi.py:221` | Deprecated `@app.on_event("startup")` |
| 14 | 🟡 Medium | `ai_worker/worker_face.py:197` | DB error silently swallowed, auto-recovery bypassed |
| 15 | 🟡 Medium | `tracker/worker_face.py:52` | Wrong `SAVE_FOLDER` path (`4_backend_api` vs `backend_api`) |
| 16 | 🟡 Medium | `newapi.py:451` | Silent "not found" response on Milvus search failure |
| 17 | 🟡 Medium | `newapi.py:907` | Always returns success even when Redis + PG both fail |
| 18 | 🟡 Medium | `newapi.py:605` | `list_subjects` misses subjects with no active membership; GROUP BY may fail |
| 19 | 🔵 Low | `producer.py:77-80` | Camera RTSP credentials + public IP hardcoded |
| 20 | 🔵 Low | `worker_yolo.py:71` | No `KeyboardInterrupt` handler — Ctrl+C doesn't stop the loop |
| 21 | 🔵 Low | `worker_notify.py:45` | CSS typo `max-w` instead of `max-width` in email template |
| 22 | 🔵 Low | `newapi.py:33-38` | CORS wildcard + credentials is a spec violation |
| 23 | 🔵 Low | `producer_folder.py:98` | Hardcoded Linux path with typo |
