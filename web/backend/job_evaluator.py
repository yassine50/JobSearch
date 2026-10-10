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
from typing import Dict, List, Optional
from urllib.parse import urlparse

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

    # 6. Third-party / aggregator (medium)
    dom = _domain(url)
    if dom in AGGREGATOR_DOMAINS:
        add("Source", f"Re-posted by aggregator ({dom}) — find the original posting", 0.6, "Medium")
    if THIRD_PARTY_COMPANY.search(company) or any(re.search(p, low) for p in THIRD_PARTY_PATTERNS):
        add("Source", "Staffing agency / undisclosed client", 0.5, "Medium")
    if any(h in dom for h in ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "smartrecruiters.com")):
        add("Source", "Posted on the company's own ATS", -0.4, "Medium")

    # 7. Scam signals (high when matched)
    for pat, label in SCAM_PATTERNS:
        if re.search(pat, low):
            add("Scam signal", label, 2.0, "High")

    # 8. Salary transparency (low)
    if job.get("salary") or _salary_numbers(desc):
        add("Salary transparency", "Pay range disclosed", -0.2, "Low")
    else:
        add("Salary transparency", "No pay range", 0.1, "Low", "unknown")

    if risk >= 2.5:
        tier = "Suspicious"
    elif risk >= 1.0:
        tier = "Proceed with Caution"
    else:
        tier = "High Confidence"
    return {"tier": tier, "risk": round(risk, 2), "score": _clamp(4.6 - risk), "signals": signals}


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
    cv = assess_cv_match(job, cv_text)
    auth = assess_work_auth(job)
    comp = assess_comp(job)
    legit = assess_legitimacy(job, sighting, liveness)

    weights = {"cv": 0.45, "legit": 0.25, "auth": 0.15, "comp": 0.15}
    global_score = (cv["score"] * weights["cv"] + legit["score"] * weights["legit"] +
                    auth["score"] * weights["auth"] + comp["score"] * weights["comp"])

    red_flags: List[str] = []
    hard_stop = False
    if legit["tier"] == "Suspicious":
        red_flags.append("Posting legitimacy is suspicious.")
        global_score = min(global_score, 2.5)
        hard_stop = True
    if liveness and liveness.get("result") == "expired":
        red_flags.append("The posting appears to be closed.")
        global_score = min(global_score, 1.5)
        hard_stop = True
    if auth["blockers"] and not auth["positives"]:
        red_flags.extend(b["label"] for b in auth["blockers"])
        global_score -= 0.3
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

    return {
        "global_score": global_score,
        "verdict": verdict,
        "verdict_label": label,
        "confidence": confidence,
        "red_flags": red_flags,
        "role_summary": {"archetype": detect_archetype(title, desc), "seniority": seniority,
                         "work_mode": remote, "location": loc, "company": job.get("company") or ""},
        "dimensions": {
            "cv_match": cv,
            "work_authorization": auth,
            "compensation": comp,
            "legitimacy": legit,
        },
        "customization": {"keywords": keywords,
                          "summary": "Mirror the missing keywords only where you genuinely have the experience."},
        "interview_focus": interview_focus,
    }
