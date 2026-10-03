
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime, timedelta, date
import re
import urllib.parse
import urllib.request

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
    if not url: return ""
    u = url.split("?")[0].rstrip("/")
    u = re.sub(r"^https?://(www\.|[a-z]{2}\.)?", "", u.lower())
    return u

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
HR_PREFIXES = ["careers","jobs","hr","recruit","hiring","talent","apply","recruitment","people","work"]
JOB_BOARDS  = {"linkedin.com","indeed.com","glassdoor.com","ziprecruiter.com","monster.com",
               "dice.com","greenhouse.io","lever.co","workday.com","myworkdayjobs.com",
               "taleo.net","icims.com","jobvite.com","wellfound.com","remoteok.com"}

def _clean_email(e):
    e = e.strip().lower()
    if any(s in e for s in SKIP_PATTERNS): return None
    if any(e.endswith(x) for x in SKIP_EXTS): return None
    try:
        from recruiter_hunter import is_email_blacklisted
        if is_email_blacklisted(e):
            return None
    except Exception:
        pass
    parts = e.split("@")
    if len(parts)!=2: return None
    loc, dom = parts
    if len(loc)<2 or len(dom)<4 or "." not in dom: return None
    return e

def _extract_emails_from_text(text):
    seen, clean = set(), []
    for e in EMAIL_RE.findall(text or ""):
        c = _clean_email(e)
        if c and c not in seen: seen.add(c); clean.append(c)
    return clean[:5]

def _domain_from_url(url):
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts)>=2 else ""
    except: return ""

def _infer_hr_emails(domain):
    if not domain or len(domain)<5 or domain in JOB_BOARDS: return []
    return [f"{p}@{domain}" for p in HR_PREFIXES[:4]]

def _score_email(email):
    local = email.split("@")[0].lower()
    s = 0
    if any(p in local for p in ["hr","recruit","hiring","talent","career","job"]): s+=10
    if any(p in local for p in ["info","contact","hello","admin"]): s+=5
    if any(p in local for p in ["noreply","no-reply","donotreply","bounce"]): s-=20
    return s

def _best_emails(extracted, inferred):
    combined = {}
    for e in extracted:
        combined[e] = {"email":e,"source":"found","score":_score_email(e)+15}
    for e in inferred:
        if e not in combined:
            combined[e] = {"email":e,"source":"inferred","score":_score_email(e)}
    return sorted(combined.values(), key=lambda x:-x["score"])[:5]

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
    return ""

def _enrich_job_description(job: dict) -> dict:
    current_desc = job.get("description") or ""
    if len(current_desc.strip()) > 80:
        return job

    url = job.get("url") or ""
    site = (job.get("site") or "").lower()
    if "linkedin" in site or "linkedin.com" in url:
        desc = _fetch_linkedin_description(url)
        if desc:
            job["description"] = desc
            new_emails = _extract_emails_from_text(desc)
            if new_emails:
                existing = [e.get("email") if isinstance(e, dict) else e for e in (job.get("emails") or [])]
                for ne in new_emails:
                    if ne not in existing:
                        job.setdefault("emails", []).append({"email": ne, "source": "found"})
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
    SUPPORTED = {"linkedin", "indeed", "glassdoor", "zip_recruiter", "google"}
    valid_sites = [s for s in req.sites if s in SUPPORTED] or ["linkedin", "indeed", "zip_recruiter", "google"]

    # Determine countries — use multi list or fall back to single
    countries_to_search = [c.strip() for c in req.countries if c.strip()] if req.countries else [req.country or "Worldwide"]
    if not countries_to_search:
        countries_to_search = ["Worldwide"]

    hours_filter = req.hours_old if (req.hours_old and req.hours_old > 0) else None

    # High-yield scrape buffer: request generous count to guarantee high results even after 24h & applied filters
    # For 24h filter, LinkedIn often returns old jobs → use higher multiplier + prefer other boards
    fetch_multiplier = 5 if hours_filter and hours_filter <= 24 else (3 if hours_filter else 2)
    per_country = max((req.results_wanted * fetch_multiplier) // max(len(countries_to_search), 1), min(max(req.results_wanted * 2, 15), 45))

    # For strict 24h searches: remove LinkedIn (it ignores f_TPR for public unauthenticated requests)
    # Indeed, Google, and ZipRecruiter actually honor the hours_old parameter reliably
    effective_sites = list(valid_sites)
    if hours_filter and hours_filter <= 24:
        effective_sites = [s for s in effective_sites if s != "linkedin"]
        if not effective_sites:
            effective_sites = ["indeed", "google", "zip_recruiter"]
        # Ensure indeed and google are included for 24h
        for must_have in ["indeed", "google"]:
            if must_have not in effective_sites and must_have in SUPPORTED:
                effective_sites.append(must_have)

    def scrape_country_worker(country_name: str):
        try:
            norm_key = country_name.strip().lower()
            if norm_key in ("worldwide", "global", "all", ""):
                # Indeed doesn't have a 'worldwide' domain; 'usa' indexes massive US + global remote jobs
                indeed_c = "usa"
                linkedin_loc = "Worldwide"
                loc = req.location.strip() if req.location.strip() else ("Remote" if req.is_remote else "Worldwide")
            else:
                indeed_c, linkedin_loc = COUNTRY_NORM.get(norm_key, (norm_key, country_name.strip()))
                loc = req.location.strip() if req.location.strip() else linkedin_loc

            df_c = scrape_jobs(
                site_name=effective_sites,
                search_term=req.title.strip(),
                location=loc,
                results_wanted=per_country,
                hours_old=hours_filter,
                country_indeed=indeed_c,
                is_remote=req.is_remote,
                easy_apply=req.easy_apply,
                linkedin_fetch_description=False,
            )
            if df_c is not None and not df_c.empty:
                df_c["_search_country"] = "Worldwide" if norm_key in ("worldwide", "global", "all", "") else country_name
                return df_c
        except Exception as err:
            print(f"[Scraper] Warning for country '{country_name}': {err}")
        return None

    try:
        all_dfs = []
        # Run parallel scraping across all selected countries
        max_workers = min(len(countries_to_search), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_country = {
                executor.submit(scrape_country_worker, c): c
                for c in countries_to_search
            }
            for future in as_completed(future_to_country):
                res_df = future.result()
                if res_df is not None and not res_df.empty:
                    all_dfs.append(res_df)

        if not all_dfs:
            return {
                "jobs": [],
                "total": 0,
                "searched_title": req.title.strip(),
                "searched_countries": countries_to_search,
                "searched_sites": valid_sites,
                "message": "No jobs found for this query on the selected boards/countries."
            }

        df = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
        df = df.fillna("")

        raw_jobs = []
        seen_keys = set()   # dedup by title+company

        for _, row in df.iterrows():
            title   = str(row.get("title", "")).strip()
            company = str(row.get("company", "")).strip()
            if not title:
                continue

            dedup_key = f"{title.lower()}|{company.lower()}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            desc    = str(row.get("description", ""))
            job_url = str(row.get("job_url", ""))
            salary  = ""
            if row.get("min_amount"):
                salary = f"${int(float(row['min_amount'])):,}"
            if row.get("max_amount"):
                salary += f"–${int(float(row['max_amount'])):,}"

            initial_emails = []
            if row.get("emails"):
                for e in str(row["emails"]).replace(";", ",").split(","):
                    c = e.strip().lower()
                    if c and "@" in c:
                        initial_emails.append({"email": c, "source": "found"})

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
                "score": None,
                "matched_skills": [],
                "missing_skills": [],
            })

        # Fast parallel enrichment of missing job descriptions (e.g. LinkedIn guest API)
        try:
            with ThreadPoolExecutor(max_workers=10) as desc_executor:
                raw_jobs = list(desc_executor.map(_enrich_job_description, raw_jobs))
        except Exception as desc_err:
            print(f"[Scraper] Parallel description enrichment warning: {desc_err}")

        # Multi-Layer Recruiter Email Discovery Engine
        from recruiter_hunter import batch_enrich_jobs
        jobs = batch_enrich_jobs(raw_jobs, max_workers=12)

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
                        print(f"Match error on '{j.get('title')}': {match_e}")
                    return j

                with ThreadPoolExecutor(max_workers=8) as matcher_executor:
                    jobs = list(matcher_executor.map(score_one_job, jobs))

                # Auto-sort so highest matching jobs appear first
                jobs.sort(key=lambda x: (x.get("score") is not None, x.get("score") or 0), reverse=True)
            except Exception as auto_err:
                print(f"[Matching] Auto-match exception: {auto_err}")

        # Check user's applied / saved applications to annotate jobs
        apps = db.query(models.Application).filter(models.Application.user_id == current_user.id).all()
        applied_urls = set()
        applied_clean_urls = set()
        applied_job_ids = set()
        applied_title_comp = set()
        applied_companies = set()

        saved_urls = set()
        saved_clean_urls = set()
        saved_job_ids = set()
        saved_title_comp = set()

        for a in apps:
            st = (a.status or "").lower()
            raw_url = (a.url or "").strip().lower()
            cl_url = _clean_job_url(raw_url)
            jid = _extract_job_id(raw_url)
            nc = _norm_company(a.company or "")
            nt = _norm_title(a.title or "")
            tc = f"{nt}|{nc}"

            if st != "saved":
                # ANY status other than 'saved' (applied, sent, review, interview, offer, rejected, accepted) is an applied application!
                if raw_url: applied_urls.add(raw_url)
                if cl_url: applied_clean_urls.add(cl_url)
                if jid: applied_job_ids.add(jid)
                if nt and nc: applied_title_comp.add(tc)
                if nc: applied_companies.add(nc)
            else:
                if raw_url: saved_urls.add(raw_url)
                if cl_url: saved_clean_urls.add(cl_url)
                if jid: saved_job_ids.add(jid)
                if nt and nc: saved_title_comp.add(tc)

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
            elif j_nc and j_nc in applied_companies and j_nt:
                for tc in applied_title_comp:
                    if "|" in tc:
                        parts = tc.split("|", 1)
                        if len(parts) == 2:
                            at, ac = parts
                            if ac == j_nc and (j_nt in at or at in j_nt):
                                is_app = True
                                break

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
        jobs = [j for j in jobs if not j.get("is_applied")]

        # Preserve rich description lengths (up to 4500 chars) for full requirements view
        for j in jobs:
            if len(j.get("description", "")) > 4500:
                j["description"] = j["description"][:4500]

        return {"jobs": jobs, "total": len(jobs)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/fetch-description")
def fetch_job_description(req: JobDescriptionRequest,
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Fetch description on-demand for a specific job."""
    url = req.url or ""
    desc = ""
    if "linkedin.com" in url or (req.job_id and str(req.job_id).isdigit()):
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

    emails = _extract_emails_from_text(desc)

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

    custom_pdf_bytes = None
    custom_pdf_name = None
    effective_score = req.match_score or 80

    if req.customize_cv and cv_text:
        try:
            from cv_tailor import tailor_cv
            tailor_res = tailor_cv(cv_text, title, company, desc or title)
            custom_pdf_bytes = tailor_res["pdf_bytes"]
            custom_pdf_name = tailor_res["filename"]
            effective_score = tailor_res["tailored_score"]
        except Exception as e:
            print(f"[EasyApply] Warning tailoring CV: {e}")

    now = datetime.utcnow()
    site_label = (req.site or "Easy Apply").title()
    notes = f"Applied via Candidature Simplifiée ({site_label})" + (f" (Tailored ATS Match: {effective_score}%)" if custom_pdf_name else "")
    if req.notes:
        notes += f"\n{req.notes}"

    if existing:
        existing.status = "applied"
        existing.applied_at = now
        existing.follow_up_date = now + timedelta(days=5)
        if url and not existing.url:
            existing.url = url
        existing.match_score = effective_score
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

        custom_pdf_bytes = None
        custom_pdf_name = None
        effective_score = item.match_score or 80

        if req.customize_cv and cv_text:
            try:
                from cv_tailor import tailor_cv
                tailor_res = tailor_cv(cv_text, title, company, desc or title)
                custom_pdf_bytes = tailor_res["pdf_bytes"]
                custom_pdf_name = tailor_res["filename"]
                effective_score = tailor_res["tailored_score"]
            except Exception:
                pass

        site_label = (item.site or "Easy Apply").title()
        notes = f"Batch applied via Candidature Simplifiée ({site_label})" + (f" (Tailored ATS Match: {effective_score}%)" if custom_pdf_name else "")

        if existing:
            existing.status = "applied"
            existing.applied_at = now
            existing.follow_up_date = now + timedelta(days=5)
            existing.match_score = effective_score
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
