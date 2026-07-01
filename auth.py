import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import models

# I set this as an environment variable in Azure App Service.
# The fallback here is only used during local development.
JWT_SECRET = os.environ.get("FORGE_JWT_SECRET", "dev-only-secret-change-me-32-bytes-minimum")
JWT_ALGORITHM = "HS256"
# I set tokens to expire after one week so users stay logged in between sessions.
JWT_EXPIRES_MINUTES = 60 * 24 * 7

# This reads the Authorization: Bearer <token> header from incoming requests.
# auto_error=False means it returns None instead of a 401 when there's no token --
# I need this for endpoints that work for both logged-in and anonymous users.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt generates a salt automatically and embeds it in the hash,
    # so I don't need to store the salt separately.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    # bcrypt extracts the salt from the stored hash and re-hashes the input to compare.
    # The plain-text password is never stored anywhere.
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: str, role: str) -> str:
    # I embed the user's ID and role directly in the token so protected endpoints
    # don't need a database lookup just to know who is calling or if they're an admin.
    # "sub" is the standard JWT claim for the user identifier.
    # "exp" is checked automatically by PyJWT when the token is decoded.
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that I attach to every protected endpoint.
    It decodes the JWT, looks up the user in Cosmos, and returns their record.
    Returns 401 if the token is missing, invalid, or expired.
    Returns 403 if an admin has banned the account.
    """
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

    # I still look up the user in the database here rather than trusting the token alone,
    # because the role in the token could be stale if an admin changed it after login.
    user = models.get_user(user_id)
    if user is None:
        raise credentials_error
    if user["is_banned"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is banned")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    # I chain this on top of get_current_user for admin-only endpoints.
    # FastAPI runs get_current_user first, then this check.
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> dict | None:
    # I use this for endpoints that behave differently depending on whether
    # the user is logged in -- like the project detail page showing the apply
    # form only if you have an account. Returns None for anonymous visitors.
    if not token:
        return None
    try:
        return get_current_user(token)
    except HTTPException:
        return None
