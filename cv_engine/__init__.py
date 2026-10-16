"""
cv_engine — Senior-grade CV extraction, pre-tailoring diagnosis, honest enhancement,
role-specific tailoring, and single-column A4 ATS PDF generation.
"""
from .analyze import career_stage, classify_type, diagnose
from .enhance import Enhancer, enhance, group_skills
from .extract import Document, Line, extract_document
from .parse import CV, Entry, parse_document
from .render import render_cv_pdf
from .tailor import analyze_and_enhance_cv, cv_to_ats_text, tailor_cv_pipeline

__all__ = [
    "Document",
    "Line",
    "extract_document",
    "CV",
    "Entry",
    "parse_document",
    "diagnose",
    "classify_type",
    "career_stage",
    "Enhancer",
    "enhance",
    "group_skills",
    "render_cv_pdf",
    "analyze_and_enhance_cv",
    "cv_to_ats_text",
    "tailor_cv_pipeline",
]
