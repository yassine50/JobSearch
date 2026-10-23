
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
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
            "breakdown": reply_res.get("breakdown") or {},
            "restored": reply_res.get("restored_applications") or 0,
            "reclassified": reply_res.get("reclassified") or 0,
            "relevant_messages": reply_res.get("relevant_messages") or 0,
            "reply_error": reply_res.get("error"),
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

_LAST_TRACKER_MAINT: dict[int, float] = {}

def _serialize(a, emails=None):
    return {
        "id": a.id, "title": a.title, "company": a.company,
        "location": a.location, "url": a.url, "status": a.status,
        "notes": a.notes or "", "match_score": a.match_score,
        "applied_at": str(a.applied_at),
        "follow_up_date": str(a.follow_up_date) if a.follow_up_date else None,
        "tailored_cv_filename": a.tailored_cv_filename,
        "has_tailored_cv": bool(a.tailored_cv_filename),
        "emails": emails or []
    }

@router.get("")
def get_all(db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user),
            search: Optional[str] = None):
    import time as _time
    from collections import defaultdict

    now_ts = _time.monotonic()
    if now_ts - _LAST_TRACKER_MAINT.get(current_user.id, 0.0) > 300.0:
        _LAST_TRACKER_MAINT[current_user.id] = now_ts
        try:
            from ..utils import purge_blacklisted_applications
            purge_blacklisted_applications(db, user_id=current_user.id)
            from ..auto_dispatcher import auto_reject_unresponsive_follow_ups
            auto_reject_unresponsive_follow_ups(db, current_user.id, days_threshold=3)
        except Exception as e:
            print(f"[Tracker] Error in periodic tracker maintenance: {e}")

    query = db.query(models.Application).filter(models.Application.user_id == current_user.id)
    if search and search.strip():
        s = f"%{search.strip()}%"
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
    if not apps:
        return []

    app_ids = [a.id for a in apps]
    all_logs = (
        db.query(models.EmailLog)
        .filter(models.EmailLog.application_id.in_(app_ids))
        .order_by(models.EmailLog.sent_at.desc())
        .all()
    )
    logs_by_app = defaultdict(list)
    for l in all_logs:
        logs_by_app[l.application_id].append({
            "id": l.id,
            "to_email": l.to_email,
            "to_name": l.to_name,
            "subject": l.subject,
            "body": l.body,
            "template_type": l.template_type,
            "status": l.status,
            "sent_at": str(l.sent_at),
        })

    return [_serialize(a, logs_by_app.get(a.id, [])) for a in apps]

@router.post("")
def create_app(req: AppCreate, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    status = "applied" if req.status in ["applied", "sent"] else req.status
    
    # Check if this application already exists (by exact URL or by company + title)
    existing = None
    if req.url and req.url.strip():
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.url == req.url.strip()
        ).first()
    if not existing and req.company and req.company.strip() and req.title and req.title.strip():
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.company.ilike(req.company.strip()),
            models.Application.title.ilike(req.title.strip())
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

def _sanitize_csv_cell(val: Optional[str]) -> str:
    """
    Sanitize CSV cell values: flatten newlines/control chars and neutralize
    spreadsheet formula-injection prefixes (ported from ai-job-search gmail-sync.md).
    """
    if val is None:
        return ""
    s = re.sub(r"[\r\n\t]+", " · ", str(val)).strip()
    if s and s[0] in ("=", "+", "-", "@"):
        s = "'" + s
    return s


@router.get("/export")
def export_csv(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """Export all applications as CSV."""
    apps = db.query(models.Application) \
             .filter(models.Application.user_id == current_user.id) \
             .order_by(models.Application.applied_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Company", "Location", "Status", "Match Score",
                     "Applied Date", "Follow Up Date", "Notes", "URL"])
    for a in apps:
        writer.writerow([
            _sanitize_csv_cell(a.title),
            _sanitize_csv_cell(a.company),
            _sanitize_csv_cell(a.location),
            _sanitize_csv_cell(a.status),
            a.match_score or 0,
            str(a.applied_at)[:10] if a.applied_at else "",
            str(a.follow_up_date)[:10] if a.follow_up_date else "",
            _sanitize_csv_cell(a.notes or ""),
            _sanitize_csv_cell(a.url or ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"}
    )


@router.get("/export-html")
def export_html_report(db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    """
    Generate a 100% self-contained, offline-capable HTML Analytics Dashboard
    with inline SVG Doughnut + Historical Stage Funnel charts and interactive filter table
    (ported from ai-job-search .claude/commands/html-report.md).
    """
    import html as _html
    import math

    apps = (
        db.query(models.Application)
        .filter(models.Application.user_id == current_user.id)
        .order_by(models.Application.applied_at.desc())
        .all()
    )

    status_counts = {
        "applied": 0, "review": 0, "interview": 0,
        "offer": 0, "accepted": 0, "rejected": 0, "saved": 0,
    }

    # Historical stage progression counters (funnel)
    reached_applied = 0
    reached_review = 0
    reached_interview = 0
    reached_offer = 0

    for a in apps:
        st = (a.status or "applied").lower()
        if st == "sent":
            st = "applied"
        status_counts[st] = status_counts.get(st, 0) + 1
        notes_low = (a.notes or "").lower()

        if st != "saved":
            reached_applied += 1
            if st in ("review", "interview", "offer", "accepted") or "status -> 'review'" in notes_low or "status -> 'interview'" in notes_low or "recruiter reply:" in notes_low:
                reached_review += 1
            if st in ("interview", "offer", "accepted") or "status -> 'interview'" in notes_low or "meet.google.com" in notes_low or "zoom.us" in notes_low:
                reached_interview += 1
            if st in ("offer", "accepted") or "status -> 'offer'" in notes_low:
                reached_offer += 1

    total_tracked = len(apps)
    submitted = max(reached_applied, 1)
    resolved = status_counts["rejected"] + status_counts["offer"] + status_counts["accepted"]
    resolution_rate = round((resolved / submitted) * 100, 1) if reached_applied else 0.0
    true_rejection_rate = round((status_counts["rejected"] / resolved) * 100, 1) if resolved else 0.0
    interview_rate = round((reached_interview / submitted) * 100, 1) if reached_applied else 0.0

    # Build SVG Doughnut segments (r=60, circumference = 2*pi*60 = 376.99)
    circ = 2 * math.pi * 60
    palette = [
        ("applied", "Applied", "#3b82f6"),
        ("review", "Under Review", "#f59e0b"),
        ("interview", "Interview", "#a855f7"),
        ("offer", "Offer", "#10b981"),
        ("accepted", "Accepted", "#eab308"),
        ("rejected", "Rejected", "#f43f5e"),
        ("saved", "Saved", "#64748b"),
    ]
    offset = 0.0
    doughnut_circles = []
    legend_items = []
    denom = max(total_tracked, 1)
    for key, label, color in palette:
        cnt = status_counts.get(key, 0)
        if cnt <= 0:
            continue
        seg = (cnt / denom) * circ
        doughnut_circles.append(
            f'<circle cx="80" cy="80" r="60" fill="transparent" stroke="{color}" '
            f'stroke-width="20" stroke-dasharray="{seg:.2f} {circ - seg:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 80 80)" />'
        )
        offset += seg
        pct = round((cnt / denom) * 100, 1)
        legend_items.append(
            f'<div class="leg-item"><span class="dot" style="background:{color}"></span>'
            f'<span>{_html.escape(label)}: <strong>{cnt}</strong> ({pct}%)</span></div>'
        )
    if not doughnut_circles:
        doughnut_circles.append('<circle cx="80" cy="80" r="60" fill="transparent" stroke="#cbd5e1" stroke-width="20" />')

    # Funnel bars
    funnel_stages = [
        ("Submitted / Applied", reached_applied, "#3b82f6"),
        ("Reached Review / Reply", reached_review, "#f59e0b"),
        ("Reached Interview", reached_interview, "#a855f7"),
        ("Reached Offer / Accepted", reached_offer, "#10b981"),
    ]
    funnel_html = []
    for label, val, color in funnel_stages:
        pct = round((val / submitted) * 100, 1) if reached_applied else 0.0
        w = max(pct, 3.0) if val > 0 else 0.0
        funnel_html.append(
            f'<div class="funnel-row">'
            f'<div class="funnel-meta"><span>{_html.escape(label)}</span><strong>{val} ({pct}%)</strong></div>'
            f'<div class="funnel-track"><div class="funnel-fill" style="width:{w}%;background:{color}"></div></div>'
            f'</div>'
        )

    # Table rows (strictly HTML-escaped per html-report.md security rule)
    rows_html = []
    for idx, a in enumerate(apps, 1):
        st = (a.status or "applied").lower()
        if st == "sent":
            st = "applied"
        dt_str = str(a.applied_at)[:10] if a.applied_at else "—"
        fu_str = str(a.follow_up_date)[:10] if a.follow_up_date else "—"
        url_raw = (a.url or "").strip()
        url_cell = (
            f'<a href="{_html.escape(url_raw, quote=True)}" target="_blank" rel="noopener">Open ↗</a>'
            if url_raw.startswith(("http://", "https://"))
            else "—"
        )
        notes_clean = _html.escape(re.sub(r"\s+", " ", (a.notes or "")).strip()[:240])
        rows_html.append(
            f'<tr data-status="{_html.escape(st, quote=True)}">'
            f'<td>{idx}</td>'
            f'<td><strong>{_html.escape(a.company or "—")}</strong></td>'
            f'<td>{_html.escape(a.title or "—")}</td>'
            f'<td>{_html.escape(a.location or "—")}</td>'
            f'<td><span class="badge st-{_html.escape(st, quote=True)}">{_html.escape(st.upper())}</span></td>'
            f'<td>{a.match_score or 0}%</td>'
            f'<td>{_html.escape(dt_str)}</td>'
            f'<td>{_html.escape(fu_str)}</td>'
            f'<td class="notes-cell">{notes_clean}</td>'
            f'<td>{url_cell}</td>'
            f'</tr>'
        )

    gen_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    user_label = _html.escape(current_user.name or current_user.email or "Candidate")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Job Application Tracker Report — {user_label}</title>
<style>
  :root {{
    --bg: #0b1120; --card: #111827; --border: #1e293b;
    --text: #f8fafc; --muted: #94a3b8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 24px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
  }}
  .container {{ max-width: 1240px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }}
  h1 {{ margin: 0; font-size: 24px; font-weight: 800; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-bottom: 24px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px; }}
  .kpi-val {{ font-size: 26px; font-weight: 800; }}
  .kpi-lbl {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 18px; padding: 20px; }}
  .card h2 {{ margin: 0 0 14px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
  .doughnut-wrap {{ display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }}
  .leg-item {{ display: flex; align-items: center; gap: 8px; font-size: 13px; margin-bottom: 6px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .funnel-row {{ margin-bottom: 12px; }}
  .funnel-meta {{ display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 5px; }}
  .funnel-track {{ height: 10px; background: #1e293b; border-radius: 999px; overflow: hidden; }}
  .funnel-fill {{ height: 100%; border-radius: 999px; }}
  .controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }}
  .btn {{ background: #1e293b; color: #e2e8f0; border: 1px solid #334155; padding: 7px 13px; border-radius: 10px; font-size: 12px; font-weight: 600; cursor: pointer; }}
  .btn.active {{ background: #2563eb; border-color: #3b82f6; color: #fff; }}
  .search {{ background: #0f172a; border: 1px solid #334155; color: #fff; padding: 7px 12px; border-radius: 10px; font-size: 12px; min-width: 220px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em; }}
  .notes-cell {{ max-width: 320px; color: #cbd5e1; font-size: 11.5px; }}
  .badge {{ padding: 3px 8px; border-radius: 6px; font-size: 10.5px; font-weight: 700; }}
  .st-applied {{ background: rgba(59,130,246,0.2); color: #93c5fd; }}
  .st-review {{ background: rgba(245,158,11,0.2); color: #fcd34d; }}
  .st-interview {{ background: rgba(168,85,247,0.2); color: #d8b4fe; }}
  .st-offer, .st-accepted {{ background: rgba(16,185,129,0.2); color: #6ee7b7; }}
  .st-rejected {{ background: rgba(244,63,94,0.2); color: #fda4af; }}
  a {{ color: #60a5fa; text-decoration: none; font-weight: 600; }}
  @media print {{ body {{ background: #fff; color: #000; }} .controls {{ display: none; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Job Application Analytics Report</h1>
      <div class="sub">Prepared for {user_label} · Generated {gen_date}</div>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-val">{total_tracked}</div><div class="kpi-lbl">Total Tracked Roles</div></div>
    <div class="kpi"><div class="kpi-val">{reached_applied}</div><div class="kpi-lbl">Applications Submitted</div></div>
    <div class="kpi"><div class="kpi-val" style="color:#c084fc">{reached_interview} ({interview_rate}%)</div><div class="kpi-lbl">Reached Interview Stage</div></div>
    <div class="kpi"><div class="kpi-val" style="color:#34d399">{reached_offer}</div><div class="kpi-lbl">Offers / Accepted</div></div>
    <div class="kpi"><div class="kpi-val">{resolution_rate}%</div><div class="kpi-lbl">Resolution Rate ({resolved}/{reached_applied})</div></div>
    <div class="kpi"><div class="kpi-val" style="color:#fb7185">{true_rejection_rate}%</div><div class="kpi-lbl">True Rejection Rate (of Resolved)</div></div>
  </div>

  <div class="charts-grid">
    <div class="card">
      <h2>Status Breakdown</h2>
      <div class="doughnut-wrap">
        <svg width="160" height="160" viewBox="0 0 160 160">
          {''.join(doughnut_circles)}
          <text x="80" y="85" text-anchor="middle" fill="#f8fafc" font-size="20" font-weight="800">{total_tracked}</text>
        </svg>
        <div>{''.join(legend_items)}</div>
      </div>
    </div>
    <div class="card">
      <h2>Historical Stage Progression Funnel</h2>
      {''.join(funnel_html)}
    </div>
  </div>

  <div class="card">
    <h2>Applications Directory</h2>
    <div class="controls">
      <button class="btn active" onclick="filterRows('all', this)">All ({total_tracked})</button>
      <button class="btn" onclick="filterRows('applied', this)">Applied ({status_counts['applied']})</button>
      <button class="btn" onclick="filterRows('review', this)">Under Review ({status_counts['review']})</button>
      <button class="btn" onclick="filterRows('interview', this)">Interview ({status_counts['interview']})</button>
      <button class="btn" onclick="filterRows('offer', this)">Offer ({status_counts['offer'] + status_counts['accepted']})</button>
      <button class="btn" onclick="filterRows('rejected', this)">Rejected ({status_counts['rejected']})</button>
      <input id="q" class="search" placeholder="Filter by company, role, notes..." oninput="applySearch()" />
    </div>
    <div style="overflow-x:auto">
      <table id="appTable">
        <thead>
          <tr><th>#</th><th>Company</th><th>Role</th><th>Location</th><th>Status</th><th>Fit</th><th>Applied</th><th>Follow-Up</th><th>Notes</th><th>Link</th></tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>
  </div>
</div>
<script>
  let currentStatus = 'all';
  function filterRows(st, btn) {{
    currentStatus = st;
    document.querySelectorAll('.controls .btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    applySearch();
  }}
  function applySearch() {{
    const q = (document.getElementById('q').value || '').toLowerCase();
    document.querySelectorAll('#appTable tbody tr').forEach(tr => {{
      const st = tr.getAttribute('data-status');
      const statusOk = currentStatus === 'all' || st === currentStatus || (currentStatus === 'offer' && st === 'accepted');
      const textOk = !q || tr.innerText.toLowerCase().includes(q);
      tr.style.display = (statusOk && textOk) ? '' : 'none';
    }});
  }}
</script>
</body>
</html>"""

    return StreamingResponse(
        iter([doc]),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=applications_report.html"},
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
                    request: Request,
                    token: Optional[str] = None,
                    db: Session = Depends(get_db)):
    """Downloads the tailored CV PDF binary stored for an application."""
    user = None
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()
    if raw_token:
        from ..auth import jwt, SECRET_KEY, ALGORITHM
        try:
            payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
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
