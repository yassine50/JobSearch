
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

class SearchRequest(BaseModel):
    title: str
    location: str = ""
    country: str = "USA"
    sites: List[str] = ["linkedin", "indeed"]
    results_wanted: int = 20
    hours_old: int = 168

class SaveJobRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    match_score: int = 0

@router.post("/search")
def search_jobs(req: SearchRequest, current_user: models.User = Depends(get_current_user)):
    try:
        from jobspy import scrape_jobs
        df = scrape_jobs(
            site_name=req.sites,
            search_term=req.title,
            location=req.location,
            results_wanted=req.results_wanted,
            hours_old=req.hours_old,
            country_indeed=req.country,
        )
        if df is None or df.empty:
            return {"jobs": [], "total": 0}
        df = df.fillna("")
        jobs = []
        for _, row in df.iterrows():
            salary = ""
            if row.get("min_amount"): salary = f"${int(row['min_amount']):,}"
            if row.get("max_amount"): salary += f" – ${int(row['max_amount']):,}"
            jobs.append({
                "title": str(row.get("title", "")),
                "company": str(row.get("company", "")),
                "location": str(row.get("location", "")),
                "url": str(row.get("job_url", "")),
                "description": str(row.get("description", ""))[:600],
                "site": str(row.get("site", "")),
                "date_posted": str(row.get("date_posted", "")),
                "salary": salary,
            })
        return {"jobs": jobs, "total": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save")
def save_job(req: SaveJobRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = models.SavedJob(user_id=current_user.id, title=req.title, company=req.company,
                          location=req.location, url=req.url, description=req.description, match_score=req.match_score)
    db.add(job); db.commit(); db.refresh(job)
    return {"message": "Saved", "id": job.id}

@router.get("/saved")
def get_saved(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    jobs = db.query(models.SavedJob).filter(models.SavedJob.user_id == current_user.id)             .order_by(models.SavedJob.saved_at.desc()).all()
    return [{"id": j.id, "title": j.title, "company": j.company, "location": j.location,
             "url": j.url, "match_score": j.match_score, "saved_at": str(j.saved_at)} for j in jobs]

@router.delete("/saved/{job_id}")
def delete_saved(job_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    job = db.query(models.SavedJob).filter(models.SavedJob.id == job_id,
                                           models.SavedJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(job); db.commit()
    return {"message": "Deleted"}
