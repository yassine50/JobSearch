"""
Extraction quality assessment + user-reviewed CV round-tripping.

Two jobs:
  1. `assess_extraction(doc, cv)` — decide how much we can trust what the extractor/parser produced
     from an arbitrary CV file (Canva, Europass, scanned, two-column...). The result drives a
     confidence banner in the UI and stops automatic sends from attaching a thin tailored CV.
  2. `cv_from_dict(d)` — rebuild a `CV` from the JSON the user reviewed/corrected in the UI, so the
     tailoring pipeline can run on human-verified structure instead of re-parsing the file.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .dates import find_date_span
from .extract import Document
from .parse import CV, Entry

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#.'’-]*")

_STOP = {
    "with", "that", "this", "from", "have", "were", "their", "they", "into", "using", "used", "based", "also",
    "such", "more", "other", "than", "over", "which", "while", "each", "within", "through", "about", "when",
    "your", "able", "will", "been", "being", "where", "these", "those", "pour", "dans", "avec", "des", "une",
    "les", "sur", "par", "aux", "est", "sont", "leur", "ainsi", "comme", "plus",
    # section headings / labels the renderer re-creates itself
    "profile", "profil", "summary", "experience", "professional", "education", "skills", "technical",
    "projects", "project", "languages", "language", "certifications", "contact", "keywords", "technologies",
    "present", "current", "page", "curriculum", "vitae", "resume",
}


def _words(text: str) -> List[str]:
    return [w.lower().strip(".,'’-") for w in _WORD_RE.findall(text or "") if len(w) > 1]


def cv_content_text(cv: CV) -> str:
    """Every piece of content the renderer can show (used for coverage checks)."""
    parts: List[str] = [cv.name, cv.headline, cv.objective, cv.summary]
    parts += list(cv.contact.values()) + list(cv.links.values())
    for e in cv.experience + cv.projects + cv.education:
        parts += [e.title, e.org, e.location, e.date_text] + e.bullets + e.stack + e.extra
    for cat, items in cv.skill_groups:
        parts += [cat] + list(items)
    parts += cv.skills + cv.unknown_skills + cv.soft_skills + cv.certifications + cv.awards
    parts += cv.activities + cv.interests
    for l in cv.languages:
        parts += [l.get("name_en", ""), l.get("level_en", "")]
    return " ".join(p for p in parts if p)


def assess_extraction(doc: Optional[Document], cv: CV) -> Dict:
    """
    Score 0–100 for how faithfully the file was understood.
    level: "high" (≥80) | "medium" (55–79) | "low" (<55).
    """
    warnings: List[str] = []
    penalty = 0
    meta = dict(getattr(doc, "meta", None) or cv.meta or {})

    # 1) Coverage: share of the source's distinct content words that made it into the structured CV
    #    (distinct + stop-word-free, so repeated "the/and/developed" cannot hide a dropped section)
    src_words = _words(doc.text if doc is not None else cv.raw_text)
    src_content = {w for w in src_words if len(w) > 3 and w not in _STOP}
    parsed_set = set(_words(cv_content_text(cv)))
    coverage = 1.0
    if len(src_words) >= 40 and src_content:
        coverage = sum(1 for w in src_content if w in parsed_set) / len(src_content)
        if coverage < 0.55:
            penalty += 40
            warnings.append(f"Only {int(coverage * 100)}% of the text in your file was recognised — some sections are probably missing.")
        elif coverage < 0.75:
            penalty += 18
            warnings.append(f"About {100 - int(coverage * 100)}% of the text in your file was not placed in any section.")
    elif doc is not None:
        penalty += 45
        warnings.append("Very little text could be read from the file.")

    # 2) Extraction path
    if meta.get("ocr_recovered") or meta.get("scanned"):
        penalty += 22
        warnings.append("The file has no selectable text (scanned/image PDF), so it was read with OCR — check names, dates and numbers.")

    # 2b) A summary that swallowed other sections (classic failure on unusual layouts): the tailor
    #     rewrites the summary, so everything trapped inside it silently disappears from the output.
    summary_words = len((cv.summary or "").split())
    src_n = max(1, len(src_words))
    if summary_words > 130 or (summary_words > 70 and summary_words > 0.35 * src_n):
        penalty += 30
        warnings.append(f"The profile/summary is unusually long ({summary_words} words) — other sections were probably merged into it.")

    # 3) Structural sanity
    if not cv.name:
        penalty += 12
        warnings.append("Your name was not detected.")
    if not (cv.contact.get("email") or cv.contact.get("phone")):
        penalty += 8
        warnings.append("No email or phone number was detected.")
    if not cv.experience and not cv.projects:
        penalty += 25
        warnings.append("No experience or project entries were detected.")
    entries = cv.experience + cv.projects
    if entries:
        empty = [e for e in entries if not e.bullets]
        if len(empty) >= max(2, (len(entries) + 1) // 2):
            penalty += 22
            warnings.append(f"{len(empty)} of {len(entries)} experience/project entries have no description.")
        undated = [e for e in cv.experience if not e.date_text]
        if cv.experience and len(undated) == len(cv.experience) and len(cv.experience) >= 2:
            penalty += 8
            warnings.append("No dates were detected on any experience entry.")
        untitled = [e for e in entries if not e.title]
        if untitled:
            penalty += 6
            warnings.append(f"{len(untitled)} entr{'y has' if len(untitled) == 1 else 'ies have'} no title.")
    if not cv.education:
        penalty += 5
        warnings.append("No education entries were detected.")
    if not cv.skills and not cv.skill_groups:
        penalty += 8
        warnings.append("No skills were detected.")

    score = max(0, min(100, 100 - penalty))
    level = "high" if score >= 80 else ("medium" if score >= 55 else "low")
    return {
        "score": score,
        "level": level,
        "coverage": round(coverage, 3),
        "extractor": meta.get("extractor", ""),
        "layout": meta.get("layout", ""),
        "warnings": warnings,
        "reviewed": False,
    }


def output_thinness(source_cv: CV, tailored_text: str) -> Optional[str]:
    """Warn when the tailored output carries far less content than the parsed source."""
    src = len(_words(cv_content_text(source_cv)))
    out = len(_words(tailored_text))
    if src >= 120 and out < 0.6 * src:
        return f"The tailored CV contains about {int(100 * out / src)}% of the content of your original."
    return None


# ─── JSON round-trip for the "review before download" step ───────────────────

def _s(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _str_list(v) -> List[str]:
    if isinstance(v, str):
        v = v.splitlines()
    return [_s(x) for x in (v or []) if _s(x)]


def _entry_from_dict(d: Dict, kind: str) -> Entry:
    date_text = _s(d.get("date_text"))
    found = find_date_span(date_text) if date_text else None
    e = Entry(
        title=_s(d.get("title")),
        org=_s(d.get("org")),
        location=_s(d.get("location")),
        dates=found[0] if found else None,
        date_text=date_text,
        bullets=_str_list(d.get("bullets")),
        stack=_str_list(d.get("stack")),
        links=_str_list(d.get("links")),
        extra=_str_list(d.get("extra")),
        kind=_s(d.get("kind")) or kind,
    )
    return e


def cv_from_dict(d: Dict) -> CV:
    """Inverse of `CV.to_dict()` (tolerant of partial / user-edited payloads)."""
    d = d or {}
    cv = CV(
        name=_s(d.get("name")),
        headline=_s(d.get("headline")),
        objective=_s(d.get("objective")),
        contact={k: _s(v) for k, v in (d.get("contact") or {}).items() if _s(v)},
        links={k: _s(v) for k, v in (d.get("links") or {}).items() if _s(v)},
        personal=_str_list(d.get("personal")),
        summary=_s(d.get("summary")),
        lang=_s(d.get("lang")) or "en",
        meta=dict(d.get("meta") or {}),
        sections_found=_str_list(d.get("sections_found")),
    )
    cv.experience = [_entry_from_dict(x, "job") for x in (d.get("experience") or []) if isinstance(x, dict)]
    cv.projects = [_entry_from_dict(x, "project") for x in (d.get("projects") or []) if isinstance(x, dict)]
    cv.education = [_entry_from_dict(x, "education") for x in (d.get("education") or []) if isinstance(x, dict)]
    for coll in (cv.experience, cv.projects, cv.education):
        coll[:] = [e for e in coll if e.title or e.org or e.bullets]

    groups = []
    for g in d.get("skill_groups") or []:
        if isinstance(g, dict):
            cat, items = g.get("category"), g.get("items")
        elif isinstance(g, (list, tuple)) and len(g) == 2:
            cat, items = g
        else:
            continue
        if isinstance(items, str):
            items = re.split(r"\s*[,;]\s*", items)
        items = _str_list(items)
        if items:
            groups.append((_s(cat) or "Skills", items))
    cv.skill_groups = groups
    flat: List[str] = []
    for _, items in groups:
        for it in items:
            if it not in flat:
                flat.append(it)
    for s in _str_list(d.get("skills")):
        if s not in flat:
            flat.append(s)
    cv.skills = flat
    cv.unknown_skills = _str_list(d.get("unknown_skills"))
    cv.soft_skills = _str_list(d.get("soft_skills"))
    cv.certifications = _str_list(d.get("certifications"))
    cv.awards = _str_list(d.get("awards"))
    cv.activities = _str_list(d.get("activities"))
    cv.interests = _str_list(d.get("interests"))

    langs = []
    for l in d.get("languages") or []:
        if not isinstance(l, dict):
            continue
        name = _s(l.get("name_en") or l.get("name"))
        if not name:
            continue
        lvl = _s(l.get("level_en") or l.get("level"))
        langs.append({
            "name_en": name, "name_fr": _s(l.get("name_fr")) or name,
            "level_en": lvl, "level_fr": _s(l.get("level_fr")) or lvl,
        })
    cv.languages = langs
    cv.raw_text = cv_content_text(cv)
    return cv
