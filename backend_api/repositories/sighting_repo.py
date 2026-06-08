from psycopg2.extras import RealDictCursor

class SightingRepository:
    def __init__(self, conn):
        self.conn = conn
        
    def get_timeline_by_person_id(self, person_id: str):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT camera_id, timestamp, image_path 
                FROM sightings 
                WHERE person_id = %s 
                ORDER BY timestamp ASC
            """, (person_id,))
            return cursor.fetchall()
