
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import smtplib, time, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..email_templates import get_application_email, get_followup_email, detect_language

router = APIRouter(prefix="/api/email", tags=["email"])

TEMPLATES = {
    "application": {
        "subject": "Application for {job_title} — {sender_name}",
        "body": """Dear {to_name},

I am writing to express my strong interest in the {job_title} position at {company}.

Having reviewed the role carefully, I believe my background and skills make me an excellent candidate for this opportunity.

I would welcome the chance to discuss how I can contribute to your team. Please find my details and attached resume below.

Thank you for your time and consideration.

Best regards,
{sender_name}
{sender_email}"""
    },
    "cold_outreach": {
        "subject": "Exploring Opportunities — {job_title} | {sender_name}",
        "body": """Dear {to_name},

I hope this message finds you well. I came across your profile and was impressed by the work being done at {company}.

I am currently exploring new opportunities in {job_title} and would love to connect. I bring strong expertise in my field and am eager to contribute to a forward-thinking team.

Would you be open to a brief conversation? I would be happy to share more about my background.

Thank you for your time.

Best regards,
{sender_name}
{sender_email}"""
    },
    "follow_up": {
        "subject": "Following Up — {job_title} Application | {sender_name}",
        "body": """Dear {to_name},

I wanted to follow up on my application for the {job_title} position at {company}.

I remain very enthusiastic about this opportunity and would love to learn about the next steps in your process.

Please let me know if you need any additional information from me.

Thank you for your consideration.

Best regards,
{sender_name}
{sender_email}"""
    },
    "thank_you": {
        "subject": "Thank You — {job_title} Interview | {sender_name}",
        "body": """Dear {to_name},

Thank you so much for taking the time to speak with me about the {job_title} position at {company}.

Our conversation reinforced my enthusiasm for this opportunity, and I am confident that my skills would be a great match.

I look forward to hearing about the next steps.

With gratitude,
{sender_name}
{sender_email}"""
    },
    "cover_letter": {
        "subject": "Cover Letter — {job_title} | {sender_name}",
        "body": ""
    },
}

class TemplateRequest(BaseModel):
    template_type: str
    to_name: str = "Hiring Team"
    company: str = ""
    job_title: str = ""
    lang: Optional[str] = None
    job_description: Optional[str] = ""
    site: Optional[str] = None
    url: Optional[str] = None

class SendEmailRequest(BaseModel):
    to_email: str
    to_name: str = "Hiring Team"
    subject: str
    body: str
    template_type: str = "custom"
    application_id: Optional[int] = None   # link to tracker card
    attach_cv: bool = True
    job_title: Optional[str] = ""
    company: Optional[str] = ""
    job_description: Optional[str] = ""
    customize_cv: Optional[bool] = False

class RecipientItem(BaseModel):
    email: str
    name: Optional[str] = "Hiring Team"
    title: Optional[str] = ""

class AutoApplyRequest(BaseModel):
    job_title: str
    company: str
    to_email: Optional[str] = ""
    to_name: Optional[str] = "Hiring Team"
    recipients: Optional[List[RecipientItem]] = None
    job_url: Optional[str] = ""
    location: Optional[str] = ""
    match_score: Optional[int] = 0
    notes: Optional[str] = ""
    job_description: Optional[str] = ""
    customize_cv: Optional[bool] = True    # honest per-job tailoring (re-order only)
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None
    lang: Optional[str] = None
    site: Optional[str] = None

class BatchAutoApplyRequest(BaseModel):
    jobs: List[AutoApplyRequest]
    delay_seconds: float = 1.0
    customize_cv: Optional[bool] = True

class SettingsRequest(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    sender_name: str

def _dispatch_smtp(settings, current_user, to_email, to_name, subject, body, attach_cv, db,
                   custom_attachment_bytes: Optional[bytes] = None,
                   custom_attachment_name: Optional[str] = None):
    """Low-level robust SMTP sender with UTF-8 headers and CV attachment."""
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Email not configured. Go to Settings → Email Setup.")
    clean_pwd = ''.join(settings.smtp_password.split())

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    sender_display = settings.sender_name or current_user.name
    msg["From"]    = f"{Header(sender_display, 'utf-8')} <{settings.smtp_user}>"
    recipient_name = to_name or "Hiring Team"
    msg["To"]      = f"{Header(recipient_name, 'utf-8')} <{to_email}>"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attach_cv:
        if custom_attachment_bytes and custom_attachment_name:
            part = MIMEApplication(custom_attachment_bytes, Name=custom_attachment_name)
            part.add_header('Content-Disposition', 'attachment', filename=custom_attachment_name)
            msg.attach(part)
        else:
            cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
            if cv and cv.file_data:
                part = MIMEApplication(bytes(cv.file_data), Name=cv.filename or "Resume.pdf")
                part.add_header('Content-Disposition', 'attachment', filename=cv.filename or "Resume.pdf")
                msg.attach(part)
            elif cv and cv.text_content:
                part = MIMEApplication(cv.text_content.encode("utf-8"), Name="Resume.txt")
                part.add_header('Content-Disposition', 'attachment', filename="Resume.txt")
                msg.attach(part)

    if getattr(settings, "auth_method", "smtp") == "gmail_oauth":
        from ..gmail_oauth import send_raw_via_gmail
        send_raw_via_gmail(settings.gmail_refresh_token, msg.as_bytes())
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(settings.smtp_user, clean_pwd)
        s.sendmail(settings.smtp_user, to_email, msg.as_string())

@router.post("/template")
def get_template(req: TemplateRequest,
                 current_user: models.User = Depends(get_current_user)):
    target_lang = req.lang
    if not target_lang and req.job_description:
        target_lang = detect_language(f"{req.job_title} {req.company} {req.job_description}")

    if req.template_type == "application":
        subj, body, _ = get_application_email(
            role_title=req.job_title,
            company=req.company,
            recruiter_name=req.to_name,
            post_text=req.job_description,
            sender_name=current_user.name,
            sender_email=current_user.email,
            lang=target_lang,
            site=req.site,
            url=req.url
        )
        return {"subject": subj, "body": body}

    if req.template_type == "follow_up":
        subj, body, _ = get_followup_email(
            role_title=req.job_title,
            company=req.company,
            recruiter_name=req.to_name,
            sender_name=current_user.name,
            sender_email=current_user.email,
            lang=target_lang
        )
        return {"subject": subj, "body": body}

    t = TEMPLATES.get(req.template_type)
    if not t:
        raise HTTPException(400, f"Unknown template: {req.template_type}")
    ctx = dict(to_name=req.to_name or "Hiring Team",
               company=req.company or "your company",
               job_title=req.job_title or "the position",
               sender_name=current_user.name,
               sender_email=current_user.email)
    return {
        "subject": t["subject"].format(**ctx),
        "body":    t["body"].format(**ctx),
    }

@router.post("/send")
def send_email(req: SendEmailRequest,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    from ..bounce_cleaner import get_blacklisted_emails
    if req.to_email.strip().lower() in get_blacklisted_emails(db):
        raise HTTPException(400, f"Cannot send email: '{req.to_email}' is blocked in the platform blacklist due to prior delivery bounces (Message bloqué / Adresse introuvable).")
    try:
        # Check if we should attach an auto-tailored CV
        custom_pdf_bytes = None
        custom_pdf_name = None
        effective_score = None

        # Transition any corresponding saved application to status='applied' (sent)
        app_to_update = None
        if req.application_id:
            app_to_update = db.query(models.Application).filter(
                models.Application.id == req.application_id,
                models.Application.user_id == current_user.id
            ).first()
        else:
            app_to_update = db.query(models.Application).filter(
                models.Application.user_id == current_user.id,
                models.Application.status == 'saved',
                (models.Application.notes.contains(req.to_email) | models.Application.company.contains(req.subject.replace('Application for', '').split('—')[0].strip()))
            ).first()

        if req.attach_cv:
            # Automatic email send strictly attaches authentic original CV (cv.file_data)
            custom_pdf_bytes = None
            custom_pdf_name = None

        _dispatch_smtp(settings, current_user, req.to_email, req.to_name,
                       req.subject, req.body, req.attach_cv, db,
                       custom_attachment_bytes=custom_pdf_bytes,
                       custom_attachment_name=custom_pdf_name)

        if app_to_update:
            app_to_update.status = "applied"
            app_to_update.applied_at = datetime.utcnow()
            if not app_to_update.follow_up_date:
                app_to_update.follow_up_date = datetime.utcnow() + timedelta(days=3)
            now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            app_to_update.notes = (app_to_update.notes or "") + f"\n[{now_str}] 📤 Dispatched email to {req.to_email}" + (" (Tailored CV attached)" if custom_pdf_bytes else "")
            req.application_id = app_to_update.id

        log = models.EmailLog(
            user_id=current_user.id,
            application_id=req.application_id,
            to_email=req.to_email, to_name=req.to_name,
            subject=req.subject, body=req.body,
            template_type=req.template_type, status="sent")
        db.add(log); db.commit()
        return {
            "message": f"✨ Email sent successfully with auto-tailored CV ({effective_score or 98}% match)!" if custom_pdf_bytes else "Email sent successfully!",
            "application_id": req.application_id,
            "tailored": bool(custom_pdf_bytes),
            "tailored_score": effective_score
        }
    except Exception as e:
        log = models.EmailLog(
            user_id=current_user.id,
            application_id=req.application_id,
            to_email=req.to_email, to_name=req.to_name,
            subject=req.subject, body=req.body,
            template_type=req.template_type, status="failed")
        db.add(log); db.commit()
        raise HTTPException(500, f"Failed to send: {str(e)}")

@router.post("/auto-apply")
def auto_apply(req: AutoApplyRequest,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """1-Click Direct Application: tailors email, attaches CV, sends to ALL verified recruiter emails found for the role, and logs in Tracker."""
    # Build list of valid recipients
    recipients_list: List[RecipientItem] = []
    if req.recipients:
        for r in req.recipients:
            if r.email and "@" in r.email:
                recipients_list.append(r)
    if not recipients_list:
        if req.to_email and "@" in req.to_email:
            recipients_list.append(RecipientItem(email=req.to_email.strip(), name=req.to_name or "Hiring Team"))

    # Deduplicate by lowercase email
    seen_emails = set()
    deduped_recipients: List[RecipientItem] = []
    for r in recipients_list:
        clean_email = r.email.strip().lower()
        if clean_email not in seen_emails:
            seen_emails.add(clean_email)
            deduped_recipients.append(r)
    recipients_list = deduped_recipients

    # Exclude blacklisted emails (prior delivery failures / bounces)
    from ..bounce_cleaner import get_blacklisted_emails
    blacklisted = get_blacklisted_emails(db, current_user.id)
    recipients_list = [r for r in recipients_list if r.email.strip().lower() not in blacklisted]

    if not recipients_list:
        raise HTTPException(400, f"No deliverable recruiter email address found for {req.company} (any found addresses were blacklisted due to prior delivery bounces).")

    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Please configure your Gmail SMTP settings first in Settings.")

    sender_name = settings.sender_name or current_user.name

    # User-clicked Auto-Apply: attach an honest per-job tailored COPY (re-ordered, nothing added).
    # Falls back to the original CV (cv.file_data) when tailoring is off, fails, or doesn't help.
    custom_pdf_bytes = None
    custom_pdf_name = None
    effective_score = req.match_score or 0
    original_score = None
    if req.customize_cv:
        from ..tailoring import honest_tailored_attachment
        cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
        custom_pdf_bytes, custom_pdf_name, original_score, t_score = honest_tailored_attachment(
            cv, req.job_title, req.company, req.job_description)
        if custom_pdf_bytes and t_score is not None:
            effective_score = t_score

    try:
        dispatched = []
        logs_to_create = []

        # 1. Iterate through all verified recruiter emails and send personalized email to each
        for i, r in enumerate(recipients_list):
            r_name = r.name if r.name and r.name.strip() else "Hiring Team"
            auto_subj, auto_body, _ = get_application_email(
                role_title=req.job_title,
                company=req.company,
                recruiter_name=r_name,
                post_text=req.job_description,
                sender_name=sender_name,
                sender_email=current_user.email,
                lang=req.lang,
                site=req.site,
                url=req.job_url
            )
            subj_to_send = req.custom_subject or auto_subj
            body_to_send = req.custom_body or auto_body

            _dispatch_smtp(settings, current_user, r.email.strip(), r_name,
                           subj_to_send, body_to_send, True, db,
                           custom_attachment_bytes=custom_pdf_bytes,
                           custom_attachment_name=custom_pdf_name)

            dispatched.append({"email": r.email.strip(), "name": r_name})
            logs_to_create.append({
                "to_email": r.email.strip(),
                "to_name": r_name,
                "subject": subj_to_send,
                "body": body_to_send
            })

            # Gentle spacing between sends to multiple recruiters
            if i < len(recipients_list) - 1:
                time.sleep(0.4)

        if not dispatched:
            raise HTTPException(500, "Failed to dispatch email to recruiters.")

        # 2. Update existing saved application or create new Application in Tracker
        notes_recipients = ", ".join(f"{r['name']} ({r['email']})" if r['name'] and r['name'] != "Hiring Team" else r['email'] for r in dispatched)
        existing_app = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            (models.Application.company.ilike(req.company) | (models.Application.url == (req.job_url or 'nonexistent')))
        ).first()

        if existing_app:
            app = existing_app
            app.status = "applied"
            app.applied_at = datetime.utcnow()
            app.follow_up_date = datetime.utcnow() + timedelta(days=5)
            app.title = req.job_title or app.title
            app.match_score = effective_score or app.match_score
            app.notes = (app.notes or "") + f"\nAuto-applied to {len(dispatched)} recruiter(s): {notes_recipients}" + (" (Tailored CV)" if custom_pdf_bytes else "")
            if custom_pdf_bytes:
                app.tailored_cv_filename = custom_pdf_name
                app.tailored_cv_data = custom_pdf_bytes
            db.commit()
            db.refresh(app)
        else:
            app = models.Application(
                user_id=current_user.id,
                title=req.job_title,
                company=req.company,
                location=req.location or "",
                url=req.job_url or "",
                status="applied",
                match_score=effective_score,
                notes=f"Auto-applied to {len(dispatched)} recruiter(s): {notes_recipients}" + (" (Tailored CV)" if custom_pdf_bytes else ""),
                applied_at=datetime.utcnow(),
                follow_up_date=datetime.utcnow() + timedelta(days=5),
                tailored_cv_filename=custom_pdf_name,
                tailored_cv_data=custom_pdf_bytes
            )
            db.add(app)
            db.commit()
            db.refresh(app)

        for l_item in logs_to_create:
            log = models.EmailLog(
                user_id=current_user.id,
                application_id=app.id,
                to_email=l_item["to_email"],
                to_name=l_item["to_name"],
                subject=l_item["subject"],
                body=l_item["body"],
                template_type="auto_apply",
                status="sent"
            )
            db.add(log)

        db.commit()

        recruiter_names = [d["name"] if d["name"] != "Hiring Team" else d["email"] for d in dispatched]
        return {
            "success": True,
            "message": f"Successfully applied to {req.company}! Sent to all {len(dispatched)} recruiter(s) ({', '.join(recruiter_names)})" + (f" — tailored CV attached (match {original_score}% → {effective_score}%)" if custom_pdf_bytes else " — original CV attached"),
            "application_id": app.id,
            "recipients_count": len(dispatched),
            "recipients": dispatched,
            "to_email": dispatched[0]["email"],
            "tailored": bool(custom_pdf_bytes),
            "original_score": original_score,
            "tailored_score": effective_score
        }
    except Exception as e:
        raise HTTPException(500, f"Auto-apply failed: {str(e)}")

@router.post("/batch-auto-apply")
def batch_auto_apply(req: BatchAutoApplyRequest,
                     db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    """Batch Auto-Apply: Iterates through qualified jobs, dynamically tailors CVs, and sends applications to ALL verified recruiters found for each position."""
    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Please configure your Gmail SMTP settings first in Settings.")

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    sender_name = settings.sender_name or current_user.name
    results = []
    applied_count = 0
    failed_count = 0

    for idx, item in enumerate(req.jobs):
        recipients_list: List[RecipientItem] = []
        if item.recipients:
            for r in item.recipients:
                if r.email and "@" in r.email:
                    recipients_list.append(r)
        if not recipients_list:
            if item.to_email and "@" in item.to_email:
                recipients_list.append(RecipientItem(email=item.to_email.strip(), name=item.to_name or "Hiring Team"))

        # Deduplicate
        seen_emails = set()
        deduped = []
        for r in recipients_list:
            clean = r.email.strip().lower()
            if clean not in seen_emails:
                seen_emails.add(clean)
                deduped.append(r)
        recipients_list = deduped

        # Filter out blacklisted emails
        from ..bounce_cleaner import get_blacklisted_emails
        blacklisted = get_blacklisted_emails(db, current_user.id)
        recipients_list = [r for r in recipients_list if r.email.strip().lower() not in blacklisted]

        if not recipients_list:
            results.append({"company": item.company, "title": item.job_title, "status": "skipped", "error": "Recruiter email(s) are blacklisted (prior bounce/block)"})
            continue

        # User-clicked batch: honest per-job tailored COPY; original CV on fallback
        custom_pdf_bytes = None
        custom_pdf_name = None
        item_score = item.match_score or 0
        item_orig_score = None
        if req.customize_cv and item.customize_cv:
            from ..tailoring import honest_tailored_attachment
            custom_pdf_bytes, custom_pdf_name, item_orig_score, t_score = honest_tailored_attachment(
                cv, item.job_title, item.company, item.job_description)
            if custom_pdf_bytes and t_score is not None:
                item_score = t_score

        try:
            job_dispatched = []
            logs_to_create = []

            for r_idx, r in enumerate(recipients_list):
                r_name = r.name if r.name and r.name.strip() else "Hiring Team"
                auto_subj, auto_body, _ = get_application_email(
                    role_title=item.job_title,
                    company=item.company,
                    recruiter_name=r_name,
                    post_text=item.job_description,
                    sender_name=sender_name,
                    sender_email=current_user.email,
                    lang=getattr(item, "lang", None),
                    site=getattr(item, "site", None),
                    url=item.job_url
                )
                subject = getattr(item, "custom_subject", None) or auto_subj
                body = getattr(item, "custom_body", None) or auto_body

                _dispatch_smtp(settings, current_user, r.email.strip(), r_name,
                               subject, body, True, db,
                               custom_attachment_bytes=custom_pdf_bytes,
                               custom_attachment_name=custom_pdf_name)

                job_dispatched.append(r.email.strip())
                logs_to_create.append({
                    "to_email": r.email.strip(),
                    "to_name": r_name,
                    "subject": subject,
                    "body": body
                })

                if r_idx < len(recipients_list) - 1:
                    time.sleep(0.4)

            if not job_dispatched:
                raise ValueError(f"Could not dispatch email to any recruiter for {item.company}")

            # Update existing saved application or create new Application in Tracker
            notes_recipients = ", ".join(f"{r.name} ({r.email})" if r.name and r.name != "Hiring Team" else r.email for r in recipients_list)
            existing_app = db.query(models.Application).filter(
                models.Application.user_id == current_user.id,
                (models.Application.company.ilike(item.company) | (models.Application.url == (item.job_url or 'nonexistent')))
            ).first()

            if existing_app:
                app = existing_app
                app.status = "applied"
                app.applied_at = datetime.utcnow()
                app.follow_up_date = datetime.utcnow() + timedelta(days=5)
                app.title = item.job_title or app.title
                app.match_score = item_score or app.match_score
                app.notes = (app.notes or "") + f"\nBatch auto-applied to {len(job_dispatched)} recruiter(s): {notes_recipients}" + (" (Tailored CV)" if custom_pdf_bytes else "")
                if custom_pdf_bytes:
                    app.tailored_cv_filename = custom_pdf_name
                    app.tailored_cv_data = custom_pdf_bytes
                db.commit()
                db.refresh(app)
            else:
                app = models.Application(
                    user_id=current_user.id,
                    title=item.job_title,
                    company=item.company,
                    location=item.location or "",
                    url=item.job_url or "",
                    status="applied",
                    match_score=item_score,
                    notes=f"Batch auto-applied to {len(job_dispatched)} recruiter(s): {notes_recipients}" + (" (Tailored CV)" if custom_pdf_bytes else ""),
                    applied_at=datetime.utcnow(),
                    follow_up_date=datetime.utcnow() + timedelta(days=5),
                    tailored_cv_filename=custom_pdf_name,
                    tailored_cv_data=custom_pdf_bytes
                )
                db.add(app)
                db.commit()
                db.refresh(app)

            for l_item in logs_to_create:
                log = models.EmailLog(
                    user_id=current_user.id,
                    application_id=app.id,
                    to_email=l_item["to_email"],
                    to_name=l_item["to_name"],
                    subject=l_item["subject"],
                    body=l_item["body"],
                    template_type="auto_apply",
                    status="sent"
                )
                db.add(log)

            db.commit()

            results.append({
                "company": item.company,
                "title": item.job_title,
                "to_emails": job_dispatched,
                "status": "sent",
                "app_id": app.id,
                "recipients_count": len(job_dispatched),
                "tailored": bool(custom_pdf_bytes),
                "original_score": item_orig_score,
                "tailored_score": item_score
            })
            applied_count += 1

            # Polite delay between jobs
            if idx < len(req.jobs) - 1 and req.delay_seconds > 0:
                time.sleep(req.delay_seconds)
        except Exception as err:
            results.append({
                "company": item.company,
                "title": item.job_title,
                "to_email": recipients_list[0].email if recipients_list else "",
                "status": "failed",
                "error": str(err)
            })
            failed_count += 1

    return {
        "total": len(req.jobs),
        "applied": applied_count,
        "failed": failed_count,
        "details": results
    }

@router.get("/history")
def get_history(db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    logs = db.query(models.EmailLog)             .filter(models.EmailLog.user_id == current_user.id)             .order_by(models.EmailLog.sent_at.desc()).limit(200).all()
    return [{"id": l.id, "to_email": l.to_email, "to_name": l.to_name,
             "subject": l.subject, "body": l.body,
             "template_type": l.template_type, "status": l.status,
             "sent_at": str(l.sent_at),
             "application_id": l.application_id} for l in logs]

@router.post("/settings")
def save_settings(req: SettingsRequest,
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    s = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if s:
        s.smtp_host=req.smtp_host; s.smtp_port=req.smtp_port
        s.smtp_user=req.smtp_user; s.smtp_password=req.smtp_password
        s.sender_name=req.sender_name
        s.auth_method = "smtp"; s.gmail_refresh_token = ""
    else:
        s = models.EmailSettings(user_id=current_user.id, **req.dict())
        db.add(s)
    db.commit()
    return {"message": "Email settings saved!"}

@router.get("/settings")
def get_settings_view(db: Session = Depends(get_db),
                      current_user: models.User = Depends(get_current_user)):
    s = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if not s:
        return {"configured": False}
    return {"configured": bool(s.smtp_user), "smtp_host": s.smtp_host,
            "smtp_port": s.smtp_port, "smtp_user": s.smtp_user,
            "sender_name": s.sender_name, "auth_method": getattr(s, "auth_method", None) or "smtp"}

# ── Custom Templates ─────────────────────────────────────────────────────────

class CustomTemplateCreate(BaseModel):
    name: str
    subject: str = ""
    body: str = ""

@router.get("/custom-templates")
def list_custom_templates(db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    items = db.query(models.CustomTemplate) \
              .filter(models.CustomTemplate.user_id == current_user.id) \
              .order_by(models.CustomTemplate.created_at.desc()).all()
    return [{"id": t.id, "name": t.name, "subject": t.subject,
             "body": t.body, "created_at": str(t.created_at)} for t in items]

@router.post("/custom-templates")
def create_custom_template(req: CustomTemplateCreate,
                           db: Session = Depends(get_db),
                           current_user: models.User = Depends(get_current_user)):
    t = models.CustomTemplate(user_id=current_user.id,
                               name=req.name, subject=req.subject, body=req.body)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name, "subject": t.subject, "body": t.body}

@router.delete("/custom-templates/{template_id}")
def delete_custom_template(template_id: int,
                           db: Session = Depends(get_db),
                           current_user: models.User = Depends(get_current_user)):
    t = db.query(models.CustomTemplate).filter(
        models.CustomTemplate.id == template_id,
        models.CustomTemplate.user_id == current_user.id).first()
    if not t: raise HTTPException(404, "Not found")
    db.delete(t); db.commit()
    return {"message": "Deleted"}

@router.post("/test")
def send_test_email(db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Email not configured")
    try:
        import smtplib as _smtp
        from email.mime.text import MIMEText as _MT
        msg = _MT("This is a test email from your Job Searcher app! Your SMTP settings are working correctly.", "plain", "utf-8")
        msg["Subject"] = "Job Searcher — Test Email ✅"
        msg["From"] = settings.smtp_user
        msg["To"] = settings.smtp_user
        if getattr(settings, "auth_method", "smtp") == "gmail_oauth":
            from ..gmail_oauth import send_raw_via_gmail
            send_raw_via_gmail(settings.gmail_refresh_token, msg.as_bytes())
            return {"message": f"Test email sent to {settings.smtp_user}!"}
        with _smtp.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            clean_pwd = "".join(settings.smtp_password.split())
            s.login(settings.smtp_user, clean_pwd)
            s.sendmail(settings.smtp_user, settings.smtp_user, msg.as_string())
        return {"message": "Test email sent!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed: {str(e)}")


class VerifyEmailRequest(BaseModel):
    email: str
    company: Optional[str] = ""
    recruiter_name: Optional[str] = ""
    source: Optional[str] = ""


@router.post("/verify")
def verify_email_endpoint(req: VerifyEmailRequest,
                          current_user: models.User = Depends(get_current_user)):
    """
    Live Verification Probe:
    Tests an email address for deliverability (MX routing + SMTP handshake)
    and verifies that it belongs to active Recruitment/HR (not generic support/sales/info).
    """
    from recruiter_hunter import verify_email_full
    result = verify_email_full(
        req.email,
        company=req.company or "",
        recruiter_name=req.recruiter_name or "",
        source=req.source or ""
    )
    return result


# ── Bounce Scanner & Blacklist Endpoints ─────────────────────────────────────

class SyncBouncesRequest(BaseModel):
    delete_from_gmail: bool = True

class BlacklistCreateRequest(BaseModel):
    email: str
    reason: Optional[str] = "Manual entry"

@router.post("/sync-bounces")
def sync_bounces_endpoint(req: SyncBouncesRequest = SyncBouncesRequest(),
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """
    Connects to Gmail via IMAP, detects all delivery failure notifications
    (such as 'Message bloqué' and 'Adresse introuvable'), extracts the dead emails,
    adds them to the persistent blacklist, purges dead applications from the tracker,
    and moves/deletes the bounce messages from Gmail.
    """
    from ..bounce_cleaner import sync_gmail_bounces
    try:
        summary = sync_gmail_bounces(db, current_user.id, delete_from_gmail=req.delete_from_gmail)
        try:
            import recruiter_hunter
            recruiter_hunter.load_blacklisted_emails(force_reload=True)
        except Exception:
            pass
        return summary
    except ValueError as ve:
        raise HTTPException(400, str(ve))
    except Exception as e:
        raise HTTPException(500, f"Bounce synchronization failed: {str(e)}")

@router.get("/blacklist")
def get_blacklist(db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Retrieves all blacklisted / bounced emails across the platform (community protection)."""
    items = db.query(models.EmailBlacklist)\
              .order_by(models.EmailBlacklist.created_at.desc()).all()
    return [{"id": b.id, "email": b.email, "reason": b.reason,
             "source": b.source, "created_at": str(b.created_at),
             "is_mine": b.user_id == current_user.id} for b in items]

@router.post("/blacklist")
def add_to_blacklist(req: BlacklistCreateRequest,
                     db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    """Manually adds an email to the persistent global blacklist for all users."""
    clean_email = req.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(400, "Invalid email address")
    # Global check across all users
    existing = db.query(models.EmailBlacklist).filter(
        models.EmailBlacklist.email == clean_email
    ).first()
    if existing:
        return {"message": "Email is already blacklisted globally", "id": existing.id}
    entry = models.EmailBlacklist(
        user_id=current_user.id,
        email=clean_email,
        reason=req.reason or "Manual entry",
        source="manual",
        created_at=datetime.utcnow()
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    try:
        import recruiter_hunter
        recruiter_hunter.load_blacklisted_emails(force_reload=True)
    except Exception:
        pass
    return {"id": entry.id, "email": entry.email, "reason": entry.reason, "created_at": str(entry.created_at), "is_mine": True}

@router.delete("/blacklist/{entry_id}")
def delete_from_blacklist(entry_id: int,
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Removes an email from the blacklist (unblocks)."""
    entry = db.query(models.EmailBlacklist).filter(
        models.EmailBlacklist.id == entry_id
    ).first()
    if not entry:
        raise HTTPException(404, "Blacklist entry not found")
    if entry.user_id and entry.user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(403, "You can only unblock entries that were added by your account")
    db.delete(entry)
    db.commit()
    try:
        import recruiter_hunter
        recruiter_hunter.load_blacklisted_emails(force_reload=True)
    except Exception:
        pass
    return {"message": "Email unblocked and removed from blacklist"}

# ---------------------------------------------------------------------------
# RECRUITER FOLLOW-UP SYSTEM
# ---------------------------------------------------------------------------

class FollowUpSendRequest(BaseModel):
    application_id: int
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None
    attach_cv: bool = True

class FollowUpBatchRequest(BaseModel):
    application_ids: Optional[List[int]] = None
    attach_cv: bool = True

def _build_followup_email(app: models.Application, user: models.User, sender_name: str, recipient_name: str) -> tuple[str, str]:
    applied_date_str = app.applied_at.strftime('%B %d, %Y') if app.applied_at else None
    detected_lang = detect_language(f"{app.title} {app.company} {app.notes or ''}")
    subj, body, _ = get_followup_email(
        role_title=app.title,
        company=app.company,
        recruiter_name=recipient_name,
        applied_date_str=applied_date_str,
        sender_name=sender_name,
        sender_email=user.email,
        lang=detected_lang
    )
    return subj, body

@router.get("/follow-up/candidates")
def get_follow_up_candidates(days: int = 3,
                             db: Session = Depends(get_db),
                             current_user: models.User = Depends(get_current_user)):
    """
    Returns all applications awaiting recruiter response (> days threshold) with no reply,
    ready for a professional follow-up email.
    """
    from ..bounce_cleaner import get_blacklisted_emails
    blacklisted = get_blacklisted_emails(db)

    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == current_user.id).first()
    sender_name = settings.sender_name if settings and settings.sender_name else current_user.name

    apps = db.query(models.Application).filter(
        models.Application.user_id == current_user.id,
        models.Application.status == "applied"
    ).all()
    if not apps:
        return []

    from collections import defaultdict
    app_ids = [a.id for a in apps]
    all_logs = (
        db.query(models.EmailLog)
        .filter(models.EmailLog.application_id.in_(app_ids))
        .all()
    )
    logs_by_app = defaultdict(list)
    for l in all_logs:
        logs_by_app[l.application_id].append(l)

    now = datetime.utcnow()
    candidates = []

    for app in apps:
        # Skip if recruiter already replied
        notes = app.notes or ""
        if "📥 Recruiter Reply:" in notes:
            continue

        applied_time = app.applied_at or now
        days_waiting = (now - applied_time).days
        if days_waiting < days:
            continue

        app_logs = logs_by_app.get(app.id, [])
        followup_logs = [l for l in app_logs if l.template_type == "follow_up"]
        follow_up_count = len(followup_logs)
        if follow_up_count >= 2:
            continue  # Professional etiquette: maximum 2 follow-ups

        # If a follow-up was already sent within the last 3 days, skip
        if followup_logs:
            sent_dates = [f.sent_at for f in followup_logs if f.sent_at]
            if sent_dates and (now - max(sent_dates)).days < 3:
                continue

        # Gather deliverable recruiter emails
        sent_logs = [l for l in app_logs if l.status != "bounced"]

        recipients = []
        seen = set()
        for log in sent_logs:
            if log.to_email and log.to_email.lower() not in seen and log.to_email.lower() not in blacklisted:
                seen.add(log.to_email.lower())
                recipients.append({"email": log.to_email, "name": log.to_name or "Hiring Team"})

        if not recipients and notes:
            import re
            extracted = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', notes)
            for e in extracted:
                e_clean = e.strip().lower()
                if e_clean not in seen and e_clean not in blacklisted:
                    seen.add(e_clean)
                    recipients.append({"email": e_clean, "name": "Hiring Team"})

        if not recipients:
            continue

        preview_subject, preview_body = _build_followup_email(app, current_user, sender_name, recipients[0]["name"])

        candidates.append({
            "application_id": app.id,
            "company": app.company,
            "title": app.title,
            "applied_at": str(app.applied_at),
            "days_waiting": days_waiting,
            "follow_up_count": follow_up_count,
            "recipients": recipients,
            "has_tailored_cv": bool(app.tailored_cv_filename),
            "preview_subject": preview_subject,
            "preview_body": preview_body
        })

    return sorted(candidates, key=lambda c: c["days_waiting"], reverse=True)

@router.post("/follow-up/send")
def send_follow_up(req: FollowUpSendRequest,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """
    Dispatches a professional follow-up email to the recruiter(s) for an application.
    """
    app = db.query(models.Application).filter(
        models.Application.id == req.application_id,
        models.Application.user_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(404, "Application not found")

    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id
    ).first()
    if not settings or not settings.smtp_user or not (settings.smtp_password or getattr(settings, "auth_method", "") == "gmail_oauth"):
        raise HTTPException(400, "Please connect your Gmail first in Settings.")

    from ..bounce_cleaner import get_blacklisted_emails
    blacklisted = get_blacklisted_emails(db)

    # Find deliverable recipients
    sent_logs = db.query(models.EmailLog).filter(
        models.EmailLog.application_id == app.id,
        models.EmailLog.status != "bounced"
    ).all()
    recipients = []
    seen = set()
    for log in sent_logs:
        if log.to_email and log.to_email.lower() not in seen and log.to_email.lower() not in blacklisted:
            seen.add(log.to_email.lower())
            recipients.append({"email": log.to_email, "name": log.to_name or "Hiring Team"})

    if not recipients and app.notes:
        import re
        extracted = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', app.notes)
        for e in extracted:
            e_clean = e.strip().lower()
            if e_clean not in seen and e_clean not in blacklisted:
                seen.add(e_clean)
                recipients.append({"email": e_clean, "name": "Hiring Team"})

    if not recipients:
        raise HTTPException(400, "No deliverable recruiter email addresses available for this application.")

    sender_name = settings.sender_name if settings.sender_name else current_user.name
    followup_count = db.query(models.EmailLog).filter(
        models.EmailLog.application_id == app.id,
        models.EmailLog.template_type == "follow_up"
    ).count() + 1

    # Attachments
    cv_bytes = None
    cv_name = None
    if req.attach_cv:
        if app.tailored_cv_data:
            cv_bytes = app.tailored_cv_data
            cv_name = app.tailored_cv_filename or f"CV_{sender_name.replace(' ', '_')}.pdf"
        else:
            cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
            if cv and cv.file_data:
                cv_bytes = cv.file_data
                cv_name = cv.filename or f"CV_{sender_name.replace(' ', '_')}.pdf"

    dispatched = []
    for r in recipients:
        subject = req.custom_subject or f"Follow-up: Application for {app.title} — {sender_name}"
        if req.custom_body:
            body = req.custom_body
        else:
            _, body = _build_followup_email(app, current_user, sender_name, r["name"])

        _dispatch_smtp(settings, current_user, r["email"], r["name"], subject, body,
                       attach_cv=bool(cv_bytes), db=db,
                       custom_attachment_bytes=cv_bytes, custom_attachment_name=cv_name)

        log = models.EmailLog(
            user_id=current_user.id,
            application_id=app.id,
            to_email=r["email"],
            to_name=r["name"],
            subject=subject,
            body=body,
            template_type="follow_up",
            status="sent"
        )
        db.add(log)
        dispatched.append(r["email"])

    timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    audit_note = f"\n[{timestamp_str}] 📤 Sent Follow-up #{followup_count} to {', '.join(dispatched)}"
    app.notes = (app.notes or "") + audit_note
    app.follow_up_date = datetime.utcnow() + timedelta(days=5)

    db.commit()

    return {
        "success": True,
        "message": f"Sent Follow-up #{followup_count} to {len(dispatched)} recruiter(s) at {app.company}!",
        "application_id": app.id,
        "dispatched_to": dispatched,
        "follow_up_count": followup_count
    }

@router.post("/follow-up/send-all")
def send_all_follow_ups(req: FollowUpBatchRequest,
                        db: Session = Depends(get_db),
                        current_user: models.User = Depends(get_current_user)):
    """
    Batch-sends polite follow-up emails to all eligible applications in one click.
    """
    candidates = get_follow_up_candidates(days=3, db=db, current_user=current_user)
    if req.application_ids:
        target_ids = set(req.application_ids)
        candidates = [c for c in candidates if c["application_id"] in target_ids]

    if not candidates:
        return {"sent_count": 0, "message": "No applications currently awaiting follow-up."}

    sent_count = 0
    errors = []

    for c in candidates:
        try:
            send_follow_up(
                FollowUpSendRequest(
                    application_id=c["application_id"],
                    attach_cv=req.attach_cv
                ),
                db=db,
                current_user=current_user
            )
            sent_count += 1
            time.sleep(0.5)
        except Exception as e:
            errors.append(f"App {c['application_id']} ({c['company']}): {str(e)}")

    return {
        "success": True,
        "sent_count": sent_count,
        "message": f"Successfully sent follow-up emails for {sent_count} application(s)!",
        "errors": errors
    }

@router.get("/calendar-analytics")
def get_calendar_analytics(year: Optional[int] = None,
                           month: Optional[int] = None,
                           db: Session = Depends(get_db),
                           current_user: models.User = Depends(get_current_user)):
    """
    Returns day-by-day analytics and log breakdown of all sent emails for the calendar view.
    Groups sent emails by calendar date (YYYY-MM-DD), with deliverability, quota tracking,
    recruiter contacts, and full thread inspection.
    """
    import calendar
    now = datetime.utcnow()
    target_year = year or now.year
    target_month = month or now.month

    # Query all email logs for current user
    logs = db.query(models.EmailLog).filter(
        models.EmailLog.user_id == current_user.id
    ).order_by(models.EmailLog.sent_at.desc()).all()

    # Pre-fetch applications to provide job titles and company names
    app_ids = {l.application_id for l in logs if l.application_id}
    apps_map = {}
    if app_ids:
        app_records = db.query(models.Application).filter(models.Application.id.in_(list(app_ids))).all()
        apps_map = {a.id: a for a in app_records}

    # Group by YYYY-MM-DD
    days_data = {}
    month_sent_total = 0
    month_bounced_total = 0
    month_followup_total = 0
    active_days_set = set()

    for l in logs:
        if not l.sent_at:
            continue
        dt = l.sent_at
        date_str = dt.strftime("%Y-%m-%d")

        # Check if log belongs to requested month/year
        in_selected_month = (dt.year == target_year and dt.month == target_month)

        if date_str not in days_data:
            days_data[date_str] = {
                "date": date_str,
                "day": dt.day,
                "month": dt.month,
                "year": dt.year,
                "total": 0,
                "sent_count": 0,
                "bounced_count": 0,
                "follow_up_count": 0,
                "emails": []
            }

        day_entry = days_data[date_str]
        day_entry["total"] += 1
        if l.status == "sent":
            day_entry["sent_count"] += 1
            if in_selected_month:
                month_sent_total += 1
        elif l.status == "bounced":
            day_entry["bounced_count"] += 1
            if in_selected_month:
                month_bounced_total += 1

        if l.template_type == "follow_up":
            day_entry["follow_up_count"] += 1
            if in_selected_month:
                month_followup_total += 1

        if in_selected_month:
            active_days_set.add(date_str)

        app_obj = apps_map.get(l.application_id)
        company_name = app_obj.company if app_obj else "Direct Outreach"
        job_title = app_obj.title if app_obj else (l.subject.split("—")[0].replace("Application for", "").strip() if "Application for" in (l.subject or "") else (l.subject or "Recruiter Contact"))

        day_entry["emails"].append({
            "id": l.id,
            "to_email": l.to_email,
            "to_name": l.to_name,
            "subject": l.subject,
            "body": l.body,
            "template_type": l.template_type,
            "status": l.status,
            "sent_at": l.sent_at.isoformat() if l.sent_at else None,
            "time_str": dt.strftime("%H:%M"),
            "company": company_name,
            "job_title": job_title,
            "application_id": l.application_id
        })

    month_name = f"{calendar.month_name[target_month]} {target_year}"

    # Calculate today's usage against Gmail's 100/day rolling limit
    today_str = now.strftime("%Y-%m-%d")
    today_data = days_data.get(today_str, {"total": 0, "sent_count": 0, "bounced_count": 0})
    today_sent = today_data["total"]

    total_dispatched_month = month_sent_total + month_bounced_total
    deliverability_rate = round((month_sent_total / total_dispatched_month * 100), 1) if total_dispatched_month > 0 else 100.0

    return {
        "year": target_year,
        "month": target_month,
        "month_name": month_name,
        "days": days_data,
        "today_str": today_str,
        "today_sent": today_sent,
        "daily_limit": 100,
        "quota_remaining": max(0, 100 - today_sent),
        "month_stats": {
            "total_sent": month_sent_total,
            "total_bounced": month_bounced_total,
            "total_follow_ups": month_followup_total,
            "active_days": len(active_days_set),
            "deliverability_rate": deliverability_rate
        }
    }



