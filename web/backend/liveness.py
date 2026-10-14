"""
Liveness — "is this posting still open?" before you spend an evening on it.

Port of career-ops liveness-core.mjs (classifyLiveness) to Python, plus
zero-cost API shortcuts:
  * Greenhouse / Lever / Ashby  → ask the ATS API directly (404 = closed)
  * LinkedIn                    → public guest job-posting endpoint
  * everything else             → fetch the page and classify the text

Results: active | expired | uncertain, with a machine code and a reason.
"""
from __future__ import annotations

import re
import time
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9,fr;q=0.8"}

HARD_EXPIRED_PATTERNS = [re.compile(p, re.I) for p in [
    r"job (is )?no longer available",
    r"job.*no longer open",
    r"\b(?:job|position|role|posting|opening|vacancy|requisition|listing)\b[\s\S]{0,60}?has been filled\b(?!\s+out)",
    r"this job has expired",
    r"job posting has expired",
    r"no longer accepting applications",
    r"this (position|role|job) (is )?no longer",
    r"this (?:job|role|position)(?: listing)? is closed\b",
    r"job (listing )?not found",
    r"the page you are looking for doesn.t exist",
    r"applications?\s+(?:(?:have|are|is)\s+)?closed",
    r"closed on \d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    r"diese stelle (ist )?(nicht mehr|bereits) besetzt",
    r"offre (expiree|n'est plus disponible)",
    r"(cette )?offre n'est plus (disponible|en ligne|active)",
    r"(offre|poste|annonce) (deja )?pourvu(e)?",
    r"ce poste n'est plus (disponible|a pourvoir|ouvert)",
    r"candidatures (closes|cloturees)",
]]
LISTING_PAGE_PATTERNS = [re.compile(r"\d+\s+jobs?\s+found", re.I), re.compile(r"search for jobs page is loaded", re.I)]
SOFT_EXPIRED_PATTERNS = [re.compile(r"\bjob expired\b", re.I)]
BOT_CHALLENGE_PATTERNS = [re.compile(p, re.I) for p in [
    r"just a moment", r"performing security verification", r"checking your browser before",
    r"verify you are (a |not a )?human", r"enable javascript and cookies to continue",
    r"attention required.*cloudflare", r"\bray id\b", r"please complete the security check",
]]
APPLY_PATTERNS = [re.compile(p, re.I) for p in [
    r"\bapply\b", r"\bpostuler\b", r"\bbewerben\b", r"\bsolicitar\b", r"submit application",
    r"easy apply", r"start application", r"candidater",
]]
MIN_CONTENT_CHARS = 300
JOB_ID_TOKEN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{5,}", re.I)

_cache: Dict[str, tuple] = {}
_lock = threading.Lock()
CACHE_TTL = 6 * 3600


def _norm(text: str) -> str:
    text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text)


def classify_liveness(status: int = 0, requested_url: str = "", final_url: str = "",
                      body_text: str = "", apply_controls: List[str] = ()) -> dict:
    body = _norm(body_text)
    controls = [_norm(c) for c in apply_controls or []]

    if status in (404, 410):
        return {"result": "expired", "code": "http_gone", "reason": f"HTTP {status}"}
    for p in BOT_CHALLENGE_PATTERNS:
        if p.search(body):
            return {"result": "uncertain", "code": "bot_challenge", "reason": "anti-bot challenge page"}
    if status in (403, 429, 503):
        return {"result": "uncertain", "code": "access_blocked", "reason": f"HTTP {status} (blocked, likely anti-bot)"}
    if status >= 500:
        return {"result": "uncertain", "code": "server_error", "reason": f"HTTP {status}"}
    if re.search(r"[?&]error=true", final_url or "", re.I):
        return {"result": "expired", "code": "expired_url", "reason": f"redirected to {final_url}"}
    for p in HARD_EXPIRED_PATTERNS:
        if p.search(body):
            return {"result": "expired", "code": "expired_body", "reason": f"page says: “{p.search(body).group(0)}”"}

    ids = JOB_ID_TOKEN.findall(requested_url or "")
    if ids and final_url and ids[-1].lower() not in final_url.lower():
        return {"result": "uncertain", "code": "redirected_off_posting",
                "reason": "redirected away from the posting (job id missing from final URL)"}
    if any(p.search(c) for c in controls for p in APPLY_PATTERNS):
        return {"result": "active", "code": "apply_control_visible", "reason": "apply button visible"}
    for p in SOFT_EXPIRED_PATTERNS:
        if p.search(body):
            return {"result": "expired", "code": "expired_body_soft", "reason": "page says job expired"}
    for p in LISTING_PAGE_PATTERNS:
        if p.search(body):
            return {"result": "expired", "code": "listing_page", "reason": "redirected to a search/listing page"}
    if len(body.strip()) < MIN_CONTENT_CHARS:
        # career-ops renders pages with Playwright; we fetch raw HTML, so a near-empty 200
        # page is usually a JavaScript shell (Indeed, Workday…), not a closed posting.
        return {"result": "uncertain", "code": "js_rendered", "reason": "page needs JavaScript — open it to confirm"}
    return {"result": "uncertain", "code": "no_apply_control", "reason": "content present but no apply button found"}


def _check_ats(url: str):
    from .open_sources import parse_ats_url, fetch_ats_posting
    if not parse_ats_url(url):
        return None
    row = fetch_ats_posting(url)
    if row:
        return {"result": "active", "code": "ats_api_listed", "reason": "listed on the company's ATS API"}
    return {"result": "expired", "code": "ats_api_missing", "reason": "no longer listed on the company's ATS"}


def _check_linkedin(url: str):
    m = re.search(r"currentJobId=(\d+)", url) or re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", url)
    if not m:
        return None
    r = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}",
                     headers=HEADERS, timeout=12)
    if r.status_code in (404, 410):
        return {"result": "expired", "code": "http_gone", "reason": f"HTTP {r.status_code}"}
    if r.status_code != 200:
        return {"result": "uncertain", "code": "access_blocked", "reason": f"LinkedIn HTTP {r.status_code}"}
    text = r.text.lower()
    if "no longer accepting applications" in text:
        return {"result": "expired", "code": "expired_body", "reason": "LinkedIn: no longer accepting applications"}
    if "apply" in text:
        return {"result": "active", "code": "apply_control_visible", "reason": "LinkedIn: accepting applications"}
    return {"result": "uncertain", "code": "no_apply_control", "reason": "LinkedIn page without apply control"}


def _check_page(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=14, allow_redirects=True)
    body, controls = "", []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        controls = [el.get_text(" ", strip=True)[:80] for el in soup.find_all(["a", "button", "input"])
                    if el.get_text(strip=True) or el.get("value")]
        controls += [el.get("value", "") for el in soup.find_all("input") if el.get("value")]
        body = soup.get_text(" ", strip=True)
    except Exception:
        body = re.sub(r"<[^>]+>", " ", r.text or "")
    return classify_liveness(r.status_code, url, r.url, body, controls)


def check_liveness(url: str) -> dict:
    url = (url or "").strip()
    if not url.startswith("http"):
        return {"url": url, "result": "uncertain", "code": "bad_url", "reason": "not an http(s) URL"}
    now = time.time()
    with _lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    try:
        res = _check_ats(url) or (_check_linkedin(url) if "linkedin.com" in url else None) or _check_page(url)
    except requests.Timeout:
        res = {"result": "uncertain", "code": "timeout", "reason": "page timed out"}
    except Exception as e:
        res = {"result": "uncertain", "code": "fetch_error", "reason": str(e)[:160]}
    res = {"url": url, **res, "checked_at": int(now)}
    with _lock:
        _cache[url] = (now, res)
    return res


def check_many(urls: List[str], workers: int = 8) -> List[dict]:
    urls = [u for u in dict.fromkeys(urls) if u][:40]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(check_liveness, urls))
