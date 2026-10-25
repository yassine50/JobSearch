"""
linkedin_post_hunter.py
=======================
Specialized engine to discover organic LinkedIn hiring posts by recruiters,
extract explicit recruiter emails from post text, and "dig deep" to uncover
the recruiter's corporate email if not directly specified in the post.
"""

from __future__ import annotations

import re
import time
import json
import logging
import urllib.parse
import hashlib
import threading
import copy
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

import requests
from requests.adapters import HTTPAdapter

try:
    from curl_cffi import requests as c_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    c_requests = requests

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False

from .auto_dispatcher import has_valid_mx

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,10}", re.I)
OBFUSCATED_EMAIL_REGEX = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\[AT\]|\(AT\)|\s+at\s+)\s*([a-zA-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\s+dot\s+|\.)\s*([a-zA-Z]{2,10})",
    re.I
)

FALSE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".js", ".css", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".pdf", ".zip", ".tar", ".gz"
)
FALSE_DOMAINS = {
    "linkedin.com", "licdn.com", "example.com", "example.org", "example.net",
    "test.com", "dummy.com", "sample.com", "domain.com", "yourcompany.com",
    "company.com", "email.com", "sentry.io", "wixpress.com"
}

SYSTEM_AUTOMATED_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster",
    "bounce", "bounces", "notifications", "notification", "alerts", "alert", "billing",
    "invoice", "invoices", "support-noreply", "news", "newsletter", "unsubscribe"
}

# Connection-pooled HTTP Session for high-concurrency requests
_POST_SESSION = requests.Session()
_http_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=0)
_POST_SESSION.mount("https://", _http_adapter)
_POST_SESSION.mount("http://", _http_adapter)

# Shared bounded worker pool + thread-local DDGS reuse to keep VPS RAM and CPU footprint minimal
_HUNTER_POOL = ThreadPoolExecutor(max_workers=14)
_TLS_DDGS = threading.local()


def generate_stable_post_id(clean_url: str) -> str:
    """
    Generates a 100% stable, deterministic identifier for a LinkedIn job posting.
    Extracts the official numeric job ID from LinkedIn URLs (e.g., 4123456789),
    or uses a canonical SHA-256 hash of the normalized URL.
    """
    if not clean_url:
        return "li_job_unknown"
    # LinkedIn job URLs typically contain an 8-12 digit numeric ID
    m = re.search(r"(?:/view/|/jobs/view/|currentJobId=|-)(\d{8,12})(?:[/?&#]|$)", clean_url)
    if m:
        return f"li_job_{m.group(1)}"
    # Generic numeric fallback in URL
    m_gen = re.search(r"(\d{8,12})", clean_url)
    if m_gen:
        return f"li_job_{m_gen.group(1)}"
    # Canonical SHA-256 fallback
    norm_url = clean_url.strip().lower().split("?")[0].rstrip("/")
    digest = hashlib.sha256(norm_url.encode("utf-8")).hexdigest()[:12]
    return f"li_post_{digest}"


class PostHunterSearchCache:
    """
    Thread-safe, bounded LRU cache with TTL for LinkedIn post searches.
    Ensures identical queries return instant, consistent, deterministic results.
    """
    def __init__(self, max_entries: int = 64, default_ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._default_ttl = default_ttl_seconds

    def _make_key(self, role: str, locations: Optional[List[str]], email_only: bool, time_range: str, limit: int, page: int = 1) -> str:
        norm_role = (role or "").strip().lower()
        clean_locs = sorted([l.strip().lower() for l in (locations or []) if l and l.strip()])
        return f"{norm_role}|{','.join(clean_locs)}|{bool(email_only)}|{time_range or 'all'}|{limit}|p{page}"

    def get(self, role: str, locations: Optional[List[str]], email_only: bool, time_range: str, limit: int, page: int = 1) -> Optional[Any]:
        key = self._make_key(role, locations, email_only, time_range, limit, page)
        with self._lock:
            if key not in self._cache:
                return None
            ts, data = self._cache[key]
            # Use shorter TTL for 24h searches to avoid stale empty results
            ttl = 90 if time_range in ("24h", "1d", "day", "past-24h") else self._default_ttl
            if time.time() - ts > ttl:
                del self._cache[key]
                return None
            return copy.deepcopy(data)

    def set(self, role: str, locations: Optional[List[str]], email_only: bool, time_range: str, limit: int, data: Any, page: int = 1) -> None:
        key = self._make_key(role, locations, email_only, time_range, limit, page)
        # Never cache empty results — always re-fetch
        if isinstance(data, tuple) and len(data) == 2:
            posts_list, _ = data
            if isinstance(posts_list, list) and len(posts_list) == 0:
                return
        elif isinstance(data, list) and len(data) == 0:
            return
        with self._lock:
            if len(self._cache) >= self._max_entries:
                # Evict oldest entry
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), copy.deepcopy(data))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

_SEARCH_CACHE = PostHunterSearchCache(max_entries=64, default_ttl_seconds=300)

_MX_CACHE: Dict[str, bool] = {}

def strictly_verify_mx(domain: str) -> bool:
    """
    Authoritative DNS MX verification.
    Verifies that the domain actually has resolving MX records that accept mail.
    Explicitly rejects RFC 7505 null MX records and domains without mail routing.
    """
    clean_domain = domain.strip().lower().rstrip(".")
    if not clean_domain or "." not in clean_domain:
        return False
        
    if clean_domain in _MX_CACHE:
        return _MX_CACHE[clean_domain]

    if not HAS_DNS:
        try:
            val = has_valid_mx(clean_domain)
            _MX_CACHE[clean_domain] = val
            return val
        except Exception:
            _MX_CACHE[clean_domain] = False
            return False

    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 2.0
        resolver.timeout = 2.0
        try:
            answers = resolver.resolve(clean_domain, "MX")
        except (dns.resolver.NoNameservers, dns.resolver.Timeout):
            resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
            answers = resolver.resolve(clean_domain, "MX")

        valid_hosts = []
        for rdata in answers:
            exchange = str(rdata.exchange).rstrip(".").lower()
            # RFC 7505 null MX check
            if exchange and exchange != "." and exchange != "0.0.0.0":
                valid_hosts.append(exchange)

        is_valid = len(valid_hosts) > 0
        _MX_CACHE[clean_domain] = is_valid
        return is_valid
    except Exception:
        _MX_CACHE[clean_domain] = False
        return False

def verify_recruiter_email_strictly(email: str, blacklisted_set: Optional[Set[str]] = None) -> Tuple[bool, str]:
    """
    Strict email validation:
    1. RFC syntax and format check
    2. Non-system / non-automated prefix check
    3. Blacklist / bounce check
    4. Authoritative DNS MX check
    Returns: (is_valid: bool, reason: str)
    """
    if not email:
        return False, "Empty email"
    
    clean_em = email.strip().lower().rstrip(".,:;!?)'\"")
    if "@" not in clean_em:
        return False, "Missing @ symbol"
        
    parts = clean_em.split("@")
    if len(parts) != 2:
        return False, "Invalid email structure"
        
    local, domain = parts[0].strip(), parts[1].strip()
    if len(local) < 2 or len(domain) < 4:
        return False, "Email address too short"
        
    if any(clean_em.endswith(ext) for ext in FALSE_EXTENSIONS):
        return False, "False extension in email"
        
    if local in SYSTEM_AUTOMATED_PREFIXES:
        return False, "Automated / noreply system email"
        
    if domain in FALSE_DOMAINS:
        return False, "Restricted placeholder domain"
        
    tld = domain.split(".")[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False, "Invalid TLD"
        
    if blacklisted_set and clean_em in blacklisted_set:
        return False, "Email blacklisted due to previous delivery bounce"
        
    if not strictly_verify_mx(domain):
        return False, f"Domain '{domain}' has no valid DNS MX mail exchange records"
        
    return True, "Valid MX-verified email"

def unescape_obfuscated_emails(text: str) -> List[str]:
    """Decodes obfuscated emails like 'john [at] company [dot] com' -> 'john@company.com'."""
    found = []
    for m in OBFUSCATED_EMAIL_REGEX.finditer(text):
        local, domain_mid, tld = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        constructed = f"{local}@{domain_mid}.{tld}".lower()
        found.append(constructed)
    return found

def extract_clean_emails_from_text(text: str, blacklisted_set: Set[str]) -> List[str]:
    """Extracts valid, deliverable recruiter emails from text."""
    if not text:
        return []
    
    # Pre-clean string by replacing escaped characters with spaces
    text = re.sub(r'\\[nrtfb]', ' ', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    
    raw = EMAIL_REGEX.findall(text)
    raw.extend(unescape_obfuscated_emails(text))
    
    clean = []
    seen = set()
    for em in raw:
        em_lower = em.strip().lower().rstrip(".,:;!?)'\"")
        em_lower = re.sub(r'^[\\/\s\'"]+', '', em_lower)
        if not em_lower or "@" not in em_lower:
            continue
        if em_lower in seen:
            continue
        if any(em_lower.endswith(ext) for ext in FALSE_EXTENSIONS):
            continue
        domain = em_lower.split("@")[-1]
        if domain in FALSE_DOMAINS:
            continue
        if em_lower in blacklisted_set:
            continue
        # Verify valid domain shape
        if "." not in domain or len(domain.split(".")[-1]) < 2:
            continue
        seen.add(em_lower)
        clean.append(em_lower)
        
    # Remove duplicates where a leading 'n' was captured from a raw \n
    final_clean = []
    for em in clean:
        local, domain = em.split("@", 1)
        if local.startswith("n") and len(local) > 2:
            stripped = local[1:] + "@" + domain
            if stripped in seen:
                continue
        final_clean.append(em)
        
    return final_clean

def extract_linkedin_activity_id(url: str) -> Optional[str]:
    """Extracts unique numeric activity, share, or ugcPost Snowflake ID from LinkedIn post URLs."""
    if not url:
        return None
    m = re.search(
        r"(?:(?:activity|share|ugcPost)[:\-](\d{15,22})|urn:li:(?:activity|share|ugcPost):(\d{15,22}))",
        url,
        re.I,
    )
    if m:
        return m.group(1) or m.group(2)
    return None


def decode_linkedin_snowflake_age(url_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Decodes the exact UTC publication timestamp and age in hours directly from LinkedIn's
    64-bit Snowflake ID (activity, share, or ugcPost), where the upper 42 bits (`id >> 22`)
    represent Unix epoch time in milliseconds.
    Works 100% offline from the URL even when LinkedIn blocks page loads.
    """
    act_id = extract_linkedin_activity_id(url_or_id) if not url_or_id.isdigit() else url_or_id
    if not act_id:
        return None
    try:
        sid = int(act_id)
        ts_ms = sid >> 22
        now_dt = datetime.now(timezone.utc)
        now_ms = int(now_dt.timestamp() * 1000)
        # Valid LinkedIn Snowflake range: 2015-01-01 through now + 24h clock skew
        if ts_ms < 1420070400000 or ts_ms > (now_ms + 86400000):
            return None
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        diff_sec = max((now_dt - dt).total_seconds(), 0.0)
        age_hours = round(diff_sec / 3600.0, 1)
        if age_hours < 1:
            age_str = "Just now"
        elif age_hours < 24:
            age_str = f"{max(1, int(age_hours))}h ago"
        elif age_hours < 48:
            age_str = "1d ago"
        elif age_hours < 168:
            age_str = f"{int(age_hours // 24)}d ago"
        elif age_hours < 720:
            age_str = f"{int(age_hours // 168)}w ago"
        else:
            age_str = f"{max(1, int(age_hours // 720))}mo ago"
        return {
            "activity_id": act_id,
            "date_published": dt.isoformat(),
            "published_epoch": int(ts_ms // 1000),
            "age_hours": age_hours,
            "age_str": age_str,
            "is_under_24h": age_hours <= 48.0,
        }
    except Exception:
        return None


def extract_url_slug_context(post_url: str) -> str:
    """
    Extracts human-readable post keywords from `/posts/<author>_<slug>-activity-<id>`.
    Provides reliable fallback context when search engine snippets are truncated.
    """
    if not post_url:
        return ""
    try:
        path = urllib.parse.urlparse(post_url).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "posts":
            slug_part = parts[1]
            if "_" in slug_part:
                body_slug = slug_part.split("_", 1)[1]
                body_slug = re.sub(r"-(?:activity|share|ugcPost)-\d+.*$", "", body_slug, flags=re.I)
                words = urllib.parse.unquote(body_slug).replace("-", " ").replace("_", " ").strip()
                return re.sub(r"\s+", " ", words)
    except Exception:
        pass
    return ""


LINKEDIN_BOILERPLATE_MARKERS = (
    "500 million+ members",
    "750 million+ members",
    "1 billion members",
    "manage your professional identity",
    "build and engage with your professional network",
    "access knowledge, insights and opportunities",
    "sign in to view more content",
    "create your free account or sign in to continue your search",
    "join linkedin today for free",
)


def is_linkedin_boilerplate(text: str) -> bool:
    """Returns True if text is LinkedIn's generic login-wall / marketing meta description."""
    if not text:
        return True
    low = text.strip().lower()
    if any(marker in low for marker in LINKEDIN_BOILERPLATE_MARKERS):
        # Check if there is substantial non-boilerplate text after stripping markers
        cleaned = clean_linkedin_boilerplate(text)
        return len(cleaned.strip()) < 35
    return False


def clean_linkedin_boilerplate(text: str) -> str:
    """Strips LinkedIn login-wall marketing boilerplate and search engine chrome from text."""
    if not text:
        return ""
    out = text
    patterns = [
        r"(?i)\b(?:\d+\s*million\+|1\s*billion\+?)?\s*members\s*\|\s*manage your professional identity\.?",
        r"(?i)manage your professional identity\.?\s*build and engage with your professional network\.?",
        r"(?i)build and engage with your professional network\.?\s*access knowledge,\s*insights and opportunities\.?",
        r"(?i)access knowledge,\s*insights and opportunities\.?",
        r"(?i)sign in to view more content.*$",
        r"(?i)create your free account or sign in.*$",
    ]
    for pat in patterns:
        out = re.sub(pat, " ", out)
    return re.sub(r"\s+", " ", out).strip()


def canonicalize_linkedin_post_url(raw_url: str) -> Tuple[str, str]:
    """
    Strips tracking queries and derives canonical clean URL and a deduplication key.
    Exclusively accepts /posts/... and /feed/update/... formats.
    Strictly rejects all job board URLs (/jobs/, /jobs-guest/, /job/).
    """
    if not raw_url:
        return "", ""
    raw_lower = raw_url.lower()
    if "/jobs/" in raw_lower or "jobs-guest" in raw_lower or "/job/" in raw_lower or "currentjobid=" in raw_lower:
        return "", ""
    if not ("linkedin.com/posts" in raw_lower or "linkedin.com/feed/update" in raw_lower):
        return "", ""
    try:
        clean = raw_url.split("?")[0].split("#")[0].rstrip("/")
        act_id = extract_linkedin_activity_id(raw_url)
        if act_id:
            parsed = urllib.parse.urlparse(clean)
            if parsed.path.startswith("/posts/"):
                return clean, f"act_{act_id}"
            return f"https://www.linkedin.com/feed/update/urn:li:activity:{act_id}", f"act_{act_id}"
        return clean, clean.lower()
    except Exception:
        clean = raw_url.split("?")[0].rstrip("/")
        return clean, clean.lower()

def extract_yahoo_redirect_url(href: str) -> Optional[str]:
    """Extracts genuine target URL from Yahoo and AOL search redirect wrappers."""
    if not href or any(eng in href for eng in ("search.yahoo.com/search", "yahoo.com/?p=", "/copilot", "/search?")):
        return None
    if "/RU=" in href:
        m = re.search(r"/RU=([^/]+)/", href)
        if m:
            try:
                real = urllib.parse.unquote(m.group(1))
                if ("linkedin.com/posts" in real or "linkedin.com/feed/update" in real) and real.startswith("http"):
                    return real.split("?")[0].rstrip("/")
            except Exception:
                pass
    if ("linkedin.com/posts" in href or "linkedin.com/feed/update" in href) and href.startswith("http"):
        return href.split("?")[0].rstrip("/")
    return None

def parse_author_info_from_url(post_url: str, title_hint: str = "") -> Dict[str, str]:
    """Derives author name and slug from linkedin.com/posts/john-doe-123_... URL or search title."""
    if title_hint:
        m1 = re.search(r"^([A-Z][A-Za-z\s.'-]{2,35}?)\s+(?:on\s+LinkedIn|posted\s+on\s+the\s+topic)\b", title_hint)
        if m1:
            return {"slug": "", "name": m1.group(1).strip()}
        m2 = re.search(r"\|\s*([A-Z][A-Za-z\s.'-]{2,35}?)(?:\s*\|\s*\d+\s*comments?)?\s*$", title_hint)
        if m2 and "linkedin" not in m2.group(1).lower():
            return {"slug": "", "name": m2.group(1).strip()}
    try:
        path = urllib.parse.urlparse(post_url).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "posts":
            raw_slug = parts[1].split("_")[0]
            slug = urllib.parse.unquote(raw_slug)
            cleaned_name = re.sub(r"-[a-z0-9]{5,}$", "", slug, flags=re.I)
            cleaned_name = re.sub(r"-\d+[a-z0-9]*$", "", cleaned_name, flags=re.I)
            cleaned_name = cleaned_name.replace("-", " ").replace("_", " ").title().strip()
            cleaned_name = urllib.parse.unquote(cleaned_name)
            if len(cleaned_name) >= 2:
                return {"slug": slug, "name": cleaned_name}
    except Exception:
        pass
    return {"slug": "", "name": "LinkedIn Recruiter"}

LOCATION_KEYWORDS = {
    "remote": ["remote", "work from home", "wfh", "anywhere", "telecommute", "100% remote"],
    "remote us": ["remote", "us", "usa", "united states"],
    "remote europe": ["remote", "europe", "emea", "uk", "germany"],
    "remote mena": ["remote", "mena", "uae", "saudi", "morocco", "gulf"],
    "remote apac": ["remote", "apac", "asia", "singapore", "australia"],
    "united states": ["united states", "usa", "us", "u.s.", "america", "new york", "san francisco", "california", "texas"],
    "usa": ["united states", "usa", "us", "u.s.", "america"],
    "us": ["united states", "usa", "us", "u.s."],
    "new york": ["new york", "nyc", "manhattan"],
    "san francisco": ["san francisco", "bay area", "silicon valley"],
    "united kingdom": ["united kingdom", "uk", "u.k.", "london", "britain", "england", "scotland"],
    "uk": ["united kingdom", "uk", "u.k.", "london", "england"],
    "london": ["london", "uk", "united kingdom"],
    "canada": ["canada", "toronto", "vancouver", "montreal", "ontario"],
    "uae": ["uae", "u.a.e.", "dubai", "abu dhabi", "sharjah", "united arab emirates"],
    "dubai": ["dubai", "uae", "united arab emirates"],
    "united arab emirates": ["united arab emirates", "uae", "dubai", "abu dhabi"],
    "saudi arabia": ["saudi arabia", "saudi", "ksa", "k.s.a.", "riyadh", "jeddah", "dammam"],
    "ksa": ["saudi arabia", "saudi", "ksa", "riyadh"],
    "riyadh": ["riyadh", "saudi arabia", "ksa"],
    "morocco": ["morocco", "maroc", "casablanca", "rabat", "marrakech", "tangier"],
    "maroc": ["morocco", "maroc", "casablanca", "rabat"],
    "casablanca": ["casablanca", "morocco", "maroc"],
    "germany": ["germany", "deutschland", "berlin", "munich", "frankfurt", "hamburg"],
    "berlin": ["berlin", "germany"],
    "france": ["france", "paris", "lyon"],
    "paris": ["paris", "france"],
    "netherlands": ["netherlands", "amsterdam", "holland", "rotterdam"],
    "amsterdam": ["amsterdam", "netherlands"],
    "switzerland": ["switzerland", "zurich", "geneva", "swiss"],
    "spain": ["spain", "espana", "madrid", "barcelona"],
    "italy": ["italy", "italia", "rome", "milan"],
    "ireland": ["ireland", "dublin"],
    "poland": ["poland", "polska", "warsaw", "krakow"],
    "sweden": ["sweden", "sverige", "stockholm"],
    "belgium": ["belgium", "brussels"],
    "singapore": ["singapore"],
    "australia": ["australia", "sydney", "melbourne", "brisbane"],
    "india": ["india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon"],
    "egypt": ["egypt", "cairo", "alexandria"],
    "qatar": ["qatar", "doha"],
    "kuwait": ["kuwait"],
    "bahrain": ["bahrain", "manama"],
    "oman": ["oman", "muscat"],
    "jordan": ["jordan", "amman"],
    "austria": ["austria", "vienna", "wien"],
    "denmark": ["denmark", "copenhagen"],
    "norway": ["norway", "oslo"],
    "portugal": ["portugal", "lisbon", "porto"],
    "mexico": ["mexico", "mexico city", "cdmx", "guadalajara"],
    "brazil": ["brazil", "brasil", "sao paulo", "rio de janeiro"],
    "argentina": ["argentina", "buenos aires"],
    "colombia": ["colombia", "bogota", "medellin"],
    "chile": ["chile", "santiago"],
    "japan": ["japan", "tokyo"],
    "south korea": ["south korea", "korea", "seoul"],
    "new zealand": ["new zealand", "auckland", "wellington"],
    "malaysia": ["malaysia", "kuala lumpur"],
    "philippines": ["philippines", "manila"],
    "indonesia": ["indonesia", "jakarta"],
}

INDIAN_LOCATION_MARKERS = [
    "india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "noida", 
    "gurgaon", "gurugram", "chennai", "kolkata", "ahmedabad", "jaipur", "chandigarh",
    "lucknow", "gomti nagar", "kochi", "cochin", "kerala", "tamil nadu", "karnataka",
    "maharashtra", "indore", "bhopal", "lpa", "ctc", "immediate joiner", "notice period",
    "inr", "₹", "+91", "tcs", "infosys", "wipro", "hcl tech"
]

US_LOCATION_REGEX = re.compile(
    r"\b("
    r"united states|usa|u\.s\.a?|us-based|us based|us remote|remote us|remote \(us\)|remote \(usa\)|"
    r"in the us|us citizen|us only|us timezone|est|pst|cst|w2|c2c|1099|"
    r"new york|nyc|manhattan|brooklyn|california|san francisco|bay area|silicon valley|"
    r"los angeles|san diego|seattle|washington dc|texas|austin|dallas|houston|"
    r"chicago|illinois|boston|massachusetts|florida|miami|orlando|tampa|atlanta|georgia|"
    r"colorado|denver|virginia|maryland|north carolina|charlotte|raleigh|"
    r"arizona|phoenix|mesa|ohio|columbus|cleveland|pennsylvania|philadelphia|pittsburgh|"
    r"michigan|detroit|minnesota|minneapolis|utah|salt lake|tennessee|nashville"
    r")\b",
    re.I
)

def extract_post_location(full_text: str, author_headline: str, target_location: str = "", target_locations: Optional[List[str]] = None) -> str:
    combined = (full_text + " " + author_headline).lower()
    
    # 1. Clean location pattern like "Location: New York, NY", "Job Location - Austin, TX"
    m_loc = re.search(r"(?:location|job location|office location|work location)[\s:\-–—]+([A-Za-z\s,]{2,25})(?:\n|\r|\.|\;|\)|\||$)", full_text, re.I)
    if m_loc:
        val = m_loc.group(1).strip()
        val_clean = val.lower()
        invalid_words = ["hiring", "immediate", "urgent", "looking", "open", "developer", "engineer", 
                         "flutter", "react", "expanding", "department", "team", "growth", "candidate", "position"]
        if len(val) < 30 and not any(k in val_clean for k in invalid_words):
            return val

    is_remote = any(w in combined for w in ["remote", "work from home", "wfh", "anywhere", "telecommute", "100% remote"])

    all_locs = []
    if target_locations:
        all_locs.extend([l.lower() for l in target_locations if l])
    if target_location:
        all_locs.append(target_location.lower())

    # If target includes USA, prioritize USA locations and ensure no foreign leaks
    if any(l in ("usa", "us", "united states", "america", "remote us") for l in all_locs) and bool(US_LOCATION_REGEX.search(combined)):
        for us_name, us_aliases in [
            ("New York, USA", ["new york", "nyc", "manhattan", "brooklyn"]),
            ("San Francisco, USA", ["san francisco", "bay area", "silicon valley"]),
            ("Austin, TX", ["austin"]),
            ("Seattle, WA", ["seattle"]),
            ("Chicago, IL", ["chicago"]),
            ("Los Angeles, CA", ["los angeles"]),
            ("Boston, MA", ["boston"]),
            ("Atlanta, GA", ["atlanta"]),
            ("Dallas, TX", ["dallas", "houston"]),
            ("Denver, CO", ["denver"]),
            ("Miami, FL", ["miami", "orlando", "tampa"]),
            ("Phoenix, AZ", ["phoenix", "mesa"]),
            ("United States", ["united states", "usa"]),
        ]:
            if any(alias in combined for alias in us_aliases):
                return f"Remote ({us_name})" if is_remote else us_name
        return "Remote (United States)" if is_remote else "United States"

    # 2. Known places & cities
    KNOWN_PLACES = [
        ("Dubai, UAE", ["dubai", "abu dhabi", "uae", "united arab emirates"]),
        ("Riyadh, Saudi Arabia", ["riyadh", "jeddah", "saudi arabia", "ksa"]),
        ("Casablanca, Morocco", ["casablanca", "rabat", "morocco", "maroc"]),
        ("Cairo, Egypt", ["cairo", "alexandria", "egypt"]),
        ("Doha, Qatar", ["doha", "qatar"]),
        ("Kuwait City, Kuwait", ["kuwait"]),
        ("London, UK", ["london", "united kingdom"]),
        ("New York, USA", ["new york", "nyc", "manhattan"]),
        ("San Francisco, USA", ["san francisco", "bay area", "silicon valley"]),
        ("United States", ["united states", "usa"]),
        ("Toronto, Canada", ["toronto", "vancouver", "montreal", "canada"]),
        ("Berlin, Germany", ["berlin", "munich", "frankfurt", "germany", "deutschland"]),
        ("Paris, France", ["paris", "france"]),
        ("Amsterdam, Netherlands", ["amsterdam", "netherlands", "holland"]),
        ("Zurich, Switzerland", ["zurich", "geneva", "switzerland"]),
        ("Madrid, Spain", ["madrid", "barcelona", "spain"]),
        ("Dublin, Ireland", ["dublin", "ireland"]),
        ("Milan, Italy", ["milan", "rome", "italy", "italia"]),
        ("Warsaw, Poland", ["warsaw", "krakow", "poland", "polska"]),
        ("Stockholm, Sweden", ["stockholm", "sweden", "sverige"]),
        ("Brussels, Belgium", ["brussels", "belgium"]),
        ("Vienna, Austria", ["vienna", "austria", "wien"]),
        ("Copenhagen, Denmark", ["copenhagen", "denmark"]),
        ("Oslo, Norway", ["oslo", "norway"]),
        ("Lisbon, Portugal", ["lisbon", "portugal", "porto"]),
        ("Singapore", ["singapore"]),
        ("Sydney, Australia", ["sydney", "melbourne", "australia"]),
        ("Tokyo, Japan", ["tokyo", "japan"]),
        ("Seoul, South Korea", ["seoul", "south korea", "korea"]),
        ("Auckland, New Zealand", ["auckland", "new zealand"]),
        ("Manama, Bahrain", ["manama", "bahrain"]),
        ("Muscat, Oman", ["muscat", "oman"]),
        ("Amman, Jordan", ["amman", "jordan"]),
        ("Mexico City, Mexico", ["mexico city", "mexico", "cdmx"]),
        ("São Paulo, Brazil", ["sao paulo", "são paulo", "brazil", "brasil"]),
        ("Buenos Aires, Argentina", ["buenos aires", "argentina"]),
        ("Bangalore, India", ["bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "india"]),
    ]

    for display_name, aliases in KNOWN_PLACES:
        if any(alias in combined for alias in aliases):
            if is_remote:
                return f"Remote ({display_name})"
            return display_name

    if is_remote:
        return "Remote"
        
    if all_locs and all_locs[0] not in ("", "all", "worldwide", "anywhere"):
        return all_locs[0].title()
        
    return "Worldwide / Flexible"

def check_single_location_match(full_text: str, author_headline: str, target_location: str, post_url: str = "") -> bool:
    if not target_location or target_location.strip().lower() in ("", "all", "worldwide", "anywhere"):
        return True
        
    t_clean = target_location.strip().lower()
    combined = (full_text + " " + author_headline).lower()
    url_low = (post_url or "").lower()
    
    # 1. Negative & Positive strict checks for USA / US
    if t_clean in ("usa", "us", "united states", "america", "remote us"):
        # Rigidly REJECT any post matching Indian cities, LPA, CTC, +91, Indian states
        if any(im in combined for im in INDIAN_LOCATION_MARKERS):
            return False
        # Rigidly REJECT other overseas domestic locations
        if any(nm in combined for nm in ["jakarta", "indonesia", "pakistan", "lahore", "karachi", "bangladesh", "dhaka", "philippines", "manila", "nigeria", "lagos", "kenya", "nairobi"]):
            return False
        # Allow remote / worldwide posts
        if any(w in combined for w in ["remote", "wfh", "work from home", "anywhere", "worldwide", "telecommute"]):
            return True
        # Match for USA keywords / states
        return bool(US_LOCATION_REGEX.search(full_text + " " + author_headline))

    # 2. Strict check for other non-Indian countries (UK, Canada, Germany, France, Morocco, UAE, etc.)
    if t_clean not in ("india", "bangalore", "mumbai", "delhi", "pune", "hyderabad", "chennai"):
        if any(im in combined for im in ["bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon", "chennai", "lucknow", "lpa", "ctc", "+91"]):
            return False

    # 3. Check if the post URL is hosted on the target country's regional LinkedIn subdomain (e.g., fr.linkedin.com, ma.linkedin.com)
    subdom_entry = COUNTRY_LINKEDIN_SUBDOMAINS.get(t_clean, "")
    if subdom_entry:
        subdom_host = subdom_entry.split("/")[0]
        if subdom_host and subdom_host in url_low:
            return True

    if t_clean in ("remote", "wfh", "work from home"):
        return any(w in combined for w in ["remote", "wfh", "work from home", "anywhere", "worldwide", "telecommute"])
        
    keywords = LOCATION_KEYWORDS.get(t_clean, [t_clean])
    if any(k in combined for k in keywords):
        return True
        
    if any(w in combined for w in ["remote", "wfh", "work from home", "anywhere", "worldwide"]):
        return True

    words = [w.strip() for w in t_clean.split() if len(w) > 2]
    if any(w in combined for w in words):
        return True
        
    return False

def check_location_match(full_text: str, author_headline: str, target_location: str = "", target_locations: Optional[List[str]] = None, post_url: str = "") -> bool:
    locs = []
    if target_locations:
        locs = [l.strip() for l in target_locations if l and l.strip()]
    elif target_location:
        locs = [target_location.strip()]
        
    if not locs or any(l.lower() in ("", "all", "worldwide", "anywhere") for l in locs):
        return True
        
    return any(check_single_location_match(full_text, author_headline, loc, post_url=post_url) for loc in locs)

def parse_user_query(query: str, locations: Optional[List[str]] = None) -> Tuple[str, List[str]]:
    """
    Parses a user search query, stripping hashtags (#hiring, #jobopening),
    extracting country/city names if present, and returning a cleaned role query
    and an updated list of locations.
    """
    if not query:
        return "", locations or ["Worldwide"]

    cleaned_locations = list(locations or [])
    if "Worldwide" in cleaned_locations and len(cleaned_locations) > 1:
        cleaned_locations = [l for l in cleaned_locations if l.lower() != "worldwide"]

    q = query.strip()

    # 1. Remove generic hiring hashtags / words from role keyword
    hiring_pattern = r"(?i)#?(?:wearehiring|nowhiring|hiringalert|jobopening|jobopportunity|hiring|recruiting|careers|vacancy|jobalert|jobs|job|vacancies)\b"
    q = re.sub(hiring_pattern, "", q).strip()

    # 2. Extract country/city if in query e.g. "flutter in germany", "react developer uk", "python remote"
    m_in = re.search(r"(?i)\s+in\s+([a-zA-Z\s]+)$", q)
    if m_in:
        candidate_loc = m_in.group(1).strip().lower()
        matched_loc = None
        for loc_key in sorted(LOCATION_KEYWORDS.keys(), key=lambda x: -len(x)):
            if loc_key == candidate_loc or candidate_loc in LOCATION_KEYWORDS[loc_key]:
                matched_loc = loc_key.title()
                break
        if matched_loc:
            if "Worldwide" in cleaned_locations:
                cleaned_locations.remove("Worldwide")
            if matched_loc not in cleaned_locations:
                cleaned_locations.append(matched_loc)
            q = q[:m_in.start()].strip()
    else:
        # Check if any location keyword is present in the query
        for loc_key, aliases in sorted(LOCATION_KEYWORDS.items(), key=lambda x: -len(x[0])):
            found = False
            for alias in sorted(aliases, key=lambda a: -len(a)):
                alias_pattern = rf"(?i)\b{re.escape(alias)}\b"
                if re.search(alias_pattern, q):
                    if alias.lower() not in ("it", "lead", "go"):
                        if "Worldwide" in cleaned_locations:
                            cleaned_locations.remove("Worldwide")
                        loc_title = loc_key.title()
                        if loc_title not in cleaned_locations:
                            cleaned_locations.append(loc_title)
                        q = re.sub(alias_pattern, "", q, flags=re.I).strip()
                        found = True
                        break
            if found:
                break

    # Clean punctuation and extra spaces
    q = re.sub(r"(?i)\s+in\s+", " ", q)
    q = re.sub(r"[#,\-_]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()

    if not q:
        q = re.sub(r"[#]", "", query).strip()

    if not cleaned_locations:
        cleaned_locations = ["Worldwide"]

    return q, cleaned_locations

# ---------------------------------------------------------
# RECRUITMENT INTENT ANALYZER (Anti-False-Positive Filter)
# ---------------------------------------------------------

NON_RECRUITMENT_PATTERNS = [
    # A) Job Seekers looking for work / #OpenToWork
    r"(?:^|\W)#?opentowork\b",
    r"\bopen to work\b",
    r"\bopen for work\b",
    r"\bopen for (?:new )?opportunities\b",
    r"\bavailable for work\b",
    r"\bavailable for hire\b",
    r"\blooking for (?:my|a new|a next|new|any)\s+(?:role|job|opportunity|opportunities|challenge|position|gig)\b",
    r"\bseeking (?:my|a new|a next|new)\s+(?:opportunity|opportunities|job|role|position|challenge)\b",
    r"\bseeking (?:full-time|part-time|contract|freelance|remote) (?:roles?|opportunities|positions?|work)\b",
    r"\bopen to (?:new |remote |immediate )?(?:roles?|opportunities|positions?|offers?|work)\b",
    r"\blooking for (?:a |new )?(?:job|work|employment)\b",
    r"\bin the job market\b",
    r"\bback in the job market\b",
    r"\bon the job market\b",
    r"\bin search of (?:my|a new|a next|new)\s+(?:opportunity|opportunities|job|role)\b",
    r"\b(?:i am|i'm|currently)\s+(?:actively\s+)?(?:looking|seeking|searching)\s+(?:for\s+)?(?:a\s+)?(?:new\s+)?(?:job|opportunity|opportunities|role|position|work)\b",
    r"\bunfortunately\s+(?:i\s+was|i've\s+been)\s+(?:laid\s+off|impacted\s+by\s+layoffs)\b",
    r"\bimpacted by (?:the\s+)?(?:recent\s+)?layoffs\b",
    r"\bwas laid off\b",
    r"\bmy resume is attached\b",
    r"\bplease find my (?:resume|cv) attached\b",
    r"\bhire me\b",
    r"\bhire\s+myself\b",
    r"\bopen to (?:full-time|part-time|contract|freelance) roles\b",
    r"\bconnect with me for (?:any\s+)?opportunities\b",
    r"\bif you have any leads\b",
    r"\bplease refer me\b",
    r"\blooking for referrals\b",
    r"\bfeel free to reach out (?:to me )?for (?:opportunities|roles|openings)\b",
    r"\bi(?:'m| am) (?:a\s+)?(?:fresher|graduate|student|candidate|job seeker)\b",
    r"\bready to take on (?:new |my next )?challenges?\b",
    r"\bready for my next (?:adventure|role|opportunity|step|chapter)\b",
    r"\bseeking my next (?:adventure|role|opportunity|step|chapter)\b",
    r"\blooking for my next (?:adventure|role|opportunity|step|chapter)\b",
    r"\bto anyone in my network\b",
    r"\bto my (?:linkedin\s+)?network\b",
    r"\bhelp me find (?:my next|a)\b",
    r"\bany recommendations or leads\b",
    r"\bany leads or referrals\b",
    r"\bopen to connect with recruiters\b",
    r"\breach out if you have (?:any\s+)?(?:openings?|roles?|opportunities)\b",
    r"\bdm me if you have (?:any\s+)?(?:openings?|roles?|opportunities)\b",
    r"(?:^|\W)#?cfbr\b",
    r"\bcomment for better reach\b",
    r"\bboost this post\b",
    r"\bplease repost\b",
    r"\bplease reshare\b",
    r"\brepost for reach\b",
    r"\breshare for reach\b",

    # B) Personal transitions, relocation, milestones (e.g. took the leap, relocated)
    r"\b(?:took|take|taking)\s+the\s+leap\b",
    r"\bdecided to take the opportunity\b",
    r"\bleft many things behind\b",
    r"\bany experience is good experience\b",
    r"\blooking forward to (?:learn|contribute|working|starting|connecting|join|be part|grow)\b",
    r"\bchance to experience\b",
    r"\btom[eé] el salto\b",
    r"\bdecid[ií] tomar la oportunidad\b",
    r"\bespero poder (?:aprender|ayudar|trabajar)\b",
    r"\bdej[eé] muchas cosas\b",
    r"\bcualquier experiencia es buena\b",

    # C) Freelance self-promotion (developers looking for clients, not hiring)
    r"\bavailable for (?:freelance|contract|consulting|gigs)\b",
    r"\bcontact me if you need (?:a|an)\b",
    r"\bhire me for\b",
    r"\bcheck out my (?:portfolio|github|projects?)\b",
    r"\bfeel free to reach out for (?:projects?|freelance)\b",
    r"\bi am a (?:freelance|freelancer)\b",

    # D) Thought Leadership, Interview Tips & Career Advice
    r"\bhere are\s+\d+\s+tips\b",
    r"\b\d+\s+tips to (?:ace|pass|crack|prepare for)\b",
    r"\bhow to (?:ace|pass|crack|prepare for) (?:your |an )?(?:interview|technical interview)\b",
    r"\binterview tips for\b",
    r"\bsecrets to getting hired\b",
    r"\bwhy most (?:candidates|recruiters|developers) fail\b",
    r"\bmy (?:journey|thoughts|take) on (?:leadership|management|career|agile)\b",
    r"\blessons i learned (?:as|from|while)\b",

    # E) Courses, Bootcamps, Training & Webinars Sales
    r"\benroll (?:now|today)\b",
    r"\bjoin our (?:masterclass|webinar|bootcamp|workshop|training program)\b",
    r"\bregister for (?:free|our upcoming)\b",
    r"\bfree webinar\b",
    r"\bcourse fee\b",
    r"\bflat \d+% off\b",
    r"\buse code [A-Z0-9]+\b",
    r"\blearn [a-z\s]+ from scratch\b",
    r"\b100% placement (?:guarantee|assistance)\b",
    r"\bbatch starts (?:from|on)\b",
    r"\blimited seats\b",

    # F) Personal updates, Work Anniversaries & Celebrations
    r"\bcelebrating\s+\d+\s+years? (?:at|with)\b",
    r"\bexcited to (?:share|announce) that (?:i have|i've|i am|i'm)\s+(?:joined|started|accepted)\b",
    r"\bhappy to (?:share|announce) that (?:i'm|i am) starting (?:a|my) new position\b",
    r"\bthrilled to announce that i (?:joined|am starting)\b",
    r"\bstarting my new (?:journey|chapter|role|position) at\b",
    r"\bproud to announce that i was promoted\b",
    r"\bhappy work anniversary\b",
]

POSITIVE_HIRING_PATTERNS = [
    # English direct hiring
    r"\bwe(?:'re| are|\s+are)\s+(?:actively\s+|urgently\s+)?#?hiring\b",
    r"\bi(?:'m| am|\s+am)\s+(?:actively\s+|urgently\s+)?#?hiring\b",
    r"\b(?:actively|urgently|currently|now)\s+#?hiring\b",
    r"\bhiring\s+(?:alert|surge|spree|immediately|urgently)\b",
    r"(?:^|\W)#(?:hiring|nowhiring|hiringalert|jobopening|jobvacancy|recruitment|recruiting|wearehiring)\b",
    r"\burgent\s+(?:hiring|requirement|opening|vacancy|need)\b",
    r"\bimmediate\s+(?:requirement|opening|vacancy|joiner required|joiner|need)\b",
    r"\bjoin our\s+(?:team|engineering team|tech team|company|startup|firm)\b",
    r"\bjoin us\b",
    r"\bour team is\s+(?:growing|expanding|hiring)\b",
    r"\bwe are (?:looking for|seeking|expanding)\b",
    r"\blooking for\s+(?:a|an|\d+)?\s*(?:senior|junior|lead|staff|principal|mid-level|experienced)?\s*[a-zA-Z\s]+(?:developer|engineer|designer|manager|specialist|lead|architect|consultant|analyst)\b",
    r"\blooking to hire\b",
    r"\bopen (?:position|positions|role|roles|vacancy|vacancies)\b",
    r"\bjob (?:opening|openings|alert|vacancy|vacancies)\b",
    r"\bcareer opportunities at\b",
    r"\bhiring for the role of\b",
    r"\bhiring for\b",
    r"\bwe have an? (?:opening|opportunity|open role) for\b",
    
    # Calls to action from hirers
    r"\b(?:send|email|share|drop|forward|mail)\s+(?:your\s+)?(?:resume|cv|profile|portfolio|details)\s+(?:to|at|via|on)\b",
    r"\bapply\s+(?:here|at|via|now|through|link)\b",
    r"\binterested\s+(?:candidates|applicants|folks|professionals)?\s*(?:can|please)?\s*(?:send|email|share|dm|reach)\b",
    r"\bdrop your (?:resume|cv|email|profile)\b",
    r"\breach out to (?:me|us) (?:at|via)\b",
    r"\bemail me (?:at|your)\b",
    r"\bdm (?:me|your cv|your resume|for details)\b",
    r"\bshare your updated (?:cv|resume)\b",
    r"\bmultiple positions? (?:open|available)\b",
    r"\bcareers?@\b",
    r"\bjobs?@\b",
    r"\btalent@\b",
    r"\brecruitment@\b",
    r"\bhr@\b",

    # German
    r"\bwir suchen\b",
    r"\bstellenangebot\b",
    r"\boffene stelle\b",
    r"\bkarriere bei\b",
    r"\bbewerben sie sich\b",
    r"\bbewerbung an\b",
    r"\bverstärkung für unser team\b",

    # French
    r"\b(?:nous\s+)?recrutons\b",
    r"\brecrutement\b",
    r"\boffre d'emploi\b",
    r"\bposte à pourvoir\b",
    r"\benvoyez votre (?:cv|candidature)\b",
    r"\bpartagez votre cv\b",
    r"\brejoignez notre équipe\b",

    # Spanish
    r"\bestamos contratando\b",
    r"\bvacante abierta\b",
    r"\bbúsqueda laboral\b",
    r"\benviar cv\b",
    r"\binteresados enviar\b",
    r"\búnete a nuestro equipo\b",

    # Arabic / Gulf
    r"\bمطلوب\b",
    r"\bوظيفة شاغرة\b",
    r"\bفرصة عمل\b",
    r"\bإرسال السيرة الذاتية\b",
    r"\bنحن نوظف\b",

    # Italian
    r"\bstiamo assumendo\b",
    r"\bofferta di lavoro\b",
    r"\binviare cv\b",
    r"\bposizione aperta\b",

    # Portuguese
    r"\bestamos contratando\b",
    r"\bestamos a recrutar\b",
    r"\bvaga aberta\b",
    r"\benvie seu (?:cv|currículo)\b",

    # Dutch
    r"\bwij zoeken\b",
    r"\bvacature\b",
    r"\bsolliciteer nu\b",
    r"\bstuur je cv\b",
]

COMPILED_NON_RECRUITMENT = [re.compile(p, re.I) for p in NON_RECRUITMENT_PATTERNS]
COMPILED_POSITIVE_HIRING = [re.compile(p, re.I) for p in POSITIVE_HIRING_PATTERNS]

UNAMBIGUOUS_JOB_SEEKER_PATTERNS = [
    r"(?:^|\W)#?opentowork\b",
    r"\bopen to work\b",
    r"\bopen for work\b",
    r"\bavailable for work\b",
    r"\bavailable for hire\b",
    r"\bhire me\b",
    r"\bhire\s+myself\b",
    r"\b(?:i am|i'm|currently)\s+(?:actively\s+)?(?:looking|seeking|searching)\s+(?:for\s+)?(?:a\s+)?(?:new\s+)?(?:job|opportunity|role|position|work)\b",
    r"\bimpacted by (?:the\s+)?(?:recent\s+)?layoffs\b",
    r"\bwas laid off\b",
    r"\bmy resume is attached\b",
    r"\bplease find my (?:resume|cv) attached\b",
    r"\b100% placement (?:guarantee|assistance)\b",
    r"\bcourse fee\b",
    r"\buse code [A-Z0-9]+\b",
    r"\bhappy work anniversary\b",
    r"\bcelebrating\s+\d+\s+years? (?:at|with)\b",
]
COMPILED_SNIPPET_DISQUALIFIED = [re.compile(p, re.I) for p in UNAMBIGUOUS_JOB_SEEKER_PATTERNS]

def is_snippet_unambiguously_disqualified(text: str) -> bool:
    """Fast pre-screening check that drops search snippets that are definitively job seekers, spam, or login-wall boilerplate."""
    if not text:
        return False
    if is_linkedin_boilerplate(text):
        return True
    lower_t = text.lower()
    for pattern in COMPILED_SNIPPET_DISQUALIFIED:
        if pattern.search(lower_t):
            return True
    return False

def analyze_recruitment_intent(text: str, author_headline: str = "", extra_context: str = "") -> Tuple[bool, str, List[str]]:
    """
    Analyzes post content, headline, and extra metadata to verify genuine recruitment/hiring intent.
    Strictly filters out LinkedIn login-wall boilerplate, job seekers (#OpenToWork), thought leadership, courses, and celebrations.
    Returns: (is_recruitment: bool, reason: str, detected_signals: List[str])
    """
    cleaned_text = clean_linkedin_boilerplate(text or "")
    cleaned_extra = clean_linkedin_boilerplate(extra_context or "")
    if not cleaned_text and not cleaned_extra:
        return False, "LinkedIn login-wall boilerplate or empty content", []

    combined = f"{cleaned_text} {author_headline or ''} {cleaned_extra}".strip().lower()
    if not combined or len(combined) < 20:
        return False, "Post content too short or empty", []

    # Step 1: Disqualify negative patterns
    for pattern in COMPILED_NON_RECRUITMENT:
        m = pattern.search(combined)
        if m:
            matched_phrase = m.group(0)
            return False, f"Disqualified: non-recruitment pattern '{matched_phrase}'", []

    # Step 2: Detect positive hiring signals
    detected_signals = []
    for pattern in COMPILED_POSITIVE_HIRING:
        m = pattern.search(combined)
        if m:
            detected_signals.append(m.group(0).strip())

    # Apply link or career link check
    has_apply_link = bool(re.search(r"https?://[^\s]+(?:apply|job|career|lever\.co|greenhouse\.io|workday|ashbyhq\.com|bamboohr\.com)", cleaned_text, re.I))
    if has_apply_link:
        detected_signals.append("direct_apply_link")

    # Author headline check
    recruiter_headline = bool(re.search(r"\b(recruiter|talent acquisition|hiring manager|head of talent|technical recruiter|hr manager|lead recruiter|sourcer|hrbp|people operations)\b", author_headline or "", re.I))
    if recruiter_headline:
        detected_signals.append("recruiter_author")

    # Relaxed check for search engine snippet / URL slug results
    if not detected_signals:
        hiring_words = [
            "hiring", "we're hiring", "we are hiring", "join our team", "open role",
            "open position", "vacancy", "job opening", "send cv", "send your cv",
            "send resume", "share your cv", "share your resume", "poste à pourvoir",
            "recrutons", "recrutement", "offre d'emploi", "looking for a", "looking for an",
            "new job opportunity", "job opportunity", "nous recherchons", "recherche un",
            "besoin d'un", "apply here", "apply now", "experience required", "years experience",
            "immediate joiner", "remote role", "contract role", "freelance", "apply:",
        ]
        if any(w in combined for w in hiring_words):
            detected_signals.append("verified_hiring_keyword")

    if not detected_signals:
        return False, "No verified hiring or recruitment signals found in post", []

    return True, "Verified genuine recruitment post", detected_signals

ROLE_DOMAIN_KEYWORDS = {
    "flutter": ["flutter", "flutterdeveloper", "flutterdev", "dart", "mobiledev", "mobiledevelopment", "appdeveloper", "crossplatform", "ios", "android"],
    "react": ["react", "reactjs", "frontend", "frontenddeveloper", "javascript", "typescript", "webdev", "fullstack", "nextjs"],
    "python": ["python", "pythondeveloper", "django", "fastapi", "backend", "backenddeveloper", "datascience", "machinelearning", "ai"],
    "java": ["java", "springboot", "javadeveloper", "backend", "microservices", "spring", "backenddeveloper"],
    "node": ["nodejs", "node", "backend", "javascript", "typescript", "expressjs", "fullstack"],
    "angular": ["angular", "angularjs", "frontend", "typescript", "javascript", "webdev"],
    "vue": ["vue", "vuejs", "frontend", "javascript", "webdev"],
    "golang": ["golang", "go", "backend", "cloud", "microservices", "backenddeveloper"],
    "rust": ["rust", "rustlang", "backend", "systems", "webassembly"],
    "ios": ["ios", "iosdeveloper", "swift", "swiftui", "mobiledev", "appdeveloper", "apple"],
    "android": ["android", "androiddeveloper", "kotlin", "mobiledev", "appdeveloper"],
    "devops": ["devops", "cloud", "aws", "kubernetes", "docker", "sre", "cicd", "infrastructure", "azure", "gcp"],
    "data": ["dataengineer", "datascience", "machinelearning", "ai", "deeplearning", "analytics", "bigdata", "python", "sql"],
    "ml": ["machinelearning", "ai", "deeplearning", "datascience", "genai", "llm", "computervision", "nlp"],
    "ai": ["ai", "artificialintelligence", "machinelearning", "genai", "deeplearning", "llm", "datascience"],
    "qa": ["qa", "qualityassurance", "tester", "automationtesting", "selenium", "softwaretester", "qajobs"],
    "product": ["productmanager", "product", "pm", "productowner", "techjobs"],
    "design": ["uiux", "productdesigner", "uxdesigner", "uidesigner", "figma", "designjobs"],
    "security": ["cybersecurity", "infosec", "security", "securityengineer", "ethicalhacking"],
    "blockchain": ["blockchain", "web3", "crypto", "smartcontracts", "solidity"],
    "fullstack": ["fullstack", "fullstackdeveloper", "softwareengineer", "developer", "techjobs"]
}

DISQUALIFIED_NON_TECH_OCCUPATIONS = [
    r"\b(?:truck|cdl|delivery|uber|taxi)\s+(?:driver|driving)\b",
    r"\b(?:registered nurse|nurse practitioner|caregiver|phlebotomist|dental hygienist)\b",
    r"\b(?:dishwasher|bartender|barista|kitchen staff|line cook)\b",
    r"\b(?:housekeeper|housekeeping|maid|babysitter|nanny)\b",
    r"\b(?:security guard|bouncer)\b",
    r"\b(?:plumber|electrician|carpenter|painter|welder|construction worker)\b",
    r"\b(?:cashier|grocery clerk|shelf stocker)\b"
]
COMPILED_NON_TECH_OCCUPATIONS = [re.compile(p, re.I) for p in DISQUALIFIED_NON_TECH_OCCUPATIONS]

def _clean_extracted_role_title(raw_title: str, fallback_role: str) -> str:
    """Cleans a candidate role title by stripping trailing sentences, emojis, and punctuation."""
    if not raw_title:
        return fallback_role
    # Stop at sentence boundaries, emojis, pipes, dashes, or common trailing clauses
    t = re.split(r"[!?\n\r|•🚀🔥✨💼🏢📍]|(?:\s+[-–—]\s+)", raw_title)[0].strip()
    t = re.split(
        r"(?i)\b(?:we\s+are|we're|were|who\s+|with\s+\d|to\s+join|is\s+looking|are\s+looking|is\s+hiring|are\s+you|at\s+[A-Z]|in\s+[A-Z]|for\s+our)\b",
        t,
    )[0].strip()
    t = re.sub(r"^(?:a|an|the|talented|passionate|skilled|experienced|motivated)\s+", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:and|&\s*)\s*(?:motivated|passionate|skilled|experienced)\s+", "", t, flags=re.I).strip()
    t = t.strip(" :,-–—.;!()")
    if 3 <= len(t) <= 45 and not any(kw in t.lower() for kw in ("http", "apply", "please", "email", "resume", "cv")):
        return t
    return fallback_role


def extract_accurate_job_title(text: str, fallback_role: str) -> str:
    """
    Extracts explicit job title declarations from post text.
    e.g. 'Hiring: Senior Frontend React Engineer' -> 'Senior Frontend React Engineer'
    """
    if not text:
        return fallback_role

    patterns = [
        r"(?:we(?:'re|\s+are)\s+hiring|hiring\s+alert|hiring\s+for(?:the\s+role\s+of)?|open\s+role|position|job\s+title|role)\s*[:\-–—|]\s*([^\n\r!?.|🚀🏢💼]{3,50})",
        r"(?:looking\s+for\s+(?:a|an)\s+|seeking\s+(?:a|an)\s+|hiring\s+(?:a|an)\s+)([A-Za-z0-9\s/+#\.\-]{3,40}?(?:developer|engineer|designer|manager|specialist|lead|architect|consultant|analyst))\b",
        r"\b((?:Senior|Junior|Lead|Mid-Level|Principal|Staff|Frontend|Backend|Full\s*Stack|Mobile)\s+[A-Za-z0-9\s/+#\.\-]{2,30}?(?:Developer|Engineer|Designer|Manager|Architect))\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            cleaned = _clean_extracted_role_title(m.group(1), "")
            if cleaned and len(cleaned) >= 4:
                return cleaned
    return fallback_role

CONFLICTING_ROLE_DISCIPLINES: Dict[str, Tuple[str, ...]] = {
    "ui_ux": ("ui/ux", "ux designer", "ui designer", "graphic designer", "product designer", "visual designer", "figma designer"),
    "qa_testing": ("qa engineer", "quality assurance", "software tester", "manual tester", "automation tester", "sdet", "test engineer", "qa analyst"),
    "devops_infra": ("devops engineer", "site reliability", "sre", "cloud architect", "system administrator", "sysadmin", "network engineer"),
    "data_science": ("data scientist", "data analyst", "power bi", "tableau developer", "data engineer", "bi developer"),
    "product_mgmt": ("product manager", "scrum master", "agile coach", "project manager", "business analyst", "product owner"),
    "sales_hr_mkt": ("business development", "sales executive", "account executive", "digital marketing", "seo specialist", "hr manager", "talent acquisition", "recruiter"),
    "erp_crm": ("sap consultant", "salesforce developer", "abap", "servicenow", "odoo developer", "dynamics 365", "oracle erp"),
}

LAUNDRY_LIST_ROLE_FAMILIES: Tuple[str, ...] = (
    r"\bjava\b", r"\bpython\b", r"\bflutter\b", r"\breact\b", r"\bangular\b", r"\bvue\b",
    r"\b\.net\b|\bdotnet\b", r"\bgolang\b", r"\bruby\b", r"\bphp\b|\blaravel\b", r"\bsalesforce\b",
    r"\bsap\b", r"\bdevops\b", r"\bqa\b|\btester\b", r"\bui/ux\b|\bux designer\b", r"\bdata engineer\b",
    r"\bscrum master\b", r"\bbusiness analyst\b", r"\bios\b|\bswift\b", r"\bandroid\b|\bkotlin\b",
)


def check_role_and_skill_fit(
    full_text: str,
    author_headline: str,
    clean_role: str,
    tags: Optional[List[str]] = None,
    post_tags: Optional[List[str]] = None
) -> Tuple[bool, int, List[str], str]:
    """
    Verifies that a LinkedIn post genuinely fits the requested job role and skills.
    1. Disqualifies occupational mismatches (e.g. drops driver/nurse posts when searching tech).
    2. Verifies Primary Role vs. Mentioned Keyword (rejects UI/UX, QA, BA, etc. when user searches a dev stack).
    3. Detects and penalizes Multi-Role "Laundry-List" posts (5+ unrelated roles in one post).
    4. Measures semantic skill overlap and extracts the actual declared job title.
    Returns: (is_relevant: bool, fit_score: int, matched_skills: List[str], clean_title: str)
    """
    combined_text = (full_text + " " + (author_headline or "")).lower()
    role_lower = clean_role.lower().strip()

    # Check if user specifically requested a non-tech role
    is_tech_search = not any(kw in role_lower for kw in ("driver", "nurse", "cook", "cleaner", "guard", "worker", "cashier", "plumber"))

    # 1. Occupational Disqualification
    if is_tech_search:
        for pattern in COMPILED_NON_TECH_OCCUPATIONS:
            if pattern.search(combined_text):
                return False, 0, [], clean_role

    # 2. Gather relevant domain skills for target role
    target_skills = set()
    for kw, skills_list in ROLE_DOMAIN_KEYWORDS.items():
        if kw in role_lower:
            target_skills.update(skills_list)

    # Extract role tokens & core technology/specialty tokens
    generic_role_words = {"the", "and", "for", "with", "all", "job", "jobs", "role", "developer", "engineer", "software", "senior", "junior", "lead", "mid", "full", "stack", "specialist", "consultant", "manager"}
    role_tokens = [w for w in re.findall(r"[a-zA-Z0-9+#]+", role_lower) if len(w) >= 2 and w not in ("the", "and", "for", "with", "all", "job", "jobs", "role")]
    core_specialty_tokens = [w for w in role_tokens if w not in generic_role_words]
    target_skills.update(role_tokens)

    # 3. Extract the declared job title from the post and verify Primary Role vs. Mentioned Keyword
    extracted_title = extract_accurate_job_title(full_text, clean_role)
    extracted_title_lower = (extracted_title or "").lower()

    # Determine which disciplines the user's query itself belongs to
    user_disciplines = set()
    for disc_name, disc_keywords in CONFLICTING_ROLE_DISCIPLINES.items():
        if any(dk in role_lower or any(tok in dk.split() for tok in core_specialty_tokens) for dk in disc_keywords):
            user_disciplines.add(disc_name)

    # Check if the extracted title belongs to a conflicting discipline and lacks the user's core specialty token
    has_core_in_title = any(tok in extracted_title_lower for tok in core_specialty_tokens) if core_specialty_tokens else True
    if not has_core_in_title:
        for disc_name, disc_keywords in CONFLICTING_ROLE_DISCIPLINES.items():
            if disc_name in user_disciplines:
                continue
            if any(dk in extracted_title_lower for dk in disc_keywords):
                # Primary role being hired is a conflicting discipline (e.g., UI/UX Designer when searching Flutter)
                return False, 0, [], clean_role

        # Also check first 200 chars of post for explicit single-role headline mismatch
        opening_window = (full_text or "")[:200].lower()
        if core_specialty_tokens and not any(tok in opening_window for tok in core_specialty_tokens):
            for disc_name, disc_keywords in CONFLICTING_ROLE_DISCIPLINES.items():
                if disc_name in user_disciplines:
                    continue
                if any(dk in opening_window for dk in disc_keywords):
                    return False, 0, [], clean_role

    # 4. Match skills in post text
    matched_skills = []
    for skill in sorted(target_skills, key=lambda s: -len(s)):
        skill_re = re.compile(rf"\b{re.escape(skill)}\b", re.I)
        if skill_re.search(combined_text):
            if skill not in matched_skills and skill not in ("developer", "engineer", "software", "tech"):
                matched_skills.append(skill)

    # 5. Check direct role presence
    exact_role_in_post = role_lower in combined_text
    core_token_in_post = any(re.search(rf"\b{re.escape(tok)}\b", combined_text) for tok in core_specialty_tokens) if core_specialty_tokens else exact_role_in_post

    # If the user searched for a specific technology/specialty (e.g. "flutter", "react", "golang")
    # and the post doesn't even contain that core token or any domain skill, reject it
    if core_specialty_tokens and not core_token_in_post and len(matched_skills) == 0:
        return False, 0, [], clean_role

    # 6. Fit Score calculation (granularity across role match, ecosystem skills, seniority, and post detail)
    non_role_skills = [s for s in matched_skills if s.lower() not in role_tokens]
    fit_score = 54  # baseline
    if exact_role_in_post:
        fit_score += 16
    elif core_token_in_post:
        fit_score += 12
    elif any(tok in combined_text for tok in role_tokens):
        fit_score += 7

    if core_specialty_tokens and any(tok in extracted_title_lower for tok in core_specialty_tokens):
        fit_score += 6  # Bonus when the primary extracted title explicitly contains the core specialty

    # Ecosystem / complementary technical skills (excluding the searched role word itself)
    fit_score += min(len(non_role_skills) * 5, 18)

    # Post detail depth bonus (reward detailed job descriptions over 1-line blurbs)
    word_count = len((full_text or "").split())
    if word_count >= 120:
        fit_score += 4
    elif word_count >= 60:
        fit_score += 2
    elif word_count < 25:
        fit_score -= 4

    # Seniority / heavy experience requirement penalty (e.g. "5+ Years", "7+ years", "Senior/Lead")
    req_years = extract_post_required_years(full_text or "")
    if req_years is not None:
        if req_years >= 6:
            fit_score -= 9
        elif req_years >= 4:
            fit_score -= 5
        elif req_years <= 2:
            fit_score += 3
    elif re.search(r"\b(senior|sr\.?|lead|principal|staff|architect)\b", extracted_title_lower):
        fit_score -= 4

    # 7. Multi-Role "Laundry-List" Detection & Penalty
    distinct_families = sum(1 for pat in LAUNDRY_LIST_ROLE_FAMILIES if re.search(pat, full_text or "", re.I))
    bulleted_roles = re.findall(
        r"(?:^|\n)\s*(?:\d+[\.\)]|[•✅👉🔹▪-])\s*[A-Za-z0-9 /+#.\-]{3,40}(?:developer|engineer|designer|analyst|manager|consultant|architect|tester)\b",
        full_text or "",
        re.I,
    )
    if distinct_families >= 5 or len(bulleted_roles) >= 5:
        fit_score = max(35, fit_score - 18)
        # If it's a massive laundry list, override the extracted title to the user's searched role if present
        if core_token_in_post:
            extracted_title = clean_role

    fit_score = min(max(fit_score, 30), 98)

    # 8. Relevance Threshold
    if role_tokens and len(matched_skills) == 0 and not exact_role_in_post and not core_token_in_post:
        return False, 0, [], clean_role

    return True, fit_score, matched_skills[:6], extracted_title


def classify_author_authority(author_name: str, author_headline: str, post_url: str = "") -> Tuple[str, int]:
    """
    Classifies the post author's authority to distinguish real human recruiters / hiring managers
    from automated job-board repost pages (e.g., Jobsera, Daily Jobs).
    Returns: (authority_type: str, score_delta: int)
    """
    name_low = (author_name or "").lower().strip()
    head_low = (author_headline or "").lower().strip()
    combined = f"{name_low} {head_low}"

    bot_keywords = (
        "jobsera", "jobs near you", "fresher jobs", "job alerts", "daily jobs",
        "hiring alert", "vacancy alert", "jobs update", "jobs hub", "rozgar",
        "walkin", "off campus", "job openings", "career updates", "jobs portal",
    )
    if any(bk in combined for bk in bot_keywords):
        return "aggregator_bot", -15

    recruiter_keywords = (
        "talent acquisition", "recruiter", "recruiting", "human resources", "hr ",
        "people operations", "head of people", "cto", "chief technology", "ceo",
        "founder", "co-founder", "vp of engineering", "engineering manager",
        "tech lead", "team lead", "hiring manager", "director of engineering",
        "head of talent", "recrutement", "rh", "chargé de recrutement",
    )
    if any(rk in combined for rk in recruiter_keywords):
        return "human_recruiter", 8

    if "linkedin.com/posts/" in (post_url or "").lower() and name_low and name_low != "linkedin recruiter":
        return "verified_member", 3

    return "member_or_company", 0


def is_supported_post_language(text: str, target_locations: Optional[List[str]] = None) -> bool:
    """
    Filters out posts written in unsupported foreign languages (e.g. Vietnamese, Polish, Turkish, Cyrillic)
    unless the user explicitly targeted that country/region.
    """
    if not text:
        return True
    locs_low = " ".join((target_locations or [])).lower()
    t_low = text.lower()

    # 1. Vietnamese check
    if not any(k in locs_low for k in ("vietnam", "hanoi", "ho chi minh", "da nang")):
        vn_markers = ("đang tìm kiếm", "tuyển dụng", "ứng viên", "việc làm", "liên hệ", "lương", "năm kinh nghiệm", "công ty")
        if any(m in t_low for m in vn_markers) or len(re.findall(r"[ăâđêôơưĂÂĐÊÔƠƯ]", text)) >= 4:
            return False

    # 2. Polish check
    if not any(k in locs_low for k in ("poland", "warsaw", "krakow", "wroclaw")):
        pl_markers = ("szukamy", "rekrutacja", "stanowisko", "doświadczenie", "praca zdalna", "aplikuj")
        if any(m in t_low for m in pl_markers) or len(re.findall(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", text)) >= 5:
            return False

    # 3. Turkish check
    if not any(k in locs_low for k in ("turkey", "istanbul", "ankara", "izmir")):
        tr_markers = ("arıyoruz", "iş ilanı", "başvuru", "özgeçmiş", "deneyimli")
        if any(m in t_low for m in tr_markers) or len(re.findall(r"[ğışĞİŞ]", text)) >= 5:
            return False

    # 4. Cyrillic check (Russian / Ukrainian / Belarusian / Bulgarian)
    if not any(k in locs_low for k in ("russia", "ukraine", "belarus", "bulgaria", "kazakhstan")):
        if len(re.findall(r"[\u0400-\u04FF]", text)) >= 12:
            return False

    return True


def extract_post_required_years(text: str) -> Optional[float]:
    """
    Extracts the minimum years of experience requested in a LinkedIn recruiter post.
    e.g. '1.5 - 3 years of experience' -> 1.5, '5+ years exp' -> 5.0
    """
    if not text:
        return None
    patterns = [
        r"\b(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?|ans?)\b",
        r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?|ans?)\s+(?:of\s+)?(?:hands-on\s+|relevant\s+|professional\s+)?(?:experience|exp|d'expérience)\b",
        r"(?:experience|exp|expérience)\s*[:\-–—|]\s*(\d+(?:\.\d+)?)\s*(?:\+|years?|yrs?|ans?)",
        r"\bminimum\s+(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                val = float(m.group(1))
                if 0.5 <= val <= 20.0:
                    return val
            except Exception:
                pass
    return None


FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "protonmail.com", "live.com", "aol.com", "ymail.com", "zoho.com",
    "gmx.com", "mail.com", "msn.com", "rediffmail.com",
}

ROLE_EMAIL_PREFIXES = {
    "hr", "careers", "career", "jobs", "job", "talent", "recruiting",
    "recruitment", "info", "contact", "apply", "cv", "resume", "hiring",
    "people", "hello", "join", "work", "team", "admin", "office", "recrutement",
    "engineering", "dev", "tech", "it", "support", "sales", "marketing",
}


def classify_recruiter_email_tier(email: str, source: str = "post_body") -> Dict[str, Any]:
    """
    Classifies a verified recruiter email into explicit quality tiers:
      - Tier 1 ('direct_corporate'): Named person at corporate domain (98% confidence)
      - Tier 2 ('role_corporate'): Official hiring/HR inbox at corporate domain (92% confidence)
      - Tier 3 ('freemail_recruiter'): Explicit recruiter Gmail/Outlook from post (78% confidence)
    """
    em_low = (email or "").strip().lower()
    if "@" not in em_low:
        return {"tier": "unknown", "tier_rank": 4, "confidence": 50, "badge": "Unverified"}

    local_part, domain_part = em_low.split("@", 1)
    prefix_clean = re.sub(r"[^a-z]", "", local_part.split(".")[0].split("_")[0].split("-")[0])

    if domain_part in FREE_EMAIL_DOMAINS:
        return {
            "tier": "freemail_recruiter",
            "tier_rank": 3,
            "confidence": 78,
            "badge": "Personal Recruiter Email",
        }

    if local_part in ROLE_EMAIL_PREFIXES or prefix_clean in ROLE_EMAIL_PREFIXES:
        return {
            "tier": "role_corporate",
            "tier_rank": 2,
            "confidence": 92,
            "badge": "Official Hiring Inbox",
        }

    return {
        "tier": "direct_corporate",
        "tier_rank": 1,
        "confidence": 98,
        "badge": "Direct Named Recruiter",
    }


def unroll_linkedin_shortlinks(text: str, blacklisted_set: Set[str]) -> Dict[str, Any]:
    """
    Resolves up to 2 https://lnkd.in/... shortlinks found inside a post or its comments
    to uncover the real external application URL, corporate domain, or mailto: email.
    """
    result: Dict[str, Any] = {
        "external_apply_url": "",
        "company_domain": "",
        "emails": [],
    }
    if not text or "lnkd.in/" not in text:
        return result

    shortlinks = list(dict.fromkeys(re.findall(r"https?://lnkd\.in/[A-Za-z0-9_-]{5,15}", text)))[:2]
    for sl in shortlinks:
        try:
            r = _POST_SESSION.get(
                sl,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                allow_redirects=False,
                timeout=2.2,
                verify=False,
            )
            dest = (r.headers.get("Location") or "").strip()
            if not dest and r.status_code == 200 and r.text:
                # LinkedIn external link interstitial page stores destination href in anchor tag
                m_dest = re.search(r'href="(https?://(?!(?:www\.)?linkedin\.com|lnkd\.in)[^"]+)"', r.text, re.I)
                if not m_dest:
                    m_dest = re.search(r'href="(mailto:[^"]+)"', r.text, re.I)
                if m_dest:
                    dest = m_dest.group(1).strip()

            if not dest:
                continue

            if dest.lower().startswith("mailto:"):
                em_cand = dest[7:].split("?")[0].strip().lower()
                is_valid, _ = verify_recruiter_email_strictly(em_cand, blacklisted_set)
                if is_valid and em_cand not in result["emails"]:
                    result["emails"].append(em_cand)
            elif dest.startswith("http") and "linkedin.com" not in dest.lower() and "lnkd.in" not in dest.lower():
                if not result["external_apply_url"]:
                    result["external_apply_url"] = dest
                parsed = urllib.parse.urlparse(dest)
                host = (parsed.netloc or "").lower().lstrip("www.")
                if host and "." in host and host not in FALSE_DOMAINS and not any(
                    ats in host for ats in ("forms.gle", "docs.google.com", "bit.ly", "tinyurl.com", "linktr.ee")
                ):
                    if not result["company_domain"]:
                        result["company_domain"] = host
        except Exception:
            pass

    return result


INVALID_COMPANY_NAMES = {
    "we", "i", "our", "my", "us", "you", "the", "this", "that", "here", "now",
    "were", "we're", "im", "i'm", "looking", "seeking", "hiring", "team",
    "our team", "hiring team", "tech company", "hiring company", "linkedin recruiter",
    "stealth", "confidential", "recruiter", "unknown", "company", "client",
    "were looking for", "we are looking", "we are hiring", "currently", "actively",
    "urgently", "remote", "full time", "full-time", "contract", "freelance",
}


def _is_valid_company_candidate(cand: str) -> bool:
    if not cand:
        return False
    c_clean = cand.strip(" ,.:;-–—|!").lower()
    if len(c_clean) < 3 or len(c_clean) > 35:
        return False
    if c_clean in INVALID_COMPANY_NAMES:
        return False
    first_word = c_clean.split()[0]
    if first_word in ("we", "we're", "were", "i", "i'm", "our", "my", "the", "this", "a", "an", "looking", "hiring", "seeking", "urgent", "immediate"):
        return False
    if any(phrase in c_clean for phrase in ("looking for", "hiring for", "are hiring", "is hiring", "join our", "apply now", "send your", "years of")):
        return False
    return True


_DDGS_SEMAPHORE = threading.Semaphore(8)

COUNTRY_LINKEDIN_SUBDOMAINS: Dict[str, str] = {
    "france": "fr.linkedin.com/posts",
    "paris": "fr.linkedin.com/posts",
    "lyon": "fr.linkedin.com/posts",
    "morocco": "ma.linkedin.com/posts",
    "maroc": "ma.linkedin.com/posts",
    "casablanca": "ma.linkedin.com/posts",
    "rabat": "ma.linkedin.com/posts",
    "uae": "ae.linkedin.com/posts",
    "united arab emirates": "ae.linkedin.com/posts",
    "dubai": "ae.linkedin.com/posts",
    "abu dhabi": "ae.linkedin.com/posts",
    "uk": "uk.linkedin.com/posts",
    "united kingdom": "uk.linkedin.com/posts",
    "london": "uk.linkedin.com/posts",
    "germany": "de.linkedin.com/posts",
    "berlin": "de.linkedin.com/posts",
    "munich": "de.linkedin.com/posts",
    "canada": "ca.linkedin.com/posts",
    "toronto": "ca.linkedin.com/posts",
    "montreal": "ca.linkedin.com/posts",
    "vancouver": "ca.linkedin.com/posts",
    "spain": "es.linkedin.com/posts",
    "madrid": "es.linkedin.com/posts",
    "barcelona": "es.linkedin.com/posts",
    "netherlands": "nl.linkedin.com/posts",
    "amsterdam": "nl.linkedin.com/posts",
    "india": "in.linkedin.com/posts",
    "bangalore": "in.linkedin.com/posts",
    "saudi arabia": "sa.linkedin.com/posts",
    "riyadh": "sa.linkedin.com/posts",
    "qatar": "qa.linkedin.com/posts",
    "doha": "qa.linkedin.com/posts",
    "egypt": "eg.linkedin.com/posts",
    "cairo": "eg.linkedin.com/posts",
    "tunisia": "tn.linkedin.com/posts",
    "belgium": "be.linkedin.com/posts",
    "switzerland": "ch.linkedin.com/posts",
    "italy": "it.linkedin.com/posts",
    "australia": "au.linkedin.com/posts",
    "singapore": "sg.linkedin.com/posts",
    "ireland": "ie.linkedin.com/posts",
}


def fetch_deep_linkedin_postings(
    role_query: str,
    locations: Optional[List[str]] = None,
    limit: int = 60,
    page: int = 1,
    time_range: str = "all"
) -> List[Dict[str, Any]]:
    """
    Harvests authentic LinkedIn recruiter publications and feed posts (linkedin.com/posts and linkedin.com/feed/update).
    Uses multi-engine search (DDGS + rate-limited Brave + Yahoo), country subdomain targeting, hashtag-combo queries,
    recruiter-persona queries, decodes exact Snowflake activity timestamps from URLs, and strips login-wall boilerplate.
    """
    clean_role, parsed_locs = parse_user_query(role_query, locations)
    if not clean_role:
        clean_role = "Software Engineer"

    target_locs = [l.strip() for l in (parsed_locs or []) if l and l.strip().lower() not in ("all", "worldwide", "anywhere")]
    sweep_locs = target_locs if target_locs else [""]

    hiring_phrases = [
        '"we are hiring"',
        '"we\'re hiring"',
        '"hiring"',
        '"now hiring"',
        '"looking for"',
        '"send your cv"',
        '"share your cv"',
        '"send resume"',
        '"job opening"',
        '"open position"',
        '"join our team"',
        '"urgently hiring"',
        '"actively hiring"',
        '"recrutons"',
        '"offre d\'emploi"',
    ]

    role_variants = [clean_role]
    role_lower_chk = clean_role.lower()

    if "node.js" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)node\.js', 'Nodejs', clean_role))
        role_variants.append(re.sub(r'(?i)node\.js', 'Node', clean_role))
    elif "nodejs" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)nodejs', 'Node.js', clean_role))
        role_variants.append(re.sub(r'(?i)nodejs', 'Node', clean_role))

    if "flutter" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)flutter\s*(developer|engineer|dev)?', 'Flutter Engineer', clean_role).strip())
        role_variants.append(re.sub(r'(?i)flutter\s*(developer|engineer|dev)?', 'Flutter', clean_role).strip())
        role_variants.append("Flutter Developer")
        role_variants.append("Flutter")

    if "react" in role_lower_chk and "native" not in role_lower_chk:
        role_variants.append("React.js Developer")
        role_variants.append("React Engineer")
    elif "react native" in role_lower_chk:
        role_variants.append("React Native Engineer")
        role_variants.append("React Native")

    if "developer" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)\bdeveloper\b', 'Engineer', clean_role))
    elif "engineer" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)\bengineer\b', 'Developer', clean_role))

    role_variants = [rv for rv in dict.fromkeys(role_variants) if rv]

    # Build role hashtags and core technology token for high-recall queries
    compact_role_tag = "#" + re.sub(r"[^a-z0-9]", "", role_lower_chk)
    core_words = [w for w in re.findall(r"[a-z0-9.#+]+", role_lower_chk) if w not in ("developer", "engineer", "senior", "junior", "lead", "software", "full", "stack", "frontend", "backend", "mobile")]
    core_skill = core_words[0] if core_words else clean_role
    core_tag = f"#{ re.sub(r'[^a-z0-9]', '', core_skill) }" if core_words else compact_role_tag

    search_tasks: List[Tuple[str, Tuple[int, int, int]]] = []

    # Priority 0: Mix exact role + core skill + Target location + high-signal hiring & email phrases
    # Note: Avoid parenthesized ("A" OR "B") groups on Yahoo as Yahoo's site: parser returns 0 results for them.
    for loc_idx, loc in enumerate(sweep_locs[:3]):
        loc_str = f' "{loc}"' if loc else ''
        loc_unq = f' {loc}' if loc else ''
        search_tasks.append((f'site:linkedin.com/posts {core_skill} hiring{loc_unq}', (0, loc_idx, 0)))
        search_tasks.append((f'site:linkedin.com/posts "{clean_role}" hiring{loc_str}', (0, loc_idx, 1)))
        search_tasks.append((f'site:linkedin.com/posts {core_skill} "send your cv"{loc_unq}', (0, loc_idx, 2)))
        search_tasks.append((f'site:linkedin.com/posts "#wearehiring" {core_skill}{loc_unq}', (0, loc_idx, 3)))
        search_tasks.append((f'site:linkedin.com/posts "#hiring" {core_skill}{loc_unq}', (0, loc_idx, 4)))
        search_tasks.append((f'site:linkedin.com/posts {core_skill} "we are hiring"{loc_unq}', (0, loc_idx, 5)))
        search_tasks.append((f'site:linkedin.com/posts {core_skill} "looking for"{loc_unq}', (0, loc_idx, 6)))
        search_tasks.append((f'site:linkedin.com/posts "{compact_role_tag}" "#hiring"{loc_unq}', (0, loc_idx, 7)))
        search_tasks.append((f'site:linkedin.com/posts {clean_role} "share your cv"{loc_unq}', (0, loc_idx, 8)))
        # Country subdomain queries if location maps to a regional LinkedIn subdomain
        if loc and loc.lower() in COUNTRY_LINKEDIN_SUBDOMAINS:
            subdom = COUNTRY_LINKEDIN_SUBDOMAINS[loc.lower()]
            search_tasks.append((f'site:{subdom} {core_skill} hiring', (0, loc_idx, 1)))
            search_tasks.append((f'site:{subdom} {core_skill} recrutons', (0, loc_idx, 2)))
            search_tasks.append((f'site:{subdom} {clean_role} "looking for"', (0, loc_idx, 3)))
        q_feed = f'site:linkedin.com/feed/update {core_skill} hiring{loc_unq}'
        search_tasks.append((q_feed, (0, loc_idx, 9)))

    # Priority 1: Broad role + hiring queries (worldwide or flexible indexing)
    for p_idx, phrase in enumerate(hiring_phrases[:8]):
        q_ww_unq = f'site:linkedin.com/posts {clean_role} {phrase}'
        search_tasks.append((q_ww_unq, (1, 0, p_idx)))
        q_ww = f'site:linkedin.com/posts "{clean_role}" {phrase}'
        search_tasks.append((q_ww, (1, 0, p_idx + 10)))

    # Priority 2: Role variants + hiring
    for r_idx, r_var in enumerate(role_variants[1:4]):
        search_tasks.append((f'site:linkedin.com/posts {r_var} hiring', (2, r_idx, 0)))
        search_tasks.append((f'site:linkedin.com/posts "{r_var}" hiring', (2, r_idx, 1)))
        search_tasks.append((f'site:linkedin.com/posts {r_var} "we are hiring"', (2, r_idx, 2)))
        search_tasks.append((f'site:linkedin.com/posts {r_var} "send your cv"', (2, r_idx, 3)))

    unique_tasks: List[Tuple[str, Tuple[int, int, int]]] = []
    seen_q = set()
    for q_str, prio in search_tasks:
        if q_str not in seen_q:
            seen_q.add(q_str)
            unique_tasks.append((q_str, prio))

    yahoo_btf = ""
    target_max_age_h: Optional[float] = None
    if time_range in ("24h", "1d", "day", "past-24h"):
        yahoo_btf = "&btf=w"
        target_max_age_h = 48.0  # LinkedIn labels 0-48h as '1d ago'
    elif time_range in ("3d", "past-3d"):
        yahoo_btf = "&btf=w"
        target_max_age_h = 72.0
    elif time_range in ("week", "7d", "1w", "past-week"):
        yahoo_btf = "&btf=m"
        target_max_age_h = 168.0
    elif time_range in ("month", "30d", "1m", "past-month"):
        yahoo_btf = "&btf=m"
        target_max_age_h = 720.0

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    _USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    ]

    try:
        from ddgs import DDGS
        has_ddgs = True
    except ImportError:
        has_ddgs = False

    def fetch_ddgs_query(q: str, tl: Optional[str] = None) -> List[Tuple[str, str, str]]:
        """Primary Yahoo-backed harvester via thread-local DDGS(verify=False) reuse."""
        results_out: List[Tuple[str, str, str]] = []
        if not has_ddgs:
            return results_out
        with _DDGS_SEMAPHORE:
            try:
                ddgs_inst = getattr(_TLS_DDGS, "client", None)
                if ddgs_inst is None:
                    ddgs_inst = DDGS(verify=False)
                    _TLS_DDGS.client = ddgs_inst
                raw_list = list(ddgs_inst.text(q, max_results=15, backend="yahoo", timelimit=tl))
                for item in raw_list:
                    href = (item.get("href") or "").strip()
                    if not href:
                        continue
                    if "linkedin.com/posts" in href or "linkedin.com/feed/update" in href:
                        clean = href.split("?")[0].rstrip("/")
                        if clean.startswith("http") and not any(bad in clean for bad in ("cold-join", "login", "signup", "/jobs/")):
                            title = clean_linkedin_boilerplate(item.get("title") or "")
                            body = clean_linkedin_boilerplate(item.get("body") or "")
                            results_out.append((clean, title, body))
            except Exception:
                _TLS_DDGS.client = None
        return results_out

    def fetch_yahoo_direct_query(q: str, b_offset: int = 1, btf_param: str = "") -> List[Tuple[str, str, str]]:
        """Direct fast Yahoo search harvester that extracts full compText snippets and titles."""
        posts_found: List[Tuple[str, str, str]] = []
        q_enc = urllib.parse.quote(q)
        ua = _USER_AGENTS[b_offset % len(_USER_AGENTS)]
        hdrs = {**headers, "User-Agent": ua}

        try:
            url = f"https://search.yahoo.com/search?p={q_enc}&b={b_offset}{btf_param}"
            if HAS_CURL_CFFI:
                r = c_requests.get(url, impersonate="chrome120", headers=hdrs, timeout=3.2, verify=False)
            else:
                r = _POST_SESSION.get(url, headers=hdrs, timeout=3.2, verify=False)
            if r.status_code == 200 and r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    real_url = extract_yahoo_redirect_url(a["href"])
                    if real_url and real_url not in [p[0] for p in posts_found]:
                        li_parent = a.find_parent("li") or a.find_parent("div", class_=re.compile(r"algo|dd"))
                        comp_text = li_parent.find("div", class_="compText") if li_parent else None
                        title_txt = clean_linkedin_boilerplate(a.get_text(" ", strip=True))
                        snip_txt = clean_linkedin_boilerplate(
                            comp_text.get_text(" ", strip=True) if comp_text else (li_parent.get_text(" ", strip=True) if li_parent else "")
                        )
                        posts_found.append((real_url, title_txt, snip_txt))
        except Exception:
            pass

        return posts_found

    harvested_by_key: Dict[str, Dict[str, Any]] = {}
    safe_page = max(1, page)
    target_harvest = min(max(limit + 15, 35), 55)

    start_idx = ((safe_page - 1) * 8) % max(len(unique_tasks), 1)
    ordered_tasks = unique_tasks[start_idx:] + unique_tasks[:start_idx]
    batch_tasks = ordered_tasks[:12]

    def _ingest_harvest_items(items: List[Tuple[str, str, str]], prio: Tuple[int, int, int]) -> None:
        for u, title_txt, snip_txt in items:
            if not u:
                continue
            clean_u, dedup_key = canonicalize_linkedin_post_url(u)
            if not clean_u or not dedup_key:
                continue

            url_slug_text = extract_url_slug_context(clean_u)
            combined_snip = clean_linkedin_boilerplate(f"{title_txt} {snip_txt}".strip())
            if not combined_snip and url_slug_text:
                combined_snip = url_slug_text

            if combined_snip and is_snippet_unambiguously_disqualified(combined_snip):
                continue

            snow = decode_linkedin_snowflake_age(clean_u)
            age_hours_val = snow["age_hours"] if snow else None

            post_id = generate_stable_post_id(clean_u)
            author_info = parse_author_info_from_url(clean_u, title_hint=title_txt)

            if dedup_key not in harvested_by_key:
                harvested_by_key[dedup_key] = {
                    "id": post_id,
                    "post_url": clean_u,
                    "role_title": clean_role,
                    "author_name": author_info.get("name") or "LinkedIn Recruiter",
                    "company": "",
                    "location": sweep_locs[0] if sweep_locs[0] else "Worldwide",
                    "search_title": title_txt,
                    "snippet": snip_txt or title_txt or url_slug_text,
                    "url_slug_text": url_slug_text,
                    "date_published": snow["date_published"] if snow else None,
                    "age_hours": age_hours_val,
                    "date_str": snow["age_str"] if snow else "Recent",
                    "is_under_24h": snow["is_under_24h"] if snow else False,
                    "source": "linkedin_publication",
                    "_priority": prio,
                }
            else:
                existing = harvested_by_key[dedup_key]
                if len(snip_txt) > len(existing.get("snippet") or ""):
                    existing["snippet"] = snip_txt
                if title_txt and not existing.get("search_title"):
                    existing["search_title"] = title_txt

    future_map = {}
    # Submit top 10 DDGS Yahoo queries + 4 direct Yahoo queries (including time-filtered & page-2 offset)
    for idx, (q_str, prio) in enumerate(batch_tasks[:10]):
        fut_ddg = _HUNTER_POOL.submit(fetch_ddgs_query, q_str, None)
        future_map[fut_ddg] = (prio[0], prio[1], prio[2] + idx)

    if target_max_age_h is not None:
        # Also submit time-bounded month/week queries on unquoted queries for high recency density
        for idx, (q_str, prio) in enumerate(batch_tasks[:3]):
            unq_q = q_str.replace('"', '')
            fut_tl = _HUNTER_POOL.submit(fetch_ddgs_query, unq_q, "m")
            future_map[fut_tl] = (0, prio[1], idx)

    for idx, (q_str, prio) in enumerate(batch_tasks[:3]):
        fut_yh = _HUNTER_POOL.submit(fetch_yahoo_direct_query, q_str, 1, "")
        future_map[fut_yh] = (prio[0], prio[1], prio[2] + idx)
        if yahoo_btf and idx == 0:
            fut_yh_btf = _HUNTER_POOL.submit(fetch_yahoo_direct_query, q_str.replace('"', ''), 1, "&btf=m")
            future_map[fut_yh_btf] = (0, prio[1], 0)

    try:
        for fut in as_completed(future_map.keys(), timeout=4.8):
            try:
                prio = future_map[fut]
                results = fut.result()
                if results:
                    _ingest_harvest_items(results, prio)
            except Exception:
                pass
            # Only stop early if we have enough in-window posts (not just old posts)
            if target_max_age_h is not None:
                in_win_cnt = sum(
                    1 for item in harvested_by_key.values()
                    if item.get("age_hours") is not None and item["age_hours"] <= target_max_age_h
                )
                if in_win_cnt >= min(limit, 20) and len(harvested_by_key) >= target_harvest:
                    break
            elif len(harvested_by_key) >= target_harvest:
                break
    except Exception:
        pass
    finally:
        for fut in future_map:
            if not fut.done():
                fut.cancel()

    # Sort harvested posts:
    # 1. Posts confirmed within target_max_age_h come first
    # 2. Priority tuple
    # 3. Freshest Snowflake age_hours first
    def _harvest_sort_key(item: Dict[str, Any]) -> Tuple[int, Tuple[int, int, int], float, str]:
        age_h = item.get("age_hours")
        if target_max_age_h is not None:
            in_window = 0 if (age_h is not None and age_h <= target_max_age_h) else (1 if age_h is None else 2)
        else:
            in_window = 0
        return (
            in_window,
            item.get("_priority", (9, 9, 9)),
            age_h if age_h is not None else 5000.0,
            item.get("post_url", ""),
        )

    sorted_posts = sorted(harvested_by_key.values(), key=_harvest_sort_key)
    for p in sorted_posts:
        p.pop("_priority", None)

    return sorted_posts[:limit]


_LI_POST_BLOCKED_UNTIL: float = 0.0


def scrape_single_post_details(
    post_item: Dict[str, Any],
    blacklisted_set: Set[str],
    max_age_hours: Optional[float] = None,
    target_location: str = "",
    target_locations: Optional[List[str]] = None,
    clean_role: str = "",
    tags: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetches the LinkedIn post, decodes its exact Snowflake timestamp, extracts full commentary text,
    mines JSON-LD comments for hidden emails/links, unrolls lnkd.in shortlinks, rejects login-wall
    boilerplate and unsupported foreign languages, validates recruitment intent and primary role fit,
    scores author authority, and classifies verified recruiter emails into quality tiers.
    """
    global _LI_POST_BLOCKED_UNTIL
    url = post_item.get("post_url", "")
    if not url or "/jobs/" in url.lower() or "jobs-guest" in url.lower() or "/job/" in url.lower():
        return None
    if not ("linkedin.com/posts" in url.lower() or "linkedin.com/feed/update" in url.lower()):
        return None

    # 1. Decode exact timestamp from LinkedIn's 64-bit Snowflake ID in the URL
    snow = decode_linkedin_snowflake_age(url)
    date_published: Optional[str] = post_item.get("date_published") or (snow["date_published"] if snow else None)
    age_hours: Optional[float] = post_item.get("age_hours") if post_item.get("age_hours") is not None else (snow["age_hours"] if snow else None)
    age_str: str = snow["age_str"] if snow else (post_item.get("date_str") or "Recent")
    is_under_24h: bool = snow["is_under_24h"] if snow else bool(post_item.get("is_under_24h", False))

    # Fast O(1) age gate BEFORE making any network call if Snowflake ID proves post is too old
    if max_age_hours is not None and age_hours is not None and age_hours > max_age_hours:
        logger.debug(f"[GATE:AGE-SNOWFLAKE] REJECTED age={age_hours:.1f}h > max={max_age_hours}h url={url[-50:]}")
        return None

    search_title = clean_linkedin_boilerplate(post_item.get("search_title") or "")
    initial_snippet = clean_linkedin_boilerplate(post_item.get("snippet") or "")
    url_slug_text = post_item.get("url_slug_text") or extract_url_slug_context(url)

    full_text = initial_snippet
    author_name = post_item.get("author_name") or ""
    if not author_name or author_name == "LinkedIn Recruiter":
        author_name = parse_author_info_from_url(url, title_hint=search_title).get("name") or "LinkedIn Recruiter"

    author_profile_url = ""
    author_headline = ""
    company_name = post_item.get("company", "")
    og_title = search_title
    found_emails: List[Dict[str, Any]] = []
    seen_email_addrs: Set[str] = set()
    comments_collected: List[str] = []

    def _add_verified_email(em_addr: str, source_label: str, contact_name: str = "") -> None:
        em_norm = (em_addr or "").strip().lower()
        if not em_norm or em_norm in seen_email_addrs or em_norm in blacklisted_set:
            return
        is_valid, _ = verify_recruiter_email_strictly(em_norm, blacklisted_set)
        if is_valid:
            seen_email_addrs.add(em_norm)
            tier_meta = classify_recruiter_email_tier(em_norm, source=source_label)
            found_emails.append({
                "email": em_norm,
                "name": contact_name or author_name or "Hiring Manager",
                "source": source_label,
                "verified": True,
                "verification_status": "MX Deliverable",
                **tier_meta,
            })

    # 2. Fetch LinkedIn public post page using link-preview crawler User-Agent first (bypasses guest authwall
    # and receives full JSON-LD + OpenGraph commentary + comments).
    # Fast-path: if LinkedIn is currently returning 999/authwall (circuit breaker active) OR snippet already has
    # rich commentary (>= 110 chars), skip redundant per-post HTTP round-trip!
    crawler_headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    now_ts = time.time()
    should_fetch_page = (now_ts >= _LI_POST_BLOCKED_UNTIL) and (len(initial_snippet) < 550 or "@" not in initial_snippet)

    try:
        r = None
        if should_fetch_page:
            r = _POST_SESSION.get(url, headers=crawler_headers, timeout=2.0, verify=False)
            _is_blocked = (
                r.status_code in (999, 429)
                or (r.status_code == 200 and ("authwall" in (r.url or "") or "login" in (r.url or "")))
            )
            if r.status_code in (999, 429):
                _LI_POST_BLOCKED_UNTIL = now_ts + 90.0
        else:
            _is_blocked = True

        if r is not None and r.status_code == 200 and r.text:
            soup = BeautifulSoup(r.text, "html.parser")

            # A. Extract og:title (author name + post preview) if not boilerplate
            og_t = soup.find("meta", property="og:title")
            if og_t and og_t.get("content"):
                raw_og_title = og_t.get("content").strip()
                if not is_linkedin_boilerplate(raw_og_title) and "sign in" not in raw_og_title.lower():
                    og_title = raw_og_title
                    parsed_from_og = parse_author_info_from_url(url, title_hint=og_title).get("name")
                    if parsed_from_og and parsed_from_og != "LinkedIn Recruiter":
                        if not author_name or author_name == "LinkedIn Recruiter":
                            author_name = parsed_from_og

            # B. Extract og:description ONLY if it is NOT LinkedIn's login-wall boilerplate
            og_desc_tag = soup.find("meta", property="og:description")
            if og_desc_tag and og_desc_tag.get("content"):
                og_desc_content = clean_linkedin_boilerplate(og_desc_tag.get("content").strip())
                if og_desc_content and not is_linkedin_boilerplate(og_desc_content):
                    if len(og_desc_content) > len(full_text):
                        full_text = og_desc_content

            if not _is_blocked:
                # C. Parse JSON-LD metadata (articleBody, author, datePublished, and comment array)
                for s in soup.find_all("script", type="application/ld+json"):
                    if s.string and ("datePublished" in s.string or "articleBody" in s.string or "description" in s.string):
                        try:
                            ld_data = json.loads(s.string)
                            raw_date = ld_data.get("datePublished")
                            if raw_date:
                                date_published = raw_date
                                clean_dp = raw_date.replace("Z", "+00:00")
                                dt = datetime.fromisoformat(clean_dp)
                                now = datetime.now(timezone.utc)
                                diff = (now - dt).total_seconds()
                                age_hours = round(max(diff, 0) / 3600.0, 1)
                                if age_hours < 1:
                                    age_str = "Just now"
                                elif age_hours < 24:
                                    age_str = f"{max(1, int(age_hours))}h ago"
                                elif age_hours < 48:
                                    age_str = "1d ago"
                                elif age_hours < 168:
                                    age_str = f"{int(age_hours // 24)}d ago"
                                elif age_hours < 720:
                                    age_str = f"{int(age_hours // 168)}w ago"
                                else:
                                    age_str = f"{max(1, int(age_hours // 720))}mo ago"
                                is_under_24h = (age_hours <= 24.0)

                            author_obj = ld_data.get("author") or ld_data.get("creator")
                            if isinstance(author_obj, dict):
                                if author_obj.get("name"):
                                    author_name = author_obj.get("name").strip()
                                if author_obj.get("url"):
                                    author_profile_url = author_obj.get("url").strip()
                                if author_obj.get("jobTitle"):
                                    author_headline = author_obj.get("jobTitle")
                                elif author_obj.get("description"):
                                    author_headline = author_obj.get("description")

                            h_org = ld_data.get("hiringOrganization")
                            if isinstance(h_org, dict) and h_org.get("name"):
                                company_name = h_org.get("name").strip()

                            if ld_data.get("articleBody"):
                                body_cand = clean_linkedin_boilerplate(ld_data.get("articleBody").strip())
                                if body_cand and not is_linkedin_boilerplate(body_cand):
                                    full_text = body_cand
                            elif ld_data.get("description"):
                                clean_ld_desc = clean_linkedin_boilerplate(
                                    BeautifulSoup(ld_data.get("description"), "html.parser").get_text("\n", strip=True)
                                )
                                if clean_ld_desc and not is_linkedin_boilerplate(clean_ld_desc) and len(clean_ld_desc) > len(full_text):
                                    full_text = clean_ld_desc

                            # Mine JSON-LD comments for recruiter emails and application links
                            raw_comments = ld_data.get("comment")
                            if isinstance(raw_comments, dict):
                                raw_comments = [raw_comments]
                            if isinstance(raw_comments, list):
                                for c_obj in raw_comments[:15]:
                                    if not isinstance(c_obj, dict):
                                        continue
                                    c_text = (c_obj.get("text") or c_obj.get("articleBody") or "").strip()
                                    if not c_text:
                                        continue
                                    c_author_obj = c_obj.get("author") or {}
                                    c_author_name = c_author_obj.get("name", "").strip() if isinstance(c_author_obj, dict) else ""
                                    c_text_low = c_text.lower()
                                    is_author_comment = bool(
                                        c_author_name
                                        and author_name
                                        and (
                                            c_author_name.lower() == author_name.lower()
                                            or c_author_name.lower().split()[0] == author_name.lower().split()[0]
                                        )
                                    )
                                    has_candidate_phrase = any(
                                        cp in c_text_low
                                        for cp in ("interested", "cfbr", "my email", "my resume", "my cv", "please review", "check my", "i am looking")
                                    )
                                    has_recruiter_phrase = any(
                                        rp in c_text_low
                                        for rp in ("send cv", "send your cv", "share cv", "share your cv", "send resume", "apply at", "email at", "hr@", "careers@", "talent@", "jobs@")
                                    )
                                    if is_author_comment or (has_recruiter_phrase and not has_candidate_phrase):
                                        comments_collected.append(c_text)
                                        c_emails = extract_clean_emails_from_text(c_text, blacklisted_set)
                                        for c_em in c_emails:
                                            _add_verified_email(c_em, "post_comment", c_author_name or author_name)
                        except Exception:
                            pass
                        break

                # D. Direct post commentary container fallback
                body_el = soup.find(
                    "div",
                    class_=re.compile(r"show-more-less-html__markup|feed-shared-update-v2__description|update-components-text|attributed-text-segment-list")
                )
                if body_el:
                    extracted_text = clean_linkedin_boilerplate(body_el.get_text("\n", strip=True))
                    if extracted_text and not is_linkedin_boilerplate(extracted_text) and len(extracted_text) > len(full_text):
                        full_text = extracted_text

                # E. Author headline from HTML if not yet found
                if not author_headline:
                    actor_desc_el = soup.find(
                        class_=re.compile(r"actor__description|feed-shared-actor__description|update-components-actor__description|base-main-card__subtitle")
                    )
                    if actor_desc_el:
                        author_headline = actor_desc_el.get_text(" ", strip=True)

                # F. Extract emails from post body
                page_emails = extract_clean_emails_from_text(full_text, blacklisted_set)
                for em in page_emails:
                    _add_verified_email(em, "post_body", author_name)
    except Exception:
        pass

    # Clean boilerplate and fall back to search title + URL slug if snippet was empty
    full_text = clean_linkedin_boilerplate(full_text)
    if (not full_text or len(full_text) < 25) and search_title and not is_linkedin_boilerplate(search_title):
        full_text = search_title
    if (not full_text or len(full_text) < 25) and url_slug_text:
        full_text = f"{full_text} {url_slug_text}".strip()

    # Reject if still empty or LinkedIn boilerplate
    if not full_text or len(full_text) < 20 or is_linkedin_boilerplate(full_text):
        return None

    # 2b. Foreign Language Gate (reject Vietnamese, Polish, Turkish, Cyrillic unless location matches)
    active_locs_for_lang = [l for l in (target_locations or ([target_location] if target_location else [])) if l]
    if not is_supported_post_language(full_text, active_locs_for_lang):
        logger.debug(f"[GATE:LANG] REJECTED unsupported foreign language url={url[-50:]}")
        return None

    # Snippet fallback email extraction
    if not found_emails and full_text:
        snippet_emails = extract_clean_emails_from_text(f"{full_text} {og_title}", blacklisted_set)
        for em in snippet_emails:
            _add_verified_email(em, "post_snippet", author_name)

    # 3. STRICT RECRUITMENT & HIRING INTENT GATE (never bypassed — runs BEFORE any external link unrolling)
    analysis_context = f"{og_title} {url_slug_text}".strip()
    is_recruiting, reason, hiring_signals = analyze_recruitment_intent(
        text=full_text,
        author_headline=author_headline,
        extra_context=analysis_context
    )
    if not is_recruiting:
        logger.debug(f"[GATE:INTENT] REJECTED reason={reason} url={url[-50:]}")
        return None

    # 4. STRICT AGE GATE (using Snowflake / JSON-LD timestamp)
    if max_age_hours is not None:
        if age_hours is not None and age_hours > max_age_hours:
            logger.debug(f"[GATE:AGE] REJECTED age={age_hours:.1f}h > max={max_age_hours}h url={url[-50:]}")
            return None
        elif age_hours is None and max_age_hours <= 24:
            combined_check = (full_text + " " + initial_snippet).lower()
            recency_signals = (
                "hour ago", "hours ago", "just now", "today", "m ago", "min ago",
                "h ago", "minute", "moments ago", "an hour", "yesterday", "1d ago", "1 day ago",
            )
            if any(sig in combined_check for sig in recency_signals):
                age_str = "Recent (<24h)"
                is_under_24h = True
            else:
                return None

    # 5. Location detection & accuracy filter (runs BEFORE external link unrolling)
    combined_for_fit = f"{full_text} {og_title} {url_slug_text}".strip()
    is_loc_matched = check_location_match(combined_for_fit, author_headline, target_location, target_locations, post_url=url)
    detected_loc = extract_post_location(combined_for_fit, author_headline, target_location, target_locations)

    active_locs = [l.strip().lower() for l in (target_locations or ([target_location] if target_location else [])) if l and l.strip()]
    if active_locs and not any(l in ("", "all", "worldwide", "anywhere") for l in active_locs):
        if not is_loc_matched:
            return None

    # 6. Strict Role & Skill Fit Gate (runs BEFORE external link unrolling)
    is_fit, fit_score, matched_skills, extracted_title = check_role_and_skill_fit(
        full_text=combined_for_fit,
        author_headline=author_headline,
        clean_role=clean_role or post_item.get("role_title", ""),
        tags=tags
    )
    if not is_fit:
        return None

    # 7. Unroll lnkd.in shortlinks ONLY for posts that passed all gates and lack a direct email
    external_apply_url = ""
    unrolled_domain = ""
    combined_for_links = full_text + ("\n" + "\n".join(comments_collected[:5]) if comments_collected else "")
    if not found_emails and "lnkd.in/" in combined_for_links:
        unrolled = unroll_linkedin_shortlinks(combined_for_links, blacklisted_set)
        external_apply_url = unrolled.get("external_apply_url") or ""
        unrolled_domain = unrolled.get("company_domain") or ""
        for u_em in unrolled.get("emails") or []:
            _add_verified_email(u_em, "unrolled_link", author_name)

    # 8. Intelligent Company Name Resolution (without blind Clearbit email guessing)
    if not _is_valid_company_candidate(company_name):
        company_candidate = ""
        m_explicit = re.search(r"(?:🏢\s*Company|Company|Organization|Organisation|Client)\s*[:—–-]\s*([A-Z0-9][A-Za-z0-9\s&.,'-]{2,35})", full_text, re.I)
        if m_explicit:
            cand = re.split(r"[\n\r|•💼📍]", m_explicit.group(1))[0].strip()
            if _is_valid_company_candidate(cand):
                company_candidate = cand

        if not company_candidate and author_headline:
            m_head = re.search(r"(?:at|@|—|-|\|)\s+([A-Z][A-Za-z0-9\s&.,'-]{2,25})", author_headline)
            if m_head:
                cand = re.split(r"[\n\r|•]", m_head.group(1))[0].strip()
                if _is_valid_company_candidate(cand):
                    company_candidate = cand

        if not company_candidate:
            m_hiring = re.search(r"\b([A-Z][A-Za-z0-9\s&]{2,25}?)\s+(?:is hiring|are hiring|is expanding|is seeking|announces|has openings|is looking for)", full_text)
            if m_hiring and _is_valid_company_candidate(m_hiring.group(1)):
                company_candidate = m_hiring.group(1).strip()

        if not company_candidate and found_emails:
            for em_info in found_emails:
                em_addr = em_info.get("email", "") if isinstance(em_info, dict) else str(em_info)
                if "@" in em_addr:
                    domain_part = em_addr.split("@")[-1].lower()
                    if domain_part not in FREE_EMAIL_DOMAINS:
                        root = domain_part.split(".")[0].replace("-", " ").title().strip()
                        if len(root) >= 2 and _is_valid_company_candidate(root):
                            company_candidate = root
                            break

        if not company_candidate and unrolled_domain:
            root = unrolled_domain.split(".")[0].replace("-", " ").title().strip()
            if len(root) >= 3 and _is_valid_company_candidate(root):
                company_candidate = root

        company_name = company_candidate if _is_valid_company_candidate(company_candidate) else "Hiring Team"

    # Sort verified emails: post_body before post_comment, then by tier_rank (1=direct_corporate, 2=role_corporate, 3=freemail_recruiter)
    found_emails.sort(key=lambda e: (0 if e.get("source") == "post_body" else 1, e.get("tier_rank", 4)))

    # 8. Author Authority Scoring & Experience Extraction
    author_authority, authority_delta = classify_author_authority(author_name, author_headline, url)
    fit_score = min(max(fit_score + authority_delta, 25), 99)
    required_years = extract_post_required_years(full_text)

    # Derive clean role title
    derived_role = _clean_extracted_role_title(
        extracted_title or "",
        post_item.get("role_title") or clean_role or "Software Engineer"
    )

    best_tier_rank = found_emails[0].get("tier_rank", 4) if found_emails else 99
    best_email_tier = found_emails[0].get("tier", "none") if found_emails else "none"

    return {
        "id": post_item.get("id"),
        "post_url": url,
        "author_name": author_name or "LinkedIn Recruiter",
        "author_profile_url": author_profile_url,
        "author_headline": author_headline or f"Recruiter at {company_name}",
        "author_authority": author_authority,
        "company": company_name,
        "location": detected_loc or post_item.get("location") or "Worldwide",
        "is_location_matched": is_loc_matched,
        "role_title": derived_role,
        "role_fit_score": fit_score,
        "required_years": required_years,
        "matched_skills": matched_skills,
        "post_snippet": full_text[:400] + ("..." if len(full_text) > 400 else ""),
        "full_text": full_text,
        "recruiter_emails": found_emails,
        "has_email": len(found_emails) > 0,
        "email_tier": best_email_tier,
        "email_tier_rank": best_tier_rank,
        "external_apply_url": external_apply_url,
        "date_published": date_published,
        "age_hours": age_hours,
        "age_str": age_str,
        "is_under_24h": is_under_24h,
        "is_recruiting": True,
        "hiring_signals": hiring_signals,
        "_24h_fallback": False,
    }


def _recompute_live_age(date_published: Optional[str], post_url: str = "") -> Tuple[Optional[str], Optional[float], str, bool]:
    """Recalculates live age_hours and age_str from ISO date_published or Snowflake URL."""
    snow = decode_linkedin_snowflake_age(post_url) if post_url else None
    dp = date_published or (snow["date_published"] if snow else None)
    if dp:
        try:
            clean_dp = dp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_dp)
            diff = max((datetime.now(timezone.utc) - dt).total_seconds(), 0.0)
            age_h = round(diff / 3600.0, 1)
            if age_h < 1.0:
                age_s = "Just now"
            elif age_h < 24.0:
                age_s = f"{max(1, int(age_h))}h ago"
            elif age_h < 48.0:
                age_s = "1d ago"
            elif age_h < 168.0:
                age_s = f"{int(age_h // 24)}d ago"
            elif age_h < 720.0:
                age_s = f"{int(age_h // 168)}w ago"
            else:
                age_s = f"{max(1, int(age_h // 720))}mo ago"
            return dp, age_h, age_s, (age_h <= 48.0)
        except Exception:
            pass
    if snow:
        return snow["date_published"], snow["age_hours"], snow["age_str"], snow["is_under_24h"]
    return dp, None, "Recent", False


def save_verified_posts_to_db(posts: List[Dict[str, Any]], clean_role: str) -> None:
    """
    Persists verified LinkedIn recruiter posts into the SQLite VerifiedRecruiterPost table
    so future searches benefit from an ever-growing index of verified recruiter posts.
    """
    if not posts:
        return
    try:
        from .database import SessionLocal
        from . import models
        db = SessionLocal()
        try:
            seen_in_batch: Set[str] = set()
            valid_items = []
            urls_batch = []
            ids_batch = []
            for p in posts:
                p_url = (p.get("post_url") or "").strip()
                p_id = (p.get("id") or generate_stable_post_id(p_url)).strip()
                if not p_url or not p_id or p_url in seen_in_batch or p_id in seen_in_batch:
                    continue
                seen_in_batch.add(p_url)
                seen_in_batch.add(p_id)
                valid_items.append((p, p_url, p_id))
                urls_batch.append(p_url)
                ids_batch.append(p_id)

            if not valid_items:
                return

            existing_rows = (
                db.query(models.VerifiedRecruiterPost)
                .filter(
                    models.VerifiedRecruiterPost.post_url.in_(urls_batch)
                    | models.VerifiedRecruiterPost.post_id.in_(ids_batch)
                )
                .all()
            )
            by_url = {r.post_url: r for r in existing_rows if r.post_url}
            by_id = {r.post_id: r for r in existing_rows if r.post_id}

            for p, p_url, p_id in valid_items:
                existing = by_url.get(p_url) or by_id.get(p_id)
                emails_json = json.dumps(p.get("recruiter_emails") or [])
                skills_json = json.dumps(p.get("matched_skills") or [])
                signals_json = json.dumps(p.get("hiring_signals") or [])
                snow = decode_linkedin_snowflake_age(p_url)
                pub_epoch = snow.get("published_epoch", 0) if snow else 0
                if existing:
                    existing.role_title = p.get("role_title") or existing.role_title
                    existing.company = p.get("company") or existing.company
                    existing.author_name = p.get("author_name") or existing.author_name
                    existing.author_headline = p.get("author_headline") or existing.author_headline
                    existing.location = p.get("location") or existing.location
                    if len(p.get("full_text") or "") > len(existing.full_text or ""):
                        existing.full_text = p.get("full_text")
                    if p.get("has_email"):
                        existing.recruiter_emails_json = emails_json
                    existing.matched_skills_json = skills_json
                    existing.hiring_signals_json = signals_json
                    existing.role_fit_score = max(p.get("role_fit_score") or 0, existing.role_fit_score or 0)
                    if p.get("date_published"):
                        existing.date_published = p.get("date_published")
                    if pub_epoch:
                        existing.published_epoch = pub_epoch
                else:
                    row = models.VerifiedRecruiterPost(
                        post_id=p_id,
                        post_url=p_url,
                        role_key=(clean_role or "").lower().strip(),
                        role_title=p.get("role_title") or clean_role,
                        company=p.get("company") or "Hiring Team",
                        author_name=p.get("author_name") or "LinkedIn Recruiter",
                        author_headline=p.get("author_headline") or "",
                        author_profile_url=p.get("author_profile_url") or "",
                        location=p.get("location") or "Worldwide",
                        full_text=p.get("full_text") or "",
                        recruiter_emails_json=emails_json,
                        matched_skills_json=skills_json,
                        hiring_signals_json=signals_json,
                        role_fit_score=p.get("role_fit_score") or 75,
                        date_published=p.get("date_published"),
                        published_epoch=pub_epoch,
                    )
                    db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"[DB-INDEX] save_verified_posts_to_db error: {exc}")


def load_verified_posts_from_db(
    clean_role: str,
    target_locs: List[str],
    max_age_hours: Optional[float],
    email_only: bool,
    blacklisted_set: Set[str],
    tags: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Loads previously verified recruiter posts from SQLite that match the requested role,
    location, language, and recency window, recalculating live age_hours from date_published.
    """
    loaded: List[Dict[str, Any]] = []
    try:
        from .database import SessionLocal
        from . import models
        db = SessionLocal()
        try:
            rows = (
                db.query(models.VerifiedRecruiterPost)
                .order_by(models.VerifiedRecruiterPost.discovered_at.desc())
                .limit(180)
                .all()
            )
            active_locs = [l.strip() for l in (target_locs or []) if l and l.strip().lower() not in ("", "all", "worldwide", "anywhere")]
            target_loc_str = active_locs[0] if active_locs else ""

            for row in rows:
                full_text = clean_linkedin_boilerplate(row.full_text or "")
                if not full_text or is_linkedin_boilerplate(full_text):
                    continue
                if not is_supported_post_language(full_text, active_locs):
                    continue

                dp, age_h, age_s, is_u24 = _recompute_live_age(row.date_published, row.post_url)
                if max_age_hours is not None:
                    if age_h is not None and age_h > max_age_hours:
                        continue
                    if age_h is None and max_age_hours <= 24:
                        continue

                is_loc_ok = check_location_match(full_text, row.author_headline or "", target_loc_str, active_locs, post_url=row.post_url or "")
                if active_locs and not is_loc_ok:
                    continue

                is_fit, fit_score, matched_skills, extracted_title = check_role_and_skill_fit(
                    full_text=full_text,
                    author_headline=row.author_headline or "",
                    clean_role=clean_role,
                    tags=tags,
                )
                if not is_fit:
                    continue

                try:
                    raw_emails = json.loads(row.recruiter_emails_json or "[]")
                except Exception:
                    raw_emails = []

                # Filter out any blind company_domain guesses from legacy rows & apply tiering
                clean_emails = []
                for em_obj in raw_emails:
                    if not isinstance(em_obj, dict):
                        continue
                    em_addr = (em_obj.get("email") or "").strip().lower()
                    em_src = em_obj.get("source") or "post_body"
                    if not em_addr or em_addr in blacklisted_set or em_src == "company_domain":
                        continue
                    tier_meta = classify_recruiter_email_tier(em_addr, source=em_src)
                    clean_emails.append({**em_obj, **tier_meta})

                clean_emails.sort(key=lambda e: e.get("tier_rank", 4))
                if email_only and not clean_emails:
                    continue

                try:
                    hiring_signals = json.loads(row.hiring_signals_json or "[]")
                except Exception:
                    hiring_signals = ["Explicit Hiring Callout"]

                author_authority, auth_delta = classify_author_authority(row.author_name or "", row.author_headline or "", row.post_url or "")
                final_fit = min(max(fit_score + auth_delta, 25), 99)
                derived_role = _clean_extracted_role_title(extracted_title or row.role_title or "", clean_role)

                loaded.append({
                    "id": row.post_id or generate_stable_post_id(row.post_url),
                    "post_url": row.post_url,
                    "author_name": row.author_name or "LinkedIn Recruiter",
                    "author_profile_url": row.author_profile_url or "",
                    "author_headline": row.author_headline or f"Recruiter at {row.company or 'Hiring Team'}",
                    "author_authority": author_authority,
                    "company": row.company if _is_valid_company_candidate(row.company or "") else "Hiring Team",
                    "location": row.location or "Worldwide",
                    "is_location_matched": is_loc_ok,
                    "role_title": derived_role,
                    "role_fit_score": final_fit,
                    "required_years": extract_post_required_years(full_text),
                    "matched_skills": matched_skills,
                    "post_snippet": full_text[:400] + ("..." if len(full_text) > 400 else ""),
                    "full_text": full_text,
                    "recruiter_emails": clean_emails,
                    "has_email": len(clean_emails) > 0,
                    "email_tier": clean_emails[0].get("tier", "none") if clean_emails else "none",
                    "email_tier_rank": clean_emails[0].get("tier_rank", 99) if clean_emails else 99,
                    "external_apply_url": "",
                    "date_published": dp,
                    "age_hours": age_h,
                    "age_str": age_s,
                    "is_under_24h": is_u24,
                    "is_recruiting": True,
                    "hiring_signals": hiring_signals,
                    "_24h_fallback": False,
                })
        finally:
            db.close()
    except Exception as exc:
        logger.debug(f"[DB-INDEX] load_verified_posts_from_db error: {exc}")
    return loaded


def fetch_linkedin_voyager_posts(
    clean_role: str,
    locations: Optional[List[str]] = None,
    time_range: str = "all",
    limit: int = 40,
    page: int = 1,
    li_at_cookie: str = "",
    tags: Optional[List[str]] = None,
    blacklisted_set: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Directly scrapes LinkedIn's official Content Search (Voyager Search API)
    for live recruiter publications and feed posts matching the role and date filter.
    Extracts author name, headline, post commentary text, activity URL, and publication timestamp.
    Strictly filters out any job board listings.
    """
    if not li_at_cookie or not li_at_cookie.strip():
        return []

    found = []
    seen_urls = set()

    # Determine date filter parameter for Voyager
    date_filter = ""
    if time_range in ("24h", "1d", "day", "past-24h"):
        date_filter = ",(key:datePosted,value:List(past-24h))"
    elif time_range in ("week", "7d", "1w", "past-week"):
        date_filter = ",(key:datePosted,value:List(past-week))"
    elif time_range in ("month", "30d", "1m", "past-month"):
        date_filter = ",(key:datePosted,value:List(past-month))"

    # Location handling: if locations are provided, append location to keywords
    keywords_clean = clean_role.strip()
    if locations:
        loc_parts = [l.strip() for l in locations if l and l.strip().lower() not in ("all", "worldwide", "anywhere")]
        if loc_parts:
            keywords_clean = f"{keywords_clean} {loc_parts[0]}"

    csrf_token = "ajax:8273940182746"
    headers = {
        "authority": "www.linkedin.com",
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "csrf-token": csrf_token,
        "x-restli-protocol-version": "2.0.0",
        "x-li-lang": "en_US",
        "x-li-track": '{"clientVersion":"1.12.*"}',
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "referer": "https://www.linkedin.com/search/results/content/",
    }
    cookies = {
        "li_at": li_at_cookie.strip(),
        "JSESSIONID": f'"{csrf_token}"',
    }

    start_offset = max(0, (page - 1) * 10)
    batch_count = min(max(limit, 10), 25)

    encoded_keywords = urllib.parse.quote(keywords_clean)
    voyager_query = f"(keywords:{encoded_keywords},flagshipSearchIntent:SEARCH_SRP,queryParameters:List((key:resultType,value:List(CONTENT)){date_filter}))"

    url = (
        "https://www.linkedin.com/voyager/api/search/dash/clusters"
        f"?decorationId=com.linkedin.voyager.dash.deco.search.SearchClusterCollection-175"
        f"&origin=FACETED_SEARCH"
        f"&q=all"
        f"&query={voyager_query}"
        f"&start={start_offset}"
        f"&count={batch_count}"
    )

    try:
        r = requests.get(url, headers=headers, cookies=cookies, timeout=5, allow_redirects=False, verify=False)
        if r.status_code == 200:
            data = r.json()
            included = data.get("included", [])

            for item in included:
                try:
                    # Look for post commentary
                    commentary_obj = item.get("commentary") or {}
                    text_obj = commentary_obj.get("text") or {}
                    post_text = text_obj.get("text") if isinstance(text_obj, dict) else (str(text_obj) if text_obj else "")
                    if not post_text:
                        if "text" in item and isinstance(item["text"], dict):
                            post_text = item["text"].get("text", "")
                        elif "summary" in item and isinstance(item["summary"], dict):
                            post_text = item["summary"].get("text", "")

                    if not post_text or len(post_text.strip()) < 15:
                        continue

                    # Pre-screen snippet to drop obvious job-seekers
                    if is_snippet_unambiguously_disqualified(post_text[:250]):
                        continue

                    # Extract activity URN / ID
                    urn = item.get("urn") or item.get("entityUrn") or ""
                    act_match = re.search(r"activity:(\d+)", urn)
                    if not act_match:
                        for val in item.values():
                            if isinstance(val, str):
                                m = re.search(r"activity:(\d+)", val)
                                if m:
                                    act_match = m
                                    break
                    if not act_match:
                        continue

                    activity_id = act_match.group(1)
                    post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}"

                    # Strict rejection of job boards
                    if "/jobs/" in post_url.lower() or "jobs-guest" in post_url.lower() or "/job/" in post_url.lower():
                        continue

                    if post_url in seen_urls:
                        continue
                    seen_urls.add(post_url)

                    # Extract author details
                    actor_obj = item.get("actor") or {}
                    author_name = ""
                    author_headline = ""
                    if isinstance(actor_obj, dict):
                        name_obj = actor_obj.get("name") or {}
                        author_name = name_obj.get("text", "") if isinstance(name_obj, dict) else str(name_obj)
                        desc_obj = actor_obj.get("description") or actor_obj.get("subDescription") or {}
                        author_headline = desc_obj.get("text", "") if isinstance(desc_obj, dict) else str(desc_obj)

                    if not author_name:
                        author_name = "LinkedIn Member"

                    # Infer company
                    company = ""
                    if author_headline:
                        m_comp = re.search(r"(?:at|@)\s+([A-Z0-9][A-Za-z0-9\s.,&-]{2,30})", author_headline)
                        if m_comp:
                            company = m_comp.group(1).strip()
                    if not company:
                        company = "Hiring Team"

                    # Timestamp
                    created_time_ms = item.get("createdTime")
                    date_published = None
                    age_hours = None
                    age_str = "Recent"
                    is_under_24h = False
                    if created_time_ms:
                        try:
                            dt = datetime.fromtimestamp(created_time_ms / 1000.0, timezone.utc)
                            date_published = dt.isoformat()
                            diff = (datetime.now(timezone.utc) - dt).total_seconds()
                            age_hours = round(max(diff, 0) / 3600.0, 1)
                            if age_hours < 1:
                                age_str = "Just now"
                            elif age_hours < 24:
                                age_str = f"{int(age_hours)}h ago"
                            elif age_hours < 48:
                                age_str = "1d ago"
                            elif age_hours < 168:
                                age_str = f"{int(age_hours // 24)}d ago"
                            else:
                                age_str = f"{int(age_hours // 168)}w ago"
                            is_under_24h = (age_hours <= 24.0)
                        except Exception:
                            pass

                    # Extract role title and check role fit
                    title = extract_accurate_job_title(post_text, clean_role)
                    is_fit, fit_score, matched_skills, clean_title = check_role_and_skill_fit(
                        post_text, author_headline, clean_role, tags=tags
                    )
                    if not is_fit:
                        continue
                    if clean_title:
                        title = clean_title

                    # Extract emails directly from the post text
                    emails_mined = extract_clean_emails_from_text(post_text, blacklisted_set if blacklisted_set else set())
                    recruiter_emails = []
                    for em in emails_mined:
                        is_valid, reason_str = verify_recruiter_email_strictly(em, blacklisted_set if blacklisted_set else set())
                        if is_valid:
                            tier_meta = classify_recruiter_email_tier(em, source="post_body")
                            recruiter_emails.append({
                                "email": em,
                                "name": author_name or "Hiring Manager",
                                "source": "post_body",
                                "verified": True,
                                "verification_status": "MX Deliverable",
                                **tier_meta,
                            })
                    recruiter_emails.sort(key=lambda e: e.get("tier_rank", 4))

                    post_id = generate_stable_post_id(post_url)

                    # Detect hiring signals
                    hiring_signals = []
                    lower_text = post_text.lower()
                    if "we are hiring" in lower_text or "now hiring" in lower_text or "recruiting" in lower_text:
                        hiring_signals.append("Explicit Hiring Callout")
                    if "@" in post_text:
                        hiring_signals.append("Direct Recruiter Email")
                    if "apply" in lower_text or "send your cv" in lower_text or "send resume" in lower_text:
                        hiring_signals.append("Application Instructions")
                    if "dm me" in lower_text or "inbox" in lower_text or "reach out" in lower_text:
                        hiring_signals.append("Direct Message Invitation")

                    loc_display = locations[0] if locations and locations[0] else "Worldwide"
                    author_authority, auth_delta = classify_author_authority(author_name, author_headline, post_url)
                    fit_score = min(max(fit_score + auth_delta, 25), 99)

                    found.append({
                        "id": post_id,
                        "post_url": post_url,
                        "role_title": _clean_extracted_role_title(title, clean_role),
                        "author_name": author_name,
                        "author_headline": author_headline,
                        "author_authority": author_authority,
                        "company": company,
                        "location": loc_display,
                        "snippet": post_text[:400] + ("..." if len(post_text) > 400 else ""),
                        "post_snippet": post_text[:400] + ("..." if len(post_text) > 400 else ""),
                        "full_text": post_text,
                        "date_str": age_str,
                        "date_published": date_published,
                        "age_hours": age_hours,
                        "age_str": age_str,
                        "is_under_24h": is_under_24h,
                        "recruiter_emails": recruiter_emails,
                        "has_email": len(recruiter_emails) > 0,
                        "email_tier": recruiter_emails[0].get("tier", "none") if recruiter_emails else "none",
                        "email_tier_rank": recruiter_emails[0].get("tier_rank", 99) if recruiter_emails else 99,
                        "primary_email": recruiter_emails[0]["email"] if recruiter_emails else None,
                        "confidence_score": recruiter_emails[0].get("confidence", 95) if recruiter_emails else 85,
                        "is_recruiting": True,
                        "hiring_signals": hiring_signals,
                        "role_fit_score": fit_score,
                        "required_years": extract_post_required_years(post_text),
                        "matched_skills": matched_skills,
                        "is_location_matched": True,
                        "source": "linkedin_voyager_stream"
                    })
                except Exception:
                    continue
    except Exception:
        pass

    return found


def search_linkedin_recruiter_posts(
    role_query: str,
    locations: Optional[List[str]] = None,
    location: str = "",
    tags: Optional[List[str]] = None,
    limit: int = 40,
    email_only: bool = False,
    time_range: str = "all",
    max_age_hours: Optional[float] = None,
    blacklisted_set: Optional[Set[str]] = None,
    agent_mode: bool = False,
    return_stats: bool = False,
    force_refresh: bool = False,
    page: int = 1,
    li_at_cookie: str = ""
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
    """
    High-yield, deep-mining search for live LinkedIn hiring postings.
    Performs multi-query expansion and multi-location pagination in parallel.
    Mines verified recruiter emails with strict authoritative DNS MX checks, comment mining,
    and lnkd.in shortlink unrolling. Persists and merges verified posts via SQLite.
    """
    if blacklisted_set is None:
        blacklisted_set = set()

    # Parse and clean query, extracting any inline country or hashtags
    clean_role, extracted_locs = parse_user_query(role_query, locations)
    if not clean_role:
        clean_role = "Software Engineer"

    # Merge locations
    target_locs = list(extracted_locs or [])
    if location and location.strip():
        if "," in location:
            for l in location.split(","):
                l_str = l.strip()
                if l_str and l_str not in target_locs:
                    target_locs.append(l_str)
        elif location.strip() not in target_locs:
            target_locs.append(location.strip())

    if "Worldwide" in target_locs and len(target_locs) > 1:
        target_locs = [l for l in target_locs if l.lower() != "worldwide"]

    if not target_locs:
        target_locs = ["Worldwide"]

    # 0. Check Search Cache if not force_refresh
    if not force_refresh:
        cached_entry = _SEARCH_CACHE.get(clean_role, target_locs, email_only, time_range, limit, page)
        if cached_entry is not None:
            cached_posts, cached_stats = cached_entry
            if blacklisted_set:
                for p in cached_posts:
                    p["recruiter_emails"] = [
                        e for e in p.get("recruiter_emails", [])
                        if e.get("email", "").lower() not in blacklisted_set
                    ]
                    p["has_email"] = len(p["recruiter_emails"]) > 0
            if return_stats:
                return cached_posts, cached_stats
            return cached_posts

    # Calculate age hours
    # Note: On LinkedIn, posts up to 48 hours old are displayed as '1d ago' (1 day).
    if time_range in ("24h", "1d", "day", "past-24h") or (max_age_hours is not None and max_age_hours <= 48):
        if max_age_hours is None:
            max_age_hours = 48.0
    elif time_range in ("3d", "past-3d") or (max_age_hours is not None and max_age_hours <= 72):
        if max_age_hours is None:
            max_age_hours = 72.0
    elif time_range in ("7d", "week", "1w", "past-week") or (max_age_hours is not None and max_age_hours <= 168):
        if max_age_hours is None:
            max_age_hours = 168.0
    elif time_range in ("month", "30d", "1m", "past-month") or (max_age_hours is not None and max_age_hours <= 720):
        if max_age_hours is None:
            max_age_hours = 720.0

    # 0b. Prioritize direct LinkedIn Voyager Content Search when session cookie is provided
    if li_at_cookie and li_at_cookie.strip():
        voyager_posts = fetch_linkedin_voyager_posts(
            clean_role, target_locs, time_range=time_range, limit=limit, page=page, li_at_cookie=li_at_cookie, tags=tags,
            blacklisted_set=blacklisted_set,
        )
        if voyager_posts:
            save_verified_posts_to_db(voyager_posts, clean_role)
            if blacklisted_set:
                for p in voyager_posts:
                    p["recruiter_emails"] = [
                        e for e in p.get("recruiter_emails", [])
                        if e.get("email", "").lower() not in blacklisted_set
                    ]
                    p["has_email"] = len(p["recruiter_emails"]) > 0

            if max_age_hours is not None:
                voyager_posts = [
                    p for p in voyager_posts
                    if (p.get("age_hours") is not None and p.get("age_hours") <= max_age_hours) or (max_age_hours > 24 and p.get("age_hours") is None)
                ]

            if email_only:
                voyager_posts = [p for p in voyager_posts if p.get("has_email")]

            voyager_posts.sort(
                key=lambda x: (
                    1 if x.get("has_email") else 0,
                    -x.get("email_tier_rank", 99),
                    x.get("role_fit_score", 0),
                    -(x.get("age_hours") if x.get("age_hours") is not None else 9999)
                ),
                reverse=True
            )

            stats = {
                "total_discovered": len(voyager_posts),
                "total_scraped": len(voyager_posts),
                "verified_hiring_posts": len(voyager_posts),
                "recruiter_emails_mined": sum(len(p.get("recruiter_emails", [])) for p in voyager_posts),
                "page": page,
                "has_more": len(voyager_posts) >= 5 or page < 50,
            }
            _SEARCH_CACHE.set(clean_role, target_locs, email_only, time_range, limit, (voyager_posts, stats), page=page)
            if return_stats:
                return voyager_posts, stats
            return voyager_posts

    # 1. Deep Multi-Angle LinkedIn Harvester (recruiter posts only)
    harvest_limit = min(max(limit + 15, 35), 55)
    found_posts = fetch_deep_linkedin_postings(
        clean_role, target_locs, limit=harvest_limit, page=page, time_range=time_range
    )

    # 2. Concurrently scrape and deep-mine candidate posts on shared _HUNTER_POOL
    detailed_posts: List[Dict[str, Any]] = []
    max_to_scrape = min(len(found_posts), harvest_limit)
    posts_to_scrape = found_posts[:max_to_scrape]

    if posts_to_scrape:
        futures = {
            _HUNTER_POOL.submit(
                scrape_single_post_details, p, blacklisted_set, max_age_hours, location, target_locs, clean_role, tags
            ): p
            for p in posts_to_scrape
        }
        try:
            for fut in as_completed(futures, timeout=7.5):
                try:
                    res = fut.result()
                    if not res:
                        continue
                    if email_only and not res.get("has_email"):
                        continue
                    detailed_posts.append(res)
                except Exception:
                    pass
        except (TimeoutError, FuturesTimeoutError, Exception):
            pass
        finally:
            for fut in futures:
                if not fut.done():
                    fut.cancel()

    # Persist newly verified live posts into SQLite index BEFORE merging
    if detailed_posts:
        save_verified_posts_to_db(detailed_posts, clean_role)

    # 2b. Merge with persistent verified posts from SQLite (within max_age_hours)
    db_verified_posts = load_verified_posts_from_db(
        clean_role=clean_role,
        target_locs=target_locs,
        max_age_hours=max_age_hours,
        email_only=email_only,
        blacklisted_set=blacklisted_set,
        tags=tags,
    )
    if db_verified_posts:
        detailed_posts.extend(db_verified_posts)

    # Fast fallback if narrow recency window yielded fewer than 6 posts
    if len(detailed_posts) < 6 and max_age_hours is not None and posts_to_scrape:
        existing_urls = {p.get("post_url") for p in detailed_posts}
        relaxed_max_age = min(max(max_age_hours * 4.5, 336.0), 2160.0)
        remaining_candidates = [p for p in posts_to_scrape if p.get("post_url") not in existing_urls][:18]
        if remaining_candidates:
            fallback_futures = {
                _HUNTER_POOL.submit(
                    scrape_single_post_details, p, blacklisted_set, relaxed_max_age, location, target_locs, clean_role, tags
                ): p
                for p in remaining_candidates
            }
            try:
                for fut in as_completed(fallback_futures, timeout=3.2):
                    try:
                        res = fut.result()
                        if not res:
                            continue
                        if email_only and not res.get("has_email"):
                            continue
                        res["_24h_fallback"] = True
                        detailed_posts.append(res)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                for fut in fallback_futures:
                    if not fut.done():
                        fut.cancel()
        if detailed_posts:
            save_verified_posts_to_db(detailed_posts, clean_role)
        # Also pull recent matching posts from SQLite within relaxed_max_age if still < 6
        if len(detailed_posts) < 6:
            db_fb_posts = load_verified_posts_from_db(
                clean_role=clean_role,
                target_locs=target_locs,
                max_age_hours=relaxed_max_age,
                email_only=email_only,
                blacklisted_set=blacklisted_set,
                tags=tags,
            )
            for db_p in db_fb_posts:
                if db_p.get("post_url") not in {p.get("post_url") for p in detailed_posts}:
                    db_p["_24h_fallback"] = True
                    detailed_posts.append(db_p)

    # 3. Deduplicate reposts that share identical normalized commentary text or URL
    deduped_posts: List[Dict[str, Any]] = []
    seen_fingerprints: Set[str] = set()
    seen_urls_final: Set[str] = set()
    for p in detailed_posts:
        u_norm = (p.get("post_url") or "").strip().lower()
        if not u_norm or u_norm in seen_urls_final:
            continue
        txt_norm = re.sub(r"[^a-z0-9]", "", (p.get("full_text") or "").lower())[:120]
        if len(txt_norm) >= 40 and txt_norm in seen_fingerprints:
            continue
        seen_urls_final.add(u_norm)
        if len(txt_norm) >= 40:
            seen_fingerprints.add(txt_norm)
        deduped_posts.append(p)

    detailed_posts = deduped_posts
    logger.debug(f"[SCRAPE] found={len(found_posts)} scraped={len(posts_to_scrape)} accepted={len(detailed_posts)}")

    # 4. Two-pass deterministic sort:
    # Pass 1: Canonical base tie-breaker (alphabetical by company, role_title, post_url)
    detailed_posts.sort(
        key=lambda x: (
            x.get("company", "").strip().lower(),
            x.get("role_title", "").strip().lower(),
            x.get("post_url", "")
        )
    )

    # Pass 2: Business ranking (in-window before fallback, verified emails, email tier quality, location matched, fit score, recency)
    detailed_posts.sort(
        key=lambda x: (
            0 if x.get("_24h_fallback") else 1,
            1 if x.get("has_email") else 0,
            -(x.get("email_tier_rank") if x.get("email_tier_rank") is not None else 99),
            1 if x.get("is_location_matched", True) else 0,
            x.get("role_fit_score", 0),
            -(x.get("age_hours") if x.get("age_hours") is not None else 9999)
        ),
        reverse=True
    )

    final_posts = detailed_posts[:max(limit, len(detailed_posts))]

    stats = {
        "total_discovered": len(found_posts),
        "total_scraped": len(posts_to_scrape),
        "verified_hiring_posts": len(detailed_posts),
        "recruiter_emails_mined": sum(len(p.get("recruiter_emails", [])) for p in detailed_posts),
        "page": page,
        "has_more": len(detailed_posts) >= limit and len(found_posts) > len(detailed_posts),
    }

    # Store in search cache for deterministic, instant repeated searches
    _SEARCH_CACHE.set(clean_role, target_locs, email_only, time_range, limit, (final_posts, stats), page=page)

    if return_stats:
        return final_posts, stats

    return final_posts


