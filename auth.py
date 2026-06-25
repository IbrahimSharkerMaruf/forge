import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import models

# In production (Azure), set FORGE_JWT_SECRET as an App Service config value.
JWT_SECRET = os.environ.get("FORGE_JWT_SECRET", "dev-only-secret-change-me-32-bytes-minimum")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 60 * 24 * 7  # 1 week

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
    )
    if not token:
        raise credentials_error
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload["sub"]
    except (jwt.PyJWTError, KeyError):
        raise credentials_error

    user = models.get_user(user_id)
    if user is None:
        raise credentials_error
    if user["is_banned"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is banned")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> dict | None:
    if not token:
        return None
    try:
        return get_current_user(token)
    except HTTPException:
        return None
