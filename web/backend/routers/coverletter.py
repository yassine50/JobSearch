
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..utils import ensure_project_root_on_path
import re

ensure_project_root_on_path()

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
    except Exception:
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

from ..email_templates import detect_language

FR_STYLES = {
    "professional": {
        "opening": "Je vous soumets par la présente ma candidature pour le poste de {job_title} au sein de {company}.",
        "body_p1": "Fort d'une solide expérience et d'une maîtrise de {skills}, j'ai développé des compétences pointues directement en adéquation avec les exigences de votre organisation.",
        "closing": "Je serais ravi d'échanger avec vous afin d'approfondir la manière dont mon parcours peut répondre à vos enjeux de développement.",
    },
    "casual": {
        "opening": "C'est avec grand enthousiasme que je candidate au poste de {job_title} chez {company}.",
        "body_p1": "Passionné par le développement et fort d'une expérience concrète avec {skills}, je serais ravi d'apporter mon dynamisme et mon savoir-faire à vos projets.",
        "closing": "Je reste à votre entière disposition pour un échange informel autour de votre vision et de vos besoins.",
    },
    "technical": {
        "opening": "Spécialisé dans le développement logiciel performant et maîtrisant {skills}, je vous propose ma candidature pour le poste de {job_title} au sein de {company}.",
        "body_p1": "Mon parcours m'a permis de concevoir des architectures robustes, maintenables et évolutives, en accord étroit avec vos critères techniques.",
        "closing": "Je serais ravi de vous présenter concrètement mes réalisations lors d'un entretien technique.",
    },
}

@router.post("/generate")
def generate(req: CLRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv_rec.text_content if cv_rec else ""

    top_skills = _extract_top_skills(cv_text, req.job_description)
    skills_str = ", ".join(top_skills) if top_skills else "mes compétences clés"
    years = _extract_years(cv_text)

    lang = detect_language(f"{req.job_title} {req.company} {req.job_description}")

    if lang == "fr":
        fr_style = FR_STYLES.get(req.style, FR_STYLES["professional"])
        fr_opening = fr_style["opening"].format(job_title=req.job_title, company=req.company, skills=skills_str)
        fr_p1 = fr_style["body_p1"].format(skills=skills_str)
        letter = f"""Madame, Monsieur,

{fr_opening}

{fr_p1}

Au cours de mon parcours professionnel, j'ai mené à bien des projets d'envergure, alliant rigueur méthodologique, autonomie et recherche constante de la qualité. Votre organisation, {req.company}, se distingue par son dynamisme et son excellence, des valeurs dans lesquelles je me reconnais pleinement.

{fr_style["closing"]}

En vous remerciant pour l'attention portée à ma candidature, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

{current_user.name}
{current_user.email}
"""
    else:
        style = STYLES.get(req.style, STYLES["professional"])
        skills_en = ", ".join(top_skills) if top_skills else "my core skills"
        opening = style["opening"].format(job_title=req.job_title, company=req.company, skills=skills_en)

        letter = f"""Dear Hiring Manager,

{opening}

With {years} of experience and a strong background in {skills_en}, I have consistently delivered impactful results throughout my career. My expertise aligns closely with what you are looking for in this role.

In my previous roles, I have demonstrated the ability to work both independently and collaboratively, taking ownership of complex challenges and delivering solutions that create real value. I am particularly drawn to {req.company} because of its reputation for innovation and excellence.

I am confident that my skills and dedication make me a strong candidate for the {req.job_title} position. {style["closing"]}

Thank you for your time and consideration. I look forward to the possibility of contributing to your team.

Sincerely,
{current_user.name}
{current_user.email}
"""

    return {"letter": letter, "skills_used": top_skills, "style": req.style,
            "job_title": req.job_title, "company": req.company, "language": lang}
