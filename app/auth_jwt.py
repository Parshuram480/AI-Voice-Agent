import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ai_voice_agent_super_secret_jwt_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 Days expiration

def create_access_token(client_id: int, email: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed HS256 JWT access token using python-jose."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": str(client_id),
        "client_id": client_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": expire,
    }

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates an incoming JWT token using python-jose."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Invalid or expired JWT token: {e}")
        return None

def verify_and_get_client_id(token_or_cookie: str) -> Optional[int]:
    """Decodes JWT token to extract client_id with fallback to numeric ID."""
    if not token_or_cookie:
        return None
        
    payload = decode_access_token(token_or_cookie)
    if payload and "client_id" in payload:
        return int(payload["client_id"])
        
    # Legacy numeric string fallback
    try:
        return int(token_or_cookie)
    except ValueError:
        return None
