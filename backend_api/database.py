from psycopg2.pool import ThreadedConnectionPool
from config import settings
from loguru import logger

_PG_DSN = dict(
    dbname=settings.postgres_db,
    user=settings.postgres_user,
    password=settings.postgres_password,
    host=settings.postgres_host,
    port=settings.postgres_port,
)

logger.info("⏳ Initialising PostgreSQL connection pool (2–10 connections)...")
db_pool = ThreadedConnectionPool(minconn=2, maxconn=10, **_PG_DSN)
logger.info("✅ PostgreSQL pool ready.")

def get_db_connection():
    """FastAPI Dependency for Unit of Work transaction scoping."""
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)
