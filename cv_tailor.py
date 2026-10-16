"""
cv_tailor.py — Senior-Grade Pre-Tailoring CV Analyzer & Executive ATS PDF Resume Generator

Workflow:
1. Deep Pre-Tailoring Analysis (`analyze_cv_profile`):
   - Classifies the CV archetype/type (Mobile, Full-Stack, Backend/Cloud, Data/AI, Product/Management, Academic/Graduate, etc.)
   - Detects CV language (EN/FR), seniority calibration, quantified impact density, and section structure
   - Repairs all PyPDF2 extraction artifacts (split words, broken hyphenation, multi-line skill wraps, URL splits)
2. Intelligent Professional Tailoring (`tailor_cv_full_match` & `tailor_cv_honest`):
   - Tailors headline, executive summary, categorized technical skills, and bullet prioritization to match the target role
   - Preserves 100% of authentic employment history, dates, metrics, and clickable links (LinkedIn, GitHub, Google Play, Live Demos)
3. Executive ATS PDF Generation (`generate_ats_pdf`):
   - Produces a clean, recruiter-grade, single-column A4 PDF with balanced typography and zero page-split widows.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Set, Tuple

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable,
        PageBreak,
        KeepTogether,
    )
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from cv_matcher import compute_match, TECH_SKILLS, SOFT_SKILLS


# ─── PyPDF2 Kerning & Extraction Repair Rules ─────────────────────────────────

_WORD_REPAIRS = [
    (r"\bf\s+aster\b", "faster"),
    (r"\bAls\s+o\b", "Also"),
    (r"\bals\s+o\b", "also"),
    (r"\ban\s+d\b", "and"),
    (r"\bGoogle\s+P\s+lay\b", "Google Play"),
    (r"\bP\s+lay\s+Console\b", "Play Console"),
    (r"\bAra\s+bic\b", "Arabic"),
    (r"\bimpac\s+t\b", "impact"),
    (r"\bdevel\s+oper\b", "developer"),
    (r"\barchitec\s+ture\b", "architecture"),
    (r"\bperfor\s+mance\b", "performance"),
    (r"\bapplica\s+tion(s?)\b", r"application\1"),
    (r"\bintegra\s+tion\b", "integration"),
    (r"\bprodu\s+ction\b", "production"),
    (r"\bcolla\s+boration\b", "collaboration"),
    (r"\brespo\s+nsiveness\b", "responsiveness"),
    (r"\bmain\s+tained\b", "maintained"),
    (r"\bstandar\s+dizing\b", "standardizing"),
    (r"\bconfigu\s+rable\b", "configurable"),
    (r"\bnotifica\s+tions\b", "notifications"),
    (r"\bauthenti\s+cation\b", "authentication"),
    (r"\bGitHub\s+Actions\s*\)", "GitHub Actions)"),
    (r"\(\s+", "("),
    (r"\s+\)", ")"),
]

_ACRONYMS = {
    "aws", "gcp", "api", "apis", "rest", "sql", "ios", "ci/cd", "ui", "ux", "html", "css",
    "json", "graphql", "fcm", "mvvm", "mvc", "mvi", "jwt", "sdk", "nosql", "php", "qa",
    "tdd", "bdd", "oop", "solid", "llm", "nlp", "ai", "ml", "s3", "ec2", "rds", "pwa",
}

_SPECIAL = {
    "graphql": "GraphQL",
    "ios": "iOS",
    "nosql": "NoSQL",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "github": "GitHub",
    "github actions": "GitHub Actions",
    "gitlab": "GitLab",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node/express": "Node.js / Express",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "react native": "React Native",
    "fastapi": "FastAPI",
    "sqlalchemy": "SQLAlchemy",
    "tailwindcss": "TailwindCSS",
    "riverpod": "Riverpod",
    "gorouter": "GoRouter",
    "getx": "GetX",
    "bloc": "BLoC",
    "clean architecture": "Clean Architecture",
    "rest/json apis": "REST/JSON APIs",
    "rest apis": "REST APIs",
    "aws s3": "AWS S3",
    "ci/cd": "CI/CD",
    "google play console": "Google Play Console",
    "app store connect": "App Store Connect",
}

_SENIORITY_WORDS = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|head|chief|director|vp|manager|junior|jr\.?|intern)\b",
    re.I,
)


def clean_extracted_text(text: str) -> str:
    """Repairs PyPDF2 extraction artifacts: broken hyphenation, kerning splits, and spacing."""
    if not text:
        return ""
    # Join hyphenated words broken across lines: "full -\nstack" -> "full-stack"
    text = re.sub(r"(\b[a-zA-Z0-9]+)\s*-\s*\n\s*([a-zA-Z0-9]+\b)", r"\1-\2", text)
    # Fix inline spaced hyphens inside compound words/URLs: "cross -platform", "yassine -youssef", "kickoff -sports.tn"
    text = re.sub(r"(\b[a-zA-Z0-9]+)\s+-\s*([a-zA-Z0-9]+\b)", r"\1-\2", text)
    text = re.sub(r"(\b[a-zA-Z0-9]+)-\s+([a-zA-Z0-9]+\b)", r"\1-\2", text)
    # Fix numeric ranges: "12 –72h" -> "12–72h"
    text = re.sub(r"(\d)\s*[–-]\s*(\d)", r"\1–\2", text)
    # Fix space before comma/period/colon/semicolon: "Tunisia , Monastir" -> "Tunisia, Monastir"
    text = re.sub(r"[ \t]+([,.;:])", r"\1", text)
    # Apply word-level kerning repairs
    for pat, repl in _WORD_REPAIRS:
        text = re.sub(pat, repl, text)
    return text


def _display_skill(s: str) -> str:
    s_clean = (s or "").strip()
    if not s_clean:
        return ""
    low = s_clean.lower()
    if low in _SPECIAL:
        return _SPECIAL[low]
    if low in _ACRONYMS:
        return low.upper()
    if not s_clean.islower():
        return s_clean
    return " ".join(
        _SPECIAL.get(w, w.upper() if w in _ACRONYMS else w.capitalize())
        for w in low.split()
    )


def _pretty_category_name(cat: str) -> str:
    c = (cat or "").strip().rstrip(":")
    if not c:
        return "Technical Skills"
    low = c.lower()
    mapping = {
        "mobile": "Mobile & Cross-Platform",
        "backend & cloud": "Backend & Cloud",
        "release & quality": "Release, CI/CD & Quality",
        "web": "Web & Frontend",
        "also familiar with": "Additional Technologies",
        "general skills": "Core Technologies",
    }
    return mapping.get(low, c[0].upper() + c[1:] if c else c)


# ─── Multi-Format CV Parser ───────────────────────────────────────────────────

_SECTION_HEADERS = {
    "summary": {
        "SUMMARY", "PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY", "PROFILE", "PROFESSIONAL PROFILE",
        "ABOUT", "ABOUT ME", "CAREER SUMMARY", "OBJECTIVE", "CAREER OBJECTIVE",
        "PROFIL", "PROFIL PROFESSIONNEL", "RÉSUMÉ", "A PROPOS", "À PROPOS",
    },
    "experience": {
        "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "EXPERIENCE", "EMPLOYMENT HISTORY",
        "WORK HISTORY", "CAREER HISTORY", "RELEVANT EXPERIENCE",
        "EXPÉRIENCE PROFESSIONNELLE", "EXPÉRIENCES PROFESSIONNELLES", "EXPÉRIENCE", "PARCOURS PROFESSIONNEL",
    },
    "projects": {
        "PERSONAL PROJECTS", "PERSONAL PROJECTS (FLUTTER)", "PROJECTS", "FEATURED PROJECTS",
        "SELECTED PROJECTS", "KEY PROJECTS", "ACADEMIC PROJECTS", "PORTFOLIO",
        "PROJETS", "PROJETS PERSONNELS", "PROJETS RÉALISÉS", "PROJETS ACADÉMIQUES",
    },
    "skills": {
        "TECHNICAL SKILLS", "SKILLS", "CORE COMPETENCIES", "SKILLS & TECHNOLOGIES",
        "TECHNOLOGIES", "TECH STACK", "KEY SKILLS", "AREAS OF EXPERTISE",
        "COMPÉTENCES", "COMPÉTENCES TECHNIQUES", "EXPERTISE TECHNIQUE",
    },
    "education": {
        "EDUCATION", "ACADEMIC BACKGROUND", "EDUCATION & QUALIFICATIONS", "ACADEMIC QUALIFICATIONS",
        "FORMATION", "ÉDUCATION", "ÉTUDES", "DIPLÔMES",
    },
    "certifications": {
        "CERTIFICATIONS", "LICENSES & CERTIFICATIONS", "CERTIFICATES", "TRAINING & CERTIFICATIONS",
        "CERTIFICATIONS & AWARDS",
    },
    "languages": {
        "LANGUAGES", "LANGUAGE PROFICIENCY", "SPOKEN LANGUAGES",
        "LANGUES", "COMPÉTENCES LINGUISTIQUES",
    },
}


def _match_section_header(line: str) -> Optional[str]:
    norm = re.sub(r"\s+", " ", line or "").strip().rstrip(":—–-").strip().upper()
    if len(norm) > 48:
        return None
    for sec_key, names in _SECTION_HEADERS.items():
        if norm in names:
            return sec_key
    return None


_MONTH_PAT = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Janv|Févr|Mars|Avr|Mai|Juin|Juil|Août|Sept|Oct|Nov|Déc)"
_DATE_TOKEN = rf"(?:{_MONTH_PAT}\.?\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_DATE_RANGE_RE = re.compile(
    rf"({_DATE_TOKEN}\s*[–\-—to]+\s*(?:{_DATE_TOKEN}|Present|Current|Now|Aujourd'hui|Actuel)|\b(?:19|20)\d{{2}}\b)",
    re.I,
)


def parse_candidate_cv(cv_text: str) -> Dict:
    """
    Parses raw CV text into structured sections preserving 100% of authentic content.
    Handles PyPDF2 multi-line skill wraps, single-space or double-space dates, pipe-separated
    project links, and both English and French section headers.
    """
    cleaned = clean_extracted_text(cv_text)
    raw_lines = [re.sub(r"[ \t]+", " ", l).strip() for l in cleaned.splitlines() if l.strip()]
    if not raw_lines:
        return {
            "name": "Candidate",
            "title": "Software Engineer",
            "contact": "",
            "summary": "",
            "experience": [],
            "projects": [],
            "skills": {},
            "education": [],
            "certifications": [],
            "languages": [],
        }

    name = raw_lines[0]
    title = ""
    idx = 1
    if len(raw_lines) > 1 and not _match_section_header(raw_lines[1]):
        second = raw_lines[1]
        if "@" not in second and not re.search(r"\+\d{2,}", second):
            title = second
            idx = 2

    contact_parts = []
    while idx < len(raw_lines):
        line = raw_lines[idx]
        if _match_section_header(line):
            break
        # Handle inline "Location: Berlin, Germany" or "Email: ..." in plain text CVs
        line_clean = re.sub(r"^(?:Location|Email|Phone|Tel|LinkedIn|GitHub|Portfolio)\s*:\s*", "", line, flags=re.I).strip()
        if line_clean:
            contact_parts.append(line_clean)
        idx += 1

    contact = "  •  ".join(contact_parts)

    sections: Dict = {
        "summary": "",
        "experience": [],
        "projects": [],
        "skills": {},
        "education": [],
        "certifications": [],
        "languages": [],
    }

    current_sec = None
    curr_item = None
    curr_bullets: List[str] = []
    last_skill_cat: Optional[str] = None

    BULLET_CHARS = ("•", "●", "-", "*", "–", "—", "▪", "◦")

    def save_item():
        nonlocal curr_item, curr_bullets
        if not curr_item:
            return
        curr_item["bullets"] = [clean_extracted_text(b.strip()) for b in curr_bullets if b.strip()]
        if current_sec == "experience":
            curr_item["role_line"] = f"{curr_item.get('role', '')}  {curr_item.get('date', '')}".strip()
            comp_loc = []
            if curr_item.get("company"):
                comp_loc.append(curr_item["company"])
            if curr_item.get("location"):
                comp_loc.append(curr_item["location"])
            curr_item["company_line"] = " — ".join(comp_loc)
            sections["experience"].append(curr_item)
        elif current_sec == "projects":
            curr_item["title_line"] = (
                f"{curr_item.get('title', '')}  |  {curr_item.get('link', '')}".strip(" |")
                if curr_item.get("link")
                else curr_item.get("title", "")
            )
            sections["projects"].append(curr_item)
        curr_item = None
        curr_bullets = []

    def _parse_exp_header(line: str) -> Optional[Dict]:
        # Pattern 1: "Senior Mobile Developer at TechCorp (2021 - Present)"
        m_at = re.match(r"^(.+?)\s+at\s+([^()]+?)\s*\(([^)]+)\)\s*$", line, re.I)
        if m_at:
            return {
                "role": m_at.group(1).strip(),
                "company": m_at.group(2).strip(),
                "location": "",
                "date": m_at.group(3).strip(),
                "bullets": [],
            }
        # Pattern 2: Line ending with a date range: "Mobile Developer Dec 2024 – Present"
        m_dr = re.match(
            rf"^(.+?)\s+({_DATE_TOKEN}\s*[–\-—to]+\s*(?:{_DATE_TOKEN}|Present|Current|Now|Aujourd'hui|Actuel))\s*$",
            line,
            re.I,
        )
        if m_dr:
            role_part = m_dr.group(1).strip().rstrip("|—–-,")
            date_part = m_dr.group(2).strip()
            return {
                "role": role_part,
                "date": date_part,
                "company": "",
                "location": "",
                "bullets": [],
            }
        return None

    def _parse_project_header(line: str) -> Optional[Dict]:
        if line.startswith(BULLET_CHARS):
            return None
        # Match project lines with pipe separator or em-dash subtitle or known link labels
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            proj_title = parts[0].rstrip("|—–- ").strip()
            link_str = " | ".join(parts[1:]).replace("·", "|").strip()
            link_str = re.sub(r"\s*\|\s*", " | ", link_str)
            return {"title": proj_title, "link": link_str, "bullets": []}
        if "—" in line and not line.endswith("."):
            return {"title": line.strip(), "link": "", "bullets": []}
        return None

    while idx < len(raw_lines):
        line = raw_lines[idx]
        sec_hit = _match_section_header(line)
        if sec_hit:
            save_item()
            current_sec = sec_hit
            idx += 1
            continue

        if current_sec == "summary":
            sections["summary"] = (sections["summary"] + " " + line).strip()
            idx += 1

        elif current_sec == "experience":
            if line.startswith(BULLET_CHARS):
                curr_bullets.append(line.lstrip("•●-*–—▪◦ ").strip())
            else:
                exp_hdr = _parse_exp_header(line)
                if exp_hdr:
                    save_item()
                    curr_item = exp_hdr
                elif curr_item and not curr_item["company"] and not curr_bullets:
                    # Company + Location line immediately following Role + Date line
                    if "—" in line or "–" in line:
                        parts = re.split(r"\s*[—–]\s*", line, maxsplit=1)
                        curr_item["company"] = parts[0].strip()
                        curr_item["location"] = parts[1].strip() if len(parts) > 1 else ""
                    elif "," in line:
                        parts = [p.strip() for p in line.split(",") if p.strip()]
                        curr_item["company"] = parts[0]
                        curr_item["location"] = ", ".join(parts[1:])
                    else:
                        curr_item["company"] = line.strip()
                elif curr_item and curr_bullets:
                    # Wrapped continuation of the previous bullet line
                    curr_bullets[-1] = (curr_bullets[-1] + " " + line).strip()
            idx += 1

        elif current_sec == "projects":
            if line.startswith(BULLET_CHARS):
                curr_bullets.append(line.lstrip("•●-*–—▪◦ ").strip())
            else:
                proj_hdr = _parse_project_header(line)
                if proj_hdr:
                    save_item()
                    curr_item = proj_hdr
                elif curr_item and curr_bullets:
                    curr_bullets[-1] = (curr_bullets[-1] + " " + line).strip()
                elif not curr_item:
                    curr_item = {"title": line.strip(), "link": "", "bullets": []}
            idx += 1

        elif current_sec == "skills":
            line_clean = line.lstrip("•●-*–—▪◦ ").strip()
            if ":" in line_clean:
                cat, val = line_clean.split(":", 1)
                cat_name = cat.strip()
                items = [x.strip() for x in val.split(",") if x.strip()]
                sections["skills"][cat_name] = items
                last_skill_cat = cat_name
            elif last_skill_cat and sections["skills"].get(last_skill_cat):
                # Continuation line of a wrapped skill category (e.g. "AWS \n S3, FastAPI, Node/Express")
                prev_list = sections["skills"][last_skill_cat]
                extra = [x.strip() for x in line_clean.split(",") if x.strip()]
                if extra and prev_list:
                    # Check if the previous line broke mid-token (like "AWS" + "S3" or unclosed "(")
                    last_tok = prev_list[-1]
                    first_tok = extra[0]
                    open_parens = sum(x.count("(") - x.count(")") for x in prev_list)
                    if (
                        last_tok.upper() == "AWS" and first_tok.upper().startswith("S3")
                    ) or (
                        open_parens > 0 and not first_tok.startswith("(")
                    ):
                        prev_list[-1] = f"{last_tok} {first_tok}".strip()
                        extra = extra[1:]
                prev_list.extend(extra)
            else:
                items = [x.strip() for x in re.split(r"[,•|]", line_clean) if x.strip()]
                if items:
                    sections["skills"].setdefault("Core Technologies", []).extend(items)
                    last_skill_cat = "Core Technologies"
            idx += 1

        elif current_sec == "education":
            sections["education"].append(line)
            idx += 1

        elif current_sec == "certifications":
            sections["certifications"].append(line.lstrip("•●-*–—▪◦ ").strip())
            idx += 1

        elif current_sec == "languages":
            sections["languages"].append(line.lstrip("•●-*–—▪◦ ").strip())
            idx += 1

        else:
            idx += 1

    save_item()

    # Final pass on skills: merge split parentheses ("Firebase (Auth", "FCM)") and normalize category names
    cleaned_skills: Dict[str, List[str]] = {}
    for cat, raw_items in sections["skills"].items():
        merged = _split_skill_items(raw_items)
        cleaned_skills[cat] = [clean_extracted_text(i) for i in merged if i.strip()]
    sections["skills"] = cleaned_skills
    sections["summary"] = clean_extracted_text(sections["summary"])

    return {
        "name": name,
        "title": title,
        "contact": contact,
        "summary": sections["summary"],
        "experience": sections["experience"],
        "projects": sections["projects"],
        "skills": sections["skills"],
        "education": sections["education"],
        "certifications": sections["certifications"],
        "languages": sections["languages"],
    }


def _split_skill_items(items: List[str]) -> List[str]:
    """Re-join items the PDF parser split inside parentheses: 'Firebase (Auth', 'FCM)' → one item."""
    out, buf, depth = [], [], 0
    for it in items:
        buf.append(it)
        depth += it.count("(") - it.count(")")
        if depth <= 0:
            out.append(", ".join(buf))
            buf, depth = [], 0
    if buf:
        out.append(", ".join(buf))
    return out


# ─── Stage 1: Deep Pre-Tailoring CV Type & Structure Analyzer ─────────────────

def analyze_cv_profile(
    cv_text: str,
    parsed: Optional[Dict] = None,
    job_title: str = "",
    job_description: str = "",
) -> Dict:
    """
    Deeply analyzes the candidate's CV BEFORE tailoring to identify:
    - CV Type / Domain Archetype (Mobile, Full-Stack, Backend/Cloud, Data/AI, Product, Academic/Graduate, Executive)
    - Language (English vs French)
    - Seniority Level & Years of Experience
    - Quantified Impact Density (metrics %, counts, multipliers)
    - Structural Layout Strategy (section ordering best suited to this CV type)
    """
    if parsed is None:
        parsed = parse_candidate_cv(cv_text)

    low_text = (cv_text or "").lower()
    title_low = (parsed.get("title") or "").lower()

    # 1. Detect CV Language
    fr_signals = sum(
        1 for w in ("expérience", "compétences", "formation", "langues", "développeur", "ingénieur", "ans d'expérience")
        if w in low_text
    )
    cv_lang = "fr" if fr_signals >= 2 else "en"

    # 2. Extract Years of Experience
    yr_matches = re.findall(r"(\d+)\+?\s*(?:years?|ans?)\s*(?:of\s+experience|d'expérience)?", low_text)
    years_exp = max((int(y) for y in yr_matches if int(y) < 40), default=0)
    if years_exp == 0 and parsed.get("experience"):
        all_years = [int(y) for e in parsed["experience"] for y in re.findall(r"\b(20\d{2})\b", e.get("date", ""))]
        if all_years:
            years_exp = max(1, 2026 - min(all_years))

    # 3. Calibrate Seniority
    if any(w in title_low for w in ("lead", "principal", "staff", "architect", "head", "director", "manager")) or years_exp >= 8:
        seniority = "Lead / Principal"
    elif "senior" in title_low or "sr" in title_low or years_exp >= 5:
        seniority = "Senior"
    elif years_exp >= 2 or len(parsed.get("experience", [])) >= 2:
        seniority = "Mid-Senior" if years_exp >= 4 else "Mid-Level"
    else:
        seniority = "Junior / Graduate"

    # 4. Classify CV Archetype / Domain Type
    all_skills_text = " ".join(
        [title_low, parsed.get("summary", "").lower()]
        + [i.lower() for items in parsed.get("skills", {}).values() for i in items]
    )
    mobile_hits = sum(1 for k in ("flutter", "dart", "ios", "android", "react native", "swift", "kotlin", "bloc", "riverpod") if k in all_skills_text)
    web_hits = sum(1 for k in ("react", "next.js", "vue", "angular", "typescript", "tailwindcss", "fastapi", "node", "django", "full-stack", "full stack") if k in all_skills_text)
    backend_hits = sum(1 for k in ("microservices", "kubernetes", "docker", "aws", "gcp", "postgres", "graphql", "kafka", "golang", "spring") if k in all_skills_text)
    ai_hits = sum(1 for k in ("machine learning", "pytorch", "tensorflow", "llm", "nlp", "data science", "deep learning", "pandas") if k in all_skills_text)
    pm_hits = sum(1 for k in ("product manager", "roadmap", "stakeholder", "user research", "scrum master", "figma") if k in all_skills_text)

    if mobile_hits >= 3 and web_hits >= 2:
        cv_type = "Mobile & Full-Stack Engineering CV"
        domain_focus = "Cross-Platform Mobile (Flutter/iOS/Android) & Full-Stack Web"
    elif mobile_hits >= 2:
        cv_type = "Mobile Application Engineering CV"
        domain_focus = "iOS / Android & Cross-Platform Mobile Architecture"
    elif ai_hits >= 2:
        cv_type = "AI, Data Science & ML Engineering CV"
        domain_focus = "Machine Learning, NLP & Data Systems"
    elif web_hits >= 3:
        cv_type = "Full-Stack Software Engineering CV"
        domain_focus = "Modern Web Frontend & Scalable Backend APIs"
    elif backend_hits >= 3:
        cv_type = "Backend, Cloud & DevOps Engineering CV"
        domain_focus = "Distributed Systems, Cloud Infrastructure & APIs"
    elif pm_hits >= 2:
        cv_type = "Product & Technical Management CV"
        domain_focus = "Product Strategy, Agile Delivery & Cross-Functional Leadership"
    elif len(parsed.get("experience", [])) == 0 and len(parsed.get("education", [])) > 0:
        cv_type = "Academic & Early-Career Technical CV"
        domain_focus = "Academic Excellence & Applied Engineering Projects"
    else:
        cv_type = "Professional Software Engineering CV"
        domain_focus = "Software Architecture, Delivery & Engineering Quality"

    # 5. Count Quantified Impact Metrics in Experience & Summary
    exp_text = (parsed.get("summary") or "") + " " + " ".join(
        b for e in parsed.get("experience", []) for b in e.get("bullets", [])
    )
    metrics_found = re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|x|\+|k\+?|ms|s\b|apps\b|features\b|downloads\b|users\b)", exp_text, re.I)

    # 6. Determine Optimal Section Order based on CV Type & Target Role
    if len(parsed.get("experience", [])) == 0 and len(parsed.get("education", [])) > 0:
        section_order = ["summary", "education", "skills", "projects", "certifications", "languages"]
        layout_strategy = "Education & Projects First (Early-Career / Academic Optimization)"
    elif seniority in ("Lead / Principal", "Senior") and len(parsed.get("experience", [])) >= 3:
        section_order = ["summary", "skills", "experience", "projects", "education", "certifications", "languages"]
        layout_strategy = "Executive Impact Layout (Summary → Core Stack → Career Track Record)"
    else:
        section_order = ["summary", "skills", "experience", "projects", "education", "certifications", "languages"]
        layout_strategy = "Technical ATS Priority Layout (Summary → Categorized Skills → Quantified Experience → Projects)"

    return {
        "cv_type": cv_type,
        "domain_focus": domain_focus,
        "language": cv_lang,
        "seniority": seniority,
        "years_experience": years_exp,
        "metrics_count": len(metrics_found),
        "roles_count": len(parsed.get("experience", [])),
        "projects_count": len(parsed.get("projects", [])),
        "skill_categories_count": len(parsed.get("skills", {})),
        "section_order": section_order,
        "layout_strategy": layout_strategy,
    }


# ─── PDF Hyperlink Extractor & Smart Project/App Link Mapper ──────────────────

def extract_pdf_links(pdf_bytes: Optional[bytes]) -> Dict:
    """
    Extracts clickable links from the original CV PDF so the tailored PDF keeps 100% of them:
    - linkedin: candidate's LinkedIn profile URL
    - github: candidate's root GitHub profile URL
    - portfolio: personal website if any
    - app_links: list of Google Play / App Store URLs (e.g. from "Live apps: League Hunters | LOL Cards")
    - project_rows: list of URL lists for each project row in document order
    """
    out = {"linkedin": "", "github": "", "portfolio": "", "app_links": [], "project_rows": []}
    if not pdf_bytes:
        return out
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        rows = []
        for page_idx, page in enumerate(reader.pages):
            for a in (page.get("/Annots") or []):
                o = a.get_object()
                act = o.get("/A")
                uri = act.get_object().get("/URI") if act else None
                if not uri:
                    continue
                uri = str(uri).strip()
                rect = [float(x) for x in o.get("/Rect", [0, 0, 0, 0])]
                low = uri.lower()
                if "linkedin.com/in/" in low and not out["linkedin"]:
                    out["linkedin"] = uri
                    continue
                if re.match(r"^https?://(www\.)?github\.com/[^/]+/?$", low) and not out["github"]:
                    out["github"] = uri
                    continue
                if low.startswith("mailto:") or low.startswith("tel:"):
                    continue
                if "play.google.com/store" in low or "apps.apple.com" in low:
                    if uri not in out["app_links"]:
                        out["app_links"].append(uri)
                    continue
                rows.append((page_idx, -rect[1], rect[0], uri))
        rows.sort()
        grouped: List[List[str]] = []
        last_key = None
        for page_idx, neg_y, x, uri in rows:
            key = (page_idx, neg_y)
            if last_key and key[0] == last_key[0] and abs(key[1] - last_key[1]) < 8:
                if uri not in grouped[-1]:
                    grouped[-1].append(uri)
            else:
                grouped.append([uri])
            last_key = key
        out["project_rows"] = grouped
    except Exception:
        pass
    return out


def _short_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")


def _esc(text: str) -> str:
    """Tidy PDF-extraction artefacts and escape text for ReportLab Paragraph markup."""
    t = clean_extracted_text(text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pretty_skill_item(item: str) -> str:
    it = clean_extracted_text(item.strip())
    low = it.lower()
    if low in _SPECIAL:
        return _SPECIAL[low]
    if it.islower() and (len(it) <= 3 or low in _ACRONYMS):
        return it.upper() if low != "ios" else "iOS"
    return it


# ─── Stage 3: Executive ATS PDF Renderer ──────────────────────────────────────

def generate_ats_pdf(
    name: str,
    headline: str,
    contact: str,
    summary: str,
    skills: Dict[str, List[str]],
    experience: List[Dict],
    projects: List[Dict],
    education: List[str],
    languages: List[str],
    links: Optional[Dict] = None,
    certifications: Optional[List[str]] = None,
    cv_profile: Optional[Dict] = None,
) -> bytes:
    """
    Generates an executive, recruiter-grade, ATS-compliant A4 PDF resume.
    Adapts section titles and ordering to the analyzed `cv_profile` (CV type & language).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import KeepTogether

    links = links or {}
    cv_profile = cv_profile or {}
    is_fr = cv_profile.get("language") == "fr"

    ACCENT = colors.HexColor("#16324F")      # Executive deep navy
    INK = colors.HexColor("#111827")         # Crisp charcoal body text
    MUTED = colors.HexColor("#4B5563")       # Secondary metadata
    RULE = colors.HexColor("#CBD5E1")        # Subtle divider rule
    LINK = colors.HexColor("#1D4ED8")        # Clickable link blue

    def _build_pdf(scale: int = 0) -> Tuple[bytes, int]:
        buf = io.BytesIO()
        LM = RM = (26 if scale == 2 else (30 if scale == 1 else 36))
        TM = BM = (18 if scale == 2 else (22 if scale == 1 else 28))
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=LM,
            rightMargin=RM,
            topMargin=TM,
            bottomMargin=BM,
            title=f"{name} — {headline}",
            author=name,
            subject=f"CV — {headline}",
        )
        W = doc.width - 8

        f_body = 8.05 if scale == 2 else (8.65 if scale == 1 else 9.2)
        l_body = 9.95 if scale == 2 else (11.2 if scale == 1 else 12.6)
        f_role = 8.65 if scale == 2 else (9.3 if scale == 1 else 9.8)
        l_role = 10.4 if scale == 2 else (11.6 if scale == 1 else 12.6)
        sec_space = 3.0 if scale == 2 else (4.5 if scale == 1 else 7.5)
        item_gap = 1.8 if scale == 2 else (3.2 if scale == 1 else 5.0)
        compact = scale > 0

        st_name = ParagraphStyle(
            "Name", fontName="Helvetica-Bold", fontSize=17.0 if scale == 2 else (18.5 if scale == 1 else 20.5), leading=19.5 if scale == 2 else (21 if scale == 1 else 24), alignment=1, textColor=ACCENT
        )
        st_head = ParagraphStyle(
            "Headline", fontName="Helvetica-Bold", fontSize=9.6 if scale == 2 else (10.3 if scale == 1 else 11.0), leading=11.8 if scale == 2 else (13 if scale == 1 else 14), alignment=1, textColor=colors.HexColor("#1E40AF")
        )
        st_contact = ParagraphStyle(
            "Contact", fontName="Helvetica", fontSize=7.9 if scale == 2 else (8.3 if scale == 1 else 8.7), leading=9.8 if scale == 2 else (10.8 if scale == 1 else 11.8), alignment=1, textColor=MUTED
        )
        st_section = ParagraphStyle(
            "Section", fontName="Helvetica-Bold", fontSize=8.9 if scale == 2 else (9.4 if scale == 1 else 9.9), leading=10.5 if scale == 2 else (11.5 if scale == 1 else 12.2), textColor=ACCENT, tracking=0.5
        )
        st_body = ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=f_body, leading=l_body, textColor=INK
        )
        st_role = ParagraphStyle(
            "Role", fontName="Helvetica-Bold", fontSize=f_role, leading=l_role, textColor=INK
        )
        st_date = ParagraphStyle(
            "Date", fontName="Helvetica-Bold", fontSize=7.9 if scale == 2 else (8.3 if scale == 1 else 8.7), leading=l_role, alignment=2, textColor=MUTED
        )
        st_company = ParagraphStyle(
            "Company", fontName="Helvetica-Bold", fontSize=8.2 if scale == 2 else (8.7 if scale == 1 else 9.1), leading=10.0 if scale == 2 else (11.0 if scale == 1 else 11.8), textColor=ACCENT
        )
        st_loc = ParagraphStyle(
            "Loc", fontName="Helvetica-Oblique", fontSize=7.9 if scale == 2 else (8.3 if scale == 1 else 8.7), leading=10.0 if scale == 2 else (11.0 if scale == 1 else 11.8), alignment=2, textColor=MUTED
        )
        st_bullet = ParagraphStyle(
            "Bullet", parent=st_body, leftIndent=10, bulletIndent=1, spaceBefore=0.5 if scale == 2 else (0.9 if scale == 1 else 1.5), leading=9.85 if scale == 2 else (11.0 if scale == 1 else 12.3)
        )
        st_link = ParagraphStyle(
            "Link", fontName="Helvetica", fontSize=7.9 if scale == 2 else (8.3 if scale == 1 else 8.7), leading=l_role, alignment=2, textColor=LINK
        )

        def two_col(left, right, ratio=0.74, top=0, bottom=0):
            t = Table([[left, right]], colWidths=[W * ratio, W * (1 - ratio)])
            t.setStyle(
                TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), top),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
                ])
            )
            return t

        def section(title_en: str, title_fr: str = ""):
            label = (title_fr if is_fr and title_fr else title_en).upper()
            return [
                Spacer(1, sec_space),
                Paragraph(label, st_section),
                HRFlowable(width="100%", thickness=0.75, color=RULE, spaceBefore=1.0 if scale == 2 else 1.5, spaceAfter=2.0 if scale == 2 else (3.0 if scale == 1 else 4.2)),
            ]

        def link_markup(label: str, url: str) -> str:
            return f'<link href="{_esc(url)}" color="#1D4ED8">{_esc(label)}</link>' if url else _esc(label)

        story = []

        # ── Header ────────────────────────────────────────────────────────────
        story.append(Paragraph(_esc(name), st_name))
        if headline:
            story.append(Spacer(1, 1))
            story.append(Paragraph(_esc(headline), st_head))

        parts = [p.strip() for p in re.split(r"\s*[•|]\s*", contact or "") if p.strip()]
        details, profiles = [], []
        for p in parts:
            p_clean = clean_extracted_text(p)
            low = p_clean.lower()
            if low == "linkedin" or "linkedin.com/in/" in low:
                url = links.get("linkedin") or (p_clean if low.startswith("http") else f"https://{p_clean}")
                lbl = _short_url(url) if "linkedin.com" in url else "LinkedIn"
                profiles.append(link_markup(lbl, url))
            elif low == "github" or "github.com/" in low:
                url = links.get("github") or (p_clean if low.startswith("http") else f"https://{p_clean}")
                lbl = _short_url(url) if "github.com" in url else "GitHub"
                profiles.append(link_markup(lbl, url))
            elif re.match(r"^(https?://|www\.)", low) or (
                re.search(r"\.(com|io|dev|me|app|net|org|tn)(/|$)", low) and "@" not in p_clean
            ):
                url = p_clean if low.startswith("http") else f"https://{p_clean}"
                profiles.append(link_markup(_short_url(p_clean), url))
            elif "@" in p_clean:
                details.append(link_markup(p_clean, f"mailto:{p_clean}"))
            else:
                details.append(_esc(p_clean))

        sep = "&nbsp;&nbsp;•&nbsp;&nbsp;"
        if details:
            story.append(Spacer(1, 2))
            story.append(Paragraph(sep.join(details), st_contact))
        if profiles:
            story.append(Paragraph(sep.join(profiles), st_contact))
        story.append(Spacer(1, 1))

        # ── Section Builders ──────────────────────────────────────────────────
        def render_summary():
            if not summary:
                return []
            out = section("Professional Summary", "Profil Professionnel")
            out.append(Paragraph(_esc(summary), st_body))
            return out

        def render_skills():
            if not skills:
                return []
            out = section("Technical Skills", "Compétences Techniques")
            for cat, items in skills.items():
                clean_items = [_esc(_pretty_skill_item(i)) for i in items if i and i.strip()]
                if not clean_items:
                    continue
                cat_label = _pretty_category_name(cat)
                out.append(
                    Paragraph(
                        f"<b>{_esc(cat_label)}:</b>&nbsp; {', '.join(clean_items)}",
                        ParagraphStyle("SkillRow", parent=st_body, spaceBefore=1.0 if compact else 1.5, leading=l_body),
                    )
                )
            return out

        def render_experience():
            if not experience:
                return []
            out = section("Professional Experience", "Expérience Professionnelle")
            app_links = links.get("app_links") or []
            for i, exp in enumerate(experience):
                r_title = exp.get("role") or exp.get("role_line", "")
                r_date = exp.get("date", "")
                if not r_date and "  " in r_title:
                    r_title, r_date = r_title.rsplit("  ", 1)
                c_name, c_loc = exp.get("company", ""), exp.get("location", "")
                if not c_name and exp.get("company_line"):
                    c_parts = re.split(r"\s+[—–-]\s+", exp["company_line"], maxsplit=1)
                    c_name = c_parts[0].strip()
                    c_loc = c_parts[1].strip() if len(c_parts) > 1 else ""

                block = [
                    two_col(
                        Paragraph(_esc(r_title.strip()), st_role),
                        Paragraph(_esc(r_date.strip()), st_date),
                        top=0 if i == 0 else item_gap,
                    )
                ]
                if c_name or c_loc:
                    block.append(
                        two_col(
                            Paragraph(_esc(c_name), st_company),
                            Paragraph(_esc(c_loc), st_loc),
                            bottom=0.5,
                        )
                    )
                for b in exp.get("bullets", []):
                    if b.lower().startswith("live apps:") and app_links:
                        prefix, rest = b.split(":", 1)
                        app_names = [a.strip() for a in rest.split("|") if a.strip()]
                        if len(app_names) == len(app_links):
                            linked_apps = " &nbsp;|&nbsp; ".join(
                                link_markup(a_name, a_url) for a_name, a_url in zip(app_names, app_links)
                            )
                            block.append(Paragraph(f"{_esc(prefix)}:&nbsp; {linked_apps}", st_bullet, bulletText="•"))
                            continue
                    block.append(Paragraph(_esc(b), st_bullet, bulletText="•"))
                out.append(KeepTogether(block))
            return out

        def render_projects():
            if not projects:
                return []
            out = section("Selected Projects", "Projets Réalisés")
            for i, proj in enumerate(projects):
                p_title = (proj.get("title") or proj.get("title_line", "")).rstrip("| ").strip()
                p_link = proj.get("link", "")
                if not p_link and "|" in p_title:
                    parts = [x.strip() for x in p_title.split("|") if x.strip()]
                    p_title = parts[0]
                    p_link = " | ".join(parts[1:])
                urls = proj.get("urls") or []
                labels = [x.strip() for x in re.split(r"\s*[|·]\s*", p_link or "") if x.strip()]
                if urls:
                    if len(labels) != len(urls):
                        labels = [("GitHub" if "github.com" in u.lower() else "Live demo" if "vercel.app" in u.lower() else _short_url(u)) for u in urls]
                    link_txt = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(link_markup(lbl, u) for lbl, u in zip(labels, urls))
                else:
                    link_txt = _esc(" | ".join(labels))
                block = [
                    two_col(
                        Paragraph(_esc(p_title), st_role),
                        Paragraph(link_txt, st_link),
                        ratio=0.75,
                        top=0 if i == 0 else (2.5 if compact else 4.2),
                    )
                ]
                for b in proj.get("bullets", []):
                    block.append(Paragraph(_esc(b), st_bullet, bulletText="•"))
                out.append(KeepTogether(block))
            return out

        def render_education():
            if not education:
                return []
            out = section("Education", "Formation")
            i = 0
            while i < len(education):
                line1 = education[i]
                m_yr = re.search(
                    r"^(.*?)\s+((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+|Expected\s+)?\d{4}(?:\s*[–-]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?\d{4}|\s*[–-]\s*Present)?)$",
                    line1.strip(),
                    re.I,
                )
                deg, yr = (m_yr.group(1).strip(), m_yr.group(2).strip()) if m_yr else (line1.strip(), "")
                line2 = education[i + 1] if i + 1 < len(education) else ""
                block = [
                    two_col(
                        Paragraph(_esc(deg), st_role),
                        Paragraph(_esc(yr), st_date),
                        ratio=0.84,
                        top=0 if i == 0 else (2.5 if compact else 4.0),
                    )
                ]
                if line2:
                    block.append(
                        Paragraph(
                            _esc(line2),
                            ParagraphStyle("School", parent=st_body, textColor=MUTED, fontName="Helvetica-Oblique"),
                        )
                    )
                out.append(KeepTogether(block))
                i += 2
            return out

        def render_certifications():
            if not certifications:
                return []
            out = section("Certifications", "Certifications")
            for c in certifications:
                out.append(Paragraph(_esc(c), st_bullet, bulletText="•"))
            return out

        def render_languages():
            if not languages:
                return []
            out = section("Languages", "Langues")
            langs = [p.strip() for l in languages for p in re.split(r"\s*[•|,;]\s*", l) if p.strip()]
            out.append(Paragraph("&nbsp;&nbsp;•&nbsp;&nbsp;".join(_esc(l) for l in langs), st_body))
            return out

        render_map = {
            "summary": render_summary,
            "skills": render_skills,
            "experience": render_experience,
            "projects": render_projects,
            "education": render_education,
            "certifications": render_certifications,
            "languages": render_languages,
        }

        sec_order = cv_profile.get("section_order") or [
            "summary", "skills", "experience", "projects", "education", "certifications", "languages"
        ]
        for sec_name in sec_order:
            fn = render_map.get(sec_name)
            if fn:
                story.extend(fn())

        doc.build(story)
        pdf_data = buf.getvalue()
        buf.close()
        return pdf_data, getattr(doc, "page", 1)

    pdf_data, page_count = _build_pdf(scale=0)
    if page_count == 2 and len(experience) <= 3:
        for s in (1, 2):
            compact_pdf, compact_pages = _build_pdf(scale=s)
            if compact_pages == 1:
                return compact_pdf
    return pdf_data


# ─── Helpers for Relevance, Headline & Summary Crafting ───────────────────────

def _relevance(text: str, keywords: List[str]) -> int:
    t = (text or "").lower()
    return sum(len(re.findall(r"\b" + re.escape(k.lower()) + r"\b", t)) for k in keywords if k)


def _clean_role_title(job_title: str) -> str:
    role = re.sub(r"\((?:remote|hybrid|on-?site|f/h|h/f|m/w/d|m/f/d)[^)]*\)", "", job_title or "", flags=re.I)
    role = re.sub(r"\s*[-–—|,]\s*(remote|hybrid|on-?site|full[- ]time|part[- ]time|contract|cdi|cdd|freelance).*$", "", role, flags=re.I)
    role = " ".join(
        _SPECIAL.get(w.lower())
        or (w.upper() if w.lower() in _ACRONYMS else (w.capitalize() if w.islower() else w))
        for w in role.split()
    ).strip()
    return role or "Software Engineer"


def _honest_headline(cv_title: str, job_title: str, cv_text: str, matched: List[str]) -> str:
    role = _clean_role_title(job_title)
    cv_low, cv_title_low = cv_text.lower(), (cv_title or "").lower()
    role = " ".join(
        w for w in role.split() if not _SENIORITY_WORDS.fullmatch(w) or w.lower() in cv_title_low
    ).strip()
    generic = {"developer", "engineer", "software", "mobile", "app", "application", "programmer", "specialist"}
    core = [w for w in re.findall(r"[a-z+#.]+", role.lower()) if w not in generic and len(w) > 1]
    supported = role and all(re.search(r"\b" + re.escape(w) + r"\b", cv_low) for w in core)
    base = role if supported else (cv_title or role or "Software Engineer")
    return _clean_role_title(base)


def _craft_professional_summary(
    parsed: Dict,
    cv_profile: Dict,
    headline: str,
    company: str,
    job_skills: List[str],
    matched_skills: List[str],
) -> Tuple[str, List[str]]:
    """
    Crafts a polished, natural executive summary that:
    1. Repairs any PDF extraction typos in the candidate's authentic summary.
    2. Aligns the opening title/identity with the target role WITHOUT duplicating the title twice.
    3. Naturally integrates the target job's top technical skills and domain focus.
    Returns (tailored_summary, adjustment_notes).
    """
    own = clean_extracted_text(re.sub(r"\s+", " ", parsed.get("summary") or "").strip())
    notes: List[str] = []

    _ignore = {"app store", "google play", "cross-platform", "state management", "agile", "scrum", "mobile", "remote", "english", "french"}
    priority_skills = [_display_skill(s) for s in job_skills if s.lower() not in _ignore][:5]

    if not own:
        yrs = f"with {cv_profile.get('years_experience')}+ years of experience " if cv_profile.get("years_experience") else ""
        sk_str = ", ".join(priority_skills[:4]) if priority_skills else "modern software architecture and scalable delivery"
        summary = (
            f"{headline} {yrs}specializing in {sk_str}. "
            f"Proven track record of designing, testing, and shipping high-performance production software "
            f"with clean architecture and measurable business impact."
        )
        notes.append(f"Generated executive summary tailored to {headline}.")
        return summary, notes

    # Split candidate's summary into sentences
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", own) if x.strip()]
    if not sents:
        return own, notes

    # Check if sentence 1 starts with a generic role title like "Mobile engineer with 4+ years..."
    # If so, upgrade the role subject to align with the target headline naturally (no double-title repetition!)
    first_sent = sents[0]
    m_lead = re.match(
        r"^(?:Experienced\s+|Senior\s+)?(?:Mobile|Flutter|Full[- ]?Stack|Software|Frontend|Backend|Web|Application)\s+(?:engineer|developer|specialist|architect)(\s+with\s+.+)$",
        first_sent,
        re.I,
    )
    if m_lead and headline:
        sents[0] = f"{headline}{m_lead.group(1)}"
        notes.append(f"Aligned executive summary opening title with target role ({headline}).")

    # Fix grammar in candidate's final sentence if it starts with "Also build..." -> "Also builds..."
    for idx_s, s in enumerate(sents):
        if re.match(r"^Also\s+build\b", s):
            sents[idx_s] = re.sub(r"^Also\s+build\b", "Also experienced in building", s)

    # Check which priority JD skills are not yet mentioned in the summary
    current_summary_low = " ".join(sents).lower()
    unmentioned = [sk for sk in priority_skills if sk.lower() not in current_summary_low][:4]
    if unmentioned:
        if len(unmentioned) == 1:
            clause = f"Core technical focus includes {unmentioned[0]}."
        else:
            clause = f"Core technical focus includes {', '.join(unmentioned[:-1])} and {unmentioned[-1]}."
        # Insert before trailing language sentence if present, otherwise at end
        sents.append(clause)
        notes.append(f"Integrated target role keywords ({', '.join(unmentioned)}) into the Executive Summary.")

    return " ".join(sents).strip(), notes


def _attach_project_links(raw_projects: List[Dict], links: Dict) -> List[Dict]:
    """
    Attaches clickable URLs from `extract_pdf_links` to each project BEFORE sorting projects
    so re-ordering projects by relevance never scrambles or drops their clickable links.
    """
    rows = links.get("project_rows") or []
    out = []
    for idx, p in enumerate(raw_projects):
        q = dict(p)
        if len(rows) == len(raw_projects):
            q["urls"] = rows[idx]
        else:
            # Match by slug/domain keyword if counts differ
            t_low = (p.get("title") or "").lower()
            matched_row = []
            for r in rows:
                for u in r:
                    u_low = u.lower()
                    if (
                        ("job" in t_low and ("job" in u_low or "vercel" in u_low))
                        or ("kickoff" in t_low and "kickoff" in u_low)
                        or ("checkin" in t_low and "checkin" in u_low)
                        or ("rorent" in t_low and ("pfe" in u_low or "rorent" in u_low))
                        or ("pickcar" in t_low and "pickcar" in u_low)
                    ):
                        matched_row = r
                        break
                if matched_row:
                    break
            if matched_row:
                q["urls"] = matched_row
        out.append(q)
    return out


def _sort_experience_bullets(bullets: List[str], keywords: List[str]) -> List[str]:
    """
    Re-orders achievement bullets by relevance to the target job while keeping
    trailers like 'Live apps: ...' anchored at the bottom of the role.
    """
    regular = [b for b in bullets if not b.lower().startswith("live apps:")]
    trailers = [b for b in bullets if b.lower().startswith("live apps:")]
    regular_sorted = sorted(regular, key=lambda b: -_relevance(b, keywords))
    return regular_sorted + trailers


def _pick_category(skill: str, cats: List[str]) -> str:
    """Places an added skill into the candidate's EXISTING category that fits best."""
    s = skill.lower()
    rules = [
        (("flutter", "dart", "swift", "kotlin", "ios", "android", "mobile", "cross-platform", "react native",
          "jetpack", "swiftui", "xcode", "bloc", "riverpod", "provider", "getx", "material", "ui"),
         ("mobile", "cross-platform")),
        (("api", "rest", "graphql", "sql", "database", "firebase", "aws", "gcp", "azure", "cloud", "mongodb",
          "postgres", "redis", "grpc", "websocket", "json", "backend", "node", "fastapi", "django", "spring", "docker", "kubernetes"),
         ("backend", "cloud", "data", "api")),
        (("ci/cd", "ci", "cd", "git", "jenkins", "deploy", "fastlane", "codemagic",
          "pipeline", "gradle", "store", "play", "test", "jest", "cypress", "pytest", "junit", "tdd", "quality"),
         ("release", "quality", "tool", "devops", "testing", "architecture")),
        (("typescript", "javascript", "react", "vue", "angular", "next", "html", "css", "tailwind", "redux", "vite", "web", "frontend"),
         ("web", "frontend", "front")),
    ]
    for kws, cat_hints in rules:
        if any(k == s or k in s for k in kws):
            for c in cats:
                if any(h in c.lower() for h in cat_hints):
                    return c
    for c in cats:
        if any(h in c.lower() for h in ("also familiar", "other", "additional", "core")):
            return c
    return cats[0] if cats else "Core Technologies"


# ─── Senior CV Engine Integration (Pre-Tailoring Diagnosis + Enhancement + Tailoring) ───

def extract_cv_text(content: bytes, filename: str = "cv.pdf") -> str:
    """
    Layout-aware text extraction for PDF (single-column, two-column/sidebar, LaTeX),
    DOCX, and plain text files using `cv_engine.extract.extract_document`.
    """
    try:
        from cv_engine.extract import extract_document
        doc = extract_document(content, filename=filename)
        if doc.text and doc.text.strip():
            return doc.text
    except Exception:
        pass
    return ""


def tailor_cv_honest(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
) -> Dict:
    """
    Runs the Senior CV Engine in Honest Mode:
    1. Layout-aware extraction & structure parsing (`cv_engine.extract` + `cv_engine.parse`)
    2. Pre-tailoring diagnosis (`cv_engine.analyze.diagnose`)
    3. Honest mechanical enhancement (`cv_engine.enhance`: fixes typos, repeated words, weak openers,
       past-tense verbs for ended roles, tech casing, and moves filler bullets into stack tags)
    4. Re-orders skills, experience bullets, and projects by relevance to the target job
    5. Renders a clean single-column A4 executive PDF (`cv_engine.render.render_cv_pdf`)
    """
    from cv_engine.tailor import tailor_cv_pipeline
    return tailor_cv_pipeline(
        cv_text=cv_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        cv_pdf_bytes=cv_pdf_bytes,
        mode="honest",
    )


def tailor_cv_full_match(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
) -> Dict:
    """
    Runs the Senior CV Engine in Full-Match Professional Mode:
    1. Layout-aware extraction & structure parsing (`cv_engine.extract` + `cv_engine.parse`)
    2. Pre-tailoring diagnosis (`cv_engine.analyze.diagnose`)
    3. Mechanical enhancement (`cv_engine.enhance`)
    4. Aligns headline, crafts a bilingual EN/FR executive summary, bridges missing JD tech skills
       into clean recruiter categories, and prioritizes bullets & projects by relevance
    5. Renders a clean single-column A4 executive PDF (`cv_engine.render.render_cv_pdf`)
    """
    from cv_engine.tailor import tailor_cv_pipeline
    return tailor_cv_pipeline(
        cv_text=cv_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        cv_pdf_bytes=cv_pdf_bytes,
        mode="full_match",
    )


def tailor_cv(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
) -> Dict:
    """Backward-compatible entry point delegating to `tailor_cv_full_match`."""
    return tailor_cv_full_match(cv_text, job_title, company, job_description, cv_pdf_bytes=cv_pdf_bytes)

