"""
Job Evaluator — "should I apply?" verdict for a single posting.

Deterministic port of the career-ops evaluation framework (modes/oferta.md +
modes/_shared.md). Each posting is scored 1–5 across the same dimensions
career-ops uses, with every finding tagged by evidence confidence:

  A  Role summary        archetype, seniority, remote / location
  B  CV match            skills / experience / seniority vs. the real CV
  C  Work authorization  sponsorship / citizenship / clearance gates
  D  Compensation        transparency + stated range
  E  Customization plan  keywords to mirror, gaps to address
  G  Posting legitimacy  age, repost pattern, specificity, realism, scam &
                         third-party signals → High Confidence / Caution / Suspicious

Global score → verdict:  ≥ 4.0 APPLY · 3.0–3.9 CONSIDER · < 3.0 SKIP
(career-ops: "apply better to fewer" — below 4.0 is not worth a full application
unless there is a specific reason.)

The candidate's CV is only read, never modified.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

URGENT_DAYS = 7

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}

_DEADLINE_TRIGGER_RE = re.compile(
    r"(?:application\s+deadline|apply\s+(?:by|before|no\s+later\s+than)|"
    r"closing\s+date|applications?\s+close(?:\s+on)?|posting\s+closes(?:\s+on)?|"
    r"date\s+limite(?:\s+de\s+candidature)?|bewerbungsfrist|sista\s+ans[oö]kningsdag)"
    r"\s*[:\-–]?\s*([^\n.;]{4,40})",
    re.I,
)


def _parse_date_Loose(raw: str) -> Optional[date]:
    if not raw:
        return None
    s = raw.strip()
    # 1. ISO YYYY-MM-DD
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 2. Month DD, YYYY (e.g. October 28, 2026)
    m = re.search(r"\b([A-Za-zÀ-ÿ]{3,10})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", s)
    if m and m.group(1).lower() in _MONTH_MAP:
        try:
            return date(int(m.group(3)), _MONTH_MAP[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            pass
    # 3. DD Month YYYY (e.g. 28 October 2026)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-zÀ-ÿ]{3,10})\.?,?\s+(20\d{2})\b", s)
    if m and m.group(2).lower() in _MONTH_MAP:
        try:
            return date(int(m.group(3)), _MONTH_MAP[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    return None


def extract_deadline(job: dict) -> dict:
    """
    Extract explicit application deadline from structured fields or JD text
    and classify urgency / expiry (ported from ai-job-search tools/rank_state.py).
    """
    raw_dl = str(job.get("deadline") or job.get("valid_through") or "").strip()
    dl_date = _parse_date_Loose(raw_dl)
    if not dl_date:
        desc = job.get("description") or ""
        m = _DEADLINE_TRIGGER_RE.search(desc)
        if m:
            dl_date = _parse_date_Loose(m.group(1))
    if not dl_date:
        return {"deadline": None, "days_remaining": None, "is_urgent": False, "is_expired": False, "label": None}

    today = datetime.utcnow().date()
    days_rem = (dl_date - today).days
    iso = dl_date.isoformat()
    is_expired = days_rem < 0
    is_urgent = 0 <= days_rem <= URGENT_DAYS
    if is_expired:
        label = f"Deadline passed ({iso})"
    elif days_rem == 0:
        label = "Closes today!"
    elif is_urgent:
        label = f"Closes in {days_rem}d ({iso})"
    else:
        label = f"Closes {iso}"
    return {
        "deadline": iso,
        "days_remaining": days_rem,
        "is_urgent": is_urgent,
        "is_expired": is_expired,
        "label": label,
    }

AGGREGATOR_DOMAINS = {
    "recruit.net", "builtin.com", "zippia.com", "expertini.com", "jooble.org", "adzuna.com", "neuvoo.com",
    "talent.com", "jobisjob.com", "jobrapido.com", "careerjet.com", "trovit.com", "simplyhired.com",
    "jobtome.com", "lensa.com", "jora.com", "jobg8.com", "geebo.com", "careerbuilder.com", "monster.com",
}

ARCHETYPES = {
    "Mobile Engineer": ["flutter", "dart", "swift", "kotlin", "react native", "ios", "android", "mobile"],
    "Frontend Engineer": ["react", "vue", "angular", "frontend", "front-end", "css", "typescript", "next.js"],
    "Backend Engineer": ["backend", "back-end", "api", "microservices", "django", "fastapi", "spring", "node"],
    "Full-Stack Engineer": ["full stack", "full-stack", "fullstack"],
    "AI / ML Engineer": ["machine learning", "llm", "deep learning", "pytorch", "tensorflow", "rag", "nlp", "ai engineer"],
    "Data Engineer / Analyst": ["data engineer", "etl", "spark", "airflow", "warehouse", "analytics", "sql", "bi "],
    "DevOps / Cloud": ["devops", "kubernetes", "terraform", "aws", "gcp", "azure", "sre", "ci/cd"],
    "Product / Project": ["product manager", "roadmap", "stakeholder", "project manager", "scrum master"],
}

AUTH_BLOCKERS = [
    (r"\b(?:must|need to|required to) (?:be|have) (?:legally )?(?:authori[sz]ed|eligible) to work in (?:the )?([A-Z][\w .]+)", "Requires existing work authorization"),
    (r"\b(?:no|not able to|unable to|cannot|can't|will not|won't|do not|does not)\s+(?:offer\s+|provide\s+)?(?:visa )?sponsor(?:ship)?", "No visa sponsorship"),
    (r"\bsponsorship (?:is )?not (?:available|offered|provided)", "No visa sponsorship"),
    (r"\b(?:u\.?s\.? citizens?|citizenship) (?:only|required)\b", "Citizenship required"),
    (r"\bsecurity clearance\b|\bTS/SCI\b|\bsecret clearance\b", "Security clearance required"),
    (r"\bgreen card holders?\b", "Green card / residency required"),
]
AUTH_POSITIVE = [
    r"\bvisa sponsorship (?:is )?(?:available|offered|provided)\b", r"\bwill sponsor\b", r"\bwe sponsor\b",
    r"\brelocation (?:support|package|assistance)\b", r"\bwork from anywhere\b", r"\bremote[- ](?:first|worldwide|anywhere)\b",
    r"\bopen to (?:international|global) candidates\b", r"\bwith or without a valid\b",
]
SCAM_PATTERNS = [
    (r"\b(?:telegram|whatsapp)\b.{0,40}\b(?:contact|message|interview|reach)", "Interview over a chat app"),
    (r"\b(?:registration|training|starter[- ]kit|equipment|application|processing) fee\b|\b(?:you|candidates?) (?:must|will need to) pay\b", "Asks the candidate to pay"),
    (r"\b(?:wire transfer|western union|gift cards?|check deposit)\b", "Unusual payment instructions"),
    (r"\b(?:earn|make) \$?\d[\d,]* (?:per|a) (?:day|week)\b.{0,40}\bno experience\b", "Too-good-to-be-true pay"),
    (r"\bunlimited earning potential\b|\bbe your own boss\b|\bmlm\b", "MLM / commission-only language"),
]
THIRD_PARTY_PATTERNS = [
    r"\bour client\b", r"\bon behalf of (?:our|a) client\b", r"\b(?:staffing|recruitment) agency\b",
    r"\bc2c\b|\bcorp[- ]to[- ]corp\b|\bw2 only\b", r"\bconfidential (?:client|company)\b",
]
THIRD_PARTY_COMPANY = re.compile(r"\b(staffing|recruit\w*|talent|consult\w*|outsourc\w*|placement|headhunt\w*)\b", re.I)
GENERIC_TITLE = re.compile(r"\b(rockstar|ninja|guru|wizard)\b", re.I)

# Verified first-party ATS hosts (ported from ai-job-search apply.md + FreeHire 14-ATS list)
VERIFIED_ATS_HOSTS: Dict[str, str] = {
    "greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "ashbyhq.com": "Ashby",
    "myworkdayjobs.com": "Workday",
    "smartrecruiters.com": "SmartRecruiters",
    "teamtailor.com": "Teamtailor",
    "workable.com": "Workable",
    "bamboohr.com": "BambooHR",
    "personio.de": "Personio",
    "personio.com": "Personio",
    "recruitee.com": "Recruitee",
    "pinpointhq.com": "Pinpoint",
    "rippling.com": "Rippling",
    "breezy.hr": "BreezyHR",
    "jobvite.com": "Jobvite",
    "icims.com": "iCIMS",
    "successfactors.com": "SuccessFactors",
}

# Zero-width / bidirectional override / tag Unicode characters (ported from tools/posting_guard.py)
_INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff\U000e0000-\U000e007f]"
)

_PROMPT_INJECTION_PATTERNS = [
    (r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+"
     r"(?:instructions?|prompts?|rules?|directions?)\b", "Prompt-injection directive"),
    (r"\b(?:you\s+are\s+now|new\s+instructions?:|system\s+prompt:|assistant:|"
     r"<\s*/?\s*(?:system|instruction|prompt)\s*>)", "Role/delimiter hijack"),
    (r"(?:<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<<SYS>>)", "Model chat-template token"),
    (r"\b(?:do\s+not\s+mention|never\s+mention|hide\s+this\s+from\s+the\s+user)\b", "Concealment instruction"),
]

# Recruiter Easter-Egg / Attention Check patterns (alert candidate to include secret phrase)
_ATTENTION_CHECK_PATTERNS = [
    (r"\b(?:if\s+you(?:'ve|\s+have)?\s+read\s+this(?:\s+far)?|to\s+show\s+you\s+read\s+this|"
     r"to\s+prove\s+you(?:'re|\s+are)\s+(?:human|not\s+a\s+bot|paying\s+attention))[^.\n]{0,120}",
     "Recruiter attention check"),
    (r"\b(?:include|mention|write|put|add)\s+(?:the\s+)?(?:word|phrase|code\s*word|secret\s+word)\s+"
     r"['\"“”‘’]?([A-Za-z0-9_-]{3,30})['\"“”‘’]?\s+in\s+your\s+(?:application|cover\s+letter|resume|cv|message|note)",
     "Secret keyword required in application"),
]

# Language gate patterns (ported from 04-job-evaluation.md)
_LANGUAGES_CATALOG = [
    "german", "dutch", "french", "spanish", "arabic", "italian", "portuguese",
    "danish", "swedish", "norwegian", "finnish", "polish", "mandarin", "chinese",
    "japanese", "korean", "hebrew", "turkish", "russian",
]


def sanitize_and_guard_posting(text: str) -> dict:
    """
    Sanitize untrusted job posting text and detect:
    1) hidden zero-width/bidi Unicode characters
    2) adversarial prompt-injection directives
    3) legitimate recruiter easter-egg / attention-check instructions
    """
    raw = text or ""
    invisible_count = len(_INVISIBLE_RE.findall(raw))
    cleaned = _INVISIBLE_RE.sub("", raw)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

    injections = []
    for pat, label in _PROMPT_INJECTION_PATTERNS:
        m = re.search(pat, cleaned, re.I)
        if m:
            snippet = cleaned[max(0, m.start() - 20): min(len(cleaned), m.end() + 40)].replace("\n", " ").strip()
            injections.append({"label": label, "snippet": snippet[:120]})

    attention_checks = []
    for pat, label in _ATTENTION_CHECK_PATTERNS:
        m = re.search(pat, cleaned, re.I)
        if m:
            snippet = cleaned[max(0, m.start() - 10): min(len(cleaned), m.end() + 50)].replace("\n", " ").strip()
            attention_checks.append({"label": label, "snippet": snippet[:140]})

    return {
        "cleaned_text": cleaned,
        "invisible_chars_stripped": invisible_count,
        "injections": injections,
        "attention_checks": attention_checks,
        "has_injection": bool(injections or invisible_count >= 5),
        "has_attention_check": bool(attention_checks),
    }


_FIRST_PARTY_VENDOR_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "smartrecruiters": "SmartRecruiters",
    "teamtailor": "Teamtailor",
    "workable": "Workable",
    "bamboohr": "BambooHR",
    "personio": "Personio",
    "recruitee": "Recruitee",
    "pinpoint": "Pinpoint",
    "rippling": "Rippling",
    "breezy": "BreezyHR",
    "breezyhr": "BreezyHR",
    "jobvite": "Jobvite",
    "icims": "iCIMS",
    "successfactors": "SuccessFactors",
}


def detect_ats_provenance(job: dict) -> dict:
    """Identify whether a job comes directly from a verified first-party ATS."""
    urls = [job.get("job_url_direct") or "", job.get("url") or ""]
    site = (job.get("site") or "").lower()
    for u in urls:
        dom = _domain(u)
        for host, vendor in VERIFIED_ATS_HOSTS.items():
            if host in dom:
                return {"is_first_party": True, "vendor": vendor, "domain": dom}
    if site.startswith("ats_"):
        raw_v = site.replace("ats_", "").strip().lower()
        if raw_v in _FIRST_PARTY_VENDOR_NAMES:
            return {"is_first_party": True, "vendor": _FIRST_PARTY_VENDOR_NAMES[raw_v], "domain": site}
    if site == "ats":
        return {"is_first_party": True, "vendor": "Company ATS", "domain": "ats"}
    return {"is_first_party": False, "vendor": None, "domain": _domain(urls[0] or urls[1])}


def assess_language_gate(job: dict, cv_text: str = "") -> dict:
    """
    Language Gate (ported from 04-job-evaluation.md):
    Detects explicit fluency requirements (e.g. 'Fluent in German', 'C1 Dutch required',
    'German (C1/C2)') and compares against the candidate's CV text.
    """
    desc = job.get("description") or ""
    title = job.get("title") or ""
    blob = f"{title}\n{desc}"
    cv_low = (cv_text or "").lower()

    required_langs: List[str] = []
    evidence_map: Dict[str, str] = {}

    for lang in _LANGUAGES_CATALOG:
        # Match patterns like: "fluent in German", "German fluency", "German (C1", "native German",
        # "business fluent German", "speaking German is required", "must speak German"
        pats = [
            rf"\b(?:fluent|fluency|proficient|proficiency|native|c1|c2|b2|business\s+level|"
            rf"mother\s+tongue|strong\s+command|written\s+and\s+spoken)\b[^.\n]{{0,35}}\b{lang}\b",
            rf"\b{lang}\b[^.\n]{{0,30}}\b(?:fluent|fluency|required|mandatory|essential|c1|c2|native|"
            rf"is\s+a\s+must|speaking\s+required)\b",
            rf"\b(?:must|need\s+to)\s+speak\s+{lang}\b",
        ]
        for p in pats:
            m = re.search(p, blob, re.I)
            if m:
                cap = lang.capitalize()
                if cap not in required_langs:
                    required_langs.append(cap)
                    evidence_map[cap] = m.group(0).replace("\n", " ").strip()[:100]
                break

    matched = []
    missing = []
    for cap in required_langs:
        if cv_low and re.search(rf"\b{cap.lower()}\b", cv_low):
            matched.append(cap)
        else:
            missing.append(cap)

    if not required_langs:
        return {
            "score": 4.5,
            "status": "supported",
            "required_languages": [],
            "matched_languages": [],
            "missing_languages": [],
            "evidence": {},
            "note": "No special non-English language gate detected.",
        }
    if missing and cv_low:
        return {
            "score": 1.8,
            "status": "supported",
            "required_languages": required_langs,
            "matched_languages": matched,
            "missing_languages": missing,
            "evidence": evidence_map,
            "note": f"Requires {', '.join(missing)} fluency not found on your CV.",
        }
    if missing and not cv_low:
        return {
            "score": 3.0,
            "status": "partial",
            "required_languages": required_langs,
            "matched_languages": [],
            "missing_languages": missing,
            "evidence": evidence_map,
            "note": f"Requires {', '.join(required_langs)} fluency — verify before applying.",
        }
    return {
        "score": 4.8,
        "status": "supported",
        "required_languages": required_langs,
        "matched_languages": matched,
        "missing_languages": [],
        "evidence": evidence_map,
        "note": f"Requires {', '.join(required_langs)} — matched on your CV.",
    }


def _clamp(x: float, lo: float = 1.0, hi: float = 5.0) -> float:
    return round(max(lo, min(hi, x)), 1)


def _domain(url: str) -> str:
    try:
        return re.sub(r"^www\.", "", urlparse(url or "").netloc.lower())
    except Exception:
        return ""


def detect_archetype(title: str, desc: str) -> str:
    text = f"{title} {title} {title} {desc}".lower()
    scores = {a: sum(text.count(k) for k in kws) for a, kws in ARCHETYPES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"


def _salary_numbers(text: str) -> List[int]:
    nums = []
    for m in re.finditer(r"(?:[$€£]|usd|eur|gbp)\s?(\d{2,3}(?:[,.]\d{3})+|\d{2,3}\s?[kK])", text or "", re.I):
        raw = m.group(1).replace(",", "").replace(".", "").replace(" ", "")
        nums.append(int(raw[:-1]) * 1000 if raw.lower().endswith("k") else int(raw))
    return nums


# ── Block G: posting legitimacy ────────────────────────────────────────────────
def assess_legitimacy(job: dict, sighting: Optional[dict] = None, liveness: Optional[dict] = None) -> dict:
    title, desc = job.get("title") or "", job.get("description") or ""
    company, url = job.get("company") or "", job.get("job_url_direct") or job.get("url") or ""
    low = desc.lower()
    signals: List[dict] = []
    risk = 0.0

    def add(signal, finding, impact, reliability, status="supported"):
        nonlocal risk
        risk += impact
        signals.append({"signal": signal, "finding": finding, "impact": impact,
                        "reliability": reliability, "status": status})

    # 1. Liveness (high reliability)
    if liveness:
        res = liveness.get("result")
        if res == "expired":
            add("Still open", f"Posting looks closed ({liveness.get('reason', '')})", 3.0, "High")
        elif res == "active":
            add("Still open", "Apply control visible — posting is live", -0.5, "High")
        else:
            add("Still open", f"Could not confirm ({liveness.get('reason', 'unknown')})", 0, "High", "unknown")

    # 2. Posting age (high)
    age = job.get("age_hours")
    if age is None:
        add("Posting age", "Unknown posting date", 0.3, "High", "unknown")
    elif age <= 24 * 30:
        add("Posting age", f"{int(age // 24)} days old — fresh", -0.3, "High")
    elif age <= 24 * 60:
        add("Posting age", f"{int(age // 24)} days old — getting stale", 0.7, "High")
    else:
        add("Posting age", f"{int(age // 24)} days old — likely ghost / evergreen", 1.5, "High")

    # 3. Repost pattern (medium)
    if sighting:
        n_urls, days = sighting.get("distinct_urls", 1), sighting.get("days_tracked", 0)
        if n_urls >= 3:
            add("Repost pattern", f"Re-posted {n_urls}× over {days} days — classic ghost-job signal", 1.2, "Medium")
        elif n_urls == 2:
            add("Repost pattern", f"Seen re-posted once ({days} days ago first)", 0.5, "Medium")
        elif days >= 45:
            add("Repost pattern", f"Listing open for {days}+ days in our history", 0.6, "Medium")

    # 4. Tech specificity in JD (medium)
    pre = (job.get("breakdown") or {}).get("job_skills")
    if pre is not None:
        n_skills = len(pre)
    else:
        try:
            from cv_matcher import TECH_SKILLS
            blob = " " + re.sub(r"[^a-z0-9+#.]+", " ", f"{title} {desc}".lower()) + " "
            n_skills = sum(1 for s in TECH_SKILLS if len(s) > 2 and f" {s} " in blob)
        except Exception:
            n_skills = -1
    if len(desc) < 250:
        add("JD specificity", "Very short / missing description", 0.8, "Medium", "partial")
    elif n_skills == 0:
        add("JD specificity", "No concrete technologies named — generic JD", 0.6, "Medium")
    elif n_skills >= 4:
        add("JD specificity", f"{n_skills} concrete technologies named", -0.3, "Medium")

    # 5. Requirements realism (medium)
    years = [int(y) for y in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", low)]
    max_years = max(years, default=0)
    if re.search(r"\b(entry[- ]level|junior|graduate|new grad|intern)\b", f"{title} {low[:600]}") and max_years >= 5:
        add("Requirements realism", f"Entry-level role asking for {max_years}+ years", 0.9, "Medium")
    elif max_years >= 15:
        add("Requirements realism", f"Asks for {max_years}+ years — unrealistic", 0.5, "Medium")
    if GENERIC_TITLE.search(title):
        add("Requirements realism", "Buzzword title (rockstar / ninja)", 0.3, "Low")

    # 6. Third-party / aggregator vs. Verified First-Party ATS (medium)
    dom = _domain(url)
    ats_prov = detect_ats_provenance(job)
    if dom in AGGREGATOR_DOMAINS:
        add("Source", f"Re-posted by aggregator ({dom}) — find the original posting", 0.6, "Medium")
    if THIRD_PARTY_COMPANY.search(company) or any(re.search(p, low) for p in THIRD_PARTY_PATTERNS):
        add("Source", "Staffing agency / undisclosed client", 0.5, "Medium")
    if ats_prov["is_first_party"]:
        add("Source", f"Verified first-party ATS ({ats_prov['vendor']})", -0.4, "High")

    # 7. Scam signals & Posting Guard (high when matched)
    for pat, label in SCAM_PATTERNS:
        if re.search(pat, low):
            add("Scam signal", label, 2.0, "High")
    guard = sanitize_and_guard_posting(desc)
    if guard["has_injection"]:
        add("Posting guard", "Adversarial prompt-injection or hidden Unicode detected in JD", 1.2, "High")
    if guard["has_attention_check"]:
        chk = guard["attention_checks"][0]["snippet"]
        add("Attention check", f"Recruiter easter-egg test in JD: \"{chk}\"", -0.2, "High")

    # 8. Salary transparency (low)
    if job.get("salary") or _salary_numbers(desc):
        add("Salary transparency", "Pay range disclosed", -0.2, "Low")
    else:
        add("Salary transparency", "No pay range", 0.1, "Low", "unknown")

    # 9. Application deadline urgency / expiry (ported from rank_state.py)
    dl_info = extract_deadline(job)
    if dl_info["is_expired"]:
        add("Deadline", f"Application deadline passed ({dl_info['deadline']})", 2.5, "High")
    elif dl_info["is_urgent"]:
        add("Deadline", f"{dl_info['label']} — prioritize if applying", -0.2, "High")

    if risk >= 2.5:
        tier = "Suspicious"
    elif risk >= 1.0:
        tier = "Proceed with Caution"
    else:
        tier = "High Confidence"
    return {"tier": tier, "risk": round(risk, 2), "score": _clamp(4.6 - risk), "signals": signals,
            "ats_provenance": ats_prov, "deadline_info": dl_info, "posting_guard": {
                "has_injection": guard["has_injection"],
                "has_attention_check": guard["has_attention_check"],
                "attention_checks": guard["attention_checks"],
                "injections": guard["injections"],
            }}


# ── Block C: work authorization ────────────────────────────────────────────────
def assess_work_auth(job: dict) -> dict:
    desc = job.get("description") or ""
    blockers = []
    for pat, label in AUTH_BLOCKERS:
        m = re.search(pat, desc, re.I)
        if m and label not in [b["label"] for b in blockers]:
            snippet = desc[max(0, m.start() - 40): m.end() + 40].replace("\n", " ").strip()
            blockers.append({"label": label, "evidence": snippet})
    positives = [re.search(p, desc, re.I).group(0) for p in AUTH_POSITIVE if re.search(p, desc, re.I)]
    if blockers and not positives:
        score, status = 2.0, "supported"
    elif blockers and positives:
        score, status = 3.0, "partial"
    elif positives:
        score, status = 4.8, "supported"
    else:
        score, status = 3.6, "unknown"
    return {"score": score, "status": status, "blockers": blockers, "positives": positives}


# ── Block D: compensation ──────────────────────────────────────────────────────
def assess_comp(job: dict) -> dict:
    nums = []
    sal = str(job.get("salary") or "")
    nums += [int(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})+|\d{4,6}", sal)]
    nums += _salary_numbers(job.get("description") or "")
    nums = [n for n in nums if 1000 <= n <= 1_000_000]
    if not nums:
        return {"score": 3.0, "status": "unknown", "range": None,
                "note": "No pay range disclosed — research market rate before the interview."}
    lo, hi = min(nums), max(nums)
    annual = hi if hi > 20000 else hi * 12
    score = 4.5 if annual >= 120000 else 4.0 if annual >= 70000 else 3.5 if annual >= 35000 else 3.0
    return {"score": score, "status": "partial", "range": [lo, hi],
            "note": f"Disclosed range {lo:,}–{hi:,}. Base vs. total comp may not be separated."}


# ── Block B + E: CV match & customization plan ─────────────────────────────────
def assess_cv_match(job: dict, cv_text: str) -> dict:
    if not cv_text:
        return {"score": 3.0, "status": "unknown", "match_pct": None, "matched": [], "missing": [],
                "note": "Upload your CV to get a real match score."}
    from cv_matcher import compute_match
    pct, bd = compute_match(cv_text, job.get("description") or "", job.get("title") or "")
    score = _clamp(1 + pct / 25)  # 0→1, 50→3, 75→4, 100→5
    seniority_note = ""
    if bd.get("seniority_gap"):
        seniority_note = "Role seniority is above your CV level."
        score = _clamp(score - 0.4)
    if bd.get("exp_penalty"):
        seniority_note += f" Asks for {bd.get('job_exp_years')} yrs vs. {bd.get('cv_exp_years')} on your CV."
    required = set(bd.get("required_skills") or [])
    missing = bd.get("missing_tech") or []
    gaps = [{
        "skill": s,
        "importance": "hard requirement" if s in required else "nice to have",
        "mitigation": ("Hard blocker unless you have adjacent experience — mention the closest equivalent."
                       if s in required else "Mention any exposure (side project, course) in the cover letter."),
    } for s in missing[:8]]
    return {"score": score, "status": "supported", "match_pct": pct,
            "matched": bd.get("matched_tech", []), "missing": missing, "gaps": gaps,
            "seniority_note": seniority_note.strip(), "tips": bd.get("tips", [])[:5]}


def ats_keywords(job: dict, cv_text: str = "", limit: int = 12) -> List[dict]:
    """Top JD keywords ranked by frequency, flagged when absent from the CV (mirror them honestly)."""
    try:
        from cv_matcher import _extract_skills, _skill_freq_in_text, TECH_SKILLS
    except Exception:
        return []
    desc = f"{job.get('title', '')}\n{job.get('description', '')}"
    skills = _extract_skills(desc, TECH_SKILLS)
    cv_skills = _extract_skills(cv_text, TECH_SKILLS) if cv_text else set()
    ranked = sorted(skills, key=lambda s: (-_skill_freq_in_text(desc, s), s))[:limit]
    return [{"keyword": s, "in_cv": s in cv_skills, "mentions": _skill_freq_in_text(desc, s)} for s in ranked]


# ── Global ─────────────────────────────────────────────────────────────────────
def evaluate_job(job: dict, cv_text: str = "", sighting: Optional[dict] = None,
                 liveness: Optional[dict] = None) -> dict:
    title, desc = job.get("title") or "", job.get("description") or ""
    guard = sanitize_and_guard_posting(desc)
    if guard["cleaned_text"] != desc:
        job = {**job, "description": guard["cleaned_text"]}
        desc = guard["cleaned_text"]

    cv = assess_cv_match(job, cv_text)
    auth = assess_work_auth(job)
    comp = assess_comp(job)
    legit = assess_legitimacy(job, sighting, liveness)
    lang_gate = assess_language_gate(job, cv_text)

    weights = {"cv": 0.45, "legit": 0.25, "auth": 0.15, "comp": 0.15}
    global_score = (cv["score"] * weights["cv"] + legit["score"] * weights["legit"] +
                    auth["score"] * weights["auth"] + comp["score"] * weights["comp"])

    red_flags: List[str] = []
    hard_stop = False
    if legit["tier"] == "Suspicious":
        red_flags.append("Posting legitimacy is suspicious.")
        global_score = min(global_score, 2.5)
        hard_stop = True
    dl_info = legit.get("deadline_info") or extract_deadline(job)
    if dl_info.get("is_expired"):
        red_flags.append(f"Application deadline passed ({dl_info['deadline']}).")
        global_score = min(global_score, 1.5)
        hard_stop = True
    if liveness and liveness.get("result") == "expired":
        red_flags.append("The posting appears to be closed.")
        global_score = min(global_score, 1.5)
        hard_stop = True
    if auth["blockers"] and not auth["positives"]:
        red_flags.extend(b["label"] for b in auth["blockers"])
        global_score -= 0.3
    if lang_gate["missing_languages"]:
        red_flags.append(lang_gate["note"])
        if cv_text:
            global_score -= 0.6
    if guard["has_injection"]:
        red_flags.append("Prompt-injection / hidden Unicode instructions stripped from JD.")
    if cv.get("match_pct") is not None and cv["match_pct"] < 35:
        red_flags.append(f"Low CV match ({cv['match_pct']}%).")
    global_score = _clamp(global_score)

    if global_score >= 4.0 and not hard_stop:
        verdict, label = "apply", "Apply — strong fit"
    elif global_score >= 3.0 and not hard_stop:
        verdict, label = "consider", "Consider — apply only with a tailored pitch"
    else:
        verdict, label = "skip", "Do not apply — save your evening"

    confidence = "supported"
    statuses = [cv["status"], auth["status"], comp["status"]]
    if statuses.count("unknown") >= 2:
        confidence = "partial"
    if cv["status"] == "unknown" and legit["tier"] != "High Confidence":
        confidence = "unknown"

    seniority = "Unknown"
    try:
        from cv_matcher import _detect_seniority
        lvl = _detect_seniority(title)
        seniority = {0: "Intern", 1: "Junior", 2: "Mid-level", 3: "Senior", 4: "Lead / Staff", 5: "Head / Director"}.get(lvl, "Not stated")
    except Exception:
        pass
    loc = job.get("location") or ""
    remote = "Remote" if re.search(r"\bremote\b", f"{loc} {title} {desc[:1500]}", re.I) else (
        "Hybrid" if re.search(r"\bhybrid\b", f"{loc} {desc[:1500]}", re.I) else "On-site / unspecified")

    keywords = ats_keywords(job, cv_text)
    interview_focus = [f"Be ready to show production work with {k['keyword']}." for k in keywords[:3] if k["in_cv"]]
    interview_focus += [f"Prepare an honest answer on {k['keyword']} (in the JD, not on your CV)." for k in keywords if not k["in_cv"]][:2]
    if guard["has_attention_check"]:
        for chk in guard["attention_checks"][:2]:
            interview_focus.insert(0, f"🎯 Recruiter Attention Check: {chk['snippet']}")
    if dl_info.get("is_urgent"):
        interview_focus.insert(0, f"⏰ {dl_info['label']} — submit your application promptly.")

    return {
        "global_score": global_score,
        "verdict": verdict,
        "verdict_label": label,
        "confidence": confidence,
        "red_flags": red_flags,
        "deadline_info": dl_info,
        "role_summary": {"archetype": detect_archetype(title, desc), "seniority": seniority,
                         "work_mode": remote, "location": loc, "company": job.get("company") or "",
                         "ats_provenance": legit.get("ats_provenance"), "deadline_info": dl_info},
        "dimensions": {
            "cv_match": cv,
            "work_authorization": auth,
            "language_gate": lang_gate,
            "compensation": comp,
            "legitimacy": legit,
        },
        "posting_guard": {
            "has_injection": guard["has_injection"],
            "has_attention_check": guard["has_attention_check"],
            "attention_checks": guard["attention_checks"],
            "injections": guard["injections"],
        },
        "customization": {"keywords": keywords,
                          "summary": "Mirror the missing keywords only where you genuinely have the experience."},
        "interview_focus": interview_focus,
    }
