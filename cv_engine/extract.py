"""
Layout-aware CV text extraction.

Why this exists: plain `PyPDF2.extract_text()` interleaves the columns of designer CVs
(Canva / Europass / moderncv), glues headings onto neighbouring lines, leaks icon-font glyphs
("/envel⌢pe", "(cid:131)") and breaks LaTeX accents ("Ing´ enierie"). Everything downstream
depends on clean, ordered lines, so we rebuild the reading order from character geometry:

  1. pdfminer gives every text line with its bbox, font name and font size.
  2. Icon-font characters are dropped; ligatures / accents / letter-spacing are repaired.
  3. A vertical gutter search splits two-column pages; right-aligned dates in single-column
     CVs are recognised and kept on the same line (separated by a TAB).
  4. Fragments on the same baseline are merged left→right with "\t" between distant pieces,
     so the parser can tell "Role\tDate" apart from running prose.

Falls back to PyPDF2 when pdfminer is unavailable, and flags image-only (scanned) PDFs.
"""
from __future__ import annotations

import io
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ICON_FONT_RE = re.compile(r"awesome|fontello|icomoon|material.?icons|glyphicon|entypo|ionicons|feather|linearicons|webdings", re.I)
SYMBOL_BULLET_FONT_RE = re.compile(r"^(?:[A-Z]{6}\+)?(?:symbol(?:mt)?|wingdings[-\w]*|zapfdingbats|dingbats)$", re.I)
BOLD_FONT_RE = re.compile(r"bold|black|heavy|semibold|demi|extrabold|-bd\b|,bd|bd$", re.I)

BULLET_GLYPHS = "•●▪■◦○◆◇❖➢➤►▸▹‣⁃∙·✓✔☐□❯→»➔➜"


@dataclass
class Line:
    text: str
    size: float = 10.0
    bold: bool = False
    x0: float = 0.0
    x1: float = 0.0
    top: float = 0.0          # distance from top of the document (pages stacked)
    page: int = 0
    col: int = 0              # -1 = spans columns, 0 = left/only column, 1 = right column
    links: List[str] = field(default_factory=list)
    caps: bool = False

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Line(p{self.page} c{self.col} {self.size:.1f}{'B' if self.bold else ''} {self.text!r})"


@dataclass
class Document:
    lines: List[Line]
    body_size: float = 10.0
    links: List[str] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(l.text.replace("\t", "  ") for l in self.lines)


# ─── Text normalisation ───────────────────────────────────────────────────────

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st"}
_COMBINING = {"´": "\u0301", "`": "\u0300", "ˆ": "\u0302", "^": "\u0302", "¨": "\u0308", "˜": "\u0303", "¸": "\u0327"}
_ACCENT_RE = re.compile(r"(\s?)([´`ˆ¨˜])\s?([A-Za-z])")


def _compose_accent(m) -> str:
    lead, acc, letter = m.group(1), m.group(2), m.group(3)
    keep_space = lead if acc in "´`" else ""
    return keep_space + unicodedata.normalize("NFC", letter + _COMBINING[acc])


_CEDILLA_RE = re.compile(r"([cC])\s?¸")
_LETTERSPACED_RE = re.compile(r"^(?:[^\s]\s){3,}[^\s]$")
_FA_NAME_LEAK_RE = re.compile(
    r"((?<![\w:/.])/?envel[⌢o]pe|(?<![\w:/.])/?map♂?mar¶?er|♂¶ap-¶arker|(?<![\w:/.])♂?phone(?=\+?\d)|"
    r"(?<![\w:/.])/linkedin(?=[a-z@])|(?<![\w:/.])/github(?=[a-z@])|(?<![\w:/.])/(?:globe|home|phone|envelope|map)(?=\s|\d|$)|"
    r"Ὄ5|♂|¶|⌢)",
)


def _collapse_letterspacing(s: str) -> str:
    """'A Z E R   B E L A I D' -> 'AZER BELAID' (display fonts with tracking)."""
    stripped = s.strip()
    words = [w for w in re.split(r"\s{2,}", stripped) if w]
    if not words:
        return s
    if all(re.fullmatch(r"\S(?: \S)*", w) for w in words):
        singles = sum(len(w.split(" ")) for w in words)
        if singles >= 5 and singles >= 2 * len(words):
            return " ".join(w.replace(" ", "") for w in words)
    return s


def normalize_text(s: str) -> str:
    if not s:
        return ""
    for k, v in _LIGATURES.items():
        s = s.replace(k, v)
    s = re.sub(r"\(cid:\d+\)", "", s)
    s = re.sub(r"[\ue000-\uf8ff]", "", s)            # private-use (icon fonts)
    s = _FA_NAME_LEAK_RE.sub(" ", s)
    s = _CEDILLA_RE.sub(lambda m: unicodedata.normalize("NFC", m.group(1) + "\u0327"), s)
    s = _ACCENT_RE.sub(_compose_accent, s)
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\u00a0", " ").replace("\u200b", "").replace("\u2009", " ").replace("\u202f", " ")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    if "\t" not in s:
        s = _collapse_letterspacing(s)
    s = "\t".join(re.sub(r"[ ]{2,}", " ", p).strip() for p in s.split("\t"))
    return s.strip()


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) > 0.85


# ─── PDF via pdfminer ─────────────────────────────────────────────────────────

def _pdf_links(pdf_bytes: bytes) -> List[Tuple[int, Tuple[float, float, float, float], str]]:
    out = []
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        for pi, page in enumerate(reader.pages):
            for a in (page.get("/Annots") or []):
                try:
                    o = a.get_object()
                    act = o.get("/A")
                    uri = act.get_object().get("/URI") if act else None
                    if not uri:
                        continue
                    rect = tuple(float(x) for x in o.get("/Rect", [0, 0, 0, 0]))
                    out.append((pi, rect, str(uri).strip()))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _fragments_from_pdfminer(pdf_bytes: bytes):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine, LTFigure, LTImage

    pages = []
    params = LAParams(line_margin=0.3, char_margin=1.6, word_margin=0.12, boxes_flow=None)
    for page in extract_pages(io.BytesIO(pdf_bytes), laparams=params):
        frags, images = [], []

        def walk(el):
            if isinstance(el, LTTextContainer):
                for ln in el:
                    if isinstance(ln, LTTextLine):
                        frags.append(_frag_from_line(ln, LTChar))
            elif isinstance(el, (LTFigure, LTImage)):
                images.append(el.bbox)
                if isinstance(el, LTFigure):
                    for child in el:
                        if isinstance(child, LTImage):
                            images.append(child.bbox)

        for el in page:
            walk(el)
        pages.append((page.bbox, [f for f in frags if f and f["text"].strip()], images))
    return pages


def _frag_from_line(ln, LTChar):
    chars = []
    seen_real = False
    for c in ln:
        if isinstance(c, LTChar):
            t = c.get_text()
            font = c.fontname or ""
            pua = bool(t) and "\ue000" <= t[0] <= "\uf8ff"
            if SYMBOL_BULLET_FONT_RE.search(font) or (pua and not ICON_FONT_RE.search(font)):
                chars.append(("• " if not seen_real else " ", c if not seen_real else None))
                continue
            if ICON_FONT_RE.search(font) or t.startswith("(cid:"):
                chars.append((" ", None))
                continue
            if t.strip():
                seen_real = True
            chars.append((t, c))
        else:  # LTAnno (inferred spaces)
            chars.append((c.get_text(), None))
    real = [c for _, c in chars if c is not None and c.get_text().strip()]
    if not real:
        return None
    text = "".join(t for t, _ in chars).replace("\n", " ")
    sizes = [c.size for c in real]
    bold_ratio = sum(1 for c in real if BOLD_FONT_RE.search(c.fontname or "")) / len(real)
    lead_chars = [c for c in real[:14] if c.get_text().isalpha()]
    lead_bold = len(lead_chars) >= 4 and (
        sum(1 for c in lead_chars if BOLD_FONT_RE.search(c.fontname or "")) / len(lead_chars)
    ) > 0.75
    return {
        "text": text,
        "x0": min(c.x0 for c in real), "x1": max(c.x1 for c in real),
        "y0": min(c.y0 for c in real), "y1": max(c.y1 for c in real),
        "size": statistics.median(sizes), "bold": bold_ratio > 0.55 or lead_bold,
    }


def _find_gutter(frags, width) -> Optional[float]:
    """Return x of a vertical gutter splitting the page into two text columns, or None."""
    body = [f for f in frags if len(f["text"].strip()) > 1]
    if len(body) < 12:
        return None
    best = None
    for g in range(int(width * 0.22), int(width * 0.78), 2):
        left = [f for f in body if f["x1"] <= g]
        right = [f for f in body if f["x0"] >= g]
        cross = len(body) - len(left) - len(right)
        if len(left) < 0.18 * len(body) or len(right) < 0.18 * len(body):
            continue
        if cross > max(3, 0.12 * len(body)):
            continue
        # gap width around g
        lmax = max((f["x1"] for f in left), default=0)
        rmin = min((f["x0"] for f in right), default=width)
        score = (cross, -(rmin - lmax))
        if best is None or score < best[0]:
            best = (score, g, left, right)
    if not best:
        return None
    _, g, left, right = best
    # Reject "single column + right-aligned dates": most right fragments share a baseline with a left one
    def has_partner(f, pool):
        return any(abs(f["y1"] - p["y1"]) < max(2.5, 0.35 * f["size"]) for p in pool)
    partnered = sum(1 for f in right if has_partner(f, left))
    right_text = " ".join(f["text"] for f in right)
    datey = len(re.findall(r"\b(19|20)\d{2}\b|present|présent|current|aujourd", right_text, re.I))
    if partnered / max(1, len(right)) > 0.55 and datey >= 0.3 * len(right):
        return None
    if partnered / max(1, len(right)) > 0.8:
        return None
    return float(g)


def _merge_rows(frags, col_of) -> List[Dict]:
    """Merge fragments that share a baseline (within a column) into rows; TAB between distant fragments."""
    rows: List[Dict] = []
    by_col: Dict[int, List[Dict]] = {}
    for f in frags:
        by_col.setdefault(col_of(f), []).append(f)
    for col, fs in by_col.items():
        fs.sort(key=lambda f: (-f["y1"], f["x0"]))
        cur: List[Dict] = []
        for f in fs:
            if cur and abs(cur[0]["y1"] - f["y1"]) <= max(2.2, 0.38 * max(f["size"], cur[0]["size"])):
                cur.append(f)
            else:
                if cur:
                    rows.append(_row(cur, col))
                cur = [f]
        if cur:
            rows.append(_row(cur, col))
    return rows


def _row(fs, col) -> Dict:
    fs = sorted(fs, key=lambda f: f["x0"])
    parts = [fs[0]["text"].strip()]
    for prev, f in zip(fs, fs[1:]):
        gap = f["x0"] - prev["x1"]
        sep = "\t" if gap > max(5.0, 0.6 * f["size"]) else " "
        parts.append(sep + f["text"].strip())
    text = "".join(parts)
    biggest = max(fs, key=lambda f: len(f["text"]))
    lead_is_bold = bool(fs[0]["bold"] and len(fs[0]["text"].strip()) >= 3)
    return {
        "text": text, "x0": fs[0]["x0"], "x1": fs[-1]["x1"], "y1": max(f["y1"] for f in fs),
        "y0": min(f["y0"] for f in fs), "size": max(f["size"] for f in fs),
        "bold": lead_is_bold or biggest["bold"] or all(f["bold"] for f in fs), "col": col,
    }


def extract_pdf(pdf_bytes: bytes) -> Document:
    try:
        pages = _fragments_from_pdfminer(pdf_bytes)
    except Exception:
        return _extract_pdf_pypdf2(pdf_bytes)

    links = _pdf_links(pdf_bytes)
    lines: List[Line] = []
    offset = 0.0
    columns_seen = 0
    has_photo = False
    total_chars = 0
    for pi, (bbox, frags, images) in enumerate(pages):
        x_min, y_min, width, height = bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]
        total_chars += sum(len(f["text"].strip()) for f in frags)
        for (ix0, iy0, ix1, iy1) in images:
            w, h = ix1 - ix0, iy1 - iy0
            if pi == 0 and 45 < w < 220 and 45 < h < 260 and 0.6 < w / max(h, 1) < 1.6 and iy1 > bbox[3] * 0.55:
                has_photo = True
        gutter = _find_gutter(frags, width)
        if gutter is not None:
            columns_seen = max(columns_seen, 2)

        def col_of(f, g=gutter, w=width, xm=x_min):
            if g is None:
                return 0
            if f["x1"] <= g + 1:
                return 0
            if f["x0"] >= g - 1:
                return 1
            if (f["x1"] - f["x0"]) > 0.55 * w:
                return -1
            return 0 if (f["x0"] + f["x1"]) / 2 < g else 1

        rows = _merge_rows(frags, col_of)
        page_links = [(r, u) for (p, r, u) in links if p == pi]
        page_row_lines: List[Tuple[Dict, Line]] = []
        for r in rows:
            text = normalize_text(r["text"])
            if not text:
                continue
            ln = Line(
                text=text, size=round(r["size"], 1), bold=r["bold"], x0=r["x0"], x1=r["x1"],
                top=offset + (bbox[3] - r["y1"]), page=pi, col=r["col"], caps=_is_caps(text),
            )
            page_row_lines.append((r, ln))
            lines.append(ln)

        # Attach each PDF link annotation to the single best matching row on this page
        for (rx0, ry0, rx1, ry1), uri in page_links:
            clean_u = sanitize_url(uri)
            if not clean_u:
                continue
            annot_ymid = 0.5 * (ry0 + ry1)
            best_ln = None
            best_dy = 999.0
            for r, ln in page_row_lines:
                if rx0 <= r["x1"] + 4 and rx1 >= r["x0"] - 4:
                    row_ymid = 0.5 * (r["y0"] + r["y1"])
                    dy = abs(row_ymid - annot_ymid)
                    if dy <= max(6.0, 0.75 * r["size"]) and dy < best_dy:
                        best_dy = dy
                        best_ln = ln
            if best_ln is not None and clean_u not in best_ln.links:
                best_ln.links.append(clean_u)
        offset += height

    # Reading order: per page, spanning rows above the columns, then left column, then right column
    lines = _postprocess(_order_columns(lines))
    sizes = [l.size for l in lines for _ in range(max(1, len(l.text) // 20))]
    body = statistics.median(sizes) if sizes else 10.0
    doc = Document(
        lines=lines, body_size=body,
        links=[u for u in (sanitize_url(raw_u) for _, _, raw_u in links) if u],
        meta={
            "source": "pdf", "pages": len(pages), "layout": "two-column" if columns_seen >= 2 else "single-column",
            "has_photo": has_photo, "scanned": total_chars < 80, "extractor": "pdfminer",
        },
    )
    return doc


_BLOCKED_DOMAINS = (
    "job-search-two-beryl.vercel.app",
)


def sanitize_url(uri: str) -> Optional[str]:
    """Repair common template bugs and filter blocked URLs."""
    u = (uri or "").strip()
    if not u or u.lower().startswith(("mailto:", "tel:")):
        return u or None
    m = re.search(r"(https?://)(?:[^/]+/(?:in/)?)?(https?://.+)$", u)
    if m:
        u = m.group(2)
    u = re.sub(r"(linkedin\.com/in/)(?:https?://)?(?:www\.)?linkedin\.com/in/", r"\1", u, flags=re.I)
    u = re.sub(r"(github\.com/)(?:https?://)?(?:www\.)?github\.com/", r"\1", u, flags=re.I)
    if " " in u.strip():
        return None
    u_low = u.lower()
    if any(b in u_low for b in _BLOCKED_DOMAINS):
        return None
    return u


_PAGE_NO_RE = re.compile(r"^(?:page\s*)?\d{1,2}(?:\s*/\s*\d{1,2})?$", re.I)


def _postprocess(lines: List[Line]) -> List[Line]:
    out: List[Line] = []
    pending_bullet: Optional[Line] = None
    for l in lines:
        t = l.text.strip()
        if _PAGE_NO_RE.match(t) or t in {"/", "|", "-"}:
            continue
        if all(c in BULLET_GLYPHS + "-*\t " for c in t):
            pending_bullet = l
            continue
        if pending_bullet is not None and pending_bullet.col == l.col and pending_bullet.page == l.page:
            l.text = "• " + t
        pending_bullet = None
        l.links = [u for u in (sanitize_url(x) for x in l.links) if u]
        # Clean inline blocked URLs or orphaned "Live demo · " when live demo URL was stripped
        for bd in _BLOCKED_DOMAINS:
            if bd in l.text.lower():
                l.text = re.sub(rf"(?:https?://)?{re.escape(bd)}/?", "", l.text, flags=re.I).strip(" •·|")
        out.append(l)
    return out


def _order_columns(lines: List[Line]) -> List[Line]:
    """Per page, rows spanning both columns cut the page into horizontal bands; each band is
    read left column first, then right column. Keeps a full-width summary between header and body."""
    out: List[Line] = []
    for p in sorted({l.page for l in lines}):
        pl = [l for l in lines if l.page == p]
        if not any(l.col == 1 for l in pl):
            out.extend(sorted(pl, key=lambda l: (l.top, l.x0)))
            continue
        spans = sorted([l for l in pl if l.col == -1], key=lambda l: l.top)
        cuts = [s.top for s in spans] + [float("inf")]
        prev = float("-inf")
        span_iter = iter(spans)
        for cut in cuts:
            band = [l for l in pl if l.col in (0, 1) and prev <= l.top < cut]
            out.extend(sorted([l for l in band if l.col == 0], key=lambda l: (l.top, l.x0)))
            out.extend(sorted([l for l in band if l.col == 1], key=lambda l: (l.top, l.x0)))
            if cut != float("inf"):
                out.append(next(span_iter))
            prev = cut
    return out


def _extract_pdf_pypdf2(pdf_bytes: bytes) -> Document:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(p.extract_text() or "" for p in reader.pages)
    lines = [Line(text=normalize_text(t)) for t in raw.splitlines() if normalize_text(t)]
    for l in lines:
        l.caps = _is_caps(l.text)
    return Document(
        lines=lines, links=[u for _, _, u in _pdf_links(pdf_bytes)],
        meta={"source": "pdf", "pages": len(reader.pages), "layout": "unknown", "has_photo": False,
              "scanned": len(raw.strip()) < 80, "extractor": "pypdf2"},
    )


# ─── DOCX / TXT ───────────────────────────────────────────────────────────────

def extract_docx(data: bytes) -> Document:
    import docx  # python-docx
    d = docx.Document(io.BytesIO(data))
    lines: List[Line] = []
    links: List[str] = []
    try:
        for rel in d.part.rels.values():
            if "hyperlink" in rel.reltype and rel.target_ref:
                links.append(rel.target_ref)
    except Exception:
        pass

    def add_par(p):
        text = normalize_text(p.text)
        if not text:
            return
        runs = [r for r in p.runs if r.text.strip()]
        sizes = [r.font.size.pt for r in runs if r.font is not None and r.font.size]
        bold = bool(runs) and all((r.bold or (p.style is not None and p.style.font is not None and p.style.font.bold)) for r in runs)
        style = (p.style.name if p.style is not None else "") or ""
        size = max(sizes) if sizes else (14.0 if style.lower().startswith(("heading", "title")) else 10.5)
        if style.lower().startswith("list") and not text.startswith(tuple(BULLET_GLYPHS + "-*")):
            text = "• " + text
        lines.append(Line(text=text, size=size, bold=bold or style.lower().startswith(("heading", "title")), caps=_is_caps(text)))

    for block in d.element.body.iterchildren():
        tag = block.tag.split("}")[-1]
        if tag == "p":
            add_par(docx.text.paragraph.Paragraph(block, d))
        elif tag == "tbl":
            tbl = docx.table.Table(block, d)
            for row in tbl.rows:
                seen = set()
                cells_text = []
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    for p in cell.paragraphs:
                        add_par(p)
    body = statistics.median([l.size for l in lines]) if lines else 10.5
    return Document(lines=lines, body_size=body, links=links,
                    meta={"source": "docx", "pages": 1, "layout": "single-column", "has_photo": False, "scanned": False, "extractor": "python-docx"})


def extract_txt(text: str) -> Document:
    lines = [Line(text=normalize_text(t)) for t in (text or "").splitlines() if normalize_text(t)]
    for l in lines:
        l.caps = _is_caps(l.text)
    return Document(lines=lines, meta={"source": "text", "pages": 1, "layout": "single-column", "has_photo": False, "scanned": False, "extractor": "text"})


def extract_document(data: Optional[bytes] = None, filename: str = "", text: str = "") -> Document:
    """Entry point: bytes + filename (pdf/docx/txt) or raw text."""
    name = (filename or "").lower()
    if data:
        if name.endswith(".pdf") or data[:5] == b"%PDF-":
            doc = extract_pdf(data)
            if not doc.meta.get("scanned") or not text:
                return doc
        elif name.endswith(".docx") or data[:2] == b"PK":
            try:
                return extract_docx(data)
            except Exception:
                pass
        elif name.endswith(".txt"):
            return extract_txt(data.decode("utf-8", errors="ignore"))
    return extract_txt(text)
