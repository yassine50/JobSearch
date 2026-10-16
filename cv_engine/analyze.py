"""
Pre-tailoring CV diagnosis — what a senior recruiter checks in the first 30 seconds.

Produces:
  • profile    : CV type, career stage, language, layout, experience totals
  • scores     : overall + structure / impact / ATS / writing / completeness (0–100)
  • issues     : severity-ranked findings, each with a concrete fix and whether we auto-fixed it
  • strengths  : what already works
  • strategy   : section order + page budget the renderer should use
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .lexicon import (
    ACTION_NOUNS_FR, ACTION_VERBS_EN, BUZZWORDS, CATEGORY_ORDER, DATA, FRONT, BACK, MOBILE, CLOUD, DESIGN, TECH,
    OBJECTIVE_RE, PERSONAL_INFO, WEAK_OPENERS, tech_category,
)
from .parse import CV

METRIC_RE = re.compile(
    r"(\d+(?:[.,]\d+)?\s?(?:%|x\b|k\b|k\+|m\b|\+|ms\b|s\b|sec|hours?|h\b|days?|jours?|users?|utilisateurs|clients?|"
    r"downloads?|téléchargements|apps?|applications|features?|fonctionnalités|requests?|records|projects?|projets|"
    r"members?|membres|people|personnes|countries|pays|stars?|commits?|channels|videos)|"
    r"\b\d{2,}(?:[.,]\d{3})*\b(?!\s*(?:–|-)\s*\d{4}))",
    re.I,
)


def _sev_rank(s: str) -> int:
    return {"critical": 0, "major": 1, "minor": 2}.get(s, 3)


def classify_type(cv: CV) -> Dict[str, str]:
    cats: Dict[str, int] = {}
    for s in cv.skills:
        if s in TECH:
            cats[tech_category(s)] = cats.get(tech_category(s), 0) + 1
    head = (cv.headline + " " + " ".join(e.title for e in cv.experience[:2])).lower()
    mobile = cats.get(MOBILE, 0) * 2 + (4 if re.search(r"flutter|mobile|android|ios|react native", head) else 0)
    front = cats.get(FRONT, 0) + (3 if re.search(r"front|ui|react|angular|vue", head) else 0)
    back = cats.get(BACK, 0) + (3 if re.search(r"back|api|java|python|\.net|node|php", head) else 0)
    data = cats.get(DATA, 0) * 2 + (5 if re.search(r"data|machine learning|\bml\b|\bai\b|ia\b|scientist|analyst", head) else 0)
    devops = cats.get(CLOUD, 0) + (5 if re.search(r"devops|cloud|sre|infra", head) else 0)
    design = cats.get(DESIGN, 0) * 2 + (5 if re.search(r"designer|ux|ui/ux", head) else 0)
    full = (6 if re.search(r"full[ -]?stack", head) else 0) + min(front, back)
    scores = {
        "Mobile Engineering": mobile, "Full-Stack Web Development": full * 1.1, "Frontend Development": front,
        "Backend Development": back, "Data / AI": data, "Cloud & DevOps": devops, "UI/UX Design": design,
    }
    best = max(scores, key=scores.get)
    if scores[best] < 2:
        best = "Software Engineering"
    focus = {
        "Mobile Engineering": "Cross-platform & native mobile apps",
        "Full-Stack Web Development": "Web frontends with backend APIs and databases",
        "Frontend Development": "Modern web interfaces",
        "Backend Development": "APIs, services and data layers",
        "Data / AI": "Data processing, ML and automation",
        "Cloud & DevOps": "Infrastructure, CI/CD and deployment",
        "UI/UX Design": "Product and interface design",
        "Software Engineering": "General software development",
    }[best]
    return {"cv_type": best, "domain_focus": focus}


def career_stage(cv: CV) -> Dict:
    job_m = cv.experience_months(("job",))
    intern_m = cv.experience_months(("internship",))
    studying = any(e.dates and e.dates.is_present for e in cv.education)
    seeking_alt = bool(re.search(r"alternance|apprentissage|stage|internship|work-study", cv.objective + " " + cv.headline, re.I))
    years = round(job_m / 12, 1)
    if job_m < 6 and (studying or seeking_alt):
        stage = "Student / Work-study"
    elif job_m < 24:
        stage = "Junior"
    elif job_m < 60:
        stage = "Mid-level"
    elif job_m < 96:
        stage = "Senior"
    else:
        stage = "Lead / Principal"
    return {"stage": stage, "job_months": job_m, "internship_months": intern_m, "years_experience": years,
            "studying": studying, "seeking_work_study": seeking_alt}


def diagnose(cv: CV) -> Dict:
    fr = cv.lang == "fr"
    issues: List[Dict] = []
    strengths: List[str] = []

    def add(sev, area, msg, fix, auto=False):
        issues.append({"severity": sev, "area": area, "message": msg, "fix": fix, "auto_fixed": auto})

    meta = cv.meta or {}
    typ = classify_type(cv)
    st = career_stage(cv)
    all_bullets = [b for e in cv.experience + cv.projects for b in e.bullets]
    exp_bullets = [b for e in cv.experience for b in e.bullets]
    metric_bullets = [b for b in all_bullets if METRIC_RE.search(b)]
    action_bullets = [b for b in all_bullets if (b.split() or [""])[0].lower().strip(",.") in ACTION_VERBS_EN or ACTION_NOUNS_FR.match(b)]
    weak = [b for b in all_bullets if WEAK_OPENERS.match(b) or len(b.split()) < 4]
    first_person = [b for b in all_bullets + [cv.summary] if re.search(r"\b(I|my|me|je|j'|mon|ma|mes)\b", b)]

    # ── Critical ──────────────────────────────────────────────────────────
    if meta.get("scanned"):
        add("critical", "ATS", "The PDF is a scanned image: applicant-tracking systems cannot read any text in it.",
            "Export the CV from Word/Google Docs/Canva as a text PDF (not a photo or scan) and upload it again.")
    if not cv.name:
        add("critical", "Header", "No candidate name detected.", "Put your full name as the first, largest line.")
    if not cv.contact.get("email"):
        add("critical", "Header", "No email address found.", "Add a professional email address in the header.")
    if not cv.contact.get("phone"):
        add("major", "Header", "No phone number found.", "Add a phone number with country code (e.g. +216 …).")
    if not cv.experience and not cv.projects and not meta.get("scanned"):
        add("critical", "Content", "No experience or projects could be found.",
            "Add internships, freelance work or academic/personal projects with 2–4 bullets each.")

    # ── Structure / ATS ───────────────────────────────────────────────────
    if meta.get("layout") == "two-column":
        add("major", "ATS", "Two-column / designer layout: many ATS read the columns out of order or skip the sidebar.",
            "Rebuilt as a single-column ATS layout.", auto=True)
    if meta.get("has_photo"):
        add("minor", "ATS", "Photo detected. Fine for Tunisia/France, but removed for UK/US/Canada/Germany applications and ATS parsing.",
            "Photo omitted in the generated CV.", auto=True)
    if cv.personal:
        add("minor", "Privacy", f"Personal details not needed by recruiters: {', '.join(cv.personal[:4])}.",
            "Removed (age, nationality, driving licence…) to avoid bias and save space.", auto=True)
    if not cv.summary or len(cv.summary.split()) < 12:
        add("major", "Summary", "No real professional summary" + (" (only an objective line)." if cv.objective else "."),
            "A 2–3 line factual summary was generated from your experience and skills.", auto=True)
    elif OBJECTIVE_RE.search(cv.summary) or BUZZWORDS.search(cv.summary) or first_person and cv.summary in first_person:
        add("minor", "Summary", "Summary reads like an objective / self-description (first person, generic adjectives).",
            "Rewritten as a factual summary focused on what you build and with which stack.", auto=True)
    if not cv.headline:
        add("minor", "Header", "No headline (target title) under the name.",
            "Added a headline derived from your experience.", auto=True)
    if len(cv.skills) < 5:
        add("major", "Skills", "Skills section is missing or very thin.",
            "Built a categorized skills section from the technologies used in your experience/projects.", auto=True)
    elif any(not g for g, _ in cv.skill_groups) and len(cv.skill_groups) > 3 or meta.get("layout") == "two-column":
        add("minor", "Skills", "Skills are not grouped into clear categories.",
            "Grouped into Languages / Frontend / Backend / Databases / Tools …", auto=True)
    if not cv.links.get("linkedin"):
        add("minor", "Header", "No working LinkedIn URL (missing, or the link in the PDF is broken).",
            "Add the full URL, e.g. linkedin.com/in/your-name.")
    if not cv.languages:
        add("minor", "Languages", "No spoken languages listed.", "Add languages with a level (e.g. English – Fluent (C1)).")
    elif not any(l.get("level_en") for l in cv.languages):
        add("minor", "Languages", "Languages have no proficiency level (graphical dots are invisible to ATS).",
            "Add a CEFR level or Native/Fluent/Intermediate to each language.")

    # ── Impact / writing ──────────────────────────────────────────────────
    if all_bullets:
        ratio = len(metric_bullets) / len(all_bullets)
        if ratio < 0.2:
            add("major", "Impact", f"Only {len(metric_bullets)} of {len(all_bullets)} bullets contain a number (users, %, time saved, volume…).",
                "Add real figures where you have them: e.g. 'Cut load time from 5s to 2s', 'Used by 1,000+ students'. We never invent numbers.")
        else:
            strengths.append(f"{len(metric_bullets)} quantified achievements")
        if len(weak) >= 2:
            add("major", "Writing", f"{len(weak)} bullets are vague or duty-style (e.g. \"{weak[0][:60]}\").",
                "Start each bullet with an action verb and the result: Built / Designed / Reduced / Automated …")
    for e in cv.experience:
        if not e.bullets:
            add("major", "Experience", f"\"{e.title or e.org}\" has no description.",
                "Add 2–4 bullets: what you built, with which stack, and the outcome.")
        elif len(e.bullets) == 1 and len(e.bullets[0].split()) < 8:
            add("major", "Experience", f"\"{e.title or e.org}\" is described in a single short line.",
                "Expand to 2–4 concrete bullets.")
        if not e.dates:
            add("major", "Experience", f"\"{e.title or e.org}\" has no dates.", "Add start and end month/year.")
    if first_person:
        add("minor", "Writing", "First-person phrasing (\"I\", \"je\", \"my\").", "Removed first person from bullets.", auto=True)
    if BUZZWORDS.search(" ".join([cv.summary] + all_bullets)):
        add("minor", "Writing", "Generic adjectives (motivated, passionate, dynamic…) carry no information for recruiters.",
            "Replace with evidence: projects shipped, users, technologies.")
    if cv.soft_skills:
        add("minor", "Content", "Stand-alone soft-skill list (teamwork, communication…).",
            "Removed: soft skills are better shown through achievements.", auto=True)
    if cv.interests and st["stage"] not in ("Student / Work-study",):
        add("minor", "Content", "Hobbies section takes space without adding value for this level.",
            "Omitted in the generated CV.", auto=True)
    # mixed-language bullets (FR CV with EN fragments or vice-versa)
    if fr and any(re.match(r"^(development|developing|implementation|using)\b", b, re.I) for b in all_bullets):
        add("minor", "Writing", "French CV contains English phrasing in bullets.", "Fixed obvious cases (Development → Développement).", auto=True)

    # ── Strengths ─────────────────────────────────────────────────────────
    if cv.experience:
        strengths.append(f"{len(cv.experience)} experience entr{'y' if len(cv.experience) == 1 else 'ies'}")
    if len(cv.projects) >= 2:
        strengths.append(f"{len(cv.projects)} projects showing hands-on work")
    if len(cv.skills) >= 10:
        strengths.append(f"Broad technical stack ({len(cv.skills)} technologies)")
    if cv.links.get("github"):
        strengths.append("GitHub profile linked")
    if action_bullets and len(action_bullets) >= 0.6 * max(1, len(all_bullets)):
        strengths.append("Bullets mostly start with action verbs")
    if any(l.get("level_en") for l in cv.languages) and len(cv.languages) >= 2:
        strengths.append("Multilingual profile with stated levels")

    # ── Scores ────────────────────────────────────────────────────────────
    def clamp(x):
        return int(max(0, min(100, round(x))))
    structure = 100
    for i in issues:
        if i["area"] in ("Header", "ATS", "Summary", "Skills", "Languages"):
            structure -= {"critical": 35, "major": 15, "minor": 6}[i["severity"]]
    impact = 30 + (50 * len(metric_bullets) / max(1, len(all_bullets))) + (20 * len(action_bullets) / max(1, len(all_bullets)))
    writing = 100 - 8 * len(weak) - 6 * len(first_person) - (8 if BUZZWORDS.search(cv.summary or "") else 0)
    completeness = sum([
        20 if cv.contact.get("email") and cv.contact.get("phone") else 8,
        20 if cv.experience or cv.projects else 0,
        15 if cv.education else 0,
        15 if len(cv.skills) >= 5 else 5,
        10 if cv.summary else 0,
        10 if cv.languages else 0,
        10 if cv.links.get("linkedin") or cv.links.get("github") else 0,
    ])
    ats = 100 - (60 if meta.get("scanned") else 0) - (25 if meta.get("layout") == "two-column" else 0) - (5 if meta.get("has_photo") else 0)
    overall = clamp(0.25 * clamp(structure) + 0.25 * clamp(impact) + 0.15 * clamp(writing) + 0.2 * clamp(completeness) + 0.15 * clamp(ats))
    if meta.get("scanned"):
        overall = min(overall, 15)

    # ── Strategy for the generated CV ─────────────────────────────────────
    stage = st["stage"]
    if stage == "Student / Work-study":
        order = ["summary", "skills", "experience", "projects", "education", "certifications", "awards", "activities", "languages"]
        if not cv.experience:
            order = ["summary", "skills", "projects", "education", "certifications", "awards", "activities", "languages"]
    elif stage in ("Junior",):
        order = ["summary", "skills", "experience", "projects", "education", "certifications", "awards", "languages"]
    else:
        order = ["summary", "skills", "experience", "projects", "education", "certifications", "awards", "languages"]
    max_pages = 1 if (meta.get("pages", 1) <= 1 or st["job_months"] < 60) else 2
    layout_strategy = {
        "Student / Work-study": "Skills & projects forward: shows what you can already build",
        "Junior": "Skills → experience → projects: proves hands-on ability fast",
        "Mid-level": "Experience-first: impact and ownership up front",
        "Senior": "Experience-first with leadership and scope",
        "Lead / Principal": "Experience-first with leadership and scope",
    }[stage]

    issues.sort(key=lambda i: (_sev_rank(i["severity"]), i["auto_fixed"]))
    profile = {
        **typ,
        "seniority": stage, "career_stage": stage,
        "years_experience": st["years_experience"], "job_months": st["job_months"],
        "internship_months": st["internship_months"],
        "language": cv.lang, "layout": meta.get("layout", "unknown"), "pages": meta.get("pages", 1),
        "has_photo": bool(meta.get("has_photo")), "scanned": bool(meta.get("scanned")),
        "roles_count": len([e for e in cv.experience if e.kind == "job"]),
        "internships_count": len([e for e in cv.experience if e.kind == "internship"]),
        "projects_count": len(cv.projects), "education_count": len(cv.education),
        "skills_count": len(cv.skills), "bullets_count": len(all_bullets),
        "metrics_count": len(metric_bullets),
        "skill_categories_count": len({tech_category(s) for s in cv.skills if s in TECH}),
        "sections_found": list(cv.sections_found),
        "section_order": order, "layout_strategy": layout_strategy, "max_pages": max_pages,
    }
    return {
        "profile": profile,
        "scores": {
            "overall": overall, "structure": clamp(structure), "impact": clamp(impact), "writing": clamp(writing),
            "completeness": clamp(completeness), "ats": clamp(ats),
        },
        "issues": issues,
        "strengths": strengths,
    }
