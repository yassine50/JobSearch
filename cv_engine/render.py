"""
Executive ATS PDF renderer (ReportLab) for structured `CV` objects.

Features:
  • Single-column A4 executive LaTeX/FAANG layout readable by all ATS parsers
  • Centered executive header with clickable email, LinkedIn, GitHub, and portfolio links
  • Bilingual EN/FR section headers with crisp full-width rules
  • Bolded impact metrics inside bullets, structured project titles, and clean language levels
  • Automatic 4-step typographic scaling so 1-page CVs fit cleanly on 1 page
"""
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import unicodedata

from .parse import CV, Entry

_NON_WINANSI_MAP = str.maketrans({
    "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ı": "i", "İ": "I",
    "ș": "s", "Ș": "S", "ş": "s", "Ş": "S", "ț": "t", "Ț": "T", "ţ": "t", "Ţ": "T",
})


def _winansi_safe(text: str) -> str:
    """Ensure every character renders cleanly in ReportLab's built-in Helvetica (WinAnsi / CP1252) without black boxes."""
    if not text:
        return ""
    s = text.translate(_NON_WINANSI_MAP)
    try:
        s.encode("cp1252")
        return s
    except UnicodeEncodeError:
        out = []
        for ch in s:
            try:
                ch.encode("cp1252")
                out.append(ch)
            except UnicodeEncodeError:
                decomposed = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
                out.append(decomposed or "")
        return "".join(out)


def _esc(text: str) -> str:
    return (
        _winansi_safe(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _short_url(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (url or "").strip()).rstrip("/")
    return u[:48] + ("…" if len(u) > 48 else "")


def _format_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "Candidate"
    if n.isupper() and len(n) > 3:
        return " ".join(w.capitalize() for w in n.split())
    return n


_CATEGORY_LABELS_EN = {
    "mobile": "Mobile & Cross-Platform",
    "backend & cloud": "Backend & Cloud",
    "release & quality": "Release, CI/CD & Quality",
    "web": "Web & Frontend",
    "also familiar with": "Additional Technologies",
    "general skills": "Core Technologies",
}


def _pretty_cat(cat: str) -> str:
    c = (cat or "").strip().rstrip(":")
    if not c:
        return ""
    low = c.lower()
    if low in _CATEGORY_LABELS_EN:
        return _CATEGORY_LABELS_EN[low]
    return c[0].upper() + c[1:]


_METRIC_HIGHLIGHT_RE = re.compile(
    r"(\b\d+(?:[.,]\d+)?\s?(?:%|x\b|k\+|\+|ms\b|s\s+to\s+\d+s\b|\d*s\b)|"
    r"\b\d{1,3}(?:,\d{3})+\+?\s*(?:downloads?|users?|features?|apps?)\b|"
    r"\b\d+\+?\s+(?:cross-platform\s+|bilingual\s+)?(?:apps?|features?|downloads?|users?|projects?)\b)",
    re.I,
)


def _format_bullet_markup(text: str) -> str:
    escaped = _esc(text)
    return _METRIC_HIGHLIGHT_RE.sub(r"<b>\1</b>", escaped)


def _clean_lang_level(lvl: str) -> str:
    if not lvl:
        return ""
    # Convert "Fluent (C1)" -> "Fluent — C1" to avoid nested parentheses "(Fluent (C1))"
    m = re.match(r"^([^(]+?)\s*\(([^)]+)\)$", lvl.strip())
    if m:
        return f"{m.group(1).strip()} — {m.group(2).strip()}"
    return lvl.strip()


SECTION_TITLES: Dict[str, Tuple[str, str]] = {
    "summary": ("Professional Summary", "Profil Professionnel"),
    "competencies": ("Core Competencies", "Compétences Clés"),
    "skills": ("Technical Skills", "Compétences Techniques"),
    "experience": ("Professional Experience", "Expérience Professionnelle"),
    "projects": ("Selected Projects", "Projets Réalisés"),
    "education": ("Education", "Formation"),
    "certifications": ("Certifications", "Certifications"),
    "awards": ("Honors & Awards", "Distinctions & Prix"),
    "activities": ("Leadership & Activities", "Vie Associative & Engagement"),
    "languages": ("Languages", "Langues"),
}


def render_cv_pdf(
    cv: CV,
    section_order: Optional[List[str]] = None,
    max_pages: int = 1,
) -> bytes:
    """Render a `CV` instance into an executive single-column A4 PDF."""
    is_fr = cv.lang == "fr"
    order = section_order or [
        "summary",
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
        "awards",
        "activities",
        "languages",
    ]

    def _build(scale: int = 0) -> Tuple[bytes, int]:
        # scale -1 = generous (short CVs), 0 = normal, 1 = compact, 2 = tight, 3 = ultra-tight
        idx = scale + 1
        margin_x = [38, 34, 30, 26, 24][idx]
        margin_y = [32, 26, 21, 17, 14][idx]
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=margin_x,
            rightMargin=margin_x,
            topMargin=margin_y,
            bottomMargin=margin_y,
            title=f"{_format_name(cv.name)} - CV",
            author=_format_name(cv.name),
        )
        avail_w = A4[0] - 2 * margin_x

        NAVY = colors.HexColor("#0F172A")
        ACCENT = colors.HexColor("#1E3A8A")
        SLATE = colors.HexColor("#1E293B")
        MUTED = colors.HexColor("#475569")
        RULE = colors.HexColor("#334155")

        f_name = [21.5, 20.5, 19.0, 17.6, 16.5][idx]
        f_head = [11.5, 11.0, 10.4, 9.8, 9.4][idx]
        f_sec = [10.2, 9.8, 9.3, 8.9, 8.6][idx]
        f_role = [10.0, 9.8, 9.3, 8.9, 8.6][idx]
        f_body = [9.5, 9.2, 8.75, 8.35, 8.0][idx]
        l_body = [13.2, 12.3, 11.4, 10.6, 10.0][idx]
        f_meta = [8.9, 8.6, 8.25, 7.95, 7.65][idx]
        sec_gap = [10.0, 7.5, 5.5, 4.0, 3.0][idx]
        item_gap = [6.0, 4.5, 3.2, 2.2, 1.5][idx]
        bul_gap = [1.8, 1.2, 0.8, 0.4, 0.2][idx]

        base = getSampleStyleSheet()["Normal"]
        st_name = ParagraphStyle(
            "Name",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_name,
            leading=f_name + 3,
            textColor=NAVY,
            alignment=1,
        )
        st_head = ParagraphStyle(
            "Headline",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_head,
            leading=f_head + 2.5,
            textColor=ACCENT,
            alignment=1,
        )
        st_contact = ParagraphStyle(
            "Contact",
            parent=base,
            fontName="Helvetica",
            fontSize=f_meta,
            leading=f_meta + 2.6,
            textColor=SLATE,
            alignment=1,
        )
        st_sec = ParagraphStyle(
            "Sec",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_sec,
            leading=f_sec + 2,
            textColor=NAVY,
        )
        st_role = ParagraphStyle(
            "Role",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_role,
            leading=f_role + 2.2,
            textColor=NAVY,
        )
        st_proj_title = ParagraphStyle(
            "ProjTitle",
            parent=base,
            fontName="Helvetica",
            fontSize=f_role,
            leading=f_role + 2.2,
            textColor=NAVY,
        )
        st_org = ParagraphStyle(
            "Org",
            parent=base,
            fontName="Helvetica-Oblique",
            fontSize=f_body,
            leading=f_body + 2,
            textColor=SLATE,
        )
        st_date = ParagraphStyle(
            "Date",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_meta,
            leading=f_meta + 2,
            textColor=NAVY,
            alignment=2,
        )
        st_loc = ParagraphStyle(
            "Loc",
            parent=base,
            fontName="Helvetica-Oblique",
            fontSize=f_meta,
            leading=f_meta + 2,
            textColor=MUTED,
            alignment=2,
        )
        st_link = ParagraphStyle(
            "Link",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=f_meta,
            leading=f_meta + 2,
            textColor=ACCENT,
            alignment=2,
        )
        st_body = ParagraphStyle(
            "Body",
            parent=base,
            fontName="Helvetica",
            fontSize=f_body,
            leading=l_body,
            textColor=NAVY,
        )
        st_bullet = ParagraphStyle(
            "Bullet",
            parent=st_body,
            leftIndent=11,
            firstLineIndent=0,
            bulletIndent=2,
            spaceBefore=bul_gap,
        )
        st_stack = ParagraphStyle(
            "Stack",
            parent=base,
            fontName="Helvetica",
            fontSize=f_meta,
            leading=f_meta + 2.2,
            textColor=SLATE,
            leftIndent=11,
            spaceBefore=1.0,
        )

        def link_markup(label: str, url: str) -> str:
            if not url:
                return _esc(label)
            href = url if url.startswith(("http://", "https://", "mailto:")) else f"https://{url}"
            return f'<link href="{_esc(href)}" color="#1E3A8A">{_esc(label)}</link>'

        def two_col(left_p, right_p, ratio=0.74, top=0.0, bottom=0.5):
            raw_r = getattr(right_p, "text", "") if right_p is not None else ""
            plain_r = re.sub(r"<[^>]+>", "", raw_r).replace("&nbsp;", " ").strip()
            if not plain_r:
                t = Table([[left_p]], colWidths=[avail_w])
            else:
                r_w = min(avail_w * 0.34, max(avail_w * (1 - ratio), len(plain_r) * f_meta * 0.56 + 10.0))
                t = Table([[left_p, right_p]], colWidths=[avail_w - r_w, r_w])
            t.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), top),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), bottom),
                    ]
                )
            )
            return t

        def section_header(key: str):
            en_t, fr_t = SECTION_TITLES.get(key, (key.title(), key.title()))
            title = (fr_t if is_fr else en_t).upper()
            return [
                Spacer(1, sec_gap),
                Paragraph(_esc(title), st_sec),
                HRFlowable(
                    width="100%",
                    thickness=0.75,
                    color=RULE,
                    spaceBefore=1.5,
                    spaceAfter=3.2 if scale < 2 else 2.0,
                ),
            ]

        story = []

        # ── Executive Centered Header ─────────────────────────────────────────
        story.append(Paragraph(_esc(_format_name(cv.name)), st_name))
        if cv.headline:
            story.append(Spacer(1, 1.5))
            story.append(Paragraph(_esc(cv.headline), st_head))

        contact_items: List[str] = []
        if cv.contact.get("location"):
            loc_txt = re.sub(r"\s+,", ",", cv.contact["location"])
            contact_items.append(_esc(loc_txt).replace(" ", "&nbsp;"))
        if cv.contact.get("phone"):
            contact_items.append(_esc(cv.contact["phone"]).replace(" ", "&nbsp;"))
        if cv.contact.get("email"):
            em = cv.contact["email"]
            contact_items.append(link_markup(em, f"mailto:{em}"))

        profile_items: List[str] = []
        for k in ("linkedin", "github", "gitlab", "portfolio"):
            url = cv.links.get(k)
            if url and "job-search-two-beryl.vercel.app" not in url.lower():
                profile_items.append(link_markup(_short_url(url), url))

        sep = "&nbsp;&nbsp;•&nbsp;&nbsp;"
        all_header_items = contact_items + profile_items

        def _fits_one_line(items: List[str]) -> bool:
            from reportlab.pdfbase.pdfmetrics import stringWidth
            plain = re.sub(r"<[^>]+>", "", sep.join(items)).replace("&nbsp;", " ").replace("&amp;", "&")
            return stringWidth(plain, "Helvetica", f_meta) <= avail_w * 0.98

        if all_header_items:
            story.append(Spacer(1, 2.5))
            # One centered line when it fits; otherwise a clean 2-line split (contact / profiles)
            # instead of letting ReportLab wrap mid-item ("Monastir," alone on a line).
            if _fits_one_line(all_header_items):
                story.append(Paragraph(sep.join(all_header_items), st_contact))
            else:
                story.append(Paragraph(sep.join(contact_items), st_contact))
                if profile_items:
                    story.append(Paragraph(sep.join(profile_items), st_contact))

        # ── Section renderers ─────────────────────────────────────────────────
        def render_summary():
            if not cv.summary:
                return []
            out = section_header("summary")
            out.append(Paragraph(_format_bullet_markup(cv.summary), st_body))
            return out

        def render_skills():
            groups = cv.skill_groups
            if not groups and cv.skills:
                from .enhance import group_skills
                groups = group_skills(cv.skills, cv.lang)
            if not groups:
                return []
            out = section_header("skills")
            skill_st = ParagraphStyle(
                "SkillRow",
                parent=st_body,
                spaceBefore=1.2 if scale == 0 else 0.6,
                leading=l_body,
            )
            for cat, items in groups:
                deduped: List[str] = []
                has_aws_s3 = any(i.strip().upper() == "AWS S3" for i in items if i)
                has_jwt_auth = any("jwt auth" in i.strip().lower() for i in items if i)
                for i in items:
                    if not i or not i.strip():
                        continue
                    val = "SOLID" if i.strip().lower() == "solid" else i.strip()
                    if has_aws_s3 and val.upper() == "AWS":
                        continue
                    if has_jwt_auth and val.upper() == "JWT":
                        continue
                    if val not in deduped:
                        deduped.append(val)
                clean = [_esc(i) for i in deduped]
                if not clean:
                    continue
                pretty_c = _pretty_cat(cat)
                if pretty_c:
                    out.append(Paragraph(f"<b>{_esc(pretty_c)}:</b>&nbsp; {', '.join(clean)}", skill_st))
                else:
                    out.append(Paragraph(", ".join(clean), skill_st))
            return out

        def _render_entry_bullets_and_stack(e: Entry, block: List):
            play_links = [u for u in e.links if "play.google.com" in u.lower() or "apps.apple.com" in u.lower()]
            for b in e.bullets:
                if b.lower().startswith("live apps:") and play_links:
                    prefix, rest = b.split(":", 1)
                    names = [a.strip().rstrip(".") for a in rest.split("|") if a.strip()]
                    if len(names) == len(play_links):
                        linked = " &nbsp;|&nbsp; ".join(
                            link_markup(n, u) for n, u in zip(names, play_links)
                        )
                        block.append(Paragraph(f"<b>{_esc(prefix)}:</b>&nbsp; {linked}", st_bullet, bulletText="•"))
                        continue
                block.append(Paragraph(_format_bullet_markup(b), st_bullet, bulletText="•"))

            if e.stack:
                bullets_joined = " ".join(e.bullets).lower()
                unmentioned = [s for s in e.stack if s.lower() not in bullets_joined]
                if not e.bullets or len(unmentioned) >= 2 or len(e.stack) >= 3:
                    lbl = "Environnement technique" if is_fr else "Technologies"
                    stack_str = ", ".join(_esc(s) for s in e.stack[:12])
                    block.append(Paragraph(f"<i>{lbl}:</i> {stack_str}", st_stack))

        def _workday_safe_date(dt: str) -> str:
            """
            Workday ATS Date-Range Compatibility (ported from ai-job-search 05-cv-templates.md):
            Workday's PDF resume parser only recognizes ASCII hyphens (-) in employment and
            education date ranges and silently drops dates separated by Unicode en/em dashes.
            """
            if not dt:
                return ""
            s = re.sub(r"\s*[\u2012\u2013\u2014\u2015\u2212]+\s*", " - ", dt.strip())
            return re.sub(r"\s{2,}", " ", s)

        def render_experience():
            if not cv.experience:
                return []
            out = section_header("experience")
            for idx, e in enumerate(cv.experience):
                left_top = e.title or e.org or ("Stage / Expérience" if is_fr else "Experience")
                sub_org = e.org if e.title and e.org else ""
                block = [
                    two_col(
                        Paragraph(_esc(left_top), st_role),
                        Paragraph(_esc(_workday_safe_date(e.date_text)), st_date),
                        ratio=0.74,
                        top=0 if idx == 0 else item_gap,
                    )
                ]
                if sub_org or e.location:
                    block.append(
                        two_col(
                            Paragraph(_esc(sub_org), st_org),
                            Paragraph(_esc(e.location), st_loc),
                            ratio=0.76,
                            bottom=0.8,
                        )
                    )
                _render_entry_bullets_and_stack(e, block)
                out.append(KeepTogether(block))
            return out

        def render_projects():
            if not cv.projects:
                return []
            out = section_header("projects")
            for idx, e in enumerate(cv.projects):
                p_title = e.title or e.org or ("Projet" if is_fr else "Project")
                # Format "Project Name — Subtitle" as "<b>Project Name</b> — <i>Subtitle</i>"
                m_dash = re.match(r"^(.+?)\s+([—–])\s+(.+)$", p_title)
                if m_dash:
                    title_html = f"<b>{_esc(m_dash.group(1).strip())}</b> {m_dash.group(2)} <i>{_esc(m_dash.group(3).strip())}</i>"
                    left_para = Paragraph(title_html, st_proj_title)
                else:
                    left_para = Paragraph(_esc(p_title), st_role)

                right_parts: List[str] = []
                for u in e.links[:2]:
                    if "job-search-two-beryl.vercel.app" in u.lower():
                        continue
                    ul = u.lower()
                    lbl = (
                        "GitHub"
                        if "github.com" in ul
                        else "GitLab"
                        if "gitlab.com" in ul
                        else "Live Demo"
                        if any(h in ul for h in ("vercel.app", "netlify.app", "herokuapp.com", "github.io"))
                        else _short_url(u)
                    )
                    right_parts.append(link_markup(lbl, u))
                if e.date_text:
                    right_parts.append(_esc(_workday_safe_date(e.date_text)))
                right_html = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(right_parts)
                right_style = st_link if right_parts and e.links else st_date

                block = [
                    two_col(
                        left_para,
                        Paragraph(right_html, right_style),
                        ratio=0.78,
                        top=0 if idx == 0 else item_gap,
                    )
                ]
                if e.org and e.title:
                    block.append(Paragraph(_esc(e.org), st_org))
                _render_entry_bullets_and_stack(e, block)
                out.append(KeepTogether(block))
            return out

        def render_education():
            if not cv.education:
                return []
            out = section_header("education")
            for idx, e in enumerate(cv.education):
                top_left = e.title or e.org
                sub_left = e.org if e.title and e.org else ""
                block = [
                    two_col(
                        Paragraph(_esc(top_left), st_role),
                        Paragraph(_esc(_workday_safe_date(e.date_text)), st_date),
                        ratio=0.78,
                        top=0 if idx == 0 else (item_gap * 0.85),
                    )
                ]
                if sub_left or e.location:
                    block.append(
                        two_col(
                            Paragraph(_esc(sub_left), st_org),
                            Paragraph(_esc(e.location), st_loc),
                            ratio=0.78,
                            bottom=0.5,
                        )
                    )
                for b in e.bullets[:2]:
                    block.append(Paragraph(_esc(b), st_bullet, bulletText="•"))
                out.append(KeepTogether(block))
            return out

        def render_simple_list(sec_key: str, items: List[str]):
            clean = [i.strip() for i in items if i and i.strip()]
            if not clean:
                return []
            out = section_header(sec_key)
            if len(clean) <= 3 and all(len(c) < 55 for c in clean):
                out.append(Paragraph("&nbsp;&nbsp;•&nbsp;&nbsp;".join(_esc(c) for c in clean), st_body))
            else:
                for c in clean:
                    out.append(Paragraph(_esc(c), st_bullet, bulletText="•"))
            return out

        def render_languages():
            if not cv.languages:
                return []
            formatted = []
            for l in cv.languages:
                name = (
                    l.get("name_fr" if is_fr else "name_en")
                    or l.get("lang_fr" if is_fr else "lang_en")
                    or l.get("name_en")
                    or l.get("lang")
                    or ""
                )
                raw_lvl = l.get("level_fr" if is_fr else "level_en") or l.get("level") or ""
                lvl = _clean_lang_level(raw_lvl)
                if not name:
                    continue
                # non-breaking inside each item so "Chinese (Basic — A2)" never splits across lines
                item = f"<b>{_esc(name)}</b> ({_esc(lvl)})" if lvl else f"<b>{_esc(name)}</b>"
                formatted.append(item.replace(" ", "&nbsp;"))
            if not formatted:
                return []
            out = section_header("languages")
            out.append(Paragraph("&nbsp;&nbsp;•&nbsp; ".join(formatted), st_body))
            return out

        def render_competencies():
            comps = [c.strip() for c in ((cv.meta or {}).get("core_competencies") or []) if c and c.strip()]
            if not comps:
                return []
            out = section_header("competencies")
            # non-breaking inside each item, breakable after each separator
            items = [_esc(c).replace(" ", "&nbsp;") for c in comps]
            out.append(Paragraph("&nbsp;&nbsp;•&nbsp; ".join(items), st_body))
            return out

        dispatch = {
            "summary": render_summary,
            "competencies": render_competencies,
            "skills": render_skills,
            "experience": render_experience,
            "projects": render_projects,
            "education": render_education,
            "certifications": lambda: render_simple_list("certifications", cv.certifications),
            "awards": lambda: render_simple_list("awards", cv.awards),
            "activities": lambda: render_simple_list("activities", cv.activities),
            "languages": render_languages,
        }

        for sec in order:
            fn = dispatch.get(sec)
            if fn:
                story.extend(fn())

        doc.build(story)
        pdf_bytes = buf.getvalue()
        buf.close()
        return pdf_bytes, getattr(doc, "page", 1)

    def _is_thin_second_page(pdf_data: bytes) -> bool:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_data))
            if len(reader.pages) != 2:
                return False
            p1 = len((reader.pages[0].extract_text() or "").strip())
            p2 = len((reader.pages[1].extract_text() or "").strip())
            return p1 > 300 and p2 < 0.32 * p1
        except Exception:
            return False

    pdf_bytes, pages = _build(scale=0)
    total_entries = len(cv.experience) + len(cv.projects)
    total_bullets = sum(len(e.bullets) for e in cv.experience + cv.projects)
    if pages == 1 and total_entries <= 3 and total_bullets <= 8:
        gen_bytes, gen_pages = _build(scale=-1)
        if gen_pages == 1:
            return gen_bytes

    target_pages = 1 if (pages == 2 and _is_thin_second_page(pdf_bytes)) else max_pages
    if pages > target_pages:
        for s in (1, 2, 3):
            cand_bytes, cand_pages = _build(scale=s)
            if cand_pages <= target_pages:
                return cand_bytes
            if target_pages == max_pages:
                pdf_bytes = cand_bytes
    return pdf_bytes
