from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "admin"
    postgres_password: str = "password"
    postgres_db: str = "surveillance"
    
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    milvus_uri: str = "http://localhost:19530"
    
    system_timezone: str = "Asia/Kolkata" # NVR Deployment timezone

    jwt_secret_key: str = ""
    
    # Notifications
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    
    smtp_sender_email: str = ""
    smtp_app_password: str = ""

    # Look for .env file in the parent directory
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
