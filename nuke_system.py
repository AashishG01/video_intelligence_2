#this is to delete the whole data 

import os
import shutil
import redis
import psycopg2
from pymilvus import MilvusClient

import sys
from backend_api.config import settings

print("⚠️  INITIATING C.O.R.E. SYSTEM FACTORY RESET ⚠️\n")

# ==========================================
# 1. NUKE REDIS (Queues & Locks)
# ==========================================
try:
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=0)
    r.flushdb()
    print("✅ REDIS: Wiped all queues, locks, and cache.")
except Exception as e:
    print(f"❌ REDIS ERROR: {e}")

# ==========================================
# 2. NUKE MILVUS (Vector Embeddings)
# ==========================================
try:
    milvus = MilvusClient(uri=settings.milvus_uri)
    for collection in ["face_embeddings", "watchlist_faces"]:
        if milvus.has_collection(collection):
            milvus.drop_collection(collection)
            print(f"✅ MILVUS: Dropped collection '{collection}'.")
except Exception as e:
    print(f"❌ MILVUS ERROR: {e}")

# ==========================================
# 3. NUKE POSTGRESQL (Operational Data)
# ==========================================
try:
    conn = psycopg2.connect(
        dbname=settings.postgres_db, 
        user=settings.postgres_user, 
        password=settings.postgres_password, 
        host=settings.postgres_host, 
        port=settings.postgres_port
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Cascade clears subjects, watchlist_members, sightings, and cameras.
    # Note: We are explicitly NOT truncating 'users' (so you can still log in) 
    # and 'system_alert_settings' (keeps your slider/audio preferences).
    cursor.execute("TRUNCATE TABLE subjects, sightings, cameras CASCADE;")
    print("✅ POSTGRESQL: Wiped sightings, cameras, subjects, and relations.")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ POSTGRESQL ERROR: {e}")

# ==========================================
# 4. NUKE PHYSICAL IMAGES (Hard Drive)
# ==========================================
try:
    save_folder = "captured_faces"
    if os.path.exists(save_folder):
        shutil.rmtree(save_folder)
    
    # Recreate empty directory structure for FastAPI to mount safely
    os.makedirs(os.path.join(save_folder, "watchlist"), exist_ok=True)
    os.makedirs(os.path.join(save_folder, "sightings"), exist_ok=True)
    print("✅ FILE SYSTEM: Wiped all saved face captures and recreated folders.")
except Exception as e:
    print(f"❌ FILE SYSTEM ERROR: {e}")

print("\n🚀 RESET COMPLETE. Restart your FastAPI backend now.")