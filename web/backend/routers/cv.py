from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from .. import models
from ..database import get_db
from ..auth import get_current_user
from ..utils import ensure_project_root_on_path
import io, os
import re as _re

ensure_project_root_on_path()
router = APIRouter(prefix="/api/cv", tags=["cv"])


def _get_active_cv(db: Session, user_id: int):
    active = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id, models.CvUpload.is_active == True)
        .order_by(models.CvUpload.uploaded_at.desc())
        .first()
    )
    if active:
        return active
    return (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id)
        .order_by(models.CvUpload.uploaded_at.desc())
        .first()
    )


class MatchRequest(BaseModel):
    job_description: str
    job_title: str = ""
    cv_text: Optional[str] = None


class BatchMatchItem(BaseModel):
    title: str = ""
    description: str = ""
    url: Optional[str] = ""


class BatchMatchRequest(BaseModel):
    jobs: List[BatchMatchItem]


def _parse(filename, content):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".txt", ".pdf", ".docx"):
        raise HTTPException(400, f"Unsupported: {ext}")
    try:
        from cv_engine.extract import extract_document
        doc = extract_document(content, filename=filename)
        if doc.text and doc.text.strip():
            return doc.text
    except Exception:
        pass
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
async def upload_cv(
    file: UploadFile = File(...),
    persona_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    if not file.filename:
        raise HTTPException(400, "Missing file name")
    text = _parse(file.filename, content)
    if not text.strip():
        raise HTTPException(400, "No text found in file")

    active_cv = _get_active_cv(db, current_user.id)
    if active_cv and not persona_name:
        db.query(models.CvUpload).filter(
            models.CvUpload.user_id == current_user.id,
            models.CvUpload.id != active_cv.id,
        ).update({"is_active": False})
        active_cv.filename = file.filename
        active_cv.text_content = text
        active_cv.file_data = content
        active_cv.parsed_json = None   # new file → previous review no longer applies
        active_cv.is_active = True
        db.commit()
        return {
            "message": "CV uploaded",
            "id": active_cv.id,
            "persona_name": active_cv.persona_name or "Primary Resume",
            "words": len(text.split()),
            "filename": file.filename,
        }
    else:
        db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).update({"is_active": False})
        analysis = _analyze_cv_text(text)
        inferred_persona = (persona_name or "").strip() or analysis.get("title") or "Primary Resume"
        cv = models.CvUpload(
            user_id=current_user.id,
            persona_name=inferred_persona,
            is_active=True,
            filename=file.filename,
            text_content=text,
            file_data=content,
        )
        db.add(cv)
        db.commit()
        db.refresh(cv)
        return {
            "message": "CV uploaded",
            "id": cv.id,
            "persona_name": cv.persona_name,
            "words": len(text.split()),
            "filename": file.filename,
        }


# ─── Multi-CV Personas Vault Endpoints ───────────────────────────────────────

@router.get("/personas")
def list_cv_personas(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cvs = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == current_user.id)
        .order_by(models.CvUpload.is_active.desc(), models.CvUpload.uploaded_at.desc())
        .all()
    )
    out = []
    for c in cvs:
        info = _analyze_cv_text(c.text_content or "")
        out.append({
            "id": c.id,
            "persona_name": c.persona_name or info.get("title") or "Primary Resume",
            "filename": c.filename,
            "is_active": bool(c.is_active),
            "words": len((c.text_content or "").split()),
            "top_skills": info.get("top_skills", [])[:6],
            "detected_role": info.get("title", "Software Developer"),
            "uploaded_at": str(c.uploaded_at),
        })
    return {"personas": out}


@router.post("/personas")
async def create_cv_persona(
    file: UploadFile = File(...),
    persona_name: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    if not file.filename:
        raise HTTPException(400, "Missing file name")
    text = _parse(file.filename, content)
    if not text.strip():
        raise HTTPException(400, "No text found in file")

    db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).update({"is_active": False})
    analysis = _analyze_cv_text(text)
    label = persona_name.strip() or analysis.get("title") or os.path.splitext(file.filename)[0]

    cv = models.CvUpload(
        user_id=current_user.id,
        persona_name=label,
        is_active=True,
        filename=file.filename,
        text_content=text,
        file_data=content,
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return {
        "id": cv.id,
        "persona_name": cv.persona_name,
        "filename": cv.filename,
        "is_active": True,
        "words": len(text.split()),
        "top_skills": analysis.get("top_skills", [])[:6],
    }


@router.post("/personas/{cv_id}/activate")
def activate_cv_persona(
    cv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    target = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.id == cv_id, models.CvUpload.user_id == current_user.id)
        .first()
    )
    if not target:
        raise HTTPException(404, "CV Persona not found")

    db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).update({"is_active": False})
    target.is_active = True
    db.commit()
    return {
        "message": f"Activated '{target.persona_name or target.filename}'",
        "id": target.id,
        "persona_name": target.persona_name,
        "filename": target.filename,
    }


@router.delete("/personas/{cv_id}")
def delete_cv_persona(
    cv_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    target = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.id == cv_id, models.CvUpload.user_id == current_user.id)
        .first()
    )
    if not target:
        raise HTTPException(404, "CV Persona not found")

    was_active = bool(target.is_active)
    db.delete(target)
    db.commit()

    if was_active:
        fallback = (
            db.query(models.CvUpload)
            .filter(models.CvUpload.user_id == current_user.id)
            .order_by(models.CvUpload.uploaded_at.desc())
            .first()
        )
        if fallback:
            fallback.is_active = True
            db.commit()

    return {"message": "Persona deleted"}


class BestPersonaRequest(BaseModel):
    job_title: str = ""
    job_description: str = ""


@router.post("/best-persona")
def find_best_cv_persona(
    req: BestPersonaRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cvs = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).all()
    if not cvs:
        raise HTTPException(400, "No CVs uploaded yet")
    try:
        from cv_matcher import compute_match
        ranked = []
        for c in cvs:
            score, bd = compute_match(c.text_content or "", req.job_description, req.job_title)
            ranked.append({
                "id": c.id,
                "persona_name": c.persona_name or c.filename,
                "filename": c.filename,
                "is_active": bool(c.is_active),
                "score": score,
                "matched_skills": bd.get("matched_tech", [])[:8],
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return {"best": ranked[0] if ranked else None, "ranked": ranked}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/match")
def match_cv(req: MatchRequest, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    cv_text = req.cv_text
    if not cv_text:
        rec = _get_active_cv(db, current_user.id)
        if not rec:
            raise HTTPException(400, "No CV uploaded. Upload your CV first.")
        cv_text = rec.text_content
    try:
        from cv_matcher import compute_match
        score, bd = compute_match(cv_text, req.job_description, req.job_title)
        return {"score": score, "breakdown": bd}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/match-batch")
def match_cv_batch(req: BatchMatchRequest, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    rec = _get_active_cv(db, current_user.id)
    if not rec or not rec.text_content:
        raise HTTPException(400, "No CV uploaded. Upload your CV first.")
    try:
        from cv_matcher import compute_match
        from concurrent.futures import ThreadPoolExecutor

        cv_text = rec.text_content

        def score_item(item: BatchMatchItem):
            s, bd = compute_match(cv_text, item.description, item.title)
            return {
                "url": item.url,
                "title": item.title,
                "score": s,
                "breakdown": bd,
                "matched_skills": bd.get("matched_tech", []),
                "missing_skills": bd.get("missing_tech", []),
                "tips": bd.get("tips", []),
            }

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(score_item, req.jobs))

        return results
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/info")
def cv_info(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cv = _get_active_cv(db, current_user.id)
    total_personas = db.query(models.CvUpload).filter(models.CvUpload.user_id == current_user.id).count()
    if not cv:
        return {"uploaded": False, "personas_count": 0}
    return {
        "uploaded": True,
        "id": cv.id,
        "persona_name": cv.persona_name or "Primary Resume",
        "filename": cv.filename,
        "words": len((cv.text_content or "").split()),
        "uploaded_at": str(cv.uploaded_at),
        "personas_count": total_personas,
    }


# ─── CV Smart Analyzer ────────────────────────────────────────────────────────

_TECH_SKILLS = [
    "Flutter","Dart","React","React Native","Vue","Angular","Next.js","TypeScript","JavaScript",
    "Python","FastAPI","Django","Node.js","Express","Java","Kotlin","Swift","iOS","Android",
    "SQL","PostgreSQL","MySQL","MongoDB","Redis","Firebase","AWS","GCP","Azure","Docker",
    "Kubernetes","Git","CI/CD","REST","GraphQL","Bloc","GetX","Provider","Riverpod",
    "TailwindCSS","Material UI","Figma","Agile","Scrum","DevOps","Machine Learning",
    "Data Science","TensorFlow","PyTorch","Spring Boot","Ruby","PHP","Laravel","Go","Rust",
    "C++","C#","Unity","Unreal","WordPress","Shopify","Salesforce","SAP"
]

_LOC_PATTERN = _re.compile(
    r'\b(London|Paris|Berlin|Amsterdam|Madrid|Barcelona|Dubai|Remote|New York|San Francisco|'
    r'Toronto|Sydney|Singapore|Bucharest|Romania|Morocco|France|Germany|UK|USA|UAE|Canada|'
    r'Saudi Arabia|Netherlands|Spain|Australia|Switzerland|Belgium|Ireland|Stockholm|Copenhagen|'
    r'Warsaw|Casablanca|Rabat|Tunis|Riyadh|Doha|Lagos|Cape Town)\b', _re.I
)


def _analyze_cv_text(text: str) -> dict:
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

    if not primary_title:
        for pat in [r'Role[:\s]+(.{5,50})', r'Position[:\s]+(.{5,50})', r'Job Title[:\s]+(.{5,50})']:
            m = _re.search(pat, text, _re.I)
            if m:
                primary_title = m.group(1).strip(); break

    found_skills = [s for s in _TECH_SKILLS
                    if _re.search(r'\b' + _re.escape(s) + r'\b', text, _re.I)]
    top_skills = found_skills[:6]

    found_locs = list(dict.fromkeys(m.group(1) for m in _LOC_PATTERN.finditer(text)))

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

    exp_matches = _re.findall(r'(\d+)\+?\s*(?:years?|ans?)\s*(?:of)?\s*(?:experience|exp)?', text, _re.I)
    years_exp = max((int(x) for x in exp_matches if int(x) < 40), default=0)
    has_remote_pref = bool(_re.search(r'\b(remote|telecommute|work from home|full.?remote)\b', text, _re.I))

    clean_title = primary_title.strip()
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
    cv = _get_active_cv(db, current_user.id)
    if not cv or not cv.text_content:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    result = _analyze_cv_text(cv.text_content)
    return result


class TailorCvRequest(BaseModel):
    job_title: str
    company: str
    job_description: str


@router.post("/tailor")
def tailor_user_cv(req: TailorCvRequest,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Analyzes the CV type & structure first, then returns tailored preview, scores, and adjustments."""
    import base64
    cv = _get_active_cv(db, current_user.id)
    if not cv or not cv.text_content:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    try:
        from web.backend.tailoring import tailor_cv_detailed
        r = tailor_cv_detailed(cv, req.job_title, req.company, req.job_description)
        if not r:
            raise HTTPException(500, "Could not analyze and tailor CV.")
        pdf_bytes = r.get("pdf_bytes")
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else None
        return {
            "original_score": r.get("original_score", 0),
            "tailored_score": r.get("tailored_score", 0),
            "matched_skills": r.get("matched_skills", []),
            "bridged_skills": r.get("bridged_skills", []),
            "target_headline": r.get("target_headline", req.job_title),
            "tailored_summary": r.get("tailored_summary", ""),
            "cv_profile": r.get("cv_profile", {}),
            "diagnosis": r.get("diagnosis", {}),
            "tips": r.get("tips", []),
            "filename": r.get("filename", "Tailored_CV.pdf"),
            "tailored_text": r.get("tailored_text", ""),
            "extraction_quality": r.get("extraction_quality", {}),
            "score_breakdown": r.get("score_breakdown", {}),
            "core_competencies": r.get("core_competencies", []),
            "pdf_base64": pdf_b64,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── Review-before-download: inspect & correct what was extracted from the CV file ───

class ParsedCvPayload(BaseModel):
    cv: dict


@router.get("/parsed")
def get_parsed_cv(db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    """Structured CV the tailoring engine will use + extraction confidence (reviewed version wins)."""
    cv = _get_active_cv(db, current_user.id)
    if not cv or not cv.text_content:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    try:
        from web.backend.tailoring import extract_cv_structure
        structured, quality = extract_cv_structure(cv)
        return {"cv": structured, "quality": quality, "filename": cv.filename}
    except Exception as e:
        raise HTTPException(500, f"Could not read CV structure: {e}")


@router.put("/parsed")
def save_parsed_cv(payload: ParsedCvPayload,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    """Save the user's corrections; all future tailoring uses this verified structure."""
    import json
    cv = _get_active_cv(db, current_user.id)
    if not cv:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    from cv_engine.quality import cv_from_dict, assess_extraction
    normalized = cv_from_dict(payload.cv)
    if not normalized.name or not (normalized.experience or normalized.projects or normalized.education):
        raise HTTPException(400, "Please keep at least your name and one experience, project or education entry.")
    data = normalized.to_dict()
    data["meta"] = {**(payload.cv.get("meta") or {}), "reviewed": True}
    cv.parsed_json = json.dumps(data, ensure_ascii=False)
    db.commit()
    q = assess_extraction(None, normalized)
    q.update({"reviewed": True, "level": "high", "score": max(q["score"], 90)})
    return {"cv": data, "quality": q, "message": "Reviewed CV saved"}


@router.delete("/parsed")
def reset_parsed_cv(db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    """Discard the reviewed version and go back to automatic extraction."""
    cv = _get_active_cv(db, current_user.id)
    if not cv:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    cv.parsed_json = None
    db.commit()
    from web.backend.tailoring import extract_cv_structure
    structured, quality = extract_cv_structure(cv)
    return {"cv": structured, "quality": quality, "message": "Reset to automatic extraction"}


@router.post("/tailored-pdf")
def download_tailored_pdf(req: TailorCvRequest,
                          db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    """Generates and downloads the ATS-optimised tailored PDF using full-match mode."""
    from fastapi.responses import Response
    cv = _get_active_cv(db, current_user.id)
    if not cv or not cv.text_content:
        raise HTTPException(400, "No CV uploaded. Please upload your CV first.")
    try:
        from web.backend.tailoring import honest_tailored_attachment
        pdf_bytes, filename, original_score, tailored_score = honest_tailored_attachment(
            cv, req.job_title, req.company, req.job_description, allow_low_confidence=True
        )
        if not pdf_bytes:
            raise HTTPException(500, "PDF generation failed — no output returned.")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
