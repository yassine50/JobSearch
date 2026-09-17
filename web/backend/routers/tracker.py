
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/tracker", tags=["tracker"])
VALID_STATUSES = ["applied","interview","offer","rejected","accepted"]

class AppCreate(BaseModel):
    title: str; company: str = ""; location: str = ""
    url: str = ""; match_score: int = 0; notes: str = ""
    status: str = "applied"; recruiter_email: str = ""

class AppUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None

def _serialize(a, emails=None):
    return {
        "id": a.id, "title": a.title, "company": a.company,
        "location": a.location, "url": a.url, "status": a.status,
        "notes": a.notes or "", "match_score": a.match_score,
        "applied_at": str(a.applied_at),
        "follow_up_date": str(a.follow_up_date) if a.follow_up_date else None,
        "emails": emails or []
    }

@router.get("")
def get_all(db: Session = Depends(get_db),
            current_user: models.User = Depends(get_current_user)):
    apps = db.query(models.Application)             .filter(models.Application.user_id == current_user.id)             .order_by(models.Application.applied_at.desc()).all()
    result = []
    for a in apps:
        logs = db.query(models.EmailLog)                 .filter(models.EmailLog.application_id == a.id)                 .order_by(models.EmailLog.sent_at.desc()).all()
        email_list = [{"id": l.id, "to_email": l.to_email, "subject": l.subject,
                       "status": l.status, "sent_at": str(l.sent_at)} for l in logs]
        result.append(_serialize(a, email_list))
    return result

@router.post("")
def create_app(req: AppCreate, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    a = models.Application(
        user_id=current_user.id, title=req.title, company=req.company,
        location=req.location, url=req.url, match_score=req.match_score,
        notes=req.notes, status=req.status)
    db.add(a); db.commit(); db.refresh(a)
    return _serialize(a)

@router.patch("/{app_id}")
def update_app(app_id: int, req: AppUpdate,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    a = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == current_user.id).first()
    if not a: raise HTTPException(404, "Not found")
    if req.status and req.status in VALID_STATUSES: a.status = req.status
    if req.notes is not None: a.notes = req.notes
    if req.follow_up_date:
        try: a.follow_up_date = datetime.fromisoformat(req.follow_up_date)
        except: pass
    db.commit()
    logs = db.query(models.EmailLog).filter(models.EmailLog.application_id == a.id).all()
    email_list = [{"id": l.id, "to_email": l.to_email, "subject": l.subject,
                   "status": l.status, "sent_at": str(l.sent_at)} for l in logs]
    return _serialize(a, email_list)

@router.delete("/{app_id}")
def delete_app(app_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    a = db.query(models.Application).filter(
        models.Application.id == app_id,
        models.Application.user_id == current_user.id).first()
    if not a: raise HTTPException(404, "Not found")
    db.delete(a); db.commit()
    return {"message": "Deleted"}

@router.get("/stats")
def stats(db: Session = Depends(get_db),
          current_user: models.User = Depends(get_current_user)):
    from sqlalchemy import func
    rows = db.query(models.Application.status, func.count(models.Application.id))             .filter(models.Application.user_id == current_user.id)             .group_by(models.Application.status).all()
    return {s: c for s, c in rows}
