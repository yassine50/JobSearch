import io
import json
import os
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from .. import models
from ..database import get_db, DB_PATH, backup_sqlite_database
from ..auth import (
    get_admin_user,
    get_password_hash,
    verify_password,
    is_admin,
    create_access_token,
    jwt,
    SECRET_KEY,
    ALGORITHM,
)
from ..utils import purge_blacklisted_applications

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _resolve_admin_from_request_or_token(
    request: Request, token: Optional[str], db: Session
) -> models.User:
    raw = (token or "").strip()
    if not raw:
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            raw = auth_header.split(" ", 1)[1].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    try:
        payload = jwt.decode(raw, SECRET_KEY, algorithms=[ALGORITHM])
        email = (payload.get("sub") or "").strip()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _stream_cv_record(cv: models.CvUpload, fallback_name: str = "Resume.pdf") -> StreamingResponse:
    fname = (cv.filename or fallback_name).replace('"', "")
    if cv.file_data:
        low = fname.lower()
        if low.endswith(".pdf"):
            media = "application/pdf"
        elif low.endswith(".docx"):
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            media = "application/octet-stream"
        return StreamingResponse(
            io.BytesIO(bytes(cv.file_data)),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    # Fallback: render clean PDF or text from text_content if file_data is empty
    txt = (cv.text_content or "").strip()
    if not txt:
        raise HTTPException(status_code=404, detail="CV record has no content")
    try:
        from ..tailoring import honest_tailored_attachment
        pdf_bytes, _, _, _ = honest_tailored_attachment(
            cv, "Professional Resume", "", "", allow_low_confidence=True
        )
        if pdf_bytes:
            pdf_name = fname if fname.lower().endswith(".pdf") else f"{os.path.splitext(fname)[0] or 'Resume'}.pdf"
            return StreamingResponse(
                io.BytesIO(bytes(pdf_bytes)),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'},
            )
    except Exception:
        pass
    txt_name = f"{os.path.splitext(fname)[0] or 'Resume'}.txt"
    return StreamingResponse(
        io.BytesIO(txt.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{txt_name}"'},
    )


class AdminLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def admin_login(req: AdminLoginRequest, db: Session = Depends(get_db)):
    """
    Dedicated Back Office login endpoint. Verifies email + password and strictly
    enforces admin authorization (role == 'admin' or email in ADMIN_EMAILS).
    """
    clean_email = (req.email or "").strip().lower()
    user = db.query(models.User).filter(func.lower(models.User.email) == clean_email).first()
    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid admin email or password")
    if not verify_password(req.password or "", user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid admin email or password")
    if not is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Access denied: this account does not have Back Office Admin privileges.",
        )

    token = create_access_token({"sub": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_admin": True,
        },
    }


# ─── Schemas ─────────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "seeker"
    daily_digest_enabled: bool = True


class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    daily_digest_enabled: Optional[bool] = None
    daily_digest_role: Optional[str] = None


class AdminAppUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    match_score: Optional[int] = None


class AdminBlacklistAdd(BaseModel):
    email: str
    reason: str = "Blocked by Admin in Back Office"


class AdminConfigUpdate(BaseModel):
    serper_api_key: Optional[str] = None
    scraper_proxy: Optional[str] = None
    adzuna_app_id: Optional[str] = None
    adzuna_app_key: Optional[str] = None
    jooble_api_key: Optional[str] = None
    careerjet_affid: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _list_backups() -> List[dict]:
    backup_dir = os.path.expanduser(
        os.getenv("DB_BACKUP_DIR", os.path.join(os.path.dirname(DB_PATH), "backups"))
    )
    if not os.path.isdir(backup_dir):
        return []
    out = []
    for fname in sorted(os.listdir(backup_dir), reverse=True):
        if fname.endswith(".db"):
            fpath = os.path.join(backup_dir, fname)
            try:
                st = os.stat(fpath)
                out.append({
                    "filename": fname,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "modified_at": datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M UTC"),
                })
            except OSError:
                pass
    return out[:15]


# ─── 1. Executive Overview & System Health ───────────────────────────────────

@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Users KPIs
    total_users = db.query(func.count(models.User.id)).scalar() or 0
    users_with_cv = db.query(func.count(func.distinct(models.CvUpload.user_id))).scalar() or 0
    users_with_smtp = (
        db.query(func.count(models.EmailSettings.user_id))
        .filter(
            or_(
                models.EmailSettings.smtp_user != "",
                models.EmailSettings.gmail_refresh_token != "",
            )
        )
        .scalar()
        or 0
    )
    digest_enabled_users = (
        db.query(func.count(models.User.id))
        .filter(models.User.daily_digest_enabled == True)
        .scalar()
        or 0
    )

    # Applications KPIs
    status_rows = (
        db.query(models.Application.status, func.count(models.Application.id))
        .group_by(models.Application.status)
        .all()
    )
    by_status = {
        "saved": 0,
        "applied": 0,
        "review": 0,
        "interview": 0,
        "offer": 0,
        "accepted": 0,
        "rejected": 0,
    }
    for st, cnt in status_rows:
        key = "applied" if st == "sent" else (st or "applied").lower()
        by_status[key] = by_status.get(key, 0) + cnt

    total_apps = sum(by_status.values())
    apps_this_week = (
        db.query(func.count(models.Application.id))
        .filter(models.Application.applied_at >= week_ago)
        .scalar()
        or 0
    )
    avg_score_raw = db.query(func.avg(models.Application.match_score)).scalar()
    avg_match_score = round(float(avg_score_raw or 0), 1)

    # Emails KPIs
    email_status_rows = (
        db.query(models.EmailLog.status, func.count(models.EmailLog.id))
        .group_by(models.EmailLog.status)
        .all()
    )
    email_by_status = {str(s or "sent"): c for s, c in email_status_rows}
    total_emails = sum(email_by_status.values())
    emails_sent = email_by_status.get("sent", 0)
    emails_bounced = email_by_status.get("bounced", 0)
    emails_failed = email_by_status.get("failed", 0)
    recruiter_replies = (
        db.query(func.count(models.EmailLog.id))
        .filter(models.EmailLog.template_type == "recruiter_reply")
        .scalar()
        or 0
    )
    follow_ups_sent = (
        db.query(func.count(models.EmailLog.id))
        .filter(models.EmailLog.template_type == "follow_up")
        .scalar()
        or 0
    )
    emails_this_week = (
        db.query(func.count(models.EmailLog.id))
        .filter(models.EmailLog.sent_at >= week_ago)
        .scalar()
        or 0
    )

    # Index & Storage counts
    verified_posts_count = db.query(func.count(models.VerifiedRecruiterPost.id)).scalar() or 0
    job_sightings_count = db.query(func.count(models.JobSighting.id)).scalar() or 0
    blacklist_count = db.query(func.count(models.EmailBlacklist.id)).scalar() or 0
    watchlists_count = db.query(func.count(models.SavedWatchlist.id)).scalar() or 0
    saved_jobs_count = db.query(func.count(models.SavedJob.id)).scalar() or 0
    templates_count = db.query(func.count(models.CustomTemplate.id)).scalar() or 0
    total_cvs_count = db.query(func.count(models.CvUpload.id)).scalar() or 0

    # System & Cache Health
    db_size_mb = 0.0
    if os.path.exists(DB_PATH):
        try:
            db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
        except OSError:
            pass

    from .jobs import _get_scraper_config, _search_cache, SEARCH_DAILY_LIMIT
    from ..official_apis import configured_providers
    cfg = _get_scraper_config()
    serper = cfg.get("serper_api_key") or os.getenv("SERPER_API_KEY", "")
    proxy = cfg.get("scraper_proxy") or os.getenv("SCRAPER_PROXY", "")
    backups = _list_backups()

    # Recent activity feed
    recent_users = (
        db.query(models.User)
        .order_by(models.User.created_at.desc())
        .limit(6)
        .all()
    )
    recent_apps = (
        db.query(models.Application, models.User.name, models.User.email)
        .outerjoin(models.User, models.Application.user_id == models.User.id)
        .order_by(models.Application.applied_at.desc())
        .limit(8)
        .all()
    )
    recent_emails = (
        db.query(models.EmailLog, models.User.email)
        .outerjoin(models.User, models.EmailLog.user_id == models.User.id)
        .order_by(models.EmailLog.sent_at.desc())
        .limit(8)
        .all()
    )

    return {
        "users": {
            "total": total_users,
            "with_cv": users_with_cv,
            "with_smtp": users_with_smtp,
            "digest_enabled": digest_enabled_users,
            "total_cvs": total_cvs_count,
        },
        "applications": {
            "total": total_apps,
            "this_week": apps_this_week,
            "avg_match_score": avg_match_score,
            "by_status": by_status,
        },
        "emails": {
            "total": total_emails,
            "sent": emails_sent,
            "bounced": emails_bounced,
            "failed": emails_failed,
            "recruiter_replies": recruiter_replies,
            "follow_ups": follow_ups_sent,
            "this_week": emails_this_week,
        },
        "index": {
            "verified_recruiter_posts": verified_posts_count,
            "job_sightings": job_sightings_count,
            "blacklisted_emails": blacklist_count,
            "saved_watchlists": watchlists_count,
            "saved_jobs": saved_jobs_count,
            "custom_templates": templates_count,
        },
        "system": {
            "db_path": DB_PATH,
            "db_size_mb": db_size_mb,
            "backups_count": len(backups),
            "backups": backups,
            "search_cache_entries": len(_search_cache),
            "has_serper": bool(serper.strip()),
            "has_proxy": bool(proxy.strip()),
            "official_providers": configured_providers(),
            "daily_search_limit": SEARCH_DAILY_LIMIT,
        },
        "recent_activity": {
            "users": [
                {
                    "id": u.id,
                    "name": u.name,
                    "email": u.email,
                    "role": u.role,
                    "created_at": str(u.created_at),
                }
                for u in recent_users
            ],
            "applications": [
                {
                    "id": a.id,
                    "title": a.title,
                    "company": a.company,
                    "status": "applied" if a.status == "sent" else a.status,
                    "match_score": a.match_score,
                    "applied_at": str(a.applied_at),
                    "user_name": u_name or "Unknown",
                    "user_email": u_email or "",
                }
                for a, u_name, u_email in recent_apps
            ],
            "emails": [
                {
                    "id": l.id,
                    "to_email": l.to_email,
                    "subject": l.subject,
                    "status": l.status,
                    "template_type": l.template_type,
                    "sent_at": str(l.sent_at),
                    "user_email": u_email or "",
                }
                for l, u_email in recent_emails
            ],
        },
    }


# ─── 2. User Management CRM ──────────────────────────────────────────────────

@router.get("/users")
def list_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    q = db.query(models.User)
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(or_(models.User.name.ilike(s), models.User.email.ilike(s)))
    if role and role.strip() and role != "all":
        q = q.filter(models.User.role == role.strip())

    users = q.order_by(models.User.id.asc()).all()

    # Batch aggregate counts per user to avoid N+1 queries
    app_counts = dict(
        db.query(models.Application.user_id, func.count(models.Application.id))
        .group_by(models.Application.user_id)
        .all()
    )
    email_counts = dict(
        db.query(models.EmailLog.user_id, func.count(models.EmailLog.id))
        .filter(models.EmailLog.status == "sent")
        .group_by(models.EmailLog.user_id)
        .all()
    )
    saved_counts = dict(
        db.query(models.SavedJob.user_id, func.count(models.SavedJob.id))
        .group_by(models.SavedJob.user_id)
        .all()
    )
    watchlist_counts = dict(
        db.query(models.SavedWatchlist.user_id, func.count(models.SavedWatchlist.id))
        .group_by(models.SavedWatchlist.user_id)
        .all()
    )

    cvs = (
        db.query(
            models.CvUpload.user_id,
            models.CvUpload.filename,
            models.CvUpload.persona_name,
            models.CvUpload.is_active,
            models.CvUpload.text_content,
        )
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .all()
    )
    cv_by_user = {}
    cv_count_by_user = {}
    for uid, fname, pname, is_act, txt in cvs:
        cv_count_by_user[uid] = cv_count_by_user.get(uid, 0) + 1
        if uid not in cv_by_user:
            cv_by_user[uid] = {
                "filename": fname,
                "persona_name": pname,
                "words": len((txt or "").split()),
            }

    smtp_rows = db.query(models.EmailSettings).all()
    smtp_by_user = {s.user_id: s for s in smtp_rows}

    out = []
    for u in users:
        cv_info = cv_by_user.get(u.id)
        smtp = smtp_by_user.get(u.id)
        smtp_ok = bool(smtp and (smtp.smtp_user or getattr(smtp, "gmail_refresh_token", "")))
        out.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role or "seeker",
            "is_admin": is_admin(u),
            "daily_digest_enabled": bool(u.daily_digest_enabled),
            "daily_digest_role": u.daily_digest_role or "",
            "last_digest_sent_at": str(u.last_digest_sent_at) if u.last_digest_sent_at else None,
            "has_linkedin_cookie": bool((u.linkedin_cookie or "").strip()),
            "created_at": str(u.created_at),
            "cv_count": cv_count_by_user.get(u.id, 0),
            "active_cv_filename": cv_info["filename"] if cv_info else None,
            "active_cv_words": cv_info["words"] if cv_info else 0,
            "smtp_configured": smtp_ok,
            "smtp_user": smtp.smtp_user if smtp else "",
            "auth_method": getattr(smtp, "auth_method", "smtp") if smtp else "smtp",
            "applications_count": app_counts.get(u.id, 0),
            "emails_sent_count": email_counts.get(u.id, 0),
            "saved_jobs_count": saved_counts.get(u.id, 0),
            "watchlists_count": watchlist_counts.get(u.id, 0),
        })
    return {"users": out, "total": len(out)}


@router.post("/users")
def create_user_admin(
    req: AdminUserCreate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    name = (req.name or "").strip()
    email = (req.email or "").strip().lower()
    if len(name) < 2:
        raise HTTPException(400, "Name must be at least 2 characters")
    if "@" not in email:
        raise HTTPException(400, "Valid email is required")
    if len(req.password or "") < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(400, "Email is already registered")

    role = req.role if req.role in ("seeker", "recruiter", "both", "admin") else "seeker"
    u = models.User(
        name=name,
        email=email,
        hashed_password=get_password_hash(req.password),
        role=role,
        daily_digest_enabled=req.daily_digest_enabled,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {
        "message": f"Created user {u.email}",
        "user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role},
    }


@router.patch("/users/{user_id}")
def update_user_admin(
    user_id: int,
    req: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    if req.name is not None and req.name.strip():
        u.name = req.name.strip()
    if req.email is not None and req.email.strip():
        new_email = req.email.strip().lower()
        existing = (
            db.query(models.User)
            .filter(models.User.email == new_email, models.User.id != user_id)
            .first()
        )
        if existing:
            raise HTTPException(400, "Email already in use by another user")
        u.email = new_email
    if req.role is not None and req.role in ("seeker", "recruiter", "both", "admin"):
        u.role = req.role
    if req.password is not None and req.password.strip():
        if len(req.password.strip()) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        u.hashed_password = get_password_hash(req.password.strip())
    if req.daily_digest_enabled is not None:
        u.daily_digest_enabled = bool(req.daily_digest_enabled)
    if req.daily_digest_role is not None:
        u.daily_digest_role = req.daily_digest_role.strip()

    db.commit()
    return {
        "message": f"Updated user {u.email}",
        "user": {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "daily_digest_enabled": bool(u.daily_digest_enabled),
            "daily_digest_role": u.daily_digest_role or "",
        },
    }


@router.delete("/users/{user_id}")
def delete_user_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin_user.id:
        raise HTTPException(400, "Cannot delete your own active admin account")

    email_deleted = u.email
    db.query(models.EmailLog).filter(models.EmailLog.user_id == user_id).delete(synchronize_session=False)
    db.query(models.Application).filter(models.Application.user_id == user_id).delete(synchronize_session=False)
    db.query(models.SavedJob).filter(models.SavedJob.user_id == user_id).delete(synchronize_session=False)
    db.query(models.CvUpload).filter(models.CvUpload.user_id == user_id).delete(synchronize_session=False)
    db.query(models.EmailSettings).filter(models.EmailSettings.user_id == user_id).delete(synchronize_session=False)
    db.query(models.CustomTemplate).filter(models.CustomTemplate.user_id == user_id).delete(synchronize_session=False)
    db.query(models.SavedWatchlist).filter(models.SavedWatchlist.user_id == user_id).delete(synchronize_session=False)
    db.query(models.EmailBlacklist).filter(models.EmailBlacklist.user_id == user_id).delete(synchronize_session=False)
    db.delete(u)
    db.commit()
    return {"message": f"Deleted user {email_deleted} and all associated records"}


@router.post("/users/{user_id}/send-digest")
def send_user_digest_now(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    from ..auto_dispatcher import dispatch_daily_top_matches_digest
    res = dispatch_daily_top_matches_digest(db, user_id, force_manual=True)
    if not res.get("sent", False):
        err_reason = res.get("error") or "Email provider rejected or skipped delivery"
        raise HTTPException(
            status_code=400,
            detail=f"Digest email NOT delivered to {res.get('recipient') or f'user #{user_id}'}: {err_reason}",
        )
    return {
        "message": f"✅ Digest DELIVERED to {res.get('recipient')} via {res.get('provider') or 'Resend'} ({res.get('matches_count', 0)} matches)",
        "sent": True,
        "recipient": res.get("recipient", ""),
        "provider": res.get("provider", ""),
        "role": res.get("role", ""),
        "matches_count": res.get("matches_count", 0),
        "mode": res.get("mode", "daily_top_5"),
    }


@router.get("/users/{user_id}/cvs")
def list_user_cvs_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    rows = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id)
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .all()
    )
    return {
        "user": {"id": u.id, "name": u.name, "email": u.email},
        "cvs": [
            {
                "id": c.id,
                "persona_name": c.persona_name or "Primary Resume",
                "filename": c.filename or f"CV_{c.id}.pdf",
                "is_active": bool(c.is_active),
                "words": len((c.text_content or "").split()),
                "text_content": c.text_content or "",
                "uploaded_at": str(c.uploaded_at),
            }
            for c in rows
        ],
    }


@router.get("/users/{user_id}/cv/download")
def download_user_active_cv_admin(
    user_id: int,
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _resolve_admin_from_request_or_token(request, token, db)
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    cv = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id)
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .first()
    )
    if not cv:
        raise HTTPException(404, "User has no uploaded CV")
    safe_user = (u.name or u.email or f"user_{user_id}").replace(" ", "_")
    return _stream_cv_record(cv, fallback_name=f"CV_{safe_user}.pdf")


@router.get("/cvs/{cv_id}/download")
def download_specific_cv_admin(
    cv_id: int,
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _resolve_admin_from_request_or_token(request, token, db)
    cv = db.query(models.CvUpload).filter(models.CvUpload.id == cv_id).first()
    if not cv:
        raise HTTPException(404, "CV not found")
    return _stream_cv_record(cv, fallback_name=f"CV_{cv_id}.pdf")


@router.get("/applications/{app_id}/cv")
def download_application_cv_admin(
    app_id: int,
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _resolve_admin_from_request_or_token(request, token, db)
    a = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if a.tailored_cv_data:
        fname = (a.tailored_cv_filename or f"Tailored_CV_{a.id}.pdf").replace('"', "")
        return StreamingResponse(
            io.BytesIO(bytes(a.tailored_cv_data)),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    cv = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == a.user_id)
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .first()
    )
    if not cv:
        raise HTTPException(404, "No CV found for this application or user")
    return _stream_cv_record(cv, fallback_name=f"CV_App_{app_id}.pdf")


# ─── 3. Global Applications & Outreach Monitor ──────────────────────────────

@router.get("/applications")
def list_all_applications(
    search: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 120,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    q = (
        db.query(models.Application, models.User.name, models.User.email)
        .outerjoin(models.User, models.Application.user_id == models.User.id)
    )
    if user_id:
        q = q.filter(models.Application.user_id == user_id)
    if status and status != "all":
        if status == "applied":
            q = q.filter(models.Application.status.in_(["applied", "sent"]))
        else:
            q = q.filter(models.Application.status == status)
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.Application.title.ilike(s),
                models.Application.company.ilike(s),
                models.Application.location.ilike(s),
                models.Application.notes.ilike(s),
                models.User.email.ilike(s),
                models.User.name.ilike(s),
            )
        )

    rows = q.order_by(models.Application.applied_at.desc()).limit(min(limit, 500)).all()
    out = []
    for a, u_name, u_email in rows:
        st = "applied" if a.status == "sent" else (a.status or "applied")
        out.append({
            "id": a.id,
            "user_id": a.user_id,
            "user_name": u_name or "Unknown",
            "user_email": u_email or "",
            "title": a.title,
            "company": a.company,
            "location": a.location,
            "url": a.url,
            "status": st,
            "match_score": a.match_score or 0,
            "notes": (a.notes or "")[:400],
            "has_tailored_cv": bool(a.tailored_cv_filename),
            "applied_at": str(a.applied_at),
            "follow_up_date": str(a.follow_up_date) if a.follow_up_date else None,
        })
    return {"applications": out, "count": len(out)}


@router.patch("/applications/{app_id}")
def update_application_admin(
    app_id: int,
    req: AdminAppUpdate,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    a = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if req.status is not None:
        a.status = req.status
    if req.notes is not None:
        a.notes = req.notes
    if req.match_score is not None:
        a.match_score = req.match_score
    db.commit()
    return {"message": "Application updated", "id": a.id, "status": a.status}


@router.delete("/applications/{app_id}")
def delete_application_admin(
    app_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    a = db.query(models.Application).filter(models.Application.id == app_id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    db.query(models.EmailLog).filter(models.EmailLog.application_id == app_id).delete(synchronize_session=False)
    db.delete(a)
    db.commit()
    return {"message": f"Deleted application #{app_id}"}


@router.get("/emails")
def list_all_emails(
    search: Optional[str] = None,
    status: Optional[str] = None,
    template_type: Optional[str] = None,
    limit: int = 120,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    q = (
        db.query(models.EmailLog, models.User.name, models.User.email)
        .outerjoin(models.User, models.EmailLog.user_id == models.User.id)
    )
    if status and status != "all":
        q = q.filter(models.EmailLog.status == status)
    if template_type and template_type != "all":
        q = q.filter(models.EmailLog.template_type == template_type)
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.EmailLog.to_email.ilike(s),
                models.EmailLog.to_name.ilike(s),
                models.EmailLog.subject.ilike(s),
                models.User.email.ilike(s),
            )
        )

    rows = q.order_by(models.EmailLog.sent_at.desc()).limit(min(limit, 500)).all()
    out = []
    for l, u_name, u_email in rows:
        out.append({
            "id": l.id,
            "user_id": l.user_id,
            "user_name": u_name or "Unknown",
            "user_email": u_email or "",
            "application_id": l.application_id,
            "to_email": l.to_email,
            "to_name": l.to_name,
            "subject": l.subject,
            "body_preview": (l.body or "")[:280],
            "template_type": l.template_type,
            "status": l.status,
            "sent_at": str(l.sent_at),
        })
    return {"emails": out, "count": len(out)}


@router.delete("/emails/{log_id}")
def delete_email_log_admin(
    log_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    l = db.query(models.EmailLog).filter(models.EmailLog.id == log_id).first()
    if not l:
        raise HTTPException(404, "Email log not found")
    db.delete(l)
    db.commit()
    return {"message": f"Deleted email log #{log_id}"}


# ─── 4. Verified Recruiter Posts Index & Blacklist Manager ───────────────────

@router.get("/recruiter-posts")
def list_recruiter_posts_index(
    search: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    q = db.query(models.VerifiedRecruiterPost)
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.VerifiedRecruiterPost.role_title.ilike(s),
                models.VerifiedRecruiterPost.role_key.ilike(s),
                models.VerifiedRecruiterPost.company.ilike(s),
                models.VerifiedRecruiterPost.author_name.ilike(s),
                models.VerifiedRecruiterPost.location.ilike(s),
                models.VerifiedRecruiterPost.recruiter_emails_json.ilike(s),
            )
        )
    rows = (
        q.order_by(models.VerifiedRecruiterPost.published_epoch.desc(), models.VerifiedRecruiterPost.id.desc())
        .limit(min(limit, 300))
        .all()
    )
    out = []
    for p in rows:
        try:
            emails = json.loads(p.recruiter_emails_json or "[]")
        except Exception:
            emails = []
        try:
            skills = json.loads(p.matched_skills_json or "[]")
        except Exception:
            skills = []
        out.append({
            "id": p.id,
            "post_id": p.post_id,
            "post_url": p.post_url,
            "role_key": p.role_key,
            "role_title": p.role_title,
            "company": p.company,
            "author_name": p.author_name,
            "location": p.location,
            "role_fit_score": p.role_fit_score,
            "emails": emails,
            "skills": skills[:8],
            "date_published": p.date_published,
            "discovered_at": str(p.discovered_at),
            "snippet": (p.full_text or "")[:240],
        })
    return {"posts": out, "count": len(out)}


@router.delete("/recruiter-posts/{post_db_id}")
def delete_recruiter_post_index(
    post_db_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    p = db.query(models.VerifiedRecruiterPost).filter(models.VerifiedRecruiterPost.id == post_db_id).first()
    if not p:
        raise HTTPException(404, "Recruiter post not found")
    db.delete(p)
    db.commit()
    return {"message": f"Deleted indexed recruiter post #{post_db_id}"}


@router.get("/blacklist")
def list_global_blacklist(
    search: Optional[str] = None,
    limit: int = 150,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    q = db.query(models.EmailBlacklist)
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.EmailBlacklist.email.ilike(s),
                models.EmailBlacklist.reason.ilike(s),
                models.EmailBlacklist.source.ilike(s),
            )
        )
    rows = q.order_by(models.EmailBlacklist.id.desc()).limit(min(limit, 500)).all()
    return {
        "blacklist": [
            {
                "id": b.id,
                "email": b.email,
                "reason": b.reason,
                "source": b.source,
                "user_id": b.user_id,
                "created_at": str(b.created_at),
            }
            for b in rows
        ],
        "count": len(rows),
    }


@router.post("/blacklist")
def add_global_blacklist(
    req: AdminBlacklistAdd,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    clean = (req.email or "").strip().lower()
    if not clean or "@" not in clean:
        raise HTTPException(400, "Valid email address is required")
    existing = db.query(models.EmailBlacklist).filter(models.EmailBlacklist.email == clean).first()
    if existing:
        existing.reason = req.reason or existing.reason
        db.commit()
        return {"message": f"{clean} is already blacklisted (reason updated)", "id": existing.id}

    entry = models.EmailBlacklist(
        user_id=None,
        email=clean,
        reason=req.reason or "Blocked by Admin in Back Office",
        source="admin_backoffice",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    purged = purge_blacklisted_applications(db)
    return {
        "message": f"Blocked {clean} globally and purged {purged} dead application(s)",
        "id": entry.id,
        "purged": purged,
    }


@router.delete("/blacklist/{entry_id}")
def remove_global_blacklist(
    entry_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    entry = db.query(models.EmailBlacklist).filter(models.EmailBlacklist.id == entry_id).first()
    if not entry:
        raise HTTPException(404, "Blacklist entry not found")
    email_val = entry.email
    db.delete(entry)
    db.commit()
    return {"message": f"Unblocked {email_val}"}


# ─── 5. System Configuration & 1-Click Maintenance ──────────────────────────

@router.get("/config")
def get_admin_config(admin_user: models.User = Depends(get_admin_user)):
    from .jobs import _get_scraper_config, SEARCH_DAILY_LIMIT
    from ..official_apis import configured_providers, get_key, KEY_NAMES
    cfg = _get_scraper_config()
    serper = cfg.get("serper_api_key") or os.getenv("SERPER_API_KEY", "")
    proxy = cfg.get("scraper_proxy") or os.getenv("SCRAPER_PROXY", "")
    return {
        "serper_api_key": serper,
        "scraper_proxy": proxy,
        **{k: get_key(k) for k in KEY_NAMES},
        "official_providers": configured_providers(),
        "daily_search_limit": SEARCH_DAILY_LIMIT,
        "backups": _list_backups(),
    }


@router.post("/config")
def save_admin_config(
    data: AdminConfigUpdate,
    admin_user: models.User = Depends(get_admin_user),
):
    from .jobs import _get_scraper_config, _save_scraper_config
    from ..official_apis import configured_providers
    cfg = _get_scraper_config()
    for field, value in data.dict().items():
        if value is not None:
            cfg[field] = value.strip()
    _save_scraper_config(cfg)
    return {
        "message": "Platform configuration saved",
        "has_serper": bool(cfg.get("serper_api_key")),
        "has_proxy": bool(cfg.get("scraper_proxy")),
        "official_providers": configured_providers(),
    }


@router.post("/maintenance/{action}")
def run_maintenance_action(
    action: str,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(get_admin_user),
):
    if action == "backup-db":
        dest = backup_sqlite_database(DB_PATH)
        if not dest:
            raise HTTPException(500, "Database backup could not be created")
        return {
            "message": f"Hot SQLite backup created: {os.path.basename(dest)}",
            "path": dest,
            "backups": _list_backups(),
        }

    elif action == "clear-cache":
        from .jobs import _search_cache, _search_cache_lock
        from ..open_sources import _cache as open_cache, _parsed_cache, _cache_lock
        from .recruiter import _RECRUITER_CACHE, _RECRUITER_LOCK

        with _search_cache_lock:
            c1 = len(_search_cache)
            _search_cache.clear()
        with _cache_lock:
            c2 = len(open_cache) + len(_parsed_cache)
            open_cache.clear()
            _parsed_cache.clear()
        with _RECRUITER_LOCK:
            c3 = len(_RECRUITER_CACHE)
            _RECRUITER_CACHE.clear()
        return {
            "message": f"Cleared all in-memory caches ({c1} job searches, {c2} open feed caches, {c3} recruiter caches)."
        }

    elif action == "purge-blacklisted":
        purged = purge_blacklisted_applications(db)
        return {"message": f"Purged {purged} blacklisted application(s) across all users.", "purged": purged}

    elif action == "purge-bounced-logs":
        deleted = (
            db.query(models.EmailLog)
            .filter(models.EmailLog.status.in_(["bounced", "failed"]))
            .delete(synchronize_session=False)
        )
        db.commit()
        return {"message": f"Purged {deleted} bounced/failed email log record(s).", "deleted": deleted}

    elif action == "auto-reject-stale":
        from ..auto_dispatcher import auto_reject_unresponsive_follow_ups
        res = auto_reject_unresponsive_follow_ups(db, days_threshold=3)
        cnt = res.get("auto_rejected_count", 0)
        return {
            "message": f"Auto-rejected {cnt} unresponsive application(s) waiting >3 days after follow-up.",
            "auto_rejected_count": cnt,
        }

    elif action == "purge-test-users":
        test_users = (
            db.query(models.User)
            .filter(
                models.User.id != admin_user.id,
                or_(
                    models.User.email.ilike("%@example.com"),
                    models.User.email.ilike("test%@test.com"),
                    models.User.email.ilike("demo%@%"),
                ),
            )
            .all()
        )
        deleted_emails = []
        for tu in test_users:
            if is_admin(tu):
                continue
            deleted_emails.append(tu.email)
            db.query(models.EmailLog).filter(models.EmailLog.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.Application).filter(models.Application.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.SavedJob).filter(models.SavedJob.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.CvUpload).filter(models.CvUpload.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.EmailSettings).filter(models.EmailSettings.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.CustomTemplate).filter(models.CustomTemplate.user_id == tu.id).delete(synchronize_session=False)
            db.query(models.SavedWatchlist).filter(models.SavedWatchlist.user_id == tu.id).delete(synchronize_session=False)
            db.delete(tu)
        db.commit()
        return {
            "message": f"Purged {len(deleted_emails)} test/demo user account(s).",
            "deleted_emails": deleted_emails,
        }

    raise HTTPException(400, f"Unknown maintenance action: {action}")
