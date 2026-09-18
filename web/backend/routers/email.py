
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import smtplib, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from .. import models
from ..database import get_db
from ..auth import get_current_user

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

class SendEmailRequest(BaseModel):
    to_email: str
    to_name: str = "Hiring Team"
    subject: str
    body: str
    template_type: str = "custom"
    application_id: Optional[int] = None   # link to tracker card
    attach_cv: bool = True

class AutoApplyRequest(BaseModel):
    job_title: str
    company: str
    to_email: str
    to_name: Optional[str] = "Hiring Team"
    job_url: Optional[str] = ""
    location: Optional[str] = ""
    match_score: Optional[int] = 0
    notes: Optional[str] = ""
    job_description: Optional[str] = ""
    customize_cv: Optional[bool] = True

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

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(settings.smtp_user, clean_pwd)
        s.sendmail(settings.smtp_user, to_email, msg.as_string())

@router.post("/template")
def get_template(req: TemplateRequest,
                 current_user: models.User = Depends(get_current_user)):
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
    try:
        _dispatch_smtp(settings, current_user, req.to_email, req.to_name,
                       req.subject, req.body, req.attach_cv, db)
        log = models.EmailLog(
            user_id=current_user.id,
            application_id=req.application_id,
            to_email=req.to_email, to_name=req.to_name,
            subject=req.subject, body=req.body,
            template_type=req.template_type, status="sent")
        db.add(log); db.commit()
        return {"message": "Email sent successfully!"}
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
    """1-Click Direct Application: tailors email, attaches CV, sends via SMTP, and logs in Tracker."""
    if not req.to_email or "@" not in req.to_email:
        raise HTTPException(400, f"No valid email address found for {req.company}")

    settings = db.query(models.EmailSettings).filter(
        models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Please configure your Gmail SMTP settings first in Settings.")

    sender_name = settings.sender_name or current_user.name
    subject = f"Application for {req.job_title} — {sender_name}"
    to_name = req.to_name or "Hiring Team"
    body = f"""Dear {to_name} at {req.company},

I am writing to express my strong interest in the {req.job_title} position.

With strong technical experience and proven expertise, I specialize in building high-performance applications and clean, reliable software solutions. Having reviewed your role, I believe my background and technical skills make me an excellent candidate for your team.

I have attached my resume for your review, detailing my accomplishments, technical stack, and shipped projects.

I would welcome the opportunity to discuss how I can contribute to {req.company}. Thank you for your time and consideration.

Best regards,
{sender_name}
{current_user.email}"""

    custom_pdf_bytes = None
    custom_pdf_name = None
    effective_score = req.match_score or 0

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    if req.customize_cv and cv and cv.text_content:
        try:
            from cv_tailor import tailor_cv
            tailor_res = tailor_cv(cv.text_content, req.job_title, req.company, req.job_description or req.job_title)
            custom_pdf_bytes = tailor_res["pdf_bytes"]
            custom_pdf_name = tailor_res["filename"]
            effective_score = tailor_res["tailored_score"]
        except Exception as t_err:
            print(f"[AutoApply] Tailoring warning: {t_err}")

    try:
        # 1. Send email with attached (tailored or base) CV
        _dispatch_smtp(settings, current_user, req.to_email, to_name,
                       subject, body, True, db,
                       custom_attachment_bytes=custom_pdf_bytes,
                       custom_attachment_name=custom_pdf_name)

        # 2. Create Application in Tracker
        app = models.Application(
            user_id=current_user.id,
            title=req.job_title,
            company=req.company,
            location=req.location or "",
            url=req.job_url or "",
            status="applied",
            match_score=effective_score,
            notes=f"Auto-applied via direct email to {req.to_email}" + (" (Tailored CV)" if custom_pdf_bytes else ""),
            applied_at=datetime.utcnow(),
            follow_up_date=datetime.utcnow() + timedelta(days=5),
            tailored_cv_filename=custom_pdf_name,
            tailored_cv_data=custom_pdf_bytes
        )
        db.add(app); db.commit(); db.refresh(app)

        # 3. Log the sent email linked to application
        log = models.EmailLog(
            user_id=current_user.id,
            application_id=app.id,
            to_email=req.to_email,
            to_name=to_name,
            subject=subject,
            body=body,
            template_type="auto_apply",
            status="sent"
        )
        db.add(log); db.commit()

        return {
            "success": True,
            "message": f"Successfully applied to {req.company}!" + (" (CV Tailored 100%)" if custom_pdf_bytes else ""),
            "application_id": app.id,
            "to_email": req.to_email,
            "tailored_score": effective_score
        }
    except Exception as e:
        raise HTTPException(500, f"Auto-apply failed: {str(e)}")

@router.post("/batch-auto-apply")
def batch_auto_apply(req: BatchAutoApplyRequest,
                     db: Session = Depends(get_db),
                     current_user: models.User = Depends(get_current_user)):
    """Batch Auto-Apply: Iterates through qualified jobs, dynamically tailors CVs, and sends applications."""
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
        if not item.to_email or "@" not in item.to_email:
            results.append({"company": item.company, "status": "skipped", "error": "Invalid email"})
            continue

        subject = f"Application for {item.job_title} — {sender_name}"
        to_name = item.to_name or "Hiring Team"
        body = f"""Dear {to_name} at {item.company},

I am writing to express my strong interest in the {item.job_title} position.

With strong technical experience and proven expertise, I specialize in building high-performance applications and clean, reliable software solutions. Having reviewed your role, I believe my background and technical skills make me an excellent candidate for your team.

I have attached my tailored resume for your review, detailing my accomplishments, technical stack, and shipped projects aligned directly with this role.

I would welcome the opportunity to discuss how I can contribute to {item.company}. Thank you for your time and consideration.

Best regards,
{sender_name}
{current_user.email}"""

        custom_pdf_bytes = None
        custom_pdf_name = None
        item_score = item.match_score or 0

        if (req.customize_cv or item.customize_cv) and cv and cv.text_content:
            try:
                from cv_tailor import tailor_cv
                tailor_res = tailor_cv(cv.text_content, item.job_title, item.company, item.job_description or item.job_title)
                custom_pdf_bytes = tailor_res["pdf_bytes"]
                custom_pdf_name = tailor_res["filename"]
                item_score = tailor_res["tailored_score"]
            except Exception as b_err:
                print(f"[BatchAutoApply] Tailoring warning for {item.company}: {b_err}")

        try:
            _dispatch_smtp(settings, current_user, item.to_email, to_name,
                           subject, body, True, db,
                           custom_attachment_bytes=custom_pdf_bytes,
                           custom_attachment_name=custom_pdf_name)

            app = models.Application(
                user_id=current_user.id,
                title=item.job_title,
                company=item.company,
                location=item.location or "",
                url=item.job_url or "",
                status="applied",
                match_score=item_score,
                notes=f"Batch auto-applied via direct email to {item.to_email}" + (" (Tailored CV)" if custom_pdf_bytes else ""),
                applied_at=datetime.utcnow(),
                follow_up_date=datetime.utcnow() + timedelta(days=5),
                tailored_cv_filename=custom_pdf_name,
                tailored_cv_data=custom_pdf_bytes
            )
            db.add(app); db.commit(); db.refresh(app)

            log = models.EmailLog(
                user_id=current_user.id,
                application_id=app.id,
                to_email=item.to_email,
                to_name=to_name,
                subject=subject,
                body=body,
                template_type="auto_apply",
                status="sent"
            )
            db.add(log); db.commit()

            results.append({"company": item.company, "title": item.job_title, "to_email": item.to_email, "status": "sent", "app_id": app.id})
            applied_count += 1

            # Polite delay between sends to prevent SMTP throttling
            if idx < len(req.jobs) - 1 and req.delay_seconds > 0:
                time.sleep(req.delay_seconds)
        except Exception as err:
            results.append({"company": item.company, "title": item.job_title, "to_email": item.to_email, "status": "failed", "error": str(err)})
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
            "sender_name": s.sender_name}

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
        with _smtp.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            clean_pwd = "".join(settings.smtp_password.split())
            s.login(settings.smtp_user, clean_pwd)
            s.sendmail(settings.smtp_user, settings.smtp_user, msg.as_string())
        return {"message": "Test email sent!"}
    except Exception as e:
        raise HTTPException(500, f"Failed: {str(e)}")
