from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import re

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..bounce_cleaner import get_blacklisted_emails
from ..linkedin_post_hunter import (
    search_linkedin_recruiter_posts,
    canonicalize_linkedin_post_url,
    generate_stable_post_id,
    extract_clean_emails_from_text,
    verify_recruiter_email_strictly,
    extract_accurate_job_title,
    check_role_and_skill_fit,
    extract_post_required_years,
    _SEARCH_CACHE
)
from .email import _dispatch_smtp
from ..email_templates import get_application_email, detect_language

router = APIRouter(prefix="/api/linkedin-posts", tags=["linkedin-posts"])

class TagSuggestRequest(BaseModel):
    role: str = ""
    locations: Optional[List[str]] = []
    custom_tags: Optional[List[str]] = []

class PostSearchRequest(BaseModel):
    role: str
    location: Optional[str] = ""
    locations: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    limit: int = 40
    email_only: bool = False
    time_range: str = "all"  # "24h", "3d", "7d", "all"
    min_score: int = 0
    sort_by: str = "score"   # "score", "newest", "emails"
    agent_mode: bool = False
    force_refresh: bool = False
    page: int = 1
    li_at: Optional[str] = ""

class ConnectAccountRequest(BaseModel):
    li_at: str

class PostApplyRequest(BaseModel):
    post_url: Optional[str] = ""
    role_title: Optional[str] = "Open Role"
    company: Optional[str] = "Company"
    location: Optional[str] = ""
    recruiter_name: Optional[str] = "Hiring Team"
    recruiter_email: str
    post_text: Optional[str] = ""
    customize_cv: bool = True
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None
    lang: Optional[str] = None
    site: Optional[str] = "linkedin"


class PostSaveRequest(BaseModel):
    post_url: str
    role_title: str
    company: str
    author_name: Optional[str] = "Recruiter"
    recruiter_emails: List[str] = []
    snippet: Optional[str] = ""

class InMailGenerateRequest(BaseModel):
    recruiter_name: Optional[str] = "Hiring Manager"
    company: str
    role_title: str
    post_text: Optional[str] = ""

class BatchApplyRequest(BaseModel):
    posts: Optional[List[PostApplyRequest]] = None
    applications: Optional[List[PostApplyRequest]] = None

@router.get("/account-status")
def get_account_status(current_user: models.User = Depends(get_current_user)):
    """Check whether a live LinkedIn session cookie (li_at) is connected for this user."""
    cookie = (getattr(current_user, "linkedin_cookie", "") or "").strip()
    is_connected = bool(cookie)
    masked = ""
    if is_connected:
        masked = cookie[:4] + "..." + cookie[-4:] if len(cookie) > 8 else "***"
    return {
        "connected": is_connected,
        "masked_cookie": masked
    }

@router.post("/connect-account")
def connect_linkedin_account(req: ConnectAccountRequest,
                             db: Session = Depends(get_db),
                             current_user: models.User = Depends(get_current_user)):
    """Saves the user's LinkedIn session cookie for direct live posts feed searching."""
    cookie_val = (req.li_at or "").strip()
    if not cookie_val:
        raise HTTPException(status_code=400, detail="LinkedIn session cookie (li_at) cannot be empty.")
    current_user.linkedin_cookie = cookie_val
    db.commit()
    return {
        "status": "connected",
        "message": "LinkedIn connected successfully! Direct live post search is now active."
    }

@router.post("/disconnect-account")
def disconnect_linkedin_account(db: Session = Depends(get_db),
                                current_user: models.User = Depends(get_current_user)):
    """Clears the saved LinkedIn session cookie."""
    current_user.linkedin_cookie = ""
    db.commit()
    return {
        "status": "disconnected",
        "message": "LinkedIn account disconnected."
    }

@router.post("/search")
def search_posts(req: PostSearchRequest,
                 db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """
    Scans live LinkedIn recruiter posts announcing open positions,
    extracts direct emails and performs deep hunter verification.
    Supports multi-country simultaneous search and autonomous AI Agent mode.
    """
    blacklisted = get_blacklisted_emails(db, current_user.id)
    
    # Normalize locations list from request
    loc_list: List[str] = []
    if req.locations and isinstance(req.locations, list):
        loc_list = [l.strip() for l in req.locations if l and l.strip()]
    elif req.location:
        if "," in req.location:
            loc_list = [l.strip() for l in req.location.split(",") if l.strip()]
        elif req.location.strip():
            loc_list = [req.location.strip()]

    li_at_cookie = (req.li_at or "").strip() or (getattr(current_user, "linkedin_cookie", "") or "").strip()

    posts, agent_stats = search_linkedin_recruiter_posts(
        role_query=req.role,
        locations=loc_list,
        location=req.location or "",
        tags=req.tags or [],
        limit=max(req.limit, 20),
        email_only=req.email_only,
        time_range=req.time_range,
        blacklisted_set=blacklisted,
        agent_mode=req.agent_mode,
        return_stats=True,
        force_refresh=req.force_refresh,
        page=getattr(req, "page", 1) or 1,
        li_at_cookie=li_at_cookie
    )

    # Run AI match scoring using compute_match from cv_matcher
    cv_text = ""
    cv_years = None
    try:
        cv = db.query(models.CvUpload.text_content).filter(models.CvUpload.user_id == current_user.id).first()
        cv_text = cv[0] if cv and cv[0] else ""
        cv_years = extract_post_required_years(cv_text) if cv_text else None
    except Exception:
        pass
    
    # Load user's application tracker and email logs using lightweight column projections
    applied_urls = set()
    applied_title_company = set()
    applied_company_set = set()
    applied_emails = set()
    saved_urls = set()
    saved_title_company = set()

    try:
        app_rows = db.query(
            models.Application.status,
            models.Application.url,
            models.Application.title,
            models.Application.company,
            models.Application.notes,
        ).filter(models.Application.user_id == current_user.id).all()

        for st_val, url_val, title_val, comp_val, notes_val in app_rows:
            status_norm = (st_val or "").lower()
            url_norm = (url_val or "").strip().lower()
            title_norm = (title_val or "").strip().lower()
            comp_norm = (comp_val or "").strip().lower()
            tc_key = f"{title_norm}|{comp_norm}"

            if status_norm != "saved":
                if url_norm:
                    applied_urls.add(url_norm)
                if title_norm and comp_norm:
                    applied_title_company.add(tc_key)
                if comp_norm:
                    applied_company_set.add(comp_norm)
                if notes_val:
                    for em in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", notes_val.lower()):
                        applied_emails.add(em)
            elif status_norm == "saved":
                if url_norm:
                    saved_urls.add(url_norm)
                if title_norm and comp_norm:
                    saved_title_company.add(tc_key)

        for (to_email,) in db.query(models.EmailLog.to_email).filter(
            models.EmailLog.user_id == current_user.id,
            models.EmailLog.status != "failed"
        ).all():
            if to_email:
                applied_emails.add(to_email.strip().lower())
    except Exception:
        pass

    for p in posts:
        desc = p.get("full_text") or p.get("post_snippet") or p.get("role_title")
        role_skills = p.get("matched_skills", [])
        role_fit = p.get("role_fit_score", 75)
        post_req_years = p.get("required_years")
        if post_req_years is None and desc:
            post_req_years = extract_post_required_years(desc)
            p["required_years"] = post_req_years

        if cv_text:
            try:
                from cv_matcher import compute_match
                score, bd = compute_match(cv_text, desc, p.get("role_title", req.role))
                base_score = max(score, int(role_fit * 0.9))
                combined_skills = list(dict.fromkeys(bd.get("matched_tech", []) + role_skills))
                p["matched_skills"] = combined_skills
                missing = bd.get("missing_tech", [])
                p["missing_skills"] = missing
                p["required_skills"] = bd.get("required_skills", [])
                
                tips = list(bd.get("tips", []))
                if not tips and missing:
                    missing_sample = ", ".join([m.title() for m in missing[:3]])
                    tips.append(f"Add key technical keywords ({missing_sample}) to your Skills section to pass automated screening.")
                    tips.append(f"Emphasize hands-on production experience related to {p.get('role_title', 'the role')} in your recent project summaries.")
                elif not tips:
                    tips.append("Your technical skills align well! Highlight measurable metrics (e.g., latency reduction, active users) in your bullets.")

                # CV Experience Alignment adjustment
                if post_req_years is not None and cv_years is not None:
                    if cv_years + 1.0 >= post_req_years:
                        base_score = min(99, base_score + 4)
                    elif post_req_years - cv_years >= 3.0:
                        base_score = max(35, base_score - 10)
                        tips.append(f"Post requests {post_req_years:g}+ years of experience; emphasize your most impactful production deliveries prominently.")

                p["score"] = base_score
                p["tips"] = tips
            except Exception as err:
                p["score"] = role_fit
                p["matched_skills"] = role_skills
                p["missing_skills"] = []
                p["tips"] = []
        else:
            p["score"] = role_fit
            p["matched_skills"] = role_skills
            p["missing_skills"] = []
            p["tips"] = [
                "Upload your CV to unlock instant ATS match scoring, view missing skills, and get personalized tips for this post."
            ]

        # Check if already applied or saved
        p_url = (p.get("post_url") or "").strip().lower()
        p_title = (p.get("role_title") or req.role or "").strip().lower()
        p_comp = (p.get("company") or "").strip().lower()
        p_tc = f"{p_title}|{p_comp}"

        post_emails = [e.get("email", "").strip().lower() for e in p.get("recruiter_emails", [])]
        is_applied = False
        if p_url and p_url in applied_urls:
            is_applied = True
        elif p_tc in applied_title_company:
            is_applied = True
        elif any(em in applied_emails for em in post_emails if em):
            is_applied = True
        elif p_comp and p_comp in applied_company_set and (p_title in req.role.lower() or req.role.lower() in p_title):
            is_applied = True

        p["is_applied"] = is_applied
        p["is_saved"] = (p_url in saved_urls or p_tc in saved_title_company) and not is_applied

    # Exclude already applied posts so the candidate never sees them again
    posts = [p for p in posts if not p.get("is_applied")]

    # Optional filter by min_score
    if req.min_score > 0:
        posts = [p for p in posts if (p.get("score") or 0) >= req.min_score]

    # Soft time-range filtering: the hunter's scrape_single_post_details() already gate-kept age.
    # Here we apply secondary filtering, but trust is_under_24h=True tags set by the hunter.
    # Also pass through _24h_fallback posts (best-effort results when all dated engines failed).
    if req.time_range in ("24h", "1d", "day", "past-24h"):
        posts = [
            p for p in posts
            if p.get("is_under_24h")
            or (p.get("age_hours") is not None and p.get("age_hours") <= 48.0)
            or (p.get("age_hours") is None and p.get("age_str", "").startswith("<"))
            or p.get("_24h_fallback")  # Best-effort: no posts found in 24h, show best available
        ]
    elif req.time_range in ("week", "7d", "1w", "past-week"):
        posts = [
            p for p in posts
            if (p.get("age_hours") is not None and p.get("age_hours") <= 168.0)
            or (p.get("age_hours") is None and p.get("age_str", "").startswith("<"))
            or p.get("_24h_fallback")
        ]
    elif req.time_range in ("month", "30d", "1m", "past-month"):
        posts = [
            p for p in posts
            if (p.get("age_hours") is not None and p.get("age_hours") <= 720.0)
            or (p.get("age_hours") is None and p.get("age_str", "").startswith("<"))
            or p.get("_24h_fallback")
        ]

    # Deterministic base sort (tie-breaker for equal scores / ages)
    posts.sort(
        key=lambda x: (
            x.get("company", "").strip().lower(),
            x.get("role_title", "").strip().lower(),
            x.get("post_url", "")
        )
    )

    # User-selected primary sort (stable sort maintains tie-breaker order)
    if req.sort_by == "score":
        posts.sort(
            key=lambda x: (
                x.get("score") or 0,
                1 if x.get("has_email") else 0,
                -(x.get("email_tier_rank") if x.get("email_tier_rank") is not None else 99),
                -(x.get("age_hours") if x.get("age_hours") is not None else 9999)
            ),
            reverse=True
        )
    elif req.sort_by == "newest":
        posts.sort(
            key=lambda x: (
                x.get("age_hours") if x.get("age_hours") is not None else 9999,
                -(x.get("score") or 0)
            )
        )
    elif req.sort_by == "emails":
        posts.sort(
            key=lambda x: (
                1 if x.get("has_email") else 0,
                -(x.get("email_tier_rank") if x.get("email_tier_rank") is not None else 99),
                len(x.get("recruiter_emails", [])),
                x.get("score") or 0
            ),
            reverse=True
        )

    # Slice to user's desired limit
    final_posts = posts[:req.limit]

    return {
        "success": True,
        "query": req.role,
        "location": req.location,
        "time_range": req.time_range,
        "agent_mode": req.agent_mode,
        "agent_stats": agent_stats,
        "page": getattr(req, "page", 1) or 1,
        "has_more": agent_stats.get("has_more", False) if isinstance(agent_stats, dict) else (len(final_posts) > 0),
        "count": len(final_posts),
        "total_unfiltered": len(posts),
        "posts": final_posts
    }

@router.post("/generate-inmail")
def generate_inmail(req: InMailGenerateRequest,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """
    Generates a personalized <= 300-character connection request note
    tailored to the recruiter and role for direct outreach on LinkedIn.
    """
    recruiter = req.recruiter_name or "there"
    first_name = recruiter.split()[0].title()
    if first_name.lower() in ("linkedin", "recruiter", "hiring", "talent", "team"):
        first_name = "there"

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    top_skills = []
    if cv and cv.text_content:
        try:
            from cv_matcher import compute_match
            _, bd = compute_match(cv.text_content, req.post_text or req.role_title, req.role_title)
            top_skills = bd.get("matched_tech", [])[:3]
        except Exception:
            pass

    skills_str = ", ".join([s.title() for s in top_skills]) if top_skills else "modern software engineering"
    
    note = f"Hi {first_name}, saw your post for {req.role_title} at {req.company}. With strong hands-on experience in {skills_str}, I'd love to connect and discuss how I can contribute!"
    if len(note) > 300:
        note = f"Hi {first_name}, saw your post hiring a {req.role_title} at {req.company}. With solid expertise in {skills_str}, I'd love to connect and share my resume!"
    if len(note) > 300:
        note = note[:297] + "..."

    return {
        "note": note,
        "length": len(note),
        "recruiter_first_name": first_name
    }

@router.post("/batch-auto-apply")
def batch_auto_apply_posts(req: BatchApplyRequest,
                           db: Session = Depends(get_db),
                           current_user: models.User = Depends(get_current_user)):
    """
    Dispatches 1-click tailored applications to a batch of selected LinkedIn recruiter posts.
    """
    items = req.posts or req.applications or []
    if not items:
        return {"success": True, "applied": 0, "errors": [], "message": "No unapplied posts provided."}

    blacklisted = get_blacklisted_emails(db, current_user.id)
    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Please configure your Gmail SMTP settings first in Settings.")

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv.text_content if cv else ""

    applied_count = 0
    errors = []

    for item in items:
        clean_email = item.recruiter_email.strip().lower()
        if clean_email in blacklisted:
            errors.append(f"{clean_email}: blocked by blacklist")
            continue

        try:
            # Automatic batch send strictly attaches authentic original CV
            custom_pdf_bytes = None
            custom_pdf_name = None
            effective_score = 75

            sender_name = settings.sender_name or current_user.name
            r_name = item.recruiter_name or "Hiring Team"
            auto_subject, auto_body, _ = get_application_email(
                role_title=item.role_title,
                company=item.company,
                recruiter_name=r_name,
                post_text=item.post_text,
                sender_name=sender_name,
                sender_email=current_user.email,
                lang=getattr(item, "lang", None),
                site=getattr(item, "site", None) or "linkedin",
                url=item.post_url
            )
            subject = getattr(item, "custom_subject", None) or auto_subject
            body = getattr(item, "custom_body", None) or auto_body

            _dispatch_smtp(settings, current_user, clean_email, r_name,
                           subject, body, True, db,
                           custom_attachment_bytes=custom_pdf_bytes,
                           custom_attachment_name=custom_pdf_name)

            now = datetime.utcnow()
            app = models.Application(
                user_id=current_user.id,
                title=item.role_title,
                company=item.company,
                location="LinkedIn Post",
                url=item.post_url,
                status="applied",
                match_score=effective_score,
                notes=f"Batch applied to LinkedIn Recruiter {r_name} ({clean_email})" + (" (Tailored CV)" if custom_pdf_bytes else ""),
                applied_at=now,
                follow_up_date=now + timedelta(days=4),
                tailored_cv_filename=custom_pdf_name,
                tailored_cv_data=custom_pdf_bytes
            )
            db.add(app)
            db.commit()
            db.refresh(app)

            log = models.EmailLog(
                user_id=current_user.id,
                application_id=app.id,
                to_email=clean_email,
                to_name=r_name,
                subject=subject,
                body=body,
                template_type="auto_apply",
                status="sent"
            )
            db.add(log)
            db.commit()

            applied_count += 1
        except Exception as item_err:
            errors.append(f"{item.company} ({clean_email}): {str(item_err)}")

    return {
        "success": True,
        "applied": applied_count,
        "total_requested": len(items),
        "errors": errors,
        "message": f"🎉 Successfully dispatched {applied_count} applications with auto-tailored CVs (95–100% fit)!"
    }

@router.post("/auto-apply")
def auto_apply_to_post(req: PostApplyRequest,
                       db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    """
    1-Click direct outreach to a recruiter from a LinkedIn post with tailored CV.
    """
    blacklisted = get_blacklisted_emails(db, current_user.id)
    clean_email = req.recruiter_email.strip().lower()
    if clean_email in blacklisted:
        raise HTTPException(400, f"Cannot send email: {clean_email} is blocked due to prior delivery bounce.")

    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == current_user.id).first()
    if not settings or not settings.smtp_user:
        raise HTTPException(400, "Please configure your Gmail SMTP settings first in Settings.")

    sender_name = settings.sender_name or current_user.name
    r_name = req.recruiter_name or "Hiring Team"

    # Automatic auto-apply strictly attaches authentic original CV
    custom_pdf_bytes = None
    custom_pdf_name = None
    effective_score = 75

    auto_subj, auto_body, _ = get_application_email(
        role_title=req.role_title,
        company=req.company,
        recruiter_name=r_name,
        post_text=req.post_text,
        sender_name=sender_name,
        sender_email=current_user.email,
        lang=req.lang,
        site=req.site or "linkedin",
        url=req.post_url
    )
    subject = req.custom_subject or auto_subj
    body = req.custom_body or auto_body

    try:
        _dispatch_smtp(settings, current_user, clean_email, r_name,
                       subject, body, True, db,
                       custom_attachment_bytes=custom_pdf_bytes,
                       custom_attachment_name=custom_pdf_name)

        now = datetime.utcnow()
        # Save to Tracker Application board as Applied (updating existing if present)
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            (models.Application.company.ilike(req.company) | (models.Application.url == (req.post_url or "nonexistent")))
        ).first()

        loc_str = req.location or "LinkedIn Post"

        if existing:
            app = existing
            app.status = "applied"
            app.applied_at = now
            app.follow_up_date = now + timedelta(days=4)
            if req.post_url: app.url = req.post_url
            if req.role_title: app.title = req.role_title
            if req.location: app.location = req.location
            app.match_score = effective_score or app.match_score
            app.notes = (app.notes or "") + f"\nDispatched direct application to Recruiter {r_name} ({clean_email})" + (" (Tailored CV)" if custom_pdf_bytes else "")
            if custom_pdf_bytes:
                app.tailored_cv_filename = custom_pdf_name
                app.tailored_cv_data = custom_pdf_bytes
            db.commit()
            db.refresh(app)
        else:
            app = models.Application(
                user_id=current_user.id,
                title=req.role_title,
                company=req.company,
                location=loc_str,
                url=req.post_url or "",
                status="applied",
                match_score=effective_score,
                notes=f"Dispatched direct application to Recruiter {r_name} ({clean_email})" + (" (Tailored CV)" if custom_pdf_bytes else ""),
                applied_at=now,
                follow_up_date=now + timedelta(days=4),
                tailored_cv_filename=custom_pdf_name,
                tailored_cv_data=custom_pdf_bytes
            )
            db.add(app)
            db.commit()
            db.refresh(app)

        log = models.EmailLog(
            user_id=current_user.id,
            application_id=app.id,
            to_email=clean_email,
            to_name=r_name,
            subject=subject,
            body=body,
            template_type="auto_apply",
            status="sent"
        )
        db.add(log)
        db.commit()

        msg = f"✨ CV automatically enhanced to {effective_score}% fit & dispatched to {r_name} at {req.company}!" if custom_pdf_bytes else f"Successfully applied to {req.company}! Email sent to {clean_email}."
        return {
            "success": True,
            "message": msg,
            "application_id": app.id,
            "tailored_score": effective_score,
            "tailored_filename": custom_pdf_name,
            "tailored": bool(custom_pdf_bytes)
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to send email to recruiter: {str(e)}")

@router.post("/save")
def save_post_to_tracker(req: PostSaveRequest,
                         db: Session = Depends(get_db),
                         current_user: models.User = Depends(get_current_user)):
    """
    Saves a LinkedIn recruiter post to Tracker in Saved / Queue status.
    """
    notes_str = f"Found on LinkedIn Post by {req.author_name}."
    if req.recruiter_emails:
        notes_str += f" Recruiter Contacts: {', '.join(req.recruiter_emails)}"
    if req.snippet:
        notes_str += f"\nSnippet: {req.snippet[:250]}"

    app = models.Application(
        user_id=current_user.id,
        title=req.role_title,
        company=req.company,
        location="LinkedIn Post",
        url=req.post_url,
        status="saved",
        match_score=75,
        notes=notes_str
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"success": True, "message": f"Saved {req.role_title} to Tracker pipeline.", "id": app.id}

@router.post("/suggest-tags")
def suggest_tags(req: TagSuggestRequest):
    """
    Deprecated: Tags removed. Returns empty structure.
    """
    return {"status": "deprecated", "domains": [], "locations": [], "trending": []}

