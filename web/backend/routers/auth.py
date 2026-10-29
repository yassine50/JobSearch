import json
import os
import re
import secrets
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models
from ..database import get_db
from ..auth import verify_password, get_password_hash, create_access_token, get_current_user, is_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_GOOGLE_CLIENT_ID = "351639376298-otgv89j6pf4mbtmpgibjg0l9l7bhllbt.apps.googleusercontent.com"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "scraper_config.json")


def _get_google_client_id() -> str:
    env_cid = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    if env_cid and not env_cid.startswith("503660329507-"):
        return env_cid
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg_cid = str(json.load(f).get("google_client_id", "") or "").strip()
            if cfg_cid and not cfg_cid.startswith("503660329507-"):
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
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_admin": is_admin(u),
    }


@router.get("/google-config")
def google_config():
    cid = _get_google_client_id()
    return {"client_id": cid, "enabled": bool(cid)}


@router.post("/google")
def google_auth(req: GoogleAuthRequest, db: Session = Depends(get_db)):
    info = {}
    client_id = _get_google_client_id()
    if req.access_token and req.access_token.strip():
        # Ensure the access token was issued to OUR OAuth client (prevents token-substitution logins)
        ti = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"access_token": req.access_token.strip()},
            timeout=10,
        )
        if ti.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired Google access token")
        aud = (ti.json().get("aud") or ti.json().get("azp") or "").strip()
        if client_id and aud != client_id:
            raise HTTPException(status_code=401, detail="Google token was not issued for CVtoMatch")
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
        if client_id and (info.get("aud") or "").strip() != client_id:
            raise HTTPException(status_code=401, detail="Google token was not issued for CVtoMatch")
    else:
        raise HTTPException(status_code=400, detail="Missing Google authentication token")

    email = (info.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Google account did not provide a valid email address")
    email_verified = info.get("email_verified")
    if email_verified not in (True, "true", "1", 1):
        raise HTTPException(status_code=401, detail="Google account email address is not verified")

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
    role = req.role if req.role in ("seeker", "recruiter", "both") else "seeker"  # never allow self-assigned "admin"
    user = models.User(name=name, email=email,
                       hashed_password=get_password_hash(password), role=role)
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
    if not user:
        # Never auto-create accounts on login: it allowed unverified account pre-hijacking.
        raise HTTPException(status_code=401, detail="No account found with this email. Please create an account first.")
    if not verify_password(password, user.hashed_password):
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


# ─── Forgot Password & Stateless 6-Digit Reset Code Flow ────────────────────

import hashlib
import hmac
import html as _html
import time as _time
from urllib.parse import quote
from ..auth import SECRET_KEY

_RESET_ATTEMPTS: dict = {}
_FORGOT_COOLDOWN: dict = {}


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


def _generate_reset_code(user: models.User, bucket: int) -> str:
    msg = f"cvtomatch-pwreset:{user.id}:{(user.email or '').lower()}:{user.hashed_password}:{bucket}".encode("utf-8")
    digest = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    num = int.from_bytes(digest[:4], "big") % 900000 + 100000
    return f"{num:06d}"


def _verify_reset_code(user: models.User, code: str) -> bool:
    clean_code = "".join((code or "").split())
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False
    now_bucket = int(_time.time() // 300)  # 5-minute buckets; check last 4 buckets (20 minutes validity)
    for offset in (0, 1, 2, 3):
        expected = _generate_reset_code(user, now_bucket - offset)
        if hmac.compare_digest(clean_code, expected):
            return True
    return False


def _build_password_reset_html(user_name: str, user_email: str, code: str, reset_url: str) -> str:
    first_name = _html.escape((user_name or "Explorer").split(" ")[0])
    safe_email = _html.escape(user_email)
    safe_code = _html.escape(code)
    safe_url = _html.escape(reset_url)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reset Your CVtoMatch Password</title>
</head>
<body style="margin:0;padding:0;background-color:#eaeff5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eaeff5;padding:32px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border:1px solid #cbd5e1;border-radius:24px;overflow:hidden;box-shadow:0 20px 50px rgba(15,23,42,0.10);">
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 100%);padding:28px 32px;text-align:center;">
              <div style="font-size:22px;font-weight:900;color:#ffffff;letter-spacing:-0.4px;">
                ⚡ CVto<span style="color:#60a5fa;">Match</span> AI
              </div>
              <div style="font-size:12px;color:#bfdbfe;margin-top:4px;font-weight:600;">
                Account Security &amp; Password Recovery
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <div style="font-size:18px;font-weight:800;color:#0f172a;margin-bottom:8px;">
                Hi {first_name},
              </div>
              <p style="font-size:14px;color:#334155;line-height:1.6;margin:0 0 20px;">
                We received a request to reset the password for your CVtoMatch account (<strong>{safe_email}</strong>). Enter this 6-digit verification code on the sign-in screen:
              </p>
              <div style="background-color:#f1f5f9;border:2px dashed #3b82f6;border-radius:16px;padding:20px;text-align:center;margin-bottom:22px;">
                <div style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1.5px;color:#64748b;margin-bottom:6px;">
                  Your 6-Digit Reset Code (Valid for 20 Minutes)
                </div>
                <div style="font-size:34px;font-weight:900;letter-spacing:8px;color:#1d4ed8;font-family:monospace;">
                  {safe_code}
                </div>
              </div>
              <div style="text-align:center;margin-bottom:22px;">
                <a href="{safe_url}" target="_blank" style="display:inline-block;background:linear-gradient(135deg,#2563eb 0%,#4f46e5 100%);background-color:#2563eb;color:#ffffff;text-decoration:none;font-size:14px;font-weight:800;padding:13px 28px;border-radius:12px;box-shadow:0 6px 16px rgba(37,99,235,0.28);">
                  🔓 Reset My Password in 1 Click →
                </a>
              </div>
              <p style="font-size:12px;color:#64748b;line-height:1.5;margin:0;">
                If you did not request a password reset, you can safely ignore this email — your password will remain unchanged.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#f8fafc;border-top:1px solid #e2e8f0;padding:16px 28px;text-align:center;font-size:11px;color:#64748b;">
              © 2026 CVtoMatch AI (<a href="https://www.cvtomatch.com" style="color:#2563eb;text-decoration:none;">www.cvtomatch.com</a>) · Official Security Notification
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    now_ts = _time.time()
    cd = _FORGOT_COOLDOWN.get(email)
    if cd:
        if now_ts - cd["last_ts"] < 60:
            raise HTTPException(
                status_code=429,
                detail="Please wait at least 60 seconds before requesting another password reset code.",
            )
        if now_ts - cd["window_ts"] < 900 and cd["count"] >= 4:
            raise HTTPException(
                status_code=429,
                detail="Too many password reset requests for this email. Please try again in 15 minutes.",
            )

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email address. Please check for typos or create a new account.",
        )

    if not cd or now_ts - cd["window_ts"] >= 900:
        _FORGOT_COOLDOWN[email] = {"window_ts": now_ts, "last_ts": now_ts, "count": 1}
    else:
        cd["last_ts"] = now_ts
        cd["count"] += 1

    now_bucket = int(_time.time() // 300)
    code = _generate_reset_code(user, now_bucket)
    base_url = (os.getenv("PUBLIC_APP_URL") or "https://www.cvtomatch.com").rstrip("/")
    reset_url = f"{base_url}/?reset_email={quote(user.email)}&reset_code={code}#auth-workbench"

    subject = f"🔐 {code} is your CVtoMatch Password Reset Code"
    plain_body = (
        f"Hi {user.name or 'Explorer'},\n\n"
        f"Your 6-digit CVtoMatch password reset code is: {code}\n"
        "This code is valid for 20 minutes.\n\n"
        f"Or click here to reset your password directly:\n{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email.\n"
        "— CVtoMatch AI Security (support@cvtomatch.com)"
    )
    html_body = _build_password_reset_html(
        user_name=user.name or "Explorer",
        user_email=user.email,
        code=code,
        reset_url=reset_url,
    )

    from ..auto_dispatcher import _dispatch_platform_digest_email
    sent = _dispatch_platform_digest_email(
        db=db,
        recipient_user=user,
        subject=subject,
        plain_body=plain_body,
        html_body=html_body,
        force_manual=True,
    )
    if not sent:
        err = getattr(_dispatch_platform_digest_email, "last_error", "") or "Email service unavailable"
        raise HTTPException(
            status_code=502,
            detail=f"Could not send reset email to {user.email}: {err}",
        )

    return {
        "message": f"We sent a 6-digit reset code to {user.email}. Check your inbox!",
        "email": user.email,
    }


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = (req.email or "").strip().lower()
    code = "".join((req.code or "").split())
    new_password = req.new_password or ""

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email address is required.")
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail="Please enter the 6-digit verification code from your email.")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    # Simple rate-limiting against brute-forcing a 6-digit code (max 8 failed attempts per 10 mins)
    now_ts = _time.time()
    rec = _RESET_ATTEMPTS.get(email)
    if rec and now_ts - rec["ts"] < 600 and rec["count"] >= 8:
        raise HTTPException(
            status_code=429,
            detail="Too many invalid code attempts. Please request a new reset code and try again in a few minutes.",
        )

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not _verify_reset_code(user, code):
        if not rec or now_ts - rec["ts"] >= 600:
            _RESET_ATTEMPTS[email] = {"count": 1, "ts": now_ts}
        else:
            rec["count"] += 1
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired 6-digit reset code. Please check your email or request a new code.",
        )

    _RESET_ATTEMPTS.pop(email, None)
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.email})
    return {
        "message": "Password reset successfully! You are now signed in.",
        "access_token": token,
        "token_type": "bearer",
        "user": _user_dict(user),
    }
