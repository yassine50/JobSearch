import os
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from . import models

def _load_secret_key() -> str:
    """
    JWT signing key. Uses JWT_SECRET_KEY from the environment if set; otherwise
    generates a strong random key ONCE and persists it to web/backend/.jwt_secret
    (git-ignored) so every worker and restart shares the same key.
    Never falls back to a public, hardcoded default.
    """
    env_key = (os.getenv("JWT_SECRET_KEY") or "").strip()
    if env_key:
        return env_key
    import secrets as _secrets
    import time as _time
    path = os.path.join(os.path.dirname(__file__), ".jwt_secret")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(_secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    for _ in range(50):  # another worker may be mid-write
        try:
            with open(path, "r") as fh:
                key = fh.read().strip()
            if key:
                return key
        except OSError:
            pass
        _time.sleep(0.05)
    raise RuntimeError("Could not load or create JWT secret key")


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days persistent login

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email or not email.strip():
            raise exc
    except JWTError:
        raise exc
    user = db.query(models.User).filter(models.User.email == email.strip()).first()
    if user is None or not user.email or not user.email.strip():
        raise exc
    return user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email or not email.strip():
            return None
        user = db.query(models.User).filter(models.User.email == email.strip()).first()
        if user is None or not user.email or not user.email.strip():
            return None
        return user
    except JWTError:
        return None

