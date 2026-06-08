class JobRepository:
    def __init__(self, conn):
        self.conn = conn
        
    def create_job(self, session_id: str, camera_id: str, status: str = 'IN_PROGRESS'):
        with self.conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO historical_jobs (session_id, camera_id, status)
                VALUES (%s, %s, %s)
            """, (session_id, camera_id, status))
            
    def update_job_status(self, session_id: str, status: str):
        with self.conn.cursor() as cursor:
            cursor.execute("""
                UPDATE historical_jobs 
                SET status = %s 
                WHERE session_id = %s
            """, (status, session_id))
