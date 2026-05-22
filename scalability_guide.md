# 🚀 Scalability, System Design & DevOps — Road to 2000 Cameras

> **Current State:** 4 cameras, single-worker pipeline, PM2 on bare metal  
> **Target State:** 2000+ cameras, multi-GPU, Kubernetes, tiered processing  
> **Reference:** [ProjectPlan_v2.md](file:///c:/Users/Hp/Desktop/video_intelligence_2/ProjectPlan_v2.md)

---

## 📊 Current Bottleneck Map

Every system has a breaking point. Here's exactly where yours will fail as cameras scale:

```
Cameras    ┃ 4       ┃ 10      ┃ 50       ┃ 200      ┃ 2000
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
Ingestion  ┃ ✅ Fine ┃ ✅ Fine ┃ 🔴 CPU   ┃ 💀 Dead  ┃ 💀 Dead
           ┃         ┃         ┃ decode   ┃ RAM blow ┃
           ┃         ┃         ┃ maxed    ┃          ┃
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
Redis      ┃ ✅ Fine ┃ ✅ Fine ┃ 🟡 Slow  ┃ 🔴 OOM  ┃ 💀 Dead
Queue      ┃ ~4 MB/s ┃ ~10MB/s ┃ ~50MB/s  ┃ ~200MB/s ┃ ~2 GB/s
           ┃         ┃         ┃ ltrim    ┃ no       ┃ impossible
           ┃         ┃         ┃ dropping ┃ replay   ┃
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
AI Worker  ┃ ✅ Fine ┃ 🟡 Lag  ┃ 🔴 Queue ┃ 💀 Dead  ┃ 💀 Dead
(single)   ┃ 1 FPS   ┃ building┃ overflow ┃ single   ┃
           ┃         ┃         ┃          ┃ GPU max  ┃
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
PostgreSQL ┃ ✅ Fine ┃ ✅ Fine ┃ ✅ Fine  ┃ 🟡 Slow  ┃ 🔴 Queries
           ┃         ┃         ┃          ┃ queries  ┃ timeout
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
Milvus     ┃ ✅ Fine ┃ ✅ Fine ┃ ✅ Fine  ┃ ✅ Fine  ┃ 🟡 Index
           ┃         ┃         ┃          ┃          ┃ rebuild
━━━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━╋━━━━━━━━━━━
Monitoring ┃ ❌ None ┃ ❌ None ┃ 💀 Blind ┃ 💀 Blind ┃ 💀 Blind
```

> [!CAUTION]
> The **first things to break** are: (1) CPU-based RTSP decode in producer.py, (2) Redis as a frame queue, and (3) single face worker processing one frame at a time. These three changes alone take you from 10 cameras to 200+.

---

## 🏗️ DIMENSION 1: Ingestion Layer (Camera → Queue)

### Current Problem
[producer.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ingestion/producer.py) uses `cv2.VideoCapture` (CPU FFmpeg decode) → JPEG encode → base64 → Redis. At 50+ cameras, CPU decode alone will saturate all cores.

### Target: NVIDIA DeepStream + GStreamer

```mermaid
graph LR
    subgraph CURRENT["❌ Current (CPU-bound)"]
        A1["cv2.VideoCapture\n(CPU FFmpeg)"] --> B1["cv2.resize\n720p"]
        B1 --> C1["JPEG Q75\nbase64"]
        C1 --> D1["Redis lpush\n~1 MB/frame"]
    end

    subgraph TARGET["✅ Target (GPU-accelerated)"]
        A2["GStreamer\nNVDEC (GPU)"] --> B2["GPU memory\n(zero-copy)"]
        B2 --> C2["Kafka producer\nprotobuf"]
    end
```

### Level 1: GStreamer + NVDEC (Medium effort, 10→200 cameras)

Replace OpenCV VideoCapture with GStreamer for hardware-accelerated decode:

```python
# pip install PyGObject  (or use GStreamer C bindings via ctypes)
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

class GPUCameraProducer:
    def __init__(self, rtsp_url, camera_id):
        Gst.init(None)
        # NVDEC hardware decode → GPU memory → appsink
        self.pipeline = Gst.parse_launch(f"""
            rtspsrc location={rtsp_url} latency=100 protocols=tcp !
            rtph264depay !
            h264parse !
            nvh264dec !
            videoconvert !
            videoscale !
            video/x-raw,width=1280,height=720 !
            appsink name=sink max-buffers=2 drop=true
        """)
```

**Impact:** Offloads video decode from CPU to GPU's dedicated NVDEC hardware. CPU usage drops from ~15% per camera to ~0.5%.

### Level 2: NVIDIA DeepStream SDK (Hard effort, 200→2000 cameras)

DeepStream processes multiple RTSP streams in a single pipeline with built-in batching:

```python
# DeepStream processes 30+ streams per GPU with batching
# config: deepstream_app_config.txt
[source0]
type=4  # RTSP
uri=rtsp://admin:admin@172.16.0.151:554/live.sdp
gpu-id=0
cudadec-memtype=0  # unified memory

[streammux]
batch-size=30         # Process 30 cameras as a single GPU batch
width=1280
height=720
gpu-id=0

[primary-gie]
model-engine-file=yolov8m.engine  # TensorRT optimized
batch-size=30
```

**Impact:** A single A100 GPU can decode + run YOLO on 200+ streams simultaneously through batching.

### Level 3: Dual-Stream Architecture

Use the camera's built-in dual-stream capability:

```
Camera Output:
├── Main Stream (1080p, 8 Mbps) → NVR/Storage (30-day retention)
└── Sub Stream (480p, 1 Mbps)  → AI Pipeline (low bandwidth, sufficient for faces)
```

This cuts network bandwidth from ~16 Gbps to ~2 Gbps for 2000 cameras.

---

## 📨 DIMENSION 2: Message Queue (Redis → Kafka)

### Current Problem
Redis `lpush/brpop` works as a FIFO queue but:
- **No persistence** — if Redis crashes, all queued frames are lost
- **No partitioning** — can't route dense cameras differently from quiet ones
- **No replay** — can't reprocess frames after a worker crash
- **Memory-bound** — each base64 frame is ~1MB; 1000 queued frames = 1GB RAM
- **Single consumer** — only one worker can pull from each queue

### Target: Apache Kafka

```mermaid
graph TB
    subgraph KAFKA["Apache Kafka Cluster"]
        T1["Topic: frames.tier1\n(400 dense cameras)\nPartitions: 8"]
        T2["Topic: frames.tier2\n(800 moderate cameras)\nPartitions: 16"]
        T3["Topic: frames.tier3\n(800 light cameras)\nPartitions: 16"]
    end

    subgraph CONSUMERS["Consumer Groups"]
        CG1["Face Worker Group\n4 workers (GPU 0-1)"]
        CG2["Analytics Group\n2 workers (GPU 2)"]
        CG3["ANPR Group\n1 worker (GPU 3)"]
    end

    T1 & T2 & T3 --> CG1
    T1 & T2 & T3 --> CG2
    T1 --> CG3
```

**Key Kafka Benefits:**

| Feature | Redis (Current) | Kafka (Target) |
|---|---|---|
| Persistence | RAM only, lost on crash | Disk-persisted, configurable retention |
| Partitioning | None | By camera tier, zone, or camera ID |
| Consumer groups | Single consumer per queue | Multiple groups (face, ANPR, analytics) |
| Replay | Impossible (lpush/brpop destructive) | Any consumer can replay from any offset |
| Throughput | ~100K msgs/sec | ~1M msgs/sec per broker |
| Backpressure | ltrim drops old frames | Consumer lag monitoring, no data loss |
| Ordering | Global FIFO | Per-partition ordering |

### Docker Compose Addition

```yaml
# Add to docker-compose.yml
zookeeper:
  image: confluentinc/cp-zookeeper:7.5.0
  environment:
    ZOOKEEPER_CLIENT_PORT: 2181

kafka:
  image: confluentinc/cp-kafka:7.5.0
  ports:
    - "9092:9092"
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    KAFKA_LOG_RETENTION_HOURS: 1  # Keep frames for 1 hour
    KAFKA_MESSAGE_MAX_BYTES: 2097152  # 2MB max message
  depends_on:
    - zookeeper
```

### Intermediate Step: Redis Streams (Lower effort)

If Kafka is too big a jump, Redis Streams provide consumer groups and persistence within Redis:

```python
# Producer
r.xadd("frames:tier1", {"camera_id": cam_id, "frame": frame_bytes}, maxlen=5000)

# Consumer (with consumer group — multiple workers can share the load)
r.xreadgroup("face_workers", "worker_1", {"frames:tier1": ">"}, count=1, block=5000)
r.xack("frames:tier1", "face_workers", message_id)
```

**Redis Streams give you:** consumer groups, message acknowledgment, and persistence — without deploying Kafka. Good for 10-100 cameras.

---

## 🧠 DIMENSION 3: AI Inference (Single Worker → Triton)

### Current Problem
[worker_face.py](file:///c:/Users/Hp/Desktop/video_intelligence_2/ai_worker/worker_face.py) loads the model in-process and processes **one frame at a time**. GPU utilization is ~10-20% because most time is spent on data transfer, not compute.

### Target: NVIDIA Triton Inference Server

```mermaid
graph TB
    subgraph CURRENT["❌ Current"]
        W1["worker_face.py\nLoads model in RAM\nProcesses 1 frame/call\nGPU util: ~15%"]
    end

    subgraph TARGET["✅ Target"]
        T["Triton Inference Server"]
        T --> M1["YOLO (TensorRT FP16)\nBatch: 16\nGPU 0"]
        T --> M2["RetinaFace (TensorRT)\nBatch: 32\nGPU 1"]
        T --> M3["ArcFace (TensorRT)\nBatch: 64\nGPU 1"]

        C1["Worker 1"] --> T
        C2["Worker 2"] --> T
        C3["Worker 3"] --> T
        C4["Worker N"] --> T
    end
```

### Step 1: TensorRT Model Optimization

Convert InsightFace ONNX models to TensorRT engines for 3-5× speedup:

```bash
# Export InsightFace to ONNX (if not already)
python -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='antelopev2')
app.prepare(ctx_id=0)
# Models are already in ~/.insightface/models/antelopev2/
"

# Convert to TensorRT FP16
trtexec --onnx=det_10g.onnx \
        --saveEngine=det_10g.engine \
        --fp16 \
        --optShapes=input:16x3x640x640 \
        --minShapes=input:1x3x640x640 \
        --maxShapes=input:32x3x640x640
```

### Step 2: Triton Model Repository

```
model_repository/
├── yolov8m/
│   ├── config.pbtxt
│   └── 1/
│       └── model.plan          # TensorRT engine
├── retinaface/
│   ├── config.pbtxt
│   └── 1/
│       └── model.plan
└── arcface/
    ├── config.pbtxt
    └── 1/
        └── model.plan
```

```protobuf
# config.pbtxt for dynamic batching
name: "retinaface"
platform: "tensorrt_plan"
max_batch_size: 32
dynamic_batching {
  preferred_batch_size: [8, 16, 32]
  max_queue_delay_microseconds: 5000
}
instance_group [{
  count: 1
  kind: KIND_GPU
  gpus: [1]
}]
```

### Step 3: Worker Calls Triton via gRPC

```python
import tritonclient.grpc as grpcclient

client = grpcclient.InferenceServerClient(url="localhost:8001")

# Batch 16 face crops into a single GPU call
inputs = [grpcclient.InferInput("input", [16, 3, 112, 112], "FP32")]
inputs[0].set_data_from_numpy(batch_of_faces)

results = client.infer("arcface", inputs)
embeddings = results.as_numpy("output")  # [16, 512] — 16 embeddings at once!
```

**Impact:** GPU utilization goes from ~15% to ~85%. A single A100 can process 500+ faces/second with batching.

### Intermediate Step: Batch Processing Without Triton

Even without Triton, you can batch within the existing worker:

```python
BATCH_SIZE = 8
BATCH_TIMEOUT = 0.5  # seconds

batch = []
while True:
    result = r.rpop("face_ready_queue")
    if result:
        batch.append(json.loads(result))
    
    if len(batch) >= BATCH_SIZE or (batch and time.time() - batch_start > BATCH_TIMEOUT):
        # Process all frames in batch
        for payload in batch:
            frame = decode_frame(payload)
            faces = face_app.get(frame)  # Still 1-at-a-time, but reduces queue latency
            process_faces(faces, payload)
        batch = []
```

---

## 🗄️ DIMENSION 4: Database & Storage

### PostgreSQL → TimescaleDB

**Current Problem:** The `sightings` table will grow to **30-50M rows/day** at 2000 cameras. Standard PostgreSQL queries will slow to a crawl.

```sql
-- Convert sightings to a TimescaleDB hypertable
-- Automatically partitions by time, enables chunk-based deletion

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Add a proper timestamp column
ALTER TABLE sightings ADD COLUMN created_at TIMESTAMPTZ 
    DEFAULT NOW();

-- Convert to hypertable (partition every 1 day)
SELECT create_hypertable('sightings', 'created_at',
    chunk_time_interval => INTERVAL '1 day',
    migrate_data => true
);

-- Auto-delete chunks older than 30 days
SELECT add_retention_policy('sightings', INTERVAL '30 days');

-- Continuous aggregate for dashboard stats (pre-computed)
CREATE MATERIALIZED VIEW hourly_stats
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', created_at) AS hour,
    camera_id,
    COUNT(*) AS face_count,
    COUNT(DISTINCT person_id) AS unique_persons
FROM sightings
GROUP BY hour, camera_id;
```

**Impact:** Queries on time-ranges become O(1) instead of scanning millions of rows. 30-day auto-purge runs in milliseconds (just drop a chunk).

### Milvus Partitioning

Partition the `face_embeddings` collection by day for efficient lifecycle management:

```python
from pymilvus import Partition

# Create daily partition
today = datetime.now().strftime("%Y%m%d")
partition_name = f"day_{today}"

if not collection.has_partition(partition_name):
    collection.create_partition(partition_name)

# Insert into today's partition
milvus_client.insert(
    collection_name=COLLECTION_NAME,
    data=[{"person_id": pid, "embedding": emb}],
    partition_name=partition_name
)

# Drop 31-day-old partition (instant deletion of millions of vectors)
old_partition = f"day_{(datetime.now() - timedelta(days=31)).strftime('%Y%m%d')}"
if collection.has_partition(old_partition):
    collection.drop_partition(old_partition)
```

### Milvus Index: IVF_FLAT → IVF_PQ for Billion-Scale

```python
# Current: IVF_FLAT (full precision, high memory)
# At 1B vectors × 512 floats × 4 bytes = 2 TB RAM — impossible

# Target: IVF_PQ (compressed to 64 bytes/vector)
# At 1B vectors × 64 bytes = 64 GB RAM — feasible on A100 80GB

index_params = {
    "index_type": "IVF_PQ",
    "metric_type": "COSINE",
    "params": {
        "nlist": 2048,      # More clusters for billion-scale
        "m": 64,            # 64 subquantizers (512/64 = 8 dims each)
        "nbits": 8          # 8-bit codes per subquantizer
    }
}
```

### MinIO for Face Crop Storage

Stop saving face crops to local disk. Use MinIO (already in Docker) for distributed S3-compatible storage:

```python
from minio import Minio

minio_client = Minio("localhost:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

# Upload face crop
bucket = "face-crops"
object_name = f"{person_id}/{camera_id}_{timestamp}.jpg"
_, buffer = cv2.imencode('.jpg', face_crop)
minio_client.put_object(bucket, object_name, io.BytesIO(buffer), len(buffer),
                         content_type="image/jpeg")

# Generate presigned URL for React frontend
url = minio_client.presigned_get_object(bucket, object_name, expires=timedelta(hours=1))
```

**Why:** Local disk doesn't scale across multiple worker nodes. MinIO is already running in your Docker stack.

---

## 🔧 DIMENSION 5: Software Engineering Patterns

### 5.1 — Microservice Decomposition

**Current:** One monolithic `newapi.py` (978 lines) handles everything — auth, WebSocket, search, CRUD, settings, streaming.

**Target:** Split into focused services:

```
services/
├── api-gateway/           ← Route requests, rate limiting, auth
│   └── Nginx + JWT validation
├── auth-service/          ← Login, register, token management
│   └── FastAPI (50 lines)
├── search-service/        ← Image upload → embed → Milvus search
│   └── FastAPI + InsightFace + Milvus client
├── watchlist-service/     ← Subject CRUD, category management
│   └── FastAPI + PostgreSQL + Milvus
├── alert-service/         ← WebSocket hub + email dispatch
│   └── FastAPI + Redis pub/sub + SMTP
├── camera-service/        ← Camera CRUD, RTSP validation
│   └── FastAPI + PostgreSQL
├── settings-service/      ← System config, threshold management
│   └── FastAPI + Redis + PostgreSQL
└── ingestion-service/     ← Camera frame capture + queue
    └── Python + GStreamer + Kafka
```

**Why:** Independent scaling (search needs GPU, auth doesn't), independent deployment, fault isolation (auth crash doesn't kill alerts).

### 5.2 — Environment Configuration (`.env` + Pydantic Settings)

**Current:** Credentials hardcoded in 6+ files. No `.env` file.

```python
# config.py — Single source of truth
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "admin"
    pg_password: str = "password"
    pg_database: str = "surveillance"
    pg_pool_min: int = 2
    pg_pool_max: int = 10
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Milvus
    milvus_uri: str = "http://localhost:19530"
    
    # JWT
    jwt_secret_key: str  # REQUIRED — no default
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    
    # AI
    match_threshold: float = 0.35
    det_thresh: float = 0.5
    det_size: int = 1024
    confidence_gate: float = 0.75
    dedup_window_sec: int = 60
    
    # SMTP
    smtp_sender_email: str = ""
    smtp_app_password: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

### 5.3 — Async Database Access

**Current:** Synchronous `psycopg2` blocks the FastAPI event loop.

```python
# Target: asyncpg for true async database access
import asyncpg

# Startup
pool = await asyncpg.create_pool(
    dsn="postgresql://admin:password@localhost:5432/surveillance",
    min_size=5, max_size=20
)

# In endpoints
@app.get("/api/system/stats")
async def get_stats():
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM sightings")
        unique = await conn.fetchval("SELECT COUNT(DISTINCT person_id) FROM sightings")
    return {"total": total, "unique": unique}
```

### 5.4 — Circuit Breaker Pattern

Prevent cascading failures when downstream services (Milvus, PostgreSQL) are down:

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=30)
def search_milvus(embedding):
    return milvus_client.search(
        collection_name=COLLECTION_NAME,
        data=[embedding], limit=1,
        search_params={"metric_type": "COSINE", "params": {"nprobe": 32}}
    )

# After 5 consecutive failures, circuit opens for 30 seconds
# During that time, calls fail immediately without hitting Milvus
# After 30 seconds, circuit enters half-open state and retries
```

### 5.5 — Structured Logging

**Current:** `print()` statements everywhere. No searchable logs.

```python
import structlog

logger = structlog.get_logger()

# Instead of: print(f"[{cam_id}] 🚨 WATCHLIST HIT: {name}")
logger.info("watchlist_match",
    camera_id=cam_id,
    person_id=person_id,
    suspect_name=name,
    risk_level=risk_level,
    distance=wl_dist,
    threshold=CURRENT_MATCH_THRESHOLD,
    is_armed=is_armed
)

# Output (JSON, searchable by any field):
# {"event":"watchlist_match","camera_id":"cam1","person_id":"SUB_xxx",
#  "suspect_name":"John Doe","risk_level":"High","distance":0.18,
#  "threshold":0.35,"is_armed":true,"timestamp":"2026-05-22T10:30:00Z"}
```

**Why:** JSON logs can be aggregated by Loki/ELK, queried by any field, and dashboarded in Grafana.

### 5.6 — Health Check Endpoints

```python
@app.get("/health")
async def health():
    """Kubernetes readiness/liveness probe target."""
    checks = {}
    
    # PostgreSQL
    try:
        conn = get_pg_connection()
        conn.cursor().execute("SELECT 1")
        conn.close()
        checks["postgres"] = "ok"
    except:
        checks["postgres"] = "error"
    
    # Redis
    try:
        r.ping()
        checks["redis"] = "ok"
    except:
        checks["redis"] = "error"
    
    # Milvus
    try:
        milvus_client.has_collection(COLLECTION_NAME)
        checks["milvus"] = "ok"
    except:
        checks["milvus"] = "error"
    
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "degraded", "checks": checks}
    )
```

---

## 🐳 DIMENSION 6: DevOps & Infrastructure

### 6.1 — Production Dockerfiles (Multi-Stage Builds)

**Current:** No Dockerfiles for Python services — running directly on host.

```dockerfile
# Dockerfile for face worker
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04 AS base

# System deps
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (changes frequently — last layer)
COPY ai_worker/ /app/ai_worker/
WORKDIR /app/ai_worker

# Pre-download model on build (not at runtime)
RUN python3 -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='antelopev2')"

CMD ["python3", "worker_face.py"]
```

### 6.2 — Kubernetes Deployment

```yaml
# k8s/face-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: face-worker
spec:
  replicas: 4  # 4 workers across GPUs
  selector:
    matchLabels:
      app: face-worker
  template:
    metadata:
      labels:
        app: face-worker
    spec:
      containers:
      - name: face-worker
        image: core/face-worker:latest
        resources:
          limits:
            nvidia.com/gpu: 1  # Each pod gets 1 GPU
          requests:
            memory: "8Gi"
            cpu: "2"
        env:
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: core-config
              key: redis-url
        - name: PG_PASSWORD
          valueFrom:
            secretKeyRef:
              name: core-secrets
              key: pg-password
        livenessProbe:
          exec:
            command: ["python3", "-c", "import redis; redis.Redis().ping()"]
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          exec:
            command: ["python3", "-c", "import redis; redis.Redis().llen('face_ready_queue')"]
          initialDelaySeconds: 10
          periodSeconds: 10
      nodeSelector:
        nvidia.com/gpu.product: "NVIDIA-A100-SXM4-80GB"
```

### Horizontal Pod Autoscaler (HPA)

```yaml
# Scale face workers based on queue depth
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: face-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: face-worker
  minReplicas: 2
  maxReplicas: 8
  metrics:
  - type: External
    external:
      metric:
        name: redis_queue_length
        selector:
          matchLabels:
            queue: face_ready_queue
      target:
        type: AverageValue
        averageValue: "100"  # Scale up when >100 frames queued per worker
```

### 6.3 — Prometheus + Grafana Monitoring

```yaml
# docker-compose monitoring addition
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    GF_SECURITY_ADMIN_PASSWORD: admin
```

**Custom metrics to export from your workers:**

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Start metrics server on port 8090
start_http_server(8090)

# Counters
faces_detected = Counter('faces_detected_total', 'Total faces detected', ['camera_id', 'status'])
watchlist_hits = Counter('watchlist_hits_total', 'Watchlist matches', ['risk_level'])

# Histograms
inference_latency = Histogram('inference_duration_seconds', 'Face detection latency',
                               buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0])
milvus_search_latency = Histogram('milvus_search_seconds', 'Milvus search latency')

# Gauges
queue_depth = Gauge('face_queue_depth', 'face_ready_queue length')
gpu_utilization = Gauge('gpu_utilization_percent', 'GPU utilization', ['gpu_id'])
active_cameras = Gauge('active_cameras', 'Number of active camera streams')

# Usage in worker loop
with inference_latency.time():
    faces = face_app.get(frame)

faces_detected.labels(camera_id=cam_id, status="NEW").inc()
queue_depth.set(r.llen("face_ready_queue"))
```

**Grafana Dashboard Panels:**

| Panel | Query | Alert Threshold |
|---|---|---|
| Queue Depth | `face_queue_depth` | > 500 for 5 min |
| Inference Latency P99 | `histogram_quantile(0.99, inference_duration_seconds)` | > 1s |
| Faces/Second | `rate(faces_detected_total[1m])` | < 1 for 5 min |
| Watchlist Hits/Hour | `increase(watchlist_hits_total[1h])` | > 10 (anomaly) |
| GPU Utilization | `gpu_utilization_percent` | < 20% (underutilized) |
| Camera Offline | `active_cameras` | < expected count |

### 6.4 — CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Build & Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: pytest tests/ -v
      - name: Lint
        run: ruff check .

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker images
        run: |
          docker build -t core/face-worker:${{ github.sha }} -f docker/face-worker.Dockerfile .
          docker build -t core/api:${{ github.sha }} -f docker/api.Dockerfile .
          docker build -t core/frontend:${{ github.sha }} -f docker/frontend.Dockerfile .
      
      - name: Push to registry
        run: |
          docker push core/face-worker:${{ github.sha }}
          docker push core/api:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Rolling update
        run: |
          kubectl set image deployment/face-worker \
            face-worker=core/face-worker:${{ github.sha }}
          kubectl set image deployment/api \
            api=core/api:${{ github.sha }}
          kubectl rollout status deployment/face-worker --timeout=300s
```

### 6.5 — Blue-Green Deployment for Zero Downtime

```yaml
# Two identical deployments — blue (current) and green (new)
# Switch traffic via service selector

apiVersion: v1
kind: Service
metadata:
  name: api
spec:
  selector:
    app: api
    version: blue    # ← Flip to "green" to switch
  ports:
  - port: 8000
```

### 6.6 — Secrets Management

**Current:** Passwords in source code and environment variables.  
**Target:** Kubernetes Secrets or HashiCorp Vault:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: core-secrets
type: Opaque
data:
  pg-password: cGFzc3dvcmQ=          # base64 encoded
  jwt-secret: <generated-256-bit-key>
  smtp-password: <app-password>
  minio-secret: bWluaW9hZG1pbg==
```

---

## 📈 Scaling Roadmap (Phased)

### Phase 1: Quick Wins (1-2 weeks) — 4→50 cameras

| Change | File | Impact |
|---|---|---|
| Create `.env` file with Pydantic Settings | All | No more hardcoded credentials |
| Increase JPEG quality to 92 | producer.py | Better face detection quality |
| Add health check endpoints | newapi.py | Foundation for monitoring |
| Replace `print()` with `structlog` | All workers | Searchable, structured logs |
| Add Prometheus metrics to workers | worker_face.py | Visibility into pipeline |
| Redis Streams instead of lpush/brpop | producer.py, workers | Consumer groups, persistence |
| Multiple face workers (same queue) | PM2 config | 2-4× throughput |

### Phase 2: Containerization (2-4 weeks) — 50→200 cameras

| Change | Impact |
|---|---|
| Write Dockerfiles for all services | Reproducible deployment |
| Docker Compose with all services | One-command startup |
| GStreamer + NVDEC for camera decode | CPU offloading |
| TensorRT model conversion | 3-5× inference speedup |
| Async database access (asyncpg) | Non-blocking API |
| Batch inference in face worker | 2-4× GPU utilization |
| TimescaleDB for sightings | Time-range queries, auto-retention |
| Milvus daily partitions | Efficient 30-day lifecycle |

### Phase 3: Distributed Architecture (4-8 weeks) — 200→2000 cameras

| Change | Impact |
|---|---|
| Apache Kafka for frame pipeline | Fault-tolerant, partitioned, replayable |
| NVIDIA Triton Inference Server | Dynamic batching, multi-GPU, hot-swap |
| DeepStream for stream ingestion | 200+ streams per GPU |
| Microservice decomposition | Independent scaling |
| Kubernetes deployment | Auto-scaling, GPU scheduling |
| Prometheus + Grafana + Alertmanager | Full observability |
| CI/CD pipeline | Automated testing + deployment |
| MinIO for face crop storage | Distributed storage |
| Milvus IVF_PQ index | Billion-scale vector search |
| Blue-green deployments | Zero-downtime updates |

---

## 🎯 Priority Matrix: What to Do First

```
                        IMPACT
                 Low ─────────── High
            ┌────────────┬────────────┐
     Low    │ Structured │ .env +     │
            │ logging    │ Pydantic   │
    EFFORT  │            │ Settings   │
            │ Health     │ JPEG Q92   │
            │ endpoints  │ Prometheus │
            ├────────────┼────────────┤
            │ MinIO      │ Docker-    │
     High   │ storage    │ ization    │
            │            │            │
            │ Blue-green │ Kafka +    │
            │ deploys    │ Triton +   │
            │            │ K8s        │
            └────────────┴────────────┘
```

> [!IMPORTANT]
> **Start with the top-right quadrant** (high impact, low effort): `.env` configuration, Prometheus metrics, JPEG quality, and Dockerfiles. These changes de-risk the entire scaling journey and can be done in days, not weeks.
