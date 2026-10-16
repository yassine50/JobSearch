import json
import os
import secrets
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models
from ..database import get_db
from ..auth import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_GOOGLE_CLIENT_ID = "351639376298-otgv89j6pf4mbtmpgibjg0l9l7bhllbt.apps.googleusercontent.com"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "scraper_config.json")


def _get_google_client_id() -> str:
    env_cid = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    if env_cid:
        return env_cid
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg_cid = str(json.load(f).get("google_client_id", "") or "").strip()
            if cfg_cid:
                return cfg_cid
    except Exception:
        pass
    return DEFAULT_GOOGLE_CLIENT_ID


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "seeker"

class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleAuthRequest(BaseModel):
    access_token: Optional[str] = None
    credential: Optional[str] = None
    role: str = "seeker"

def _user_dict(u):
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


@router.get("/google-config")
def google_config():
    cid = _get_google_client_id()
    return {"client_id": cid, "enabled": bool(cid)}


@router.post("/google")
def google_auth(req: GoogleAuthRequest, db: Session = Depends(get_db)):
    info = {}
    if req.access_token and req.access_token.strip():
        r = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {req.access_token.strip()}"},
            timeout=10,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired Google access token")
        info = r.json()
    elif req.credential and req.credential.strip():
        r = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": req.credential.strip()},
            timeout=10,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired Google ID token")
        info = r.json()
    else:
        raise HTTPException(status_code=400, detail="Missing Google authentication token")

    email = (info.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Google account did not provide a valid email address")

    raw_name = (info.get("name") or info.get("given_name") or "").strip()
    if not raw_name or len(raw_name) < 2:
        raw_name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

    user = db.query(models.User).filter(models.User.email == email).first()
    is_new_user = False
    if not user:
        is_new_user = True
        role = req.role if req.role in ("seeker", "recruiter", "both") else "seeker"
        user = models.User(
            name=raw_name,
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(24)),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.name or not user.name.strip():
        user.name = raw_name
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
        "user": _user_dict(user),
    }


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    name = (req.name or "").strip()
    email = (req.email or "").strip().lower()
    password = req.password or ""

    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required (at least 2 characters)")
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Clean up any legacy blank/anonymous user records if present
    db.query(models.User).filter((models.User.email == "") | (models.User.email.is_(None))).delete(synchronize_session=False)

    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(name=name, email=email,
                       hashed_password=get_password_hash(password), role=req.role)
    db.add(user); db.commit(); db.refresh(user)
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = (req.email or "").strip().lower()
    password = req.password or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}

@router.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {**_user_dict(current_user), "created_at": str(current_user.created_at)}

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None

@router.patch("/profile")
def update_profile(req: ProfileUpdate,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    if req.name:
        current_user.name = req.name.strip()
    if req.password:
        if len(req.password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        current_user.hashed_password = get_password_hash(req.password)
    db.commit()
    return {"message": "Profile updated", "name": current_user.name, "email": current_user.email}
