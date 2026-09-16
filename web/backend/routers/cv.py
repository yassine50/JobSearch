
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .. import models
from ..database import get_db
from ..auth import get_current_user
import io, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
router = APIRouter(prefix="/api/cv", tags=["cv"])

class MatchRequest(BaseModel):
    job_description: str
    job_title: str = ""
    cv_text: Optional[str] = None

def _parse(filename, content):
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".txt":
        return content.decode("utf-8", errors="ignore")
    elif ext == ".pdf":
        try:
            import PyPDF2
            r = PyPDF2.PdfReader(io.BytesIO(content))
            return "\n".join(p.extract_text() or "" for p in r.pages)
        except Exception as e:
            raise HTTPException(400, f"PDF error: {e}")
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(400, f"DOCX error: {e}")
    raise HTTPException(400, f"Unsupported: {ext}")

@router.post("/upload")
async def upload_cv(file: UploadFile = File(...), db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    content = await file.read()
    text = _parse(file.filename, content)
    if not text.strip():
        raise HTTPException(400, "No text found in file")
    existing = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    if existing:
        existing.filename = file.filename
        existing.text_content = text
        db.commit()
    else:
        cv = models.CvUpload(user_id=current_user.id, filename=file.filename, text_content=text)
        db.add(cv); db.commit()
    return {"message": "CV uploaded", "words": len(text.split()), "filename": file.filename}

@router.post("/match")
def match_cv(req: MatchRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    cv_text = req.cv_text
    if not cv_text:
        rec = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
        if not rec:
            raise HTTPException(400, "No CV uploaded. Upload your CV first.")
        cv_text = rec.text_content
    try:
        from cv_matcher import compute_match
        score, bd = compute_match(cv_text, req.job_description, req.job_title)
        return {"score": score, "breakdown": bd}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/info")
def cv_info(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    if not cv:
        return {"uploaded": False}
    return {"uploaded": True, "filename": cv.filename, "words": len(cv.text_content.split()),
            "uploaded_at": str(cv.uploaded_at)}
