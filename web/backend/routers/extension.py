import base64
import io
import json
import os
import re
import zipfile
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db
from .cv import _get_active_cv, _analyze_cv_text

router = APIRouter(prefix="/api/extension", tags=["extension"])


# ─── Helpers to extract clean structured candidate fields from CV ─────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[\w]+\.)?linkedin\.com/in/[a-zA-Z0-9_\-]+/?", re.I)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[a-zA-Z0-9_\-]+/?", re.I)
_URL_RE = re.compile(r"https?://[^\s,;)>\"]+", re.I)
_DATE_STR_RE = re.compile(
    r"\b(19\d{2}|20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december|present|current|now)\b",
    re.I,
)
_KNOWN_COUNTRIES = {
    "romania", "roumanie", "tunisia", "tunisie", "france", "germany",
    "united kingdom", "uk", "united states", "usa", "canada", "spain",
    "italy", "netherlands", "belgium", "switzerland", "morocco",
    "united arab emirates", "uae",
}


def _is_date_str(s: str) -> bool:
    return bool(s and _DATE_STR_RE.search(str(s)))


def _normalize_url(u: str) -> str:
    if not u:
        return ""
    u = u.strip().rstrip(".,;)")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def _build_candidate_profile(user: models.User, cv: Optional[models.CvUpload]) -> Dict[str, Any]:
    text = (cv.text_content if cv else "") or ""
    structured: Dict[str, Any] = {}
    if cv and text:
        try:
            from web.backend.tailoring import extract_cv_structure
            structured, _ = extract_cv_structure(cv)
        except Exception:
            structured = {}

    analysis = _analyze_cv_text(text) if text else {}
    contact = structured.get("contact") or {}
    links = structured.get("links") or {}

    full_name = (structured.get("name") or user.name or "").strip()
    if not full_name or "@" in full_name:
        full_name = (user.name or "").strip()
    name_parts = [p for p in full_name.split() if p]
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    email = (contact.get("email") or "").strip()
    if not email:
        m = _EMAIL_RE.search(text)
        email = m.group(0) if m else user.email

    phone = (contact.get("phone") or "").strip()
    if not phone:
        for m in _PHONE_RE.finditer(text[:1500]):
            cand = m.group(0).strip()
            digits = re.sub(r"\D", "", cand)
            if 8 <= len(digits) <= 15:
                phone = cand
                break

    location = (contact.get("location") or "").strip()
    if not location and analysis.get("locations_found"):
        location = analysis["locations_found"][0]

    loc_parts = [p.strip() for p in location.split(",") if p.strip()]
    city = ""
    country = ""
    if len(loc_parts) >= 2:
        city = loc_parts[0]
        country = loc_parts[-1]
    elif len(loc_parts) == 1:
        if loc_parts[0].lower() in _KNOWN_COUNTRIES:
            country = loc_parts[0]
            city = ""
        else:
            city = loc_parts[0]
            country = analysis.get("suggested_countries", [""])[0] if analysis.get("suggested_countries") else ""

    linkedin_url = _normalize_url(links.get("linkedin") or "")
    if not linkedin_url:
        m = _LINKEDIN_RE.search(text)
        if m:
            linkedin_url = _normalize_url(m.group(0))

    github_url = _normalize_url(links.get("github") or "")
    if not github_url:
        m = _GITHUB_RE.search(text)
        if m:
            github_url = _normalize_url(m.group(0))

    portfolio_url = _normalize_url(links.get("portfolio") or links.get("website") or "")
    if not portfolio_url:
        for m in _URL_RE.finditer(text):
            u = m.group(0)
            if "linkedin.com" not in u.lower() and "github.com" not in u.lower():
                portfolio_url = _normalize_url(u)
                break

    experiences = structured.get("experience") or []
    educations = structured.get("education") or []

    current_title = (
        structured.get("headline")
        or (experiences[0].get("title") if experiences else "")
        or analysis.get("primary_title")
        or analysis.get("title")
        or "Software Engineer"
    ).strip()

    first_org = (experiences[0].get("org") if experiences else "").strip()
    current_company = "" if _is_date_str(first_org) else first_org
    years_exp = analysis.get("years_experience") or (max(1, len(experiences) * 2) if experiences else 3)

    skills_list = structured.get("skills") or analysis.get("skills") or []
    summary = (structured.get("summary") or "").strip()
    if not summary and skills_list:
        summary = (
            f"{current_title} with {years_exp}+ years of hands-on experience building production solutions "
            f"using {', '.join(skills_list[:6])}."
        )

    highest_edu = educations[0] if educations else {}
    degree = (highest_edu.get("title") or "Bachelor's Degree in Computer Science").strip()
    university = (highest_edu.get("org") or "").strip()
    grad_date = (highest_edu.get("date_text") or "").strip()

    # Resume PDF binary (base64) for automatic <input type="file"> injection
    resume_b64 = None
    resume_filename = (cv.filename if cv and cv.filename else "Resume.pdf")
    if cv and getattr(cv, "file_data", None):
        resume_b64 = base64.b64encode(cv.file_data).decode("ascii")

    clean_experiences = []
    for e in experiences[:6]:
        org_str = (e.get("org") or e.get("company") or "").strip()
        date_str = (e.get("date_text") or (org_str if _is_date_str(org_str) else "")).strip()
        bullets = e.get("bullets") or []
        clean_experiences.append({
            "title": (e.get("title") or "").strip(),
            "company": "" if _is_date_str(org_str) else org_str,
            "location": (e.get("location") or "").strip(),
            "date_text": date_str,
            "description": "\n".join(f"• {b}" for b in bullets if b),
        })

    clean_educations = []
    for e in educations[:6]:
        org_str = (e.get("org") or e.get("school") or "").strip()
        date_str = (e.get("date_text") or (org_str if _is_date_str(org_str) else "")).strip()
        clean_educations.append({
            "degree": (e.get("title") or e.get("degree") or "").strip(),
            "school": "" if _is_date_str(org_str) else org_str,
            "date_text": date_str,
        })

    is_currently_employed = any(
        re.search(r"\b(present|current|now|ongoing|actuel)\b", exp.get("date_text", ""), re.I)
        for exp in clean_experiences
    )

    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "location": location,
        "city": city,
        "country": country,
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "portfolio_url": portfolio_url,
        "current_title": current_title,
        "current_company": current_company if is_currently_employed else "",
        "is_currently_employed": is_currently_employed,
        "years_experience": years_exp,
        "summary": summary,
        "skills": skills_list[:25],
        "skills_Joined": ", ".join(skills_list[:20]),
        "degree": degree,
        "university": university,
        "graduation_date": grad_date,
        "experiences": clean_experiences,
        "educations": clean_educations,
        "defaults": {
            "work_authorization": "Yes",
            "requires_sponsorship": "No",
            "willing_to_relocate": "Yes",
            "remote_preference": "Remote / Hybrid",
            "notice_period": "2 weeks / Immediate",
            "how_did_you_hear": "Company Careers Page / LinkedIn",
            "gender": "Decline to self-identify",
            "veteran_status": "I am not a protected veteran",
            "disability_status": "I do not wish to answer",
            "ethnicity": "Decline to self-identify",
        },
        "resume_filename": resume_filename,
        "resume_base64": resume_b64,
        "has_cv": bool(cv and text),
        "active_persona_id": cv.id if cv else None,
        "active_persona_name": (cv.persona_name or cv.filename) if cv else None,
    }


@router.get("/profile")
def get_extension_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Returns structured autofill fields, active CV PDF base64, and available CV personas."""
    active_cv = _get_active_cv(db, current_user.id)
    profile = _build_candidate_profile(current_user, active_cv)

    personas = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == current_user.id)
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .all()
    )
    profile["personas"] = [
        {
            "id": p.id,
            "persona_name": p.persona_name or p.filename or "Resume",
            "filename": p.filename,
            "is_active": bool(p.is_active),
        }
        for p in personas
    ]
    return profile


class QuestionItem(BaseModel):
    id: str
    label: str
    field_type: str = "textarea"  # text | textarea | select | radio
    options: Optional[List[str]] = None


class AutofillJobRequest(BaseModel):
    job_title: str = ""
    company: str = ""
    job_description: str = ""
    job_url: str = ""
    tailor_cv: bool = True
    questions: List[QuestionItem] = []


def _answer_custom_question(
    q: QuestionItem,
    profile: Dict[str, Any],
    job_title: str,
    company: str,
    matched_skills: List[str],
    cover_pitch: str,
) -> str:
    label_l = (q.label or "").lower().strip()
    skills_str = ", ".join((matched_skills or profile.get("skills") or ["modern software engineering"])[:6])
    role_str = job_title or profile.get("current_title") or "this role"
    comp_str = company or "your team"
    years = profile.get("years_experience") or 3

    # If options are provided (select / radio), pick the best matching option
    if q.options:
        opts = [o.strip() for o in q.options if o and o.strip()]
        if any(k in label_l for k in ["english", "language", "proficiency", "fluency", "cefr", "level"]) or any(
            re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", o.lower()) for o in opts
        ):
            for pat in [r"\bc1\b", r"\badvanced\b", r"\bc2\b", r"\b(fluent|proficient)\b", r"\bb2\b"]:
                for o in opts:
                    if re.search(pat, o.lower()) and "pre intermediate" not in o.lower() and "pre-intermediate" not in o.lower():
                        return o
        if any(k in label_l for k in ["authorized", "legally", "eligible to work", "right to work", "relocat", "remote"]):
            for o in opts:
                if o.lower().startswith("yes"):
                    return o
        if any(k in label_l for k in ["sponsorship", "visa", "require sponsor", "need sponsor"]):
            for o in opts:
                if o.lower().startswith("no"):
                    return o
        if any(k in label_l for k in ["gender", "veteran", "disability", "race", "ethnic", "hispanic"]):
            for o in opts:
                if any(w in o.lower() for w in ["decline", "prefer not", "wish not", "do not wish", "not to"]):
                    return o
        if any(k in label_l for k in ["hear about", "source", "where did you find"]):
            for o in opts:
                if any(w in o.lower() for w in ["linkedin", "job board", "website", "career", "other"]):
                    return o

    # Years of experience & project history questions grounded strictly in the candidate's profile
    exps = profile.get("experiences") or []
    exp0 = next((e for e in exps if re.search(r"developer|engineer|architect|lead|scientist|analyst|manager|designer", e.get("title", ""), re.I)), exps[0] if exps else {})
    exp_role = (exp0.get("title") or profile.get("current_title") or "Software Engineer").strip()
    exp_comp = (exp0.get("company") or profile.get("current_company") or "").strip()
    at_comp_clause = f" at {exp_comp}" if exp_comp else ""
    comp_clean = comp_str if comp_str.lower() != role_str.lower() and comp_str.lower() not in ("the hiring team", "company") else "your engineering team"

    if re.search(r"\b(when\s+was\s+the\s+last\s+time|when\s+did\s+you\s+last|last\s+time\s+you\s+worked|how\s+recently)\b", label_l):
        return (
            f"I most recently worked with these technologies during my role as {exp_role}{at_comp_clause}, "
            f"where I designed and delivered production features using {skills_str}."
        )

    if any(k in label_l for k in ["how many years", "years of experience", "years experience"]):
        if q.field_type in ("number", "text") or len(label_l) < 95:
            return str(int(years))
        return f"{years}+ years of hands-on experience."

    if re.search(r"\b(have\s+you\s+worked\s+on|have\s+you\s+ever\s+worked|share\s+an\s+example|including\s+your\s+role|key\s+technologies\s+used)\b", label_l):
        exp_desc = (exp0.get("description") or "").strip()
        first_bullet = exp_desc.split("\n")[0].lstrip("• ").strip() if exp_desc else ""
        example_clause = (
            f"Example: {first_bullet.rstrip('.')}. "
            if first_bullet
            else f"Example: I engineered and maintained production systems{at_comp_clause} featuring clean modular architecture, reliable API integration, and automated testing. "
        )
        return (
            f"Yes, I have hands-on experience in this area. {example_clause}"
            f"Role: {exp_role}{at_comp_clause}. Key technologies used: {skills_str}."
        )

    if re.search(r"\b(briefly\s+describe|describe\s+(?:your\s+)?(?:most\s+recent\s+|a\s+recent\s+|a\s+)?project|recent\s+project\s+involving|project\s+involving)\b", label_l):
        exp_desc = (exp0.get("description") or "").strip()
        first_bullet = exp_desc.split("\n")[0].lstrip("• ").strip() if exp_desc else ""
        if first_bullet:
            return (
                f"In my recent work as {exp_role}{at_comp_clause}, I {first_bullet[0].lower() + first_bullet[1:] if len(first_bullet) > 1 else first_bullet.rstrip('.')}. "
                f"Key technologies used: {skills_str}."
            )
        return (
            f"In my most recent project as {exp_role}{at_comp_clause}, I designed, implemented, and shipped "
            f"production software workflows using {skills_str}, focusing on performance, reliability, and maintainability."
        )

    # Salary / Compensation expectations
    if any(k in label_l for k in ["salary", "compensation", "pay expectation", "desired pay", "remuneration", "rate"]):
        if q.field_type == "number":
            return "90000"
        return "Flexible and negotiable based on the total compensation package and role responsibilities."

    # Notice period / Start date
    if any(k in label_l for k in ["notice period", "when can you start", "earliest start", "availability", "available to start"]):
        return "Available to start within 2 weeks (or immediately for urgent onboarding)."

    # Work authorization / visa
    if any(k in label_l for k in ["sponsorship", "require visa", "need a visa"]):
        return "No"
    if any(k in label_l for k in ["authorized to work", "legally authorized", "eligible to work", "right to work"]):
        return "Yes"

    # Cover letter / Why company / Why role / Additional info
    if any(k in label_l for k in ["cover letter", "why do you want", "why are you interested", "why should we", "good fit", "interest in", "what excites you", "motivation"]):
        return cover_pitch

    # Challenging project / achievement
    if any(k in label_l for k in ["project", "proud of", "challenge", "accomplishment", "achievement", "built"]):
        exp_desc = exp0.get("description") or ""
        first_bullet = exp_desc.split("\n")[0].lstrip("• ").strip() if exp_desc else ""
        base = (
            f"As a {exp_role}{at_comp_clause}, I designed and delivered production workflows using {skills_str}. "
        )
        if first_bullet:
            base += f"Specifically, I {first_bullet[0].lower() + first_bullet[1:] if len(first_bullet) > 1 else first_bullet}. "
        base += f"I would bring this same execution speed and ownership to {comp_clean} in the {role_str} role."
        return base

    # Default thoughtful professional summary answer
    return (
        f"With {years}+ years of hands-on experience as a {exp_role} "
        f"working with {skills_str}, I have delivered production software solutions{at_comp_clause} "
        f"and am ready to contribute immediately to {comp_clean} in the {role_str} role."
    )


@router.post("/autofill-job")
def autofill_for_job(
    req: AutofillJobRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Analyzes the job page the user is viewing, computes live match score,
    optionally tailors the CV PDF for the role, and answers custom screening questions.
    """
    active_cv = _get_active_cv(db, current_user.id)
    profile = _build_candidate_profile(current_user, active_cv)

    match_score = 0
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    tailored_b64 = profile.get("resume_base64")
    tailored_filename = profile.get("resume_filename") or "Resume.pdf"
    used_tailored_pdf = False

    if active_cv and active_cv.text_content and (req.job_description or req.job_title):
        try:
            from cv_matcher import compute_match
            s, bd = compute_match(active_cv.text_content, req.job_description or req.job_title, req.job_title)
            match_score = int(s or 0)
            matched_skills = bd.get("matched_tech", [])[:10]
            missing_skills = bd.get("missing_tech", [])[:6]
        except Exception:
            pass

        if req.tailor_cv:
            try:
                from web.backend.tailoring import honest_tailored_attachment
                pdf_bytes, fname, orig_s, tail_s = honest_tailored_attachment(
                    active_cv,
                    req.job_title or profile.get("current_title") or "Software Engineer",
                    req.company or "Company",
                    req.job_description or req.job_title,
                    allow_low_confidence=True,
                )
                if pdf_bytes:
                    tailored_b64 = base64.b64encode(pdf_bytes).decode("ascii")
                    tailored_filename = fname or tailored_filename
                    used_tailored_pdf = True
                    if tail_s:
                        match_score = max(match_score, int(tail_s))
            except Exception:
                pass

    skills_highlight = ", ".join((matched_skills or profile.get("skills") or ["software development"])[:5])
    role_title = req.job_title or profile.get("current_title") or "this role"
    company_name = req.company or "your team"

    cover_pitch = (
        f"Dear {company_name} Hiring Team,\n\n"
        f"I am excited to apply for the {role_title} position at {company_name}. "
        f"With {profile.get('years_experience', 3)}+ years of experience in {skills_highlight}, "
        f"I have a strong track record of building reliable, user-focused products and delivering measurable impact.\n\n"
        f"{profile.get('summary', '')}\n\n"
        f"I would welcome the opportunity to discuss how my background aligns with {company_name}'s goals. "
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{profile.get('full_name')}\n{profile.get('email')}\n{profile.get('phone')}"
    ).strip()

    question_answers: Dict[str, str] = {}
    for q in req.questions[:25]:
        question_answers[q.id] = _answer_custom_question(
            q, profile, role_title, company_name, matched_skills, cover_pitch
        )

    return {
        "profile": profile,
        "match_score": match_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "cover_letter": cover_pitch,
        "question_answers": question_answers,
        "resume_filename": tailored_filename,
        "resume_base64": tailored_b64,
        "used_tailored_pdf": used_tailored_pdf,
    }


class TrackFromExtensionRequest(BaseModel):
    title: str
    company: str
    location: str = "Remote"
    url: str = ""
    match_score: int = 0
    notes: str = "Applied via CVtoMatch Chrome Extension Autofill"


@router.post("/track")
def track_application_from_extension(
    req: TrackFromExtensionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Logs an application submitted with the Chrome Extension into the user's Tracker board."""
    existing = None
    if req.url:
        existing = (
            db.query(models.Application)
            .filter(
                models.Application.user_id == current_user.id,
                models.Application.url == req.url,
            )
            .first()
        )
    if existing:
        existing.status = "applied"
        existing.applied_at = datetime.utcnow()
        if req.match_score:
            existing.match_score = max(existing.match_score or 0, req.match_score)
        db.commit()
        return {"id": existing.id, "status": "updated", "message": "Updated existing Tracker card"}

    app_rec = models.Application(
        user_id=current_user.id,
        title=(req.title or "Job Application").strip()[:180],
        company=(req.company or "Company").strip()[:140],
        location=(req.location or "Remote").strip()[:120],
        url=(req.url or "").strip(),
        status="applied",
        match_score=req.match_score or 0,
        notes=req.notes or "Applied via CVtoMatch Chrome Extension Autofill",
        follow_up_date=datetime.utcnow() + timedelta(days=4),
    )
    db.add(app_rec)
    db.commit()
    db.refresh(app_rec)
    return {"id": app_rec.id, "status": "created", "message": "Saved to Application Tracker"}


@router.get("/download.zip")
def download_extension_zip():
    """Packages the `chrome-extension/` folder into a ready-to-install ZIP archive."""
    ext_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "chrome-extension")
    )
    if not os.path.isdir(ext_dir):
        raise HTTPException(404, "Chrome extension directory not found on server.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(ext_dir):
            for file in files:
                if file.startswith("."):
                    continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, ext_dir)
                zf.write(abs_path, arcname=os.path.join("CVtoMatch-Autofill-Extension", rel_path))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="CVtoMatch-Autofill-Extension.zip"'
        },
    )
