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
import secrets
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from . import models
from .auth import get_current_user, SECRET_KEY, create_access_token, get_password_hash, is_admin
from .database import get_db

logger = logging.getLogger("jobsearcher.gmail_oauth")
router = APIRouter(prefix="/api/email/google", tags=["gmail-oauth"])

SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scraper_config.json")
DEFAULT_GOOGLE_CLIENT_ID = "351639376298-otgv89j6pf4mbtmpgibjg0l9l7bhllbt.apps.googleusercontent.com"
DEFAULT_GOOGLE_CLIENT_SECRET = "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"


def _cfg(name: str) -> str:
    v = os.getenv(name.upper(), "")
    if v:
        return v.strip()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            val = str(json.load(f).get(name, "") or "").strip()
            if val:
                return val
    except Exception:
        pass
    if name == "google_client_id":
        return DEFAULT_GOOGLE_CLIENT_ID
    if name == "google_client_secret":
        return DEFAULT_GOOGLE_CLIENT_SECRET
    return ""


def _client():
    return _cfg("google_client_id"), _cfg("google_client_secret")


def backend_url() -> str:
    return (os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000").rstrip("/")


def frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "http://localhost:5173").rstrip("/")


_ALLOWED_ORIGINS = {
    "https://www.cvtomatch.com",
    "https://cvtomatch.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def _safe_origin(origin: str) -> str:
    """Exact-match origin whitelist (prevents open redirects like cvtomatch.com.evil.io)."""
    clean = (origin or "").strip().rstrip("/")
    if clean.startswith(("http://localhost:", "http://127.0.0.1:")):
        return clean
    extra = {o.strip().rstrip("/") for o in (os.getenv("ALLOWED_FRONTEND_ORIGINS") or "").split(",") if o.strip()}
    return clean if clean in (_ALLOWED_ORIGINS | extra | {frontend_url()}) else ""


def redirect_uri(origin: str = "") -> str:
    clean_origin = _safe_origin(origin)
    if clean_origin:
        if "localhost" in clean_origin or "127.0.0.1" in clean_origin:
            return "http://localhost:8000/api/email/google/callback"
        if clean_origin == "https://cvtomatch.com":
            return "https://www.cvtomatch.com/api/email/google/callback"
        return f"{clean_origin}/api/email/google/callback"
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
def auth_url(origin: str = "", current_user: models.User = Depends(get_current_user)):
    cid, _ = _client()
    if not is_configured():
        raise HTTPException(400, "Connect Gmail isn't set up yet by the platform admin.")
    clean_origin = _safe_origin(origin)
    r_uri = redirect_uri(clean_origin)
    state = jwt.encode({
        "uid": current_user.id,
        "exp": datetime.utcnow() + timedelta(minutes=10),
        "p": "gmail",
        "origin": clean_origin,
        "r_uri": r_uri,
    }, SECRET_KEY, algorithm="HS256")
    params = {"client_id": cid, "redirect_uri": r_uri, "response_type": "code",
              "scope": SCOPES, "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true", "state": state}
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


@router.get("/login-url")
def login_url(origin: str = "", role: str = "seeker"):
    """
    Build a server-side Google OAuth 2.0 Sign-In URL using the authorized
    `/api/email/google/callback` redirect URI (avoids GIS JavaScript `origin_mismatch`).
    """
    cid, _ = _client()
    if not is_configured():
        raise HTTPException(400, "Google Sign-In is not configured on this server.")
    clean_origin = _safe_origin(origin) or frontend_url()
    r_uri = redirect_uri(clean_origin)
    safe_role = role if role in ("seeker", "recruiter", "both") else "seeker"
    state = jwt.encode({
        "p": "login",
        "role": safe_role,
        "origin": clean_origin,
        "r_uri": r_uri,
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }, SECRET_KEY, algorithm="HS256")
    params = {
        "client_id": cid,
        "redirect_uri": r_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "state": state,
    }
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


def _popup_login_html(front_origin: str, payload_dict: dict) -> HTMLResponse:
    js_payload = json.dumps(payload_dict)
    safe_front = json.dumps(front_origin or frontend_url())
    html_str = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Signing in with Google...</title></head>
<body style="background:#050811;color:#fff;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
  <div style="text-align:center;">
    <div style="font-size:15px;font-weight:700;margin-bottom:6px;">Completing Google Sign-In...</div>
    <div style="font-size:12px;color:#94a3b8;">This window will close automatically.</div>
  </div>
  <script>
    (function() {{
      var data = {js_payload};
      var front = {safe_front};
      try {{
        if (window.opener && !window.opener.closed) {{
          window.opener.postMessage(data, "*");
          setTimeout(function() {{ window.close(); }}, 80);
          return;
        }}
      }} catch (e) {{}}
      if (data.access_token) {{
        window.location.replace(front + "/?google_auth_token=" + encodeURIComponent(data.access_token));
      }} else {{
        window.location.replace(front + "/?google_auth_error=" + encodeURIComponent(data.error || "Google authentication failed"));
      }}
    }})();
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_str)


@router.get("/callback")
def callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    back = f"{frontend_url()}/settings"
    r_uri = redirect_uri()
    purpose = "gmail"
    front_origin = frontend_url()
    role = "seeker"
    uid = 0
    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=["HS256"])
        purpose = payload.get("p") or "gmail"
        if purpose not in ("gmail", "login"):
            raise JWTError("bad purpose")
        if payload.get("origin") and _safe_origin(payload["origin"]):
            front_origin = _safe_origin(payload["origin"])
            back = f"{front_origin}/settings"
        if payload.get("r_uri"):
            r_uri = payload["r_uri"]
        if purpose == "gmail":
            uid = int(payload["uid"])
        else:
            role = payload.get("role") if payload.get("role") in ("seeker", "recruiter", "both") else "seeker"
    except Exception:
        if purpose == "login":
            return _popup_login_html(front_origin, {"type": "cvtomatch_google_auth", "error": "Sign-in session expired. Please try again."})
        return RedirectResponse(f"{back}?gmail=error&reason=expired")

    if error:
        if purpose == "login":
            return _popup_login_html(front_origin, {"type": "cvtomatch_google_auth", "error": error[:100]})
        from urllib.parse import quote
        return RedirectResponse(f"{back}?gmail=error&reason={quote(error[:100])}")

    cid, secret = _client()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": cid, "client_secret": secret,
        "redirect_uri": r_uri, "grant_type": "authorization_code"}, timeout=15)
    if r.status_code != 200:
        logger.warning(f"[GoogleOAuth] code exchange failed: {r.text[:300]}")
        if purpose == "login":
            return _popup_login_html(front_origin, {"type": "cvtomatch_google_auth", "error": "Failed to exchange Google authorization code."})
        return RedirectResponse(f"{back}?gmail=error&reason=exchange")
    tok = r.json()

    if purpose == "login":
        info = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {tok.get('access_token', '')}"},
            timeout=10,
        ).json()
        email = (info.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return _popup_login_html(front_origin, {"type": "cvtomatch_google_auth", "error": "Google account did not provide a valid email."})
        raw_name = (info.get("name") or info.get("given_name") or "").strip()
        if not raw_name or len(raw_name) < 2:
            raw_name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
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
        jwt_tok = create_access_token({"sub": user.email})
        user_payload = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_admin": is_admin(user),
        }
        return _popup_login_html(front_origin, {
            "type": "cvtomatch_google_auth",
            "access_token": jwt_tok,
            "user": user_payload,
        })

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
