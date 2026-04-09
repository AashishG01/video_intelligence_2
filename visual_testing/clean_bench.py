from pymilvus import MilvusClient
import redis

# 1. Milvus Cleanup (Only Benchmark Collection)
milvus_client = MilvusClient(uri="http://localhost:19530")
COLLECTION_NAME = "bench_embeddings"

if milvus_client.has_collection(COLLECTION_NAME):
    milvus_client.drop_collection(COLLECTION_NAME)
    print(f"✅ Dropped Milvus collection: {COLLECTION_NAME}")

# 2. Redis Cleanup (Only Benchmark Queues)
r = redis.Redis(host='localhost', port=6379, db=0)
r.delete("bench_raw_frames", "bench_face_ready")
print("✅ Deleted benchmark Redis queues.")

print("\n🚀 System is now fresh for a clean benchmark start!")