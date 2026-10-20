
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..utils import ensure_project_root_on_path
from ..email_templates import detect_language
import re

ensure_project_root_on_path()

router = APIRouter(prefix="/api/coverletter", tags=["coverletter"])


class CLRequest(BaseModel):
    job_title: str
    company: str
    job_description: str
    style: str = "professional"  # professional / casual / technical


# Anti-cliché & em-dash sanitizer (ported from ai-job-search 03-writing-style.md)
_CLICHE_REPLACEMENTS = [
    (re.compile(r"\bpassionate about\b", re.I), "focused on"),
    (re.compile(r"\bthrilled to\b", re.I), "ready to"),
    (re.compile(r"\binvaluable\b", re.I), "practical"),
    (re.compile(r"\bcutting-edge\b", re.I), "production"),
    (re.compile(r"\bsynergy\b", re.I), "collaboration"),
    (re.compile(r"\bthought leader\b", re.I), "practitioner"),
    (re.compile(r"\bguru\b|\bninja\b|\brockstar\b", re.I), "specialist"),
]


def _clean_style(text: str) -> str:
    """Enforce 03-writing-style.md: zero em-dashes, zero filler clichés."""
    out = (text or "").replace("—", ", ").replace("–", "-")
    out = re.sub(r"\s+,", ",", out)
    for pat, repl in _CLICHE_REPLACEMENTS:
        out = pat.sub(repl, out)
    return out.strip()


def _extract_top_skills(cv_text: str, jd: str, n: int = 6) -> list:
    try:
        from cv_matcher import _extract_skills, _skill_freq_in_text, TECH_SKILLS
        cv_skills = _extract_skills(cv_text, TECH_SKILLS) if cv_text else set()
        jd_skills = _extract_skills(jd, TECH_SKILLS) if jd else set()
        matched = sorted(cv_skills & jd_skills, key=lambda s: (-_skill_freq_in_text(jd, s), s))
        if len(matched) >= 3:
            return matched[:n]
        extra = sorted(jd_skills - cv_skills, key=lambda s: (-_skill_freq_in_text(jd, s), s))
        combined = matched + [s for s in sorted(cv_skills) if s not in matched] + extra
        return combined[:n]
    except Exception:
        words = re.findall(r"\b[A-Za-z+#]{3,}\b", cv_text or jd)
        return list(dict.fromkeys(words))[:n]


def _extract_years(cv_text: str) -> str:
    m = re.search(r"(\d+)\+?\s*(?:years?|ans?)", cv_text or "", re.I)
    return f"{m.group(1)}+ years" if m else "hands-on experience"


def _extract_cv_evidence(cv_text: str, jd: str) -> dict:
    """
    Parse the candidate's real CV via cv_engine.parse_cv to ground cover letters
    and portal form answers in verified projects, roles, and achievements.
    """
    evidence = {
        "specialty": "",
        "bullets": [],
        "best_project": None,
        "recent_role": None,
    }
    if not cv_text:
        return evidence

    jd_words = {w.lower() for w in re.findall(r"[A-Za-z0-9+#.]{3,}", jd or "")}
    try:
        from cv_engine.parse import parse_cv
        parsed = parse_cv(cv_text)
        evidence["specialty"] = (parsed.headline or "").split("|")[0].split("•")[0].strip()

        scored_bullets = []
        for exp in (parsed.experience or []):
            if not evidence["recent_role"] and (exp.title or exp.company):
                evidence["recent_role"] = {
                    "title": exp.title or "Software Engineer",
                    "company": exp.company or "",
                    "dates": exp.dates or "Recent",
                    "bullets": list(exp.bullets or []),
                }
            for b in (exp.bullets or []):
                b_clean = _clean_style(b)
                if 25 <= len(b_clean) <= 220:
                    b_tokens = {w.lower() for w in re.findall(r"[A-Za-z0-9+#.]{3,}", b_clean)}
                    overlap = len(b_tokens & jd_words)
                    has_metric = 2 if re.search(r"\b\d+(?:%|x|ms|s|k|\+)\b", b_clean, re.I) else 0
                    scored_bullets.append((overlap + has_metric, b_clean))

        best_proj = None
        best_proj_score = -1
        for proj in (parsed.projects or []):
            p_bullets = [_clean_style(b) for b in (proj.bullets or []) if b.strip()]
            blob = f"{proj.title} {proj.tech} {' '.join(p_bullets)}"
            p_tokens = {w.lower() for w in re.findall(r"[A-Za-z0-9+#.]{3,}", blob)}
            sc = len(p_tokens & jd_words)
            if sc > best_proj_score and (proj.title or p_bullets):
                best_proj_score = sc
                best_proj = {
                    "name": proj.title or "Production Engineering Project",
                    "role": evidence["specialty"] or "Lead Developer",
                    "dates": proj.dates or "Recent",
                    "tech": proj.tech or "",
                    "bullets": p_bullets,
                }
            for b_clean in p_bullets:
                if 25 <= len(b_clean) <= 220:
                    b_tokens = {w.lower() for w in re.findall(r"[A-Za-z0-9+#.]{3,}", b_clean)}
                    scored_bullets.append((len(b_tokens & jd_words) + 1, b_clean))

        scored_bullets.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        for _, b_txt in scored_bullets:
            norm = b_txt[:50].lower()
            if norm not in seen:
                seen.add(norm)
                evidence["bullets"].append(b_txt)
            if len(evidence["bullets"]) >= 3:
                break

        evidence["best_project"] = best_proj
    except Exception:
        pass
    return evidence


def _trim_to_140(text: str) -> str:
    clean = _clean_style(re.sub(r"\s+", " ", text).strip())
    if len(clean) <= 140:
        return clean
    cut = clean[:137].rsplit(" ", 1)[0].rstrip(",;.")
    return cut + "."


def build_portal_form_fields(
    cv_text: str,
    user_name: str,
    job_title: str,
    company: str,
    job_description: str,
    lang: str = "en",
) -> dict:
    """
    Generate copy-pasteable Portal Application Form Answers
    (ported from ai-job-search 08-application-forms.md):
      1. Self-Introduction (~130 words full + ~70 words compact)
      2. 140-Character Stand-Out Pitches (3 angles, each <= 140 chars)
      3. Why This Company & Role (~90 words, task-solving forward framing)
      4. Structured Project Entry (Name, Role, Dates, 100w & 50w descriptions)
    """
    top_skills = _extract_top_skills(cv_text, job_description, n=5)
    s1 = top_skills[0] if len(top_skills) > 0 else "software engineering"
    s2 = top_skills[1] if len(top_skills) > 1 else "system architecture"
    s3 = top_skills[2] if len(top_skills) > 2 else "automated testing"
    skills_inline = ", ".join(top_skills[:4]) if top_skills else "modern software stacks"
    years = _extract_years(cv_text)
    ev = _extract_cv_evidence(cv_text, job_description)
    specialty = ev["specialty"] or job_title or "Software Engineer"
    comp = (company or "your team").strip()
    role = (job_title or "this role").strip()

    highlight_1 = ev["bullets"][0] if len(ev["bullets"]) > 0 else (
        f"Built and shipped production features across {s1} and {s2} with a focus on reliability and clean architecture."
    )
    highlight_2 = ev["bullets"][1] if len(ev["bullets"]) > 1 else (
        f"Improved delivery velocity and runtime stability using {s3} and structured code reviews."
    )

    if lang == "fr":
        intro_full = _clean_style(
            f"Ingénieur spécialisé en {skills_inline} avec {years} d'expérience, je conçois et déploie des applications fiables du prototype jusqu'à la mise en production.\n\n"
            f"Au cours de mes expériences récentes, j'ai notamment : {highlight_1} Par ailleurs : {highlight_2}\n\n"
            f"Rejoindre {comp} en tant que {role} représente l'opportunité d'appliquer directement mon expertise en {s1} et {s2} aux enjeux techniques de votre équipe dès le premier jour."
        )
        intro_short = _clean_style(
            f"Spécialiste en {skills_inline} ({years}), j'ai livré des systèmes en production alliant performance et maintenabilité. {highlight_1} Je souhaite mettre cette expérience concrète au service de {comp} pour le poste de {role}."
        )
        why_comp = _clean_style(
            f"Ce qui m'attire chez {comp} pour le poste de {role}, c'est la possibilité de résoudre des problèmes concrets autour de {s1} et {s2}. Plutôt qu'une approche théorique, j'apporte une exécution pragmatique sur {skills_inline} afin d'accélérer votre feuille de route technique et garantir la fiabilité en production."
        )
        pitches = [
            {"angle": "Stack + Exécution", "text": _trim_to_140(f"Spécialiste {s1} & {s2} ({years}) habitué à livrer des systèmes fiables en production du design au déploiement.")},
            {"angle": "Impact Mesurable", "text": _trim_to_140(f"Ingénieur {role} maîtrisant {s1}, {s2} et {s3}, orienté qualité de code, performance et livraison rapide.")},
            {"angle": "Adéquation Directe", "text": _trim_to_140(f"Expérience concrète sur {skills_inline} directement applicable aux priorités techniques de {comp}.")},
        ]
    else:
        intro_full = _clean_style(
            f"I am a {specialty} with {years} of experience building and scaling production systems across {skills_inline}. My work focuses on turning complex product and infrastructure requirements into reliable, maintainable software.\n\n"
            f"In my recent work, I have delivered concrete outcomes that map directly to this role: {highlight_1} Additionally, {highlight_2}\n\n"
            f"I am applying for the {role} role at {comp} because your technical priorities around {s1} and {s2} match the exact systems I build and ship every day."
        )
        intro_short = _clean_style(
            f"{specialty} with {years} of hands-on experience in {skills_inline}. {highlight_1} Ready to contribute immediately to {comp}'s {role} roadmap across {s1} and {s2}."
        )
        why_comp = _clean_style(
            f"{comp}'s focus on shipping high-reliability systems with {s1} and {s2} aligns directly with my day-to-day engineering work. Rather than needing a long ramp-up on {skills_inline}, I can step in immediately to help your team execute on the {role} roadmap, reduce technical bottlenecks, and ship clean production code."
        )
        pitches = [
            {"angle": "Breadth + Depth", "text": _trim_to_140(f"{specialty} with {years} in {s1}, {s2}, and {s3}, shipping reliable production systems end to end.")},
            {"angle": "End-to-End Delivery", "text": _trim_to_140(f"Hands-on builder across {skills_inline} who takes features from architecture to tested production release.")},
            {"angle": "Role + Stack Fit", "text": _trim_to_140(f"Proven track record in {s1} and {s2} ready to solve {comp}'s core {role} challenges from day one.")},
        ]

    for p in pitches:
        p["chars"] = len(p["text"])

    proj_src = ev["best_project"] or ev["recent_role"] or {
        "name": f"{s1.title()} & {s2.title()} Production System",
        "role": specialty,
        "dates": "Recent",
        "tech": skills_inline,
        "bullets": [highlight_1, highlight_2],
    }
    proj_name = proj_src.get("name") or f"{ proj_src.get('title', role) } — { proj_src.get('company', 'Production') }"
    proj_role = proj_src.get("role") or proj_src.get("title") or specialty
    proj_dates = proj_src.get("dates") or "Recent"
    proj_bullets = proj_src.get("bullets") or [highlight_1, highlight_2]
    proj_full_desc = _clean_style(
        f"Designed, implemented, and maintained {proj_name} using {skills_inline}. "
        + " ".join(proj_bullets[:3])
        + f" Ensured production reliability, clean modular architecture, and measurable delivery impact relevant to {role}."
    )
    proj_short_desc = _clean_style(
        f"Built {proj_name} with {skills_inline}. {proj_bullets[0] if proj_bullets else highlight_1}"
    )

    return {
        "self_intro": {
            "full": intro_full,
            "full_words": len(intro_full.split()),
            "full_chars": len(intro_full),
            "short": intro_short,
            "short_words": len(intro_short.split()),
            "short_chars": len(intro_short),
        },
        "stand_out_pitches": pitches,
        "why_company": {
            "text": why_comp,
            "words": len(why_comp.split()),
            "chars": len(why_comp),
        },
        "structured_project": {
            "name": proj_name,
            "role": proj_role,
            "dates": proj_dates,
            "tech_stack": proj_src.get("tech") or skills_inline,
            "description_100w": proj_full_desc,
            "description_100w_words": len(proj_full_desc.split()),
            "description_50w": proj_short_desc,
            "description_50w_words": len(proj_short_desc.split()),
        },
    }


@router.post("/generate")
def generate(req: CLRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv_rec.text_content if cv_rec else ""

    top_skills = _extract_top_skills(cv_text, req.job_description, n=5)
    skills_str = ", ".join(top_skills) if top_skills else "modern software engineering"
    years = _extract_years(cv_text)
    ev = _extract_cv_evidence(cv_text, req.job_description)
    specialty = ev["specialty"] or req.job_title

    lang = detect_language(f"{req.job_title} {req.company} {req.job_description}")

    # Engaging headline formula from 03-writing-style.md:
    # "[Title/specialty] specializing in [2-3 keywords from their JD]"
    top_3_kw = ", ".join(top_skills[:3]) if top_skills else req.job_title
    if lang == "fr":
        headline = f"{specialty} spécialisé en {top_3_kw}"
    else:
        headline = f"{specialty} specializing in {top_3_kw}"

    # Build 3 concrete task-solving impact bullets grounded in the candidate's CV
    cv_bullets = ev["bullets"][:3]
    if not cv_bullets:
        s1 = top_skills[0] if len(top_skills) > 0 else "core engineering"
        s2 = top_skills[1] if len(top_skills) > 1 else "system design"
        if lang == "fr":
            cv_bullets = [
                f"Conception et mise en production d'architectures robustes autour de {s1} et {s2}.",
                f"Optimisation de la qualité logicielle, des tests automatisés et de la maintenabilité sur {skills_str}.",
                f"Collaboration technique directe avec les équipes produit pour livrer des fonctionnalités fiables dans les délais.",
            ]
        else:
            cv_bullets = [
                f"Designed, built, and shipped production features across {s1} and {s2} with clean, maintainable architecture.",
                f"Improved system reliability, automated testing, and delivery speed across {skills_str}.",
                f"Partnered across engineering and product to translate complex technical requirements into shipped solutions.",
            ]
    bullets_block = "\n".join(f"• {_clean_style(b)}" for b in cv_bullets)

    if lang == "fr":
        if req.style == "casual":
            opening = f"Les priorités techniques de {req.company} autour de {skills_str} correspondent exactement aux systèmes que je conçois et déploie au quotidien, c'est pourquoi je vous propose ma candidature pour le poste de {req.job_title}."
            closing = "Je serais ravi d'échanger de vive voix sur la manière dont je peux contribuer concrètement à votre feuille de route dès mon arrivée."
        elif req.style == "technical":
            opening = f"Fort de {years} d'expérience pratique sur {skills_str}, je vous soumets ma candidature au poste de {req.job_title} chez {req.company} avec l'objectif d'être immédiatement opérationnel sur votre stack."
            closing = "Je reste à votre disposition pour un entretien technique afin d'approfondir ces réalisations et discuter de vos enjeux d'architecture."
        else:
            opening = f"Avec {years} d'expérience dédiée à la conception et à la mise en production de solutions utilisant {skills_str}, je vous présente ma candidature au poste de {req.job_title} au sein de {req.company}."
            closing = "Je me tiens à votre disposition pour un entretien afin d'échanger sur la contribution directe que je peux apporter à votre équipe."

        letter = _clean_style(f"""Objet : {headline} ({req.job_title})

Madame, Monsieur,

{opening}

Voici comment mes réalisations récentes répondent directement aux besoins de ce poste :
{bullets_block}

Plutôt qu'une montée en compétence théorique, j'apporte à {req.company} une exécution éprouvée sur {top_3_kw} permettant d'accélérer vos livraisons tout en garantissant la stabilité en production.

{closing}

Cordialement,
{current_user.name}
{current_user.email}""")
    else:
        if req.style == "casual":
            opening = f"Seeing {req.company}'s focus on {skills_str} for the {req.job_title} role immediately caught my attention because these are the exact problems I build and ship solutions for every day."
            closing = f"I would welcome a conversation on how my background with {top_3_kw} can help your team hit its upcoming milestones."
        elif req.style == "technical":
            opening = f"As a {specialty} with {years} of hands-on production experience across {skills_str}, I am applying for the {req.job_title} position at {req.company} ready to contribute directly to your engineering roadmap."
            closing = f"I would welcome a technical discussion to walk through the architecture and trade-offs behind these systems and how they map to {req.company}'s stack."
        else:
            opening = f"With {years} of experience building and delivering production software across {skills_str}, I am applying for the {req.job_title} position at {req.company}."
            closing = f"I welcome the opportunity to discuss how my experience across {top_3_kw} can support {req.company}'s upcoming priorities."

        letter = _clean_style(f"""Re: {headline} ({req.job_title})

Dear Hiring Team at {req.company},

{opening}

Here is how my recent hands-on work maps directly to what you need in this role:
{bullets_block}

Rather than requiring a long ramp-up on your stack, I can step in immediately to help {req.company} ship reliable solutions across {top_3_kw} while keeping code quality and maintainability high.

{closing}

Sincerely,
{current_user.name}
{current_user.email}""")

    portal_form_fields = build_portal_form_fields(
        cv_text=cv_text,
        user_name=current_user.name or "",
        job_title=req.job_title,
        company=req.company,
        job_description=req.job_description,
        lang=lang,
    )
    word_count = len(letter.split())

    return {
        "letter": letter,
        "headline": headline,
        "word_count": word_count,
        "char_count": len(letter),
        "skills_used": top_skills,
        "evidence_bullets": cv_bullets,
        "portal_form_fields": portal_form_fields,
        "style": req.style,
        "job_title": req.job_title,
        "company": req.company,
        "language": lang,
    }
