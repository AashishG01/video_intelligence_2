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
    
    cursor.close()
    conn.close()
    print("✅ PostgreSQL 'sightings' table ready.")
except Exception as e:
    print(f"❌ Postgres Init Error: {e}")

# ==========================================
# 2. INITIALIZE MILVUS STANDALONE (Vectors)
# ==========================================
print("\n⏳ Connecting to Milvus Standalone (Docker)...")
# Note the URI change to use the network port
client = MilvusClient(uri="http://localhost:19530")

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
    index_type="IVF_FLAT", # Upgraded to IVF_FLAT for better scaling
    params={"nlist": 128}
)
client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)

print(f"✅ Milvus collection '{COLLECTION_NAME}' ready on Docker.")
print("\n🚀 Database Infrastructure Fully Initialized!")