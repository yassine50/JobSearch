"""
Shared helpers for country local-board scraper plugins (``local_boards_ext/<region>.py``).

PLUGIN CONTRACT
===============
Each region module exposes::

    DIRECT_SCRAPERS: Dict[str, List[Callable[[str], List[dict]]]]
    BOARDS: Dict[str, List[str]]          # human readable board names per country (for UI / back office)

* Keys are canonical country keys of ``local_boards.COUNTRY_LOCAL_BOARDS`` (e.g. "uk", "czech republic").
* A country's list in a plugin is AUTHORITATIVE: it replaces the legacy scrapers for that country,
  so re-use (import) legacy scrapers that still work instead of duplicating them.
* Every scraper: ``fn(query: str) -> List[dict]`` built with :func:`row`. It must
    - never raise (wrap in try/except -> ``[]``),
    - do at most 2 HTTP calls, each through :func:`get` / :func:`post` / :func:`cffi_get` (timeout <= 3.5 s),
    - return single, live postings only (no search / category pages, drop expired/closed when exposed),
    - put the real employer in ``company`` ("" if unknown — never the board name),
    - always include the country name in ``location`` (use :func:`with_country`),
    - NEVER inject the search query into title/description (relevance is scored by the engine),
    - return <= MAX_ROWS rows.
The engine (``local_boards.fetch_country_local_boards``) handles caching, single-flight de-duplication,
deadlines, relevance scoring, country verification and health tracking — scrapers stay simple.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("jobsearcher.local_boards_ext")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,de;q=0.7",
}
JSON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 3.5
MAX_ROWS = 20

# One pooled session for every plugin -> TLS/keep-alive reuse across scrapers & searches.
SESSION = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=0)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────

def get(url: str, *, headers: Optional[dict] = None, timeout: float = TIMEOUT, **kw) -> Optional[requests.Response]:
    """GET through the pooled session; returns the response only on HTTP 200, else None."""
    try:
        r = SESSION.get(url, headers=headers or HEADERS, timeout=min(timeout, TIMEOUT), **kw)
        if r.status_code != 200:
            logger.debug(f"[ext] GET {url} -> HTTP {r.status_code}")
            return None
        return r
    except Exception as e:
        logger.debug(f"[ext] GET {url} failed: {e}")
        return None


def post(url: str, *, headers: Optional[dict] = None, timeout: float = TIMEOUT, **kw) -> Optional[requests.Response]:
    try:
        r = SESSION.post(url, headers=headers or JSON_HEADERS, timeout=min(timeout, TIMEOUT), **kw)
        if r.status_code not in (200, 201):
            logger.debug(f"[ext] POST {url} -> HTTP {r.status_code}")
            return None
        return r
    except Exception as e:
        logger.debug(f"[ext] POST {url} failed: {e}")
        return None


def cffi_get(url: str, *, timeout: float = TIMEOUT, impersonate: str = "chrome124", **kw):
    """GET with browser TLS fingerprint (curl_cffi) for Cloudflare / Akamai protected boards."""
    try:
        from curl_cffi import requests as cffi_requests
        r = cffi_requests.get(url, impersonate=impersonate, timeout=min(timeout, TIMEOUT), verify=False, **kw)
        if r.status_code != 200:
            logger.debug(f"[ext] CFFI {url} -> HTTP {r.status_code}")
            return None
        return r
    except Exception as e:
        logger.debug(f"[ext] CFFI {url} failed: {e}")
        return None


def soup(text: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(text, "lxml")
    except Exception:
        return BeautifulSoup(text, "html.parser")


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

def clean(text) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(str(text))).strip()


def strip_html(raw: str, limit: int = 1800) -> str:
    if not raw:
        return ""
    try:
        txt = BeautifulSoup(_html.unescape(raw), "html.parser").get_text(" ", strip=True)
    except Exception:
        txt = re.sub(r"<[^>]+>", " ", raw)
    return clean(txt)[:limit]


def with_country(loc: str, country: str, aliases: Iterable[str] = ()) -> str:
    loc = clean(loc).strip(" ,-·|")
    if not loc:
        return country
    low = loc.lower()
    for a in (country, *aliases):
        if a and a.lower() in low:
            return loc
    return f"{loc}, {country}"


def first_term(query: str) -> str:
    q = (query or "").strip()
    return q.split()[0].lower() if q.split() else q.lower()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def extract_json_after(text: str, marker: str):
    i = text.find(marker)
    if i < 0:
        return None
    i += len(marker)
    while i < len(text) and text[i] in " \t\r\n=":
        i += 1
    try:
        return json.JSONDecoder().raw_decode(text[i:])[0]
    except Exception:
        return None


def next_data(text: str):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def ld_json_jobs(text: str) -> List[dict]:
    """Return every schema.org JobPosting object embedded as JSON-LD in a page."""
    out: List[dict] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    out.append(d)
                for k in ("@graph", "itemListElement", "item", "mainEntity"):
                    if k in d:
                        stack.append(d[k])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dates
# ─────────────────────────────────────────────────────────────────────────────

def parse_date(raw) -> str:
    """ISO / epoch / 'dd.mm.yyyy' / relative multilingual ('3 days ago', 'il y a 2 jours', 'vor 5 Tagen',
    'hace 3 días', 'acum 2 zile', 'před 3 dny', '2 gün önce' ...) -> 'YYYY-MM-DD' or ''."""
    if raw is None or raw == "":
        return ""
    try:
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
            v = float(raw)
            if v > 1e11:
                v /= 1000.0
            if v > 1e8:
                return datetime.utcfromtimestamp(v).date().isoformat()
    except Exception:
        pass
    s = clean(raw).lower()
    today = datetime.utcnow().date()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            pass
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except Exception:
            pass
    if re.search(r"\b(today|just|now|heute|aujourd|hoy|hoje|azi|dnes|bugün|bugun|danas|dzisiaj|idag|i dag|tänään)\b", s):
        return today.isoformat()
    if re.search(r"\b(yesterday|gestern|hier|ayer|ontem|ieri|včera|vcera|dün|dun|jučer|wczoraj|igår|i går|eilen)\b", s):
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*\+?\s*([a-zA-Zа-яÀ-ÿăâîșțşţčćđšžůěřýöüğı]+)", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if re.match(r"(min|sec|sek|seg|std|stund|hour|heure|hora|uur|tim|ore|ora|hod|saat|h$)", unit):
            return today.isoformat()
        if re.match(r"(day|tag|jour|día|dia|dag|dni|dny|den|zi|gün|gun|dan|päiv|d$)", unit):
            return (today - timedelta(days=n)).isoformat()
        if re.match(r"(week|woche|semaine|semana|uke|uge|veck|tydz|týd|sapt|hafta|tjed|vik|w$)", unit):
            return (today - timedelta(weeks=n)).isoformat()
        if re.match(r"(month|monat|mois|mes|maand|måned|månad|miesi|měs|luni|lună|ay$|mjes|kuuk)", unit):
            return (today - timedelta(days=30 * n)).isoformat()
        if re.match(r"(year|jahr|an|año|ano|jaar|år|rok|yıl|godin|vuo)", unit):
            return (today - timedelta(days=365 * n)).isoformat()
    return ""


def is_expired(valid_through: str) -> bool:
    d = parse_date(valid_through)
    return bool(d and d < datetime.utcnow().date().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# Row builder
# ─────────────────────────────────────────────────────────────────────────────

_REMOTE_RE = re.compile(
    r"\b(remote|fully remote|100% remote|télétravail|teletrabajo|remoto|home ?office|fjernarbeid|"
    r"distans|zdalna|praca zdalna|uzaktan|la distanță|la distanta|na dálku|etätyö|thuiswerk)\b",
    re.I,
)


def remote_flag(*texts) -> bool:
    return bool(_REMOTE_RE.search(" ".join(clean(t) for t in texts if t)))


def row(site: str, title: str, company: str, location: str, job_url: str,
        description: str = "", date_posted: str = "", is_remote: Optional[bool] = None,
        job_url_direct: str = "", salary_text: str = "") -> dict:
    title = clean(title)
    description = clean(description)[:2000]
    return {
        "site": site,
        "title": title,
        "company": clean(company),
        "location": clean(location),
        "job_url": job_url,
        "job_url_direct": job_url_direct or job_url,
        "description": description,
        "date_posted": date_posted or "",
        "is_remote": remote_flag(title, location) if is_remote is None else bool(is_remote),
        "salary_text": clean(salary_text)[:80],
    }


def ld_to_row(site: str, jp: dict, country: str, default_url: str = "", aliases: Iterable[str] = ()) -> Optional[dict]:
    """Convert a schema.org JobPosting dict into a row (None when expired or incomplete)."""
    try:
        title = clean(jp.get("title") or jp.get("name"))
        url = (jp.get("url") or default_url or "").strip()
        if not title or not url:
            return None
        if is_expired(jp.get("validThrough") or ""):
            return None
        org = jp.get("hiringOrganization") or {}
        company = clean(org.get("name") if isinstance(org, dict) else org)
        locs = jp.get("jobLocation") or []
        if isinstance(locs, dict):
            locs = [locs]
        loc_txt = ""
        for l in locs:
            addr = (l or {}).get("address") or {}
            if isinstance(addr, dict):
                loc_txt = ", ".join(x for x in [clean(addr.get("addressLocality")), clean(addr.get("addressRegion"))] if x)
                if loc_txt:
                    break
        remote = str(jp.get("jobLocationType") or "").upper() == "TELECOMMUTE"
        return row(site, title, company, with_country(loc_txt, country, aliases), url,
                   strip_html(jp.get("description") or ""), parse_date(jp.get("datePosted") or ""),
                   remote or None)
    except Exception:
        return None
