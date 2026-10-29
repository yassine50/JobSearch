"""
Direct (no Google / Serper) scrapers for European local job boards.

Every public scraper has the signature ``scrape_xxx(query: str) -> List[dict]`` and
returns rows shaped exactly like the other local-board scrapers in
``local_boards.py``::

    {
        "site": str,            # short board id, e.g. "reed", "karriere.at"
        "title": str,
        "company": str,         # real employer ("" if unknown, never the board name)
        "location": str,        # always contains the country name
        "job_url": str,         # absolute URL of ONE specific posting
        "job_url_direct": str,  # external apply URL when known, else job_url
        "description": str,
        "date_posted": str,     # "YYYY-MM-DD" or ""
        "is_remote": bool,
    }

Rules followed by every scraper:
  * plain ``requests`` with a browser User-Agent, timeout <= 4.5 s per call,
    at most 2 HTTP calls, ~15 rows max;
  * everything wrapped in try/except -> ``[]`` on any failure (never raises);
  * postings flagged as expired / closed / archived are dropped when exposed.

Boards that were evaluated but are NOT implemented:
  * devitjobs.nl / swissdevjobs.ch / germantechjobs.de ``/api/jobsLight`` -> the
    domains now redirect to LinkedIn / jobcopilot sign-up pages (dead).
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import quote, quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("jobsearcher.local_scrapers_eu")

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
TIMEOUT = 3.2
MAX_ROWS = 15

_SESSION = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get(url: str, *, headers: Optional[dict] = None, **kw) -> Optional[requests.Response]:
    try:
        r = _SESSION.get(url, headers=headers or HEADERS, timeout=TIMEOUT, **kw)
        if r.status_code != 200:
            logger.debug(f"[eu] {url} -> HTTP {r.status_code}")
            return None
        return r
    except Exception as e:
        logger.debug(f"[eu] GET {url} failed: {e}")
        return None


def _clean(text) -> str:
    if text is None:
        return ""
    s = _html.unescape(str(text))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _strip_html(raw: str, limit: int = 1500) -> str:
    if not raw:
        return ""
    try:
        txt = BeautifulSoup(_html.unescape(raw), "html.parser").get_text(" ", strip=True)
    except Exception:
        txt = re.sub(r"<[^>]+>", " ", raw)
    return _clean(txt)[:limit]


def _iso(raw) -> str:
    """Return YYYY-MM-DD from an ISO-ish datetime string or epoch (s / ms)."""
    if raw is None or raw == "":
        return ""
    try:
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
            v = float(raw)
            if v > 1e11:  # milliseconds
                v /= 1000.0
            return datetime.utcfromtimestamp(v).date().isoformat()
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except Exception:
        pass
    return ""


_MONTHS = {
    # en
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # pt
    "fev": 2, "abr": 4, "mai": 5, "ago": 8, "set": 9, "out": 10, "dez": 12,
    # fr / es / de / nl / da / no
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "juin": 6, "juil": 7,
    "août": 8, "aout": 8, "déc": 12, "ene": 1, "dic": 12, "mär": 3, "okt": 10,
    "dez.": 12, "mei": 5, "maj": 5, "des": 12,
}

_TODAY_WORDS = (
    "today", "heute", "aujourd", "hoy", "hoje", "i dag", "idag", "vandaag", "dzisiaj",
    "just now", "nieuw", "new", "neu", "nouveau", "nueva", "nuevo", "nova", "ny ",
)
_YESTERDAY_WORDS = ("yesterday", "gestern", "hier", "ayer", "ontem", "i går", "igår", "gisteren", "wczoraj")


def _relative_date(raw: str) -> str:
    """Parse relative / localised dates ('vor 3 Tagen', 'il y a 5 jours', '30 dager siden',
    'Gestern veröffentlicht', '21.10.2026', '02/10/2026' ...) into YYYY-MM-DD ("" if unknown)."""
    if not raw:
        return ""
    s = _clean(raw).lower()
    today = datetime.now().date()

    iso = _iso(s)
    if iso:
        return iso
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except Exception:
            pass

    # Relative "N <unit>" (any language)
    m = re.search(r"(\d+)\s*\+?\s*([a-zA-ZÀ-ÿæøåäöüß]+)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if re.match(r"(min|sek|sec|seg|std|stund|hour|heure|hora|uur|tim|time|h$|godz)", unit):
            return today.isoformat()
        if re.match(r"(day|tag|jour|día|dia|dag|dni|dzie|d$)", unit):
            return (today - timedelta(days=n)).isoformat()
        if re.match(r"(week|woche|semaine|semana|uke|uge|veck|tydz|w$)", unit):
            return (today - timedelta(weeks=n)).isoformat()
        if re.match(r"(month|monat|mois|mes|maand|måned|månad|miesi)", unit):
            return (today - timedelta(days=30 * n)).isoformat()

    if any(w in s for w in _YESTERDAY_WORDS):
        return (today - timedelta(days=1)).isoformat()
    if any(w in s for w in _TODAY_WORDS):
        return today.isoformat()

    # "21 out" / "16 octobre" / "3 Oct 2026"
    m = re.search(r"\b(\d{1,2})\.?\s+([a-zéûôäå]{3,})\.?(?:\s+(\d{4}))?", s)
    if m:
        mo = _MONTHS.get(m.group(2)[:4]) or _MONTHS.get(m.group(2)[:3])
        if mo:
            try:
                yr = int(m.group(3)) if m.group(3) else today.year
                cand = date(yr, mo, int(m.group(1)))
                if cand > today and not m.group(3):
                    cand = date(yr - 1, mo, int(m.group(1)))
                return cand.isoformat()
            except Exception:
                pass
    return ""


def _with_country(loc: str, country: str, aliases: Iterable[str] = ()) -> str:
    loc = _clean(loc).strip(" ,-")
    if not loc:
        return country
    low = loc.lower()
    if country.lower() in low:
        return loc
    return f"{loc}, {country}"


_GENERIC_WORDS = {
    "developer", "developers", "dev", "engineer", "engineers", "entwickler", "entwicklerin",
    "développeur", "developpeur", "desarrollador", "programador", "programmer", "utvikler",
    "udvikler", "utvecklare", "ontwikkelaar", "programista", "senior", "junior", "mid",
    "lead", "remote", "job", "jobs", "the", "and", "of", "for", "de", "en", "h/f", "m/w/d",
    "software", "stack",
}


_ROLE_FALLBACK_PAT = re.compile(
    r"(?<![a-z0-9])(software|developer|engineer|entwickler|softwareentwickler|développeur|developpeur|"
    r"desarrollador|programador|programmer|programista|programator|programer|utvikler|udvikler|"
    r"utvecklare|ontwikkelaar|sviluppatore|kehittäjä|sovelluskehittäjä|ohjelmistokehittäjä|"
    r"vývojář|vyvojar|yazılım|yazilim|fullstack|full-stack|backend|frontend|mobile|devops)(?![a-z0-9])"
)


def _key_terms(query: str) -> List[str]:
    toks = [t for t in re.split(r"[^\w#+.]+", (query or "").lower()) if t]
    keys = [t for t in toks if t not in _GENERIC_WORDS and len(t) > 1]
    return keys


def _matches_strict(query: str, *texts) -> bool:
    """Strict keyword match for unfiltered static feeds (e.g. Arbeitnow)."""
    hay = " ".join(_clean(t) for t in texts if t).lower()
    keys = _key_terms(query)
    if not keys:
        return bool(_ROLE_FALLBACK_PAT.search(hay))
    return all(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", hay) for k in keys)


def _matches(query: str, *texts) -> bool:
    """True when all key query terms appear OR when the board's server-side search returned a compatible role title."""
    if _matches_strict(query, *texts):
        return True
    hay = " ".join(_clean(t) for t in texts if t).lower()
    return bool(_ROLE_FALLBACK_PAT.search(hay))


def _remote_flag(*texts) -> bool:
    hay = " ".join(_clean(t) for t in texts if t).lower()
    return bool(re.search(
        r"\b(remote|fully remote|100% remote|télétravail complet|teletrabajo|solo teletrabajo|"
        r"remoto|homeoffice only|fjernarbeid|hjemmekontor|distansarbete|på distans|zdalna)\b",
        hay,
    ))


def _row(site: str, title: str, company: str, location: str, job_url: str,
         description: str = "", date_posted: str = "", is_remote: bool = False,
         job_url_direct: str = "") -> dict:
    return {
        "site": site,
        "title": _clean(title),
        "company": _clean(company),
        "location": _clean(location),
        "job_url": job_url,
        "job_url_direct": job_url_direct or job_url,
        "description": _clean(description)[:2000],
        "date_posted": date_posted or "",
        "is_remote": bool(is_remote),
    }


def _slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-")


def _extract_json_after(text: str, marker: str):
    i = text.find(marker)
    if i < 0:
        return None
    i += len(marker)
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return json.JSONDecoder().raw_decode(text[i:])[0]


# ─────────────────────────────────────────────────────────────────────────────
# UK — Reed
# ─────────────────────────────────────────────────────────────────────────────

def scrape_reed(query: str) -> List[dict]:
    """Reed.co.uk via the embedded __NEXT_DATA__ search results (promoted ads skipped)."""
    out: List[dict] = []
    try:
        r = _get(f"https://www.reed.co.uk/jobs/{_slug(query)}-jobs")
        if not r:
            return []
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            return []
        sr = json.loads(m.group(1))["props"]["pageProps"]["searchResults"]
        today = datetime.now().date().isoformat()
        seen = set()
        for j in sr.get("jobs") or []:
            jd = j.get("jobDetail") or {}
            if jd.get("isPromoted") or j.get("isWithdrawn"):
                continue
            exp = _iso(jd.get("expiryDate"))
            if exp and exp < today:
                continue
            url = j.get("url") or ""
            if not url or not jd.get("jobId"):
                continue
            job_url = "https://www.reed.co.uk" + url if url.startswith("/") else url
            if job_url in seen:
                continue
            seen.add(job_url)
            company = (jd.get("ouName") or "").strip()
            if company.lower() == "anonymous":
                company = ""
            city = jd.get("displayLocationName") or ""
            county = jd.get("countyLocation") or ""
            loc = ", ".join(x for x in dict.fromkeys([city, county]) if x)
            ext = jd.get("externalUrl") or ""
            out.append(_row(
                "reed", jd.get("jobTitle"), company,
                _with_country(loc, "United Kingdom", ("uk",)),
                job_url, jd.get("jobDescriptionSnippet"),
                _iso(jd.get("displayDate") or jd.get("dateCreated")),
                (jd.get("workingOption") or "").lower() == "remote",
                ext if ext.startswith("http") else "",
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[Reed] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Austria — karriere.at
# ─────────────────────────────────────────────────────────────────────────────

def scrape_karriere_at(query: str) -> List[dict]:
    """karriere.at via window.VUE_INITIAL_STATE (only *active* items; expired ones skipped)."""
    out: List[dict] = []
    try:
        r = _get(f"https://www.karriere.at/jobs/{_slug(query)}", headers={"User-Agent": UA})
        if not r:
            return []
        state = _extract_json_after(r.text, "window.VUE_INITIAL_STATE =")
        items = (((state or {}).get("jobsSearchList") or {}).get("activeItems") or {}).get("items") or []
        for it in items:
            j = it.get("jobsItem") or {}
            if not j or j.get("isActive") is False or j.get("disabled"):
                continue
            link = j.get("link") or ""
            if not re.search(r"/jobs/\d+", link):
                continue
            comp = j.get("company") or {}
            company = "" if comp.get("isChiffre") or comp.get("companyEmpty") else (comp.get("name") or "")
            locs = ", ".join(l.get("name", "") for l in (j.get("locations") or []) if l.get("name"))
            desc = " ".join(x for x in [j.get("summary"), j.get("snippet")] if x)
            out.append(_row(
                "karriere.at", j.get("title"), company,
                _with_country(locs, "Austria", ("österreich",)),
                link, desc, _relative_date(j.get("date") or ""),
                False,
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[karriere.at] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Portugal — itjobs.pt
# ─────────────────────────────────────────────────────────────────────────────

def scrape_itjobs_pt(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://www.itjobs.pt/emprego", params={"q": query})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for block in soup.select("div.block"):
            dd = block.select_one(".date-box .d-d")
            dm = block.select_one(".date-box .d-m")
            posted = _relative_date(f"{dd.get_text(strip=True)} {dm.get_text(strip=True)}") if dd and dm else ""
            for li in block.select("ul.listing > li"):
                a = li.select_one("a.title[href*='/oferta/']")
                if not a:
                    continue
                href = a["href"]
                job_url = "https://www.itjobs.pt" + href if href.startswith("/") else href
                if job_url in seen:
                    continue
                seen.add(job_url)
                comp = li.select_one(".list-name a") or li.select_one(".list-name")
                details = li.select_one(".list-details")
                det_txt = details.get_text(" ", strip=True) if details else ""
                loc = re.split(r"\s{2,}|Híbrido|Remoto|Presencial", det_txt)[0].strip() if det_txt else ""
                out.append(_row(
                    "itjobs.pt", a.get("title") or a.get_text(" ", strip=True),
                    comp.get_text(" ", strip=True) if comp else "",
                    _with_country(loc, "Portugal"),
                    job_url, det_txt, posted,
                    "remoto" in det_txt.lower() and "híbrido" not in det_txt.lower(),
                ))
                if len(out) >= MAX_ROWS:
                    return out
    except Exception as e:
        logger.debug(f"[itjobs.pt] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Spain — Tecnoempleo, InfoJobs
# ─────────────────────────────────────────────────────────────────────────────

def scrape_tecnoempleo(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://www.tecnoempleo.com/ofertas-trabajo/", params={"te": query})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select("h3 a[href*='/rf-']"):
            job_url = a["href"].split("?")[0]
            if not job_url.startswith("http") or job_url in seen:
                continue
            seen.add(job_url)
            card = a.find_parent("div", class_="row") or a.parent
            comp_a = card.select_one("a[href$='-trabajo']")
            company = comp_a.get_text(" ", strip=True) if comp_a else ""
            loc_span = card.select_one("span.d-block")
            loc_txt = loc_span.get_text(" ", strip=True) if loc_span else ""
            city_b = loc_span.select_one("b") if loc_span else None
            city = city_b.get_text(" ", strip=True) if city_b else ""
            desc_el = card.select_one("span.hidden-md-down")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            card_txt = card.get_text(" ", strip=True).lower()
            if "oferta cerrada" in card_txt or "caducada" in card_txt:
                continue
            m = re.search(r"\d{2}/\d{2}/\d{4}", loc_txt or card_txt)
            remote = "100% remoto" in loc_txt.lower() or "(remoto" in loc_txt.lower()
            out.append(_row(
                "tecnoempleo", a.get("title") or a.get_text(" ", strip=True), company,
                _with_country(city or ("Remoto" if remote else ""), "Spain", ("españa",)),
                job_url, desc, _relative_date(m.group(0)) if m else "", remote,
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[tecnoempleo] {e}")
        return []
    return out


def scrape_infojobs(query: str) -> List[dict]:
    """InfoJobs.net via window.__INITIAL_PROPS__ (server-rendered JSON)."""
    out: List[dict] = []
    try:
        r = _get(
            "https://www.infojobs.net/jobsearch/search-results/list.xhtml",
            params={"keyword": query},
        )
        if not r:
            return []
        m = re.search(r'window\.__INITIAL_PROPS__ = JSON\.parse\("(.*?)"\);?\s*</script>', r.text, re.S)
        if not m:
            return []
        props = json.loads(json.loads('"' + m.group(1) + '"'))
        for o in props.get("offers") or []:
            link = o.get("link") or ""
            if not link or "/of-i" not in link:
                continue
            if link.startswith("//"):
                link = "https:" + link
            job_url = link.split("?")[0]
            tele = (o.get("teleworking") or "")
            city = o.get("city") or o.get("province") or ""
            out.append(_row(
                "infojobs", o.get("title"), o.get("companyName") or "",
                _with_country(city, "Spain", ("españa",)),
                job_url, o.get("description") or "", _iso(o.get("publishedAt")),
                "solo teletrabajo" in tele.lower() or tele.lower() == "teletrabajo",
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[infojobs] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Denmark — Jobindex
# ─────────────────────────────────────────────────────────────────────────────

def scrape_jobindex(query: str) -> List[dict]:
    """Jobindex.dk via the embedded `var Stash = {...}` search response."""
    out: List[dict] = []
    try:
        r = _get("https://www.jobindex.dk/jobsoegning", params={"q": query})
        if not r:
            return []
        stash = _extract_json_after(r.text, "var Stash =") or {}
        results = (
            ((stash.get("jobsearch/result_app/list") or {}).get("storeData") or {})
            .get("searchResponse") or {}
        ).get("results") or []
        today = datetime.now().date().isoformat()
        for j in results:
            if j.get("is_archived"):
                continue
            last = j.get("lastdate") or ""
            if last and _iso(last) and _iso(last) < today:
                continue
            tid = j.get("tid") or ""
            job_url = j.get("share_url") or (f"https://www.jobindex.dk/vis-job/{tid}" if tid else "")
            if not job_url:
                continue
            area = j.get("area") or ""
            if not area and j.get("addresses"):
                area = (j["addresses"][0] or {}).get("city") or ""
            apply_url = j.get("apply_url") or ""
            out.append(_row(
                "jobindex", j.get("headline"), j.get("companytext") or "",
                _with_country(area, "Denmark", ("danmark",)),
                job_url, _strip_html(j.get("html") or "", 1200), _iso(j.get("firstdate")),
                bool(j.get("home_workplace")),
                apply_url if isinstance(apply_url, str) and apply_url.startswith("http") else "",
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[jobindex] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Norway — FINN.no, arbeidsplassen (NAV)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_finn(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://www.finn.no/job/search", params={"q": query})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for art in soup.select("article"):
            a = art.select_one("a.job-card-link[href*='/job/ad/']") or art.select_one("a[href*='/job/ad/']")
            if not a:
                continue
            job_url = a["href"].split("?")[0]
            if job_url.startswith("/"):
                job_url = "https://www.finn.no" + job_url
            if job_url in seen:
                continue
            seen.add(job_url)
            comp_el = art.select_one(".text-caption strong") or art.select_one("strong")
            company = comp_el.get_text(" ", strip=True) if comp_el else ""
            company = re.sub(r"\s*\(via [^)]*\)\s*$", "", company)
            h3 = art.select_one("h3")
            pills = [li.get_text(" ", strip=True) for li in art.select("ul.job-card__pills li")]
            t = art.select_one("time[datetime]")
            loc = pills[0] if pills and not (t and t.get_text(strip=True) == pills[0]) else ""
            txt = art.get_text(" ", strip=True).lower()
            if "utløpt" in txt or "frist utløpt" in txt:
                continue
            out.append(_row(
                "finn.no", a.get_text(" ", strip=True), company,
                _with_country(loc, "Norway", ("norge",)),
                job_url, h3.get_text(" ", strip=True) if h3 else "",
                _iso(t["datetime"]) if t else "",
                _remote_flag(loc),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[finn.no] {e}")
        return []
    return out


def scrape_arbeidsplassen(query: str) -> List[dict]:
    """arbeidsplassen.nav.no — the JSON search endpoint used by its own frontend."""
    out: List[dict] = []
    try:
        r = _get(
            "https://arbeidsplassen.nav.no/stillinger/api/search",
            params={"q": query},
            headers=JSON_HEADERS,
        )
        if not r:
            return []
        hits = ((r.json() or {}).get("hits") or {}).get("hits") or []
        today = datetime.now().date().isoformat()
        seen_ref = set()
        for h in hits:
            s = h.get("_source") or {}
            if (s.get("status") or "ACTIVE").upper() != "ACTIVE":
                continue
            exp = _iso(s.get("expires"))
            if exp and exp < today:
                continue
            uuid = s.get("uuid") or h.get("_id")
            if not uuid:
                continue
            props = s.get("properties") or {}
            title = (props.get("jobtitle") or s.get("title") or "").strip()
            employer = (s.get("employer") or {}).get("name") or s.get("businessName") or ""
            dedupe = (title.lower(), (s.get("businessName") or employer).lower()[:20])
            if dedupe in seen_ref:
                continue
            seen_ref.add(dedupe)
            locs = s.get("locationList") or []
            city = ""
            if locs:
                city = (locs[0].get("city") or locs[0].get("municipal") or locs[0].get("county") or "").title()
            meta = s.get("generatedSearchMetadata") or {}
            desc = " ".join(x for x in [s.get("title"), meta.get("shortSummary")] if x)
            remote_prop = " ".join(props.get("remote") or []) if isinstance(props.get("remote"), list) else str(props.get("remote") or "")
            out.append(_row(
                "arbeidsplassen", title, s.get("businessName") or employer,
                _with_country(city, "Norway", ("norge",)),
                f"https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}",
                desc, _iso(s.get("published")),
                "hjemmekontor" == remote_prop.lower().strip() or "kun hjemmekontor" in remote_prop.lower(),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[arbeidsplassen] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sweden — Arbetsförmedlingen JobTech API
# ─────────────────────────────────────────────────────────────────────────────

def scrape_jobtech_se(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get(
            "https://jobsearch.api.jobtechdev.se/search",
            params={"q": query, "limit": MAX_ROWS},
            headers=JSON_HEADERS,
        )
        if not r:
            return []
        today = datetime.now().date().isoformat()
        for h in (r.json() or {}).get("hits") or []:
            if h.get("removed"):
                continue
            dl = _iso(h.get("application_deadline"))
            if dl and dl < today:
                continue
            job_url = h.get("webpage_url") or (f"https://arbetsformedlingen.se/platsbanken/annonser/{h.get('id')}" if h.get("id") else "")
            if not job_url:
                continue
            emp = h.get("employer") or {}
            addr = h.get("workplace_address") or {}
            city = addr.get("municipality") or addr.get("city") or addr.get("region") or ""
            apply = (h.get("application_details") or {}).get("url") or ""
            desc = ((h.get("description") or {}).get("text") or "")
            wm = ((h.get("workplace_model") or {}).get("label") or "")
            out.append(_row(
                "arbetsformedlingen", h.get("headline"), emp.get("name") or emp.get("workplace") or "",
                _with_country(city, "Sweden", ("sverige",)),
                job_url, desc[:2000], _iso(h.get("publication_date")),
                "distans" in wm.lower() or "remote" in wm.lower(),
                apply if apply.startswith("http") else "",
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[jobtech] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Poland — NoFluffJobs
# ─────────────────────────────────────────────────────────────────────────────

def scrape_nofluffjobs(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        q = (query or "").strip()
        first = q.split()[0] if q.split() else q
        body = {"criteriaSearch": {"requirement": [first.lower()]}, "page": 1}
        if len(q.split()) > 1 and first.lower() in _GENERIC_WORDS:
            body = {"rawSearch": q, "page": 1}
        r = _SESSION.post(
            "https://nofluffjobs.com/api/search/posting",
            params={"page": 1, "salaryCurrency": "PLN", "salaryPeriod": "month", "region": "pl"},
            json=body,
            headers={**JSON_HEADERS, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        seen = set()
        for p in (r.json() or {}).get("postings") or []:
            if "pl" not in (p.get("regions") or ["pl"]):
                continue
            key = p.get("reference") or (p.get("title"), p.get("name"))
            if key in seen:
                continue
            loc_obj = p.get("location") or {}
            places = loc_obj.get("places") or []
            fully_remote = bool(loc_obj.get("fullyRemote") or p.get("fullyRemote"))
            pl_cities = [
                pl.get("city") for pl in places
                if pl.get("city") and pl.get("city") != "Remote"
                and ((pl.get("country") or {}).get("code") in (None, "POL"))
            ]
            in_poland = any((pl.get("country") or {}).get("code") == "POL" for pl in places)
            if not in_poland and not pl_cities:
                continue
            url = p.get("url") or ""
            if not url:
                continue
            seen.add(key)
            city = pl_cities[0] if pl_cities else ("Remote" if fully_remote else "")
            tiles = [t.get("value") for t in ((p.get("tiles") or {}).get("values") or []) if t.get("value")]
            sal = p.get("salary") or {}
            sal_txt = f"{sal.get('from')}-{sal.get('to')} {sal.get('currency')} ({sal.get('type')})" if sal else ""
            desc = "; ".join(x for x in [", ".join(tiles), ", ".join(p.get("seniority") or []), sal_txt] if x)
            out.append(_row(
                "nofluffjobs", p.get("title"), p.get("name") or "",
                _with_country(city, "Poland", ("polska",)),
                f"https://nofluffjobs.com/pl/job/{url}", desc,
                _iso(p.get("renewed") or p.get("posted")), fully_remote,
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[nofluffjobs] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Netherlands — Jobbird (+ Arbeitnow NL filter)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_jobbird(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://www.jobbird.com/nl/vacature", params={"s": query},
                 headers={**HEADERS, "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select("a.job-search__result-list__result__title[href*='/nl/vacature/']"):
            job_url = a["href"].split("?")[0]
            if not re.search(r"/nl/vacature/\d+", job_url) or job_url in seen:
                continue
            seen.add(job_url)
            card = a.find_parent("div", class_="row") or a.parent
            comp = card.select_one(".cro-recruiter-name")
            loc = card.select_one(".cro-job-location")
            posted = card.select_one(".cro-time-posted")
            perks = card.select_one(".job-search__job-card__perks")
            snippet = card.select_one(".job-search__result-list__result__description, p")
            card_txt = card.get_text(" ", strip=True).lower()
            if "verlopen" in card_txt or "gesloten" in card_txt:
                continue
            desc = " ".join(x.get_text(" ", strip=True) for x in [snippet, perks] if x)
            loc_txt = loc.get_text(" ", strip=True) if loc else ""
            out.append(_row(
                "jobbird", a.get_text(" ", strip=True),
                comp.get_text(" ", strip=True) if comp else "",
                _with_country(loc_txt, "Netherlands", ("nederland",)),
                job_url, desc,
                _relative_date(posted.get_text(" ", strip=True)) if posted else "",
                _remote_flag(loc_txt, a.get_text(" ", strip=True)),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[jobbird] {e}")
        return []
    return out


# Arbeitnow public API (one shared, short-lived cache; the feed is ~2 MB, hourly updates)
_ARBEITNOW_CACHE: Dict[str, object] = {"ts": 0.0, "data": []}
_ARBEITNOW_LOCK = threading.Lock()
_ARBEITNOW_TTL = 15 * 60

_COUNTRY_CITY_HINTS: Dict[str, tuple] = {
    "Germany": (
        "germany", "deutschland", "berlin", "münchen", "munich", "hamburg", "köln", "cologne",
        "frankfurt", "stuttgart", "düsseldorf", "dusseldorf", "leipzig", "dresden", "hannover",
        "nürnberg", "nuremberg", "bremen", "essen", "dortmund", "bonn", "karlsruhe", "mannheim",
        "münster", "augsburg", "wiesbaden", "chemnitz", "potsdam", "freiburg", "heidelberg",
        "aachen", "kiel", "regensburg", "ulm", "mainz", "darmstadt", "bayern", "hessen",
        "sachsen", "nordrhein-westfalen", "baden-württemberg", "niedersachsen", "brandenburg",
        "rheinland-pfalz", "schleswig-holstein", "thüringen",
    ),
    "Netherlands": (
        "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "den haag", "the hague",
        "eindhoven", "groningen", "tilburg", "almere", "breda", "nijmegen", "haarlem", "arnhem",
        "delft", "leiden", "zwolle", "noord-holland", "zuid-holland", "noord-brabant", "gelderland",
    ),
    "Switzerland": (
        "switzerland", "schweiz", "suisse", "svizzera", "zürich", "zurich", "genf", "geneva",
        "genève", "basel", "bern", "lausanne", "luzern", "lucerne", "zug", "winterthur",
        "st. gallen", "lugano",
    ),
}


def _arbeitnow_feed() -> list:
    with _ARBEITNOW_LOCK:
        if time.time() - float(_ARBEITNOW_CACHE["ts"]) < _ARBEITNOW_TTL and _ARBEITNOW_CACHE["data"]:
            return _ARBEITNOW_CACHE["data"]  # type: ignore[return-value]
    r = _get("https://www.arbeitnow.com/api/job-board-api", headers=JSON_HEADERS)
    if not r:
        return []
    data = (r.json() or {}).get("data") or []
    with _ARBEITNOW_LOCK:
        _ARBEITNOW_CACHE["ts"] = time.time()
        _ARBEITNOW_CACHE["data"] = data
    return data


def _scrape_arbeitnow_country(query: str, country: str) -> List[dict]:
    out: List[dict] = []
    try:
        hints = _COUNTRY_CITY_HINTS[country]
        # avoid "essen"/"bern"/"ulm" substring false-positives with word-boundary match
        pat = re.compile(r"(?<![a-zà-ÿ])(" + "|".join(re.escape(h) for h in hints) + r")(?![a-zà-ÿ])")
        for j in _arbeitnow_feed():
            loc = j.get("location") or ""
            if not pat.search(loc.lower()):
                continue
            tags = " ".join(j.get("tags") or [])
            desc = _strip_html(j.get("description") or "", 2000)
            if not _matches_strict(query, j.get("title"), tags, desc):
                continue
            url = j.get("url") or ""
            if not url.startswith("http"):
                continue
            loc_disp = loc.split(";")[0].strip()
            out.append(_row(
                "arbeitnow", j.get("title"), j.get("company_name") or "",
                _with_country(loc_disp, country, hints[:2]),
                url, desc, _iso(j.get("created_at")), bool(j.get("remote")),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[arbeitnow/{country}] {e}")
        return []
    return out


def scrape_arbeitnow_de(query: str) -> List[dict]:
    return _scrape_arbeitnow_country(query, "Germany")


def scrape_arbeitnow_nl(query: str) -> List[dict]:
    return _scrape_arbeitnow_country(query, "Netherlands")


def scrape_arbeitnow_ch(query: str) -> List[dict]:
    return _scrape_arbeitnow_country(query, "Switzerland")


# ─────────────────────────────────────────────────────────────────────────────
# Switzerland — jobs.ch
# ─────────────────────────────────────────────────────────────────────────────

def scrape_jobs_ch(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get(
            "https://www.jobs.ch/api/v1/public/search",
            params={"query": query, "rows": 20},
            headers=JSON_HEADERS,
        )
        if not r:
            return []
        for d in (r.json() or {}).get("documents") or []:
            if d.get("is_active") is False:
                continue
            links = d.get("_links") or {}
            job_url = ((links.get("detail_en") or links.get("detail_de") or links.get("detail_fr") or {}).get("href") or "")
            if not job_url and d.get("job_id"):
                job_url = f"https://www.jobs.ch/en/vacancies/detail/{d['job_id']}/"
            if not job_url:
                continue
            company = d.get("company_name") or "" if d.get("company_visible", True) else ""
            title = d.get("title") or ""
            out.append(_row(
                "jobs.ch", title, company,
                _with_country(d.get("place") or "", "Switzerland", ("schweiz", "suisse")),
                job_url, d.get("preview") or "",
                _iso(d.get("initial_publication_date") or d.get("publication_date")),
                _remote_flag(title),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[jobs.ch] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# France — HelloWork
# ─────────────────────────────────────────────────────────────────────────────

def scrape_hellowork(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get(
            "https://www.hellowork.com/fr-fr/emploi/recherche.html",
            params={"k": query},
            headers={**HEADERS, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
        )
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for card in soup.select("[data-cy='serpCard']"):
            a = card.select_one("a[data-cy='offerTitle'][href*='/fr-fr/emplois/']")
            if not a:
                continue
            href = a["href"].split("?")[0]
            if not re.search(r"/fr-fr/emplois/\d+\.html$", href):
                continue
            job_url = "https://www.hellowork.com" + href if href.startswith("/") else href
            if job_url in seen:
                continue
            seen.add(job_url)
            spans = a.select("h3 span")
            title = spans[0].get_text(" ", strip=True) if spans else a.get_text(" ", strip=True)
            company = spans[1].get_text(" ", strip=True) if len(spans) > 1 else ""
            loc_el = card.select_one("[data-cy='localisationCard']")
            loc = loc_el.get_text(" ", strip=True) if loc_el else ""
            tags = [t.get_text(" ", strip=True) for t in card.select(".tag-secondary-s")]
            date_el = card.select_one(".text-grey-500")
            tele = " ".join(tags).lower()
            out.append(_row(
                "hellowork", title, company,
                _with_country(loc, "France"),
                job_url, a.get("aria-label") or " · ".join(tags),
                _relative_date(date_el.get_text(" ", strip=True)) if date_el else "",
                "télétravail complet" in tele or "full remote" in tele,
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[hellowork] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Hungary & Czech Republic — NoFluffJobs CEE API
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_nofluffjobs_city(query: str, city_hint: str, country_code: str, country_label: str, region_slug: str) -> List[dict]:
    out: List[dict] = []
    try:
        q = (query or "").strip()
        first = q.split()[0] if q.split() else q
        search_tok = first if first.lower() not in _GENERIC_WORDS else q
        body = {"rawSearch": f"{city_hint} {search_tok}".strip(), "page": 1}
        r = _SESSION.post(
            "https://nofluffjobs.com/api/search/posting",
            params={"page": 1, "salaryCurrency": "EUR", "salaryPeriod": "month", "region": region_slug},
            json=body,
            headers={**JSON_HEADERS, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        seen = set()
        for p in (r.json() or {}).get("postings") or []:
            key = p.get("reference") or (p.get("title"), p.get("name"))
            if key in seen:
                continue
            loc_obj = p.get("location") or {}
            places = loc_obj.get("places") or []
            fully_remote = bool(loc_obj.get("fullyRemote") or p.get("fullyRemote"))
            local_cities = [
                pl.get("city") for pl in places
                if pl.get("city") and (
                    (pl.get("country") or {}).get("code") == country_code
                    or city_hint.lower() in (pl.get("city") or "").lower()
                )
            ]
            if not local_cities and not any((pl.get("country") or {}).get("code") == country_code for pl in places):
                continue
            url = p.get("url") or ""
            if not url:
                continue
            seen.add(key)
            city = local_cities[0] if local_cities else city_hint
            tiles = [t.get("value") for t in ((p.get("tiles") or {}).get("values") or []) if t.get("value")]
            desc = "; ".join(x for x in [", ".join(tiles), ", ".join(p.get("seniority") or [])] if x)
            if not _matches(query, p.get("title"), desc):
                continue
            out.append(_row(
                f"nofluffjobs.{region_slug}", p.get("title"), p.get("name") or "",
                _with_country(city, country_label),
                f"https://nofluffjobs.com/{region_slug}/job/{url}", desc,
                _iso(p.get("renewed") or p.get("posted")), fully_remote,
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[nofluffjobs_{region_slug}] {e}")
        return []
    return out


def scrape_nofluffjobs_hu(query: str) -> List[dict]:
    return _scrape_nofluffjobs_city(query, "Budapest", "HUN", "Hungary", "hu")


def scrape_nofluffjobs_cz(query: str) -> List[dict]:
    # NoFluffJobs uses region="com" (or "pl") for Czechia; region="cz" returns empty body
    return _scrape_nofluffjobs_city(query, "Prague", "CZE", "Czech Republic", "com")


def scrape_startupjobs_cz(query: str) -> List[dict]:
    """Direct JSON API scraper for StartupJobs.cz (Czech Republic's leading tech job board)."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    search_terms = [first] if first not in _GENERIC_WORDS else ["developer"]
    if first in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        search_terms.append("mobile")
    seen = set()
    for term in search_terms:
        try:
            r = _SESSION.post(
                "https://back.startupjobs.cz/api/search-offers",
                json={"query": term},
                headers={**JSON_HEADERS, "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            offers = r.json()
            if not isinstance(offers, list):
                continue
            for o in offers:
                if not isinstance(o, dict) or not o.get("id"):
                    continue
                oid = o["id"]
                name_obj = o.get("name") or {}
                title = (
                    (name_obj.get("en") or name_obj.get("cs") or "")
                    if isinstance(name_obj, dict)
                    else str(name_obj)
                ).strip()
                slug_obj = o.get("slug") or {}
                slug = (
                    (slug_obj.get("cs") or slug_obj.get("en") or "")
                    if isinstance(slug_obj, dict)
                    else str(slug_obj)
                ).strip()
                if not title:
                    continue
                job_url = f"https://www.startupjobs.cz/nabidka/{oid}/{slug}" if slug else f"https://www.startupjobs.cz/nabidka/{oid}"
                if job_url in seen:
                    continue
                seen.add(job_url)
                comp_obj = o.get("company") or {}
                company = (comp_obj.get("name") if isinstance(comp_obj, dict) else "") or "Startup via StartupJobs.cz"
                locs_obj = o.get("locations") or {}
                loc_en = (locs_obj.get("en") or locs_obj.get("cs") or "Prague") if isinstance(locs_obj, dict) else "Prague"
                if loc_en.lower() in ("remote", "plně remote"):
                    loc_str = "Prague, Czech Republic (Remote)"
                else:
                    loc_str = _with_country(loc_en, "Czech Republic", ("česko", "czechia", "praha", "prague", "brno"))
                desc = f"{title} at {company} ({loc_str})"
                out.append(_row(
                    "startupjobs.cz", title, company, loc_str, job_url, desc, "",
                    bool(o.get("collaboration") and "remote" in str(locs_obj).lower()),
                ))
                if len(out) >= MAX_ROWS:
                    return out
        except Exception as e:
            logger.debug(f"[startupjobs.cz] {term}: {e}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Germany — XING Jobs DE
# ─────────────────────────────────────────────────────────────────────────────

def scrape_xing_de(query: str) -> List[dict]:
    """Direct HTML scraper for XING Jobs (xing.com/jobs/search — Germany's DACH career network)."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    search_terms = [q]
    if first in ("flutter", "dart") and "mobile" not in q.lower():
        search_terms.append("Flutter Developer")
    seen = set()
    for term in search_terms:
        try:
            r = _get("https://www.xing.com/jobs/search", params={"keywords": term})
            if not r:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/jobs/']"):
                href = (a.get("href") or "").split("?")[0].strip()
                if not re.match(r"^/jobs/[a-z0-9-]+-\d+$", href):
                    continue
                job_url = f"https://www.xing.com{href}"
                if job_url in seen:
                    continue
                card = a.find_parent("article") or a.find_parent("li") or a
                h_el = card.select_one("h2, h3")
                lines = [ln.strip() for ln in card.get_text("\n", strip=True).splitlines() if ln.strip()]
                title = h_el.get_text(" ", strip=True) if h_el else (lines[0] if lines else "")
                if not title or len(title) < 3:
                    continue
                seen.add(job_url)
                company = lines[1] if len(lines) > 1 and lines[1] != title else "Employer via XING"
                city = lines[2] if len(lines) > 2 and len(lines[2]) <= 40 else "Berlin"
                time_el = card.select_one("time[datetime]")
                posted = _iso(time_el.get("datetime")) if time_el else ""
                desc = f"{' | '.join(lines[:6])}"
                out.append(_row(
                    "xing.com", title, company,
                    _with_country(city, "Germany", ("deutschland",)),
                    job_url, desc, posted,
                    _remote_flag(title, desc),
                ))
                if len(out) >= MAX_ROWS:
                    return out
        except Exception as e:
            logger.debug(f"[xing.com] {term}: {e}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Country-Scoped European ATS & Local Boards Helper (Finland, Belgium, Ireland, Italy, Croatia, Turkey)
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_freehire_country(
    query: str,
    country_label: str,
    site_tag: str,
    city_hints: tuple,
    default_city: str,
) -> List[dict]:
    """Query FreeHire's European ATS & EURES index strictly filtered to the target country's cities."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    terms = [f"{first} {country_label}"]
    if first in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        terms.append(f"mobile developer {country_label}")
    elif first not in ("developer", "software"):
        terms.append(f"software developer {country_label}")
    else:
        terms.append(f"developer {country_label}")

    seen = set()
    for fq in terms:
        try:
            r = _SESSION.get(
                "https://freehire.me/api/v1/agent/jobs/search",
                params={"q": fq, "limit": "25"},
                headers={"User-Agent": "freehire-search-cli/0.1.0", "Accept": "application/json"},
                timeout=3.8,
            )
            if r.status_code != 200:
                continue
            for it in ((r.json() or {}).get("data") or (r.json() or {}).get("jobs") or []):
                loc = (it.get("location") or "").strip().strip(",")
                pub_slug = (it.get("public_slug") or "").strip()
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                loc_check_blob = f"{loc} {title} {pub_slug}".lower()
                if not any(h in loc_check_blob for h in city_hints):
                    continue
                comp = (it.get("company") or f"Employer in {country_label}").strip()
                if comp.lower() in ("betfair", "paddy power", "flutterbe"):
                    continue
                jurl = (it.get("apply_url") or it.get("url") or "").strip().split("?")[0]
                if "whatjobs." in jurl.lower() and pub_slug:
                    jurl = f"https://freehire.me/jobs/{pub_slug}"
                if not jurl or "flutterbe." in jurl.lower() or jurl in seen:
                    continue
                seen.add(jurl)
                raw_desc = _strip_html(it.get("description") or "", 1400)
                desc = f"{title} at {comp} ({loc or default_city}, {country_label}) — {raw_desc}"
                out.append(_row(
                    site_tag,
                    title,
                    comp,
                    _with_country(loc or default_city, country_label, city_hints[:2]),
                    jurl,
                    desc,
                    _iso(it.get("posted_at") or it.get("created_at")),
                    bool(it.get("remote")) or _remote_flag(loc, title),
                ))
                if len(out) >= MAX_ROWS:
                    return out
        except Exception as e:
            logger.debug(f"[freehire/{country_label}] {fq}: {e}")
    return out


def _scrape_talent_eu(cc: str, country_label: str, site_tag: str, default_city: str, query: str) -> List[dict]:
    """Direct HTML JobCard scraper for {cc}.talent.com/jobs (Belgium, Italy, Finland, etc.)."""
    out: List[dict] = []
    q = (query or "").strip()
    seen = set()
    try:
        r = _get(f"https://{cc}.talent.com/jobs", params={"k": q})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div[data-new-id]")[:MAX_ROWS]:
            nid = (card.get("data-new-id") or "").strip()
            if not nid:
                continue
            job_url = f"https://{cc}.talent.com/view?id={nid}"
            if job_url in seen:
                continue
            lines = [
                ln.strip()
                for ln in card.get_text("\n", strip=True).splitlines()
                if ln.strip() and ln.strip() != "•"
            ]
            if len(lines) < 3:
                continue
            title = lines[0]
            comp = lines[1]
            if comp.lower() in ("betfair", "paddy power", "flutterbe"):
                continue
            loc_raw = lines[2].strip(" ,") or default_city
            loc = _with_country(loc_raw, country_label)
            desc = f"{title} at {comp} ({loc}) — {' '.join(lines[3:6])}"
            seen.add(job_url)
            out.append(_row(
                site_tag,
                title,
                comp,
                loc,
                job_url,
                desc,
                "",
                _remote_flag(title, loc, desc),
            ))
    except Exception as e:
        logger.debug(f"[{cc}.talent.com] {q}: {e}")
    return out


def scrape_duunitori_fi(query: str) -> List[dict]:
    """Finland local tech jobs (fi.talent.com + Duunitori)."""
    out = _scrape_talent_eu("fi", "Finland", "duunitori.fi", "Helsinki", query)
    if len(out) < 5:
        out.extend(_scrape_freehire_country(
            query,
            "Finland",
            "duunitori.fi",
            ("finland", "suomi", "helsinki", "espoo", "tampere", "turku", "oulu", "vantaa", "jyväskylä", "kuopio"),
            "Helsinki",
        ))
    return out[:MAX_ROWS]


def scrape_stepstone_be(query: str) -> List[dict]:
    """Belgium local tech jobs (be.talent.com + BrusselsJobs.com)."""
    out = _scrape_talent_eu("be", "Belgium", "stepstone.be", "Brussels", query)
    try:
        r = _get("https://www.brusselsjobs.com/", params={"s": query})
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            seen = {row["job_url"] for row in out}
            for a in soup.select("h2 a[href*='/job_display/'], h3 a[href*='/job_display/']"):
                href = (a.get("href") or "").split("?")[0].strip()
                if not href:
                    continue
                job_url = href if href.startswith("http") else f"https://www.brusselsjobs.com{href}"
                if job_url in seen:
                    continue
                title = a.get_text(" ", strip=True)
                if not title:
                    continue
                seen.add(job_url)
                out.append(_row(
                    "brusselsjobs.com",
                    title,
                    "Employer via BrusselsJobs",
                    "Brussels, Belgium",
                    job_url,
                    f"{title} (Brussels, Belgium)",
                    "",
                    _remote_flag(title),
                ))
                if len(out) >= MAX_ROWS:
                    break
    except Exception as e:
        logger.debug(f"[brusselsjobs.com] {query}: {e}")
    return out[:MAX_ROWS]


def scrape_irishjobs_ie(query: str) -> List[dict]:
    """Ireland local tech jobs via RecruitIreland.com direct search."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    terms = [q]
    if first in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        terms.append("mobile developer")
    seen = set()
    for term in terms:
        try:
            r = _get("https://www.recruitireland.com/search/jobs", params={"query": term})
            if not r:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/company/'][href*='/job/']"):
                href = (a.get("href") or "").split("?")[0].strip()
                if not href or href in seen:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or title.lower() in ("view job", "save job") or title.lower().startswith("executive job"):
                    continue
                seen.add(href)
                m_comp = re.search(r"/company/([^/]+)/job/", href)
                company = m_comp.group(1).replace("-", " ").title() if m_comp else "Employer via RecruitIreland"
                card = a.parent.parent if a.parent and a.parent.parent else a
                lines = [
                    ln.strip()
                    for ln in card.get_text("\n", strip=True).splitlines()
                    if ln.strip() and ln.strip().lower() not in ("view job", "save job")
                ]
                snippet = lines[1] if len(lines) > 1 else ""
                loc_raw = lines[2] if len(lines) > 2 and len(lines[2]) <= 45 else "Dublin"
                loc = _with_country(loc_raw, "Ireland", ("ireland", "dublin", "cork", "galway", "limerick"))
                desc = f"{title} at {company} ({loc}) — {snippet}"
                out.append(_row(
                    "recruitireland.com",
                    title,
                    company,
                    loc,
                    href,
                    desc,
                    "",
                    _remote_flag(title, snippet, loc),
                ))
                if len(out) >= MAX_ROWS:
                    return out
        except Exception as e:
            logger.debug(f"[recruitireland.com] {term}: {e}")
    return out


def scrape_italyjobs_it(query: str) -> List[dict]:
    """Italy local tech jobs (it.talent.com + ReteInformaticaLavoro.it)."""
    out = _scrape_talent_eu("it", "Italy", "infojobs.it", "Milan", query)
    try:
        r = _get("https://www.reteinformaticalavoro.it/offerte-di-lavoro/", params={"cerca": query})
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            seen = {row["job_url"] for row in out}
            for a in soup.select("a[href*='/lavoro/']"):
                href = (a.get("href") or "").split("?")[0].strip()
                if not re.search(r"/lavoro/\d+/", href):
                    continue
                job_url = href if href.startswith("http") else f"https://www.reteinformaticalavoro.it{href}"
                if job_url in seen:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or len(title) < 3:
                    continue
                seen.add(job_url)
                out.append(_row(
                    "reteinformaticalavoro.it",
                    title,
                    "Employer via ReteInformaticaLavoro",
                    "Milan, Italy",
                    job_url,
                    f"{title} (Milan, Italy)",
                    "",
                    _remote_flag(title),
                ))
                if len(out) >= MAX_ROWS:
                    break
    except Exception as e:
        logger.debug(f"[reteinformaticalavoro.it] {query}: {e}")
    return out[:MAX_ROWS]


def scrape_posao_hr(query: str) -> List[dict]:
    """Croatia local tech jobs: direct Posao.hr HTML scraper + Croatia ATS."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    terms = [first]
    if first in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        terms.extend(["mobile", "developer"])
    elif first not in ("developer", "programer"):
        terms.append("developer")
    seen = set()
    for term in terms:
        try:
            r = _get(f"https://www.posao.hr/poslovi/izraz/{_slug(term)}/")
            if not r:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/oglasi/']"):
                raw_href = a.get("href") or ""
                if "source=featured-ads" in raw_href:
                    continue
                href = raw_href.split("?")[0].strip()
                if not re.search(r"/oglasi/[^/]+/\d+/?$", href):
                    continue
                job_url = href if href.startswith("http") else f"https://www.posao.hr{href}"
                if job_url in seen:
                    continue
                lines = [ln.strip() for ln in a.get_text("\n", strip=True).splitlines() if ln.strip()]
                if not lines:
                    continue
                title = lines[0]
                if not _ROLE_FALLBACK_PAT.search(title.lower()) and first not in title.lower():
                    continue
                seen.add(job_url)
                city = lines[1] if len(lines) > 1 and len(lines[1]) <= 35 else "Zagreb"
                posted = _relative_date(lines[2]) if len(lines) > 2 else ""
                desc = f"{title} ({city}, Croatia)"
                out.append(_row(
                    "posao.hr", title, "Employer via Posao.hr",
                    _with_country(city, "Croatia", ("hrvatska", "zagreb", "split", "rijeka", "osijek")),
                    job_url, desc, posted, _remote_flag(title, city),
                ))
                if len(out) >= MAX_ROWS:
                    return out
        except Exception as e:
            logger.debug(f"[posao.hr] {term}: {e}")

    if len(out) < 5:
        out.extend(_scrape_freehire_country(
            query,
            "Croatia",
            "moj-posao.net",
            ("croatia", "hrvatska", "zagreb", "split", "rijeka", "osijek", "zadar"),
            "Zagreb",
        ))
    return out[:MAX_ROWS]


def scrape_eleman_tr(query: str) -> List[dict]:
    """Turkey local tech jobs: direct Eleman.net IT category scraper + Turkey ATS."""
    out: List[dict] = []
    q = (query or "").strip()
    first = q.split()[0].lower() if q.split() else q.lower()
    seen = set()
    # 1. FreeHire Turkey ATS (Istanbul / Ankara / Izmir software & mobile engineering roles)
    out.extend(_scrape_freehire_country(
        query,
        "Turkey",
        "kariyer.net",
        ("turkey", "türkiye", "turkiye", "istanbul", "ankara", "izmir", "bursa", "antalya", "kocaeli"),
        "Istanbul",
    ))
    for r in out:
        seen.add(r["job_url"])

    # 2. Direct Eleman.net Bilişim (IT) listings
    if len(out) < MAX_ROWS:
        try:
            r = _get("https://www.eleman.net/is-ilanlari/bilisim")
            if r:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select("a[href*='/is-ilani/']"):
                    href = (a.get("href") or "").split("?")[0].strip()
                    if not re.search(r"/is-ilani/[a-z0-9-]+-i\d+$", href):
                        continue
                    job_url = href if href.startswith("http") else f"https://www.eleman.net{href}"
                    if job_url in seen:
                        continue
                    lines = [ln.strip() for ln in a.get_text("\n", strip=True).splitlines() if ln.strip()]
                    if not lines:
                        continue
                    title = lines[0]
                    company = lines[1] if len(lines) > 1 else "Employer via Eleman.net"
                    city = lines[2] if len(lines) > 2 else "Istanbul"
                    low_blob = f"{title} {company} {href}".lower()
                    if first not in ("software", "developer") and first not in low_blob and not any(
                        w in low_blob for w in ("yazilim", "yazılım", "developer", "mobil", "uzman", "mühendis", "muhendis", "bilgi işlem", "bilisim")
                    ):
                        continue
                    seen.add(job_url)
                    desc = f"{title} at {company} ({city}, Turkey)"
                    out.append(_row(
                        "eleman.net", title, company,
                        _with_country(city, "Turkey", ("türkiye", "istanbul", "ankara", "izmir")),
                        job_url, desc, "", _remote_flag(title, city),
                    ))
                    if len(out) >= MAX_ROWS:
                        break
        except Exception as e:
            logger.debug(f"[eleman.net] {e}")
    return out[:MAX_ROWS]


# ─────────────────────────────────────────────────────────────────────────────
# Bulgaria — Dev.bg
# ─────────────────────────────────────────────────────────────────────────────

def scrape_dev_bg(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://dev.bg/", params={"s": query, "post_type": "job_listing"})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for item in soup.select(".job-list-item"):
            a = item.select_one("a.ab-trigger[href*='/company/jobads/']") or item.select_one("a[href*='/company/jobads/']")
            if not a or not a.get("href"):
                continue
            job_url = a["href"].split("?")[0].strip()
            if job_url in seen:
                continue
            seen.add(job_url)
            h6 = item.select_one("h6.job-title, h6")
            title = h6.get_text(" ", strip=True) if h6 else a.get_text(" ", strip=True)
            comp_el = item.select_one(".company-name, span.hide-for-small-only")
            company = comp_el.get_text(" ", strip=True) if comp_el else ""
            badge_el = item.select_one(".badge")
            loc_raw = badge_el.get_text(" ", strip=True) if badge_el else "Sofia"
            if "remote" in loc_raw.lower() or "fully remote" in loc_raw.lower():
                loc = "Sofia, Bulgaria (Remote)"
            elif "sofia" in loc_raw.lower() or "plovdiv" in loc_raw.lower() or "varna" in loc_raw.lower():
                loc = f"{loc_raw.split()[0]}, Bulgaria"
            else:
                loc = "Sofia, Bulgaria"
            date_el = item.select_one(".date")
            tags = " ".join(img.get("title") or img.get("alt") or "" for img in item.select("img[title], img[alt]"))
            desc = f"{title} at {company}. Tech stack: {tags}".strip()
            if not _matches(query, title, desc, job_url):
                continue
            out.append(_row(
                "dev.bg", title, company, loc, job_url, desc,
                _relative_date(date_el.get_text(" ", strip=True)) if date_el else "",
                _remote_flag(loc_raw, title),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[dev.bg] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Greece — Skywalker.gr
# ─────────────────────────────────────────────────────────────────────────────

def scrape_skywalker_gr(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://www.skywalker.gr/el/aggelies-ergasias", params={"keywords": query})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for kw_attempt in (query, "developer"):
            if kw_attempt != query:
                r = _get("https://www.skywalker.gr/el/aggelies-ergasias", params={"keywords": kw_attempt})
                if not r:
                    break
                soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/el/aggelia-ergasias/']"):
                href = a.get("href", "").split("?")[0].strip()
                if href.endswith("/apply") or not re.search(r"/el/aggelia-ergasias/[0-9a-z]+/[^/]+$", href):
                    continue
                job_url = f"https://www.skywalker.gr{href}" if href.startswith("/") else href
                if job_url in seen:
                    continue
                slug = href.rstrip("/").rsplit("/", 1)[-1]
                slug_title = slug.replace("-", " ").strip().title()
                raw_txt = a.get_text(" ", strip=True)
                title = slug_title if len(raw_txt) > 90 or not raw_txt else raw_txt
                if not title or len(title) < 3:
                    continue
                if not _matches(kw_attempt, title, raw_txt, slug_title):
                    continue
                seen.add(job_url)
                desc = f"{raw_txt} ({slug_title})"
                out.append(_row(
                    "skywalker.gr", title, "Employer via Skywalker.gr",
                    "Athens, Greece", job_url, desc, "", _remote_flag(title, raw_txt),
                ))
                if len(out) >= MAX_ROWS:
                    break
            if out:
                break
    except Exception as e:
        logger.debug(f"[skywalker.gr] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Ukraine — Djinni.co
# ─────────────────────────────────────────────────────────────────────────────

def scrape_djinni_ua(query: str) -> List[dict]:
    out: List[dict] = []
    try:
        r = _get("https://djinni.co/jobs/", params={"primary_keyword": query})
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select("a.job-item__title-link[href*='/jobs/'], a[href*='/jobs/']"):
            href = a.get("href", "").split("?")[0].strip()
            if not re.match(r"^/jobs/\d+-", href):
                continue
            job_url = f"https://djinni.co{href}"
            if job_url in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 3:
                continue
            seen.add(job_url)
            li = a.find_parent("li") or a.find_parent("div")
            comp_a = li.select_one("a[href*='/jobs/company-']") if li else None
            company = comp_a.get_text(" ", strip=True) if comp_a else "Employer via Djinni"
            loc_txt = li.get_text(" ", strip=True) if li else ""
            if not _matches(query, title, loc_txt):
                continue
            out.append(_row(
                "djinni.co", title, company, "Kyiv, Ukraine", job_url, loc_txt, "",
                _remote_flag(title, loc_txt),
            ))
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[djinni.co] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Additional Country-Scoped Talent.com Local Board Scrapers across Europe
# ─────────────────────────────────────────────────────────────────────────────

def scrape_talent_uk(query: str) -> List[dict]:
    return _scrape_talent_eu("uk", "United Kingdom", "totaljobs.uk", "London", query)


def scrape_talent_fr(query: str) -> List[dict]:
    return _scrape_talent_eu("fr", "France", "apec.fr", "Paris", query)


def scrape_talent_de(query: str) -> List[dict]:
    return _scrape_talent_eu("de", "Germany", "stepstone.de", "Berlin", query)


def scrape_talent_at(query: str) -> List[dict]:
    return _scrape_talent_eu("at", "Austria", "stepstone.at", "Vienna", query)


def scrape_talent_nl(query: str) -> List[dict]:
    return _scrape_talent_eu("nl", "Netherlands", "nationalevacaturebank.nl", "Amsterdam", query)


def scrape_talent_ch(query: str) -> List[dict]:
    return _scrape_talent_eu("ch", "Switzerland", "jobup.ch", "Zurich", query)


def scrape_talent_es(query: str) -> List[dict]:
    return _scrape_talent_eu("es", "Spain", "infojobs.net", "Madrid", query)


def scrape_talent_pt(query: str) -> List[dict]:
    return _scrape_talent_eu("pt", "Portugal", "net-empregos.com", "Lisbon", query)


def scrape_talent_dk(query: str) -> List[dict]:
    return _scrape_talent_eu("dk", "Denmark", "jobnet.dk", "Copenhagen", query)


def scrape_talent_se(query: str) -> List[dict]:
    return _scrape_talent_eu("se", "Sweden", "platsbanken.se", "Stockholm", query)


def scrape_talent_no(query: str) -> List[dict]:
    return _scrape_talent_eu("no", "Norway", "finn.no", "Oslo", query)


def scrape_talent_pl(query: str) -> List[dict]:
    return _scrape_talent_eu("pl", "Poland", "pracuj.pl", "Warsaw", query)


def scrape_talent_cz(query: str) -> List[dict]:
    return _scrape_talent_eu("cz", "Czech Republic", "jobs.cz", "Prague", query)


def scrape_talent_hu(query: str) -> List[dict]:
    return _scrape_talent_eu("hu", "Hungary", "profession.hu", "Budapest", query)


def scrape_talent_bg(query: str) -> List[dict]:
    return _scrape_talent_eu("bg", "Bulgaria", "jobs.bg", "Sofia", query)


def scrape_talent_gr(query: str) -> List[dict]:
    return _scrape_talent_eu("gr", "Greece", "kariera.gr", "Athens", query)


def scrape_talent_ua(query: str) -> List[dict]:
    return _scrape_talent_eu("ua", "Ukraine", "work.ua", "Kyiv", query)


def scrape_talent_tr(query: str) -> List[dict]:
    return _scrape_talent_eu("tr", "Turkey", "kariyer.net", "Istanbul", query)


def scrape_talent_ie(query: str) -> List[dict]:
    return _scrape_talent_eu("ie", "Ireland", "ie.talent.com", "Dublin", query)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

DIRECT_SCRAPERS: Dict[str, List[Callable[[str], List[dict]]]] = {
    "uk": [scrape_reed, scrape_talent_uk],
    "austria": [scrape_karriere_at, scrape_talent_at],
    "portugal": [scrape_itjobs_pt, scrape_talent_pt],
    "spain": [scrape_tecnoempleo, scrape_infojobs, scrape_talent_es],
    "denmark": [scrape_jobindex, scrape_talent_dk],
    "norway": [scrape_finn, scrape_arbeidsplassen, scrape_talent_no],
    "sweden": [scrape_jobtech_se, scrape_talent_se],
    "poland": [scrape_nofluffjobs, scrape_talent_pl],
    "hungary": [scrape_nofluffjobs_hu, scrape_talent_hu],
    "czech republic": [scrape_talent_cz, scrape_startupjobs_cz, scrape_nofluffjobs_cz],
    "bulgaria": [scrape_dev_bg, scrape_talent_bg],
    "greece": [scrape_skywalker_gr, scrape_talent_gr],
    "ukraine": [scrape_djinni_ua, scrape_talent_ua],
    "netherlands": [scrape_jobbird, scrape_talent_nl, scrape_arbeitnow_nl],
    "switzerland": [scrape_jobs_ch, scrape_talent_ch, scrape_arbeitnow_ch],
    "france": [scrape_hellowork, scrape_talent_fr],
    "germany": [scrape_xing_de, scrape_talent_de, scrape_arbeitnow_de],
    "finland": [scrape_duunitori_fi],
    "belgium": [scrape_stepstone_be],
    "ireland": [scrape_irishjobs_ie, scrape_talent_ie],
    "italy": [scrape_italyjobs_it],
    "croatia": [scrape_posao_hr],
    "turkey": [scrape_eleman_tr, scrape_talent_tr],
}

__all__ = ["DIRECT_SCRAPERS"] + [f.__name__ for fs in DIRECT_SCRAPERS.values() for f in fs]
