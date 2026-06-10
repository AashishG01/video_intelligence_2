import cv2
import time
import redis
import json
import base64
import os
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.parse
import sys
from loguru import logger
from datetime import datetime

logger.add("logs/producer_historic.log", rotation="10 MB")

# Import centralized configuration
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend_api'))
from config import settings

# Force TCP for RTSP to prevent UDP packet loss
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Connect to local Redis
r = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=0)

def get_nvr_config(camera_id):
    """Fetch NVR parameters for a camera from the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            host=settings.postgres_host,
            port=settings.postgres_port
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT nvr_brand, nvr_ip, nvr_user, nvr_pass, nvr_channel FROM cameras WHERE camera_id = %s", (camera_id,))
        cam = cursor.fetchone()
        cursor.close()
        conn.close()
        return cam
    except Exception as e:
        logger.error(f"Failed to fetch NVR config from DB for camera {camera_id}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Time Machine: NVR Historical Extractor")
    parser.add_argument("--camera_id", type=str, required=True, help="Camera ID in DB")
    parser.add_argument("--start", type=int, required=True, help="Start Unix Timestamp")
    parser.add_argument("--end", type=int, required=True, help="End Unix Timestamp")
    parser.add_argument("--session", type=str, required=True, help="Unique Session ID for queue isolation")
    args = parser.parse_args()
    
    # Bind context to all logs in this session
    log = logger.bind(session_id=args.session, camera_id=args.camera_id)

    log.info(f"TIME MACHINE INITIALIZED. Time Window: {args.start} -> {args.end}")

    cam = get_nvr_config(args.camera_id)
    if not cam:
        log.error("Camera not found or has no NVR configuration.")
        return

    nvr_brand = cam.get('nvr_brand', '').lower()
    
    # 1. Build Replay URL
    encoded_pass = urllib.parse.quote(cam.get('nvr_pass') or "")
    nvr_ip = cam.get('nvr_ip')
    nvr_user = cam.get('nvr_user')
    nvr_channel = cam.get('nvr_channel', 1)

    # Convert timestamps to local datetime objects to respect NVR local timezone
    dt_start = datetime.fromtimestamp(args.start)
    dt_end = datetime.fromtimestamp(args.end)

    if nvr_brand == 'uniview':
        replay_url = f"rtsp://{nvr_user}:{encoded_pass}@{nvr_ip}:554/c{nvr_channel}/b{args.start}/e{args.end}/replay"
    elif nvr_brand == 'hikvision':
        hik_start = dt_start.strftime("%Y%m%dT%H%M%SZ")
        hik_end = dt_end.strftime("%Y%m%dT%H%M%SZ")
        replay_url = f"rtsp://{nvr_user}:{encoded_pass}@{nvr_ip}:554/Streaming/tracks/{nvr_channel}01/?starttime={hik_start}&endtime={hik_end}"
    elif nvr_brand == 'cpplus' or nvr_brand == 'dahua':
        cp_start = dt_start.strftime("%Y_%m_%d_%H_%M_%S")
        cp_end = dt_end.strftime("%Y_%m_%d_%H_%M_%S")
        replay_url = f"rtsp://{nvr_user}:{encoded_pass}@{nvr_ip}:554/cam/playback?channel={nvr_channel}&starttime={cp_start}&endtime={cp_end}"
    else:
        log.error(f"Unsupported NVR brand: {nvr_brand}")
        return
    
    queue_name = f"historic_frames_queue:{args.session}"
    
    log.info("Connecting to NVR stream...")
    cap = None
    try:
        cap = cv2.VideoCapture(replay_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            log.error("Failed to connect to NVR replay stream.")
            return

        original_fps = cap.get(cv2.CAP_PROP_FPS)
        if not original_fps or original_fps <= 0:
            original_fps = 25.0 # Fallback to Uniview default
            
        log.info(f"Stream Connected! Original FPS: {original_fps}")

        # Aggressive Frame Skipping (Targeting ~3 FPS for AI)
        # If original is 25 fps, we skip ~8 frames for every 1 processed.
        target_fps = 3.0
        skip_interval = max(1, int(original_fps / target_fps))
        
        frame_count = 0
        processed_count = 0

        while True:
            # --- Redis OOM Protection (Backpressure) ---
            while r.llen(queue_name) > 500:
                log.warning("Queue full (500). Pausing extraction to let AI catch up...")
                time.sleep(1.0)

            ret, frame = cap.read()
            if not ret:
                log.info("End of File (EOF) reached.")
                break

            frame_count += 1
            
            # Frame Skipping
            if frame_count % skip_interval != 0:
                continue

            # --- True Forensic Timestamp Calculation ---
            # The true time of this frame is exactly how many seconds into the video it is.
            seconds_elapsed = frame_count / original_fps
            true_timestamp = args.start + seconds_elapsed

            # Optimization: Resize slightly to speed up AI & save Redis RAM
            ai_frame = cv2.resize(frame, (1280, 720))
            _, ai_buffer = cv2.imencode('.jpg', ai_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            ai_base64 = base64.b64encode(ai_buffer).decode('utf-8')
            
            payload = {
                "session_id": args.session,
                "camera_id": args.camera_id,
                "timestamp": true_timestamp, # TRUST THIS TIME!
                "frame_data": ai_base64
            }
            
            # Push to isolated session queue
            r.lpush(queue_name, json.dumps(payload))
            processed_count += 1
            
            if processed_count % 10 == 0:
                pass # Removed noisy print

    except Exception as e:
        log.exception(f"Extraction aborted due to error: {e}")
    finally:
        # 🚨 HIGH FIX 1: Guaranteed Hardware Socket Release
        if cap is not None:
            cap.release()
            
        # 🚨 HIGH FIX 2: Guaranteed State Machine Resolution (The Orphan Fix)
        # Even if the script crashes, it sends the EOF pill so the AI worker knows to close the DB row.
        log.info("Injecting EOF Poison Pill into queue...")
        eof_payload = {"status": "EOF", "camera_id": args.camera_id, "session_id": args.session}
        r.lpush(queue_name, json.dumps(eof_payload))
        
        log.info("Time Machine Extraction Complete and Safely Shut Down.")

if __name__ == "__main__":
    main()
