"""
Per-job honest CV tailoring for user-clicked sends (Auto-Apply, Batch Auto-Apply,
Easy Apply, Batch Easy Apply).

Rules:
  • Full-match mode (user opted in): adds every missing job skill, removes off-topic content,
    targets the exact role title (see cv_tailor.tailor_cv_full_match).
  • The stored original CV (CvUpload.file_data) is never modified.
  • Falls back to the original CV on any error or a too-short job description.
  • If the user reviewed/corrected the extracted CV (CvUpload.parsed_json), tailoring runs on that
    verified structure instead of re-parsing the file.
  • Automatic sends never attach a tailored CV built from a LOW-confidence extraction that the user
    has not reviewed — the original file is sent instead (no silently thin CVs).
  • The automatic dispatcher and follow-ups do NOT call this — follow-ups reuse the CV
    that was sent first (Application.tailored_cv_data).
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger(__name__)

MIN_JD_CHARS = 30


def reviewed_cv_dict(cv):
    """The user-reviewed structured CV for this upload, or None."""
    raw = getattr(cv, "parsed_json", None)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def extract_cv_structure(cv):
    """(structured_cv_dict, extraction_quality) for the stored CV — reviewed version wins."""
    from cv_engine.quality import assess_extraction, cv_from_dict
    reviewed = reviewed_cv_dict(cv)
    if reviewed:
        q = assess_extraction(None, cv_from_dict(reviewed))
        q.update({"reviewed": True, "level": "high", "score": max(q["score"], 90)})
        return reviewed, q
    from cv_engine.tailor import extract_structured_cv
    parsed, quality = extract_structured_cv(
        cv_text=cv.text_content or "",
        cv_pdf_bytes=getattr(cv, "file_data", None),
        filename=getattr(cv, "filename", "cv.pdf") or "cv.pdf",
    )
    return parsed.to_dict(), quality


def tailor_cv_detailed(cv, job_title: str, company: str, job_description: str):
    """Return full tailoring dictionary including cv_profile, tips, matched_skills, and pdf_bytes."""
    if not cv or not (cv.text_content or "").strip():
        return None
    jd = (job_description or job_title or "").strip()
    try:
        from cv_tailor import tailor_cv_full_match
        return tailor_cv_full_match(
            cv.text_content,
            job_title or "",
            company or "",
            jd,
            cv_pdf_bytes=getattr(cv, "file_data", None),
            filename=getattr(cv, "filename", "cv.pdf") or "cv.pdf",
            cv_override=reviewed_cv_dict(cv),
        )
    except Exception as e:
        logger.warning("CV tailoring failed for %s @ %s: %s", job_title, company, e)
        return None


def honest_tailored_attachment(cv, job_title: str, company: str, job_description: str, allow_low_confidence: bool = False):
    """Return (pdf_bytes, filename, original_score, tailored_score) or (None, None, None, None).

    `allow_low_confidence=True` is only used for an explicit user download from the review modal.
    """
    if not cv or not (cv.text_content or "").strip():
        return None, None, None, None
    jd = (job_description or job_title or "").strip()
    if len(jd) < MIN_JD_CHARS:
        jd = f"{job_title or 'Software Engineer'} at {company or 'Company'}. {jd}".strip()
    r = tailor_cv_detailed(cv, job_title, company, jd)
    if not r or not r.get("use_tailored") or not r.get("pdf_bytes"):
        return None, None, (r.get("original_score") if r else None), None
    q = r.get("extraction_quality") or {}
    if not allow_low_confidence and q.get("level") == "low" and not q.get("reviewed"):
        logger.info("Skipping tailored CV for %s @ %s: low extraction confidence (%s)", job_title, company, q.get("score"))
        return None, None, r.get("original_score"), None
    return r["pdf_bytes"], r["filename"], r["original_score"], r["tailored_score"]
