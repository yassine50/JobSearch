"""
Job-description alignment helpers used by the tailoring pipeline to push the ATS match as close to
100% as the candidate's real profile allows.

What the ATS scorer (`cv_matcher.compute_match`) rewards, and how each helper addresses it:
  • tech skills in a Skills section (40%)      → tailor.py bridges every JD skill into the skills section
  • wording similarity with the JD (30%)       → `jd_key_phrases` + Core Competencies + summary focus line,
                                                 `prune_for_relevance` removes off-topic noise that dilutes it
  • role title (15%)                           → headline alignment (tailor._select_headline)
  • soft skills (8%)                           → `jd_soft_skills` surfaced in Core Competencies

Honesty boundary: nothing here invents employers, job titles, dates, degrees or metrics. In honest mode
only phrases already evidenced in the CV are surfaced.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence

from .lexicon import canonical_tech

_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at", "as", "is", "are", "be",
    "we", "you", "our", "your", "will", "can", "must", "should", "have", "has", "that", "this", "these", "those",
    "it", "its", "their", "them", "who", "what", "which", "from", "into", "across", "within", "via", "such", "etc",
    "plus", "also", "including", "other", "any", "all", "more", "most", "very", "well", "per", "e.g", "i.e",
    "looking", "hiring", "seeking", "join", "team", "role", "position", "candidate", "ideal", "company",
    "experience", "experienced", "knowledge", "understanding", "familiarity", "proficiency", "proficient",
    "ability", "able", "skills", "skill", "strong", "excellent", "good", "solid", "proven", "great", "deep",
    "required", "requirements", "requirement", "preferred", "nice", "bonus", "responsibilities", "qualifications",
    "years", "year", "minimum", "least", "degree", "bachelor", "bachelor's", "master", "master's", "relevant",
    "related", "field", "similar", "equivalent", "new", "using", "use", "used", "based", "work", "working",
    "environment", "opportunity", "help", "make", "ensure", "need", "needs", "like", "want", "someone", "day",
    "le", "la", "les", "des", "du", "de", "et", "ou", "en", "un", "une", "pour", "avec", "sur", "dans", "nous",
    "vous", "votre", "notre", "est", "sont", "aux", "au", "par",
}

# Leading verbs stripped from responsibility clauses: "design data models" -> "data models"
_VERBS = {
    "build", "building", "maintain", "maintaining", "design", "designing", "develop", "developing", "create",
    "implement", "implementing", "ensure", "ensuring", "collaborate", "collaborating", "communicate", "provide",
    "providing", "troubleshoot", "troubleshooting", "manage", "managing", "document", "documenting", "install",
    "configure", "handle", "handling", "resolve", "resolving", "meet", "escalate", "support", "supporting",
    "lead", "leading", "drive", "own", "deliver", "delivering", "write", "writing", "test", "testing", "deploy",
    "deploying", "monitor", "monitoring", "optimize", "optimizing", "improve", "improving", "analyze", "analyse",
    "analyzing", "perform", "conduct", "participate", "contribute", "coordinate", "review", "mentor", "train",
    "define", "plan", "track", "report", "prepare", "assist", "process", "respond", "answer", "identify",
    "migrate", "integrate", "integrating", "automate", "automating", "scale", "architect", "gather", "translate",
}

_PEOPLE = {"scientists", "engineers", "developers", "stakeholders", "colleagues", "managers", "members",
           "teammates", "clients", "users", "partners", "peers", "people", "staff", "analysts"}

_ACRONYMS = {"etl", "elt", "api", "apis", "rest", "sql", "nosql", "ci", "cd", "ci/cd", "aws", "gcp", "kpi", "kpis",
             "sla", "slas", "crm", "erp", "ui", "ux", "qa", "it", "bi", "ml", "ai", "nlp", "seo", "hr", "itil",
             "saas", "b2b", "b2c", "os", "macos", "ios", "mvp"}

SOFT_DISPLAY = {
    "communication": "Communication", "teamwork": "Teamwork", "leadership": "Leadership",
    "problem solving": "Problem Solving", "problem-solving": "Problem Solving", "time management": "Time Management",
    "attention to detail": "Attention to Detail", "empathy": "Empathy", "mentoring": "Mentoring",
    "collaboration": "Cross-functional Collaboration", "customer service": "Customer Service",
    "adaptability": "Adaptability", "critical thinking": "Critical Thinking", "creativity": "Creativity",
    "stakeholder management": "Stakeholder Management", "project management": "Project Management",
    "organization": "Organisation", "multitasking": "Multitasking", "negotiation": "Negotiation",
    "presentation": "Presentation Skills", "analytical": "Analytical Thinking",
}


def _display_phrase(words: Sequence[str]) -> str:
    out = []
    for w in words:
        c = canonical_tech(w)
        lw = w.lower()
        if c and c.lower() == lw and len(w) > 2:
            out.append(c)
        elif lw in _ACRONYMS:
            special = {"macos": "macOS", "ios": "iOS", "apis": "APIs", "kpis": "KPIs", "slas": "SLAs"}
            out.append(special.get(lw, w.upper()))
        else:
            out.append(w.capitalize() if w.islower() else w)
    return " ".join(out)


def _tokens(text: str) -> List[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#./'-]*", text or "")


_DEGREE_CLAUSE = re.compile(r"\b(degree|bachelor|master|diploma|licen[cs]e|dipl[oô]me|phd|bac\s*\+)", re.I)
_LANG_NAMES = {"english", "french", "spanish", "german", "arabic", "italian", "portuguese", "chinese", "russian",
               "turkish", "dutch", "romanian", "anglais", "français", "francais", "espagnol", "allemand", "arabe"}
try:
    from cv_matcher import TECH_SKILLS as _MATCHER_TECH
    _TECH_KEYS = {str(k).lower() for k in _MATCHER_TECH}
except Exception:  # pragma: no cover
    _TECH_KEYS = set()


def jd_key_phrases(job_description: str, job_title: str = "", limit: int = 10,
                   exclude: Iterable[str] = ()) -> List[str]:
    """Salient 2–3 word noun phrases from the JD ("scalable ETL pipelines", "data quality", "customer inquiries")."""
    jd = job_description or ""
    title_words = {w.lower() for w in _tokens(job_title)}
    excl = {e.lower() for e in exclude}
    clauses = re.split(r"[\n.;:!?()•·]|\s[-–—/]\s|,\s|\band\b|\bor\b|\bet\b|\bou\b", jd, flags=re.I)
    counts: Dict[str, int] = {}
    first_pos: Dict[str, int] = {}
    words_of: Dict[str, List[str]] = {}
    for clause in clauses:
        if _DEGREE_CLAUSE.search(clause):
            continue
        toks = _tokens(clause)
        run: List[str] = []

        def flush():
            nonlocal run
            r, run = run, []
            while r and (r[0].lower() in _VERBS or r[0].lower() in _STOP):
                r = r[1:]
            while r and r[-1].lower() in _STOP:
                r = r[:-1]
            if not 2 <= len(r) <= 4:
                return
            low = [w.lower() for w in r]
            key = " ".join(low)
            if any(w in _PEOPLE for w in low):
                return
            if all(canonical_tech(w) for w in r) or canonical_tech(key) or key in _TECH_KEYS:
                return                                # tech skills are handled by the skills section
            if all(w in _LANG_NAMES for w in low):
                return
            if set(low) <= title_words:               # "data engineer" = the headline itself
                return
            if re.fullmatch(r"\d+\+?", low[0]):
                return
            if key in excl:
                return
            counts[key] = counts.get(key, 0) + 1
            if key not in first_pos:
                first_pos[key] = len(first_pos)
                words_of[key] = r

        for t in toks:
            if t.lower() in _STOP and run and t.lower() not in {"of", "de"}:
                flush()
                continue
            run.append(t)
            if len(run) > 4:
                run = run[-4:]
        flush()

    keys = list(counts)
    # Drop phrases contained in a longer kept phrase ("data models" vs "design data models")
    keys.sort(key=lambda k: (-counts[k], first_pos[k]))
    kept: List[str] = []
    for k in keys:
        if any(k in o or o in k for o in kept):
            continue
        kept.append(k)
        if len(kept) >= limit:
            break
    return [_display_phrase(words_of[k]) for k in kept]


def jd_soft_skills(breakdown: Dict, job_description: str = "") -> List[str]:
    seen: List[str] = []
    for s in list(breakdown.get("matched_soft") or []) + list(breakdown.get("missing_soft") or []):
        d = SOFT_DISPLAY.get(s.lower(), s.title())
        if d not in seen:
            seen.append(d)
    # The ATS dictionary misses common phrasings ("problem-solving", "attention to detail") — scan the JD too
    for pat, disp in _SOFT_PATTERNS:
        if re.search(pat, job_description or "", re.I) and disp not in seen:
            seen.append(disp)
    return seen


_SOFT_PATTERNS = [
    (r"\bproblem[- ]solving\b", "Problem Solving"), (r"\battention to detail\b|\bdetail[- ]oriented\b", "Attention to Detail"),
    (r"\bteam ?work\b|\bteam player\b", "Teamwork"), (r"\bcommunicat", "Communication"),
    (r"\bempath", "Empathy"), (r"\btime management\b", "Time Management"), (r"\bleadership\b", "Leadership"),
    (r"\bmentor", "Mentoring"), (r"\bcustomer service\b", "Customer Service"),
    (r"\bcollaborat", "Cross-functional Collaboration"), (r"\badaptab", "Adaptability"),
    (r"\bmulti-?tasking\b", "Multitasking"), (r"\bcritical thinking\b", "Critical Thinking"),
    (r"\bstakeholder", "Stakeholder Management"), (r"\borgani[sz]ation(?:al)? skills\b|\borgani[sz]ed\b", "Organisation"),
    (r"\banalytical\b", "Analytical Thinking"), (r"\bownership\b", "Ownership"),
]

_COMMON_CAPS = {
    "we", "you", "our", "the", "a", "an", "and", "or", "for", "with", "in", "on", "to", "of", "as", "is", "are",
    "experience", "strong", "excellent", "knowledge", "must", "nice", "plus", "bonus", "requirements", "required",
    "responsibilities", "about", "what", "who", "why", "how", "join", "senior", "junior", "lead", "remote",
    "hybrid", "full", "time", "part", "contract", "bachelor", "master", "degree", "phd", "years", "year", "team",
    "company", "role", "position", "job", "salary", "benefits", "location", "office", "work", "monday", "friday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "europe", "usa", "uk", "eu", "ok", "etc", "i", "it", "all", "any", "please", "apply",
}


def jd_named_tools(job_description: str, cv_text: str, job_title: str = "", company: str = "",
                   limit: int = 8) -> List[str]:
    """
    Proper-noun tools/platforms/standards named in the JD that the CV lacks and the ATS dictionary
    does not know (Zendesk, Salesforce, ServiceNow, ITIL, Codemagic, Windows, SLA...).
    """
    jd = job_description or ""
    low_cv = (cv_text or "").lower()
    skip = {w.lower() for w in _tokens(job_title)} | {w.lower() for w in _tokens(company)} | _LANG_NAMES
    out: List[str] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#]*(?:[./][A-Za-z0-9+#]+)*", jd):
        w = m.group(0).strip("./")
        lw = w.lower()
        if len(w) < 2 or lw in skip or lw in _COMMON_CAPS or lw in _STOP:
            continue
        camel = bool(re.search(r"[a-z][A-Z]", w))                # ServiceNow, GitLab
        acronym = w.isupper() and 2 <= len(w) <= 6 and w.isalpha()
        capital = w[:1].isupper() and w[1:].islower()
        if not (camel or acronym or capital):
            continue
        prev = jd[:m.start()].rstrip()
        sentence_start = not prev or prev[-1] in ".!?:\n•·-–—(" or prev.endswith("\n")
        if capital and not camel and sentence_start:
            continue
        if acronym and lw in {"it", "hr", "ok"}:
            continue
        if re.search(r"(?<![\w])" + re.escape(lw) + r"(?![\w])", low_cv):
            continue
        disp = canonical_tech(w) or ({"slas": "SLA", "kpis": "KPI"}.get(lw) or w)
        if disp.lower() not in {o.lower() for o in out}:
            out.append(disp)
        if len(out) >= limit:
            break
    return out


def build_core_competencies(phrases: List[str], soft: List[str], cv_text: str, mode: str,
                            limit: int = 12) -> List[str]:
    """Competency list for the CV. Honest mode keeps only items already evidenced in the CV text."""
    low_cv = (cv_text or "").lower()
    items: List[str] = []
    for p in phrases + soft:
        if mode != "full_match":
            words = [w for w in re.findall(r"[a-zà-ÿ0-9+#]+", p.lower()) if w not in _STOP]
            if not words or not all(w in low_cv for w in words):
                continue
        if p.lower() not in {i.lower() for i in items}:
            items.append(p)
        if len(items) >= limit:
            break
    return items


def _rel(text: str, keywords: Sequence[str]) -> int:
    t = (text or "").lower()
    return sum(1 for k in keywords if k and re.search(r"(?<![\w])" + re.escape(k.lower()) + r"(?![\w])", t))


_TOOLISH_CAT = re.compile(r"tool|ide|other|autres|outils|misc|additional|software|environment", re.I)


def prune_for_relevance(cv, keywords: Sequence[str], mode: str) -> List[str]:
    """
    Remove off-topic noise that dilutes JD similarity, without deleting real experience:
      • tool-ish skill categories keep relevant items + at most 4 others
      • fully irrelevant tool-ish categories are dropped when ≥3 categories remain
      • with >3 projects, projects with zero JD relevance are dropped (best 3 always kept)
    Returns human-readable notes.
    """
    if mode != "full_match":
        return []
    notes: List[str] = []
    groups = list(cv.skill_groups or [])
    new_groups = []
    dropped_items = 0
    for cat, items in groups:
        if _TOOLISH_CAT.search(cat or "") and "additional technologies" not in (cat or "").lower():
            rel = [i for i in items if _rel(i, keywords)]
            other = [i for i in items if i not in rel]
            keep = rel + other[:4]
            if not rel and len(groups) >= 4:
                dropped_items += len(items)
                continue
            dropped_items += len(items) - len(keep)
            new_groups.append((cat, keep))
        else:
            new_groups.append((cat, items))
    if dropped_items:
        cv.skill_groups = new_groups
        notes.append(f"Trimmed {dropped_items} off-topic tools from the skills section to sharpen JD focus.")
    if len(cv.projects) > 3:
        scored = sorted(cv.projects, key=lambda p: -_rel(" ".join([p.title, p.org] + p.bullets + p.stack), keywords))
        keep = scored[:3] + [p for p in scored[3:] if _rel(" ".join([p.title, p.org] + p.bullets + p.stack), keywords)]
        if len(keep) < len(cv.projects):
            notes.append(f"Omitted {len(cv.projects) - len(keep)} project(s) unrelated to the role.")
            cv.projects = [p for p in cv.projects if p in keep]
    return notes


def pdf_text(pdf_bytes: bytes) -> str:
    """Text layer of the rendered PDF — the tailored score is computed on what recruiters' ATS will read."""
    try:
        import io
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return ""
