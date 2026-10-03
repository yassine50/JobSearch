
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
import io, csv, re
from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/tracker", tags=["tracker"])
VALID_STATUSES = ["saved", "applied", "sent", "review", "interview", "offer", "rejected", "accepted"]

@router.post("/sync-mailbox")
def sync_mailbox(db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """
    Unified Mailbox Sync & Outreach Automation:
    1. Cleans Gmail bounces, expunges dead messages from Sent, blacklists globally.
    2. Synchronizes recruiter replies and updates application outcomes (interview/review/rejected).
    3. Auto-dispatches follow-ups for applications waiting >3 days with no recruiter reply.
    4. Dispatches saved/queued applications to recruiters with tailored CVs.
    """
    from ..bounce_cleaner import sync_gmail_bounces
    from ..reply_analyzer import sync_recruiter_replies
    from ..auto_dispatcher import auto_dispatch_follow_ups, dispatch_saved_applications, auto_reject_unresponsive_follow_ups

    # 1. Clean bounces
    bounce_res = {}
    try:
        bounce_res = sync_gmail_bounces(db, current_user.id, delete_from_gmail=True)
    except Exception as e:
        bounce_res = {"error": str(e)}

    # 2. Sync incoming recruiter replies
    reply_res = {}
    try:
        reply_res = sync_recruiter_replies(db, current_user.id)
    except Exception as e:
        reply_res = {"error": str(e)}

    # 3. Follow-up automation for applications waiting >3 days
    followup_res = {}
    try:
        followup_res = auto_dispatch_follow_ups(db, current_user.id, days_threshold=3)
    except Exception as e:
        followup_res = {"error": str(e)}

    # 3b. Auto-reject applications where follow-up was sent >3 days ago without recruiter response
    auto_reject_res = {}
    try:
        auto_reject_res = auto_reject_unresponsive_follow_ups(db, current_user.id, days_threshold=3)
    except Exception as e:
        auto_reject_res = {"error": str(e)}

    # 4. Dispatch saved / queued applications
    saved_res = {}
    try:
        saved_res = dispatch_saved_applications(db, current_user.id)
    except Exception as e:
        saved_res = {"error": str(e)}

    dead_purged = (bounce_res.get("tracker_purged") or 0) + (bounce_res.get("deleted_from_sent") or 0)
    replies_updated = reply_res.get("updated_applications") or 0
    follow_ups_sent = followup_res.get("sent_count") or 0
    auto_rejected = auto_reject_res.get("auto_rejected_count") or 0
    saved_sent = saved_res.get("sent_count") or 0
    quota_reached = bool(followup_res.get("quota_reached") or saved_res.get("quota_reached"))
    remaining_saved = saved_res.get("remaining_saved", 0)

    return {
        "success": True,
        "bounces": bounce_res,
        "replies": reply_res,
        "follow_ups": followup_res,
        "auto_reject": auto_reject_res,
        "saved_jobs": saved_res,
        "summary": {
            "dead_purged": dead_purged,
            "replies_updated": replies_updated,
            "follow_ups_sent": follow_ups_sent,
            "auto_rejected": auto_rejected,
            "saved_sent": saved_sent,
            "quota_reached": quota_reached,
            "remaining_saved": remaining_saved,
            "breakdown": reply_res.get("breakdown") or {}
        }
    }

@router.post("/auto-reject-unresponsive")
def trigger_auto_reject(days: int = 3,
                        db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    """Automatically moves applications where a follow-up was sent >days ago with no response to 'rejected'."""
    from ..auto_dispatcher import auto_reject_unresponsive_follow_ups
    return auto_reject_unresponsive_follow_ups(db, current_user.id, days_threshold=days)

@router.post("/sync-replies")
def sync_replies(db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """
    Scans incoming recruiter replies from Gmail, detects application outcomes
    (rejection, review, interview, offer), and updates the tracker board.
    """
    from ..reply_analyzer import sync_recruiter_replies
    try:
        res = sync_recruiter_replies(db, current_user.id)
        return res
    except ValueError as ve:
        raise HTTPException(400, str(ve))
    except Exception as e:
        raise HTTPException(500, f"Reply synchronization failed: {str(e)}")

class AppCreate(BaseModel):
    title: str; company: str = ""; location: str = ""
    url: str = ""; match_score: int = 0; notes: str = ""
    status: str = "applied"; recruiter_email: str = ""

class AppUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None

def _serialize(a, emails=None):
    return {
        "id": a.id, "title": a.title, "company": a.company,
        "location": a.location, "url": a.url, "status": a.status,
        "notes": a.notes or "", "match_score": a.match_score,
        "applied_at": str(a.applied_at),
        "follow_up_date": str(a.follow_up_date) if a.follow_up_date else None,
        "tailored_cv_filename": a.tailored_cv_filename,
        "has_tailored_cv": bool(a.tailored_cv_data or a.tailored_cv_filename),
        "emails": emails or []
    }

@router.get("")
def get_all(db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user),
            search: Optional[str] = None):
    # 1. Real-time purge of blacklisted bounced applications
    bl_rows = db.query(models.EmailBlacklist.email).all()
    full_blacklist = {r[0].strip().lower() for r in bl_rows if r[0]}
    if full_blacklist:
        linked_log_ids = {
            r[0] for r in db.query(models.EmailLog.application_id).filter(
                models.EmailLog.application_id.isnot(None),
                models.EmailLog.to_email.in_(list(full_blacklist))
            ).all() if r[0]
        }
        all_user_apps = db.query(models.Application).filter(models.Application.user_id == current_user.id).all()
        purged = False
        for app in all_user_apps:
            notes_lower = (app.notes or "").lower()
            url_lower = (app.url or "").lower()
            comp_lower = (app.company or "").lower()
            is_dead = (app.id in linked_log_ids)
            if not is_dead:
                for b in full_blacklist:
                    b_domain = b.split('@')[-1] if '@' in b else ''
                    domain_slug = b_domain.split('.')[0] if b_domain else ''
                    if (b in notes_lower) or (b in url_lower) or (b_domain and b_domain in url_lower) or (domain_slug and len(domain_slug) > 3 and domain_slug in comp_lower):
                        is_dead = True
                        break
            if is_dead:
                db.query(models.EmailLog).filter(models.EmailLog.application_id == app.id).update(
                    {"application_id": None, "status": "bounced"},
                    synchronize_session=False
                )
                db.delete(app)
                purged = True
        if purged:
            db.commit()

    # 2. Real-time auto-reject: applications with follow-up sent >=3 days ago without recruiter response
    try:
        from ..auto_dispatcher import auto_reject_unresponsive_follow_ups
        auto_reject_unresponsive_follow_ups(db, current_user.id, days_threshold=3)
    except Exception as e:
        print(f"[Tracker] Error in auto_reject_unresponsive_follow_ups: {e}")

    query = db.query(models.Application).filter(models.Application.user_id == current_user.id)
    if search and search.strip():
        s = f"%{search.strip()}%"
        # Search by title, company, notes, or matching email in EmailLog
        matching_app_ids = db.query(models.EmailLog.application_id)\
                             .filter(models.EmailLog.user_id == current_user.id,
                                     models.EmailLog.to_email.ilike(s))\
                             .subquery()
        query = query.filter(
            models.Application.company.ilike(s) |
            models.Application.title.ilike(s) |
            models.Application.notes.ilike(s) |
            models.Application.id.in_(matching_app_ids)
        )
    apps = query.order_by(models.Application.applied_at.desc()).all()
    result = []
    for a in apps:
        logs = db.query(models.EmailLog) \
                 .filter(models.EmailLog.application_id == a.id) \
                 .order_by(models.EmailLog.sent_at.desc()).all()
        email_list = [{"id": l.id, "to_email": l.to_email, "to_name": l.to_name,
                       "subject": l.subject, "body": l.body,
                       "template_type": l.template_type,
                       "status": l.status, "sent_at": str(l.sent_at)} for l in logs]
        result.append(_serialize(a, email_list))
    return result

@router.post("")
def create_app(req: AppCreate, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    status = "applied" if req.status in ["applied", "sent"] else req.status
    
    # Check if this application already exists (especially in saved status)
    existing = db.query(models.Application).filter(
        models.Application.user_id == current_user.id,
        (models.Application.company.ilike(req.company) | (models.Application.url == (req.url or "nonexistent")))
    ).first()

    if existing:
        if status == "applied":
            existing.status = "applied"
            existing.applied_at = datetime.utcnow()
            if not existing.follow_up_date:
                existing.follow_up_date = datetime.utcnow() + timedelta(days=3)
        if req.notes:
            existing.notes = (existing.notes or "") + f"\n{req.notes}"
        if req.match_score:
            existing.match_score = req.match_score
        db.commit()
        db.refresh(existing)
        return _serialize(existing)

    a = models.Application(
        user_id=current_user.id, title=req.title, company=req.company,
        location=req.location, url=req.url, match_score=req.match_score,
        notes=req.notes, status=status)
    db.add(a); db.commit(); db.refresh(a)
    return _serialize(a)

@router.patch("/{app_id}")
def update_app(app_id: int, req: AppUpdate,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    a = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == current_user.id).first()
    if not a: raise HTTPException(404, "Not found")
    if req.status:
        st = "applied" if req.status == "sent" else req.status
        if st in VALID_STATUSES:
            a.status = st
            if st == "applied" and not a.applied_at:
                a.applied_at = datetime.utcnow()
    if req.notes is not None: a.notes = req.notes
    if req.follow_up_date:
        try: a.follow_up_date = datetime.fromisoformat(req.follow_up_date)
        except: pass
    db.commit()
    logs = db.query(models.EmailLog).filter(models.EmailLog.application_id == a.id).all()
    email_list = [{"id": l.id, "to_email": l.to_email, "subject": l.subject,
                   "status": l.status, "sent_at": str(l.sent_at)} for l in logs]
    return _serialize(a, email_list)

@router.delete("/clear-all")
def clear_all_applications(db: Session = Depends(get_db),
                           current_user: models.User = Depends(get_current_user)):
    """Delete all applications and email logs for the current user to allow re-applying."""
    db.query(models.EmailLog).filter(models.EmailLog.user_id == current_user.id).delete()
    db.query(models.Application).filter(models.Application.user_id == current_user.id).delete()
    db.commit()
    return {"message": "All applications and email logs successfully cleared"}

@router.delete("/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    a = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == current_user.id).first()
    if not a: raise HTTPException(404, "Not found")
    db.delete(a); db.commit()
    return {"message": "Deleted"}

@router.get("/stats")
def stats(db: Session = Depends(get_db),
          current_user: models.User = Depends(get_current_user)):
    rows = db.query(models.Application.status, func.count(models.Application.id)) \
             .filter(models.Application.user_id == current_user.id) \
             .group_by(models.Application.status).all()
    return {s: c for s, c in rows}

@router.get("/stats/detailed")
def stats_detailed(db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Returns pipeline counts + email count + response rate + weekly activity."""
    uid = current_user.id

    # Pipeline
    pipeline_rows = db.query(models.Application.status, func.count(models.Application.id)) \
        .filter(models.Application.user_id == uid) \
        .group_by(models.Application.status).all()
    pipeline = {s: c for s, c in pipeline_rows}

    total_apps   = sum(pipeline.values())
    offers       = pipeline.get("offer", 0) + pipeline.get("accepted", 0)
    interviews   = pipeline.get("interview", 0)
    response_rate = round((interviews + offers) / total_apps * 100) if total_apps else 0

    # Emails sent
    email_count = db.query(func.count(models.EmailLog.id)) \
        .filter(models.EmailLog.user_id == uid, models.EmailLog.status == "sent").scalar() or 0

    # Follow-ups due (today or overdue)
    today = date.today()
    follow_ups_due = db.query(models.Application) \
        .filter(models.Application.user_id == uid,
                models.Application.follow_up_date != None,
                func.date(models.Application.follow_up_date) <= str(today),
                models.Application.status.in_(["applied","interview"])) \
        .all()
    follow_ups = [_serialize(a) for a in follow_ups_due]

    # Recent emails (last 5)
    recent_emails = db.query(models.EmailLog) \
        .filter(models.EmailLog.user_id == uid) \
        .order_by(models.EmailLog.sent_at.desc()).limit(5).all()
    recent = [{"to_email": l.to_email, "subject": l.subject,
               "status": l.status, "sent_at": str(l.sent_at)} for l in recent_emails]

    # This week applications
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    this_week = db.query(func.count(models.Application.id)) \
        .filter(models.Application.user_id == uid,
                models.Application.applied_at >= week_ago).scalar() or 0

    return {
        "pipeline": pipeline,
        "total": total_apps,
        "interviews": interviews,
        "offers": offers,
        "response_rate": response_rate,
        "emails_sent": email_count,
        "follow_ups_due": follow_ups,
        "recent_emails": recent,
        "this_week": this_week,
    }

@router.get("/export")
def export_csv(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """Export all applications as CSV."""
    apps = db.query(models.Application) \
             .filter(models.Application.user_id == current_user.id) \
             .order_by(models.Application.applied_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title","Company","Location","Status","Match Score",
                     "Applied Date","Follow Up Date","Notes","URL"])
    for a in apps:
        writer.writerow([
            a.title, a.company, a.location, a.status, a.match_score,
            str(a.applied_at)[:10] if a.applied_at else "",
            str(a.follow_up_date)[:10] if a.follow_up_date else "",
            a.notes or "", a.url or ""
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"}
    )

@router.get("/{app_id}/thread")
def get_app_thread(app_id: int,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """
    Returns full details of sent emails and incoming recruiter responses
    for a specific application, ordered chronologically as a conversation thread.
    """
    app = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(404, "Application not found")

    from ..reply_analyzer import extract_portal_url, extract_meeting_link

    # 1. Emails from EmailLog (both Outbound and Full Inbound Recruiter Replies)
    logs = db.query(models.EmailLog).filter(
        models.EmailLog.application_id == app.id
    ).order_by(models.EmailLog.sent_at.asc()).all()

    email_thread_items = []
    has_inbound_in_logs = False

    for l in logs:
        if l.template_type == "recruiter_reply":
            has_inbound_in_logs = True
            portal_url = extract_portal_url(l.body, app.url) if l.body else app.url
            meet_url = extract_meeting_link(l.body or "") or extract_meeting_link(l.subject or "")
            email_thread_items.append({
                "id": l.id,
                "direction": "inbound",
                "to_email": l.to_email,
                "from_header": l.to_name or l.to_email,
                "subject": l.subject,
                "body": l.body or "",
                "status_outcome": l.status or app.status,
                "portal_link": portal_url,
                "meet_link": meet_url,
                "template_type": l.template_type,
                "sent_at": str(l.sent_at),
                "timestamp": str(l.sent_at)
            })
        else:
            email_thread_items.append({
                "id": l.id,
                "direction": "outbound",
                "to_email": l.to_email,
                "to_name": l.to_name or "Hiring Team",
                "subject": l.subject,
                "body": l.body or "",
                "status": l.status,
                "template_type": l.template_type,
                "sent_at": str(l.sent_at),
                "timestamp": str(l.sent_at)
            })

    # 2. Extract received replies from app.notes (fallback only if not already recorded with full text in EmailLog)
    notes_inbound_items = []
    if not has_inbound_in_logs:
        note_lines = (app.notes or "").split("\n")
        for line in note_lines:
            line = line.strip()
            if not line:
                continue
            m_ts = re.search(r'\[([^\]]+)\]\s*📥\s*Recruiter Reply:\s*(.+)', line, re.I)
            if m_ts:
                ts = m_ts.group(1).strip()
                rest = m_ts.group(2).strip()
                status_m = re.search(r"Status\s*->\s*'([^']+)'", rest)
                portal_m = re.search(r'Portal\s*\/\s*Position\s*Link:\s*([^\s,]+)', rest) or re.search(r'Portal\s*\/\s*Position\s*Link:\s*([^\.]+)\.', rest)
                meet_m = re.search(r'Google Meet Link:\s*(https?://[^\s,]+)', rest) or re.search(r'(https?://meet\.google\.com/[^\s<>"\'\)]+)', rest)
                quote_m = re.search(r'\"([^\"]+)\"$', rest)
                body_txt = quote_m.group(1).strip() if quote_m else rest
                from_m = re.search(r'From:\s*(.+?)\.\s*\"', rest)
                from_h = from_m.group(1).strip() if from_m else "Recruiter"

                notes_inbound_items.append({
                    "direction": "inbound",
                    "timestamp": ts,
                    "status_outcome": status_m.group(1) if status_m else app.status,
                    "portal_link": portal_m.group(1).rstrip('.,;:') if portal_m else None,
                    "meet_link": meet_m.group(1).rstrip('.,;:') if meet_m else None,
                    "from_header": from_h,
                    "body": body_txt,
                    "subject": f"Re: Application for {app.title}"
                })

    # Combine all items into a chronological thread
    thread = sorted(email_thread_items + notes_inbound_items, key=lambda x: x.get("timestamp", ""))

    portal_url = extract_portal_url(app.notes, app.url) if app.notes else app.url
    meet_url = extract_meeting_link(app.notes or "")

    discovered_emails = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', app.notes or "")

    return {
        "application": {
            "id": app.id,
            "title": app.title,
            "company": app.company,
            "location": app.location,
            "url": app.url,
            "status": app.status,
            "notes": app.notes,
            "match_score": app.match_score,
            "applied_at": str(app.applied_at),
            "follow_up_date": str(app.follow_up_date) if app.follow_up_date else None,
            "tailored_cv_filename": app.tailored_cv_filename,
            "has_tailored_cv": bool(app.tailored_cv_data or app.tailored_cv_filename),
            "portal_url": portal_url,
            "meet_url": meet_url,
            "discovered_emails": list(dict.fromkeys(discovered_emails))
        },
        "thread": thread,
        "sent_count": len([m for m in thread if m.get("direction") == "outbound"]),
        "received_count": len([m for m in thread if m.get("direction") == "inbound"])
    }

@router.get("/{app_id}/cv")
def download_app_cv(app_id: int,
                    token: Optional[str] = None,
                    db: Session = Depends(get_db)):
    """Downloads the tailored CV PDF binary stored for an application."""
    user = None
    if token:
        from ..auth import jwt, SECRET_KEY, ALGORITHM
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_email = payload.get("sub")
            user = db.query(models.User).filter(models.User.email == user_email).first()
        except Exception:
            pass

    if not user:
        raise HTTPException(401, "Unauthorized")

    app = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == user.id
    ).first()
    if not app or not app.tailored_cv_data:
        raise HTTPException(404, "Tailored CV not found")

    filename = app.tailored_cv_filename or f"CV_{app.company.replace(' ', '_')}.pdf"
    return StreamingResponse(
        io.BytesIO(bytes(app.tailored_cv_data)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
