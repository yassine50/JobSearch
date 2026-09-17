
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .. import models
from ..database import get_db
from ..auth import get_current_user
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter(prefix="/api/email", tags=["email"])

TEMPLATES = {
    "application": {
        "subject": "Application for {job_title} — {sender_name}",
        "body": """Dear {to_name},

I am writing to express my strong interest in the {job_title} position at {company}.

Having reviewed the role carefully, I believe my background and skills make me an excellent candidate for this opportunity.

I would welcome the chance to discuss how I can contribute to your team. Please find my details below.

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
    to_name: str
    subject: str
    body: str
    template_type: str = "custom"
    application_id: Optional[int] = None   # link to tracker card

class SettingsRequest(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    sender_name: str

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
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Email not configured. Go to Settings → Email Setup.")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = req.subject
        msg["From"]    = f"{settings.sender_name or current_user.name} <{settings.smtp_user}>"
        msg["To"]      = f"{req.to_name} <{req.to_email}>"
        msg.attach(MIMEText(req.body, "plain"))
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.smtp_user, req.to_email, msg.as_string())
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
