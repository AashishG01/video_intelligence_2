import psycopg2
from pymilvus import MilvusClient, DataType

# ==========================================
# 1. INITIALIZE POSTGRESQL (Metadata & RBAC)
# ==========================================
print("⏳ Connecting to PostgreSQL...")
try:
    # Use your actual credentials here
    conn = psycopg2.connect(
        dbname="surveillance",
        user="admin",
        password="password",
        host="localhost",
        port="5432"
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # --- Sightings Table (General AI Detections) ---
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

    # --- Auth Table (RBAC) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # --- NEW: Subject Master Table (Identity Dossier) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            subject_uuid VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            age INT,
            gender VARCHAR(20),
            occupation VARCHAR(255),
            physical_description TEXT,
            risk_level VARCHAR(20) DEFAULT 'Low' CHECK (risk_level IN ('Low','Medium','High','Extreme')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # --- NEW: Watchlist Category Definitions ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            color_code VARCHAR(10) DEFAULT '#3b82f6',
            description TEXT
        );
    """)

    # --- NEW: Watchlist Members (Linkage) ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_members (
            id SERIAL PRIMARY KEY,
            subject_id INT REFERENCES subjects(id) ON DELETE CASCADE,
            category_id INT REFERENCES watchlist_categories(id) ON DELETE CASCADE,
            added_by VARCHAR(50),
            notes TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # --- NEW: Seed Default Categories (Avoids duplicates with ON CONFLICT) ---
    cursor.execute("""
        INSERT INTO watchlist_categories (name, color_code, description) VALUES
        ('Blacklist',      '#ef4444', 'Dangerous. Detain on sight.'),
        ('Most Wanted',    '#f97316', 'High priority. Gather intelligence.'),
        ('Missing Person', '#3b82f6', 'Report sighting to family/authority.'),
        ('VIP',            '#a855f7', 'High-value individual. Notify supervisor.')
        ON CONFLICT (name) DO NOTHING;
    """)
    
    print("✅ PostgreSQL Infrastructure Ready (RBAC + Dossier + Watchlists).")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ Postgres Init Error: {e}")


# ==========================================
# 2. INITIALIZE MILVUS STANDALONE (Vectors)
# ==========================================
print("\n⏳ Connecting to Milvus Standalone...")
client = MilvusClient(uri="http://localhost:19530")

# --- Collection 1: face_embeddings (General Search) ---
COLLECTION_NAME = "face_embeddings"
if not client.has_collection(collection_name=COLLECTION_NAME):
    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="person_id", datatype=DataType.VARCHAR, max_length=100)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)
    
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})
    client.create_collection(collection_name=COLLECTION_NAME, schema=schema)
    client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
    print(f"✅ Milvus collection '{COLLECTION_NAME}' ready.")

# --- Collection 2: watchlist_faces (Identity Search) ---
WATCHLIST_COLLECTION = "watchlist_faces"
if not client.has_collection(collection_name=WATCHLIST_COLLECTION):
    wl_schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=False)
    wl_schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    wl_schema.add_field(field_name="watchlist_id", datatype=DataType.VARCHAR, max_length=100)
    wl_schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=512)
    
    wl_index = client.prepare_index_params()
    wl_index.add_index(field_name="embedding", metric_type="COSINE", index_type="IVF_FLAT", params={"nlist": 128})
    client.create_collection(collection_name=WATCHLIST_COLLECTION, schema=wl_schema)
    client.create_index(collection_name=WATCHLIST_COLLECTION, index_params=wl_index)
    print(f"✅ Milvus collection '{WATCHLIST_COLLECTION}' ready.")

print("\n🚀 Database Infrastructure Fully Initialized!")