import redis
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# ─────────────────────────────────────────
# CONFIGURATION — Replace with your credentials
# ─────────────────────────────────────────
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "driveblade7@gmail.com"      # 👈 Apna Gmail daalo
SENDER_PASSWORD = "rbol hixn fntu rrpy"    # 👈 Apna 16-digit App Password daalo (bina space ke)

EMAIL_COOLDOWN_SEC = 300  # Ek hi bande ka email dubara 5 minute (300 sec) tak nahi jayega

# ─────────────────────────────────────────
# 1. Connections
# ─────────────────────────────────────────
print("⏳ Connecting to Redis...")
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
pubsub = r.pubsub()

# Hum wahi channel sunenge jo React UI sunta hai
pubsub.subscribe('live_face_alerts')
print("📧 Notification Microservice Online. Awaiting Threat Intel...")

# ─────────────────────────────────────────
# 2. Email Sending Engine (Tactical HTML)
# ─────────────────────────────────────────
def send_threat_email(alert_data, recipient_emails):
    suspect_name = alert_data.get('full_name', 'Unknown Target')
    risk_level = alert_data.get('risk_level', 'UNKNOWN')
    confidence = float(alert_data.get('confidence', 0)) * 100
    cam_id = alert_data.get('camera_id', 'Unknown Camera')
    timestamp = time.ctime(alert_data.get('timestamp', time.time()))

    subject = f"🚨 C.O.R.E. ALERT: Level {risk_level} Threat Detected - {suspect_name}"

    # Sleek, dark-mode tactical email template
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #020617; color: #f8fafc; padding: 20px;">
            <div style="max-w: 600px; margin: auto; border: 2px solid #ef4444; border-radius: 12px; background-color: #0f172a; overflow: hidden;">
                
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

                <div style="background-color: #020617; padding: 15px; text-align: center; border-top: 1px solid #1e293b;">
                    <p style="font-size: 11px; color: #64748b; margin: 0;">This is an automated dispatch from the C.O.R.E. Surveillance Network. Do not reply.</p>
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

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_emails, msg.as_string())
        server.quit()
        print(f"✅ Threat intel dispatched to: {recipient_emails}")
    except Exception as e:
        print(f"❌ SMTP Escalation Failed: {e}")

# ─────────────────────────────────────────
# 3. Main Listening Loop
# ─────────────────────────────────────────
for message in pubsub.listen():
    if message['type'] == 'message':
        try:
            alert = json.loads(message['data'])

            # RULE 1: We only escalate if it's a Watchlist Match. We don't spam for unknown people.
            if alert.get('status') == 'WATCHLIST_MATCH':
                person_id = alert.get('person_id')

                # RULE 2: Anti-Spam Check (Specific to Emails)
                # Ensure we don't send 50 emails if the suspect stands in front of the camera for 2 minutes
                email_lock_key = f"email_sent_{person_id}"
                if r.exists(email_lock_key):
                    print(f"🔕 Email for {person_id} is on cooldown. Skipping.")
                    continue

                # RULE 3: Fetch the dynamically assigned emails from Redis
                raw_emails = r.get("GLOBAL_NOTIFY_EMAILS")
                if raw_emails:
                    target_emails = json.loads(raw_emails)
                    if len(target_emails) > 0:
                        print(f"🚨 ALERT TRIGGERED! Escalating to {len(target_emails)} operators...")
                        
                        # Fire the email
                        send_threat_email(alert, target_emails)
                        
                        # Lock the email system for this specific person for 5 minutes
                        r.setex(email_lock_key, EMAIL_COOLDOWN_SEC, "1")
                    else:
                        print("⚠️ Threat detected, but NO EMAILS configured in C.O.R.E UI.")
                else:
                    print("⚠️ Threat detected, but GLOBAL_NOTIFY_EMAILS key is missing in Redis.")

        except Exception as e:
            print(f"⚠️ Notification Worker Error: {e}")