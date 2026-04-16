import psycopg2
from pymilvus import MilvusClient, DataType

# ==========================================
# 1. INITIALIZE POSTGRESQL (Metadata)
# ==========================================
print("⏳ Connecting to PostgreSQL...")
try:
    conn = psycopg2.connect(
        dbname="surveillance",
        user="admin",
        password="password",
        host="localhost",
        port="5432"
    )
    conn.autocommit = True
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sightings (
            id SERIAL PRIMARY KEY,
            person_id VARCHAR(100) NOT NULL,
            camera_id VARCHAR(50) NOT NULL,
            timestamp FLOAT NOT NULL,
            image_path TEXT NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON sightings(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_person_id ON sightings(person_id);")

    # ── Watchlist Metadata Table ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY,
            watchlist_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            threat_level VARCHAR(50) DEFAULT 'UNKNOWN',
            image_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_id ON watchlist(watchlist_id);")
    
    cursor.close()
    conn.close()
    print("✅ PostgreSQL 'sightings' + 'watchlist' tables ready.")
except Exception as e:
    print(f"❌ Postgres Init Error: {e}")

# ==========================================
# 2. INITIALIZE MILVUS STANDALONE (Vectors)
# ==========================================
print("\n⏳ Connecting to Milvus Standalone (Docker)...")
client = MilvusClient(uri="http://localhost:19530")

# ── Collection 1: face_embeddings (AI Worker general sightings) ──
COLLECTION_NAME = "face_embeddings"

if client.has_collection(collection_name=COLLECTION_NAME):
    print(f"Collection '{COLLECTION_NAME}' exists. Resetting for fresh start...")
    client.drop_collection(collection_name=COLLECTION_NAME)

schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
schema.add_field(field_name="person_id", datatype=DataType.VARCHAR, max_length=100)
schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)

client.create_collection(collection_name=COLLECTION_NAME, schema=schema)

index_params = client.prepare_index_params()
index_params.add_index(
    field_name="embedding",
    metric_type="COSINE",
    index_type="IVF_FLAT",
    params={"nlist": 128}
)
client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
print(f"✅ Milvus collection '{COLLECTION_NAME}' ready.")

# ── Collection 2: watchlist_faces (Enrolled suspects for live search) ──
WATCHLIST_COLLECTION = "watchlist_faces"

if client.has_collection(collection_name=WATCHLIST_COLLECTION):
    print(f"Collection '{WATCHLIST_COLLECTION}' exists. Resetting...")
    client.drop_collection(collection_name=WATCHLIST_COLLECTION)

wl_schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
wl_schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
wl_schema.add_field(field_name="watchlist_id", datatype=DataType.VARCHAR, max_length=100)
wl_schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)

client.create_collection(collection_name=WATCHLIST_COLLECTION, schema=wl_schema)

wl_index = client.prepare_index_params()
wl_index.add_index(
    field_name="embedding",
    metric_type="COSINE",
    index_type="IVF_FLAT",
    params={"nlist": 128}
)
client.create_index(collection_name=WATCHLIST_COLLECTION, index_params=wl_index)
print(f"✅ Milvus collection '{WATCHLIST_COLLECTION}' ready.")

print("\n🚀 Database Infrastructure Fully Initialized!")