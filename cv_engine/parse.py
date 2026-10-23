"""
Structure parser: turns ordered, styled lines (from extract.py) into a structured CV.

Pipeline
  1. classify headings (exact EN/FR vocabulary, fuzzy for typos, style-aware)
  2. stream lines into sections, column by column; text above a column's first heading
     goes to the header pool (name, headline, contacts, summary)
  3. per-section parsers: entries (experience / projects / education), skills, languages, lists
Nothing is invented here: every field comes from the source document.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .dates import DateSpan, find_date_span, strip_dates, total_months
from .extract import BULLET_GLYPHS, Document, Line, sanitize_url
from .lexicon import (
    AMBIGUOUS_TECH, CITIES, COUNTRIES, DEGREE_WORDS, HEADING_INDEX, LANG_LEVELS, OBJECTIVE_RE,
    PERSONAL_INFO, REMOTE_WORDS, ROLE_WORDS, SCHOOL_WORDS, SPOKEN_LANGS, canonical_tech, norm_key,
    strip_accents,
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.\-]?)?(?:\(\d{1,4}\)[\s.\-]?)?\d{2,4}(?:[\s.\-]?\d{2,4}){2,4}")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;|]+|(?:linkedin\.com|github\.com|gitlab\.com|behance\.net|dribbble\.com)/[^\s,;|]+|\b[\w-]+\.(?:herokuapp\.com|vercel\.app|netlify\.app|github\.io|com|tn|fr|dev|io|me|app|net|org)(?:/[^\s,;|]*)?", re.I)
BULLET_RE = re.compile(rf"^\s*[{re.escape(BULLET_GLYPHS)}\-\*–]+\s*")
LABEL_RE = re.compile(
    r"^\s*(technologies?(?: used| utilisées?| utilisés?)?|tech(?:nical)? stack|stack|environnement(?: technique)?|environment|"
    r"acquired skills(?: and competencies)?|comp[ée]tences acquises|skills used|"
    r"outils|tools|avec|with|web app|mobile app|working solution|technos?|langages?|frameworks?|"
    r"main tasks|tâches(?: principales)?|missions?|réalisations|responsabilités|responsibilities|sujet|subject|"
    r"hosted application|lien|link|live|keywords?|mots[- ]cl[ée]s|tools used|outils utilis[ée]s)\s*:\s*",
    re.I,
)
COMPANY_HINT = re.compile(
    r"\b(labs?|technolog(?:y|ies)|tech|solutions?|software|consulting|group|groupe|sarl|sa|inc|ltd|llc|gmbh|"
    r"corp|company|agency|agence|studio|systems|services|digital|space|education|bank|banque|telecom|"
    r"université|university|faculty|faculté|school|école|institute|institut|startup|s\.a\.|s\.a\.r\.l)\b",
    re.I,
)


STRICT_ROLE = re.compile(
    r"\b(developer|d[ée]veloppeu(?:r|se)|engineer|ing[ée]nieur|intern|internship|stage|stagiaire|alternan\w*|"
    r"founder|fondateur|ceo|cto|manager|consultant|freelance|analyst|designer|lead)\b", re.I)


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Entry:
    title: str = ""
    org: str = ""
    location: str = ""
    dates: Optional[DateSpan] = None
    date_text: str = ""
    bullets: List[str] = field(default_factory=list)
    stack: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)   # header lines we could not label
    kind: str = ""                                    # job | internship | project | education

    def to_dict(self) -> Dict:
        return {
            "title": self.title, "org": self.org, "location": self.location, "date_text": self.date_text,
            "bullets": list(self.bullets), "stack": list(self.stack), "links": list(self.links),
            "kind": self.kind, "extra": list(self.extra),
        }


@dataclass
class CV:
    name: str = ""
    headline: str = ""
    objective: str = ""
    contact: Dict[str, str] = field(default_factory=dict)
    links: Dict[str, str] = field(default_factory=dict)
    personal: List[str] = field(default_factory=list)
    summary: str = ""
    experience: List[Entry] = field(default_factory=list)
    projects: List[Entry] = field(default_factory=list)
    education: List[Entry] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)            # canonical tech, in source order
    skill_groups: List[Tuple[str, List[str]]] = field(default_factory=list)  # source categories
    unknown_skills: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    languages: List[Dict[str, str]] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    awards: List[str] = field(default_factory=list)
    activities: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    lang: str = "en"
    meta: Dict = field(default_factory=dict)
    sections_found: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name, "headline": self.headline, "objective": self.objective,
            "contact": dict(self.contact), "links": dict(self.links), "personal": list(self.personal),
            "summary": self.summary,
            "experience": [e.to_dict() for e in self.experience],
            "projects": [e.to_dict() for e in self.projects],
            "education": [e.to_dict() for e in self.education],
            "skills": list(self.skills), "skill_groups": [[c, list(i)] for c, i in self.skill_groups],
            "unknown_skills": list(self.unknown_skills), "soft_skills": list(self.soft_skills),
            "languages": list(self.languages), "certifications": list(self.certifications),
            "awards": list(self.awards), "activities": list(self.activities), "interests": list(self.interests),
            "lang": self.lang, "meta": dict(self.meta), "sections_found": list(self.sections_found),
        }

    def experience_months(self, kinds=("job", "internship")) -> int:
        return total_months([e.dates for e in self.experience if e.dates and e.kind in kinds])


# ─── Heading detection ────────────────────────────────────────────────────────

_FUZZY_KEYS = list(HEADING_INDEX.keys())


_SECTION_HEADER_PHRASE_RE: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:core|key|technical|professional|it|digital|hard)\s+(?:&\s+\w+\s+)?(?:skills|competencies|proficiencies)$", re.I), "skills"),
    (re.compile(r"^(?:relevant|professional|work|career|industry)\s+(?:work\s+)?(?:experience|history|background)$", re.I), "experience"),
    (re.compile(r"^(?:selected|key|notable|academic|personal|technical)\s+projects$", re.I), "projects"),
    (re.compile(r"^(?:academic|educational)\s+(?:background|qualifications|history)$", re.I), "education"),
    (re.compile(r"^(?:executive|professional|career)\s+(?:summary|profile|overview)$", re.I), "summary"),
]


def heading_section(line: Line, body_size: float, plain: bool) -> Optional[str]:
    raw = line.text.strip()
    if not raw or raw.endswith(".") or LABEL_RE.match(raw):
        return None
    parts = [p for p in raw.split("\t") if p.strip()]
    cand = norm_key(raw.replace("\t", " ").rstrip(":—–-").strip())
    words = cand.split()
    if not words or len(words) > 6 or len(cand) > 48:
        return None
    styled = plain or line.caps or line.bold or line.size >= body_size * 1.10
    if not styled:
        return None
    # Prevent wrapped lowercase sentence tails ("experiences") or job/school titles ("Stage de fin d'étude", "Horizen education") from matching
    if not plain and raw[:1].islower():
        return None
    if cand in HEADING_INDEX:
        return HEADING_INDEX[cand]
    # two headings side by side ("PROGRAMMING SKILLS\tTECHNOLOGY SKILLS")
    if len(parts) > 1:
        secs = [HEADING_INDEX.get(norm_key(p.rstrip(":"))) for p in parts]
        if all(secs):
            return secs[0]
    if re.search(r"\d", cand) or "|" in raw:
        return None
    close = difflib.get_close_matches(cand, _FUZZY_KEYS, n=1, cutoff=0.84)
    if close:
        return HEADING_INDEX[close[0]]
    # Fallback only for genuine major section headers (ALL CAPS or >= 1.18x body size)
    if (plain or line.caps or line.size >= body_size * 1.18) and ":" not in raw.rstrip(":"):
        for pat, sec_name in _SECTION_HEADER_PHRASE_RE:
            if pat.match(cand):
                return sec_name
    return None


def detect_language(text: str) -> str:
    t = " " + strip_accents(text.lower()) + " "
    fr = sum(t.count(w) for w in (" de ", " des ", " et ", " le ", " la ", " les ", " du ", " une ", " pour ", " avec ", " stage ", " formation ", " competences "))
    en = sum(t.count(w) for w in (" the ", " and ", " of ", " to ", " with ", " for ", " in ", " developed ", " experience ", " skills "))
    return "fr" if fr > en * 1.15 else "en"


# ─── Small helpers ────────────────────────────────────────────────────────────

def is_bullet(text: str) -> bool:
    return bool(BULLET_RE.match(text)) and not re.match(r"^\s*-\s*\d", text)


def strip_bullet(text: str) -> str:
    return BULLET_RE.sub("", text).replace("\t", " ").strip()


def tech_tokens(text: str) -> Tuple[List[str], List[str]]:
    """Split a list-like string into (canonical tech, leftover tokens)."""
    t = LABEL_RE.sub("", text)
    t = re.sub(r"\b(?:etc\.?|and|et|&amp;)\b", ",", t, flags=re.I)
    pieces = re.split(r"\s*(?:,|;|\||•|·|/(?!\s*(?:css|c\+\+|ux|ui|cd)(?:\b|$))|\t|\s{2,}|\s\+\s|\(|\))\s*", t)
    found, left = [], []
    for p in pieces:
        p = p.strip(" :-–").rstrip(".").strip()
        if not p:
            continue
        c = canonical_tech(p)
        if c:
            found.append(c)
            continue
        # "Angular Angular-Material TypeScript SCSS" → try word by word (skipping ambiguous English words)
        words = p.split()
        if len(words) > 1:
            i, acc = 0, []
            while i < len(words):
                bi = canonical_tech(" ".join(words[i:i + 2])) if i + 1 < len(words) else None
                if bi:
                    acc.append(bi); i += 2; continue
                w_low = words[i].strip(" :-–.").lower()
                uni = None if w_low in AMBIGUOUS_TECH else canonical_tech(words[i])
                if uni:
                    acc.append(uni)
                else:
                    left.append(words[i])
                i += 1
            found.extend(acc)
            continue
        left.append(p)
    out = []
    for f in found:
        if f not in out:
            out.append(f)
    return out, left


_SENTENCE_START = re.compile(
    r"^(?:implemented|developed|built|designed|created|utili[sz]ed|used|using|experience|experienced|proficient|"
    r"worked|working|conducted|managed|improved|focused|delivered|integrated|deployed|led|participated|"
    r"développement|developpement|development|réalisation|conception|création|utilisation|gestion|mise en|"
    r"j'ai|i |we |the |a |an |le |la |les |un |une )",
    re.I,
)


def looks_like_stack(text: str) -> bool:
    t = strip_bullet(text)
    if len(t) > 160 or t.endswith(".") and len(t.split()) > 8:
        return False
    if LABEL_RE.match(t) and re.match(r"^\s*(technolog|tech|stack|environ|outils|tools|avec|with|web app|mobile app|working solution|technos?|langages?|frameworks?)", t, re.I):
        return True
    if _SENTENCE_START.match(t):
        return False
    found, left = tech_tokens(t)
    meaningful_left = [w for w in left if len(w) > 2 and not re.fullmatch(r"[\W\d]+", w)]
    return len(found) >= 2 and len(found) >= 1.5 * len(meaningful_left) or (len(found) >= 1 and not meaningful_left)


def split_location(text: str) -> Tuple[str, str]:
    """'Hippo labs Remote' -> ('Hippo labs', 'Remote'); 'Flesk Consulting, Monastir' -> ('Flesk Consulting', 'Monastir')."""
    t = text.strip(" ,|–—-")
    low = strip_accents(t.lower())
    m = REMOTE_WORDS.search(t)
    if m and m.end() >= len(t) - 1:
        return t[: m.start()].strip(" ,|–—-("), t[m.start():].strip(" ()")
    parts = [p.strip() for p in re.split(r"\s*(?:,|\||–|—| - )\s*", t) if p.strip()]
    if len(parts) >= 2:
        tail = ", ".join(parts[1:])
        if is_location(tail):
            return parts[0], tail
    words = t.split()
    # trailing "Monastir Tunisia" / "Sousse" — but keep "Faculty of Sciences of Monastir" intact
    for k in (3, 2, 1):
        if len(words) > k:
            tail = " ".join(words[-k:])
            head = " ".join(words[:-k]).strip(" ,")
            tl = strip_accents(tail.lower()).strip(",")
            if all(any(w == c or w in c.split() for c in list(CITIES) + list(COUNTRIES)) for w in tl.replace(",", " ").split()):
                if re.search(r"\b(of|de|des|du|d'|la|le|à|in)$", head, re.I):
                    continue
                return head, tail.strip(" ,")
    return t, ""


def is_location(text: str) -> bool:
    raw = (text or "").strip()
    if REMOTE_WORDS.fullmatch(raw.strip(" ()")):
        return True
    t = strip_accents(raw.lower()).strip(" ,.")
    t = REMOTE_WORDS.sub(" ", t)
    t = re.sub(r"[()]", " ", t)
    t = re.sub(r"\b\d{4,5}\b", "", t)          # years and postal codes ("Monastir, Tunisia - 5000")
    toks = [w for w in re.split(r"[\s,>/|–—-]+", t) if w]
    if not toks or len(toks) > 5:
        return False
    names = set(CITIES) | set(COUNTRIES)
    return all(any(w == n or w in n.split() for n in names) for w in toks)


LINK_LABEL_RE = re.compile(
    r"^(?:live demo|demo|live|github|gitlab|code|source(?: code)?|website|web site|site|app store|google play|"
    r"play store|link|lien|repo|repository|portfolio|video|vidéo|apk)$|^[\w-]+\.(?:tn|com|io|app|dev|me|net|org|fr)(?:/\S*)?$",
    re.I,
)


# ─── Main parser ──────────────────────────────────────────────────────────────

def parse_document(doc: Document) -> CV:
    cv = CV(meta=dict(doc.meta), raw_text=doc.text)
    plain = doc.meta.get("source") == "text"
    body = doc.body_size or 10.0

    # 1) Stream lines into sections (header pool for lines before a column's first heading)
    sections: Dict[str, List[Line]] = {}
    header: List[Line] = []
    current: Optional[str] = None
    prev: Optional[Line] = None
    for ln in doc.lines:
        if prev is not None and ln.page == prev.page and ln.col != prev.col and not (prev.col == -1 and ln.col == 0 and current):
            current = None  # new column → wait for its first heading
        if prev is not None and prev.col == -1 and ln.col != -1:
            current = current if ln.col == 0 and current else None
        sec = heading_section(ln, body, plain)
        if sec:
            current = sec
            sections.setdefault(sec, [])
            if sec not in cv.sections_found:
                cv.sections_found.append(sec)
            # inline content after "Skills: Python, Java" style headings
            parts = ln.text.split(":", 1)
            if len(parts) == 2 and parts[1].strip() and norm_key(parts[0]) in HEADING_INDEX:
                sections[sec].append(
                    Line(text=parts[1].strip(), size=ln.size, bold=False, col=ln.col, page=ln.page, links=ln.links)
                )
            prev = ln
            continue
        # inline heading with content: "Languages : Arabic, English" / "LANGUES : ..." in plain docs
        m = re.match(r"^\s*([A-Za-zÀ-ÿ' &]{3,40})\s*:\s*(.+)$", ln.text)
        if m and current is None and norm_key(m.group(1)) in HEADING_INDEX:
            s2 = HEADING_INDEX[norm_key(m.group(1))]
            sections.setdefault(s2, []).append(Line(text=m.group(2), size=ln.size, bold=False, col=ln.col, page=ln.page, links=ln.links))
            prev = ln
            continue
        if current is None:
            header.append(ln)
        else:
            sections[current].append(ln)
        prev = ln

    cv.lang = detect_language(doc.text)

    # 2) Header: name, headline, contacts, summary
    _parse_header(cv, header, doc, body)
    if "contact" in sections:
        _parse_contact_lines(cv, sections["contact"])

    # 3) Sections
    if "summary" in sections:
        txt = " ".join(strip_bullet(l.text) for l in sections["summary"])
        txt = _join_hyphenated(txt)
        if OBJECTIVE_RE.search(txt) and len(txt.split()) < 25 and not cv.objective:
            cv.objective = txt
        else:
            cv.summary = (cv.summary + " " + txt).strip() if cv.summary else txt
    for sec in ("experience", "projects"):
        if sec in sections:
            getattr(cv, sec).extend(parse_entries(_prejoin(sections[sec]), sec, body, cv.lang))
    if "education" in sections:
        cv.education.extend(parse_education(_prejoin(sections["education"]), cv.lang))
    # Combined "Experience & Projects" sections: move project-like entries
    _split_mixed_experience(cv)
    if "skills" in sections:
        _parse_skills(cv, sections["skills"])
    if "languages" in sections:
        cv.languages.extend(parse_languages([l.text for l in sections["languages"]]))
    if "soft_skills" in sections:
        cv.soft_skills = _list_items(sections["soft_skills"])
    if "certifications" in sections:
        cv.certifications = _paragraph_items(sections["certifications"])
    if "awards" in sections:
        cv.awards = _paragraph_items(sections["awards"])
    if "activities" in sections:
        cv.activities = _paragraph_items(sections["activities"])
    if "interests" in sections:
        cv.interests = _list_items(sections["interests"])

    # 4) Evidence skills: tech used inside experience/projects that the skills section missed
    for e in cv.experience + cv.projects:
        for t in e.stack:
            if canonical_tech(t) and t not in cv.skills:
                cv.skills.append(t)

    # 5) Links: map leftover URLs (only linkedin/github/email/phone, never guess portfolio from project links)
    for u in doc.links:
        u2 = sanitize_url(u)
        if u2:
            _register_link(cv, u2, allow_portfolio=False)

    # 6) Footers ("YASSINE YOUSSEF - RESUME") leak into the last list section
    if cv.name:
        nk = norm_key(cv.name)
        for attr in ("interests", "activities", "certifications", "awards", "soft_skills"):
            setattr(cv, attr, [i for i in getattr(cv, attr) if nk not in norm_key(i)])
    return cv


# ─── Header ───────────────────────────────────────────────────────────────────

def _parse_header(cv: CV, header: List[Line], doc: Document, body: float) -> None:
    pool = list(header)
    first_page = [l for l in doc.lines if l.page == 0]
    # Name: largest text on page 1 that looks like a person's name
    def name_like(t: str) -> bool:
        t0 = re.split(r"\s*\|\|?\s*|\t", t)[0].strip()
        words = t0.split()
        return (1 < len(words) <= 5 and not re.search(r"[@\d:/]", t0) and not ROLE_WORDS.search(t0)
                and not HEADING_INDEX.get(norm_key(t0)) and sum(c.isalpha() for c in t0) >= 0.8 * len(t0.replace(" ", "")))
    cands = sorted([l for l in first_page if name_like(l.text)], key=lambda l: (-l.size, l.top))
    name_line = cands[0] if cands else None
    if name_line is not None:
        parts = [p.strip() for p in re.split(r"\s*\|\|?\s*|\t", name_line.text) if p.strip()]
        cv.name = _title_case_name(parts[0])
        if len(parts) > 1:
            cv.headline = _clean_headline(" ".join(parts[1:]))
        if name_line in pool:
            pool.remove(name_line)
    elif pool:
        cv.name = _title_case_name(pool.pop(0).text)

    # Header rows that merge a headline with a right-aligned contact ("Software Engineer\tMonastir, Tunisia")
    # are split into independent lines so neither the headline nor the contact is lost.
    split_pool: List[Line] = []
    for l in pool:
        parts = [p.strip() for p in l.text.split("\t") if p.strip()]
        if len(parts) > 1:
            for p in parts:
                split_pool.append(Line(text=p, size=l.size, bold=l.bold, x0=l.x0, x1=l.x1, top=l.top,
                                       page=l.page, col=l.col, links=list(l.links), caps=p.isupper()))
        else:
            split_pool.append(l)
    pool[:] = split_pool

    # Headline: first short role-like line in header (bigger than body, or containing role words)
    for idx_l, l in enumerate(list(pool)):
        t = l.text.replace("\t", " ").strip()
        if OBJECTIVE_RE.search(t) and len(t.split()) <= 14:
            cv.objective = cv.objective or t.strip(" .")
            pool.remove(l)
            continue
        if not cv.headline and len(t.split()) <= 9 and not EMAIL_RE.search(t) and not re.search(r"\d{4,}", t) \
                and sum(ch.isdigit() for ch in t) < 4 \
                and (ROLE_WORDS.search(t) or (l.size > body * 1.15 and not is_location(t))) and not URL_RE.search(t) \
                and not t.startswith('"'):
            pool.remove(l)
            # Check if the immediately following header line is a wrapped continuation of an all-caps/bold headline
            # e.g. "DIPLÔMÉ EN LICENCE FONDAMENTALE" + "EN SCIENCES DE L'INFORMATIQUE"
            if pool and pool[0].col == l.col and (pool[0].bold or pool[0].caps):
                t_next = pool[0].text.replace("\t", " ").strip()
                if (
                    len(t_next.split()) <= 6
                    and not EMAIL_RE.search(t_next)
                    and not URL_RE.search(t_next)
                    and not is_location(t_next)
                    and not heading_section(pool[0], body, False)
                    and re.match(r"^(?:en|in|of|de|d['’]|&|and|et|sp[ée]cialit[ée]|option)\b", t_next, re.I)
                ):
                    t = f"{t} {t_next}"
                    pool.pop(0)
            cv.headline = _clean_headline(t)
    _parse_contact_lines(cv, pool, header_mode=True)


def _title_case_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if s.isupper() or s.islower():
        return " ".join(w.capitalize() if not re.match(r"^(de|da|del|el|ben|bin|van|von|le|la)$", w.lower()) else w.lower() for w in s.split())
    # "Achraf MABROUK" -> "Achraf Mabrouk"
    return " ".join(w.capitalize() if w.isupper() and len(w) > 2 else w for w in s.split())


def _clean_headline(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" |-–—:")
    if s.isupper():
        small = {"and", "of", "&", "in", "for", "de", "et", "en", "des"}
        s = " ".join(w.lower() if w.lower() in small else (w if w in {"AI", "ML", "QA", "UI", "UX", "IT", "PHP", "IOS", "SQL"} else w.capitalize()) for w in s.split())
        s = s.replace("Ios", "iOS")
    return s


def _register_link(cv: CV, url: str, allow_portfolio: bool = True) -> None:
    clean_u = sanitize_url(url)
    if not clean_u:
        return
    low = clean_u.lower()
    if low.startswith("mailto:"):
        cv.contact.setdefault("email", clean_u[7:])
        return
    if low.startswith("tel:"):
        cv.contact.setdefault("phone", clean_u[4:].strip())
        return
    full = clean_u if low.startswith("http") else "https://" + clean_u.lstrip("/")
    if "linkedin.com/in/" in low:
        cv.links.setdefault("linkedin", full)
    elif re.search(r"github\.com/[^/]+/?$", low):
        cv.links.setdefault("github", full)
    elif "github.com/" in low or "gitlab.com/" in low:
        cv.links.setdefault("github", re.sub(r"(github\.com/[^/]+).*", r"\1", full))
    elif any(x in low for x in ("youtu", "play.google", "apps.apple", "drive.google")):
        return
    elif allow_portfolio and not cv.links.get("portfolio"):
        cv.links["portfolio"] = full


def _parse_contact_lines(cv: CV, lines: List[Line], header_mode: bool = False) -> None:
    prose: List[str] = []
    for l in lines:
        for u in l.links:
            _register_link(cv, u, allow_portfolio=True)
        if header_mode and l.text.strip().startswith(('"', "«", "“")):
            continue  # mottos / quotes
        for part in re.split(r"\t|\s\|\|?\s|\s•\s|\s·\s", l.text):
            t = part.strip()
            if not t:
                continue
            t = re.sub(r"^(?:address|adresse|phone|tel|tél|téléphone|mobile|email|e-mail|mail|linkedin|github|portfolio|website|site web|site|location|localisation)\s*:\s*", "", t, flags=re.I)
            consumed = False
            for em in EMAIL_RE.findall(t):
                cv.contact.setdefault("email", em.lower() if em.isupper() else em)
                t = t.replace(em, " ")
                consumed = True
            for u in URL_RE.findall(t):
                if "@" in u:
                    continue
                _register_link(cv, u.rstrip(".)"), allow_portfolio=True)
                t = t.replace(u, " ")
                consumed = True
            if re.search(r"@[\w-]{3,}", t) and not EMAIL_RE.search(t):
                consumed = True  # "@achraf-mabrouk95" handle; URL comes from the link annotation
                t = re.sub(r"@[\w-]+", " ", t)
            t = re.sub(r"\+\s*\((\d{1,4})\)", r"+\1", t)
            ph = PHONE_RE.search(t)
            if ph and len(re.sub(r"\D", "", ph.group(0))) >= 8:
                cv.contact.setdefault("phone", re.sub(r"\s+", " ", ph.group(0)).strip())
                t = t.replace(ph.group(0), " ")
                consumed = True
            t = re.sub(r"\s+", " ", t).strip(" |,•·-–—")
            if not t:
                continue
            if PERSONAL_INFO.search(t) and len(t.split()) <= 6:
                cv.personal.append(t)
                continue
            if is_location(t) or re.match(r"^\d{4}\s+\w+", t) and is_location(re.sub(r"\d{4}", "", t)):
                cv.contact.setdefault("location", _clean_location(t))
                continue
            if header_mode and (len(t.split()) >= 6 or (prose and t[:1].islower())):
                prose.append(t)
            elif header_mode and t.startswith('"'):
                continue  # quotes / mottos
            elif not consumed and header_mode and len(t.split()) <= 4 and not cv.contact.get("location") and re.search(r"[A-Za-z]", t):
                # Short unknown header bits (e.g. 'Ahmed Dhia Gara' LinkedIn label) are ignored
                continue
    if prose and not cv.summary:
        txt = _join_hyphenated(" ".join(prose))
        if OBJECTIVE_RE.search(txt) and len(txt.split()) < 20:
            cv.objective = cv.objective or txt
        else:
            cv.summary = txt


def _clean_location(t: str) -> str:
    t = re.sub(r"\b\d{4,5}\b", "", t).strip(" .")
    t = re.sub(r"\s*[–—-]\s*$", "", t).strip(" .,")
    parts = [p.strip(" -–—") for p in re.split(r"[,]", t) if p.strip(" -–—")]
    parts = [p.title() if p.islower() else p for p in parts]
    # "Tunisia, 5000 Monastir" -> "Monastir, Tunisia"
    if len(parts) == 2 and strip_accents(parts[0].lower()) in COUNTRIES:
        parts = [parts[1], parts[0]]
    return ", ".join(parts)


_COMPOUND_HYPHEN_PREFIXES = {
    "cross", "full", "real", "high", "multi", "self", "user", "client", "server", "object", "event",
    "data", "cloud", "web", "open", "end", "to", "post", "pre", "co", "non", "well", "solution",
    "rule", "role", "time", "cost", "hands", "state", "feature", "peer", "third", "first", "second",
    "back", "front", "low", "long", "short",
}


def _join_hyphenated(t: str) -> str:
    def _repl(m):
        w1, w2 = m.group(1), m.group(2)
        if not w2.islower():
            return m.group(0)
        if len(w1) <= 2 or w1.lower() in _COMPOUND_HYPHEN_PREFIXES:
            return f"{w1}-{w2}"
        return w1 + w2

    t = re.sub(r"(\w+)-\s+(\w+)", _repl, t)
    return re.sub(r"\s+", " ", t).strip()


# ─── Entries (experience / projects / education) ──────────────────────────────

_DATE_WORD = re.compile(
    r"^(?:from|de|du|to|au|à|a|since|depuis|until|present|presnt|pr[ée]sent|current|now|aujourd'?hui|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"janv(?:ier)?|f[ée]vr?(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[uû]t|septembre|octobre|novembre|d[ée]c(?:embre)?|"
    r"summer|[ée]t[ée]|winter|hiver|spring|printemps|(?:19|20)\d{2}|\d{1,2}/(?:19|20)\d{2}|[-–—/,.])$",
    re.I,
)


def _is_date_fragment(t: str) -> bool:
    t = t.strip()
    if not t or len(t) > 42:
        return False
    toks = [x for x in re.split(r"\s+|(?<=\d)(?=[-–])|(?<=[-–])(?=\d)", t.replace(",", " , ")) if x]
    if not toks or not all(_DATE_WORD.match(x) for x in toks):
        return False
    return bool(re.search(r"(19|20)\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|janv|f[ée]v|avr|mai|juin|juil|ao[uû]t|d[ée]c|summer|[ée]t[ée]", t, re.I))


_PROJECT_PIPE_HEADER_RE = re.compile(
    r"^[^•●▪■◦\t]{2,85}\s+\|\s+(?:live\s*demo|demo|github|gitlab|[\w-]+\.(?:tn|com|io|app|dev|net|org|fr)|[A-Za-z0-9+#.\s,/()-]{2,45})$",
    re.I,
)
_PROJECT_DASH_HEADER_RE = re.compile(
    r"^[A-Z][\w\s.+-]{1,35}\s+[—–]\s+[A-Z][^.!?]{3,70}$"
)


def _headerish(l: Line, body: float) -> bool:
    t = re.sub(r"\s+\.$", ".", l.text.strip())
    if is_bullet(t):
        return False
    words = t.replace("\t", " ").split()
    if len(words) > 16:
        return False
    has_date = bool(find_date_span(t)) and len(words) <= 14
    styled = l.bold or l.size > body + 1.4 or l.caps
    is_proj_hdr = bool(_PROJECT_PIPE_HEADER_RE.match(t) or _PROJECT_DASH_HEADER_RE.match(t))
    if is_proj_hdr or (has_date and (styled or "\t" in t or re.search(r"\([^)]*\d{4}[^)]*\)\s*$", t))):
        return True
    if re.match(r"^(?:c['’][ée]tai[st]|d[ée]velopper\b|il s['’]agit|it is\b|this is\b)", t, re.I) or _SENTENCE_START.match(t):
        return False
    tab_hdr = "\t" in t and len(words) <= 12 and (
        has_date
        or styled
        or any(is_location(p.strip()) or ROLE_WORDS.search(p) or DEGREE_WORDS.search(p) for p in t.split("\t"))
    )
    role_dash_hdr = (
        not t.endswith((".", ";"))
        and len(words) <= 8
        and bool(STRICT_ROLE.search(t))
        and (" - " in t or is_location(t.split(",")[-1].strip()))
    )
    return has_date or (styled and not t.endswith((".", ";")) and len(words) <= 14) or tab_hdr or role_dash_hdr


def parse_entries(lines: List[Line], section: str, body: float, lang: str) -> List[Entry]:
    entries: List[Entry] = []
    cur: Optional[Entry] = None
    date_frags: List[str] = []
    in_body = False          # we've seen bullets/description for the current entry
    stack_mode = False       # previous line was a "Technologies used:" label
    saw_body_stack = False   # we've already parsed a body stack line for this entry
    last_glyph = False       # last bullet came from a real bullet glyph
    title_sig: Optional[Tuple[float, bool]] = None
    kind = section[:-1] if section != "education" else "education"

    def finish():
        nonlocal cur, date_frags
        if cur is None:
            return
        if date_frags and not cur.dates:
            found = find_date_span(" ".join(date_frags))
            if found:
                cur.dates = found[0]
        if cur.dates:
            cur.date_text = cur.dates.display(lang)
        _finalize_entry(cur, section)
        if cur.title or cur.org or cur.bullets:
            entries.append(cur)
        cur, date_frags = None, []

    for l in lines:
        raw = l.text.strip()
        if not raw:
            continue
        # Skip job-board auto-summary headers ("Experience by\tTelecommunications : 1 year", "departments", "IT Software : 1 year")
        if section == "experience" and cur is None and re.match(
            r"^(?:experience\s+by\b|departments\s*$|[\w\s/&+-]{2,28}\s*:\s*\d+\s*(?:years?|months?|ans?|mois)\b)",
            raw.replace("\t", " "),
            re.I,
        ):
            continue
        # Strip leading duration sub-column ("1 year\tBucurești | Telecommunications")
        raw = re.sub(
            r"^\d+\s*(?:years?|months?|ans?|mois)(?:\s+(?:and|et)\s+\d+\s*(?:years?|months?|ans?|mois))?\t+",
            "",
            raw,
            flags=re.I,
        ).strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split("\t") if p.strip()]
        # Peel a date fragment from a date sub-column ("From March 2022 to\tPython Developer")
        frag = None
        if len(parts) >= 2 and _is_date_fragment(parts[0]):
            frag, parts = parts[0], parts[1:]
        elif len(parts) >= 2 and _is_date_fragment(parts[-1]):
            frag, parts = parts[-1], parts[:-1]
        else:
            m = re.match(r"^((?:from|de)\s+\S+(?:\s+\d{4})?\s+(?:to|au|à))\s+(.+)$", raw, re.I)
            if m and _is_date_fragment(m.group(1)):
                frag, parts = m.group(1), [m.group(2)]
        text = "\t".join(parts)
        clean = text.replace("\t", " ").strip()
        bullet = is_bullet(text)
        label_only = bool(LABEL_RE.match(strip_bullet(clean))) and not LABEL_RE.sub("", strip_bullet(clean)).strip()
        stack_label = label_only and re.match(
            r"^\s*(technolog|tech|stack|environ|acquired skills|comp[ée]tences acquises|skills used|outils|tools|avec|with|web app|mobile app|working solution|technos?|langages?|frameworks?)",
            strip_bullet(clean),
            re.I,
        )

        if cur is not None and label_only:
            stack_mode = bool(stack_label)
            in_body = True
            continue
        if cur is not None and stack_mode and not bullet and not _headerish_strict(l, text, body):
            cur.stack.extend(s for s in stack_items(clean) if s not in cur.stack)
            saw_body_stack = True
            stack_mode = False
            continue
        stack_mode = False

        is_date_subitem = (
            in_body
            and raw.lstrip().startswith("|")
            and not strip_dates(re.sub(r"^\|\s*(?:en\s+)?", "", clean, flags=re.I)).strip(" :,-")
        )
        headerish = (
            not is_date_subitem
            and (
                _headerish(Line(text=text, size=l.size, bold=l.bold, caps=l.caps), body)
                or (frag is not None and not bullet)
            )
        )
        is_stack_line = looks_like_stack(clean)
        sig = (round(l.size, 1), l.bold)

        starts_new = False
        if headerish and not bullet:
            if cur is None:
                starts_new = True
            elif in_body:
                starts_new = not is_stack_line or frag is not None
            elif title_sig and sig == title_sig and (cur.dates or date_frags) and not is_stack_line and section != "education" and (cur.title and cur.org):
                starts_new = True
            elif section == "education" and _edu_field_full(cur, text):
                starts_new = True
        elif (
            cur is not None
            and in_body
            and saw_body_stack
            and len(clean.split()) >= 3
            and not _STACK_NOISE.fullmatch(clean)
            and not is_stack_line
            and not bullet
            and not label_only
            and not is_date_subitem
            and not re.match(r"^(?:avec|with|lien|link|hosted|live)\b", clean, re.I)
        ):
            # When an entry already concluded with a "Technologies used:" stack line, the next prose/title line starts a new entry
            starts_new = True

        if frag is not None and cur is not None and not is_date_subitem:
            if not in_body and date_frags and _completes_range(date_frags, frag):
                starts_new = False
            elif in_body:
                starts_new = True

        if starts_new:
            finish()
            cur = Entry(kind=kind)
            in_body = False
            saw_body_stack = False
            last_glyph = False
            title_sig = sig
        if cur is None:
            cur = Entry(kind=kind)
            title_sig = sig
        if frag and not is_date_subitem:
            date_frags.append(frag)
        for u in l.links:
            if u not in cur.links and not u.lower().startswith(("mailto:", "tel:")):
                cur.links.append(u)

        if is_date_subitem:
            cur.bullets.append(re.sub(r"^\|\s*(?:en\s+)?", "", clean, flags=re.I).strip())
            continue

        if bullet:
            body_txt = strip_bullet(text)
            if URL_RE.fullmatch(body_txt.strip(" .")):
                u = body_txt.strip(" .")
                u = u if u.startswith("http") else "https://" + u
                if u not in cur.links:
                    cur.links.append(u)
                in_body = True
                continue
            if LABEL_RE.match(body_txt) and looks_like_stack(body_txt):
                cur.stack.extend(s for s in stack_items(body_txt) if s not in cur.stack)
                saw_body_stack = True
            elif is_stack_line and len(body_txt.split()) <= 10:
                cur.stack.extend(s for s in stack_items(body_txt) if s not in cur.stack)
                saw_body_stack = True
            elif label_only:
                pass
            else:
                if re.match(r"^\s*(main tasks|tâches(?: principales)?|missions?|responsabilités|responsibilities)\s*:", body_txt, re.I):
                    body_txt = LABEL_RE.sub("", body_txt).strip()
                if body_txt:
                    cur.bullets.append(body_txt)
                    last_glyph = True
            in_body = True
            continue

        # Wrapped company line right after "| Mar, 2022 Réalisé au sein de l'entreprise Barthauer" -> "Software Tunisia."
        if (not in_body and cur.title and cur.org and len(clean.split()) <= 3
                and clean[:1].isupper() and COMPANY_HINT.search(clean) and not STRICT_ROLE.search(clean)):
            cur.org = f"{cur.org} {clean.rstrip('.')}"
            continue

        if not in_body and headerish:
            _absorb_header_line(cur, text, section)
            continue
        if (not in_body and cur.title and not cur.org and section == "experience" and len(clean.split()) <= 7
                and (not clean.endswith(".") or len(clean.split()) <= 5) and not is_stack_line and not _SENTENCE_START.match(clean)):
            _absorb_header_line(cur, text.rstrip("."), section)
            continue

        # If previous bullet was a date-only sub-item ("Mar, 2022") and current line starts with "Avec ", merge them
        if cur.bullets and _is_date_fragment(re.sub(r"^en\s+", "", cur.bullets[-1], flags=re.I)) and re.match(r"^(?:avec|with)\b", clean, re.I):
            cur.bullets[-1] = f"{cur.bullets[-1]} — {clean}"
            for s in stack_items(re.sub(r"^(?:avec|with)\s+", "", clean, flags=re.I)):
                if s not in cur.stack:
                    cur.stack.append(s)
            continue

        # Non-bullet body text
        # If the previous bullet is an unfinished sentence and current line is a short wrapped sentence tail ending with '.', join it first
        if (
            cur.bullets
            and not LABEL_RE.match(clean)
            and len(clean.split()) <= 4
            and clean.endswith(".")
            and not cur.bullets[-1].rstrip().endswith((".", "!", "?", ":"))
        ):
            cur.bullets[-1] = _join_hyphenated(cur.bullets[-1] + " " + clean)
            in_body = True
            continue
        if is_stack_line or re.match(r"^(?:avec|with)\s*:\s*", clean, re.I):
            cur.stack.extend(s for s in stack_items(clean) if s not in cur.stack)
            if in_body:
                saw_body_stack = True
            continue
        if re.match(r"^(sujet|subject|lien|link|hosted application|main tasks|tâches|missions?)\s*:", clean, re.I):
            clean = LABEL_RE.sub("", clean).strip()
            for u in URL_RE.findall(clean):
                u_clean = u.rstrip(".)")
                u_full = u_clean if u_clean.startswith("http") else "https://" + u_clean
                if u_full not in cur.links:
                    cur.links.append(u_full)
            if URL_RE.fullmatch(clean.strip(" .")):
                continue
        if not clean:
            continue
        if URL_RE.fullmatch(clean.strip(" .")):
            u = clean.strip(" .")
            if u not in cur.links:
                cur.links.append(u if u.startswith("http") else "https://" + u)
            continue
        if cur.bullets and _is_continuation(cur.bullets[-1], clean, last_glyph):
            cur.bullets[-1] = _join_hyphenated(cur.bullets[-1] + " " + clean)
        else:
            cur.bullets.append(clean)
            last_glyph = False
        in_body = True
    finish()
    return entries


def _headerish_strict(l: Line, text: str, body: float) -> bool:
    """A real entry header (used to leave stack mode): has a date or is visibly styled as a title."""
    t = text.replace("\t", " ")
    return bool(find_date_span(t)) or (l.size > body + 1.0) or (l.bold and ROLE_WORDS.search(t) is not None)


_STACK_NOISE = re.compile(r"\b(framework|library|librairie|module|language|langage|tools?|outils?)\b", re.I)


def stack_items(text: str) -> List[str]:
    """Items of a tech-stack line: canonical names when known, otherwise the original token (kept short)."""
    t = LABEL_RE.sub("", strip_bullet(text))
    t = re.sub(
        r"^(?:proficient in|utili[sz]ed(?: skills in)?|experienced in|experience (?:with|in)|skilled in|familiar with|knowledge of)\s+",
        "",
        t,
        flags=re.I,
    )
    out: List[str] = []
    for p in re.split(r"\s*(?:,|;|\||•|·|\s\+\s|\t|\s{2,}|\s/\s|\s[-–—]\s)\s*", t):
        p = re.sub(
            r"^(?:front[- ]?end|back[- ]?end|web\s+app|mobile\s+app|desktop\s+app|database|base\s+de\s+donn[ée]es|api|ui|ux|design|serveur|server|client)\s*:\s*",
            "",
            p.strip(),
            flags=re.I,
        )
        p = p.strip(" .:-–—")
        # keep balanced parentheses ("Python (Web Scraping)"), drop only stray ones
        if p.count("(") != p.count(")"):
            p = p.strip("()").strip()
            if p.count("(") > p.count(")"):
                p += ")"
        if not p or re.fullmatch(r"(?:etc|and|et|\W+)", p, re.I):
            continue
        if _DATE_WORD.fullmatch(p) or _is_date_fragment(p):
            continue
        c = canonical_tech(p) or canonical_tech(_STACK_NOISE.sub("", p).strip())
        if c:
            out.append(c)
            continue
        found, left = tech_tokens(p)
        meaningful = [w for w in left if len(w) > 2 and not _STACK_NOISE.fullmatch(w)]
        if found and not meaningful:
            out.extend(found)
        elif len(p.split()) <= 4 and re.search(r"[A-Za-z]", p):
            cleaned_p = _STACK_NOISE.sub("", p).strip() or p
            if not COMPANY_HINT.search(cleaned_p) and not _DATE_WORD.fullmatch(cleaned_p) and not find_date_span(cleaned_p):
                out.append(cleaned_p)
    return list(dict.fromkeys(x for x in out if x))

def _completes_range(frags: List[str], frag: str) -> bool:
    joined = " ".join(frags)
    return bool(re.search(r"(?:to|au|à|-|–)\s*$", joined.strip(), re.I)) or not find_date_span(joined) or (
        find_date_span(joined) and not find_date_span(joined)[0].end)


def _is_continuation(prev: str, nxt: str, prev_was_glyph: bool = False) -> bool:
    if not prev:
        return False
    p = prev.rstrip()
    if nxt[:1].islower() or p.endswith(("-", ",", "/", "(", "&", " and", " et", " de", " des", " du", " the", " of", " to", " a", " à", " pour", " with", " avec", " for", " in", " en", " sur", " par")):
        return True
    if p.endswith((".", "!", "?", ":")):
        return False
    if nxt.rstrip().endswith(".") and not re.match(r"^(?:live apps|technologies|stack|lien|link)\s*:", nxt, re.I):
        return True
    # When the entry uses explicit bullet glyphs ("•"), any non-bullet line is a wrapped continuation
    return prev_was_glyph


def _prejoin(lines: List[Line]) -> List[Line]:
    """Join words hyphenated across a line break: 'Com-' + 'puter Science' -> 'Computer Science'."""
    out: List[Line] = []
    for l in lines:
        m = re.search(r"(\w+)-$", out[-1].text) if out else None
        if m and l.text[:1].islower() and out[-1].col == l.col:
            prev = out[-1]
            keep_hyphen = len(m.group(1)) <= 2 or m.group(1).lower() in _COMPOUND_HYPHEN_PREFIXES
            prev.text = (prev.text if keep_hyphen else prev.text[:-1]) + l.text
            prev.links = prev.links + [u for u in l.links if u not in prev.links]
            continue
        out.append(Line(text=l.text, size=l.size, bold=l.bold, x0=l.x0, x1=l.x1, top=l.top, page=l.page, col=l.col, links=list(l.links), caps=l.caps))
    return out


def _edu_field_full(cur: Entry, text: str) -> bool:
    t = text.replace("\t", " ")
    if DEGREE_WORDS.search(t) and cur.title and DEGREE_WORDS.search(cur.title):
        return True
    if SCHOOL_WORDS.search(t) and cur.org and not DEGREE_WORDS.search(t) and cur.title:
        return True
    return False


def _trim_edges(s: str) -> str:
    s = s.strip(" |–—-:,")
    # drop unbalanced edge parentheses only
    while s.endswith(")") and s.count("(") < s.count(")"):
        s = s[:-1].rstrip()
    while s.startswith("(") and s.count("(") > s.count(")"):
        s = s[1:].lstrip()
    if s.count("(") > s.count(")"):
        s = s + ")"
    return s.strip(" |–—-:,")


def _absorb_header_line(cur: Entry, text: str, section: str) -> None:
    """Assign a header-ish line to title / org / dates / location / stack."""
    parts = [p.strip() for p in text.split("\t") if p.strip()]
    for part in parts:
        found = find_date_span(part)
        if found and not cur.dates:
            cur.dates = found[0]
            rest = strip_dates(part)
        else:
            rest = part
        rest = _trim_edges(rest)
        if not rest:
            continue
        # "HealthCare Plus | Android: Java, XML, Firebase" / "Live demo | GitHub"
        segs = [s.strip() for s in re.split(r"\s+\|\s+|\s*\|\s*(?=[A-Z])|\s+·\s+", rest) if s.strip()]
        if section == "education" and len(segs) == 2 and DEGREE_WORDS.search(segs[0]) and not SCHOOL_WORDS.search(segs[1]):
            segs = [f"{segs[0]} – {segs[1]}"]
        for seg in segs:
            _assign_segment(cur, seg, section)


def _assign_segment(cur: Entry, seg: str, section: str) -> None:
    seg = _trim_edges(seg)
    if not seg:
        return
    if LINK_LABEL_RE.match(seg):
        if re.match(r"^[\w-]+\.(?:tn|com|io|app|dev|me|net|org|fr)(?:/\S*)?$", seg, re.I):
            u = sanitize_url("https://" + seg)
            if u and u not in cur.links:
                cur.links.append(u)
        return
    if is_location(seg):
        cur.location = cur.location or seg
        return
    if re.match(r"^(projet|project)\s+(fin d'ann[ée]e|acad[ée]mique|personnel|universitaire|de fin d'[ée]tudes?)", seg, re.I):
        cur.extra.append(seg)
        return
    if (cur.title or section == "projects") and (looks_like_stack(seg) or (
            section == "projects" and cur.title and len(seg.split()) <= 6 and tech_tokens(seg)[0] and not ROLE_WORDS.search(seg))):
        cur.stack.extend(s for s in stack_items(seg) if s not in cur.stack)
        return
    if section == "education":
        if DEGREE_WORDS.search(seg) and not cur.title:
            cur.title = seg
        elif SCHOOL_WORDS.search(seg) and not cur.org:
            org, loc = split_location(seg)
            cur.org, cur.location = org, cur.location or loc
        elif not cur.title:
            cur.title = seg
        elif not cur.org:
            org, loc = split_location(seg)
            cur.org, cur.location = org, cur.location or loc
        else:
            cur.extra.append(seg)
        return
    # experience / projects
    if not cur.title:
        cur.title = seg
    elif not cur.org:
        org, loc = split_location(seg)
        # Swap if the first line looks like a company and the second like a role
        if ROLE_WORDS.search(org) and not ROLE_WORDS.search(cur.title) and COMPANY_HINT.search(cur.title or ""):
            cur.title, org = org, cur.title
        cur.org = org
        cur.location = cur.location or loc
    elif not cur.location and split_location(seg)[1]:
        cur.location = split_location(seg)[1]
    else:
        cur.extra.append(seg)


def parse_education(lines: List[Line], lang: str) -> List[Entry]:
    """Education is field-based: degree / school / dates / details, in any order and layout."""
    entries: List[Entry] = []
    cur: Optional[Entry] = None
    date_frags: List[str] = []
    last_field = ""

    def finish():
        nonlocal cur, date_frags
        if cur is None:
            return
        if date_frags and not cur.dates:
            found = find_date_span(" ".join(date_frags))
            if found:
                cur.dates = found[0]
        if cur.dates:
            cur.date_text = cur.dates.display(lang)
        if not cur.title and cur.bullets:
            cur.title = cur.bullets.pop(0)
        cur.title = _trim_edges(re.sub(r"\s+", " ", cur.title))
        cur.org = _trim_edges(re.sub(r"\s+", " ", cur.org))
        if cur.title or cur.org:
            entries.append(cur)
        cur, date_frags = None, []

    for l in lines:
        raw = strip_bullet(l.text) if is_bullet(l.text) else l.text.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split("\t") if p.strip()]
        for part in parts:
            if _is_date_fragment(part):
                if cur is None:
                    cur = Entry(kind="education")
                joined = find_date_span(" ".join(date_frags)) if date_frags else None
                if cur.dates or (joined and joined[0].end and not _completes_range(date_frags, part)):
                    finish()
                    cur = Entry(kind="education")
                date_frags.append(part)
                last_field = "date"
                continue
            found = find_date_span(part)
            seg_text = part
            if found:
                if cur is not None and (cur.dates or date_frags):
                    finish()
                if cur is None:
                    cur = Entry(kind="education")
                cur.dates = found[0]
                seg_text = strip_dates(part)
            seg_text = _trim_edges(seg_text)
            if not seg_text:
                continue
            segs = [s.strip() for s in re.split(r"\s+\|\s+|\s*\|\s*(?=[A-Z])", seg_text) if s.strip()]
            if len(segs) == 1 and re.search(r"\s+[-–—]\s+", segs[0]):
                sub = [s.strip() for s in re.split(r"\s+[-–—]\s+", segs[0], maxsplit=1) if s.strip()]
                if len(sub) == 2 and (
                    (DEGREE_WORDS.search(sub[0]) and SCHOOL_WORDS.search(sub[1]))
                    or (SCHOOL_WORDS.search(sub[0]) and DEGREE_WORDS.search(sub[1]))
                ):
                    segs = sub
            if len(segs) == 2 and DEGREE_WORDS.search(segs[0]) and not SCHOOL_WORDS.search(segs[1]):
                segs = [f"{segs[0]} – {segs[1]}"]
            for seg in segs:
                if seg.lower() in ("străinătate", "strainatate"):
                    continue
                is_deg = bool(DEGREE_WORDS.search(seg))
                starts_school = bool(re.match(r"^(?:faculty|facult[ée]|universit|[ée]cole|institut|lyc[ée]e|school|high school|college|secondary school)", seg, re.I))
                is_school = (bool(SCHOOL_WORDS.search(seg)) and not is_deg) or starts_school
                if cur is None:
                    cur = Entry(kind="education")
                if is_school:
                    if cur.org and (cur.title or cur.dates or date_frags):
                        finish()
                        cur = Entry(kind="education")
                    org, loc = split_location(seg)
                    cur.org, cur.location = org, cur.location or loc
                    last_field = "org"
                elif is_deg:
                    if cur.title and (DEGREE_WORDS.search(cur.title) or cur.org or cur.dates or date_frags):
                        finish()
                        cur = Entry(kind="education")
                    cur.title = seg
                    last_field = "title"
                elif last_field == "title" and len(seg.split()) <= 3 and not cur.org and seg[:1].isupper() and not is_location(seg):
                    cur.title = f"{cur.title} {seg}"          # wrapped title ("...in Computer" / "Science")
                elif cur.title and len(cur.title.split()) <= 3 and DEGREE_WORDS.search(cur.title) and len(seg.split()) <= 8 and not is_location(seg):
                    cur.title = f"{cur.title} — {seg}"
                elif is_location(seg):
                    cur.location = cur.location or seg
                elif not cur.title and len(seg.split()) <= 12:
                    cur.title = seg
                    last_field = "title"
                elif not cur.org and len(seg.split()) <= 8 and not seg.endswith("."):
                    org, loc = split_location(seg)
                    cur.org, cur.location = org, cur.location or loc
                    last_field = "org"
                else:
                    techs, left = tech_tokens(seg)
                    if techs and len(techs) >= len([w for w in left if len(w) > 3]):
                        cur.stack.extend(t for t in techs if t not in cur.stack)
                    else:
                        cur.bullets.append(_join_hyphenated(seg))
    finish()
    return entries


def _format_bullet_end(b: str) -> str:
    s = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s+", " ", b)).strip(" .")
    if not s:
        return ""
    if s.lower().startswith("live apps:") or s.endswith(("!", "?")):
        return s
    if len(s.split()) >= 4:
        return s + "."
    return s


_INDUSTRY_NOISE_ORGS = {
    "telecommunications",
    "it software",
    "call-center / bpo",
    "it / telecom",
    "education / training",
    "training, formare profesională",
    "training, formare profesionala",
    "formare profesională",
    "formare profesionala",
    "străinătate",
    "strainatate",
}


def _finalize_entry(e: Entry, section: str) -> None:
    if e.org and e.org.strip().lower() in _INDUSTRY_NOISE_ORGS:
        e.org = ""
    e.extra = [x for x in e.extra if x.strip().lower() not in _INDUSTRY_NOISE_ORGS]
    e.bullets = [b for b in e.bullets if b.strip(" .").lower() not in _INDUSTRY_NOISE_ORGS]
    e.stack = [s for s in e.stack if s.strip(" .").lower() not in _INDUSTRY_NOISE_ORGS]
    # Title like "Python Developer at Hippo" / "Développeur chez X"
    m = re.match(r"^(.+?)\s+(?:at|chez|@)\s+(.+)$", e.title)
    if m and not e.org and section != "education":
        e.title, e.org = m.group(1).strip(), m.group(2).strip()
    # Title like "Content Moderator - Genpact" or "Stagiaire - OPTANS" when e.org is empty
    m_dash = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", e.title)
    if m_dash and not e.org and section == "experience":
        left_p, right_p = m_dash.group(1).strip(), m_dash.group(2).strip()
        if ROLE_WORDS.search(left_p) and len(right_p.split()) <= 5 and not ROLE_WORDS.search(right_p):
            e.title, e.org = left_p, right_p
    if e.org:
        e.org = re.sub(
            r"^(?:r[ée]alis[ée]r?|effectu[ée]r?)\s+au\s+sein\s+de\s+(?:l['’]entreprise|la\s+soci[ée]t[ée])\s+",
            "",
            e.org,
            flags=re.I,
        ).strip()
    # Generic title like "Applications" where e.org or e.bullets[0] describes the actual application
    if e.title.lower() in ("applications", "application", "projets", "projects"):
        if e.org and (_SENTENCE_START.match(e.org) or re.match(r"^d[ée]velopp", e.org, re.I)):
            first_sent = e.org
            if e.bullets and (e.bullets[0][:1].islower() or e.org.endswith((" pour", " de", " à", " for", " to"))):
                first_sent = f"{e.org} {e.bullets.pop(0)}"
            e.bullets.insert(0, first_sent)
            e.org = ""
        if e.bullets:
            m_app = re.search(r"(application\s+d['’][\w\sÀ-ÿ]{3,35}?)(?:\s+pour\b|$)", e.bullets[0], re.I)
            if m_app:
                e.title = m_app.group(1).strip().capitalize()
    # Untitled project/experience entries whose first bullet describes the project ("Conception et développement d'une application...")
    if not e.title and e.bullets:
        b0 = e.bullets[0].strip()
        m_proj_fr = re.match(
            r"^(?:conception\s+et\s+d[ée]veloppement|d[ée]veloppement(?:\s+front[- ]?end|\s+back[- ]?end)?|r[ée]alisation|cr[ée]ation)\s+d['’](?:une?|du)\s+(.+?)(?:\s+pour\s+(?:la\s+soci[ée]t[ée]\s+|l['’]entreprise\s+)?(.+?))?\s*\.?$",
            b0,
            re.I,
        )
        if m_proj_fr:
            app_title = m_proj_fr.group(1).strip(" .")
            e.title = app_title[:1].upper() + app_title[1:]
            if m_proj_fr.group(2) and not e.org and len(m_proj_fr.group(2).split()) <= 5:
                e.org = m_proj_fr.group(2).strip(" .")
        elif len(b0.split()) <= 10:
            e.title = e.bullets.pop(0).strip(" .")
    if e.org and not e.location:
        org, loc = split_location(e.org)
        if loc:
            e.org, e.location = org, loc
    # Kind
    blob = f"{e.title} {e.org}".lower()
    if section == "experience":
        e.kind = "internship" if re.search(r"\b(intern|internship|stage|stagiaire|trainee|alternan|apprenti|pfe|fin d'[ée]tudes?|summer|été|graduation)\b", blob) else "job"
    elif section == "projects":
        e.kind = "project"
    # Pull stack out of bullets that are pure tech/method comma lists without verbs
    keep = []
    for b in e.bullets:
        if b.strip().lower() in ("framework", "library"):
            continue
        is_comma_tech_list = (
            "," in b
            and "—" not in b
            and len(b.split()) <= 12
            and len(tech_tokens(b)[0]) >= 2
            and not re.search(
                r"\b(19\d{2}|20\d{2}|avec|with|developed|designed|built|implemented|proposed|analysed|analyzed|extracted|created|used|using|managed|led|wrote|worked|integrated|d[ée]velopp|conception|r[ée]alisation|gestion|utilisation|cr[ée]ation)\b",
                b,
                re.I,
            )
        )
        if (looks_like_stack(b) and len(b.split()) <= 14 and "—" not in b and not find_date_span(b)) or is_comma_tech_list:
            e.stack.extend(t for t in stack_items(b) if t not in e.stack)
        else:
            keep.append(b)
    e.bullets = [_format_bullet_end(b) for b in keep if b.strip(" .")]
    e.stack = list(dict.fromkeys(e.stack))
    dedup_links: List[str] = []
    seen_links = set()
    for u in e.links:
        u_clean = sanitize_url(u)
        if not u_clean:
            continue
        k = u_clean.rstrip("/").lower()
        if k not in seen_links:
            seen_links.add(k)
            dedup_links.append(u_clean.rstrip("/"))
    e.links = dedup_links
    if e.location:
        e.location = _clean_location(e.location.replace(">", ","))
    e.title = re.sub(r"\s+", " ", e.title).strip(" :|-–—")
    e.org = re.sub(r"\s+", " ", e.org).strip(" :|-–—")


def _split_mixed_experience(cv: CV) -> None:
    """For 'Experience & Projects' style sections, move entries that are clearly projects."""
    if "projects" in cv.sections_found:
        return
    moved = []
    for e in list(cv.experience):
        title = f"{e.title} {e.org}".lower()
        if not e.org and not STRICT_ROLE.search(title) and re.search(r"\b(app|application|site|website|platform|plateforme|bot|game|jeu|clone|clonage|system|système|tool|outil|projet|project)\b", title):
            e.kind = "project"
            moved.append(e)
    for e in moved:
        cv.experience.remove(e)
        cv.projects.append(e)


# ─── Skills / languages / lists ───────────────────────────────────────────────

_EXTRA_ENGINEERING_SKILLS = {
    "ci/cd": "CI/CD",
    "gradle": "Gradle",
    "code signing": "Code Signing",
    "unit and widget testing": "Unit & Widget Testing",
    "unit & widget testing": "Unit & Widget Testing",
    "material 3": "Material 3",
    "cupertino": "Cupertino",
    "realtime database": "Realtime Database",
    "firebase analytics": "Firebase Analytics",
    "solid": "SOLID",
    "jwt authentication": "JWT Authentication",
    "rest/json apis": "REST/JSON APIs",
    "windows 10/11": "Windows 10/11",
    "tcp/ip": "TCP/IP",
    "wi-fi": "Wi-Fi",
    "vpn": "VPN",
    "dns/dhcp": "DNS/DHCP",
}


def _split_skill_chunks(items: str) -> List[str]:
    """Split a skill line on commas/pipes/tabs/bullets while keeping parenthetical groups intact."""
    chunks: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in items:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif depth == 0 and ch in (",", ";", "|", "•", "\t"):
            s = "".join(buf).strip(" .-")
            if s:
                chunks.append(s)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip(" .-")
    if tail:
        chunks.append(tail)
    return chunks


def _prejoin_skill_lines(lines: List[Line]) -> List[Line]:
    """Join wrapped skill continuation lines (e.g. 'Time and Priority' + 'Management, Quick Learner', or 'Jupyter' + 'Notebook')."""
    out: List[Line] = []
    for l in lines:
        raw = strip_bullet(l.text)
        if not raw:
            continue
        if out:
            prev = out[-1]
            prev_raw = strip_bullet(prev.text)
            has_colon_cur = bool(re.match(r"^\s*[^:]{2,45}\s*:", raw))
            is_bold_hdr = l.bold and not re.search(r"[,|\t:]", raw) and len(raw.split()) <= 4 and not canonical_tech(raw)
            if not is_bullet(l.text) and not has_colon_cur and not is_bold_hdr and prev.col == l.col:
                # Continuation if previous line has unclosed parens, ends with a connector, or current starts with continuation word
                unclosed_paren = prev_raw.count("(") > prev_raw.count(")")
                ends_conn = bool(re.search(r"(?:,|&|\band|\bet|/|-|\bStaff|\bPriority|\bJupyter|\bIntelliJ|\bVisual\s+Studio)\s*$", prev_raw, re.I))
                starts_cont = bool(re.match(r"^(?:management|coordination|notebook|idea|code|studio|learner|support|design|content|troubleshooting)\b", raw, re.I))
                if unclosed_paren or ends_conn or starts_cont:
                    sep = "" if prev_raw.endswith("-") else " "
                    prev.text = prev.text.rstrip() + sep + raw.lstrip()
                    continue
        out.append(Line(text=l.text, size=l.size, bold=l.bold, x0=l.x0, x1=l.x1, top=l.top, page=l.page, col=l.col, links=list(l.links), caps=l.caps))
    return out


def _parse_skills(cv: CV, lines: List[Line]) -> None:
    joined_lines = _prejoin_skill_lines(lines)
    for l in joined_lines:
        raw = strip_bullet(l.text)
        if not raw:
            continue
        label, items = None, raw
        m = re.match(r"^\s*([^:]{2,45}?)\s*:\s*(.*)$", raw.replace("\t", " , ", 1) if ":" not in raw.split("\t")[0] else raw)
        if m and not canonical_tech(m.group(1)):
            label, items = m.group(1).strip(), m.group(2).strip()
        if label and re.search(r"\b(lang(?:ue|uage)s?(?! de programmation| informatiques)|spoken)\b", label, re.I) and not re.search(r"program|informati|markup|coding", label, re.I):
            cv.languages.extend(parse_languages([items]))
            continue
        if label and re.search(r"^(?:soft|savoir[- ]?[êe]tre|qualit[ée]s?(?: personnelles)?$|personal skills|interpersonal)", label.strip(), re.I):
            cv.soft_skills.extend(_split_items(items))
            continue
        if (label is not None and not items) or (label is None and l.bold and not re.search(r"[,|\t]", raw) and len(raw.split()) <= 4 and not canonical_tech(raw)):
            # Sub-heading like "Programming languages" or "Softwares :" with items on following lines
            hdr_name = (label or raw).rstrip(":").strip()
            if hdr_name.lower() not in ("general skills", "skills", "compétences"):
                cv.skill_groups.append((hdr_name, []))
            continue

        group_label = label or (cv.skill_groups[-1][0] if cv.skill_groups and cv.skill_groups[-1][0] else None)
        has_explicit_category = bool(group_label)

        found, left = tech_tokens(items)
        chunks = _split_skill_chunks(items)
        # Preserve well-known engineering skills and domain/non-developer skills in categorized or comma-separated skill lines
        for chunk in chunks:
            c_clean = re.sub(r"\s*\(primary\)\s*", "", chunk, flags=re.I).strip(" .")
            if not c_clean or re.fullmatch(r"(?:etc|and|et|ide|os|softwares?|logiciels?)", c_clean, re.I):
                continue
            c_low = c_clean.lower()
            if c_low in _EXTRA_ENGINEERING_SKILLS:
                mapped = _EXTRA_ENGINEERING_SKILLS[c_low]
                if mapped not in found:
                    found.append(mapped)
                continue
            if "ci/cd" in c_low and "CI/CD" not in found:
                found.insert(0, "CI/CD")
            # Check parenthetical sub-items (e.g. "Firebase (Auth, Firestore, Realtime DB, FCM, Crashlytics, Analytics)")
            m_paren = re.search(r"\(([^)]+)\)", c_clean)
            if m_paren:
                for sub_p in re.split(r"\s*,\s*", m_paren.group(1)):
                    sp_low = sub_p.strip().lower()
                    if sp_low in _EXTRA_ENGINEERING_SKILLS and _EXTRA_ENGINEERING_SKILLS[sp_low] not in found:
                        found.append(_EXTRA_ENGINEERING_SKILLS[sp_low])
            # If this chunk yielded zero canonical tech tokens, preserve it if it's a valid domain/professional skill
            c_techs, _ = tech_tokens(c_clean)
            if not c_techs and (has_explicit_category or len(chunks) >= 2):
                words_c = c_clean.split()
                if (
                    1 <= len(words_c) <= 6
                    and 2 <= len(c_clean) <= 48
                    and re.search(r"[A-Za-zÀ-ÿ]", c_clean)
                    and not find_date_span(c_clean)
                    and not EMAIL_RE.search(c_clean)
                    and not URL_RE.search(c_clean)
                ):
                    if c_clean not in found:
                        found.append(c_clean)

        # Remove redundant bare "AWS" if "AWS S3" is already in the same line
        if "AWS S3" in found and "AWS" in found and not re.search(r"\baws\b(?!\s*s3)", items, re.I):
            found = [x for x in found if x != "AWS"]
        # Remove redundant "Material Design" if "Material 3" is already in the same line and "Material Design" was not written
        if "Material 3" in found and "Material Design" in found and not re.search(r"\bmaterial\s+design\b", items, re.I):
            found = [x for x in found if x != "Material Design"]
        found = [_EXTRA_ENGINEERING_SKILLS.get(x.lower(), x) for x in found]

        if group_label and cv.skill_groups and cv.skill_groups[-1][0] == group_label:
            for f in found:
                if f not in cv.skill_groups[-1][1]:
                    cv.skill_groups[-1][1].append(f)
        elif found or group_label:
            cv.skill_groups.append((group_label or "", list(found)))
        for f in found:
            if f not in cv.skills:
                cv.skills.append(f)
        for w in left:
            w = w.strip(" .")
            if 1 < len(w) <= 30 and len(w.split()) <= 3 and not re.fullmatch(r"(?:ide|etc|and|et|softwares?|logiciels?|os)", w, re.I):
                if re.search(r"[A-Z0-9.#+]", w) and w not in cv.unknown_skills and w not in cv.skills:
                    cv.unknown_skills.append(w)

    # Remove empty placeholder skill groups
    cv.skill_groups = [(cat, grp) for cat, grp in cv.skill_groups if grp]


def _split_items(t: str) -> List[str]:
    return [p.strip(" .-") for p in re.split(r"\s*(?:,|;|\||•|\t| - |\s-(?=[A-ZÀ-Ý]))\s*", t) if p.strip(" .-")]


def _list_items(lines: List[Line]) -> List[str]:
    joined = " | ".join(strip_bullet(l.text) for l in lines)
    joined = re.sub(r"\|\s*([a-zà-ÿ])", r" \1", joined)  # wrapped lines
    items = []
    for p in _split_items(joined.replace(" | ", "|").replace("|", ",")):
        p = re.sub(r"^-\s*", "", p).strip()
        if p and p not in items:
            items.append(p)
    return items


def _paragraph_items(lines: List[Line]) -> List[str]:
    items: List[str] = []
    # Side-by-side items laid out as a grid (Canva): "CCNA 1\tCCNA 2" over
    # "Introduction to Networks\tRouting and switching principles" -> pair them column-wise.
    paired: List[Line] = []
    i = 0
    while i < len(lines):
        a = lines[i]
        b = lines[i + 1] if i + 1 < len(lines) else None
        pa = [p.strip() for p in a.text.split("\t") if p.strip()]
        pb = [p.strip() for p in b.text.split("\t") if p.strip()] if b is not None else []
        if b is not None and len(pa) >= 2 and len(pa) == len(pb) and not is_bullet(a.text) and not is_bullet(b.text):
            for x, y in zip(pa, pb):
                paired.append(Line(text=f"• {x} — {y}", size=a.size, bold=True, x0=a.x0, x1=a.x1, top=a.top,
                                   page=a.page, col=a.col, links=list(a.links)))
            i += 2
            continue
        paired.append(a)
        i += 1
    lines = paired
    all_bold = all(l.bold for l in lines if l.text.strip())
    for l in lines:
        t = l.text.replace("\t", " ").strip()
        if not t:
            continue
        if t.startswith("|") and items:
            items[-1] = f"{items[-1]} {t}"
            continue
        if URL_RE.fullmatch(t.strip(" .")) and items:
            items[-1] = f"{items[-1]} ({t.strip(' .')})"
            continue
        if items and items[-1].endswith(":") and not (is_bullet(t) or re.match(r"^-\S", t)):
            items[-1] = f"{items[-1]} {t}"
            continue
        if is_bullet(t) or re.match(r"^-\S", t) or not items or (l.bold and not all_bold) or re.match(r"^\d{4}\b", t) or re.match(r"^\d{1,2}\s+\w+\s+\d{4}", t):
            items.append(strip_bullet(t).lstrip("-").strip())
        else:
            items[-1] = _join_hyphenated(items[-1] + " " + t)
    return [i for i in items if i]


_LANG_NAME_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(strip_accents(k)) for k in SPOKEN_LANGS), key=len, reverse=True)) + r")\b", re.I)


def parse_languages(texts: List[str]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    joined = strip_accents(" , ".join(t.replace("\t", " , ") for t in texts))
    hits = list(_LANG_NAME_RE.finditer(joined))
    for i, m in enumerate(hits):
        key = m.group(1).lower()
        en, fr = next(v for k, v in SPOKEN_LANGS.items() if strip_accents(k) == key)
        if any(d["name_en"] == en for d in out):
            continue
        seg = joined[m.end(): hits[i + 1].start() if i + 1 < len(hits) else len(joined)].lower()
        lvl_en = lvl_fr = ""
        for pat, en_l, fr_l in LANG_LEVELS:
            if re.search(pat, strip_accents(seg), re.I) or re.search(pat, seg, re.I):
                lvl_en, lvl_fr = en_l, fr_l
                break
        out.append({"name_en": en, "name_fr": fr, "level_en": lvl_en, "level_fr": lvl_fr})
    return out
