
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models
from ..database import get_db
from ..auth import get_current_user
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

router = APIRouter(prefix="/api/coverletter", tags=["coverletter"])

class CLRequest(BaseModel):
    job_title: str
    company: str
    job_description: str
    style: str = "professional"  # professional / casual / technical

def _extract_top_skills(cv_text: str, jd: str, n=5) -> list:
    try:
        from cv_matcher import _extract_skills, TECH_SKILLS
        cv_skills = _extract_skills(cv_text, TECH_SKILLS)
        jd_skills = _extract_skills(jd, TECH_SKILLS)
        matched = list(cv_skills & jd_skills)
        return sorted(matched)[:n] if matched else list(cv_skills)[:n]
    except:
        words = re.findall(r"\b[A-Za-z+#]{2,}\b", cv_text)
        return list(set(words))[:n]

def _extract_years(cv_text: str) -> str:
    m = re.search(r"(\d+)\+?\s*years?", cv_text, re.I)
    return f"{m.group(1)}+ years" if m else "several years"

STYLES = {
    "professional": {
        "opening": "I am writing to express my strong interest in the {job_title} position at {company}.",
        "tone": "formal and results-driven",
        "closing": "I would welcome the opportunity to discuss how my experience aligns with your needs.",
    },
    "casual": {
        "opening": "I was excited to come across the {job_title} role at {company} — it looks like a perfect fit!",
        "tone": "friendly and enthusiastic",
        "closing": "I would love to chat about how I can bring value to your team.",
    },
    "technical": {
        "opening": "As a specialist with hands-on expertise in {skills}, I am eager to apply for the {job_title} role at {company}.",
        "tone": "technical and precise",
        "closing": "I would welcome a technical discussion to demonstrate how my expertise directly addresses your requirements.",
    },
}

@router.post("/generate")
def generate(req: CLRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv_rec.text_content if cv_rec else ""

    top_skills = _extract_top_skills(cv_text, req.job_description)
    skills_str = ", ".join(top_skills) if top_skills else "my core skills"
    years = _extract_years(cv_text)
    style = STYLES.get(req.style, STYLES["professional"])

    opening = style["opening"].format(job_title=req.job_title, company=req.company, skills=skills_str)

    letter = f"""Dear Hiring Manager,

{opening}

With {years} of experience and a strong background in {skills_str}, I have consistently delivered impactful results throughout my career. My expertise aligns closely with what you are looking for in this role.

In my previous roles, I have demonstrated the ability to work both independently and collaboratively, taking ownership of complex challenges and delivering solutions that create real value. I am particularly drawn to {req.company} because of its reputation for innovation and excellence.

I am confident that my skills and dedication make me a strong candidate for the {req.job_title} position. {style["closing"]}

Thank you for your time and consideration. I look forward to the possibility of contributing to your team.

Sincerely,
{current_user.name}
{current_user.email}
"""
    return {"letter": letter, "skills_used": top_skills, "style": req.style,
            "job_title": req.job_title, "company": req.company}
