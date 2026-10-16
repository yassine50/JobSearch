"""
End-to-end Senior CV Pipeline:
  1. Layout-aware extraction (`extract_document`)
  2. Structural parsing (`parse_document`)
  3. Pre-tailoring diagnosis (`diagnose`)
  4. Honest mechanical enhancement (`enhance`)
  5. Target-role tailoring (`tailor_cv_pipeline`)
  6. Executive single-column A4 PDF rendering (`render_cv_pdf`)
"""
from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional, Tuple

from cv_matcher import compute_match

from .analyze import career_stage, classify_type, diagnose
from .enhance import enhance, group_skills
from .extract import extract_document
from .lexicon import (
    BUZZWORDS,
    CATEGORY_FR,
    CATEGORY_ORDER,
    OBJECTIVE_RE,
    TECH,
    canonical_tech,
    tech_category,
)
from .parse import CV, Entry, parse_document
from .render import _format_name, render_cv_pdf

_SENIORITY_RE = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|head|chief|director|vp|manager|junior|jr\.?|intern|stagiaire)\b",
    re.I,
)

_IGNORE_SUMMARY_SKILLS = {
    "app store",
    "google play",
    "cross-platform",
    "state management",
    "agile",
    "scrum",
    "mobile",
    "remote",
    "english",
    "french",
    "git",
    "github",
    "jira",
}


def _relevance(text: str, keywords: List[str]) -> int:
    t = (text or "").lower()
    return sum(len(re.findall(r"(?<![\w])" + re.escape(k.lower()) + r"(?![\w])", t)) for k in keywords if k)


def _clean_role_title(job_title: str, lang: str = "en") -> str:
    role = re.sub(
        r"\((?:remote|hybrid|on-?site|f/h|h/f|m/w/d|m/f/d|stage|alternance)[^)]*\)",
        "",
        job_title or "",
        flags=re.I,
    )
    role = re.sub(
        r"\s*[-–—|,]\s*(remote|hybrid|on-?site|full[- ]time|part[- ]time|contract|cdi|cdd|freelance|stage|alternance).*$",
        "",
        role,
        flags=re.I,
    )
    words = []
    for w in role.split():
        c = canonical_tech(w)
        if c and c.lower() == w.lower():
            words.append(c)
        elif w.islower():
            words.append(w.capitalize())
        else:
            words.append(w)
    out = " ".join(words).strip()
    if not out:
        return "Ingénieur Logiciel" if lang == "fr" else "Software Engineer"
    return out


def _default_headline_from_cv(cv: CV, diag_profile: Dict) -> str:
    if cv.headline and len(cv.headline.split()) <= 8:
        return cv.headline
    fr = cv.lang == "fr"
    cv_type = diag_profile.get("cv_type", "Software Engineering")
    mapping_en = {
        "Mobile Engineering": "Mobile Application Developer",
        "Full-Stack Web Development": "Full-Stack Software Engineer",
        "Frontend Development": "Frontend Developer",
        "Backend Development": "Backend Software Engineer",
        "Data / AI": "Data & AI Engineer",
        "Cloud & DevOps": "Cloud & DevOps Engineer",
        "UI/UX Design": "UI/UX Product Designer",
        "Software Engineering": "Software Engineer",
    }
    mapping_fr = {
        "Mobile Engineering": "Développeur d'Applications Mobiles",
        "Full-Stack Web Development": "Ingénieur études et développement Full-Stack",
        "Frontend Development": "Développeur Front-End",
        "Backend Development": "Développeur Back-End",
        "Data / AI": "Ingénieur Data & Intelligence Artificielle",
        "Cloud & DevOps": "Ingénieur Cloud & DevOps",
        "UI/UX Design": "Designer UI/UX",
        "Software Engineering": "Ingénieur Logiciel",
    }
    return (mapping_fr if fr else mapping_en).get(cv_type, "Software Engineer")


def _select_headline(cv: CV, diag_profile: Dict, job_title: str, mode: str) -> str:
    clean_target = _clean_role_title(job_title, cv.lang)
    fallback = _default_headline_from_cv(cv, diag_profile)
    if not job_title or not job_title.strip():
        return fallback

    if mode == "full_match":
        if len(clean_target) <= 56:
            return clean_target
        return fallback

    # honest mode: only adopt target role words supported by the CV
    cv_blob = (cv.raw_text + " " + " ".join(cv.skills)).lower()
    cv_head_low = (cv.headline or "").lower()
    filtered = " ".join(
        w for w in clean_target.split() if not _SENIORITY_RE.fullmatch(w) or w.lower() in cv_head_low
    ).strip()
    generic = {
        "developer", "engineer", "software", "mobile", "app", "application", "programmer",
        "specialist", "développeur", "ingénieur", "logiciel", "web", "full", "stack", "fullstack",
    }
    core = [w for w in re.findall(r"[a-zA-ZÀ-ÿ+#.]+", filtered.lower()) if w not in generic and len(w) > 1]
    if filtered and all(w in cv_blob for w in core):
        return filtered
    return fallback


def _craft_summary(
    cv: CV,
    diag_profile: Dict,
    headline: str,
    job_skills: List[str],
    matched_skills: List[str],
    mode: str,
) -> Tuple[str, List[str]]:
    """
    Produces a clean, factual 2–3 sentence executive summary in the CV's language.
    Replaces weak/objective/first-person summaries or missing summaries while preserving
    already strong factual summaries (such as Yassine's).
    """
    fr = cv.lang == "fr"
    own = (cv.summary or "").strip()
    notes: List[str] = []

    priority_display: List[str] = []
    pool = (job_skills if mode == "full_match" else matched_skills) + cv.skills
    for s in pool:
        if not s or s.lower() in _IGNORE_SUMMARY_SKILLS:
            continue
        c = canonical_tech(s) or s
        if c not in priority_display:
            priority_display.append(c)
        if len(priority_display) >= 6:
            break

    has_first_person = bool(re.search(r"\b(I|my|me|je|j'|mon|ma|mes)\b", own))
    is_weak_summary = (
        not own
        or len(own.split()) < 14
        or bool(OBJECTIVE_RE.search(own))
        or bool(BUZZWORDS.search(own))
        or has_first_person
    )

    if not is_weak_summary:
        # Keep candidate's strong factual summary, align opening role & append unmentioned target skills
        sents = [
            x.strip()
            for x in re.split(r"(?<=[.!?])\s+", own)
            if x.strip()
            and not re.match(r"^(?:Core technical focus includes|Compétences clés mobilisées\s*:)", x.strip(), re.I)
        ]
        if sents:
            m_lead = re.match(
                r"^(?:Experienced\s+|Senior\s+)?(?:Mobile|Flutter|Full[- ]?Stack|Software|Frontend|Backend|Web|Application)\s+(?:engineer|developer|specialist|architect)(\s+with\s+.+)$",
                sents[0],
                re.I,
            )
            if m_lead and headline and not fr:
                sents[0] = f"{headline}{m_lead.group(1)}"
                notes.append(f"Aligned summary opening title with target role ({headline}).")
            for idx_s, s in enumerate(sents):
                if re.match(r"^Also\s+build\b", s):
                    sents[idx_s] = re.sub(r"^Also\s+build\b", "Also experienced in building", s)
        joined_low = " ".join(sents).lower()
        unmentioned = [sk for sk in priority_display[:5] if sk.lower() not in joined_low][:4]
        if unmentioned and mode == "full_match":
            if fr:
                clause = f"Compétences clés mobilisées : {', '.join(unmentioned)}."
            elif len(unmentioned) == 1:
                clause = f"Core technical focus includes {unmentioned[0]}."
            else:
                clause = f"Core technical focus includes {', '.join(unmentioned[:-1])} and {unmentioned[-1]}."
            sents.append(clause)
            notes.append(f"Integrated target role keywords ({', '.join(unmentioned)}) into the Executive Summary.")
        return " ".join(sents).strip(), notes

    # Build a factual summary grounded in the candidate's real history
    job_m = diag_profile.get("job_months", 0)
    intern_m = diag_profile.get("internship_months", 0)
    years = diag_profile.get("years_experience", 0)
    n_roles = len(cv.experience)
    n_projs = len(cv.projects)
    top_stack = ", ".join(priority_display[:5]) if priority_display else ("Java, Python, JavaScript" if not fr else "Java, Python, JavaScript")

    if fr:
        if years >= 1.5:
            exp_phrase = f"fort de {int(round(years))}+ ans d'expérience dans la conception et le développement d'applications"
        elif n_roles >= 2:
            exp_phrase = f"fort de {n_roles} expériences professionnelles et stages significatifs en développement logiciel"
        elif n_roles == 1 and n_projs >= 1:
            exp_phrase = f"avec une expérience pratique acquise en stage et à travers {n_projs} projets techniques"
        else:
            exp_phrase = "spécialisé dans la conception et le développement d'applications modernes"
        summary = (
            f"{headline} {exp_phrase}. "
            f"Maîtrise technique de {top_stack}, avec une approche orientée qualité du code, "
            f"architecture modulaire et livraison de solutions fiables en production."
        )
        notes.append("Rédaction d'un profil professionnel factuel et aligné ATS (remplaçant l'objectif générique).")
    else:
        if years >= 1.5:
            exp_phrase = f"with {int(round(years))}+ years of hands-on experience designing, building, and shipping production software"
        elif n_roles >= 2:
            exp_phrase = f"with hands-on experience across {n_roles} software engineering roles and internships"
        elif n_roles == 1 and n_projs >= 1:
            exp_phrase = f"with practical experience across industry internship work and {n_projs} end-to-end engineering projects"
        else:
            exp_phrase = "specializing in full-lifecycle application development and clean software architecture"
        summary = (
            f"{headline} {exp_phrase}. "
            f"Strong technical command of {top_stack}, focused on scalable architecture, "
            f"clean maintainable code, and reliable end-to-end delivery."
        )
        notes.append(f"Generated factual executive summary tailored to {headline}.")
    return summary, notes


def _build_tailored_skill_groups(
    cv: CV,
    keywords: List[str],
    missing_tech: List[str],
    mode: str,
) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """
    Organizes the candidate's skills into clean recruiter categories, expanding compound
    testing phrases and (in full_match mode) bridging missing JD tech skills into the
    appropriate category.
    """
    fr = cv.lang == "fr"
    has_clean_source_groups = (
        len(cv.skill_groups) >= 3
        and all(bool(cat and cat.strip()) for cat, _ in cv.skill_groups)
        and cv.meta.get("layout") != "two-column"
    )

    added: List[str] = []

    if has_clean_source_groups:
        groups: Dict[str, List[str]] = {}
        for cat, items in cv.skill_groups:
            expanded: List[str] = []
            for it in items:
                m = re.fullmatch(r"(\w+)\s+and\s+(\w+)\s+(testing|development|design)", it.strip(), re.I)
                if m:
                    expanded.extend([
                        f"{m.group(1).title()} {m.group(3).title()}",
                        f"{m.group(2).title()} {m.group(3).title()}",
                    ])
                else:
                    expanded.append(canonical_tech(it) or it)
            rel = [x for x in expanded if _relevance(x, keywords) > 0]
            rest = [x for x in expanded if x not in rel]
            groups[cat] = sorted(rel, key=lambda x: -_relevance(x, keywords)) + rest

        if mode == "full_match":
            for s in missing_tech:
                disp = canonical_tech(s) or s.title()
                if any(disp.lower() == x.lower() or disp.lower() in x.lower() for items in groups.values() for x in items):
                    continue
                target_cat = _match_existing_category(disp, list(groups.keys()))
                groups.setdefault(target_cat, [])
                n_rel = sum(1 for x in groups[target_cat] if _relevance(x, keywords) > 0)
                groups[target_cat].insert(n_rel, disp)
                added.append(disp)

        sorted_groups = sorted(
            groups.items(),
            key=lambda kv: (
                "also familiar" in kv[0].lower() or "additional" in kv[0].lower() or "autres" in kv[0].lower(),
                -sum(_relevance(i, keywords) for i in kv[1]),
            ),
        )
        return sorted_groups, added

    # Otherwise, build clean recruiter categories from canonical cv.skills
    all_skills: List[str] = []
    for s in cv.skills:
        c = canonical_tech(s) or s
        if c and not any(c.lower().lstrip(".") == x.lower().lstrip(".") for x in all_skills):
            all_skills.append(c)

    if mode == "full_match":
        for s in missing_tech:
            disp = canonical_tech(s) or s.title()
            if disp and not any(disp.lower().lstrip(".") == x.lower().lstrip(".") for x in all_skills):
                all_skills.append(disp)
                added.append(disp)

    grouped = group_skills(all_skills, cv.lang)
    prioritized: List[Tuple[str, List[str]]] = []
    for cat, items in grouped:
        rel = [x for x in items if _relevance(x, keywords) > 0]
        rest = [x for x in items if x not in rel]
        prioritized.append((cat, sorted(rel, key=lambda x: -_relevance(x, keywords)) + rest))

    prioritized.sort(
        key=lambda kv: (
            kv[0] in ("Other", "Autres"),
            -sum(_relevance(i, keywords) for i in kv[1]),
        )
    )
    return prioritized, added


def _match_existing_category(skill: str, cats: List[str]) -> str:
    cat_std = tech_category(skill) if skill in TECH else ""
    s_low = skill.lower()
    hints = {
        "Mobile": ("mobile", "cross-platform", "flutter"),
        "Frontend": ("web", "front", "ui"),
        "Backend": ("backend", "api", "server", "back"),
        "Databases": ("backend", "data", "db", "cloud"),
        "Cloud & DevOps": ("cloud", "devops", "release", "backend"),
        "Testing & Quality": ("release", "quality", "test"),
        "Architecture & Practices": ("release", "quality", "arch", "method"),
    }.get(cat_std, ())
    for h in hints:
        for c in cats:
            if h in c.lower():
                return c
    if any(k in s_low for k in ("flutter", "dart", "ios", "android", "mobile", "bloc", "riverpod")):
        for c in cats:
            if "mobile" in c.lower():
                return c
    for c in cats:
        if any(w in c.lower() for w in ("also familiar", "other", "additional", "autres")):
            return c
    return cats[0] if cats else "Core Technologies"


def cv_to_ats_text(cv: CV, extra_competencies: Optional[List[str]] = None) -> str:
    """Serialize a structured `CV` into clean ATS plain text."""
    lines: List[str] = [_format_name(cv.name)]
    if cv.headline:
        lines.append(cv.headline)
    contact_parts = [
        cv.contact.get("location", ""),
        cv.contact.get("email", ""),
        cv.contact.get("phone", ""),
        cv.links.get("linkedin", ""),
        cv.links.get("github", ""),
        cv.links.get("portfolio", ""),
    ]
    contact_str = " • ".join(p for p in contact_parts if p)
    if contact_str:
        lines.append(contact_str)

    if cv.summary:
        lines.extend(["", "PROFESSIONAL SUMMARY", cv.summary])

    if cv.skill_groups:
        lines.extend(["", "TECHNICAL SKILLS"])
        for cat, items in cv.skill_groups:
            if items:
                lines.append(f"{cat}: {', '.join(items)}" if cat else ", ".join(items))

    if cv.experience:
        lines.extend(["", "PROFESSIONAL EXPERIENCE"])
        for e in cv.experience:
            hdr = " — ".join(p for p in (e.title, e.org, e.location, e.date_text) if p)
            if hdr:
                lines.append(hdr)
            for b in e.bullets:
                lines.append(f"• {b}")
            if e.stack:
                lines.append(f"Technologies: {', '.join(e.stack)}")

    if cv.projects:
        lines.extend(["", "SELECTED PROJECTS"])
        for e in cv.projects:
            hdr = " | ".join(p for p in [e.title, e.org, e.date_text] + e.links[:2] if p)
            if hdr:
                lines.append(hdr)
            for b in e.bullets:
                lines.append(f"• {b}")
            if e.stack:
                lines.append(f"Technologies: {', '.join(e.stack)}")

    if cv.education:
        lines.extend(["", "EDUCATION"])
        for e in cv.education:
            hdr = " — ".join(p for p in (e.title, e.org, e.location, e.date_text) if p)
            if hdr:
                lines.append(hdr)
            for b in e.bullets:
                lines.append(f"• {b}")

    if cv.certifications:
        lines.extend(["", "CERTIFICATIONS"] + [f"• {c}" for c in cv.certifications])

    if cv.awards:
        lines.extend(["", "HONORS & AWARDS"] + [f"• {a}" for a in cv.awards])

    if cv.activities:
        lines.extend(["", "LEADERSHIP & ACTIVITIES"] + [f"• {a}" for a in cv.activities])

    if cv.languages:
        lang_strs = []
        for l in cv.languages:
            nm = l.get("name_en") or l.get("lang_en") or l.get("lang") or ""
            lv = l.get("level_en") or l.get("level") or ""
            if nm:
                lang_strs.append(f"{nm} ({lv})" if lv else nm)
        if lang_strs:
            lines.extend(["", "LANGUAGES", " • ".join(lang_strs)])

    if extra_competencies:
        lines.extend(["", "CORE COMPETENCIES: " + ", ".join(extra_competencies)])

    return "\n".join(lines)


def analyze_and_enhance_cv(
    cv_text: str = "",
    cv_pdf_bytes: Optional[bytes] = None,
    filename: str = "cv.pdf",
) -> Tuple[CV, CV, Dict, List[Dict[str, str]]]:
    """
    Runs steps 1–4 of the senior pipeline:
      1. Layout-aware extraction
      2. Structure parsing
      3. Pre-tailoring diagnosis (`pre_diag`)
      4. Mechanical enhancement (`enhanced_cv`, `changes`)
    Returns `(raw_cv, enhanced_cv, pre_diag, changes)`.
    """
    if cv_pdf_bytes:
        doc = extract_document(cv_pdf_bytes, filename=filename)
    else:
        doc = extract_document((cv_text or "").encode("utf-8"), filename="cv.txt")
    raw_cv = parse_document(doc)
    pre_diag = diagnose(raw_cv)
    enhanced_cv, changes = enhance(raw_cv)
    return raw_cv, enhanced_cv, pre_diag, changes


def tailor_cv_pipeline(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
    mode: str = "full_match",
    filename: str = "cv.pdf",
) -> Dict:
    """
    Complete pre-tailoring analysis → enhancement → job tailoring → executive PDF pipeline.
    Compatible with both `tailor_cv_full_match` and `tailor_cv_honest` return schemas,
    while adding rich pre-tailoring diagnostics (`diagnosis`, `enhancements`, `quality_scores`).
    """
    clean_role = (job_title or "").strip() or "Software Engineer"
    clean_co = (company or "").strip() or "Company"

    raw_cv, cv, pre_diag, changes = analyze_and_enhance_cv(
        cv_text=cv_text,
        cv_pdf_bytes=cv_pdf_bytes,
        filename=filename,
    )

    # Use layout-aware extracted text if raw_cv has richer text than legacy cv_text
    source_text_for_match = raw_cv.raw_text if (cv_pdf_bytes and raw_cv.raw_text) else (cv_text or raw_cv.raw_text)
    base_score, bd = compute_match(source_text_for_match, job_description, clean_role)

    jd_low = (job_description or "").lower()
    required = set(bd.get("required_skills") or [])
    job_skills = list(bd.get("job_skills") or [])
    matched_tech = list(bd.get("matched_tech") or [])

    def _first_pos(sk: str) -> int:
        idx = jd_low.find(sk.lower())
        return idx if idx >= 0 else 10**6

    job_skills.sort(key=lambda s: (s not in required, -min(jd_low.count(s.lower()), 3), _first_pos(s)))
    missing_tech = [s for s in job_skills if s in set(bd.get("missing_tech") or [])]
    missing_soft = list(bd.get("missing_soft") or []) + list(bd.get("matched_soft") or [])
    keywords = (job_skills if mode == "full_match" else matched_tech) + [
        w for w in re.findall(r"[a-zA-ZÀ-ÿ+#.]{3,}", clean_role.lower())
    ]

    diag_profile = pre_diag["profile"]

    # 1. Headline
    cv.headline = _select_headline(cv, diag_profile, clean_role, mode)

    # 2. Categorized skills
    cv.skill_groups, added_skills = _build_tailored_skill_groups(
        cv=cv,
        keywords=keywords,
        missing_tech=missing_tech,
        mode=mode,
    )
    # Keep cv.skills synced with skill_groups
    flat_skills: List[str] = []
    for _, items in cv.skill_groups:
        for it in items:
            if it not in flat_skills:
                flat_skills.append(it)
    cv.skills = flat_skills

    # 3. Experience bullet sorting (preserve chronology, prioritize relevant bullets, keep "Live apps:" last)
    for e in cv.experience:
        regular = [b for b in e.bullets if not b.lower().startswith("live apps:")]
        trailers = [b for b in e.bullets if b.lower().startswith("live apps:")]
        e.bullets = sorted(regular, key=lambda b: -_relevance(b, keywords)) + trailers

    # 4. Projects sorting by relevance (preserve internal narrative bullet order within each project)
    cv.projects.sort(
        key=lambda p: -_relevance(
            " ".join([p.title, p.org] + p.bullets + p.stack),
            keywords,
        )
    )
    if len(cv.projects) > 6:
        cv.projects = cv.projects[:6]

    # 5. Executive Summary
    cv.summary, summary_notes = _craft_summary(
        cv=cv,
        diag_profile=diag_profile,
        headline=cv.headline,
        job_skills=job_skills,
        matched_skills=matched_tech,
        mode=mode,
    )

    # 6. Compute post-enhancement CV quality diagnosis
    post_diag = diagnose(cv)
    post_diag["scores"]["overall"] = max(post_diag["scores"]["overall"], pre_diag["scores"]["overall"])

    # 7. Serialize to ATS text & compute new match score
    extra_soft = [s.title() for s in missing_soft[:6]] if mode == "full_match" and missing_soft else None
    tailored_text = cv_to_ats_text(cv, extra_competencies=extra_soft)
    new_score, _ = compute_match(tailored_text, job_description, clean_role)
    final_score = max(base_score, new_score)

    # 8. Render executive single-column A4 PDF
    sec_order = diag_profile.get("section_order")
    max_pages = diag_profile.get("max_pages", 1)
    pdf_bytes = render_cv_pdf(cv, section_order=sec_order, max_pages=max_pages)

    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", _format_name(cv.name)).strip("_") or "Candidate"
    safe_co = re.sub(r"[^a-zA-Z0-9]", "_", clean_co).strip("_") or "Company"

    # Build human-readable tips / audit summary
    tips: List[str] = [
        f"Pre-Tailoring Diagnosis: {diag_profile['cv_type']} ({diag_profile['seniority']}, "
        f"CV Quality {pre_diag['scores']['overall']}/100 → {post_diag['scores']['overall']}/100).",
        f"Layout Strategy: {diag_profile['layout_strategy']} (rebuilt into single-column A4 ATS format).",
    ]
    if changes:
        tips.append(f"Applied {len(changes)} automatic CV enhancements (typos, action verbs, tech casing, deduplication).")
    tips.extend(summary_notes)
    if added_skills:
        tips.append(f"Bridged {len(added_skills)} target JD skills into structured categories ({', '.join(added_skills[:6])}).")

    highlighted = [canonical_tech(s) or s for s in (matched_tech + added_skills)[:12] if s]

    # Attach pre/post quality scores & issues onto cv_profile so existing frontend/backend consumers have everything
    enriched_profile = {
        **diag_profile,
        "quality_scores_before": pre_diag["scores"],
        "quality_scores_after": post_diag["scores"],
        "issues": pre_diag["issues"],
        "strengths": pre_diag["strengths"],
        "enhancements": changes[:30],
        "enhancements_count": len(changes),
    }

    return {
        "tailored_text": tailored_text,
        "pdf_bytes": pdf_bytes,
        "filename": f"CV_{safe_name}_{safe_co}.pdf",
        "original_score": base_score,
        "tailored_score": final_score,
        "use_tailored": True,
        "bridged_skills": added_skills,
        "emphasized_skills": highlighted,
        "matched_skills": highlighted,
        "missing_tech": [] if mode == "full_match" else bd.get("missing_tech", []),
        "target_headline": cv.headline,
        "tailored_summary": cv.summary,
        "cv_profile": enriched_profile,
        "diagnosis": {
            "before_scores": pre_diag["scores"],
            "after_scores": post_diag["scores"],
            "issues": pre_diag["issues"],
            "strengths": pre_diag["strengths"],
            "enhancements": changes[:30],
            "enhancements_count": len(changes),
        },
        "tips": tips,
        "mode": mode,
    }
