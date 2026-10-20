"""
Search Quality Engine
=====================
Pure-python helpers used by /api/jobs/search to get MORE results with BETTER quality:

1. Query expansion   – equivalent job titles (+ French variants for French-speaking markets)
                       so each board is searched with several phrasings of the same role.
2. Relevance scoring – whole-word, synonym-aware title/description matching. Stops false
                       positives such as "Developer" matching the company "Atlantic Developments".
3. Smart dedup/merge – the same job found on several boards / query variants is merged into
                       one card (best description, union of recruiter emails, freshest date).
4. Spam filtering    – drops commission-only / MLM / "earn $$$ from home" style listings.
5. Quality ranking   – relevance + freshness + description richness + salary + recruiter email.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary
# ─────────────────────────────────────────────────────────────────────────────

STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "on", "de", "des",
    "du", "la", "le", "les", "et", "en", "h", "f", "m", "x", "hf", "fh", "mf", "fm", "w",
}

# Seniority / contract words: useful for ranking but must never be *required* to match.
SOFT_WORDS: Set[str] = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "chief", "head", "mid",
    "entry", "level", "intern", "internship", "trainee", "graduate", "associate", "remote",
    "hybrid", "onsite", "contract", "freelance", "temporary", "temp", "permanent", "full",
    "part", "time", "i", "ii", "iii", "iv", "confirme", "confirmé", "stage", "stagiaire",
    "alternance", "cdi", "cdd", "new", "experienced",
}

# Tokens that are interchangeable inside a job title.
TOKEN_EQUIV: List[Set[str]] = [
    {"developer", "engineer", "programmer", "dev", "développeur", "developpeur", "ingénieur",
     "ingenieur", "coder", "swe", "sde"},
    {"software", "logiciel", "application", "applications", "app"},
    {"frontend", "front", "ui"},
    {"backend", "back", "server"},
    {"fullstack", "full-stack", "stack"},
    {"javascript", "js"},
    {"typescript", "ts"},
    {"react", "reactjs"},
    {"node", "nodejs"},
    {"vue", "vuejs"},
    {"angular", "angularjs"},
    {"golang", "go"},
    {"python", "django", "flask", "fastapi"},
    {"mobile", "android", "ios", "flutter"},
    {"devops", "sre", "reliability", "platform"},
    {"cloud", "aws", "azure", "gcp"},
    {"ml", "machine", "ai", "artificial", "ia"},
    {"data", "données", "donnees", "analytics"},
    {"analyst", "analyste"},
    {"scientist", "science"},
    {"manager", "management", "gestionnaire", "responsable"},
    {"designer", "design", "ux"},
    {"security", "cybersecurity", "sécurité", "securite", "infosec"},
    {"support", "helpdesk", "technician", "technicien"},
    {"administrator", "admin", "administrateur"},
    {"network", "réseau", "reseau", "networking"},
    {"qa", "quality", "test", "tester", "testing", "automation"},
    {"accountant", "comptable", "accounting"},
    {"sales", "commercial", "vente"},
    {"marketing", "marketeur"},
    {"consultant", "consulting"},
    {"architect", "architecte", "architecture"},
    {"product", "produit"},
    {"project", "projet"},
    {"business", "bi"},
    {"web", "website"},
]

_EQUIV_INDEX: Dict[str, int] = {}
for _i, _grp in enumerate(TOKEN_EQUIV):
    for _w in _grp:
        _EQUIV_INDEX[_w] = _i

# Full-title synonym groups used for query expansion (first = canonical).
ROLE_SYNONYMS: List[List[str]] = [
    ["software developer", "software engineer", "application developer", "programmer"],
    ["full stack developer", "full stack engineer", "fullstack developer"],
    ["frontend developer", "front end developer", "frontend engineer", "react developer"],
    ["backend developer", "back end developer", "backend engineer"],
    ["web developer", "web engineer", "frontend developer"],
    ["mobile developer", "mobile engineer", "flutter developer", "android developer", "ios developer"],
    ["flutter developer", "mobile developer", "dart developer"],
    ["react developer", "frontend developer", "react engineer"],
    ["python developer", "python engineer", "backend developer"],
    ["java developer", "java engineer", "backend developer"],
    ["devops engineer", "site reliability engineer", "platform engineer", "cloud engineer"],
    ["cloud engineer", "devops engineer", "aws engineer"],
    ["data analyst", "business intelligence analyst", "bi analyst", "reporting analyst"],
    ["data scientist", "machine learning engineer", "ai engineer"],
    ["machine learning engineer", "ml engineer", "ai engineer", "data scientist"],
    ["ai engineer", "machine learning engineer", "llm engineer"],
    ["data engineer", "etl developer", "big data engineer"],
    ["qa engineer", "test automation engineer", "software tester", "quality assurance analyst"],
    ["ui ux designer", "product designer", "ux designer", "ui designer"],
    ["product manager", "product owner", "technical product manager"],
    ["project manager", "it project manager", "program manager"],
    ["it support", "help desk technician", "it technician", "desktop support"],
    ["system administrator", "systems administrator", "it administrator", "sysadmin"],
    ["network engineer", "network administrator", "network technician"],
    ["cybersecurity analyst", "security analyst", "information security analyst", "soc analyst"],
    ["business analyst", "it business analyst", "functional analyst"],
    ["accountant", "staff accountant", "bookkeeper"],
    ["digital marketing", "marketing specialist", "growth marketer"],
]

# French equivalents (searched additionally in French-speaking markets).
FRENCH_TITLES: Dict[str, List[str]] = {
    "software developer": ["développeur logiciel", "ingénieur logiciel"],
    "software engineer": ["ingénieur logiciel", "développeur logiciel"],
    "full stack developer": ["développeur full stack"],
    "frontend developer": ["développeur front-end"],
    "backend developer": ["développeur back-end"],
    "web developer": ["développeur web"],
    "mobile developer": ["développeur mobile"],
    "flutter developer": ["développeur flutter", "développeur mobile"],
    "react developer": ["développeur react"],
    "python developer": ["développeur python"],
    "java developer": ["développeur java"],
    "devops engineer": ["ingénieur devops"],
    "data analyst": ["analyste de données", "data analyst"],
    "data scientist": ["data scientist", "scientifique des données"],
    "data engineer": ["ingénieur data", "data engineer"],
    "machine learning engineer": ["ingénieur machine learning", "ingénieur ia"],
    "ai engineer": ["ingénieur ia", "ingénieur intelligence artificielle"],
    "qa engineer": ["ingénieur qa", "testeur logiciel"],
    "product manager": ["chef de produit", "product manager"],
    "project manager": ["chef de projet", "chef de projet informatique"],
    "it support": ["technicien support informatique", "support informatique"],
    "system administrator": ["administrateur système"],
    "network engineer": ["ingénieur réseau"],
    "cybersecurity analyst": ["analyste cybersécurité"],
    "business analyst": ["analyste fonctionnel", "business analyst"],
    "accountant": ["comptable"],
}

FRENCH_MARKETS: Set[str] = {"france", "fr", "morocco", "ma", "belgium", "switzerland", "quebec",
                            "luxembourg", "tunisia", "algeria", "senegal"}

SPAM_PATTERNS = re.compile(
    r"(commission[\s-]*only|100%\s*commission|earn\s+\$?\d{3,}|\$\d{3,}\s*(?:/|per)\s*(?:day|week)|"
    r"\bmlm\b|network\s+marketing|be\s+your\s+own\s+boss|work\s+from\s+home\s*!{1,}|"
    r"no\s+experience\s+needed\s*!|crypto\s+trading\s+signals|paid\s+surveys?|mystery\s+shopper|"
    r"data\s+entry\s*-\s*\$|sign[\s-]*on\s+bonus\s+\$\d{4,}.*driver)",
    re.IGNORECASE,
)

BAD_COMPANY = {"", "confidential", "n/a", "na", "none", "nan", "unknown", "private"}


# ─────────────────────────────────────────────────────────────────────────────
# Tokenisation
# ─────────────────────────────────────────────────────────────────────────────

def _stem(tok: str) -> str:
    """Very light stemmer: only plural forms, so 'developments' ≠ 'developer'."""
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith(("ers", "ors", "ists", "ysts", "ants", "ents", "ects")):
        return tok[:-1]
    return tok


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    t = text.lower()
    t = t.replace("full-stack", "fullstack").replace("full stack", "fullstack")
    t = t.replace("front-end", "frontend").replace("front end", "frontend")
    t = t.replace("back-end", "backend").replace("back end", "backend")
    t = t.replace("node.js", "nodejs").replace("react.js", "reactjs").replace("vue.js", "vuejs")
    t = t.replace("c++", "cpp").replace("c#", "csharp").replace(".net", "dotnet")
    raw = re.findall(r"[a-zà-ÿ0-9+#]+", t)
    return [_stem(w) for w in raw if w not in STOPWORDS]


def _equiv(tok: str) -> str:
    """Map a token to its equivalence-class key."""
    idx = _EQUIV_INDEX.get(tok)
    return f"#{idx}" if idx is not None else tok


def core_tokens(query: str) -> List[str]:
    toks = [t for t in tokenize(query) if t not in SOFT_WORDS]
    return toks or tokenize(query)


# ─────────────────────────────────────────────────────────────────────────────
# Query expansion
# ─────────────────────────────────────────────────────────────────────────────

def expand_queries(title: str, country: str = "", max_variants: int = 3) -> List[str]:
    """Return the original query followed by equivalent phrasings of the same role."""
    base = (title or "").strip()
    if not base:
        return []
    low = re.sub(r"\s+", " ", base.lower())
    variants: List[str] = [base]

    def _add(v: str):
        if v and v.lower() not in {x.lower() for x in variants}:
            variants.append(v)

    # Find the synonym group whose canonical/members best match the query.
    stripped = " ".join(core_tokens(low))
    matched_group: Optional[List[str]] = None
    for grp in ROLE_SYNONYMS:
        if low in grp or stripped in [" ".join(core_tokens(g)) for g in grp]:
            matched_group = grp
            break
    if matched_group is None:
        for grp in ROLE_SYNONYMS:
            if grp[0] in low:
                matched_group = grp
                break

    seniority = [w for w in low.split() if w in {"senior", "junior", "lead", "sr", "jr", "principal"}]
    prefix = (seniority[0] + " ") if seniority else ""

    # French phrasing first in French-speaking markets (local boards index French titles).
    if country and country.strip().lower() in FRENCH_MARKETS:
        key = matched_group[0] if matched_group else stripped
        for fr in FRENCH_TITLES.get(key, [])[:1]:
            _add(fr)

    if matched_group:
        for syn in matched_group:
            if syn != low and syn != stripped:
                _add(_nice_case(prefix + syn))
    else:
        # Generic developer ↔ engineer swap keeps the user's technology keyword.
        if "developer" in low:
            _add(_nice_case(low.replace("developer", "engineer")))
        elif "engineer" in low:
            _add(_nice_case(low.replace("engineer", "developer")))

    return variants[:max_variants]


_ACRONYMS = {"bi": "BI", "qa": "QA", "ui": "UI", "ux": "UX", "ai": "AI", "ml": "ML", "it": "IT",
             "soc": "SOC", "etl": "ETL", "aws": "AWS", "ios": "iOS", "llm": "LLM", "sre": "SRE"}


def _nice_case(s: str) -> str:
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in s.split())


# ─────────────────────────────────────────────────────────────────────────────
# Relevance
# ─────────────────────────────────────────────────────────────────────────────

def relevance_score(query: str, title: str, description: str = "") -> int:
    """0-100 score of how well a job matches the searched role.

    - Exact phrase in title                   → 100
    - All core words (synonym-aware) in title → 90
    - Partial title match                     → 40-80
    - Description-only match                  → ≤ 35
    """
    q_core = core_tokens(query)
    if not q_core:
        return 50
    t_low = (title or "").lower()
    q_low = (query or "").lower().strip()
    if q_low and re.search(r"\b" + re.escape(q_low) + r"\b", t_low):
        return 100

    t_classes = {_equiv(t) for t in tokenize(title)}
    q_classes = [_equiv(t) for t in q_core]
    hits = sum(1 for c in q_classes if c in t_classes)
    frac = hits / len(q_classes)

    if frac >= 1.0:
        return 90
    if hits:
        # The "role noun" (last word, e.g. developer / analyst) matters most.
        role_hit = q_classes[-1] in t_classes
        return int(40 + 30 * frac + (10 if role_hit else 0))

    if description:
        d_classes = {_equiv(t) for t in tokenize(description[:4000])}
        d_hits = sum(1 for c in q_classes if c in d_classes)
        phrase_in_desc = q_low and q_low in description.lower()
        if phrase_in_desc:
            return 35
        return int(25 * d_hits / len(q_classes))
    return 0


def best_relevance(queries: Iterable[str], title: str, description: str = "") -> int:
    return max((relevance_score(q, title, description) for q in queries if q), default=0)


def is_spam(title: str, description: str = "", company: str = "") -> bool:
    blob = f"{title} {company} {(description or '')[:1500]}"
    return bool(SPAM_PATTERNS.search(blob))


# ─────────────────────────────────────────────────────────────────────────────
# Dedup / merge (ported & expanded from ai-job-search tools/job_key.py)
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

_CHAR_MAP = str.maketrans({
    "ø": "o", "æ": "ae", "å": "aa",
    "ö": "o", "ä": "ae", "ü": "u", "ß": "ss", "œ": "oe",
})

_CORP_SUFFIX_RE = re.compile(
    r"\b("
    r"a/s|aps|i/s|p/s|k/s|"
    r"ab|oy|oyj|as|asa|ehf|"
    r"gmbh|ag|se|kg|ug|mbh|"
    r"bv|nv|sarl|sas|sa|srl|spa|sl|"
    r"plc|ltd|limited|llp|inc|incorporated|corp|corporation|llc|co|"
    r"company|group|holding|holdings|technologies|solutions|labs"
    r")\.?$"
)


def _fold_ascii(text: str) -> str:
    """Fold Nordic/European characters and strip Unicode combining marks."""
    s = (text or "").strip().lower().translate(_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def normalize_company_key(company: str) -> str:
    """Canonical company key resilient to legal suffixes, parentheticals, and diacritics."""
    s = _fold_ascii(company)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9/]+", " ", s).strip()
    prev = None
    while s != prev:
        prev = s
        s = _CORP_SUFFIX_RE.sub("", s).strip()
    return re.sub(r"[^a-z0-9]", "", s)


def normalize_title_key(title: str) -> str:
    """Canonical title key stripping gender markers (m/f/d, h/f) and trailing location tails."""
    s = _fold_ascii(title)
    s = re.sub(r"\([^)]*\)", " ", s)
    for sep in (" - ", " – ", " — ", ", "):
        if sep in s:
            head, tail = s.rsplit(sep, 1)
            # Strip trailing location/mode/gender tails while keeping real role qualifiers
            if len(head) >= 6 and (
                len(tail) <= 22 or any(w in tail for w in ("remote", "hybrid", "onsite", "h/f", "m/f", "f/h", "all genders"))
            ):
                s = head
                break
    return re.sub(r"[^a-z0-9+#]", "", s)


def _norm(s: str) -> str:
    return normalize_company_key(s)


def canonical_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    m = re.search(r"currentjobid=(\d+)", u) or re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", u)
    if m:
        return f"linkedin:{m.group(1)}"
    m = re.search(r"[?&]jk=([a-z0-9]+)", u)
    if m:
        return f"indeed:{m.group(1)}"
    m = re.search(r"jobbank\.gc\.ca/jobsearch/jobposting/(\d+)", u)
    if m:
        return f"jobbank:{m.group(1)}"
    m = re.search(r"[?&]gh_jid=(\d+)", u) or re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", u)
    if m:
        return f"greenhouse:{m.groups()[-1]}"
    m = re.search(r"jobs\.lever\.co/([^/?#]+)/([0-9a-f-]{16,})", u)
    if m:
        return f"lever:{m.group(1)}/{m.group(2)}"
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{16,})", u)
    if m:
        return f"ashby:{m.group(1)}/{m.group(2)}"
    u = re.sub(r"^https?://(www\.)?", "", u.split("#")[0])
    u = u.split("?")[0].rstrip("/")
    u = re.sub(r";jsessionid=[^/?]*", "", u)
    return u


def dedup_keys(job: dict) -> List[str]:
    keys = []
    cu = canonical_url(job.get("url") or "")
    if cu:
        keys.append("u:" + cu)
    du = canonical_url(job.get("job_url_direct") or "")
    if du and du != cu:
        keys.append("u:" + du)
    nt = normalize_title_key(job.get("title", ""))
    nc = normalize_company_key(job.get("company", ""))
    if nt and nc and nc not in {normalize_company_key(b) for b in BAD_COMPANY}:
        # Same normalized title at the same company in the same city = same opening across portals.
        city = _fold_ascii((job.get("location") or "").split(",")[0])
        city = re.sub(r"[^a-z0-9]", "", city)
        keys.append(f"tc:{nt}|{nc}|{city}")
        # Also match remote/unspecified city against concrete city when company+title are specific
        if len(nt) >= 12 and len(nc) >= 4:
            keys.append(f"tcr:{nt}|{nc}")
    return keys


def _email_list(job: dict) -> List[str]:
    out = []
    for e in job.get("emails") or []:
        em = (e.get("email") if isinstance(e, dict) else str(e)).strip().lower()
        if em and "@" in em:
            out.append(em)
    return out


def merge_jobs(primary: dict, other: dict) -> dict:
    """Merge `other` into `primary`, keeping the richest data from both."""
    if len(other.get("description") or "") > len(primary.get("description") or ""):
        primary["description"] = other["description"]
    have = set(_email_list(primary))
    for e in other.get("emails") or []:
        em = (e.get("email") if isinstance(e, dict) else str(e)).strip().lower()
        if em and em not in have:
            primary.setdefault("emails", []).append(e if isinstance(e, dict) else {"email": em, "source": "found"})
            have.add(em)
    for fld in ("salary", "job_url_direct", "company_url_direct", "company_url", "location"):
        if not primary.get(fld) and other.get(fld):
            primary[fld] = other[fld]
    pa, oa = primary.get("age_hours"), other.get("age_hours")
    if oa is not None and (pa is None or oa < pa):
        for fld in ("age_hours", "age_str", "date_posted", "is_under_24h"):
            primary[fld] = other.get(fld)
    for flag in ("easy_apply", "is_direct_apply", "is_international_eligible"):
        primary[flag] = bool(primary.get(flag) or other.get(flag))
    sites = set(primary.get("also_on") or [primary.get("site")])
    sites.add(other.get("site"))
    primary["also_on"] = sorted(s for s in sites if s)
    return primary


def dedup_and_merge(jobs: List[dict]) -> List[dict]:
    key_to_idx: Dict[str, int] = {}
    out: List[dict] = []
    for job in jobs:
        keys = dedup_keys(job)
        idx = next((key_to_idx[k] for k in keys if k in key_to_idx), None)
        if idx is None:
            out.append(job)
            idx = len(out) - 1
        else:
            out[idx] = merge_jobs(out[idx], job)
        for k in keys:
            key_to_idx.setdefault(k, idx)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Quality score
# ─────────────────────────────────────────────────────────────────────────────

def quality_score(job: dict) -> int:
    """0-100 composite: relevance 50 · freshness 20 · richness 10 · email 10 · salary 5 · company 5."""
    rel = job.get("relevance") or 0
    score = rel * 0.5

    age = job.get("age_hours")
    if age is None:
        score += 6
    elif age <= 24:
        score += 20
    elif age <= 72:
        score += 16
    elif age <= 168:
        score += 12
    elif age <= 720:
        score += 6
    else:
        score += 2

    dlen = len(job.get("description") or "")
    score += 10 if dlen >= 800 else (6 if dlen >= 250 else (2 if dlen >= 80 else 0))
    score += 10 if _email_list(job) else 0
    score += 5 if job.get("salary") else 0
    score += 0 if _norm(job.get("company", "")) in {_norm(b) for b in BAD_COMPANY} else 5
    if len(job.get("also_on") or []) > 1:
        score += 3  # confirmed on multiple boards = real, active opening
    return max(0, min(100, int(round(score))))
