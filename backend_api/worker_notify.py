import os
import json
import smtplib
import asyncio
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

from loguru import logger
import redis.asyncio as redis_async
import redis as redis_sync
from twilio.rest import Client

from config import settings

logger.add("logs/worker_notify.log", rotation="10 MB")

# ─────────────────────────────────────────
# CONFIGURATION — Loaded from config.py
# ─────────────────────────────────────────
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = settings.smtp_sender_email
SENDER_PASSWORD = settings.smtp_app_password

# Initialize Sync Redis for Cooldowns (simpler for setex)
r_sync = redis_sync.Redis(host=settings.redis_host, port=settings.redis_port, db=0, decode_responses=True)

# Initialize Twilio Client
twilio_client = None
if settings.twilio_account_sid and settings.twilio_auth_token:
    try:
        twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        logger.info("📱 Twilio Client Initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Twilio client: {e}")
else:
    logger.warning("Twilio credentials not found. SMS notifications are disabled.")

# ── Fail fast: refuse to start if SMTP credentials are missing ──
if not SENDER_EMAIL or not SENDER_PASSWORD:
    logger.warning("SMTP credentials not set in .env! Email notifications are disabled.")

EMAIL_COOLDOWN_SEC = 300  # 5 minutes
SMS_COOLDOWN_SEC = 300    # 5 minutes

# ─────────────────────────────────────────
# 1. Email Sending Engine (Synchronous in background thread)
# ─────────────────────────────────────────
def send_threat_email(alert_data, recipient_emails):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return
        
    suspect_name = alert_data.get('full_name', 'Unknown Target')
    risk_level = alert_data.get('risk_level', 'UNKNOWN')
    confidence = float(alert_data.get('confidence', 0)) * 100
    cam_id = alert_data.get('camera_id', 'Unknown Camera')
    timestamp = time.ctime(alert_data.get('timestamp', time.time()))

    live_image_url = alert_data.get('live_image')
    reference_image_url = alert_data.get('reference_image')
    
    live_image_path = live_image_url.replace("/images/", "captured_faces/") if live_image_url else None
    reference_image_path = reference_image_url.replace("/images/", "captured_faces/") if reference_image_url else None

    subject = f"🚨 C.O.R.E. ALERT: Level {risk_level} Threat Detected - {suspect_name}"

    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #020617; color: #f8fafc; padding: 20px;">
            <div style="max-width: 600px; margin: auto; border: 2px solid #ef4444; border-radius: 12px; background-color: #0f172a; overflow: hidden;">
                <div style="background-color: #ef4444; padding: 15px; text-align: center;">
                    <h2 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: 2px; text-transform: uppercase;">Critical Watchlist Match</h2>
                    <p style="color: #fca5a5; margin: 5px 0 0 0; font-size: 12px; letter-spacing: 1px;">PROTOCOL OVERRIDE: IMMEDIATE ACTION REQUIRED</p>
                </div>
                <div style="padding: 25px;">
                    <h3 style="color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Identified Target</h3>
                    <p style="font-size: 32px; font-weight: bold; margin: 0 0 15px 0; color: #ffffff;">{suspect_name}</p>
                    <span style="background-color: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #ef4444; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; text-transform: uppercase;">
                        Risk Level: {risk_level}
                    </span>
                    <hr style="border: 0; border-top: 1px solid #1e293b; margin: 25px 0;">
                    
                    <table style="width: 100%; border-collapse: separate; border-spacing: 10px 0;">
                        <tr>
                            <td style="width: 50%; text-align: center; background-color: #1e293b; padding: 10px; border-radius: 8px;">
                                <span style="color: #94a3b8; font-size: 12px; text-transform: uppercase; display: block; margin-bottom: 8px;">Live Capture</span>
                                <img src="cid:live_image" style="width: 100%; max-height: 200px; object-fit: contain; border-radius: 4px; border: 1px solid #334155;" alt="Live Capture">
                            </td>
                            <td style="width: 50%; text-align: center; background-color: #1e293b; padding: 10px; border-radius: 8px;">
                                <span style="color: #94a3b8; font-size: 12px; text-transform: uppercase; display: block; margin-bottom: 8px;">Database Profile</span>
                                <img src="cid:ref_image" style="width: 100%; max-height: 200px; object-fit: contain; border-radius: 4px; border: 1px solid #334155;" alt="Database Profile">
                            </td>
                        </tr>
                    </table>
                    <br>

                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 10px 0;">
                                <span style="color: #94a3b8; font-size: 12px; text-transform: uppercase;">Location Feed</span><br>
                                <strong style="font-size: 16px; color: #60a5fa;">{cam_id}</strong>
                            </td>
                            <td style="padding: 10px 0;">
                                <span style="color: #94a3b8; font-size: 12px; text-transform: uppercase;">AI Confidence</span><br>
                                <strong style="font-size: 16px; color: #f59e0b;">{confidence:.2f}% Match</strong>
                            </td>
                        </tr>
                        <tr>
                            <td colspan="2" style="padding: 10px 0;">
                                <span style="color: #94a3b8; font-size: 12px; text-transform: uppercase;">Timestamp</span><br>
                                <strong style="font-size: 14px;">{timestamp}</strong>
                            </td>
                        </tr>
                    </table>
                </div>
            </div>
        </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg['Subject'] = subject
    msg['From'] = f"CORE Command <{SENDER_EMAIL}>"
    msg['To'] = ", ".join(recipient_emails)

    part = MIMEText(html_body, "html")
    msg.attach(part)

    # Attach Live Image
    if live_image_path and os.path.exists(live_image_path):
        try:
            with open(live_image_path, "rb") as f:
                img_live = MIMEImage(f.read())
            img_live.add_header('Content-ID', '<live_image>')
            img_live.add_header('Content-Disposition', 'inline')
            msg.attach(img_live)
        except Exception as e:
            logger.error(f"Failed to attach live image: {e}")

    # Attach Reference Image
    if reference_image_path and os.path.exists(reference_image_path):
        try:
            with open(reference_image_path, "rb") as f:
                img_ref = MIMEImage(f.read())
            img_ref.add_header('Content-ID', '<ref_image>')
            img_ref.add_header('Content-Disposition', 'inline')
            msg.attach(img_ref)
        except Exception as e:
            logger.error(f"Failed to attach reference image: {e}")

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_emails, msg.as_string())
        server.quit()
        logger.info(f"✅ Threat intel (Email) dispatched to: {recipient_emails}")
    except Exception as e:
        logger.error(f"❌ SMTP Escalation Failed: {e}")

# ─────────────────────────────────────────
# 2. SMS Sending Engine (Asynchronous)
# ─────────────────────────────────────────
async def send_threat_sms(alert_data: dict, phone_numbers: list):
    if not twilio_client or not settings.twilio_phone_number:
        return

    suspect_name = alert_data.get('full_name', 'Unknown Target')
    risk_level = alert_data.get('risk_level', 'UNKNOWN')
    cam_id = alert_data.get('camera_id', 'Unknown Camera')
    timestamp_readable = time.strftime('%H:%M:%S', time.localtime(alert_data.get('timestamp', time.time())))

    # Strict 160-char formatting to prevent double billing
    message_body = f"[CORE] {risk_level} ALERT: {suspect_name} on {cam_id} at {timestamp_readable}"
    message_body = message_body[:160] 

    for number in phone_numbers:
        # E.164 Normalization (Default +91 for India)
        clean_num = re.sub(r'\D', '', number)
        if len(clean_num) == 10:
            clean_num = f"+91{clean_num}"
        elif len(clean_num) > 10 and not clean_num.startswith('+'):
            clean_num = f"+{clean_num}"
            
        try:
            # Async Execution to protect the worker thread
            await twilio_client.messages.create_async(
                body=message_body,
                from_=settings.twilio_phone_number,
                to=clean_num
            )
            logger.info(f"✅ Threat intel (SMS) dispatched to: {clean_num}")
        except Exception as e:
            logger.error(f"❌ Failed to send SMS to {clean_num}: {e}")

# ─────────────────────────────────────────
# 3. Main Listening Loop (Asyncio)
# ─────────────────────────────────────────
async def notification_loop():
    logger.info("📧 Notification Microservice Online. Awaiting Threat Intel...")
    
    # We use redis.asyncio to prevent the pubsub loop from blocking
    r_async = redis_async.Redis(host=settings.redis_host, port=settings.redis_port, db=0, decode_responses=True)
    pubsub = r_async.pubsub()
    await pubsub.subscribe('live_face_alerts')

    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    alert = json.loads(message['data'])

                    # RULE 1: Only escalate Watchlist Matches
                    if alert.get('status') == 'WATCHLIST_MATCH':
                        if not alert.get('is_armed', True):
                            logger.info(f"🔕 System is DISARMED. Skipping alerts for {alert.get('full_name', 'Unknown')}.")
                            continue

                        person_id = alert.get('person_id')
                        
                        # --- EMAIL PROCESSING ---
                        email_lock_key = f"email_sent_{person_id}"
                        if not r_sync.exists(email_lock_key):
                            raw_emails = r_sync.get("GLOBAL_NOTIFY_EMAILS")
                            if raw_emails:
                                target_emails = json.loads(raw_emails)
                                if len(target_emails) > 0:
                                    logger.info(f"🚨 Escalating (Email) to {len(target_emails)} operators...")
                                    # Execute synchronous SMTP blocking in a separate background thread
                                    asyncio.create_task(asyncio.to_thread(send_threat_email, alert, target_emails))
                                    r_sync.setex(email_lock_key, EMAIL_COOLDOWN_SEC, "1")
                                    
                        # --- SMS PROCESSING ---
                        sms_lock_key = f"sms_sent_{person_id}"
                        if not r_sync.exists(sms_lock_key):
                            raw_phones = r_sync.get("GLOBAL_NOTIFY_PHONES")
                            if raw_phones:
                                target_phones = json.loads(raw_phones)
                                if len(target_phones) > 0:
                                    logger.info(f"🚨 Escalating (SMS) to {len(target_phones)} devices...")
                                    # Execute Twilio async
                                    asyncio.create_task(send_threat_sms(alert, target_phones))
                                    r_sync.setex(sms_lock_key, SMS_COOLDOWN_SEC, "1")

                except Exception as e:
                    logger.error(f"⚠️ Notification Message Parsing Error: {e}")
                    
    except asyncio.CancelledError:
        logger.info("\n🛑 Notification Microservice stopped.")
    except Exception as e:
        logger.exception(f"⚠️ Redis Connection Lost in Async Loop: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(notification_loop())
    except KeyboardInterrupt:
        logger.info("\n🛑 Notification Microservice stopped by user.")