from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models
from ..database import get_db
from ..auth import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "seeker"

class LoginRequest(BaseModel):
    email: str
    password: str

def _user_dict(u):
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}

@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(name=req.name, email=req.email,
                       hashed_password=get_password_hash(req.password), role=req.role)
    db.add(user); db.commit(); db.refresh(user)
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
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
