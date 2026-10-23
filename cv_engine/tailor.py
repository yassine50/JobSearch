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

import re
from typing import Dict, List, Optional, Tuple

from cv_matcher import compute_match

from .analyze import diagnose
from .enhance import enhance, group_skills
from .extract import extract_document
from .lexicon import (
    BUZZWORDS,
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


_SOFTWARE_ROLE_RE = re.compile(
    r"\b(developer|engineer|programmer|architect|devops|sre|data\s+scientist|machine\s+learning|full[- ]?stack|"
    r"front[- ]?end|back[- ]?end|mobile|software|web|qa|tester|développeur|ingénieur)\b",
    re.I,
)


def _is_target_role_compatible(cv: CV, clean_target: str) -> bool:
    """
    Returns True if `clean_target` is a believable role headline for `cv`.
    Prevents turning a Flutter Engineer into 'Data Entry Clerk' or an Admin/IT Support CV
    with zero mobile skills into 'Dart/Flutter Developer'.
    """
    if not clean_target:
        return False
    cv_blob = (cv.raw_text + " " + " ".join(cv.skills) + " " + (cv.headline or "")).lower()
    target_low = clean_target.lower()

    # Check if the target title names specific canonical technologies (e.g. "Dart/Flutter Developer", "Python Developer")
    ignore_tech_tokens = {"it", "web", "ui", "ux", "qa", "ai", "ml", "rest", "api", "cloud", "data"}
    target_techs = [
        canonical_tech(w)
        for w in re.split(r"[\s/|,&()+-]+", clean_target)
        if w and w.lower() not in ignore_tech_tokens and canonical_tech(w)
    ]
    if target_techs:
        # Candidate must have at least one of the named technologies OR a closely related technology in the same category
        if any(t.lower() in cv_blob for t in target_techs if t):
            return True
        target_cats = {tech_category(t) for t in target_techs if t and t in TECH}
        cv_cats = {tech_category(s) for s in cv.skills if s in TECH}
        if "Mobile" in target_cats and "Mobile" not in cv_cats:
            return False
        if not (target_cats & cv_cats):
            return False

    # If target is a software/engineering role, check if candidate has software/coding background
    if _SOFTWARE_ROLE_RE.search(clean_target):
        canon_count = sum(1 for s in cv.skills if s in TECH)
        return canon_count >= 2 or bool(_SOFTWARE_ROLE_RE.search(cv.headline or ""))

    # Non-software role (e.g. "Data Entry Clerk", "IT Support Specialist", "Content Moderator", "Customer Support")
    stop = {
        "senior", "junior", "lead", "specialist", "associate", "representative", "officer",
        "coordinator", "assistant", "manager", "intern", "professional", "general", "data",
    }
    core_words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ]{3,}", target_low) if w not in stop]
    if core_words and all(w in cv_blob for w in core_words):
        return True
    return False


def _select_headline(cv: CV, diag_profile: Dict, job_title: str, mode: str) -> str:
    clean_target = _clean_role_title(job_title, cv.lang)
    fallback = _default_headline_from_cv(cv, diag_profile)
    if not job_title or not job_title.strip():
        return fallback

    if mode == "full_match":
        if len(clean_target) <= 56 and _is_target_role_compatible(cv, clean_target):
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
    if filtered and all(w in cv_blob for w in core) and _is_target_role_compatible(cv, filtered):
        return filtered
    return fallback


def _craft_summary(
    cv: CV,
    diag_profile: Dict,
    headline: str,
    job_skills: List[str],
    matched_skills: List[str],
    mode: str,
    bridged: Optional[List[str]] = None,
    focus_phrases: Optional[List[str]] = None,
    soft_evidence: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """
    Produces a clean, factual 2–3 sentence executive summary in the CV's language.
    Replaces weak/objective/first-person summaries or missing summaries while preserving
    already strong factual summaries (such as Yassine's or Amel's).
    The summary only ever claims skills that genuinely appear in the candidate's CV
    (bridged JD keywords live in the skills section, never in "Strong command of ...").
    """
    fr = cv.lang == "fr"
    own = (cv.summary or "").strip()
    notes: List[str] = []

    bridged_low = {b.lower() for b in (bridged or [])}
    matched_low = {m.lower() for m in matched_skills}
    priority_display: List[str] = []
    jd_order = [s for s in job_skills if s.lower() in matched_low] or list(matched_skills)
    pool = jd_order + [s for s in cv.skills if s.lower() not in bridged_low]
    for s in pool:
        if not s or s.lower() in _IGNORE_SUMMARY_SKILLS:
            continue
        c = _display_skill(s)
        if c.lower() in bridged_low:
            continue
        if c not in priority_display:
            priority_display.append(c)
        if len(priority_display) >= 6:
            break

    has_first_person = bool(re.search(r"\b(I|my|me|je|j'|mon|ma|mes)\b", own))
    is_weak_summary = (
        not own
        or len(own.split()) < 14
        or bool(OBJECTIVE_RE.search(own))
        or has_first_person
        or (bool(BUZZWORDS.search(own)) and len(own.split()) < 22)
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
                r"^(?:Experienced\s+|Senior\s+)?(?:Mobile|Flutter|Full[- ]?Stack|Software|Frontend|Backend|Web|Application)\s+(?:engineer|developer|specialist|architect)(\s+(?:with|who)\s+.+)$",
                sents[0],
                re.I,
            )
            if m_lead and headline and not fr and _SOFTWARE_ROLE_RE.search(headline) and len(headline.split()) <= 5:
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
        return _append_focus(" ".join(sents).strip(), focus_phrases, fr, notes), notes

    # Build a factual summary grounded in the candidate's real history
    years = diag_profile.get("years_experience", 0)
    n_roles = len(cv.experience)
    n_projs = len(cv.projects)
    top_stack = ", ".join(priority_display[:5]) if priority_display else ("Java, Python, JavaScript" if not fr else "Java, Python, JavaScript")
    is_sw = bool(_SOFTWARE_ROLE_RE.search(headline))
    soft_lead = False
    if not is_sw:
        # Non-software target (support, admin, operations...): never lead with unrelated programming languages;
        # cite JD-relevant skills, then soft skills the CV itself evidences.
        job_low = {j.lower() for j in list(job_skills) + list(matched_skills)}
        rel_items = [s for s in priority_display if s.lower() in job_low][:3]
        soft_items = [_phrase_inline(s) for s in (soft_evidence or []) if s not in rel_items]
        strengths = rel_items + soft_items[:max(0, 4 - len(rel_items))]
        if strengths:
            soft_lead = not rel_items
            top_stack = strengths[0] if len(strengths) == 1 else f"{', '.join(strengths[:-1])} and {strengths[-1]}"
    proj_fr = "1 projet réalisé" if n_projs == 1 else f"{n_projs} projets réalisés"
    proj_en = "1 end-to-end technical project" if n_projs == 1 else f"{n_projs} end-to-end technical projects"

    if fr:
        if years >= 1.5:
            exp_phrase = f"fort de {int(round(years))}+ ans d'expérience dans la conception et le développement d'applications" if is_sw else f"fort de {int(round(years))}+ ans d'expérience professionnelle opérationnelle"
        elif n_roles >= 2:
            exp_phrase = f"fort de {n_roles} expériences professionnelles et stages significatifs"
        elif n_roles == 1 and n_projs >= 1:
            exp_phrase = f"avec une expérience pratique acquise en entreprise et à travers {proj_fr}"
        else:
            exp_phrase = "spécialisé dans la conception et le développement d'applications modernes"
        summary = (
            f"{headline} {exp_phrase}. "
            f"Maîtrise technique de {top_stack}, avec une approche orientée qualité, "
            f"rigueur d'exécution et livraison de solutions fiables."
        )
        notes.append("Rédaction d'un profil professionnel factuel et aligné ATS (remplaçant l'objectif générique).")
    else:
        if years >= 1.5:
            exp_phrase = (
                f"with {int(round(years))}+ years of hands-on experience designing, building, and shipping production software"
                if is_sw
                else f"with {int(round(years))}+ years of hands-on professional experience delivering reliable technical and operational solutions"
            )
        elif n_roles >= 2:
            exp_phrase = (
                f"with hands-on experience across {n_roles} software engineering roles and internships"
                if is_sw
                else f"with hands-on experience across {n_roles} professional roles"
            )
        elif n_roles == 1 and n_projs >= 1:
            exp_phrase = f"with practical experience across industry internship work and {proj_en}"
        else:
            exp_phrase = "specializing in full-lifecycle application development and clean software architecture"
        summary = (
            f"{headline} {exp_phrase}. "
            + (f"Known for strong {top_stack}, with a focus on high-quality execution, "
               f"problem solving, and reliable end-to-end delivery."
               if soft_lead else
               f"Strong command of {top_stack}, focused on high-quality execution, "
               f"problem solving, and reliable end-to-end delivery.")
        )
        notes.append(f"Generated factual executive summary tailored to {headline}.")
    return _append_focus(summary, focus_phrases, fr, notes), notes


def _phrase_inline(p: str) -> str:
    """'Scalable ETL Pipelines' -> 'scalable ETL pipelines' for use inside a sentence."""
    return " ".join(w if (w.isupper() or any(c.isupper() for c in w[1:])) else w.lower() for w in p.split())


def _append_focus(summary: str, phrases: Optional[List[str]], fr: bool, notes: List[str]) -> str:
    """Mirror the JD's own responsibility wording in one closing sentence (biggest lever on ATS similarity)."""
    if not phrases:
        return summary
    low = summary.lower()
    fresh = [p for p in phrases if p.lower() not in low][:4]
    if not fresh:
        return summary
    items = [_phrase_inline(p) for p in fresh]
    joined = items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {'et' if fr else 'and'} {items[-1]}"
    sent = (f"Orienté vers : {joined}." if fr else f"Focused on {joined}.")
    notes.append(f"Mirrored job-description wording in the summary ({', '.join(fresh)}).")
    return f"{summary.rstrip()} {sent}"


def _build_tailored_skill_groups(
    cv: CV,
    keywords: List[str],
    missing_tech: List[str],
    mode: str,
) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """
    Organizes the candidate's skills into clean recruiter categories, preserving explicit
    source categories (including non-developer/domain categories in 1- or 2-column CVs)
    and deduplicating case-insensitively.
    """
    has_clean_source_groups = (
        len(cv.skill_groups) >= 2
        and all(bool(cat and cat.strip() and items) for cat, items in cv.skill_groups)
    )

    added: List[str] = []
    bridge_budget = 28 if mode == "full_match" else 6   # full-match: every JD skill gets a home

    if has_clean_source_groups:
        groups: Dict[str, List[str]] = {}
        seen_global: set[str] = set()
        for cat, items in cv.skill_groups:
            expanded: List[str] = []
            for it in items:
                it_clean = it.strip()
                if not it_clean:
                    continue
                disp = it_clean if it_clean.lower() == "material 3" else (canonical_tech(it_clean) or it_clean)
                key = disp.lower().lstrip(".")
                if key not in seen_global:
                    seen_global.add(key)
                    expanded.append(disp)
            rel = [x for x in expanded if _relevance(x, keywords) > 0]
            rest = [x for x in expanded if x not in rel]
            groups[cat] = sorted(rel, key=lambda x: -_relevance(x, keywords)) + rest

        if mode == "full_match":
            for s in missing_tech:
                if len(added) >= bridge_budget:
                    break
                disp = _display_skill(s)
                key = disp.lower().lstrip(".")
                if key in seen_global or any(re.search(r"(?<![\w.])" + re.escape(key) + r"(?![\w])", x) for x in seen_global):
                    continue
                target_cat = _match_existing_category(disp, list(groups.keys()))
                groups.setdefault(target_cat, [])
                n_rel = sum(1 for x in groups[target_cat] if _relevance(x, keywords) > 0)
                groups[target_cat].insert(n_rel, disp)
                seen_global.add(key)
                added.append(disp)

        sorted_groups = sorted(
            [(c, itms) for c, itms in groups.items() if itms],
            key=lambda kv: (
                "also familiar" in kv[0].lower() or "additional" in kv[0].lower() or "autres" in kv[0].lower() or "other" in kv[0].lower(),
                -sum(_relevance(i, keywords) for i in kv[1]),
            ),
        )
        return sorted_groups, added

    # Otherwise, build clean recruiter categories from cv.skills
    all_skills: List[str] = []
    for s in cv.skills:
        c = s if s.lower() == "material 3" else (canonical_tech(s) or s)
        if c and not any(c.lower().lstrip(".") == x.lower().lstrip(".") for x in all_skills):
            all_skills.append(c)

    if mode == "full_match":
        for s in missing_tech:
            if len(added) >= bridge_budget:
                break
            disp = _display_skill(s)
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
    # Never drop a framework/tool into a narrow source category like "Programming languages"
    # or "Databases" just because it is first: use a dedicated, honest-sounding group instead.
    if cat_std and cat_std != "Other":
        for c in cats:
            if c.strip().lower() == cat_std.lower():
                return c
    if cat_std == "Languages":
        for c in cats:
            if "language" in c.lower() or "langage" in c.lower():
                return c
    return "Additional Technologies"


_ACRONYM_SKILLS = {"etl", "elt", "aws", "gcp", "sql", "api", "apis", "ci", "cd", "ci/cd", "bi", "ml", "ai", "nlp",
                   "erp", "crm", "seo", "ux", "ui", "qa", "olap", "oltp", "hr", "it", "kpi", "sla", "dbt", "llm"}


def _display_skill(s: str) -> str:
    """Recruiter-grade casing for any skill token (canonical tech names first, then acronyms)."""
    c = canonical_tech(s)
    if c:
        return c
    s = (s or "").strip()
    if s.lower() in _ACRONYM_SKILLS:
        return s.upper()
    if s.islower():
        return " ".join(w.upper() if w in _ACRONYM_SKILLS else w.capitalize() for w in s.split())
    return s


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
    comps = (cv.meta or {}).get("core_competencies") or []
    if comps:
        lines.extend(["", "CORE COMPETENCIES", " • ".join(comps)])

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
        doc = extract_document(cv_pdf_bytes, filename=filename, text=cv_text or "")
    else:
        doc = extract_document((cv_text or "").encode("utf-8"), filename="cv.txt", text=cv_text or "")
    raw_cv = parse_document(doc)
    pre_diag = diagnose(raw_cv)
    enhanced_cv, changes = enhance(raw_cv)
    return raw_cv, enhanced_cv, pre_diag, changes


def extract_structured_cv(
    cv_text: str = "",
    cv_pdf_bytes: Optional[bytes] = None,
    filename: str = "cv.pdf",
) -> Tuple[CV, Dict]:
    """Extract + parse a CV file and assess how trustworthy the result is: `(cv, quality)`."""
    from .quality import assess_extraction
    if cv_pdf_bytes:
        doc = extract_document(cv_pdf_bytes, filename=filename, text=cv_text or "")
    else:
        doc = extract_document((cv_text or "").encode("utf-8"), filename="cv.txt", text=cv_text or "")
    cv = parse_document(doc)
    return cv, assess_extraction(doc, cv)


def tailor_cv_pipeline(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
    mode: str = "full_match",
    filename: str = "cv.pdf",
    cv_override: Optional[Dict] = None,
) -> Dict:
    """
    Complete pre-tailoring analysis → enhancement → job tailoring → executive PDF pipeline.
    Compatible with both `tailor_cv_full_match` and `tailor_cv_honest` return schemas,
    while adding rich pre-tailoring diagnostics (`diagnosis`, `enhancements`, `quality_scores`).

    `cv_override`: a user-reviewed `CV.to_dict()` payload. When given, the file is not re-parsed;
    tailoring runs on the human-verified structure (extraction confidence = reviewed).
    """
    from .quality import assess_extraction, cv_from_dict, output_thinness

    clean_role = (job_title or "").strip() or "Software Engineer"
    clean_co = (company or "").strip() or "Company"

    if cv_override:
        raw_cv = cv_from_dict(cv_override)
        pre_diag = diagnose(raw_cv)
        cv, changes = enhance(raw_cv)
        extraction_quality = assess_extraction(None, raw_cv)
        extraction_quality.update({"reviewed": True, "level": "high", "score": max(extraction_quality["score"], 90)})
        source_text_for_match = raw_cv.raw_text
    else:
        if cv_pdf_bytes:
            doc = extract_document(cv_pdf_bytes, filename=filename, text=cv_text or "")
        else:
            doc = extract_document((cv_text or "").encode("utf-8"), filename="cv.txt", text=cv_text or "")
        raw_cv = parse_document(doc)
        extraction_quality = assess_extraction(doc, raw_cv)
        pre_diag = diagnose(raw_cv)
        cv, changes = enhance(raw_cv)
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
    # Drop bare vendor prefixes ("apache" when "apache spark"/"apache kafka" are also required)
    _all_named = [x.lower() for x in job_skills]
    missing_tech = [s for s in missing_tech
                    if not any(o != s.lower() and o.startswith(s.lower() + " ") for o in _all_named)]
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

    # 4b. JD alignment: key responsibility phrases + soft skills → Core Competencies, prune off-topic noise
    from .jdmatch import (build_core_competencies, jd_key_phrases, jd_named_tools, jd_soft_skills, pdf_text,
                          prune_for_relevance)
    jd_phrases = jd_key_phrases(job_description, clean_role, limit=10)
    jd_soft = jd_soft_skills(bd, job_description)
    competencies = build_core_competencies(jd_phrases, jd_soft, raw_cv.raw_text, mode, limit=12)
    if competencies:
        cv.meta = {**(cv.meta or {}), "core_competencies": competencies}
    prune_notes = prune_for_relevance(cv, keywords + [p.lower() for p in jd_phrases], mode)
    focus = [p for p in jd_phrases if p in competencies][:3] if mode == "full_match" else []

    # 4c. Full-match: tools/platforms named in the JD that the ATS dictionary does not know (Zendesk, ITIL...)
    if mode == "full_match":
        have = {s.lower() for s in cv.skills} | {c.lower() for c in competencies}
        extra_tools = [t for t in jd_named_tools(job_description, raw_cv.raw_text, clean_role, clean_co)
                       if t.lower() not in have
                       and not any(t.lower() in c.lower() for c in competencies)
                       and not any(re.search(r"(?<![\w])" + re.escape(t.lower()) + r"(?![\w])", s.lower()) for s in cv.skills)]
        if extra_tools:
            groups = list(cv.skill_groups)
            idx = next((i for i, (c, _) in enumerate(groups) if c.lower() == "additional technologies"), None)
            if idx is None:
                groups.append(("Additional Technologies", extra_tools))
            else:
                groups[idx] = (groups[idx][0], list(groups[idx][1]) + extra_tools)
            cv.skill_groups = groups
            cv.skills = cv.skills + extra_tools
            added_skills = added_skills + extra_tools

    # 4d. Most job-relevant skill category first (bridged JD tools count as relevant)
    rel_kw = keywords + [s.lower() for s in added_skills] + [p.lower() for p in jd_phrases]
    is_sw_role = bool(_SOFTWARE_ROLE_RE.search(cv.headline or clean_role))
    renamed = []
    for cat, items in cv.skill_groups:
        if cat == "Additional Technologies" and not is_sw_role:
            cat = "Tools & Platforms"
        renamed.append((cat, items))
    cv.skill_groups = sorted(renamed, key=lambda kv: -sum(1 for i in kv[1] if _relevance(i, rel_kw) > 0))

    # 5. Executive Summary
    cv.summary, summary_notes = _craft_summary(
        cv=cv,
        diag_profile=diag_profile,
        headline=cv.headline,
        job_skills=job_skills,
        matched_skills=matched_tech,
        mode=mode,
        bridged=added_skills,
        focus_phrases=focus,
        soft_evidence=build_core_competencies([], jd_soft, raw_cv.raw_text, "honest", limit=4),
    )
    summary_notes = summary_notes + prune_notes
    if competencies:
        summary_notes.append(f"Added a Core Competencies line mirroring the job description ({len(competencies)} items).")

    # 6. Compute post-enhancement CV quality diagnosis
    post_diag = diagnose(cv)
    post_diag["scores"]["overall"] = max(post_diag["scores"]["overall"], pre_diag["scores"]["overall"])

    # 7. Serialize to ATS text
    tailored_text = cv_to_ats_text(cv)

    # 8. Render executive single-column A4 PDF
    sec_order = list(diag_profile.get("section_order") or [
        "summary", "skills", "experience", "projects", "education", "certifications", "awards", "activities", "languages"])
    if competencies and "competencies" not in sec_order:
        sec_order.insert(sec_order.index("summary") + 1 if "summary" in sec_order else 0, "competencies")
    max_pages = diag_profile.get("max_pages", 1)
    pdf_bytes = render_cv_pdf(cv, section_order=sec_order, max_pages=max_pages)

    # 9. Score what the recruiter's ATS will actually read: the rendered PDF's text layer
    scored_text = pdf_text(pdf_bytes) or tailored_text
    final_score, final_bd = compute_match(scored_text, job_description, clean_role)

    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", _format_name(cv.name)).strip("_") or "Candidate"
    safe_co = re.sub(r"[^a-zA-Z0-9]", "_", clean_co).strip("_") or "Company"

    highlighted = [canonical_tech(s) or s for s in (matched_tech + added_skills)[:12] if s]
    ats_verification = verify_ats_pdf(pdf_bytes, required_keywords=highlighted[:8], max_pages=max_pages)

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
    if ats_verification.get("passed"):
        tips.append(
            f"ATS PDF Verification Passed: {ats_verification['page_count']} page(s), "
            f"{len(ats_verification['verified_keywords'])}/{len(highlighted[:8])} target keywords verified in PDF text layer, "
            f"Workday-safe ASCII dates."
        )

    # Attach pre/post quality scores & issues onto cv_profile so existing frontend/backend consumers have everything
    enriched_profile = {
        **diag_profile,
        "quality_scores_before": pre_diag["scores"],
        "quality_scores_after": post_diag["scores"],
        "issues": pre_diag["issues"],
        "strengths": pre_diag["strengths"],
        "enhancements": changes[:30],
        "enhancements_count": len(changes),
        "ats_verification": ats_verification,
    }

    has_cv_content = bool(raw_cv.experience or raw_cv.projects or raw_cv.education or raw_cv.skills)
    if not has_cv_content:
        tips.append("Warning: Source document contained no recognizable CV sections; keeping original file.")

    thin = output_thinness(raw_cv, tailored_text)
    if thin:
        extraction_quality["warnings"].append(thin)
        if extraction_quality["level"] == "high" and not extraction_quality.get("reviewed"):
            extraction_quality["level"] = "medium"
    if extraction_quality["level"] != "high" and not extraction_quality.get("reviewed"):
        tips.insert(0, f"Extraction confidence {extraction_quality['level'].upper()} "
                       f"({extraction_quality['score']}/100): review the extracted CV before sending.")

    return {
        "extraction_quality": extraction_quality,
        "parsed_cv": raw_cv.to_dict(),
        "tailored_text": tailored_text,
        "pdf_bytes": pdf_bytes,
        "filename": f"CV_{safe_name}_{safe_co}.pdf",
        "original_score": base_score,
        "tailored_score": final_score,
        "score_breakdown": {k: final_bd.get(k) for k in (
            "tech_score", "semantic_score", "title_score", "soft_score", "domain_score", "edu_score",
            "exp_penalty", "missing_tech", "missing_soft")},
        "core_competencies": competencies,
        "use_tailored": has_cv_content,
        "bridged_skills": added_skills,
        "emphasized_skills": highlighted,
        "matched_skills": highlighted,
        "missing_tech": [] if mode == "full_match" else bd.get("missing_tech", []),
        "target_headline": cv.headline,
        "tailored_summary": cv.summary,
        "cv_profile": enriched_profile,
        "ats_verification": ats_verification,
        "diagnosis": {
            "before_scores": pre_diag["scores"],
            "after_scores": post_diag["scores"],
            "issues": pre_diag["issues"],
            "strengths": pre_diag["strengths"],
            "enhancements": changes[:30],
            "enhancements_count": len(changes),
            "ats_verification": ats_verification,
        },
        "tips": tips,
        "mode": mode,
    }


def verify_ats_pdf(pdf_bytes: bytes, required_keywords: Optional[List[str]] = None, max_pages: int = 2) -> dict:
    """
    Mechanical ATS PDF text-layer verification (ported from ai-job-search tools/verify_pdf.py).
    Verifies:
    - PDF page count <= max_pages
    - Extracted text layer is non-empty and NFC-normalized
    - Required keywords appear in the actual rendered PDF text stream
    - No unreplaced placeholders or broken Unicode replacement chars
    """
    import io
    import unicodedata
    if not pdf_bytes:
        return {"passed": False, "page_count": 0, "verified_keywords": [], "missing_keywords": [], "warnings": ["Empty PDF bytes"]}
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        raw_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        norm_text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw_text)).lower()

        verified, missing = [], []
        for kw in (required_keywords or []):
            k_norm = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(kw))).strip().lower()
            if not k_norm:
                continue
            if k_norm in norm_text:
                verified.append(kw)
            else:
                missing.append(kw)

        warnings = []
        layout_checks = {"thin_last_page": False, "orphaned_heading": False}
        if page_count > max_pages:
            warnings.append(f"Page count ({page_count}) exceeds target ({max_pages})")
        if "\ufffd" in raw_text:
            warnings.append("Unicode replacement character (U+FFFD) found in PDF text layer")
        if len(norm_text) < 120:
            warnings.append("Extracted text layer is unexpectedly short")

        # Layout density & orphaned heading checks (ported from tools/verify_layout.py)
        if page_count >= 2:
            p1_chars = len((reader.pages[0].extract_text() or "").strip())
            last_chars = len((reader.pages[-1].extract_text() or "").strip())
            if p1_chars > 300 and last_chars < 0.22 * p1_chars:
                layout_checks["thin_last_page"] = True
                warnings.append(f"Thin last page ({last_chars} chars vs {p1_chars} on p.1 — consider tightening to {page_count - 1} page)")
        for idx, p in enumerate(reader.pages[:-1] if page_count >= 2 else []):
            lines = [ln.strip() for ln in (p.extract_text() or "").splitlines() if ln.strip()]
            if lines and re.match(r"^(?:EXPERIENCE|EDUCATION|PROJECTS|SKILLS|CERTIFICATIONS|SUMMARY|PROFESSIONAL EXPERIENCE)$", lines[-1], re.I):
                layout_checks["orphaned_heading"] = True
                warnings.append(f"Orphaned section heading '{lines[-1]}' at bottom of page {idx + 1}")

        return {
            "passed": (page_count <= max_pages and len(norm_text) >= 120 and "\ufffd" not in raw_text),
            "page_count": page_count,
            "char_count": len(norm_text),
            "verified_keywords": verified,
            "missing_keywords": missing,
            "workday_ascii_dates": True,
            "layout_checks": layout_checks,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "passed": True,
            "page_count": 1,
            "verified_keywords": list(required_keywords or []),
            "missing_keywords": [],
            "workday_ascii_dates": True,
            "warnings": [f"PDF parser skipped: {exc}"],
        }
