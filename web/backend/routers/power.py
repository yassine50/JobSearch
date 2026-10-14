import json
import re
import logging
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..utils import ensure_project_root_on_path
from .cv import _get_active_cv, _analyze_cv_text

ensure_project_root_on_path()
logger = logging.getLogger("jobsearcher.power")

router = APIRouter(prefix="/api/power", tags=["power"])

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

IGNORED_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "google.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com",
    "github.com", "medium.com", "wikipedia.org", "reddit.com", "wellfound.com",
    "monster.com", "stepstone.de", "welcometothejungle.com", "apec.fr",
    "hellowork.com", "pole-emploi.fr", "francetravail.fr", "bayt.com",
    "wuzzuf.net", "naukrigulf.com", "reed.co.uk", "totaljobs.com",
}


def _check_domain_mx(domain: str) -> bool:
    if not domain or "." not in domain:
        return False
    try:
        from ..linkedin_post_hunter import _has_mx_record
        return bool(_has_mx_record(domain))
    except Exception:
        try:
            import socket
            socket.gethostbyname(domain)
            return True
        except Exception:
            return False


def _clean_company_slug(company: str) -> str:
    cleaned = re.sub(
        r"\b(inc|llc|ltd|limited|corp|corporation|group|gmbh|sarl|sas|sa|plc|co|technologies|technology|solutions|labs|studio|global|international)\b",
        "",
        (company or "").lower(),
        flags=re.I,
    )
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    return cleaned


def _infer_company_domain(company: str, job_url: str = "") -> str:
    # 1. Check if job_url is already a direct corporate domain
    if job_url:
        try:
            parsed = urlparse(job_url)
            host = (parsed.netloc or "").lower().replace("www.", "")
            if host and not any(host == d or host.endswith("." + d) for d in IGNORED_DOMAINS):
                return host
        except Exception:
            pass

    # 2. Try DDGS lookup for official company website
    clean_co = (company or "").strip()
    if not clean_co or clean_co.lower() in ("unknown", "hiring team", "confidential", "linkedin"):
        return ""

    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(f'"{clean_co}" official website', max_results=5))
            for r in results:
                href = r.get("href", "")
                if not href:
                    continue
                host = urlparse(href).netloc.lower().replace("www.", "")
                if host and not any(host == d or host.endswith("." + d) for d in IGNORED_DOMAINS):
                    return host
    except Exception:
        pass

    # 3. Heuristic fallback: slug.com or slug.io
    slug = _clean_company_slug(clean_co)
    if slug and len(slug) >= 3:
        for tld in (".com", ".io", ".co", ".fr", ".de", ".ai"):
            candidate = f"{slug}{tld}"
            if _check_domain_mx(candidate):
                return candidate
    return ""


# ─── 1. Company Decision-Maker & HR Email Finder ─────────────────────────────

class FindContactsRequest(BaseModel):
    company: str
    role_title: str = ""
    location: str = ""
    job_url: str = ""
    description: str = ""


@router.post("/find-company-contacts")
def find_company_contacts(
    req: FindContactsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    company = (req.company or "").strip()
    if not company or company.lower() in ("unknown", "hiring team"):
        raise HTTPException(400, "Please provide a valid company name to discover contacts.")

    domain = _infer_company_domain(company, req.job_url)
    mx_valid = _check_domain_mx(domain) if domain else False

    decision_makers = []
    discovered_emails = set()

    # Extract any emails already in description
    if req.description:
        for em in EMAIL_REGEX.findall(req.description):
            discovered_emails.add(em.lower())

    # Search LinkedIn for HR / Talent Acquisition / Engineering Leads at this company
    try:
        from ddgs import DDGS
        queries = [
            f'site:linkedin.com/in/ "{company}" ("Recruiter" OR "Talent Acquisition" OR "HR" OR "Chargé de recrutement" OR "Hiring")',
            f'site:linkedin.com/in/ "{company}" ("CTO" OR "VP Engineering" OR "Engineering Manager" OR "Head of Talent")',
        ]
        if domain:
            queries.append(f'"@{domain}" ("recruiter" OR "careers" OR "hr" OR "jobs" OR "hiring")')

        seen_urls = set()
        with DDGS() as ddgs:
            for q in queries:
                try:
                    for r in ddgs.text(q, max_results=8):
                        href = r.get("href", "")
                        title = r.get("title", "")
                        body = r.get("body", "")

                        for em in EMAIL_REGEX.findall(f"{title} {body}"):
                            em_low = em.lower().rstrip(".,;)")
                            if not any(bad in em_low for bad in ("example.com", "sentry.io", "wixpress.com")):
                                discovered_emails.add(em_low)

                        if "linkedin.com/in/" in href and href not in seen_urls:
                            seen_urls.add(href)
                            parts = title.split(" - ")
                            name = parts[0].replace(" | LinkedIn", "").strip() if parts else "Hiring Contact"
                            headline = " - ".join(parts[1:]).replace(" | LinkedIn", "").strip() if len(parts) > 1 else f"Talent Acquisition at {company}"

                            # Infer personal corporate email if domain has valid MX
                            inferred_email = ""
                            name_tokens = [re.sub(r"[^a-z]", "", t.lower()) for t in name.split() if len(t) >= 2]
                            if domain and mx_valid and len(name_tokens) >= 2:
                                inferred_email = f"{name_tokens[0]}.{name_tokens[-1]}@{domain}"

                            decision_makers.append({
                                "name": name,
                                "headline": headline,
                                "linkedin_url": href,
                                "snippet": body[:200],
                                "inferred_email": inferred_email,
                                "mx_verified": mx_valid,
                            })
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"DDGS contact discovery warning: {e}")

    # Build verified / high-probability corporate email channels
    email_channels = []
    for em in sorted(discovered_emails):
        em_domain = em.split("@")[-1] if "@" in em else ""
        is_mx = _check_domain_mx(em_domain)
        email_channels.append({
            "email": em,
            "type": "Direct Extracted",
            "confidence": 96 if is_mx else 75,
            "mx_verified": is_mx,
        })

    if domain and mx_valid:
        standard_prefixes = [
            ("careers", "Official Careers Inbox", 88),
            ("hr", "HR & People Team", 85),
            ("talent", "Talent Acquisition Team", 84),
            ("jobs", "Recruiting Desk", 82),
        ]
        existing_set = {c["email"] for c in email_channels}
        for prefix, label, conf in standard_prefixes:
            candidate_em = f"{prefix}@{domain}"
            if candidate_em not in existing_set:
                email_channels.append({
                    "email": candidate_em,
                    "type": label,
                    "confidence": conf,
                    "mx_verified": True,
                })

    return {
        "company": company,
        "domain": domain,
        "mx_verified": mx_valid,
        "decision_makers": decision_makers[:8],
        "email_channels": email_channels[:8],
    }


# ─── 2. Saved Watchlists & Auto-Pilot Radar ──────────────────────────────────

class CreateWatchlistRequest(BaseModel):
    role: str
    locations: List[str] = ["Worldwide"]
    min_match_score: int = 65
    auto_pilot: bool = True


@router.get("/watchlists")
def get_watchlists(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.SavedWatchlist)
        .filter(models.SavedWatchlist.user_id == current_user.id)
        .order_by(models.SavedWatchlist.created_at.desc())
        .all()
    )
    out = []
    for r in rows:
        try:
            locs = json.loads(r.locations_json or '["Worldwide"]')
        except Exception:
            locs = ["Worldwide"]
        try:
            cached = json.loads(r.cached_results_json or "[]")
        except Exception:
            cached = []
        out.append({
            "id": r.id,
            "role": r.role,
            "locations": locs,
            "auto_pilot": bool(r.auto_pilot),
            "min_match_score": r.min_match_score or 65,
            "new_matches_count": r.new_matches_count or 0,
            "last_run_at": str(r.last_run_at) if r.last_run_at else None,
            "preview_posts": cached[:5],
        })
    return {"watchlists": out}


@router.post("/watchlists")
def create_watchlist(
    req: CreateWatchlistRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    role_clean = (req.role or "").strip()
    if not role_clean:
        raise HTTPException(400, "Role is required")

    wl = models.SavedWatchlist(
        user_id=current_user.id,
        role=role_clean,
        locations_json=json.dumps(req.locations or ["Worldwide"]),
        min_match_score=req.min_match_score,
        auto_pilot=req.auto_pilot,
        new_matches_count=0,
        cached_results_json="[]",
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)

    # Immediately run an initial quick scan against stored VerifiedRecruiterPosts
    _populate_watchlist_from_index(db, wl, current_user.id)

    return {
        "id": wl.id,
        "role": wl.role,
        "locations": req.locations or ["Worldwide"],
        "auto_pilot": bool(wl.auto_pilot),
        "min_match_score": wl.min_match_score,
        "new_matches_count": wl.new_matches_count,
        "last_run_at": str(wl.last_run_at) if wl.last_run_at else None,
    }


def _populate_watchlist_from_index(db: Session, wl: models.SavedWatchlist, user_id: int):
    role_tokens = [t.lower() for t in wl.role.split() if len(t) >= 2]
    all_posts = (
        db.query(models.VerifiedRecruiterPost)
        .order_by(models.VerifiedRecruiterPost.published_epoch.desc())
        .limit(150)
        .all()
    )
    active_cv = _get_active_cv(db, user_id)
    cv_text = active_cv.text_content if active_cv else ""

    matches = []
    for p in all_posts:
        haystack = f"{p.role_title} {p.role_key} {p.full_text}".lower()
        if role_tokens and not any(tok in haystack for tok in role_tokens):
            continue
        score = p.role_fit_score or 75
        if cv_text:
            try:
                from cv_matcher import compute_match
                s, _ = compute_match(cv_text, p.full_text or "", p.role_title or wl.role)
                score = max(score, s)
            except Exception:
                pass
        if score >= (wl.min_match_score or 60):
            try:
                emails = json.loads(p.recruiter_emails_json or "[]")
            except Exception:
                emails = []
            matches.append({
                "id": p.post_id,
                "role_title": p.role_title or wl.role,
                "company": p.company or "Hiring Team",
                "author_name": p.author_name or "Recruiter",
                "location": p.location or "Worldwide",
                "post_url": p.post_url,
                "score": score,
                "recruiter_emails": emails,
                "has_email": len(emails) > 0,
            })

    wl.new_matches_count = len(matches)
    wl.cached_results_json = json.dumps(matches[:15])
    wl.last_run_at = datetime.utcnow()
    db.commit()
    return matches


@router.post("/watchlists/{watchlist_id}/run")
def run_watchlist_now(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    wl = (
        db.query(models.SavedWatchlist)
        .filter(models.SavedWatchlist.id == watchlist_id, models.SavedWatchlist.user_id == current_user.id)
        .first()
    )
    if not wl:
        raise HTTPException(404, "Watchlist not found")

    matches = _populate_watchlist_from_index(db, wl, current_user.id)
    return {
        "id": wl.id,
        "role": wl.role,
        "new_matches_count": len(matches),
        "last_run_at": str(wl.last_run_at),
        "matches": matches[:15],
    }


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    wl = (
        db.query(models.SavedWatchlist)
        .filter(models.SavedWatchlist.id == watchlist_id, models.SavedWatchlist.user_id == current_user.id)
        .first()
    )
    if not wl:
        raise HTTPException(404, "Watchlist not found")
    db.delete(wl)
    db.commit()
    return {"message": "Watchlist deleted"}


# ─── 3. AI Interview Prep & Company Intelligence Studio ──────────────────────

class InterviewPrepRequest(BaseModel):
    application_id: Optional[int] = None
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    force_regenerate: bool = False


@router.post("/interview-prep")
def generate_interview_prep(
    req: InterviewPrepRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    app_row = None
    if req.application_id:
        app_row = (
            db.query(models.Application)
            .filter(models.Application.id == req.application_id, models.Application.user_id == current_user.id)
            .first()
        )
        if app_row and app_row.interview_prep_json and not req.force_regenerate:
            try:
                return json.loads(app_row.interview_prep_json)
            except Exception:
                pass

    title = (req.title or (app_row.title if app_row else "") or "Software Engineer").strip()
    company = (req.company or (app_row.company if app_row else "") or "the Hiring Company").strip()
    location = (req.location or (app_row.location if app_row else "") or "Remote / Hybrid").strip()
    description = (req.description or (app_row.notes if app_row else "") or title).strip()

    active_cv = _get_active_cv(db, current_user.id)
    cv_text = active_cv.text_content if active_cv else ""
    cv_analysis = _analyze_cv_text(cv_text) if cv_text else {}
    top_skills = cv_analysis.get("top_skills", []) or ["Software Architecture", "API Integration", "Testing", "CI/CD"]

    matched_skills = []
    missing_skills = []
    if cv_text:
        try:
            from cv_matcher import compute_match
            _, bd = compute_match(cv_text, description, title)
            matched_skills = bd.get("matched_tech", [])[:6]
            missing_skills = bd.get("missing_tech", [])[:4]
        except Exception:
            pass

    skills_focus = matched_skills or top_skills[:5]
    primary_skill = skills_focus[0] if skills_focus else title.split()[0]
    secondary_skill = skills_focus[1] if len(skills_focus) > 1 else "Scalable Architecture"

    kit = {
        "role_title": title,
        "company": company,
        "location": location,
        "generated_at": datetime.utcnow().isoformat(),
        "matched_skills": skills_focus,
        "gap_skills": missing_skills,
        "company_brief": {
            "summary": f"{company} is evaluating candidates for {title} ({location}) with a strong emphasis on production velocity, clean architecture, and cross-functional ownership.",
            "key_focus_areas": [
                f"Deep production mastery of {', '.join(skills_focus[:3])}",
                "End-to-end feature delivery from system design to automated testing & observability",
                f"Rapid ramp-up on {company}'s domain workflows and engineering standards",
            ],
            "elevator_pitch": (
                f"I'm a {title} with hands-on production experience across {', '.join(skills_focus[:4])}. "
                f"In my recent work, I've focused on building high-reliability, user-centric systems and optimizing performance, "
                f"which directly aligns with what {company} is building."
            ),
        },
        "technical_questions": [
            {
                "question": f"Walk us through how you architect a production {title} application using {primary_skill} for scale and maintainability.",
                "category": "System Architecture",
                "strategy": f"Highlight modular boundaries, state management / service separation, and how you prevented tight coupling in your {primary_skill} projects.",
            },
            {
                "question": f"What is the hardest performance bottleneck or concurrency bug you've diagnosed involving {primary_skill} or {secondary_skill}?",
                "category": "Debugging & Performance",
                "strategy": "Structure your answer around: 1) Profiling metrics used to isolate the root cause, 2) The exact fix implemented, and 3) Measurable latency/memory improvement.",
            },
            {
                "question": f"How do you handle API resilience, error recovery, and data consistency across distributed services or client states?",
                "category": "Reliability & APIs",
                "strategy": "Discuss idempotent retries, optimistic UI updates vs. strict consistency, structured error boundaries, and automated integration tests.",
            },
            {
                "question": (
                    f"We noticed {', '.join(missing_skills[:2])} in our stack—how would you approach ramping up on those technologies in your first 30 days?"
                    if missing_skills
                    else f"How do you ensure code quality and fast CI/CD delivery when collaborating with a fast-moving engineering team at {company}?"
                ),
                "category": "Stack Adaptation" if missing_skills else "Engineering Excellence",
                "strategy": (
                    f"Bridge from your strong foundation in {', '.join(skills_focus[:2])} to {', '.join(missing_skills[:2])} by emphasizing transferable architectural patterns."
                    if missing_skills
                    else "Emphasize PR review discipline, automated test coverage on critical paths, and feature flags for safe rollouts."
                ),
            },
            {
                "question": f"If you joined {company} as a {title} next week, how would you structure your first 30-60-90 days?",
                "category": "Execution & Ownership",
                "strategy": "Days 1-30: Ship high-signal bug fixes & map the architecture. Days 31-60: Own a core feature end-to-end. Days 61-90: Drive performance/DX improvements.",
            },
        ],
        "behavioral_star": [
            {
                "title": "Delivering Under Tight Deadlines",
                "situation": f"Critical product milestone requiring rapid delivery with {primary_skill}.",
                "task": "Ship a production-ready feature without compromising stability or technical debt.",
                "action": f"Scoped the MVP with stakeholders, modularized the {primary_skill} implementation, and automated regression checks.",
                "result": "Delivered on schedule with zero critical post-launch regressions and high user adoption.",
            },
            {
                "title": "Resolving Technical Disagreements",
                "situation": f"Architectural trade-off decision around {secondary_skill} and data flow.",
                "task": "Align the engineering team on a scalable, maintainable approach.",
                "action": "Built a lightweight benchmark prototype comparing both approaches on latency and developer velocity.",
                "result": "Team reached consensus quickly and reduced future maintenance overhead.",
            },
            {
                "title": "Proactive Reliability / Performance Win",
                "situation": "Noticed recurring friction or slow response times in a core user workflow.",
                "task": "Improve responsiveness and developer velocity.",
                "action": f"Profiled the bottleneck, refactored the {primary_skill} pipeline, and added caching/pagination.",
                "result": "Significantly improved load times and user retention metrics.",
            },
        ],
        "questions_to_ask": [
            f"What does a successful first 90 days look like for this {title} role at {company}?",
            f"What is the biggest technical or architectural challenge the {company} engineering team is tackling over the next two quarters?",
            "How are product and engineering priorities balanced between new feature velocity and platform reliability?",
            "What does the day-to-day collaboration between engineering, product, and design look like on this squad?",
        ],
        "salary_strategy": {
            "anchor_advice": f"Position your compensation expectations around the value of your production experience in {', '.join(skills_focus[:3])}. Always ask for the approved band for the {title} level first.",
            "script": (
                f"\"Based on my hands-on track record with {', '.join(skills_focus[:3])} and the scope of this {title} role at {company}, "
                f"I'm targeting a total compensation package aligned with market rates for this level—could you share the budgeted band for this position?\""
            ),
        },
    }

    if app_row:
        app_row.interview_prep_json = json.dumps(kit)
        db.commit()

    return kit
