
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, timedelta, date
import os
import sys
import re
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger("jobsearcher.jobs")

def _compute_job_age_hours(date_val: Any) -> Optional[float]:
    if not date_val:
        return None
    now = datetime.utcnow()
    # Check date or datetime object
    if isinstance(date_val, datetime):
        diff = (now - date_val).total_seconds() / 3600.0
        return max(0.0, round(diff, 1))
    elif isinstance(date_val, (date,)):
        dt = datetime.combine(date_val, datetime.min.time())
        diff = (now - dt).total_seconds() / 3600.0
        return max(0.0, round(diff, 1))
    
    val_str = str(date_val).strip()
    if not val_str or val_str.lower() in ("none", "nan", "nat", ""):
        return None

    # Check ISO / YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", val_str)
    if m:
        try:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d = datetime(year, month, day)
            diff = (now - d).total_seconds() / 3600.0
            return max(0.0, round(diff, 1))
        except Exception:
            pass

    # Check relative text
    low = val_str.lower()
    if any(w in low for w in ["just now", "moment", "second", "minute", "min ago", "mins ago",
                               "less than an hour", "moments ago", "few seconds"]):
        return 0.5
    # Handle "an hour ago" / "about an hour" → 1h
    if re.search(r"\ban?\s+hour\b", low):
        return 1.0
    m_h = re.search(r"(\d+)\s*(?:hour|hr|h)\b", low)
    if m_h:
        return float(m_h.group(1))
    if "yesterday" in low or re.search(r"\b1\s*day\s*ago\b|\b1d\s*ago\b", low):
        return 24.0
    # Handle "a day ago" → 24h
    if re.search(r"\ba\s+day\s+ago\b", low):
        return 24.0
    m_d = re.search(r"(\d+)\s*(?:day|d)\b", low)
    if m_d:
        return float(m_d.group(1)) * 24.0
    # Handle "a week ago" → 168h
    if re.search(r"\ba\s+week\s+ago\b", low):
        return 168.0
    m_w = re.search(r"(\d+)\s*(?:week|wk|w)\b", low)
    if m_w:
        return float(m_w.group(1)) * 168.0
    # Handle "a month ago" → 720h
    if re.search(r"\ba\s+month\s+ago\b", low):
        return 720.0
    m_m = re.search(r"(\d+)\s*(?:month|mo|m)\b", low)
    if m_m:
        return float(m_m.group(1)) * 720.0

    return None

def _format_age_str(age_hours: Optional[float]) -> str:
    if age_hours is None:
        return ""
    if age_hours < 1:
        return "Just now"
    if age_hours < 24:
        return f"{int(age_hours)}h ago"
    days = int(age_hours // 24)
    if days == 1:
        return "1d ago"
    if days < 7:
        return f"{days}d ago"
    weeks = int(days // 7)
    if weeks < 4:
        return f"{weeks}w ago"
    months = int(days // 30)
    return f"{months}mo ago"
from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

def _extract_job_id(url: str) -> Optional[str]:
    if not url: return None
    m = (
        re.search(r"currentJobId=(\d+)", url) or
        re.search(r"/view/[^/?#]*-?(\d{7,12})", url) or
        re.search(r"-(\d{7,12})(?:[/?#]|$)", url) or
        re.search(r"/jobs/view/(\d+)", url) or
        re.search(r"(\d{8,11})", url)
    )
    return m.group(1) if m else None

def _clean_job_url(url: str) -> str:
    """Canonical key for a posting URL. Must keep id-carrying query params
    (Indeed ?jk=, LinkedIn currentJobId, Greenhouse gh_jid) — stripping the whole
    query collapsed every Indeed job to 'indeed.com/viewjob' and one applied
    Indeed job then hid all Indeed results."""
    if not url: return ""
    from ..search_engine import canonical_url
    m = re.search(r"[?&]gh_jid=(\d+)", url)
    if m:
        return f"greenhouse:{m.group(1)}"
    return canonical_url(url)

def _norm_company(c: str) -> str:
    if not c: return ""
    s = c.lower().strip()
    s = re.sub(r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|technologies|solutions|group|labs|holdings|company|co)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)

def _norm_title(t: str) -> str:
    if not t: return ""
    return re.sub(r"[^a-z0-9]", "", t.lower().strip())

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,10}",
    re.IGNORECASE
)
SKIP_PATTERNS = {"example","sentry","wixpress","amazonaws","cloudfront","noreply",
                 "no-reply","placeholder","test@","sample","youremail","@email.com",
                 "@domain.com","privacy@","legal@","support@sentry", "jnahar@dashkar.com",
                 "laura.peters@fartherforward.com", "fartherforward.com"}
SKIP_EXTS = {".png",".jpg",".jpeg",".gif",".svg",".webp",".css",".js"}

def _clean_email(e: str) -> Optional[str]:
    if not e: return None
    clean = e.strip().lower()
    if any(s in clean for s in SKIP_PATTERNS): return None
    if any(clean.endswith(x) for x in SKIP_EXTS): return None
    try:
        from recruiter_hunter import is_email_blacklisted
        if is_email_blacklisted(clean):
            return None
    except Exception:
        pass
    parts = clean.split("@")
    if len(parts) != 2: return None
    loc, dom = parts
    if len(loc) < 2 or len(dom) < 4 or "." not in dom: return None
    return clean

def _extract_emails_from_text(text: str) -> List[str]:
    if not text: return []
    seen, clean = set(), []
    for e in EMAIL_RE.findall(text):
        c = _clean_email(e)
        if c and c not in seen:
            seen.add(c)
            clean.append(c)
    return clean[:5]

def _extract_row_emails(row: Any, desc: str = "") -> List[dict]:
    """Extract and validate initial recruiter emails from raw scrape row and job description."""
    initial_emails: List[dict] = []
    seen: set = set()

    def _add(clean_em: str, source: str, score: int):
        clean_em = clean_em.strip().lower()
        if (clean_em and "@" in clean_em and 
            clean_em not in seen and 
            not any(clean_em.endswith(x) for x in SKIP_EXTS) and
            not any(s in clean_em for s in SKIP_PATTERNS)):
            seen.add(clean_em)
            initial_emails.append({
                "email": clean_em,
                "source": source,
                "score": score,
                "verified": True,
                "is_hr": True
            })

    site_str = str(row.get("site", "") if hasattr(row, "get") else "").lower()
    is_jb = "job_bank" in site_str
    default_source = "job_bank" if is_jb else "found"
    default_score = 200 if is_jb else 180

    raw_val = row.get("emails") if hasattr(row, "get") else None
    if isinstance(raw_val, (list, tuple, set)):
        for em in raw_val:
            cleaned = re.sub(r"[\[\]'\"\s]", "", str(em))
            _add(cleaned, default_source, default_score)
    elif raw_val and str(raw_val).lower() not in ("none", "nan", ""):
        for em in str(raw_val).replace(";", ",").split(","):
            cleaned = re.sub(r"[\[\]'\"\s]", "", em)
            _add(cleaned, default_source, default_score)

    if desc:
        for em in EMAIL_RE.findall(desc):
            _add(em, "found", 180)

    return initial_emails

def _fetch_linkedin_description(url_or_id: str) -> str:
    """Fetches full job description via LinkedIn public guest API."""
    job_id = None
    url_or_id = str(url_or_id or "").strip()
    if url_or_id.isdigit():
        job_id = url_or_id
    else:
        m = (
            re.search(r"currentJobId=(\d+)", url_or_id) or
            re.search(r"/view/[^/?#]*-?(\d{8,12})", url_or_id) or
            re.search(r"-(\d{8,12})(?:[/?#]|$)", url_or_id) or
            re.search(r"/jobs/view/(\d+)", url_or_id) or
            re.search(r"(\d{9,11})", url_or_id)
        )
        if m:
            job_id = m.group(1)

    if not job_id:
        return ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        import requests as req_lib
        from bs4 import BeautifulSoup
        g_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        resp = req_lib.get(g_url, headers=headers, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            div = soup.find("div", class_=lambda x: x and "show-more-less-html__markup" in x)
            if div:
                return div.get_text(separator="\n").strip()
    except Exception:
        pass
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "scraper_config.json")

def _get_scraper_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_scraper_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save scraper config: {e}")


# ── Platform admin (only admins can see / change the server-side API keys) ─────
def is_admin(user) -> bool:
    admins = os.getenv("ADMIN_EMAILS", "yassineyoussefwx@gmail.com")
    return bool(user) and (user.email or "").strip().lower() in {
        e.strip().lower() for e in admins.split(",") if e.strip()}


# ── Shared search cache: identical searches within 6h reuse the scraped results ─
import threading as _threading
SEARCH_CACHE_TTL_S = int(os.getenv("SEARCH_CACHE_TTL_S", str(6 * 3600)))
_search_cache: dict = {}
_search_cache_lock = _threading.Lock()


def _search_cache_key(req, countries, sites, hours) -> str:
    return json.dumps({
        "t": (req.title or "").strip().lower(), "l": (req.location or "").strip().lower(),
        "c": sorted(c.lower() for c in countries), "s": sorted(sites), "h": hours,
        "r": bool(req.is_remote), "e": bool(req.easy_apply), "i": bool(req.international_only),
        "n": req.results_wanted,
    }, sort_keys=True)


def _search_cache_get(key: str):
    import time as _t
    with _search_cache_lock:
        hit = _search_cache.get(key)
        if hit and _t.time() - hit[0] < SEARCH_CACHE_TTL_S:
            return hit[1], hit[2]
        _search_cache.pop(key, None)
    return None


def _search_cache_put(key: str, df, per_site: dict):
    import time as _t
    with _search_cache_lock:
        if len(_search_cache) > 200:  # keep memory bounded
            for k in sorted(_search_cache, key=lambda k: _search_cache[k][0])[:50]:
                _search_cache.pop(k, None)
        _search_cache[key] = (_t.time(), df.copy(), dict(per_site))


# ── Per-user daily quota on fresh scrapes (cache hits are free) ────────────────
SEARCH_DAILY_LIMIT = int(os.getenv("SEARCH_DAILY_LIMIT", "40"))
_search_quota: dict = {}


def _check_and_count_search_quota(user):
    from datetime import date as _date
    if is_admin(user) or SEARCH_DAILY_LIMIT <= 0:
        return
    key = (user.id, _date.today().isoformat())
    with _search_cache_lock:
        used = _search_quota.get(key, 0)
        if used >= SEARCH_DAILY_LIMIT:
            raise HTTPException(429, f"Daily search limit reached ({SEARCH_DAILY_LIMIT} new searches/day). "
                                     "Repeating a recent search is still free — try again tomorrow for new ones.")
        _search_quota[key] = used + 1

def _fetch_serper_google_jobs(query: str, location: str = "", country: str = "us", results_wanted: int = 15, api_key: str = "") -> List[dict]:
    """Fetches structured Google Search Jobs using Serper API when key is configured."""
    if not api_key:
        return []
    try:
        import requests as req_lib
        from urllib.parse import urlparse
        url = "https://google.serper.dev/search"
        loc_str = location if location and location.lower() != "worldwide" else ""
        q_str = f"{query} jobs in {loc_str}" if loc_str else f"{query} jobs"
        gl_map = {
            "usa": "us", "united states": "us", "canada": "ca", "france": "fr",
            "germany": "de", "uk": "uk", "united kingdom": "uk", "netherlands": "nl",
            "morocco": "ma", "united arab emirates": "ae", "uae": "ae", "singapore": "sg"
        }
        gl = gl_map.get(str(country).lower().strip(), "us")
        payload = {"q": q_str, "gl": gl, "hl": "en", "num": max(10, min(results_wanted, 30))}
        resp = req_lib.post(url, json=payload, headers={"X-API-KEY": api_key, "Content-Type": "application/json"}, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            jobs = []
            for item in data.get("organic", [])[:results_wanted]:
                raw_title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                if not link or not raw_title:
                    continue
                # Clean title
                title = raw_title.split("|")[0].split(" - ")[0].split(" – ")[0].strip()
                title = re.sub(r"^(?:Now Hiring:\s*\d*\s*|Apply for\s*|\$\d+k-\$\d+k\s*)", "", title, flags=re.I).strip()
                # Parse company
                parsed = urlparse(link)
                netloc = parsed.netloc.replace("www.", "")
                domain_name = netloc.split(".")[0].capitalize()
                company = domain_name
                m_co = re.search(r"(?:at|by|with)\s+([A-Z][A-Za-z0-9\s&]{2,25})(?:\s*[\.\,\-–|]|\s+in\s+|\s*$)", raw_title)
                if m_co:
                    company = m_co.group(1).strip()
                jobs.append({
                    "title": title or query.title(),
                    "company": company,
                    "location": loc_str or "United States",
                    "description": snippet,
                    "job_url": link,
                    "job_url_direct": link,
                    "date_posted": "Recently",
                    "salary": "",
                    "site": "google"
                })
            return jobs
    except Exception as e:
        logger.warning(f"[SerperGoogleJobs] Error: {e}")
    return []

def _fetch_jobbank_details(job_id_or_url: str) -> dict:
    """Fetch complete Job Bank Canada posting details, instructions, screening questions,
    and especially the recruiter's email hiding behind 'Additional ways to apply'."""
    m = re.search(r"(\d{7,10})", str(job_id_or_url or ""))
    job_id = m.group(1) if m else None
    if not job_id:
        return {}

    det_url = f"https://www.jobbank.gc.ca/jobsearch/jobposting/{job_id}"
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers = {
        "User-Agent": ua,
        "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    title = ""
    company = ""
    location = ""
    salary = ""
    desc_parts = []
    is_intl = False

    # 1. Fetch static detail page
    try:
        import requests as req_lib
        from bs4 import BeautifulSoup
        r_get = req_lib.get(det_url, headers=headers, timeout=12)
        if r_get.status_code == 200:
            soup = BeautifulSoup(r_get.text, "html.parser")
            t_elem = soup.find("span", property="title") or soup.find("h1")
            if t_elem:
                title = t_elem.get_text(strip=True)

            c_elem = soup.find("span", property="hiringOrganization") or soup.find("li", class_="business")
            if c_elem:
                company = c_elem.get_text(strip=True)

            l_elem = soup.find("span", property="jobLocation") or soup.find("li", class_="location")
            if l_elem:
                location = l_elem.get_text(strip=True)

            s_elem = soup.find("li", class_="salary")
            if s_elem:
                salary = s_elem.get_text(strip=True).replace("Salary", "").strip()

            req_div = soup.find("div", class_="job-posting-detail-requirements")
            if req_div:
                desc_parts.append(req_div.get_text(separator="\n", strip=True))
            else:
                main_sec = soup.find("section", id="job-posting-detail") or soup.find("main")
                if main_sec:
                    desc_parts.append(main_sec.get_text(separator="\n", strip=True)[:3500])

            page_text = soup.get_text()
            if "other candidates with or without" in page_text.lower() or "without a valid canadian work permit" in page_text.lower():
                is_intl = True
    except Exception as e_get:
        logger.warning(f"[JobBank] Detail page fetch warning for {job_id}: {e_get}")

    # 2. JSF AJAX POST for 'How to Apply' (Recruiter Email behind 'Additional ways to apply')
    payload = {
        "jakarta.faces.partial.ajax": "true",
        "jakarta.faces.source": "applynowbutton",
        "jakarta.faces.partial.execute": "jobid",
        "jakarta.faces.partial.render": "applynow markappliedgroup",
        "jakarta.faces.behavior.event": "action",
        "action": "applynowbutton",
        "seekeractivity:jobid": job_id,
        "seekeractivity_SUBMIT": "1",
        "jakarta.faces.ViewState": "stateless",
        "seekeractivity": "seekeractivity",
    }
    post_headers = {
        "User-Agent": ua,
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": det_url,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/xml, text/xml, */*; q=0.01",
    }

    emails: List[str] = []
    ext_apply_url = None
    hta_text = ""

    try:
        import requests as req_lib
        from bs4 import BeautifulSoup
        r_post = req_lib.post(det_url, data=payload, headers=post_headers, timeout=12)
        if r_post.status_code == 200:
            cdata = re.search(r"<!\[CDATA\[(.*?)\]\]>", r_post.text, re.DOTALL)
            content = cdata.group(1) if cdata else r_post.text
            hta_soup = BeautifulSoup(content, "html.parser")

            # mailto links
            for a in hta_soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("mailto:"):
                    em = href.replace("mailto:", "").split("?")[0].strip().lower()
                    if "@" in em and em not in emails:
                        emails.append(em)
                elif href.startswith("http") and "jobbank.gc.ca" not in href:
                    if not ext_apply_url:
                        ext_apply_url = href

            # Regex search for recruiter emails inside the Additional ways to apply block
            for em in EMAIL_RE.findall(content):
                em_clean = em.lower().strip()
                if em_clean not in emails and not any(em_clean.endswith(ext) for ext in [".png", ".jpg", ".css", ".js"]):
                    emails.append(em_clean)

            # Details / How to apply block
            det_tag = hta_soup.find("details") or hta_soup.find("div", id="howtoapply")
            if det_tag:
                hta_text = det_tag.get_text(separator="\n", strip=True)
                desc_parts.append(f"\n### How to Apply & Recruiter Instructions\n{hta_text}")
    except Exception as e_post:
        logger.warning(f"[JobBank] HTA AJAX POST warning for {job_id}: {e_post}")

    full_desc = "\n\n".join(desc_parts)
    if is_intl:
        full_desc = (
            "### 🌐 International Candidate Eligibility\n"
            "✅ **This employer accepts applications from Canadian citizens, permanent residents, "
            "and international candidates (with or without a valid Canadian work permit / LMIA-eligible).**\n\n"
            + full_desc
        )

    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "url": det_url,
        "emails": emails,
        "description": full_desc,
        "job_url_direct": ext_apply_url,
        "easy_apply": bool(emails or "direct apply" in hta_text.lower()),
        "is_direct_apply": bool("direct apply" in hta_text.lower()),
        "is_international_eligible": is_intl,
    }

def _enrich_job_description(job: dict) -> dict:
    url = job.get("url") or ""
    site = (job.get("site") or "").lower()

    # Dedicated enrichment for Job Bank Canada postings
    if "jobbank.gc.ca" in url or "job_bank" in site:
        existing_emails = job.get("emails") or []
        valid_emails = [
            re.sub(r"[\[\]'\"\s]", "", (e.get("email") if isinstance(e, dict) else str(e))).lower()
            for e in existing_emails
        ]
        valid_emails = [e for e in valid_emails if "@" in e]
        current_desc = job.get("description") or ""
        # The Job Bank scraper already ran the 'How to apply' AJAX call, so only re-fetch
        # when the description is genuinely missing (avoids doubling requests per listing).
        if len(current_desc.strip()) < 150:
            jb_res = _fetch_jobbank_details(url)
            if jb_res.get("description") and len(jb_res["description"]) > len(current_desc):
                job["description"] = jb_res["description"]
            if jb_res.get("emails"):
                existing_set = {
                    (e.get("email") if isinstance(e, dict) else str(e)).lower()
                    for e in job.get("emails", [])
                }
                for ne in jb_res["emails"]:
                    clean_ne = ne.strip().lower()
                    if clean_ne and clean_ne not in existing_set:
                        existing_set.add(clean_ne)
                        job.setdefault("emails", []).append({
                            "email": clean_ne,
                            "source": "job_bank",
                            "score": 200,
                            "verified": True,
                            "is_hr": True
                        })
            if jb_res.get("easy_apply"):
                job["easy_apply"] = True
            if jb_res.get("is_direct_apply"):
                job["is_direct_apply"] = True
            if jb_res.get("job_url_direct"):
                job["job_url_direct"] = jb_res["job_url_direct"]
        return job

    current_desc = job.get("description") or ""

    # Always mine any email addresses from the job description immediately
    if current_desc:
        new_emails = _extract_emails_from_text(current_desc)
        if new_emails:
            existing = {
                (e.get("email") if isinstance(e, dict) else str(e)).lower()
                for e in (job.get("emails") or [])
            }
            for ne in new_emails:
                clean_ne = ne.strip().lower()
                if clean_ne and clean_ne not in existing:
                    existing.add(clean_ne)
                    job.setdefault("emails", []).append({"email": clean_ne, "source": "found"})

    if len(current_desc.strip()) > 80:
        return job

    if "linkedin" in site or "linkedin.com" in url:
        desc = _fetch_linkedin_description(url)
        if desc:
            job["description"] = desc
            new_emails = _extract_emails_from_text(desc)
            if new_emails:
                existing = {
                    (e.get("email") if isinstance(e, dict) else str(e)).lower()
                    for e in (job.get("emails") or [])
                }
                for ne in new_emails:
                    clean_ne = ne.strip().lower()
                    if clean_ne and clean_ne not in existing:
                        existing.add(clean_ne)
                        job.setdefault("emails", []).append({"email": clean_ne, "source": "found"})
    return job

class SearchRequest(BaseModel):
    title: str
    location: str = ""
    country: str = "Worldwide"
    countries: List[str] = []          # multi-country support
    sites: List[str] = ["linkedin", "indeed"]
    results_wanted: int = 30
    hours_old: Optional[int] = None    # None/0 means all-time
    is_remote: bool = False
    easy_apply: Optional[bool] = None
    international_only: Optional[bool] = False

class ImportUrlRequest(BaseModel):
    url: str

class JobDescriptionRequest(BaseModel):
    url: str
    job_id: Optional[str] = None
    title: Optional[str] = ""

class SaveJobRequest(BaseModel):
    title: str; company: str=""; location: str=""
    url: str=""; description: str=""; match_score: int=0

class MarkAppliedRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    match_score: int = 0
    notes: str = ""

class EasyApplyRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    job_url_direct: Optional[str] = ""
    description: Optional[str] = ""
    site: Optional[str] = "linkedin"
    match_score: Optional[int] = 0
    notes: Optional[str] = ""
    customize_cv: Optional[bool] = True

class BatchEasyApplyJobsRequest(BaseModel):
    jobs: List[EasyApplyRequest]
    customize_cv: Optional[bool] = True

class ScraperConfigModel(BaseModel):
    serper_api_key: Optional[str] = None
    scraper_proxy: Optional[str] = None
    adzuna_app_id: Optional[str] = None
    adzuna_app_key: Optional[str] = None
    jooble_api_key: Optional[str] = None
    careerjet_affid: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

@router.get("/scraper-config")
def get_scraper_config_route(current_user: models.User = Depends(get_current_user)):
    from ..official_apis import configured_providers, get_key, KEY_NAMES
    cfg = _get_scraper_config()
    serper = cfg.get("serper_api_key") or os.getenv("SERPER_API_KEY", "")
    proxy = cfg.get("scraper_proxy") or os.getenv("SCRAPER_PROXY") or os.getenv("GLASSDOOR_PROXY", "")
    public = {
        "is_admin": is_admin(current_user),
        "has_serper": bool(serper.strip()),
        "has_proxy": bool(proxy.strip()),
        "official_providers": configured_providers(),
        "daily_search_limit": SEARCH_DAILY_LIMIT,
    }
    if not public["is_admin"]:
        return public  # never expose server keys to regular users
    return {**public, "serper_api_key": serper, "scraper_proxy": proxy,
            **{k: get_key(k) for k in KEY_NAMES}}

@router.post("/scraper-config")
def save_scraper_config_route(data: ScraperConfigModel, current_user: models.User = Depends(get_current_user)):
    if not is_admin(current_user):
        raise HTTPException(403, "Only the platform admin can change API keys.")
    cfg = _get_scraper_config()
    for field, value in data.dict().items():
        if value is not None:
            cfg[field] = value.strip()
    _save_scraper_config(cfg)
    from ..official_apis import configured_providers
    return {"message": "Scraper configuration updated successfully", "has_serper": bool(cfg.get("serper_api_key")),
            "has_proxy": bool(cfg.get("scraper_proxy")), "official_providers": configured_providers()}

COUNTRY_NORM = {
    "uae": ("united arab emirates", "United Arab Emirates"),
    "united arab emirates": ("united arab emirates", "United Arab Emirates"),
    "dubai": ("united arab emirates", "Dubai, United Arab Emirates"),
    "abu dhabi": ("united arab emirates", "Abu Dhabi, United Arab Emirates"),
    "usa": ("usa", "United States"),
    "us": ("usa", "United States"),
    "united states": ("usa", "United States"),
    "uk": ("uk", "United Kingdom"),
    "gb": ("uk", "United Kingdom"),
    "united kingdom": ("uk", "United Kingdom"),
    "canada": ("canada", "Canada"),
    "ca": ("canada", "Canada"),
    "germany": ("germany", "Germany"),
    "de": ("germany", "Germany"),
    "france": ("france", "France"),
    "fr": ("france", "France"),
    "netherlands": ("netherlands", "Netherlands"),
    "nl": ("netherlands", "Netherlands"),
    "morocco": ("morocco", "Morocco"),
    "ma": ("morocco", "Morocco"),
    "singapore": ("singapore", "Singapore"),
    "sg": ("singapore", "Singapore"),
    "saudi arabia": ("saudi arabia", "Saudi Arabia"),
    "sa": ("saudi arabia", "Saudi Arabia"),
    "qatar": ("qatar", "Qatar"),
    "egypt": ("egypt", "Egypt"),
    "india": ("india", "India"),
    "australia": ("australia", "Australia"),
    "worldwide": ("usa", "Worldwide"),
    "global": ("usa", "Worldwide"),
}

@router.post("/search")
def search_jobs(req: SearchRequest,
                db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from jobspy import scrape_jobs
    import pandas as pd

    # Filter to supported jobspy sites - enable multi-board scraping
    # remote_boards / ats / hackernews are zero-auth open sources (see open_sources.py)
    SUPPORTED = {"linkedin", "indeed", "job_bank", "glassdoor", "google", "remote_boards", "ats", "hackernews", "official_apis"}
    valid_sites = [s for s in req.sites if s in SUPPORTED] or ["linkedin", "indeed", "job_bank"]
    if req.international_only and "job_bank" not in valid_sites:
        valid_sites.append("job_bank")

    # Determine countries — use multi list or fall back to single
    countries_to_search = [c.strip() for c in req.countries if c.strip()] if req.countries else [req.country or "Worldwide"]
    if not countries_to_search:
        countries_to_search = ["Worldwide"]
    if req.international_only and not any(c.lower() in ("canada", "worldwide", "global") for c in countries_to_search):
        countries_to_search.append("Canada")

    hours_filter = req.hours_old if (req.hours_old and req.hours_old > 0) else None

    # High-yield scrape buffer: request generous count to guarantee high results even after 24h & applied filters
    # For 24h filter, LinkedIn often returns old jobs → use higher multiplier + prefer other boards
    fetch_multiplier = 5 if hours_filter and hours_filter <= 24 else (3 if hours_filter else 2)
    per_country = max((req.results_wanted * fetch_multiplier) // max(len(countries_to_search), 1), min(max(req.results_wanted * 2, 15), 45))

    # For strict 24h searches: remove LinkedIn (it ignores f_TPR for public unauthenticated requests)
    # Indeed and Job Bank actually honor the hours_old parameter reliably
    effective_sites = list(valid_sites)
    if hours_filter and hours_filter <= 24:
        effective_sites = [s for s in effective_sites if s != "linkedin"]
        if not effective_sites:
            effective_sites = ["indeed", "job_bank"]
        # Ensure indeed and job_bank are included for 24h
        for must_have in ["indeed", "job_bank"]:
            if must_have not in effective_sites and must_have in SUPPORTED:
                effective_sites.append(must_have)

    from ..search_engine import (
        expand_queries, best_relevance, is_spam, dedup_and_merge, quality_score,
    )
    from ..open_sources import fetch_open_source, OPEN_SITE_IDS
    from ..official_apis import configured_providers as _official_providers
    _official_active = bool(_official_providers())
    from ..sightings import record_and_annotate
    import time as _time
    from concurrent.futures import wait as _wait, FIRST_COMPLETED

    t_start = _time.time()
    SCRAPE_BUDGET_S = 30      # hard wall-clock budget for the whole scraping fan-out
    # How many phrasings of the role each board is queried with
    SITE_VARIANT_LIMIT = {"indeed": 3, "linkedin": 2, "job_bank": 2, "glassdoor": 2, "google": 2}
    stats = {"tasks": 0, "tasks_ok": 0, "tasks_failed": 0, "tasks_timed_out": 0,
             "raw": 0, "after_dedup": 0, "after_relevance": 0, "spam_removed": 0,
             "per_site": {}, "queries": {}, "timings": {}}

    def _country_ctx(country_name: str):
        norm_key = country_name.strip().lower()
        if norm_key in ("worldwide", "global", "all", ""):
            indeed_c = "usa"
            loc = req.location.strip() if req.location.strip() else ("Remote" if req.is_remote else "Worldwide")
        else:
            indeed_c, linkedin_loc = COUNTRY_NORM.get(norm_key, (norm_key, country_name.strip()))
            loc = req.location.strip() if req.location.strip() else linkedin_loc
        sites = [
            s for s in effective_sites
            if s != "job_bank" or norm_key in ("canada", "ca", "worldwide", "global", "all", "") or req.international_only
        ] or list(effective_sites)
        return norm_key, indeed_c, loc, sites

    # Build the fan-out task list
    tasks = []
    all_queries: List[str] = [req.title.strip()]
    for country_name in countries_to_search:
        norm_key, indeed_c, loc, sites = _country_ctx(country_name)
        variants = expand_queries(req.title.strip(), norm_key, max_variants=3) or [req.title.strip()]
        stats["queries"][country_name] = variants
        for q in variants:
            if q not in all_queries:
                all_queries.append(q)
        for site in sites:
            if site == "official_apis" and not _official_active:
                continue
            if site in OPEN_SITE_IDS:
                # Feeds/ATS are fetched once and filtered locally with every variant.
                tasks.append((country_name, norm_key, site, variants, per_country, indeed_c, loc))
                continue
            for vi, q in enumerate(variants[: SITE_VARIANT_LIMIT.get(site, 2)]):
                want = per_country if vi == 0 else max(10, per_country // 2)
                tasks.append((country_name, norm_key, site, q, want, indeed_c, loc))
    stats["tasks"] = len(tasks)
    stats["sites_searched"] = sorted({t[2] for t in tasks})
    stats["countries_searched"] = list(countries_to_search)

    def scrape_task(task):
        country_name, norm_key, site, q, want, indeed_c, loc = task
        search_country = "Worldwide" if norm_key in ("worldwide", "global", "all", "") else country_name

        # Zero-auth open sources: remote boards, company ATS (Greenhouse/Lever/Ashby), HN hiring
        if site in OPEN_SITE_IDS:
            rows = fetch_open_source(
                site, list(q), country=search_country, location=req.location.strip(),
                hours_old=hours_filter,
                serper_key=os.getenv("SERPER_API_KEY", "") or _get_scraper_config().get("serper_api_key", ""),
            )
            if not rows:
                return None
            df_o = pd.DataFrame(rows)
            df_o["_search_country"] = search_country
            df_o["_query"] = q[0]
            return df_o

        # Indeed cannot search for literal 'Worldwide' or 'Global' as a city name
        site_loc = loc
        if site == "indeed" and str(loc).strip().lower() in ("worldwide", "global", "all"):
            site_loc = "Remote" if req.is_remote else ""

        # High-precision Google Jobs integration via Serper API if key is set
        if site == "google":
            serper_key = os.getenv("SERPER_API_KEY", "") or _get_scraper_config().get("serper_api_key", "")
            if serper_key:
                g_jobs = _fetch_serper_google_jobs(q, location=loc, country=indeed_c, results_wanted=want, api_key=serper_key)
                if g_jobs:
                    df_g = pd.DataFrame(g_jobs)
                    df_g["_search_country"] = search_country
                    df_g["_query"] = q
                    return df_g

        kwargs = dict(
            site_name=[site],
            search_term=q,
            location=site_loc,
            results_wanted=want,
            hours_old=hours_filter,
            country_indeed=indeed_c,
            is_remote=req.is_remote,
            easy_apply=req.easy_apply,
            international_only=bool(req.international_only),
            linkedin_fetch_description=False,
        )
        # Pass proxy if configured for Glassdoor / Cloudflare-protected boards
        proxy = os.getenv("SCRAPER_PROXY") or os.getenv("GLASSDOOR_PROXY") or _get_scraper_config().get("scraper_proxy", "")
        if proxy and site in ("glassdoor", "google"):
            kwargs["proxies"] = [proxy]

        if site == "google":
            kwargs["google_search_term"] = f"{q} jobs near {loc}" if loc and loc.lower() != "worldwide" else f"{q} jobs"
        df_t = scrape_jobs(**kwargs)
        if df_t is not None and not df_t.empty:
            df_t["_search_country"] = "Worldwide" if norm_key in ("worldwide", "global", "all", "") else country_name
            df_t["_query"] = q
            return df_t
        return None

    try:
        all_dfs = []
        cache_key = _search_cache_key(req, countries_to_search, effective_sites, hours_filter)
        cached = _search_cache_get(cache_key)
        if cached is not None:
            # Identical search done recently (by anyone) → reuse it, costs no API quota
            cached_df, cached_per_site = cached
            all_dfs = [cached_df.copy()]
            stats["per_site"] = dict(cached_per_site)
            stats["cache_hit"] = True
            stats["tasks_ok"] = len(tasks)
        else:
            _check_and_count_search_quota(current_user)
            executor = ThreadPoolExecutor(max_workers=min(max(len(tasks), 1), 16))
            fut_map = {executor.submit(scrape_task, t): t for t in tasks}
            pending = set(fut_map)
            deadline = t_start + SCRAPE_BUDGET_S
            while pending:
                remaining = deadline - _time.time()
                if remaining <= 0:
                    break
                done, pending = _wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
                for fut in done:
                    t = fut_map[fut]
                    try:
                        res_df = fut.result()
                        stats["tasks_ok"] += 1
                        if res_df is not None and not res_df.empty:
                            all_dfs.append(res_df)
                            stats["per_site"][t[2]] = stats["per_site"].get(t[2], 0) + len(res_df)
                    except Exception as err:
                        stats["tasks_failed"] += 1
                        logger.warning(f"[Scraper] {t[2]} / '{t[3]}' / {t[0]} failed: {err}")
            stats["tasks_timed_out"] = len(pending)
            if pending:
                logger.info(f"[Scraper] {len(pending)} scrape tasks exceeded the {SCRAPE_BUDGET_S}s budget; returning partial results")
            executor.shutdown(wait=False, cancel_futures=True)
            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
                _search_cache_put(cache_key, combined, stats["per_site"])
                all_dfs = [combined]
        stats["timings"]["scrape_s"] = round(_time.time() - t_start, 1)

        if not all_dfs:
            return {
                "jobs": [],
                "total": 0,
                "searched_title": req.title.strip(),
                "searched_countries": countries_to_search,
                "searched_sites": valid_sites,
                "stats": stats,
                "message": "No jobs found for this query on the selected boards/countries.",
            }

        df = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
        df = df.fillna("")
        stats["raw"] = len(df)

        raw_jobs = []

        for _, row in df.iterrows():
            title   = str(row.get("title", "")).strip()
            company = str(row.get("company", "")).strip()
            if not title:
                continue

            desc    = str(row.get("description", ""))
            job_url = str(row.get("job_url", ""))
            salary  = ""
            try:
                if row.get("min_amount"):
                    salary = f"${int(float(row['min_amount'])):,}"
                if row.get("max_amount") and float(row["max_amount"]) != float(row.get("min_amount") or 0):
                    salary += f"–${int(float(row['max_amount'])):,}"
            except (TypeError, ValueError):
                salary = ""
            if not salary and row.get("salary_text"):
                salary = str(row.get("salary_text"))[:60]

            initial_emails = _extract_row_emails(row, desc)

            date_raw = row.get("date_posted")
            age_hours = _compute_job_age_hours(date_raw)
            date_str = str(date_raw) if date_raw else ""
            age_str = _format_age_str(age_hours)
            is_under_24h = bool(age_hours is not None and age_hours <= 24.0)

            # Strictly enforce 24-hour (or custom hours) filter
            if hours_filter is not None:
                if age_hours is not None and age_hours > hours_filter:
                    continue
                # If age_hours is None and 24h filter was selected, never let indeterminate/unverified jobs pollute 24h results
                if age_hours is None and hours_filter <= 24:
                    continue

            is_easy_apply = bool(
                row.get("easy_apply") or
                row.get("is_direct_apply")
            )

            raw_jobs.append({
                "title": title,
                "company": company,
                "location": str(row.get("location", "")),
                "url": job_url,
                "job_url_direct": str(row.get("job_url_direct", "")),
                "company_url_direct": str(row.get("company_url_direct", "")),
                "company_url": str(row.get("company_url", "")),
                "description": desc,
                "site": str(row.get("site", "")),
                "date_posted": date_str,
                "age_hours": age_hours,
                "age_str": age_str,
                "is_under_24h": is_under_24h,
                "salary": salary,
                "emails": initial_emails,
                "easy_apply": is_easy_apply,
                "is_direct_apply": is_easy_apply,
                "company_domain": "",
                "imported": False,
                "country": str(row.get("_search_country", "")),
                "listing_type": str(row.get("listing_type", "")),
                "company_industry": str(row.get("company_industry", "")),
                "is_international_eligible": bool(
                    "international" in str(row.get("company_industry", "")).lower() or
                    "international" in desc.lower() or
                    req.international_only
                ),
                "score": None,
                "matched_skills": [],
                "missing_skills": [],
                "matched_query": str(row.get("_query", "")),
                "also_on": [str(row.get("site", ""))],
                "relevance": best_relevance(all_queries, title, desc),
                "_spam": is_spam(title, desc, company),
            })

        # ── Quality stage 1: spam removal + cross-board / cross-query merge ──
        before_spam = len(raw_jobs)
        raw_jobs = [j for j in raw_jobs if not j.pop("_spam", False)]
        stats["spam_removed"] = before_spam - len(raw_jobs)
        raw_jobs = dedup_and_merge(raw_jobs)
        stats["after_dedup"] = len(raw_jobs)

        # ── Quality stage 2: adaptive relevance filter ──
        # Strong = the title really is the searched role (synonym-aware).
        # Weak   = only the description matches; used to back-fill when strong results are scarce.
        strong = [j for j in raw_jobs if j["relevance"] >= 40]
        weak = sorted((j for j in raw_jobs if 20 <= j["relevance"] < 40), key=lambda j: -j["relevance"])
        min_wanted = max(req.results_wanted, 15)
        if len(strong) < min_wanted:
            strong += weak[: min_wanted - len(strong)]
        raw_jobs = strong
        stats["after_relevance"] = len(raw_jobs)

        # Cap work for the (expensive) enrichment stages: best candidates first.
        for j in raw_jobs:
            j["quality"] = quality_score(j)
        raw_jobs.sort(key=lambda j: -j["quality"])
        MAX_RESULTS = min(max(req.results_wanted * 6, 150), 250)
        raw_jobs = raw_jobs[:MAX_RESULTS]

        def _bounded_map(fn, items, workers, budget_s):
            """Parallel map that never blocks longer than budget_s; unfinished items are kept as-is."""
            ex = ThreadPoolExecutor(max_workers=workers)
            futs = [ex.submit(fn, it) for it in items]
            _wait(futs, timeout=budget_s)
            out = []
            for it, f in zip(items, futs):
                if f.done() and not f.exception():
                    out.append(f.result())
                else:
                    out.append(it)
            ex.shutdown(wait=False, cancel_futures=True)
            return out

        # Fast parallel enrichment of missing job descriptions (e.g. LinkedIn guest API)
        t_enrich = _time.time()
        try:
            raw_jobs = _bounded_map(_enrich_job_description, raw_jobs, 12, 25)
        except Exception as desc_err:
            logger.warning(f"[Scraper] Parallel description enrichment warning: {desc_err}")
        stats["timings"]["describe_s"] = round(_time.time() - t_enrich, 1)

        # Descriptions are now richer → refine relevance for jobs that were description-only matches.
        for j in raw_jobs:
            if j.get("relevance", 0) < 40 and j.get("description"):
                j["relevance"] = max(j["relevance"], best_relevance(all_queries, j["title"], j["description"]))

        # Multi-Layer Recruiter Email Discovery Engine (time-boxed so search stays fast)
        t_hunt = _time.time()
        from recruiter_hunter import enrich_job_emails

        def _hunt(j: dict) -> dict:
            direct = list(j.get("emails") or [])
            try:
                found = enrich_job_emails(dict(j)) or []
            except Exception as hunt_err:
                logger.warning(f"[RecruiterHunter] {j.get('company')}: {hunt_err}")
                found = []
            merged, seen_em = [], set()
            for e in direct + found:
                em = re.sub(r"[\[\]'\"\s]", "", (e.get("email") if isinstance(e, dict) else str(e))).lower()
                if em and "@" in em and em not in seen_em:
                    seen_em.add(em)
                    merged.append(e if isinstance(e, dict) else {"email": em, "source": "found"})
            j["emails"] = merged
            if not j.get("company_domain") and merged:
                j["company_domain"] = merged[0]["email"].split("@")[-1]
            return j

        jobs = _bounded_map(_hunt, raw_jobs, 20, 12)
        stats["timings"]["email_hunt_s"] = round(_time.time() - t_hunt, 1)

        # Automatic High-Accuracy AI Matching if user has a CV
        cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
        if cv_rec and cv_rec.text_content and jobs:
            try:
                from cv_matcher import compute_match
                cv_text = cv_rec.text_content

                def score_one_job(j):
                    try:
                        s, bd = compute_match(cv_text, j.get("description", ""), j.get("title", ""))
                        j["score"] = s
                        j["breakdown"] = bd
                        j["matched_skills"] = bd.get("matched_tech", [])
                        j["missing_skills"] = bd.get("missing_tech", [])
                        j["tips"] = bd.get("tips", [])
                    except Exception as match_e:
                        logger.debug(f"Match error on '{j.get('title')}': {match_e}")
                    return j

                with ThreadPoolExecutor(max_workers=8) as matcher_executor:
                    jobs = list(matcher_executor.map(score_one_job, jobs))
            except Exception as auto_err:
                logger.warning(f"[Matching] Auto-match exception: {auto_err}")

        # ── career-ops signals: repost history, posting legitimacy, work-authorization gates ──
        t_sig = _time.time()
        record_and_annotate(db, jobs)
        from ..job_evaluator import assess_legitimacy, assess_work_auth
        for j in jobs:
            try:
                lg = assess_legitimacy(j, j.get("sighting"))
                j["legitimacy"] = {"tier": lg["tier"], "risk": lg["risk"],
                                   "flags": [s["finding"] for s in lg["signals"] if s["impact"] >= 0.5]}
                wa = assess_work_auth(j)
                j["work_auth"] = {"blockers": [b["label"] for b in wa["blockers"]],
                                  "positives": wa["positives"][:3]}
            except Exception as sig_err:
                logger.debug(f"[Signals] {j.get('title')}: {sig_err}")
        stats["timings"]["signals_s"] = round(_time.time() - t_sig, 1)

        # ── Final ranking: CV fit (if available) blended with listing quality ──
        for j in jobs:
            j["quality"] = quality_score(j)
            cv = j.get("score")
            j["rank_score"] = round(0.55 * cv + 0.45 * j["quality"], 1) if cv is not None else float(j["quality"])
            # Ghost / suspicious postings sink (career-ops Block G)
            tier = (j.get("legitimacy") or {}).get("tier")
            j["rank_score"] -= 15 if tier == "Suspicious" else (5 if tier == "Proceed with Caution" else 0)
            j["rank_score"] -= 3 * min(j.get("repost_count") or 0, 3)
        jobs.sort(key=lambda x: x["rank_score"], reverse=True)
        stats["timings"]["total_s"] = round(_time.time() - t_start, 1)

        # Check user's applied / saved applications to annotate jobs
        apps = db.query(models.Application).filter(models.Application.user_id == current_user.id).all()
        applied_urls: set = set()
        applied_clean_urls: set = set()
        applied_job_ids: set = set()
        applied_title_comp: set = set()
        applied_company_to_titles: dict = {}

        saved_urls: set = set()
        saved_clean_urls: set = set()
        saved_job_ids: set = set()
        saved_title_comp: set = set()

        for a in apps:
            st = (a.status or "").lower()
            raw_url = (a.url or "").strip().lower()
            cl_url = _clean_job_url(raw_url)
            jid = _extract_job_id(raw_url)
            nc = _norm_company(a.company or "")
            nt = _norm_title(a.title or "")
            tc = f"{nt}|{nc}"

            if st != "saved":
                if raw_url: applied_urls.add(raw_url)
                if cl_url: applied_clean_urls.add(cl_url)
                if jid: applied_job_ids.add(jid)
                if nt and nc: applied_title_comp.add(tc)
                if nc and nt:
                    applied_company_to_titles.setdefault(nc, set()).add(nt)
            else:
                if raw_url: saved_urls.add(raw_url)
                if cl_url: saved_clean_urls.add(cl_url)
                if jid: saved_job_ids.add(jid)
                if nt and nc: saved_title_comp.add(tc)

        # Every recruiter address already applied to (sent emails + addresses noted on Tracker cards)
        applied_emails: set = set()
        for a in apps:
            if (a.status or "").lower() != "saved" and a.notes:
                applied_emails.update(m.lower() for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+\w", a.notes))
        for (to_email,) in db.query(models.EmailLog.to_email).filter(
                models.EmailLog.user_id == current_user.id,
                models.EmailLog.status != "failed").all():
            if to_email:
                applied_emails.add(to_email.strip().lower())
        applied_emails.discard((current_user.email or "").lower())
        hidden_by_email = 0

        for j in jobs:
            j_raw_url = (j.get("url") or j.get("job_url_direct") or "").strip().lower()
            j_cl_url = _clean_job_url(j_raw_url)
            j_id = _extract_job_id(j_raw_url)
            j_nc = _norm_company(j.get("company") or "")
            j_nt = _norm_title(j.get("title") or "")
            j_tc = f"{j_nt}|{j_nc}"

            is_app = False
            if j_raw_url and j_raw_url in applied_urls:
                is_app = True
            elif j_cl_url and j_cl_url in applied_clean_urls:
                is_app = True
            elif j_id and j_id in applied_job_ids:
                is_app = True
            elif j_tc and j_tc in applied_title_comp:
                is_app = True
            elif j_nc and j_nt and j_nc in applied_company_to_titles:
                for at in applied_company_to_titles[j_nc]:
                    if j_nt in at or at in j_nt:
                        is_app = True
                        break
            if not is_app and applied_emails:
                j_emails = {((e.get("email") or "") if isinstance(e, dict) else str(e or "")).strip().lower()
                            for e in (j.get("emails") or [])}
                j_emails.discard("")
                if j_emails & applied_emails:
                    is_app = True
                    hidden_by_email += 1

            is_sav = False
            if not is_app:
                if j_raw_url and j_raw_url in saved_urls:
                    is_sav = True
                elif j_cl_url and j_cl_url in saved_clean_urls:
                    is_sav = True
                elif j_id and j_id in saved_job_ids:
                    is_sav = True
                elif j_tc and j_tc in saved_title_comp:
                    is_sav = True

            j["is_applied"] = is_app
            j["is_saved"] = is_sav

        # Exclude already applied jobs so candidate never sees them again
        before_hide = len(jobs)
        jobs = [j for j in jobs if not j.get("is_applied")]
        stats["hidden_already_applied"] = before_hide - len(jobs)
        stats["hidden_by_email"] = hidden_by_email

        # Preserve rich description lengths (up to 4500 chars) for full requirements view
        for j in jobs:
            if len(j.get("description", "")) > 4500:
                j["description"] = j["description"][:4500]

        return {
            "jobs": jobs,
            "total": len(jobs),
            "searched_title": req.title.strip(),
            "searched_countries": countries_to_search,
            "searched_sites": valid_sites,
            "queries_used": all_queries,
            "stats": stats,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/fetch-description")
def fetch_job_description(req: JobDescriptionRequest,
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Fetch description on-demand for a specific job."""
    url = req.url or ""
    desc = ""
    emails = []

    # 1. Job Bank Canada specialized fetch (with JSF AJAX extraction for recruiter email)
    if "jobbank.gc.ca" in url or (req.job_id and "jobbank" in str(req.job_id).lower()):
        jb_res = _fetch_jobbank_details(req.job_id or url)
        if jb_res.get("description"):
            desc = jb_res["description"]
        if jb_res.get("emails"):
            emails = list(jb_res["emails"])
    elif "linkedin.com" in url or (req.job_id and str(req.job_id).isdigit()):
        desc = _fetch_linkedin_description(req.job_id or url)

    if not desc and url.startswith("http"):
        try:
            from bs4 import BeautifulSoup
            import requests as req_lib
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = req_lib.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "noscript", "nav", "footer"]):
                    tag.decompose()
                desc = soup.get_text("\n", strip=True)[:4500]
        except Exception:
            pass

    for e in _extract_emails_from_text(desc):
        if e not in emails:
            emails.append(e)

    score = None
    breakdown = {}
    matched_skills = []
    missing_skills = []
    tips = []

    cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    if cv_rec and cv_rec.text_content and desc:
        try:
            from cv_matcher import compute_match
            score, breakdown = compute_match(cv_rec.text_content, desc, req.title or "")
            matched_skills = breakdown.get("matched_tech", [])
            missing_skills = breakdown.get("missing_tech", [])
            tips = breakdown.get("tips", [])
        except Exception:
            pass

    return {
        "description": desc,
        "emails": emails,
        "score": score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "tips": tips
    }


@router.post("/import-url")
def import_from_url(req: ImportUrlRequest,
                    db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Scrape any job posting URL and extract emails + basic info."""
    clean_url = req.url.strip()

    # 1. Specialized instant handler for Job Bank Canada URLs
    if "jobbank.gc.ca" in clean_url:
        jb_data = _fetch_jobbank_details(clean_url)
        if jb_data and jb_data.get("title"):
            jb_emails = [{"email": e, "source": "found"} for e in jb_data.get("emails", [])]
            score = None
            breakdown = {}
            matched_skills = []
            missing_skills = []
            tips = []
            cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
            if cv_rec and cv_rec.text_content and jb_data.get("description"):
                try:
                    from cv_matcher import compute_match
                    score, breakdown = compute_match(cv_rec.text_content, jb_data["description"], jb_data["title"])
                    matched_skills = breakdown.get("matched_tech", [])
                    missing_skills = breakdown.get("missing_tech", [])
                    tips = breakdown.get("tips", [])
                except Exception:
                    pass
            return {
                "job": {
                    "title": jb_data["title"],
                    "company": jb_data["company"] or "Job Bank Employer",
                    "location": jb_data.get("location", ""),
                    "url": jb_data.get("url", clean_url),
                    "job_url_direct": jb_data.get("job_url_direct", clean_url),
                    "description": jb_data.get("description", ""),
                    "site": "Job Bank (Canada)",
                    "date_posted": "",
                    "salary": jb_data.get("salary", ""),
                    "emails": jb_emails,
                    "easy_apply": jb_data.get("easy_apply", False),
                    "is_direct_apply": jb_data.get("is_direct_apply", False),
                    "company_domain": "",
                    "imported": True,
                    "score": score,
                    "breakdown": breakdown,
                    "matched_skills": matched_skills,
                    "missing_skills": missing_skills,
                    "tips": tips
                }
            }
    try:
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Try curl_cffi first (bypasses anti-bot / Cloudflare)
        # Fall back to regular requests if not available
        try:
            from curl_cffi import requests as c_requests
            resp = c_requests.get(
                req.url, impersonate="chrome", timeout=15,
                headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            html = resp.text
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
        except ImportError:
            import requests as r
            import urllib3; urllib3.disable_warnings()
            resp = r.get(req.url, headers=headers, timeout=12, verify=False)
            resp.raise_for_status()
            html = resp.text

        soup  = BeautifulSoup(html, "html.parser")
        # Strip scripts/styles
        for tag in soup(["script","style","noscript"]): tag.decompose()
        text = soup.get_text(" ", strip=True)

        # Try to extract title
        title = ""
        if soup.title: title = soup.title.string or ""
        for sel in ["h1","[class*='job-title']","[class*='title']"]:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True): title = el.get_text(strip=True); break

        # Company from meta or og tags
        company = ""
        for attr in [("property","og:site_name"),("name","author"),("property","og:title")]:
            tag = soup.find("meta", {attr[0]:attr[1]})
            if tag and tag.get("content"): company = tag["content"]; break

        from recruiter_hunter import enrich_job_emails
        job_data = {
            "title":    title[:120] or "Imported Job",
            "company":  company[:80] or domain,
            "location": "",
            "url":      req.url,
            "job_url_direct": req.url,
            "description": text,
            "site":     "custom",
            "date_posted": "",
            "salary":   "",
            "emails":   [],
            "company_domain": domain,
            "imported": True,
            "score": score,
            "breakdown": breakdown,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "tips": tips,
        }
        job_data["emails"] = enrich_job_emails(job_data)
        if not job_data.get("company_domain") and job_data["emails"]:
            job_data["company_domain"] = job_data["emails"][0]["email"].split("@")[-1]

        job_data["description"] = text[:800]
        return job_data
    except Exception as e:
        raise HTTPException(400, f"Could not import URL: {str(e)}")

@router.post("/save")
def save_job(req: SaveJobRequest, db: Session=Depends(get_db),
             current_user: models.User=Depends(get_current_user)):
    job = models.SavedJob(user_id=current_user.id, title=req.title,
        company=req.company, location=req.location, url=req.url,
        description=req.description, match_score=req.match_score)
    db.add(job)

    # Sync into Tracker Application table as status='saved'
    existing = None
    if req.url:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.url == req.url
        ).first()
    if not existing and req.company and req.title:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.company.ilike(req.company),
            models.Application.title.ilike(req.title)
        ).first()

    if existing:
        if existing.status == "saved":
            existing.match_score = req.match_score or existing.match_score
    else:
        app = models.Application(
            user_id=current_user.id,
            title=req.title,
            company=req.company,
            location=req.location or "",
            url=req.url or "",
            status="saved",
            match_score=req.match_score or 0,
            notes=f"Saved from Job Board.\nDescription: {(req.description or '')[:300]}"
        )
        db.add(app)

    db.commit()
    db.refresh(job)
    return {"message":"Saved","id":job.id}

@router.post("/mark-applied")
def mark_job_applied(req: MarkAppliedRequest, db: Session=Depends(get_db),
                     current_user: models.User=Depends(get_current_user)):
    """Explicitly marks a job as applied and records it in Tracker."""
    url = (req.url or "").strip()
    title = (req.title or "").strip()
    company = (req.company or "").strip()

    existing = None
    if url:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.url == url
        ).first()
    if not existing and company and title:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.company.ilike(company),
            models.Application.title.ilike(title)
        ).first()

    now = datetime.utcnow()
    if existing:
        existing.status = "applied"
        existing.applied_at = now
        if not existing.follow_up_date:
            existing.follow_up_date = now + timedelta(days=5)
        if url and not existing.url:
            existing.url = url
        if req.match_score:
            existing.match_score = req.match_score
        if req.notes:
            existing.notes = (existing.notes or "") + f"\n{req.notes}"
        db.commit()
        db.refresh(existing)
        return {"message": "Updated existing application to applied", "id": existing.id}

    app = models.Application(
        user_id=current_user.id,
        title=title,
        company=company,
        location=req.location or "",
        url=url,
        status="applied",
        match_score=req.match_score or 0,
        notes=req.notes or "Applied on external portal.",
        applied_at=now,
        follow_up_date=now + timedelta(days=5)
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"message": "Job marked as applied and saved to tracker", "id": app.id}

@router.post("/easy-apply")
def easy_apply_job(req: EasyApplyRequest,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """
    Auto-applies to a job with Candidature Simplifiée (Easy Apply) without needing an email.
    Generates tailored CV, ATS alignment, and registers the application in Tracker.
    """
    url = (req.url or req.job_url_direct or "").strip()
    title = (req.title or "").strip()
    company = (req.company or "").strip()
    desc = (req.description or "").strip()

    existing = None
    if url:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.url == url
        ).first()
    if not existing and company and title:
        existing = db.query(models.Application).filter(
            models.Application.user_id == current_user.id,
            models.Application.company.ilike(company),
            models.Application.title.ilike(title)
        ).first()

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv.text_content if cv else ""

    # User-clicked Easy Apply: honest per-job tailored COPY saved on the Tracker card
    # (download it there to upload on the job site). Original CV is never modified.
    custom_pdf_bytes = None
    custom_pdf_name = None
    effective_score = req.match_score or 0
    original_score = None
    if req.customize_cv:
        from ..tailoring import honest_tailored_attachment
        custom_pdf_bytes, custom_pdf_name, original_score, t_score = honest_tailored_attachment(
            cv, title, company, desc)
        if custom_pdf_bytes and t_score is not None:
            effective_score = t_score

    now = datetime.utcnow()
    site_label = (req.site or "Easy Apply").title()
    notes = f"Applied via Candidature Simplifiée ({site_label})" + (f" (Tailored CV: match {original_score}% → {effective_score}%)" if custom_pdf_name else "")
    if req.notes:
        notes += f"\n{req.notes}"

    if existing:
        existing.status = "applied"
        existing.applied_at = now
        existing.follow_up_date = now + timedelta(days=5)
        if url and not existing.url:
            existing.url = url
        existing.match_score = effective_score or existing.match_score
        existing.notes = notes
        if custom_pdf_bytes:
            existing.tailored_cv_filename = custom_pdf_name
            existing.tailored_cv_data = custom_pdf_bytes
        db.commit()
        db.refresh(existing)
        return {
            "success": True,
            "message": f"Successfully applied via Candidature Simplifiée for {title} at {company}!",
            "application_id": existing.id,
            "match_score": effective_score,
            "tailored_cv": bool(custom_pdf_bytes)
        }

    app = models.Application(
        user_id=current_user.id,
        title=title,
        company=company,
        location=req.location or "",
        url=url,
        status="applied",
        match_score=effective_score,
        notes=notes,
        applied_at=now,
        follow_up_date=now + timedelta(days=5),
        tailored_cv_filename=custom_pdf_name,
        tailored_cv_data=custom_pdf_bytes
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {
        "success": True,
        "message": f"Successfully applied via Candidature Simplifiée for {title} at {company}!",
        "application_id": app.id,
        "match_score": effective_score,
        "tailored_cv": bool(custom_pdf_bytes)
    }

@router.post("/batch-easy-apply")
def batch_easy_apply_jobs(req: BatchEasyApplyJobsRequest,
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """
    Auto-applies to ALL selected Candidature Simplifiée (Easy Apply) jobs in 1 batch.
    Generates tailored CVs and logs each job into the Tracker pipeline.
    """
    if not req.jobs:
        return {"success": True, "applied_count": 0, "message": "No jobs provided for batch application."}

    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv.text_content if cv else ""

    applied_jobs = []
    now = datetime.utcnow()

    for item in req.jobs:
        url = (item.url or item.job_url_direct or "").strip()
        title = (item.title or "").strip()
        company = (item.company or "").strip()
        desc = (item.description or "").strip()

        existing = None
        if url:
            existing = db.query(models.Application).filter(
                models.Application.user_id == current_user.id,
                models.Application.url == url
            ).first()
        if not existing and company and title:
            existing = db.query(models.Application).filter(
                models.Application.user_id == current_user.id,
                models.Application.company.ilike(company),
                models.Application.title.ilike(title)
            ).first()

        # User-clicked batch Easy Apply: honest per-job tailored COPY saved on the Tracker card
        custom_pdf_bytes = None
        custom_pdf_name = None
        effective_score = item.match_score or 0
        original_score = None
        if req.customize_cv and item.customize_cv:
            from ..tailoring import honest_tailored_attachment
            custom_pdf_bytes, custom_pdf_name, original_score, t_score = honest_tailored_attachment(
                cv, title, company, desc)
            if custom_pdf_bytes and t_score is not None:
                effective_score = t_score

        site_label = (item.site or "Easy Apply").title()
        notes = f"Batch applied via Candidature Simplifiée ({site_label})" + (f" (Tailored CV: match {original_score}% → {effective_score}%)" if custom_pdf_name else "")

        if existing:
            existing.status = "applied"
            existing.applied_at = now
            existing.follow_up_date = now + timedelta(days=5)
            existing.match_score = effective_score or existing.match_score
            existing.notes = notes
            if custom_pdf_bytes:
                existing.tailored_cv_filename = custom_pdf_name
                existing.tailored_cv_data = custom_pdf_bytes
            db.commit()
            applied_jobs.append({"id": existing.id, "title": title, "company": company, "url": url})
        else:
            app = models.Application(
                user_id=current_user.id,
                title=title,
                company=company,
                location=item.location or "",
                url=url,
                status="applied",
                match_score=effective_score,
                notes=notes,
                applied_at=now,
                follow_up_date=now + timedelta(days=5),
                tailored_cv_filename=custom_pdf_name,
                tailored_cv_data=custom_pdf_bytes
            )
            db.add(app)
            db.commit()
            db.refresh(app)
            applied_jobs.append({"id": app.id, "title": title, "company": company, "url": url})

    return {
        "success": True,
        "applied_count": len(applied_jobs),
        "jobs": applied_jobs,
        "message": f"Successfully auto-applied to {len(applied_jobs)} Candidature Simplifiée job(s) and saved to Tracker!"
    }

@router.get("/saved")
def get_saved(db: Session=Depends(get_db),
              current_user: models.User=Depends(get_current_user)):
    jobs = db.query(models.SavedJob)\
             .filter(models.SavedJob.user_id==current_user.id)\
             .order_by(models.SavedJob.saved_at.desc()).all()
    return [{"id":j.id,"title":j.title,"company":j.company,"location":j.location,
             "url":j.url,"match_score":j.match_score,"saved_at":str(j.saved_at)} for j in jobs]

@router.delete("/saved/{job_id}")
def delete_saved(job_id: int, db: Session=Depends(get_db),
                 current_user: models.User=Depends(get_current_user)):
    job = db.query(models.SavedJob).filter(
        models.SavedJob.id==job_id,
        models.SavedJob.user_id==current_user.id).first()
    if not job: raise HTTPException(404,"Not found")
    db.delete(job); db.commit()
    return {"message":"Deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# career-ops integrations: "should I apply?" evaluation + liveness check
# ─────────────────────────────────────────────────────────────────────────────
class EvaluateJobRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    job_url_direct: Optional[str] = ""
    description: str = ""
    salary: Optional[str] = ""
    date_posted: Optional[str] = ""
    age_hours: Optional[float] = None
    site: Optional[str] = ""
    check_liveness: bool = True


class LivenessRequest(BaseModel):
    urls: List[str]


@router.post("/evaluate")
def evaluate_job_route(req: EvaluateJobRequest,
                       db: Session = Depends(get_db),
                       current_user: models.User = Depends(get_current_user)):
    """Full A–G evaluation (career-ops oferta.md) → 1–5 score and Apply / Consider / Skip verdict."""
    from ..job_evaluator import evaluate_job
    from ..sightings import lookup
    from ..liveness import check_liveness

    job = req.dict()
    if job.get("age_hours") is None and job.get("date_posted"):
        job["age_hours"] = _compute_job_age_hours(job["date_posted"])
    # Descriptions arrive truncated from search results — refetch when thin.
    if len((job.get("description") or "").strip()) < 300 and job.get("url"):
        try:
            job = _enrich_job_description({**job, "site": job.get("site") or ""})
        except Exception:
            pass

    cv_rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    cv_text = cv_rec.text_content if cv_rec and cv_rec.text_content else ""
    live = None
    if req.check_liveness:
        target = job.get("job_url_direct") or job.get("url") or ""
        if target:
            live = check_liveness(target)
    result = evaluate_job(job, cv_text, sighting=lookup(db, job), liveness=live)
    result["liveness"] = live
    return result


@router.post("/liveness")
def liveness_route(req: LivenessRequest, current_user: models.User = Depends(get_current_user)):
    """Is the posting still open? (career-ops liveness-core) — active / expired / uncertain per URL."""
    from ..liveness import check_many
    if not req.urls:
        raise HTTPException(400, "No URLs provided")
    return {"results": check_many(req.urls)}


@router.get("/open-sources")
def open_sources_info(current_user: models.User = Depends(get_current_user)):
    """List the zero-auth sources and ATS companies the 'remote_boards' / 'ats' sites cover."""
    from ..open_sources import REMOTE_BOARDS, load_ats_companies
    companies = load_ats_companies()
    return {
        "remote_boards": REMOTE_BOARDS,
        "ats_companies": len(companies),
        "ats_vendors": sorted({c["vendor"] for c in companies}),
        "serper_ats_discovery": bool(os.getenv("SERPER_API_KEY", "") or _get_scraper_config().get("serper_api_key", "")),
    }
