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
TIMEOUT = 12
CACHE_TTL_S = 30 * 60

REMOTE_BOARDS = ["remotive", "remoteok", "jobicy", "himalayas", "weworkremotely", "workingnomads", "arbeitnow"]
OPEN_SITE_IDS = {"remote_boards", "ats", "hackernews", "official_apis"}

# ── tiny thread-safe TTL cache (feeds are shared across queries/users) ──────────
_cache: Dict[str, tuple] = {}
_cache_lock = threading.Lock()


def _get(url: str, as_json: bool = True, params: Optional[dict] = None, ttl: int = CACHE_TTL_S):
    key = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code == 404:
        data = None
    else:
        r.raise_for_status()
        data = r.json() if as_json else r.text
    with _cache_lock:
        _cache[key] = (now, data)
    return data


# ── helpers ────────────────────────────────────────────────────────────────────
def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    raw = html.unescape(raw) if "&lt;" in raw else raw
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(raw, "html.parser").get_text("\n")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\xa0]+", " ", text)).strip()


def _iso_date(value) -> str:
    """Normalise epoch seconds/ms or date strings to YYYY-MM-DD ('' if unknown)."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            v = float(value)
            v = v / 1000 if v > 1e12 else v
            return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%d")
        s = str(value).strip()
        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m:
            return m.group(0)
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return ""


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
    data = _get("https://remoteok.com/api") or []
    out = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is the legal notice
        out.append(_row("remoteok", j.get("position"), j.get("company"), j.get("location") or "Remote",
                        j.get("url"), html_to_text(j.get("description", "")), _iso_date(j.get("date")),
                        apply_url=j.get("apply_url") or j.get("url"),
                        min_amount=j.get("salary_min") or None, max_amount=j.get("salary_max") or None,
                        is_remote=True))
    return out


def _jobicy(query: str) -> List[dict]:
    tag = re.sub(r"\s+", " ", query.lower()).strip()
    data = _get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100, "tag": tag}) or {}
    jobs = data.get("jobs") or []
    if not jobs:  # tag search is strict — fall back to the latest feed and filter locally
        jobs = (_get("https://jobicy.com/api/v2/remote-jobs", params={"count": 100}) or {}).get("jobs") or []
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
        jobs = (_get("https://himalayas.app/jobs/api", params={"limit": 50}) or {}).get("jobs") or []
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
    xml_text = _get("https://weworkremotely.com/remote-jobs.rss", as_json=False) or ""
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


def _workingnomads(query: str) -> List[dict]:
    data = _get("https://www.workingnomads.com/api/exposed_jobs/") or []
    return [
        _row("workingnomads", j.get("title"), j.get("company_name"), j.get("location") or "Remote", j.get("url"),
             html_to_text(j.get("description", "")), _iso_date(j.get("pub_date")), is_remote=True)
        for j in data if isinstance(j, dict)
    ]


def _arbeitnow(query: str) -> List[dict]:
    out = []
    for page in (1, 2):
        data = _get("https://www.arbeitnow.com/api/job-board-api", params={"page": page}) or {}
        for j in data.get("data", []):
            remote = bool(j.get("remote"))
            loc = ", ".join(x for x in [j.get("location") or "", "Remote" if remote else ""] if x)
            out.append(_row("arbeitnow", j.get("title"), j.get("company_name"), loc, j.get("url"),
                            html_to_text(j.get("description", "")), _iso_date(j.get("created_at")),
                            is_remote=remote))
        if len(data.get("data", [])) < 100:
            break
    return out


REMOTE_FETCHERS: Dict[str, Callable[[str], List[dict]]] = {
    "remotive": _remotive, "remoteok": _remoteok, "jobicy": _jobicy, "himalayas": _himalayas,
    "weworkremotely": _weworkremotely, "workingnomads": _workingnomads, "arbeitnow": _arbeitnow,
}


# ── Hacker News "Who is hiring?" ───────────────────────────────────────────────
def _hackernews(query: str) -> List[dict]:
    search = _get("https://hn.algolia.com/api/v1/search_by_date",
                  params={"tags": "story,author_whoishiring", "hitsPerPage": 5}) or {}
    story = next((h for h in search.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()), None)
    if not story:
        return []
    thread = _get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}") or {}
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


# ── ATS (Greenhouse / Lever / Ashby) ───────────────────────────────────────────
_ATS_FILE = os.path.join(os.path.dirname(__file__), "ats_companies.json")
_EXTRA_ATS = [  # broad tech employers on top of the career-ops AI list
    ("greenhouse", "stripe"), ("greenhouse", "airbnb"), ("greenhouse", "discord"), ("greenhouse", "robinhood"),
    ("greenhouse", "figma"), ("greenhouse", "gitlab"), ("greenhouse", "reddit"), ("greenhouse", "dropbox"),
    ("greenhouse", "cloudflare"), ("greenhouse", "datadog"), ("greenhouse", "instacart"), ("greenhouse", "lyft"),
    ("greenhouse", "pinterest"), ("greenhouse", "duolingo"), ("greenhouse", "coinbase"), ("greenhouse", "twilio"),
    ("lever", "palantir"), ("lever", "spotify"), ("ashby", "openai"), ("ashby", "notion"), ("ashby", "ramp"),
    ("ashby", "linear"),
]


def load_ats_companies() -> List[dict]:
    try:
        companies = json.load(open(_ATS_FILE, encoding="utf-8"))
    except Exception:
        companies = []
    seen = {(c["vendor"], c["slug"].lower()) for c in companies}
    for vendor, slug in _EXTRA_ATS:
        if (vendor, slug) not in seen:
            companies.append({"name": _pretty_slug(slug), "vendor": vendor, "slug": slug})
    return companies


def _greenhouse_board(slug: str, company: str = "") -> List[dict]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"}) or {}
    return [_greenhouse_row(j, slug, company) for j in data.get("jobs", [])]


def _greenhouse_row(j: dict, slug: str, company: str = "") -> dict:
    return _row("greenhouse", j.get("title"), j.get("company_name") or company or _pretty_slug(slug),
                (j.get("location") or {}).get("name", ""), j.get("absolute_url"),
                html_to_text(j.get("content", "")), _iso_date(j.get("first_published") or j.get("updated_at")))


def _lever_board(slug: str, company: str = "") -> List[dict]:
    data = _get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}) or []
    return [_lever_row(j, slug, company) for j in data if isinstance(j, dict)]


def _lever_row(j: dict, slug: str, company: str = "") -> dict:
    sr = j.get("salaryRange") or {}
    desc = j.get("descriptionPlain") or html_to_text(j.get("description", ""))
    for block in j.get("lists") or []:
        desc += f"\n\n{block.get('text', '')}\n{html_to_text(block.get('content', ''))}"
    return _row("lever", j.get("text"), company or _pretty_slug(slug),
                (j.get("categories") or {}).get("location", ""), j.get("hostedUrl"), desc,
                _iso_date(j.get("createdAt")), apply_url=j.get("applyUrl"),
                min_amount=sr.get("min"), max_amount=sr.get("max"),
                is_remote=(j.get("workplaceType") == "remote"))


def _ashby_board(slug: str, company: str = "") -> List[dict]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                params={"includeCompensation": "true"}) or {}
    return [_ashby_row(j, slug, company) for j in data.get("jobs", []) if j.get("isListed", True)]


def _ashby_row(j: dict, slug: str, company: str = "") -> dict:
    loc = j.get("location") or ""
    if j.get("isRemote") and "remote" not in loc.lower():
        loc = f"{loc}, Remote".strip(", ")
    row = _row("ashby", j.get("title"), company or _pretty_slug(slug), loc, j.get("jobUrl"),
               j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
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
        tbs = "qdr:m"  # career-ops rule: postings older than ~60 days are mostly ghosts

    def one_host(host: str) -> List[str]:
        # Serper's free tier caps num at 10 → one query per ATS host, run in parallel.
        payload = {"q": f'site:{host} "{query}"{loc}', "num": 10, "tbs": tbs}
        r = requests.post("https://google.serper.dev/search", json=payload,
                          headers={"X-API-KEY": api_key, "Content-Type": "application/json"}, timeout=TIMEOUT)
        if r.status_code != 200:
            logger.info(f"[ATS] Serper {host}: HTTP {r.status_code} {r.text[:120]}")
            return []
        return [i.get("link", "") for i in r.json().get("organic", [])]

    urls: List[str] = []
    with ThreadPoolExecutor(max_workers=len(SERPER_ATS_HOSTS)) as ex:
        for links in ex.map(one_host, SERPER_ATS_HOSTS):
            for link in links:
                if parse_ats_url(link) and link not in urls:
                    urls.append(link)
    ex = ThreadPoolExecutor(max_workers=10)
    futs = [ex.submit(fetch_ats_posting, u) for u in urls[:40]]
    wait(futs, timeout=14)
    rows = [f.result() for f in futs if f.done() and not f.exception() and f.result()]
    ex.shutdown(wait=False, cancel_futures=True)
    return rows


def _ats_direct(query: str, relevant: Callable[[dict], bool]) -> List[dict]:
    companies = load_ats_companies()

    def one(c):
        try:
            rows = BOARD_FETCHERS[c["vendor"]](c["slug"], c.get("name", ""))
            return [r for r in rows if relevant(r)]
        except Exception as e:
            logger.debug(f"[ATS] board {c['vendor']}/{c['slug']}: {e}")
            return []

    out: List[dict] = []
    ex = ThreadPoolExecutor(max_workers=16)
    futs = [ex.submit(one, c) for c in companies]
    wait(futs, timeout=18)
    for f in futs:
        if f.done() and not f.exception():
            out.extend(f.result())
    ex.shutdown(wait=False, cancel_futures=True)
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
            # Exact distinctive words in the title ("Senior Flutter Engineer") …
            if all(t in t_raw for t in distinct_raw):
                return True
            # … or synonyms of them (flutter ≈ mobile) *together with* the role noun.
            if all(c in t_cls for c in distinct) and role and role in t_cls:
                return True
            if role and role in t_cls:
                if d_counts is None:
                    d_counts = {}
                    for t in tokenize((row.get("description") or "")[:6000]):
                        d_counts[t] = d_counts.get(t, 0) + 1
                # Description-only matches need the literal keyword repeated: agencies list dozens
                # of stacks once ("React, Flutter, .NET…"); a real Flutter role mentions it repeatedly.
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
        ex = ThreadPoolExecutor(max_workers=len(REMOTE_FETCHERS))
        futs = {ex.submit(fn, query): name for name, fn in REMOTE_FETCHERS.items()}
        wait(futs, timeout=15)
        for f, name in futs.items():
            if f.done() and not f.exception():
                rows.extend(f.result())
            elif f.done():
                logger.info(f"[OpenSources] {name} failed: {f.exception()}")
        ex.shutdown(wait=False, cancel_futures=True)
    elif site == "hackernews":
        rows = _hackernews(query)
    elif site == "ats":
        ex = ThreadPoolExecutor(max_workers=2)
        futs = [ex.submit(_ats_direct, query, relevant)]
        if serper_key:
            futs.append(ex.submit(_serper_ats_discovery, query, location or country, serper_key, hours_old))
        wait(futs, timeout=22)
        for f in futs:
            if f.done() and not f.exception():
                rows.extend(f.result())
            elif f.done():
                logger.info(f"[OpenSources] ATS sub-task failed: {f.exception()}")
        ex.shutdown(wait=False, cancel_futures=True)
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
        if r.get("salary_text") and not r.get("min_amount"):
            nums = [int(n.replace(",", "")) for n in re.findall(r"\d{2,3}(?:,\d{3})+|\d{5,6}", r["salary_text"])]
            if nums:
                r["min_amount"], r["max_amount"] = min(nums), max(nums)
        out.append(r)
    return out
