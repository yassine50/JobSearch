
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


# ─── CV Smart Analyzer ────────────────────────────────────────────────────────
import re as _re

_TECH_SKILLS = [
    "Flutter","Dart","React","React Native","Vue","Angular","Next.js","TypeScript","JavaScript",
    "Python","FastAPI","Django","Node.js","Express","Java","Kotlin","Swift","iOS","Android",
    "SQL","PostgreSQL","MySQL","MongoDB","Redis","Firebase","AWS","GCP","Azure","Docker",
    "Kubernetes","Git","CI/CD","REST","GraphQL","Bloc","GetX","Provider","Riverpod",
    "TailwindCSS","Material UI","Figma","Agile","Scrum","DevOps","Machine Learning",
    "Data Science","TensorFlow","PyTorch","Spring Boot","Ruby","PHP","Laravel","Go","Rust",
    "C++","C#","Unity","Unreal","WordPress","Shopify","Salesforce","SAP"
]

_COUNTRIES = [
    "USA","UK","France","Germany","Canada","Australia","Netherlands","Spain","Belgium",
    "Switzerland","Ireland","Sweden","Denmark","Norway","UAE","Singapore","Poland",
    "Romania","Morocco","Tunisia","Saudi Arabia","Qatar","Brazil","India","Remote"
]

_LOC_PATTERN = _re.compile(
    r'\b(London|Paris|Berlin|Amsterdam|Madrid|Barcelona|Dubai|Remote|New York|San Francisco|'
    r'Toronto|Sydney|Singapore|Bucharest|Romania|Morocco|France|Germany|UK|USA|UAE|Canada|'
    r'Saudi Arabia|Netherlands|Spain|Australia|Switzerland|Belgium|Ireland|Stockholm|Copenhagen|'
    r'Warsaw|Casablanca|Rabat|Tunis|Riyadh|Doha|Lagos|Cape Town)\b', _re.I
)

def _analyze_cv_text(text: str) -> dict:
    # 1. Job title — look at first 10 non-empty lines for a title-like line
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    primary_title = ""
    alt_titles = []
    TITLE_RE = _re.compile(
        r'\b(Developer|Engineer|Designer|Manager|Analyst|Architect|Lead|Consultant|'
        r'Specialist|Expert|Director|Scientist|Administrator|Coordinator|Officer|'
        r'Full.?Stack|Front.?End|Back.?End|Mobile|DevOps|Data|AI|ML|Product|QA|SRE)\b',
        _re.I
    )
    for line in lines[:12]:
        if TITLE_RE.search(line) and 3 < len(line) < 70 and not any(c in line for c in ['@','•','+','http']):
            if not primary_title:
                primary_title = line
            elif line not in alt_titles:
                alt_titles.append(line)

    # Fallback: grep for role patterns deeper in text
    if not primary_title:
        for pat in [r'Role[:\s]+(.{5,50})', r'Position[:\s]+(.{5,50})', r'Job Title[:\s]+(.{5,50})']:
            m = _re.search(pat, text, _re.I)
            if m:
                primary_title = m.group(1).strip(); break

    # 2. Skills
    found_skills = [s for s in _TECH_SKILLS
                    if _re.search(r'\b' + _re.escape(s) + r'\b', text, _re.I)]

    # 3. Location / Country from CV text
    found_locs = list(dict.fromkeys(m.group(1) for m in _LOC_PATTERN.finditer(text)))

    # Map locations to searchable countries
    LOC_COUNTRY_MAP = {
        "London":"UK","Paris":"France","Berlin":"Germany","Amsterdam":"Netherlands",
        "Madrid":"Spain","Barcelona":"Spain","Dubai":"UAE","Bucharest":"Romania",
        "Toronto":"Canada","Sydney":"Australia","Singapore":"Singapore","Warsaw":"Poland",
        "Casablanca":"Morocco","Rabat":"Morocco","Tunis":"Tunisia","Riyadh":"Saudi Arabia",
        "Doha":"Qatar","Stockholm":"Sweden","Copenhagen":"Denmark","Cape Town":"South Africa",
    }
    suggested_countries = []
    for loc in found_locs:
        mapped = LOC_COUNTRY_MAP.get(loc, loc)
        if mapped not in suggested_countries:
            suggested_countries.append(mapped)

    # 4. Experience years & remote preference
    exp_matches = _re.findall(r'(\d+)\+?\s*(?:years?|ans?)\s*(?:of)?\s*(?:experience|exp)?', text, _re.I)
    years_exp = max((int(x) for x in exp_matches if int(x) < 40), default=0)
    has_remote_pref = bool(_re.search(r'\b(remote|telecommute|work from home|full.?remote)\b', text, _re.I))

    # 5. Search keywords — optimize for highest job board search yield
    clean_title = primary_title.strip()
    # Normalize overly specific titles to high-volume equivalents
    if _re.search(r'flutter.*mobile.*developer', clean_title, _re.I):
        search_query = "Flutter Developer"
    elif _re.search(r'react.*native.*mobile', clean_title, _re.I):
        search_query = "React Native Developer"
    elif _re.search(r'full.?stack.*developer', clean_title, _re.I) and top_skills:
        search_query = f"Full Stack {top_skills[0]} Developer" if top_skills[0] in ["Java", "Python", "React", "Node.js"] else "Full Stack Developer"
    elif clean_title:
        search_query = clean_title
    elif top_skills:
        search_query = f"{top_skills[0]} Developer"
    else:
        search_query = "Software Developer"

    top_skills = found_skills[:6]

    return {
        "title":            search_query,
        "primary_title":    primary_title,
        "alt_titles":       alt_titles[:4],
        "skills":           found_skills[:20],
        "top_skills":       top_skills,
        "locations_found":  found_locs[:6],
        "suggested_countries": suggested_countries[:5],
        "years_experience": years_exp,
        "is_remote":        has_remote_pref,
        "search_query":     search_query,
    }

@router.get("/analyze")
def analyze_cv(db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """Analyze stored CV and return structured data to auto-fill the search form."""
    cv = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).first()
    if not cv or not cv.text_content:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    result = _analyze_cv_text(cv.text_content)
    return result
