import os
import secrets
from dotenv import load_dotenv
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# ─────────────────────────────────────────
# BULLETPROOF .ENV LOADING
# This file loads its own .env FIRST, before reading any variables.
# This eliminates the Python Import Order Race Condition permanently.
# No matter which file imports auth.py first, the key will always exist.
# ─────────────────────────────────────────
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# ─────────────────────────────────────────
# JWT SECRET KEY — CRASH-PROOF LOADING
# Priority Order:
#   1. Read from .env file (production)
#   2. Read from system environment variable
#   3. Auto-generate a temporary dev key (with loud warning)
# The server will NEVER crash due to a missing key.
# ─────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

if not SECRET_KEY:
    # Generate a temporary key so the server can still boot
    SECRET_KEY = secrets.token_hex(32)
    os.environ["JWT_SECRET_KEY"] = SECRET_KEY
    print("\n" + "=" * 60)
    print("⚠️  WARNING: JWT_SECRET_KEY not found in .env file!")
    print("   A temporary key has been auto-generated for this session.")
    print("   ⚡ All existing login tokens will be INVALIDATED on restart.")
    print("   To fix permanently, add this to your .env file:")
    print(f'   JWT_SECRET_KEY={SECRET_KEY}')
    print("=" * 60 + "\n")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 Hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This tells FastAPI where the frontend will send login requests
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- THE MIDDLEWARE BOUNCERS ---

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
        return {"username": username, "role": role}
    except JWTError:
        raise credentials_exception

async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RESTRICTED: Administrator clearance required."
        )
    return current_user