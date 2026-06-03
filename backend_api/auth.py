import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Load .env file from project root (using absolute path to be bulletproof)
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# ─────────────────────────────────────────
# JWT SECURITY CONFIGURATION
# SECRET_KEY must be set as an environment variable — never hardcode it.
# Generate a strong key with:  python -c "import secrets; print(secrets.token_hex(32))"
# Then set it before starting the API:
#   Linux/macOS : export JWT_SECRET_KEY="<your-generated-key>"
#   Windows CMD : set JWT_SECRET_KEY=<your-generated-key>
#   .env file   : JWT_SECRET_KEY=<your-generated-key>  (add .env to .gitignore)
# ─────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "\n❌  JWT_SECRET_KEY environment variable is not set!\n"
        "    The API server refuses to start without it — a missing key means\n"
        "    all authentication is broken or trivially bypassable.\n"
        "    Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "    Then export it:     export JWT_SECRET_KEY=<generated-value>\n"
        "    See notes.md § BUG-004 for full setup instructions."
    )

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