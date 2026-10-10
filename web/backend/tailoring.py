"""
Per-job honest CV tailoring for user-clicked sends (Auto-Apply, Batch Auto-Apply,
Easy Apply, Batch Easy Apply).

Rules:
  • Full-match mode (user opted in): adds every missing job skill, removes off-topic content,
    targets the exact role title (see cv_tailor.tailor_cv_full_match).
  • The stored original CV (CvUpload.file_data) is never modified.
  • Falls back to the original CV on any error or a too-short job description.
  • The automatic dispatcher and follow-ups do NOT call this — follow-ups reuse the CV
    that was sent first (Application.tailored_cv_data).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger(__name__)

MIN_JD_CHARS = 150


def honest_tailored_attachment(cv, job_title: str, company: str, job_description: str):
    """Return (pdf_bytes, filename, original_score, tailored_score) or (None, None, None, None)."""
    if not cv or not (cv.text_content or "").strip():
        return None, None, None, None
    jd = (job_description or "").strip()
    if len(jd) < MIN_JD_CHARS:
        return None, None, None, None
    try:
        from cv_tailor import tailor_cv_full_match
        r = tailor_cv_full_match(cv.text_content, job_title or "", company or "", jd,
                             cv_pdf_bytes=getattr(cv, "file_data", None))
        if not r.get("use_tailored") or not r.get("pdf_bytes"):
            return None, None, r.get("original_score"), None
        return r["pdf_bytes"], r["filename"], r["original_score"], r["tailored_score"]
    except Exception as e:  # never block an application because tailoring failed
        logger.warning("Honest CV tailoring failed for %s @ %s: %s", job_title, company, e)
        return None, None, None, None
