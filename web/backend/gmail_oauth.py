"""
"Connect Gmail" — one-click Google sign-in that lets the app send applications from the
user's own Gmail via the Gmail API (scope: gmail.send only — we can never read their inbox).

Setup (once, by the platform admin — users never configure anything):
  1. Google Cloud Console → create project → enable "Gmail API"
  2. OAuth consent screen → External → add scope .../auth/gmail.send
  3. Credentials → OAuth client ID → "Web application"
       Authorized redirect URI:  {BACKEND_PUBLIC_URL}/api/email/google/callback
       (default http://localhost:8000/api/email/google/callback)
  4. Paste Client ID + Client Secret in Settings → Platform API Keys (or env
     GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).

Env (optional): BACKEND_PUBLIC_URL (default http://localhost:8000),
                FRONTEND_URL (default http://localhost:5173)
"""
import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user, SECRET_KEY
from .database import get_db

logger = logging.getLogger("jobsearcher.gmail_oauth")
router = APIRouter(prefix="/api/email/google", tags=["gmail-oauth"])

SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scraper_config.json")


def _cfg(name: str) -> str:
    v = os.getenv(name.upper(), "")
    if v:
        return v.strip()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return str(json.load(f).get(name, "") or "").strip()
    except Exception:
        return ""


def _client():
    return _cfg("google_client_id"), _cfg("google_client_secret")


def backend_url() -> str:
    return (os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000").rstrip("/")


def frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")


def redirect_uri() -> str:
    return f"{backend_url()}/api/email/google/callback"


def is_configured() -> bool:
    cid, secret = _client()
    return bool(cid and secret)


# ── access-token cache (refresh tokens are long-lived; access tokens last 1h) ──
_tok_cache: dict = {}
_tok_lock = threading.Lock()


def _access_token(refresh_token: str) -> str:
    if not refresh_token:
        raise HTTPException(400, "Gmail is not connected. Go to Settings → Email and click Connect Gmail.")
    with _tok_lock:
        hit = _tok_cache.get(refresh_token)
        if hit and hit[1] - 60 > time.time():
            return hit[0]
    cid, secret = _client()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": secret, "refresh_token": refresh_token,
        "grant_type": "refresh_token"}, timeout=15)
    if r.status_code != 200:
        logger.warning(f"[Gmail] token refresh failed: {r.text[:200]}")
        raise HTTPException(401, "Your Gmail connection expired or was revoked. "
                                 "Go to Settings → Email and click Connect Gmail again.")
    d = r.json()
    with _tok_lock:
        _tok_cache[refresh_token] = (d["access_token"], time.time() + int(d.get("expires_in", 3600)))
    return d["access_token"]


def send_raw_via_gmail(refresh_token: str, raw_mime: bytes):
    """Send an already-built MIME message (headers, body, attachments) via the Gmail API."""
    token = _access_token(refresh_token)
    r = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"raw": base64.urlsafe_b64encode(raw_mime).decode()}, timeout=30)
    if r.status_code >= 300:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        raise HTTPException(502, f"Gmail rejected the email: {msg}")


# ── routes ─────────────────────────────────────────────────────────────────────
@router.get("/status")
def status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    s = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == current_user.id).first()
    connected = bool(s and s.auth_method == "gmail_oauth" and s.gmail_refresh_token)
    return {"available": is_configured(), "connected": connected,
            "email": s.smtp_user if connected else "", "redirect_uri": redirect_uri()}


@router.get("/auth-url")
def auth_url(current_user: models.User = Depends(get_current_user)):
    cid, _ = _client()
    if not is_configured():
        raise HTTPException(400, "Connect Gmail isn't set up yet by the platform admin.")
    state = jwt.encode({"uid": current_user.id, "exp": datetime.utcnow() + timedelta(minutes=10),
                        "p": "gmail"}, SECRET_KEY, algorithm="HS256")
    params = {"client_id": cid, "redirect_uri": redirect_uri(), "response_type": "code",
              "scope": SCOPES, "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true", "state": state}
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


@router.get("/callback")
def callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    back = f"{frontend_url()}/settings"
    if error:
        return RedirectResponse(f"{back}?gmail=error&reason={error}")
    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=["HS256"])
        if payload.get("p") != "gmail":
            raise JWTError("bad purpose")
        uid = int(payload["uid"])
    except Exception:
        return RedirectResponse(f"{back}?gmail=error&reason=expired")

    cid, secret = _client()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": cid, "client_secret": secret,
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, timeout=15)
    if r.status_code != 200:
        logger.warning(f"[Gmail] code exchange failed: {r.text[:300]}")
        return RedirectResponse(f"{back}?gmail=error&reason=exchange")
    tok = r.json()
    if "gmail.send" not in tok.get("scope", ""):
        return RedirectResponse(f"{back}?gmail=error&reason=permission")
    refresh = tok.get("refresh_token")
    if not refresh:
        return RedirectResponse(f"{back}?gmail=error&reason=no_refresh")

    info = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                        headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=10).json()
    gmail = (info.get("email") or "").strip()
    if not gmail:
        return RedirectResponse(f"{back}?gmail=error&reason=email")

    user = db.query(models.User).filter(models.User.id == uid).first()
    s = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == uid).first()
    if not s:
        s = models.EmailSettings(user_id=uid)
        db.add(s)
    s.auth_method = "gmail_oauth"
    s.gmail_refresh_token = refresh
    s.smtp_user = gmail            # keeps every existing "is email configured?" check working
    s.smtp_password = ""
    s.smtp_host, s.smtp_port = "smtp.gmail.com", 587
    if not s.sender_name:
        s.sender_name = (info.get("name") or (user.name if user else "") or "").strip()
    db.commit()
    return RedirectResponse(f"{back}?gmail=connected")


@router.post("/disconnect")
def disconnect(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    s = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == current_user.id).first()
    if s and s.gmail_refresh_token:
        try:
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": s.gmail_refresh_token}, timeout=10)
        except Exception:
            pass
        _tok_cache.pop(s.gmail_refresh_token, None)
        s.gmail_refresh_token = ""
        s.auth_method = "smtp"
        s.smtp_user = ""
        db.commit()
    return {"message": "Gmail disconnected"}
