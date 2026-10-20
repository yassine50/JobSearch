"""
Open job sources — zero-auth public feeds and ATS APIs.

Ported from the provider layer of career-ops (github.com/santifer/career-ops):
instead of scraping protected boards, these sources expose structured public
JSON/RSS, so they never get blocked and always return clean, live data.

Sources
-------
remote_boards : Remotive, RemoteOK, Jobicy, Himalayas, We Work Remotely,
                Working Nomads, Arbeitnow
ats           : Company career pages hosted on Greenhouse / Lever / Ashby.
                1) Serper `site:` discovery across the ATS hosts (any company)
                2) Direct board APIs for a curated list of tech companies
                Every hit is re-read from the ATS API, so closed postings are dropped.
hackernews    : The latest "Ask HN: Who is hiring?" thread.

Every function returns rows shaped like JobSpy DataFrame rows
(title, company, location, job_url, job_url_direct, description, site,
date_posted, min_amount, max_amount) so they flow through the existing
search pipeline unchanged.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import requests

logger = logging.getLogger("jobsearcher.open_sources")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/xml, */*"}
TIMEOUT = 6.5
CACHE_TTL_S = 30 * 60

REMOTE_BOARDS = ["remotive", "remoteok", "jobicy", "himalayas", "weworkremotely", "workingnomads", "arbeitnow"]
OPEN_SITE_IDS = {"remote_boards", "ats", "hackernews", "official_apis"}

# ── Shared connection-pooled HTTP session (reuses TLS handshakes across calls) ──
_OPEN_SESSION = requests.Session()
_open_adapter = requests.adapters.HTTPAdapter(pool_connections=24, pool_maxsize=24, max_retries=0)
_OPEN_SESSION.mount("https://", _open_adapter)
_OPEN_SESSION.mount("http://", _open_adapter)

# Shared bounded worker pool for fast parallel feed & ATS harvesting
_OPEN_POOL = ThreadPoolExecutor(max_workers=20)

# ── Thread-safe TTL caches ──
_cache: Dict[str, tuple] = {}
_parsed_cache: Dict[str, tuple] = {}
_cache_lock = threading.Lock()


def _get(url: str, as_json: bool = True, params: Optional[dict] = None, ttl: int = CACHE_TTL_S, cache_raw: bool = True):
    key = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    now = time.time()
    if cache_raw:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
    r = _OPEN_SESSION.get(url, params=params, headers=HEADERS, timeout=4.5)
    if r.status_code == 404:
        data = None
    else:
        r.raise_for_status()
        data = r.json() if as_json else r.text
    if cache_raw:
        with _cache_lock:
            if len(_cache) >= 60:
                for k in sorted(_cache, key=lambda k: _cache[k][0])[:20]:
                    _cache.pop(k, None)
            _cache[key] = (now, data)
    return data


def _get_parsed(cache_key: str, builder: Callable[[], List[dict]], ttl: int = CACHE_TTL_S) -> List[dict]:
    """Caches already-parsed compact row dicts so multi-MB raw JSON/XML is freed immediately and never re-parsed."""
    now = time.time()
    with _cache_lock:
        hit = _parsed_cache.get(cache_key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    rows = builder() or []
    with _cache_lock:
        if len(_parsed_cache) >= 80:
            for k in sorted(_parsed_cache, key=lambda k: _parsed_cache[k][0])[:20]:
                _parsed_cache.pop(k, None)
        _parsed_cache[cache_key] = (now, rows)
    return rows


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\xa0]+")
_NL_RE = re.compile(r"\n\s*\n+")


# ── helpers ────────────────────────────────────────────────────────────────────
def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    if len(raw) > 8000:
        raw = raw[:8000]
    raw = html.unescape(raw) if "&" in raw else raw
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _NL_RE.sub("\n\n", _WS_RE.sub(" ", text)).strip()[:2400]


def _iso_date(value) -> str:
    """Normalise epoch seconds/ms or date strings to ISO-8601 (preserving time when available)."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            v = float(value)
            v = v / 1000 if v > 1e12 else v
            return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        s = str(value).strip()
        if re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", s):
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m and not re.search(r"\d{2}:\d{2}:\d{2}", s):
            return m.group(0)
        from email.utils import parsedate_to_datetime
        dt_rfc = parsedate_to_datetime(s)
        if dt_rfc.tzinfo is not None:
            dt_rfc = dt_rfc.astimezone(timezone.utc)
        return dt_rfc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
        return m.group(0) if m else ""


def _row(site: str, title: str, company: str, location: str, url: str, description: str = "",
         date_posted: str = "", apply_url: str = "", min_amount=None, max_amount=None,
         is_remote: bool = False) -> dict:
    return {
        "site": site,
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or ("Remote" if is_remote else "")).strip(),
        "job_url": url,
        "job_url_direct": apply_url or url,
        "description": description or "",
        "date_posted": date_posted,
        "min_amount": min_amount if min_amount else "",
        "max_amount": max_amount if max_amount else "",
        "is_remote": is_remote,
    }


def _pretty_slug(slug: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_.]+", slug or "") if w)


# ── Remote boards ──────────────────────────────────────────────────────────────
def _remotive(query: str) -> List[dict]:
    data = _get("https://remotive.com/api/remote-jobs", params={"search": query, "limit": 100}) or {}
    out = []
    for j in data.get("jobs", []):
        out.append(_row("remotive", j.get("title"), j.get("company_name"),
                        j.get("candidate_required_location") or "Remote", j.get("url"),
                        html_to_text(j.get("description", "")), _iso_date(j.get("publication_date")),
                        is_remote=True))
        if j.get("salary"):
            out[-1]["salary_text"] = j["salary"]
    return out


def _remoteok(query: str) -> List[dict]:
    def _build():
        data = _get("https://remoteok.com/api", cache_raw=False) or []
        out = []
        for j in data:
            if not isinstance(j, dict) or not j.get("position"):
                continue
            out.append(_row("remoteok", j.get("position"), j.get("company"), j.get("location") or "Remote",
                            j.get("url"), html_to_text(j.get("description", "")), _iso_date(j.get("date")),
                            apply_url=j.get("apply_url") or j.get("url"),
                            min_amount=j.get("salary_min") or None, max_amount=j.get("salary_max") or None,
                            is_remote=True))
        return out
    return _get_parsed("feed:remoteok", _build)


def _jobicy(query: str) -> List[dict]:
    tag = re.sub(r"\s+", " ", query.lower()).strip()
    data = _get("https://jobicy.com/api/v2/remote-jobs", params={"count": 80, "tag": tag}) or {}
    jobs = data.get("jobs") or []
    if not jobs:
        return _get_parsed("feed:jobicy_all", lambda: [
            _row("jobicy", j.get("jobTitle"), j.get("companyName"), j.get("jobGeo") or "Remote", j.get("url"),
                 html_to_text(j.get("jobDescription") or j.get("jobExcerpt") or ""), _iso_date(j.get("pubDate")),
                 min_amount=j.get("annualSalaryMin") or None, max_amount=j.get("annualSalaryMax") or None,
                 is_remote=True)
            for j in ((_get("https://jobicy.com/api/v2/remote-jobs", params={"count": 80}, cache_raw=False) or {}).get("jobs") or [])
        ])
    return [
        _row("jobicy", j.get("jobTitle"), j.get("companyName"), j.get("jobGeo") or "Remote", j.get("url"),
             html_to_text(j.get("jobDescription") or j.get("jobExcerpt") or ""), _iso_date(j.get("pubDate")),
             min_amount=j.get("annualSalaryMin") or None, max_amount=j.get("annualSalaryMax") or None,
             is_remote=True)
        for j in jobs
    ]


def _himalayas(query: str) -> List[dict]:
    jobs = []
    try:
        data = _get("https://himalayas.app/jobs/api/search", params={"q": query}) or {}
        jobs = data.get("jobs") or []
    except Exception:
        jobs = []
    if not jobs:
        return _get_parsed("feed:himalayas_all", lambda: [
            _row("himalayas", j.get("title"), j.get("companyName"),
                 ", ".join(l for l in (j.get("locationRestrictions") or []) if isinstance(l, str)) or "Remote (Worldwide)",
                 j.get("applicationLink") or j.get("guid"),
                 html_to_text(j.get("description") or j.get("excerpt") or ""), _iso_date(j.get("pubDate")),
                 min_amount=j.get("minSalary") or None, max_amount=j.get("maxSalary") or None,
                 is_remote=True)
            for j in ((_get("https://himalayas.app/jobs/api", params={"limit": 50}, cache_raw=False) or {}).get("jobs") or [])
        ])
    out = []
    for j in jobs:
        locs = j.get("locationRestrictions") or []
        loc = ", ".join(l for l in locs if isinstance(l, str)) or "Remote (Worldwide)"
        out.append(_row("himalayas", j.get("title"), j.get("companyName"), loc,
                        j.get("applicationLink") or j.get("guid"),
                        html_to_text(j.get("description") or j.get("excerpt") or ""), _iso_date(j.get("pubDate")),
                        min_amount=j.get("minSalary") or None, max_amount=j.get("maxSalary") or None,
                        is_remote=True))
    return out


def _weworkremotely(query: str) -> List[dict]:
    def _build():
        xml_text = _get("https://weworkremotely.com/remote-jobs.rss", as_json=False, cache_raw=False) or ""
        out = []
        try:
            root = ET.fromstring(xml_text.encode("utf-8"))
        except Exception:
            return out
        for item in root.iter("item"):
            raw_title = (item.findtext("title") or "").strip()
            company, _, role = raw_title.partition(":")
            if not role:
                company, role = "", raw_title
            out.append(_row("weworkremotely", role.strip(), company.strip(),
                            (item.findtext("region") or "Remote").strip(), (item.findtext("link") or "").strip(),
                            html_to_text(item.findtext("description") or ""), _iso_date(item.findtext("pubDate")),
                            is_remote=True))
        return out
    return _get_parsed("feed:weworkremotely", _build)


def _workingnomads(query: str) -> List[dict]:
    def _build():
        data = (_get("https://www.workingnomads.com/api/exposed_jobs/", cache_raw=False) or [])[:160]
        return [
            _row("workingnomads", j.get("title"), j.get("company_name"), j.get("location") or "Remote", j.get("url"),
                 html_to_text(j.get("description", "")), _iso_date(j.get("pub_date")), is_remote=True)
            for j in data if isinstance(j, dict)
        ]
    return _get_parsed("feed:workingnomads", _build)


def _arbeitnow(query: str) -> List[dict]:
    def _build():
        out = []
        data = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": 1}, cache_raw=False) or {}
        for j in data.get("data", []):
            remote = bool(j.get("remote"))
            loc = ", ".join(x for x in [j.get("location") or "", "Remote" if remote else ""] if x)
            out.append(_row("arbeitnow", j.get("title"), j.get("company_name"), loc, j.get("url"),
                            html_to_text(j.get("description", "")), _iso_date(j.get("created_at")),
                            is_remote=remote))
        return out
    return _get_parsed("feed:arbeitnow", _build)


REMOTE_FETCHERS: Dict[str, Callable[[str], List[dict]]] = {
    "remotive": _remotive, "remoteok": _remoteok, "jobicy": _jobicy, "himalayas": _himalayas,
    "weworkremotely": _weworkremotely, "workingnomads": _workingnomads, "arbeitnow": _arbeitnow,
}


# ── Hacker News "Who is hiring?" ───────────────────────────────────────────────
def _hackernews(query: str) -> List[dict]:
    def _build():
        search = _get("https://hn.algolia.com/api/v1/search_by_date",
                      params={"tags": "story,author_whoishiring", "hitsPerPage": 5}, cache_raw=False) or {}
        story = next((h for h in search.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()), None)
        if not story:
            return []
        thread = _get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}", cache_raw=False) or {}
        thread_url = f"https://news.ycombinator.com/item?id={story['objectID']}"
        out = []
        for c in thread.get("children", []) or []:
            text = html_to_text(c.get("text") or "")
            if len(text) < 80:
                continue
            first = text.split("\n", 1)[0]
            parts = [p.strip() for p in first.split("|") if p.strip()]
            company = parts[0] if parts else ""
            role = parts[1] if len(parts) > 1 else first[:120]
            location = parts[2] if len(parts) > 2 else ""
            m = re.search(r"https?://[^\s<>\"')]+", text)
            comment_url = f"https://news.ycombinator.com/item?id={c.get('id')}"
            out.append(_row("hackernews", role, company[:80], location, comment_url, text,
                            _iso_date(c.get("created_at_i") or c.get("created_at")),
                            apply_url=m.group(0) if m else thread_url,
                            is_remote="remote" in first.lower()))
        return out
    return _get_parsed("feed:hackernews", _build)


# ── ATS (Greenhouse / Lever / Ashby) ───────────────────────────────────────────
_ATS_FILE = os.path.join(os.path.dirname(__file__), "ats_companies.json")
_EXTRA_ATS = [
    ("greenhouse", "stripe"), ("greenhouse", "airbnb"), ("greenhouse", "discord"),
    ("greenhouse", "figma"), ("greenhouse", "gitlab"), ("greenhouse", "cloudflare"),
    ("greenhouse", "datadog"), ("greenhouse", "coinbase"), ("lever", "spotify"),
    ("ashby", "openai"), ("ashby", "notion"), ("ashby", "linear"),
]


def load_ats_companies() -> List[dict]:
    try:
        with open(_ATS_FILE, encoding="utf-8") as f:
            companies = json.load(f)
    except Exception:
        companies = []
    priority = [{"name": _pretty_slug(slug), "vendor": vendor, "slug": slug} for vendor, slug in _EXTRA_ATS]
    seen = {(c["vendor"], c["slug"].lower()) for c in priority}
    for c in companies:
        key = (c["vendor"], c["slug"].lower())
        if key not in seen:
            seen.add(key)
            priority.append(c)
    return priority


def _greenhouse_board(slug: str, company: str = "") -> List[dict]:
    def _build():
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", cache_raw=False) or {}
        return [_greenhouse_row(j, slug, company) for j in (data.get("jobs") or [])[:250]]
    return _get_parsed(f"ats:gh:{slug}", _build)


def _greenhouse_row(j: dict, slug: str, company: str = "") -> dict:
    row = _row("greenhouse", j.get("title"), j.get("company_name") or company or _pretty_slug(slug),
               (j.get("location") or {}).get("name", ""), j.get("absolute_url"),
               html_to_text(j.get("content", "")) if j.get("content") else "",
               _iso_date(j.get("first_published") or j.get("updated_at")))
    row["_gh_slug"] = slug
    row["_gh_id"] = j.get("id")
    return row


def _lever_board(slug: str, company: str = "") -> List[dict]:
    def _build():
        data = _get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json", "limit": 150}, cache_raw=False) or []
        return [_lever_row(j, slug, company) for j in data[:150] if isinstance(j, dict)]
    return _get_parsed(f"ats:lever:{slug}", _build)


def _lever_row(j: dict, slug: str, company: str = "") -> dict:
    sr = j.get("salaryRange") or {}
    desc = j.get("descriptionPlain") or html_to_text(j.get("description", ""))
    return _row("lever", j.get("text"), company or _pretty_slug(slug),
                (j.get("categories") or {}).get("location", ""), j.get("hostedUrl"), desc[:2400],
                _iso_date(j.get("createdAt")), apply_url=j.get("applyUrl"),
                min_amount=sr.get("min"), max_amount=sr.get("max"),
                is_remote=(j.get("workplaceType") == "remote"))


def _ashby_board(slug: str, company: str = "") -> List[dict]:
    def _build():
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                    params={"includeCompensation": "true"}, cache_raw=False) or {}
        return [_ashby_row(j, slug, company) for j in data.get("jobs", []) if j.get("isListed", True)]
    return _get_parsed(f"ats:ashby:{slug}", _build)


def _ashby_row(j: dict, slug: str, company: str = "") -> dict:
    loc = j.get("location") or ""
    if j.get("isRemote") and "remote" not in loc.lower():
        loc = f"{loc}, Remote".strip(", ")
    row = _row("ashby", j.get("title"), company or _pretty_slug(slug), loc, j.get("jobUrl"),
               (j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")))[:2400],
               _iso_date(j.get("publishedAt")), apply_url=j.get("applyUrl"), is_remote=bool(j.get("isRemote")))
    comp = (j.get("compensation") or {}).get("compensationTierSummary")
    if comp:
        row["salary_text"] = comp
    return row


BOARD_FETCHERS = {"greenhouse": _greenhouse_board, "lever": _lever_board, "ashby": _ashby_board}

ATS_URL_PATTERNS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([a-z0-9_-]+)/jobs/(\d+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/.*[?&]for=([a-z0-9_-]+).*[?&]token=(\d+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)/([0-9a-f-]{36})", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)/([0-9a-f-]{36})", re.I)),
]


def parse_ats_url(url: str) -> Optional[tuple]:
    for vendor, rx in ATS_URL_PATTERNS:
        m = rx.search(url or "")
        if m:
            return vendor, m.group(1), m.group(2)
    return None


def fetch_ats_posting(url: str) -> Optional[dict]:
    """Re-read a single posting from its ATS API. Returns None when the posting is closed/unknown."""
    parsed = parse_ats_url(url)
    if not parsed:
        return None
    vendor, slug, job_id = parsed
    try:
        if vendor == "greenhouse":
            j = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}")
            return _greenhouse_row(j, slug) if j and j.get("title") else None
        if vendor == "lever":
            j = _get(f"https://api.lever.co/v0/postings/{slug}/{job_id}")
            return _lever_row(j, slug) if j and j.get("text") else None
        if vendor == "ashby":
            for row in _ashby_board(slug):
                if job_id in (row["job_url"] or ""):
                    return row
    except Exception as e:
        logger.debug(f"[ATS] {vendor}/{slug}/{job_id}: {e}")
    return None


SERPER_ATS_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")


def _serper_ats_discovery(query: str, location: str, api_key: str, hours_old: Optional[int]) -> List[dict]:
    """Google (via Serper) every Greenhouse/Lever/Ashby posting for the role, then verify each via its API."""
    loc = "" if (location or "").lower() in ("", "worldwide", "global", "all") else f" {location}"
    if hours_old:
        tbs = "qdr:d" if hours_old <= 24 else ("qdr:w" if hours_old <= 168 else "qdr:m")
    else:
        tbs = "qdr:m"

    def one_host(host: str) -> List[str]:
        payload = {"q": f'site:{host} "{query}"{loc}', "num": 10, "tbs": tbs}
        r = _OPEN_SESSION.post("https://google.serper.dev/search", json=payload,
                               headers={"X-API-KEY": api_key, "Content-Type": "application/json"}, timeout=3.8)
        if r.status_code != 200:
            return []
        return [i.get("link", "") for i in r.json().get("organic", [])]

    urls: List[str] = []
    futs_h = [_OPEN_POOL.submit(one_host, h) for h in SERPER_ATS_HOSTS]
    wait(futs_h, timeout=4.0)
    for fh in futs_h:
        if fh.done() and not fh.exception():
            for link in fh.result():
                if parse_ats_url(link) and link not in urls:
                    urls.append(link)

    if not urls:
        return []
    futs = [_OPEN_POOL.submit(fetch_ats_posting, u) for u in urls[:16]]
    wait(futs, timeout=4.0)
    rows = [f.result() for f in futs if f.done() and not f.exception() and f.result()]
    return rows


def _yahoo_ats_discovery(query: str, location: str, relevant: Callable[[dict], bool]) -> List[dict]:
    """Free web-wide ATS discovery via Yahoo Search across Greenhouse, Lever, and Ashby."""
    loc = "" if (location or "").lower() in ("", "worldwide", "global", "all") else f" {location}"

    def one_host(host: str) -> List[str]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                res = list(ddgs.text(f"site:{host} {query}{loc}", max_results=10, backend="yahoo"))
            return [r.get("href", "") for r in res if r.get("href")]
        except Exception:
            return []

    urls: List[str] = []
    futs_h = [_OPEN_POOL.submit(one_host, h) for h in SERPER_ATS_HOSTS]
    wait(futs_h, timeout=2.4)
    for fh in futs_h:
        if fh.done() and not fh.exception():
            for link in fh.result():
                if parse_ats_url(link) and link not in urls:
                    urls.append(link)

    if not urls:
        return []
    futs = [_OPEN_POOL.submit(fetch_ats_posting, u) for u in urls[:14]]
    wait(futs, timeout=2.4)
    rows = [f.result() for f in futs if f.done() and not f.exception() and f.result()]
    for r in rows:
        r.pop("_gh_slug", None)
        r.pop("_gh_id", None)
    return rows


def _ats_direct(query: str, relevant: Callable[[dict], bool]) -> List[dict]:
    companies = load_ats_companies()[:30]

    def one(c):
        try:
            rows = BOARD_FETCHERS[c["vendor"]](c["slug"], c.get("name", ""))
            return [dict(r) for r in rows if relevant(r)]
        except Exception as e:
            logger.debug(f"[ATS] board {c['vendor']}/{c['slug']}: {e}")
            return []

    out: List[dict] = []
    futs = [_OPEN_POOL.submit(one, c) for c in companies]
    wait(futs, timeout=3.5)
    for f in futs:
        if f.done() and not f.exception():
            out.extend(f.result())

    # Enrich descriptions for matched Greenhouse rows (up to 10) in parallel
    gh_missing = [r for r in out if not r.get("description") and r.get("_gh_slug") and r.get("_gh_id")][:10]
    if gh_missing:
        def _fill_gh(r):
            try:
                j = _get(f"https://boards-api.greenhouse.io/v1/boards/{r['_gh_slug']}/jobs/{r['_gh_id']}")
                if j and j.get("content"):
                    r["description"] = html_to_text(j["content"])
            except Exception:
                pass
        gh_futs = [_OPEN_POOL.submit(_fill_gh, r) for r in gh_missing]
        wait(gh_futs, timeout=1.8)

    for r in out:
        r.pop("_gh_slug", None)
        r.pop("_gh_id", None)
    return out


_FREEHIRE_ISO2: Dict[str, str] = {
    "usa": "US", "us": "US", "united states": "US",
    "uk": "GB", "gb": "GB", "united kingdom": "GB",
    "canada": "CA", "ca": "CA",
    "germany": "DE", "de": "DE",
    "france": "FR", "fr": "FR",
    "netherlands": "NL", "nl": "NL",
    "morocco": "MA", "ma": "MA",
    "singapore": "SG", "sg": "SG",
    "uae": "AE", "united arab emirates": "AE", "dubai": "AE",
    "saudi arabia": "SA", "sa": "SA",
    "india": "IN", "in": "IN",
    "australia": "AU", "au": "AU",
    "switzerland": "CH", "ch": "CH",
    "spain": "ES", "es": "ES",
    "italy": "IT", "it": "IT",
    "sweden": "SE", "se": "SE",
    "denmark": "DK", "dk": "DK",
    "norway": "NO", "no": "NO",
    "finland": "FI", "fi": "FI",
    "ireland": "IE", "ie": "IE",
    "poland": "PL", "pl": "PL",
    "portugal": "PT", "pt": "PT",
    "belgium": "BE", "be": "BE",
    "austria": "AT", "at": "AT",
}


def _freehire_ats(query: str, country: str = "", location: str = "",
                  hours_old: Optional[int] = None,
                  relevant: Optional[Callable[[dict], bool]] = None) -> List[dict]:
    """
    FreeHire public 14-ATS aggregation API (https://freehire.me/api/v1/agent/jobs/search).
    Searches directly across Greenhouse, Lever, Ashby, Workday, SmartRecruiters, BambooHR,
    Workable, Recruitee, Personio, Pinpoint, Rippling, Teamtailor, BreezyHR, and Jobvite
    with full descriptions, structured skills, work_mode, and salary enrichment.
    """
    import math
    base_url = "https://freehire.me/api/v1/agent/jobs/search"
    params: Dict[str, str] = {
        "q": query,
        "limit": "40",
        "offset": "0",
        "description_format": "text",
    }
    if hours_old and hours_old > 0:
        params["posted_within_days"] = str(max(1, int(math.ceil(hours_old / 24.0))))

    c_norm = (country or "").strip().lower()
    iso2 = _FREEHIRE_ISO2.get(c_norm)
    if iso2:
        params["country"] = iso2
    if location and location.strip().lower() not in ("", "worldwide", "global", "all", c_norm):
        params["location"] = location.strip()

    def _call_freehire(p: Dict[str, str]) -> List[dict]:
        for attempt in range(2):
            try:
                r = _OPEN_SESSION.get(
                    base_url,
                    params=p,
                    headers={"User-Agent": "freehire-search-cli/0.1.0", "Accept": "application/json"},
                    timeout=5.0,
                )
                if r.status_code == 429 and attempt == 0:
                    retry_after = min(float(r.headers.get("retry-after", "1.5") or 1.5), 2.5)
                    time.sleep(retry_after)
                    continue
                if r.status_code != 200:
                    return []
                payload = r.json()
                return payload.get("data") or []
            except Exception as exc:
                logger.debug(f"[FreeHire] request failed: {exc}")
                return []
        return []

    items = _call_freehire(params)
    # If strict country/location filter yielded very few hits, broaden to global ATS and let _location_ok filter
    if len(items) < 4 and ("country" in params or "location" in params):
        broad = {k: v for k, v in params.items() if k not in ("country", "location")}
        more = _call_freehire(broad)
        seen_slugs = {it.get("public_slug") or it.get("url") for it in items}
        for it in more:
            k = it.get("public_slug") or it.get("url")
            if k not in seen_slugs:
                items.append(it)
                seen_slugs.add(k)

    out: List[dict] = []
    for item in items:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not title or not url:
            continue
        enrichment = item.get("enrichment") or {}
        sal_min = enrichment.get("salary_min")
        sal_max = enrichment.get("salary_max")
        sal_cur = enrichment.get("salary_currency") or "$"
        sal_per = enrichment.get("salary_period") or ""
        sal_txt = ""
        if sal_min or sal_max:
            lo = f"{sal_cur} {int(sal_min):,}" if sal_min else ""
            hi = f"{sal_cur} {int(sal_max):,}" if sal_max and sal_max != sal_min else ""
            sal_txt = f"{lo}{' - ' + hi if hi else ''}{(' / ' + sal_per) if sal_per else ''}".strip()

        work_mode = (item.get("work_mode") or "").lower()
        loc_str = (item.get("location") or "").strip() or ("Remote" if work_mode == "remote" else "Worldwide")
        vendor = (item.get("source") or "ats").lower()
        desc = html_to_text(item.get("description") or "")
        skills = item.get("skills") or []
        if skills and isinstance(skills, list):
            skills_line = ", ".join(str(s) for s in skills[:18] if s)
            if skills_line and skills_line.lower() not in desc.lower():
                desc = f"{desc}\n\nKey Technologies: {skills_line}".strip()

        row = _row(
            site=f"ats_{vendor}" if not vendor.startswith("ats") else vendor,
            title=title,
            company=(item.get("company") or "").strip(),
            location=loc_str,
            url=url,
            description=desc,
            date_posted=_iso_date(item.get("posted_at")),
            is_remote=(work_mode == "remote" or "remote" in loc_str.lower()),
            min_amount=sal_min,
            max_amount=sal_max,
        )
        if sal_txt:
            row["salary_text"] = sal_txt
        if enrichment.get("category"):
            row["company_industry"] = enrichment["category"]
        if relevant is None or relevant(row):
            out.append(row)
    return out


# ── public entry point ─────────────────────────────────────────────────────────
_ANYWHERE = ("anywhere", "worldwide", "global", "remote", "")


def _location_ok(row: dict, country: str) -> bool:
    """Keep jobs the candidate can take from the selected country (remote-friendly rows always pass)."""
    c = (country or "").strip().lower()
    if c in ("", "worldwide", "global", "all"):
        return True
    loc = (row.get("location") or "").lower()
    if not loc or any(loc.strip() == a for a in _ANYWHERE) or "worldwide" in loc or "anywhere" in loc:
        return True
    aliases = {c}
    if c in ("usa", "us", "united states"):
        aliases |= {"usa", "united states", "us", "u.s.", "america"}
    if c in ("uk", "united kingdom", "gb"):
        aliases |= {"uk", "united kingdom", "england", "london", "britain"}
    if c in ("uae", "united arab emirates"):
        aliases |= {"uae", "united arab emirates", "dubai", "abu dhabi"}
    return any(re.search(rf"\b{re.escape(a)}\b", loc) for a in aliases) or (
        row.get("is_remote") and any(k in loc for k in ("emea", "europe", "africa", "international")))


def make_strict_matcher(queries: List[str]) -> Callable[[dict], bool]:
    """
    Feeds return *every* job on the board, so relevance must be strict:
    the distinctive words of the query (e.g. "flutter" in "flutter developer") must be in the
    title, or the title must carry the role noun AND the description must mention every
    distinctive word. Synonym-aware via search_engine's equivalence classes.
    """
    from .search_engine import tokenize, core_tokens, _equiv

    specs = []
    for q in queries:
        raw = core_tokens(q)
        if not raw:
            continue
        core = [_equiv(t) for t in raw]
        role = core[-1] if len(core) > 1 else None
        distinct = core[:-1] if len(core) > 1 else core
        distinct_raw = raw[:-1] if len(raw) > 1 else raw
        specs.append((q.lower().strip(), role, distinct, distinct_raw))

    def ok(row: dict) -> bool:
        title = row.get("title") or ""
        if not title or not row.get("job_url"):
            return False
        t_low = title.lower()
        t_toks = tokenize(title)
        t_raw, t_cls = set(t_toks), {_equiv(t) for t in t_toks}
        d_counts = None
        for q_low, role, distinct, distinct_raw in specs:
            if q_low and re.search(r"\b" + re.escape(q_low) + r"\b", t_low):
                return True
            if all(t in t_raw for t in distinct_raw):
                return True
            if all(c in t_cls for c in distinct) and role and role in t_cls:
                return True
            if role and role in t_cls:
                if d_counts is None:
                    d_counts = {}
                    for t in tokenize((row.get("description") or "")[:4000]):
                        d_counts[t] = d_counts.get(t, 0) + 1
                if all(d_counts.get(t, 0) >= 3 for t in distinct_raw):
                    return True
        return False

    return ok


def fetch_open_source(site: str, queries: List[str], *,
                      country: str = "", location: str = "", hours_old: Optional[int] = None,
                      serper_key: str = "") -> List[dict]:
    """
    Fetch one of the open sources ('remote_boards' | 'ats' | 'hackernews') and keep only rows
    strictly relevant to the query (feeds would otherwise flood results with unrelated roles).
    """
    queries = [q for q in (queries if isinstance(queries, list) else [queries]) if q and q.strip()]
    if not queries:
        return []
    query = queries[0]
    relevant = make_strict_matcher(queries)

    rows: List[dict] = []
    if site == "remote_boards":
        futs = {_OPEN_POOL.submit(fn, query): name for name, fn in REMOTE_FETCHERS.items()}
        wait(futs, timeout=4.2)
        for f, name in futs.items():
            if f.done() and not f.exception():
                rows.extend(f.result())
            elif f.done():
                logger.info(f"[OpenSources] {name} failed: {f.exception()}")
    elif site == "hackernews":
        rows = _hackernews(query)
    elif site == "ats":
        ats_futs = [
            _OPEN_POOL.submit(_freehire_ats, query, country, location, hours_old, relevant),
            _OPEN_POOL.submit(_ats_direct, query, relevant),
            _OPEN_POOL.submit(_yahoo_ats_discovery, query, location or country, relevant),
        ]
        if len(queries) > 1:
            ats_futs.append(_OPEN_POOL.submit(_freehire_ats, queries[1], country, location, hours_old, relevant))
        if serper_key:
            ats_futs.append(_OPEN_POOL.submit(_serper_ats_discovery, query, location or country, serper_key, hours_old))
        wait(ats_futs, timeout=5.5)
        for af in ats_futs:
            if af.done() and not af.exception():
                rows.extend(af.result() or [])
    elif site == "official_apis":
        from .official_apis import fetch_official
        rows = fetch_official(query, country=country, location=location, hours_old=hours_old)
    else:
        return []

    out, seen = [], set()
    for r in rows:
        if not relevant(r) or not _location_ok(r, country):
            continue
        key = (r["job_url"] or "").split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        r_copy = dict(r)
        if r_copy.get("salary_text") and not r_copy.get("min_amount"):
            nums = [int(n.replace(",", "")) for n in re.findall(r"\d{2,3}(?:,\d{3})+|\d{5,6}", r_copy["salary_text"])]
            if nums:
                r_copy["min_amount"], r_copy["max_amount"] = min(nums), max(nums)
        out.append(r_copy)
    return out
