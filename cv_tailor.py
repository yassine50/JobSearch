"""
cv_tailor.py — Public CV Tailoring Facade delegating to the Senior CV Engine (`cv_engine`).

Provides `tailor_cv_full_match` and `tailor_cv_honest` entrypoints for backend services.
"""

from __future__ import annotations

from typing import Dict, Optional


def tailor_cv_honest(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
    filename: str = "cv.pdf",
    cv_override: Optional[Dict] = None,
) -> Dict:
    """
    Runs the Senior CV Engine in Honest Mode:
    1. Layout-aware extraction & structure parsing (`cv_engine.extract` + `cv_engine.parse`)
    2. Pre-tailoring diagnosis (`cv_engine.analyze.diagnose`)
    3. Honest mechanical enhancement (`cv_engine.enhance`)
    4. Re-orders skills, experience bullets, and projects by relevance to the target job
    5. Renders a clean single-column A4 executive PDF (`cv_engine.render.render_cv_pdf`)
    """
    from cv_engine.tailor import tailor_cv_pipeline
    return tailor_cv_pipeline(
        cv_text=cv_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        cv_pdf_bytes=cv_pdf_bytes,
        mode="honest",
        filename=filename,
        cv_override=cv_override,
    )


def tailor_cv_full_match(
    cv_text: str,
    job_title: str,
    company: str,
    job_description: str,
    cv_pdf_bytes: Optional[bytes] = None,
    filename: str = "cv.pdf",
    cv_override: Optional[Dict] = None,
) -> Dict:
    """
    Runs the Senior CV Engine in Full-Match Professional Mode:
    1. Layout-aware extraction & structure parsing (`cv_engine.extract` + `cv_engine.parse`)
    2. Pre-tailoring diagnosis (`cv_engine.analyze.diagnose`)
    3. Mechanical enhancement (`cv_engine.enhance`)
    4. Aligns headline, crafts a bilingual EN/FR executive summary, bridges missing JD tech skills
       into clean recruiter categories, and prioritizes bullets & projects by relevance
    5. Renders a clean single-column A4 executive PDF (`cv_engine.render.render_cv_pdf`)
    """
    from cv_engine.tailor import tailor_cv_pipeline
    return tailor_cv_pipeline(
        cv_text=cv_text,
        job_title=job_title,
        company=company,
        job_description=job_description,
        cv_pdf_bytes=cv_pdf_bytes,
        mode="full_match",
        filename=filename,
        cv_override=cv_override,
    )
