
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import re, urllib.parse, urllib.request
from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,10}",
    re.IGNORECASE
)
SKIP_PATTERNS = {"example","sentry","wixpress","amazonaws","cloudfront","noreply",
                 "no-reply","placeholder","test@","sample","youremail","@email.com",
                 "@domain.com","privacy@","legal@","support@sentry"}
SKIP_EXTS = {".png",".jpg",".jpeg",".gif",".svg",".webp",".css",".js"}
HR_PREFIXES = ["careers","jobs","hr","recruit","hiring","talent","apply","recruitment","people","work"]
JOB_BOARDS  = {"linkedin.com","indeed.com","glassdoor.com","ziprecruiter.com","monster.com",
               "dice.com","greenhouse.io","lever.co","workday.com","myworkdayjobs.com",
               "taleo.net","icims.com","jobvite.com","wellfound.com","remoteok.com"}

def _clean_email(e):
    e = e.strip().lower()
    if any(s in e for s in SKIP_PATTERNS): return None
    if any(e.endswith(x) for x in SKIP_EXTS): return None
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

class SearchRequest(BaseModel):
    title: str
    location: str = ""
    country: str = "USA"
    sites: List[str] = ["linkedin","indeed"]
    results_wanted: int = 20
    hours_old: int = 168

class ImportUrlRequest(BaseModel):
    url: str

class SaveJobRequest(BaseModel):
    title: str; company: str=""; location: str=""
    url: str=""; description: str=""; match_score: int=0

@router.post("/search")
def search_jobs(req: SearchRequest,
                current_user: models.User = Depends(get_current_user)):
    # Filter to only supported jobspy sites
    SUPPORTED = {"linkedin","indeed","glassdoor","zip_recruiter","google"}
    valid_sites = [s for s in req.sites if s in SUPPORTED] or ["linkedin","indeed"]
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(site_name=valid_sites, search_term=req.title,
                         location=req.location, results_wanted=req.results_wanted,
                         hours_old=req.hours_old, country_indeed=req.country)
        if df is None or df.empty: return {"jobs":[],"total":0}
        df = df.fillna("")
        jobs = []
        for _,row in df.iterrows():
            desc    = str(row.get("description",""))
            job_url = str(row.get("job_url",""))
            company = str(row.get("company",""))
            salary  = ""
            if row.get("min_amount"): salary = f"${int(float(row['min_amount'])):,}"
            if row.get("max_amount"): salary += f"–${int(float(row['max_amount'])):,}"
            extracted = _extract_emails_from_text(desc)
            if row.get("emails"):
                for e in str(row["emails"]).replace(";",",").split(","):
                    c = _clean_email(e.strip())
                    if c and c not in extracted: extracted.append(c)
            domain   = _domain_from_url(job_url)
            inferred = _infer_hr_emails(domain)
            jobs.append({
                "title":str(row.get("title","")), "company":company,
                "location":str(row.get("location","")), "url":job_url,
                "description":desc[:800], "site":str(row.get("site","")),
                "date_posted":str(row.get("date_posted","")), "salary":salary,
                "emails":_best_emails(extracted,inferred),
                "company_domain":domain, "imported":False,
            })
        return {"jobs":jobs,"total":len(jobs)}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/import-url")
def import_from_url(req: ImportUrlRequest,
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
        from curl_cffi import requests as c_requests
        
        # curl_cffi impersonates a real browser (Chrome) to bypass 403 Forbidden / Cloudflare
        resp = c_requests.get(
            req.url, 
            impersonate="chrome", 
            timeout=15, 
            headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.reason}")
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

        domain   = _domain_from_url(req.url)
        extracted = _extract_emails_from_text(text)
        inferred  = _infer_hr_emails(domain)

        return {
            "title":    title[:120] or "Imported Job",
            "company":  company[:80] or domain,
            "location": "",
            "url":      req.url,
            "description": text[:800],
            "site":     "custom",
            "date_posted": "",
            "salary":   "",
            "emails":   _best_emails(extracted, inferred),
            "company_domain": domain,
            "imported": True,
        }
    except Exception as e:
        raise HTTPException(400, f"Could not import URL: {str(e)}")

@router.post("/save")
def save_job(req: SaveJobRequest, db: Session=Depends(get_db),
             current_user: models.User=Depends(get_current_user)):
    job = models.SavedJob(user_id=current_user.id, title=req.title,
        company=req.company, location=req.location, url=req.url,
        description=req.description, match_score=req.match_score)
    db.add(job); db.commit(); db.refresh(job)
    return {"message":"Saved","id":job.id}

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
