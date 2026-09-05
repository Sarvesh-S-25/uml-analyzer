"""Authentication helpers.

Two substantive changes from the previous version:

1. The signing key comes from configuration, never from a literal in source.
2. Token validation re-checks that the subject still exists in the database.
   Previously a deleted user's unexpired token stayed valid on every protected
   route, because only the signature was verified.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models.user_model as user_model
from config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, MAX_ANALYSES_PER_HOUR, SECRET_KEY
from database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt silently truncates beyond 72 bytes; reject rather than accept a
    # password whose tail was never checked.
    if len(plain_password.encode("utf-8")) > 72:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be at most 72 bytes.")
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update(
        {
            "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "iat": datetime.now(timezone.utc),
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> user_model.DBUser:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise CREDENTIALS_EXCEPTION

    username = payload.get("sub")
    if not username:
        raise CREDENTIALS_EXCEPTION

    user = (
        db.query(user_model.DBUser)
        .filter(user_model.DBUser.username == username)
        .first()
    )
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user


def get_current_username(user: user_model.DBUser = Depends(get_current_user)) -> str:
    return user.username


# --- Rate limiting -----------------------------------------------------------
# Every analysis can spend money at a third-party API, so an authenticated user
# must not be able to trigger an unbounded number of them.

_BUCKETS: Dict[str, Tuple[float, int]] = {}
_WINDOW_SECONDS = 3600.0


def rate_limit(user: user_model.DBUser = Depends(get_current_user)) -> user_model.DBUser:
    now = time.monotonic()
    window_start, count = _BUCKETS.get(user.username, (now, 0))

    if now - window_start > _WINDOW_SECONDS:
        window_start, count = now, 0

    if count >= MAX_ANALYSES_PER_HOUR:
        retry_after = int(_WINDOW_SECONDS - (now - window_start))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Analysis rate limit reached ({MAX_ANALYSES_PER_HOUR}/hour).",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    _BUCKETS[user.username] = (window_start, count + 1)
    return user
