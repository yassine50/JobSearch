"""
auto_dispatcher.py
Automated queue & follow-up dispatcher:
1. Auto Follow-Up: scans applications waiting >3 days with no recruiter reply,
   and dispatches polite follow-up emails with resume re-attached.
2. Queue Dispatcher: scans saved applications (queued jobs with tailored CVs),
   validates DNS MX and blacklist, and dispatches them to recruiters,
   handling daily Gmail SMTP quota gracefully.
"""
import re, time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from . import models
from .bounce_cleaner import get_blacklisted_emails

def has_valid_mx(domain: str) -> bool:
    try:
        import dns.resolver
        records = dns.resolver.resolve(domain, 'MX')
        return len(records) > 0
    except Exception:
        return False

def auto_dispatch_follow_ups(db: Session, user_id: int, days_threshold: int = 3) -> Dict[str, Any]:
    from .routers.email import get_follow_up_candidates, send_follow_up, FollowUpSendRequest
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {"sent_count": 0, "errors": ["User not found"]}

    candidates = get_follow_up_candidates(days=days_threshold, db=db, current_user=user)
    sent_count = 0
    errors = []
    quota_reached = False

    for c in candidates:
        try:
            send_follow_up(
                FollowUpSendRequest(
                    application_id=c["application_id"],
                    attach_cv=True
                ),
                db=db,
                current_user=user
            )
            sent_count += 1
            time.sleep(0.5)
        except Exception as e:
            err_str = str(e)
            if "5.4.5" in err_str or "Daily user sending limit exceeded" in err_str:
                quota_reached = True
                errors.append(f"Gmail daily sending quota limit reached: {err_str}")
                break
            errors.append(f"App {c['application_id']} ({c['company']}): {err_str}")

    return {
        "sent_count": sent_count,
        "eligible_count": len(candidates),
        "quota_reached": quota_reached,
        "errors": errors
    }

def extract_recipients_from_notes(notes: str, company: str) -> List[Dict[str, str]]:
    recipients = []
    seen = set()
    matches_with_name = re.findall(r'([A-Za-z\s\.\'-]+)\s*\(([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\)', notes or '')
    for name, email in matches_with_name:
        clean_name = name.strip(' ,:\n\t')
        clean_email = email.strip().lower()
        if clean_email not in seen and '@' in clean_email:
            seen.add(clean_email)
            recipients.append({'name': clean_name or f'Hiring Team at {company}', 'email': clean_email})

    standalone = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', notes or '')
    for email in standalone:
        clean_email = email.strip().lower()
        if clean_email not in seen:
            seen.add(clean_email)
            recipients.append({'name': f'Hiring Team at {company}', 'email': clean_email})

    return recipients

def dispatch_saved_applications(db: Session, user_id: int) -> Dict[str, Any]:
    from .routers.email import _dispatch_smtp
    user = db.query(models.User).filter(models.User.id == user_id).first()
    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == user_id).first()
    if not user or not settings or not settings.smtp_user:
        return {"sent_count": 0, "remaining_saved": 0, "quota_reached": False, "error": "Email settings not configured"}

    blacklisted = get_blacklisted_emails(db)
    saved_apps = db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.status == 'saved'
    ).order_by(models.Application.id.asc()).all()

    if not saved_apps:
        return {"sent_count": 0, "remaining_saved": 0, "quota_reached": False}

    sent_count = 0
    quota_reached = False
    errors = []
    sender_name = settings.sender_name or user.name

    for app in saved_apps:
        # Extract recruiter recipients
        all_recips = extract_recipients_from_notes(app.notes, app.company)

        # Filter deliverable recipients (valid MX, not blacklisted, not noreply)
        valid_recips = []
        for r in all_recips:
            em = r["email"].strip().lower()
            if em in blacklisted:
                continue
            if any(p in em for p in ["noreply", "no-reply", "donotreply"]):
                continue
            domain = em.split('@')[-1]
            if not has_valid_mx(domain):
                print(f"[AutoDispatcher] Skipping invalid MX domain {domain} for {em}")
                continue
            valid_recips.append(r)

        if not valid_recips:
            print(f"[AutoDispatcher] No deliverable MX recipient for saved App #{app.id} ({app.company})")
            continue

        subject = f"Application for {app.title} — {sender_name}"
        # Automated dispatch strictly uses authentic original CV (not tailored)
        custom_pdf_bytes = None
        custom_pdf_name = None

        app_dispatched_emails = []
        try:
            for r in valid_recips:
                r_name = r["name"]
                body = f"""Dear {r_name} at {app.company},

I am writing to express my strong interest in the {app.title} position.

With strong technical experience and proven expertise, I specialize in building high-performance applications and clean, reliable software solutions. Having reviewed your role, I believe my background and technical skills make me an excellent candidate for your team.

I have attached my resume for your review, detailing my accomplishments, technical stack, and shipped projects.

I would welcome the opportunity to discuss how I can contribute to {app.company}. Thank you for your time and consideration.

Best regards,
{sender_name}
{user.email}"""

                _dispatch_smtp(
                    settings, user, r["email"], r_name, subject, body,
                    attach_cv=True, db=db,
                    custom_attachment_bytes=custom_pdf_bytes,
                    custom_attachment_name=custom_pdf_name
                )

                log = models.EmailLog(
                    user_id=user.id,
                    application_id=app.id,
                    to_email=r["email"],
                    to_name=r_name,
                    subject=subject,
                    body=body,
                    template_type="auto_apply",
                    status="sent"
                )
                db.add(log)
                app_dispatched_emails.append(r["email"])
                time.sleep(0.5)

            # Move application to applied
            now = datetime.utcnow()
            app.status = "applied"
            app.applied_at = now
            app.follow_up_date = now + timedelta(days=3)
            ts_str = now.strftime('%Y-%m-%d %H:%M')
            app.notes = (app.notes or "") + f"\n[{ts_str}] 📤 Dispatched from queue to {', '.join(app_dispatched_emails)} (Original CV)"
            db.commit()
            sent_count += 1
            print(f"[AutoDispatcher] Successfully dispatched saved App #{app.id} ({app.company}) to {app_dispatched_emails}")

        except Exception as e:
            err_str = str(e)
            print(f"[AutoDispatcher] Error dispatching saved App #{app.id}: {err_str}")
            db.rollback()
            if "5.4.5" in err_str or "Daily user sending limit exceeded" in err_str:
                quota_reached = True
                errors.append("Gmail SMTP daily user sending limit exceeded")
                break
            else:
                errors.append(f"App {app.id} ({app.company}): {err_str}")

    remaining_saved = db.query(models.Application).filter(
        models.Application.user_id == user_id,
        models.Application.status == 'saved'
    ).count()

    return {
        "sent_count": sent_count,
        "remaining_saved": remaining_saved,
        "quota_reached": quota_reached,
        "errors": errors
    }

def auto_reject_unresponsive_follow_ups(db: Session, user_id: int = None, days_threshold: int = 3) -> Dict[str, Any]:
    """
    Scans applications where a follow-up email was sent. If >= days_threshold (default 3 days)
    have elapsed with no recruiter response, automatically moves the application status
    directly to 'rejected'.
    """
    query = db.query(models.Application).filter(
        models.Application.status.in_(["applied", "sent"])
    )
    if user_id is not None:
        query = query.filter(models.Application.user_id == user_id)

    apps = query.all()
    if not apps:
        return {"checked": 0, "auto_rejected": 0, "applications": []}

    from collections import defaultdict
    app_ids = [a.id for a in apps]
    all_logs = (
        db.query(models.EmailLog)
        .filter(models.EmailLog.application_id.in_(app_ids))
        .order_by(models.EmailLog.sent_at.desc())
        .all()
    )
    logs_by_app = defaultdict(list)
    for l in all_logs:
        logs_by_app[l.application_id].append(l)

    now = datetime.utcnow()
    rejected_apps = []

    for app in apps:
        app_logs = logs_by_app.get(app.id, [])
        followup_logs = [
            l for l in app_logs
            if l.template_type == "follow_up" and l.status != "bounced"
        ]

        last_followup_time = None
        if followup_logs and followup_logs[0].sent_at:
            last_followup_time = followup_logs[0].sent_at
        elif app.notes and "📤 Sent Follow-up" in app.notes:
            matches = re.findall(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+📤 Sent Follow-up', app.notes)
            if matches:
                try:
                    last_followup_time = datetime.strptime(matches[-1], '%Y-%m-%d %H:%M')
                except Exception:
                    pass

        if not last_followup_time:
            continue

        # Check if >= days_threshold (3 days / 72 hours) have elapsed since the follow-up
        elapsed = now - last_followup_time
        if elapsed.total_seconds() < days_threshold * 86400:
            continue

        # Check if recruiter has responded since that follow-up
        has_reply_since_followup = False
        if app.notes and "📥 Recruiter Reply:" in app.notes:
            reply_matches = re.findall(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+📥 Recruiter Reply:', app.notes)
            for rm in reply_matches:
                try:
                    reply_dt = datetime.strptime(rm, '%Y-%m-%d %H:%M')
                    if reply_dt >= last_followup_time:
                        has_reply_since_followup = True
                        break
                except Exception:
                    pass

        if has_reply_since_followup:
            continue

        # Any genuine recruiter reply (not out-of-office) means the application is alive
        recruiter_log_reply = any(
            l.template_type in ("recruiter_reply", "incoming") and l.status not in ("auto_reply", "ignore")
            for l in app_logs
        )
        if recruiter_log_reply:
            continue

        # Automatically transition to 'rejected'
        app.status = "rejected"
        timestamp_str = now.strftime('%Y-%m-%d %H:%M')
        app.notes = (app.notes or "") + f"\n[{timestamp_str}] ⏱️ Auto-Closed: No recruiter response {days_threshold} days after follow-up -> Marked as Rejected"
        rejected_apps.append({
            "id": app.id,
            "title": app.title,
            "company": app.company,
            "last_follow_up": str(last_followup_time),
            "days_elapsed": round(elapsed.total_seconds() / 86400, 1)
        })
        print(f"[AutoReject] Application #{app.id} ({app.title} at {app.company}) auto-rejected: 3 days after follow-up with no response.")

    if rejected_apps:
        db.commit()

    return {
        "auto_rejected_count": len(rejected_apps),
        "rejected_applications": rejected_apps
    }
