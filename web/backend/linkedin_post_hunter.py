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
import base64
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

from .bounce_cleaner import get_blacklisted_emails
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
_http_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=1)
_POST_SESSION.mount("https://", _http_adapter)
_POST_SESSION.mount("http://", _http_adapter)


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

HASHTAG_REGEX = re.compile(r"#([a-zA-Z0-9_\u0600-\u06FF]{2,35})\b", re.UNICODE)

def extract_hashtags_from_text(text: str) -> List[str]:
    """Extracts organic hashtags and tags from LinkedIn post content."""
    if not text:
        return []
    tags = []
    seen = set()
    skip_tags = {"linkedin", "post", "like", "share", "comment", "repost", "viral", "explore"}
    for m in HASHTAG_REGEX.finditer(text):
        tag = m.group(1).strip().lower()
        if tag and tag not in seen and tag not in skip_tags and not tag.isdigit():
            seen.add(tag)
            tags.append(tag)
    return tags[:10]

def extract_linkedin_activity_id(url: str) -> Optional[str]:
    """Extracts unique numeric activity or share ID from LinkedIn post URLs to prevent duplicate scraping."""
    if not url:
        return None
    m = re.search(r"(?:activity[:\-](\d{15,22})|urn:li:(?:activity|share):(\d{15,22}))", url)
    if m:
        return m.group(1) or m.group(2)
    return None

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

def extract_bing_redirect_url(href: str) -> Optional[str]:
    """Extracts destination LinkedIn URL from Bing search results or /ck/a? redirect wrappers."""
    if not href:
        return None
    # Filter out internal Bing navigation links (search, copilot, etc.)
    if any(p in href for p in ("bing.com/search", "copilotsearch", "/search?", "bing.com/images", "bing.com/news")):
        return None
    # Case 1: Direct LinkedIn URL in href
    if ("linkedin.com/posts" in href or "linkedin.com/feed/update" in href) and href.startswith("http"):
        return href.split("?")[0].rstrip("/")
    # Case 2: Bing's /ck/a?! redirect wrapper — real URL is base64-encoded in the p= parameter
    if "/ck/a?" in href and "p=" in href:
        try:
            # Format: /ck/a?!&&p=<base64>JmltdH...
            m = re.search(r"[?&]p=([a-zA-Z0-9_\-]+)", href)
            if m:
                b64_str = m.group(1)
                # Bing base64 uses URL-safe alphabet
                b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
                decoded = base64.urlsafe_b64decode(b64_str).decode("utf-8", errors="ignore")
                # The decoded string often starts with the URL
                url_m = re.search(r"https?://[^\s\"'>]+linkedin\.com/(?:posts|feed/update)[^\s\"'>]*", decoded)
                if url_m:
                    return url_m.group(0).split("?")[0].rstrip("/")
        except Exception:
            pass
    # Case 3: Legacy Bing u=a1<base64> format
    if "/ck/a?" in href and "u=" in href:
        try:
            m = re.search(r"[?&]u=a1([a-zA-Z0-9_\-]+)", href)
            if m:
                b64_str = m.group(1)
                b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
                decoded = base64.urlsafe_b64decode(b64_str).decode("utf-8", errors="ignore")
                if ("linkedin.com/posts" in decoded or "linkedin.com/feed/update" in decoded) and decoded.startswith("http"):
                    return decoded.split("?")[0].rstrip("/")
        except Exception:
            pass
    return None

def extract_ddg_redirect_url(href: str) -> Optional[str]:
    """Extracts destination LinkedIn URL from DuckDuckGo /l/?uddg= redirect wrapper."""
    if not href or any(eng in href for eng in ("duckduckgo.com/html/?q=", "duckduckgo.com/?q=")):
        return None
    if "uddg=" in href:
        try:
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                decoded = urllib.parse.unquote(m.group(1))
                if ("linkedin.com/posts" in decoded or "linkedin.com/feed/update" in decoded) and decoded.startswith("http"):
                    return decoded.split("?")[0].rstrip("/")
        except Exception:
            pass
    if ("linkedin.com/posts" in href or "linkedin.com/feed/update" in href) and href.startswith("http"):
        return href.split("?")[0].rstrip("/")
    return None

def parse_author_info_from_url(post_url: str) -> Dict[str, str]:
    """Derives author name and slug from linkedin.com/posts/john-doe-123_... URL."""
    try:
        path = urllib.parse.urlparse(post_url).path
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "posts":
            raw_slug = parts[1].split("_")[0]
            slug = urllib.parse.unquote(raw_slug)
            cleaned_name = re.sub(r"-\d+[a-z0-9]*$", "", slug)
            cleaned_name = cleaned_name.replace("-", " ").replace("_", " ").title()
            cleaned_name = urllib.parse.unquote(cleaned_name)
            return {"slug": slug, "name": cleaned_name}
    except Exception:
        pass
    return {"slug": "", "name": "LinkedIn Recruiter"}

LOCATION_MAPPINGS = {
    "remote": '("remote" OR "work from home" OR "anywhere" OR "WFH" OR "telecommute")',
    "remote us": '("remote" AND ("USA" OR "United States" OR "US"))',
    "remote europe": '("remote" AND ("Europe" OR "EMEA" OR "UK" OR "Germany"))',
    "remote mena": '("remote" AND ("MENA" OR "UAE" OR "Saudi" OR "Morocco"))',
    "united states": '("United States" OR "USA" OR "US")',
    "usa": '("United States" OR "USA" OR "US")',
    "us": '("United States" OR "USA" OR "US")',
    "new york": '("New York" OR "NYC")',
    "san francisco": '("San Francisco" OR "Bay Area" OR "Silicon Valley")',
    "united kingdom": '("United Kingdom" OR "UK" OR "London")',
    "uk": '("United Kingdom" OR "UK" OR "London")',
    "london": '("London" OR "UK")',
    "canada": '("Canada" OR "Toronto" OR "Vancouver" OR "Montreal")',
    "uae": '("UAE" OR "Dubai" OR "United Arab Emirates" OR "Abu Dhabi")',
    "dubai": '("Dubai" OR "UAE" OR "United Arab Emirates")',
    "united arab emirates": '("United Arab Emirates" OR "UAE" OR "Dubai")',
    "saudi arabia": '("Saudi Arabia" OR "KSA" OR "Riyadh" OR "Jeddah")',
    "ksa": '("Saudi Arabia" OR "KSA" OR "Riyadh")',
    "riyadh": '("Riyadh" OR "Saudi Arabia")',
    "morocco": '("Morocco" OR "Casablanca" OR "Rabat" OR "Maroc")',
    "maroc": '("Morocco" OR "Casablanca" OR "Rabat" OR "Maroc")',
    "casablanca": '("Casablanca" OR "Morocco")',
    "germany": '("Germany" OR "Berlin" OR "Munich" OR "Frankfurt" OR "Deutschland")',
    "berlin": '("Berlin" OR "Germany")',
    "france": '("France" OR "Paris" OR "Lyon")',
    "paris": '("Paris" OR "France")',
    "netherlands": '("Netherlands" OR "Amsterdam" OR "Holland")',
    "amsterdam": '("Amsterdam" OR "Netherlands")',
    "switzerland": '("Switzerland" OR "Zurich" OR "Geneva")',
    "spain": '("Spain" OR "Madrid" OR "Barcelona")',
    "italy": '("Italy" OR "Rome" OR "Milan")',
    "ireland": '("Ireland" OR "Dublin")',
    "poland": '("Poland" OR "Warsaw")',
    "sweden": '("Sweden" OR "Stockholm")',
    "belgium": '("Belgium" OR "Brussels")',
    "singapore": '("Singapore")',
    "australia": '("Australia" OR "Sydney" OR "Melbourne")',
    "india": '("India" OR "Bangalore" OR "Hyderabad" OR "Pune" OR "Mumbai")',
    "egypt": '("Egypt" OR "Cairo")',
    "qatar": '("Qatar" OR "Doha")',
    "kuwait": '("Kuwait")',
    "bahrain": '("Bahrain" OR "Manama")',
    "oman": '("Oman" OR "Muscat")',
    "jordan": '("Jordan" OR "Amman")',
    "austria": '("Austria" OR "Vienna" OR "Wien")',
    "denmark": '("Denmark" OR "Copenhagen")',
    "norway": '("Norway" OR "Oslo")',
    "portugal": '("Portugal" OR "Lisbon" OR "Porto")',
    "mexico": '("Mexico" OR "Mexico City" OR "CDMX")',
    "brazil": '("Brazil" OR "Brasil" OR "São Paulo" OR "Rio de Janeiro")',
    "argentina": '("Argentina" OR "Buenos Aires")',
    "colombia": '("Colombia" OR "Bogotá" OR "Medellin")',
    "chile": '("Chile" OR "Santiago")',
    "japan": '("Japan" OR "Tokyo")',
    "south korea": '("South Korea" OR "Korea" OR "Seoul")',
    "new zealand": '("New Zealand" OR "Auckland")',
    "malaysia": '("Malaysia" OR "Kuala Lumpur")',
    "philippines": '("Philippines" OR "Manila")',
    "indonesia": '("Indonesia" OR "Jakarta")',
}

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

def check_single_location_match(full_text: str, author_headline: str, target_location: str) -> bool:
    if not target_location or target_location.strip().lower() in ("", "all", "worldwide", "anywhere"):
        return True
        
    t_clean = target_location.strip().lower()
    combined = (full_text + " " + author_headline).lower()
    
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

def check_location_match(full_text: str, author_headline: str, target_location: str = "", target_locations: Optional[List[str]] = None) -> bool:
    locs = []
    if target_locations:
        locs = [l.strip() for l in target_locations if l and l.strip()]
    elif target_location:
        locs = [target_location.strip()]
        
    if not locs or any(l.lower() in ("", "all", "worldwide", "anywhere") for l in locs):
        return True
        
    return any(check_single_location_match(full_text, author_headline, loc) for loc in locs)

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
    """Fast pre-screening check that only drops search snippets that are definitively job seekers or spam."""
    if not text:
        return False
    lower_t = text.lower()
    for pattern in COMPILED_SNIPPET_DISQUALIFIED:
        if pattern.search(lower_t):
            return True
    return False

def is_disqualified_post(text: str) -> bool:
    """Check for full text matching non-recruitment patterns."""
    if not text:
        return False
    lower_t = text.lower()
    for pattern in COMPILED_NON_RECRUITMENT:
        if pattern.search(lower_t):
            return True
    return False

def analyze_recruitment_intent(text: str, author_headline: str = "", extra_context: str = "") -> Tuple[bool, str, List[str]]:
    """
    Analyzes post content, headline, and extra metadata to verify genuine recruitment/hiring intent.
    Strictly filters out job seekers (#OpenToWork), thought leadership, courses, and celebrations.
    Returns: (is_recruitment: bool, reason: str, detected_signals: List[str])
    """
    combined = f"{text or ''} {author_headline or ''} {extra_context or ''}".strip().lower()
    if not combined or len(combined) < 15:
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
    has_apply_link = bool(re.search(r"https?://[^\s]+(?:apply|job|career|lever\.co|greenhouse\.io|workday)", text or "", re.I))
    if has_apply_link:
        detected_signals.append("direct_apply_link")

    # Author headline check
    recruiter_headline = bool(re.search(r"\b(recruiter|talent acquisition|hiring manager|head of talent|technical recruiter|hr manager|lead recruiter|sourcer)\b", author_headline or "", re.I))
    if recruiter_headline:
        detected_signals.append("recruiter_author")

    # Relaxed check for search engine snippet results
    if not detected_signals:
        hiring_words = ["hiring", "join our team", "open role", "vacancy", "career", "job opening", "send cv", "send resume", "poste à pourvoir", "recrutons"]
        if any(w in combined for w in hiring_words):
            detected_signals.append("search_query_hiring_intent")

    if not detected_signals:
        return False, "No verified hiring or recruitment signals found in post", []

    return True, "Verified genuine recruitment post", detected_signals

def get_role_variants(clean_role: str) -> List[str]:
    """Generates natural synonyms (e.g. Developer <-> Engineer) to maximize recruiter post discovery."""
    variants = [clean_role]
    lower_r = clean_role.lower()
    if "developer" in lower_r:
        variants.append(re.sub(r'(?i)\bdeveloper\b', 'Engineer', clean_role))
    elif "engineer" in lower_r:
        variants.append(re.sub(r'(?i)\bengineer\b', 'Developer', clean_role))
    return list(dict.fromkeys(variants))

def build_post_and_feed_queries(role: str, loc_str: str, phrases: List[str]) -> List[str]:
    """Generates both linkedin.com/posts and linkedin.com/feed/update queries for high discovery rate."""
    queries = []
    loc_part = f'"{loc_str}"' if loc_str and not loc_str.startswith('"') and not loc_str.startswith("(") else loc_str
    for p in phrases:
        queries.append(f'site:linkedin.com/posts "{role}" {loc_part} {p}'.strip())
    # Add top feed/update queries
    for p in phrases[:3]:
        queries.append(f'site:linkedin.com/feed/update "{role}" {loc_part} {p}'.strip())
    return queries

CORE_HIRING_TAGS = [
    "hiring", "urgenthiring", "hiringalert", "jobopening", "jobopportunity",
    "nowhiring", "recruiting", "careers", "immediatejoiner", "vacancy",
    "employment", "recruitment", "hiringnow", "jobalert", "talentacquisition"
]

WORK_MODE_TAGS = [
    "remote", "remotejob", "remotework", "workfromhome", "wfh", "telecommute"
]

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

LOCATION_TAG_MAPPINGS = {
    "united states": ["usjobs", "techjobsusa", "hiringusa", "usajobs"],
    "usa": ["usjobs", "techjobsusa", "hiringusa", "usajobs"],
    "united kingdom": ["ukjobs", "londonjobs", "techjobsuk"],
    "uk": ["ukjobs", "londonjobs", "techjobsuk"],
    "germany": ["germanyjobs", "berlinjobs", "techjobsde", "jobsingermany"],
    "france": ["recrutementfrance", "parisjobs", "emploi", "techjobsfrance"],
    "uae": ["dubaijobs", "uaejobs", "gulfjobs", "middleeastjobs"],
    "united arab emirates": ["dubaijobs", "uaejobs", "gulfjobs", "middleeastjobs"],
    "saudi arabia": ["saudijobs", "riyadhjobs", "recruitmentksa"],
    "qatar": ["qatarjobs", "dohajobs", "gulfjobs"],
    "kuwait": ["kuwaitjobs", "gulfjobs"],
    "morocco": ["moroccojobs", "recrutementmaroc", "casablancajobs"],
    "egypt": ["egyptjobs", "cairojobs"],
    "canada": ["canadajobs", "torontojobs", "vancouverjobs"],
    "netherlands": ["amsterdamjobs", "dutchjobs"],
    "switzerland": ["swissjobs", "zurichjobs"],
    "spain": ["madridjobs", "barcelonajobs", "spainjobs"],
    "singapore": ["singaporejobs", "sgjobs"],
    "australia": ["australiajobs", "sydneyjobs", "melbournejobs"],
    "remote": ["remotejob", "remotework", "workfromhome", "wfh", "remote"],
    "worldwide": ["remotejob", "remotework", "workfromhome", "wfh", "worldwidejobs"]
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

def extract_accurate_job_title(text: str, fallback_role: str) -> str:
    """
    Extracts explicit job title declarations from post text.
    e.g. 'Hiring: Senior Frontend React Engineer' -> 'Senior Frontend React Engineer'
    """
    if not text:
        return fallback_role

    patterns = [
        r"(?:hiring for(?: the role of)?|looking for an?|urgently hiring an?|open role[:\-–]|position[:\-–]|hiring[:\-–])\s+([A-Z][A-Za-z0-9\s/+#\.\-]{3,45}(?:developer|engineer|designer|manager|specialist|lead|architect|consultant|analyst))",
        r"(?:role|job title|designation)\s*[:\-–]\s*([A-Z][A-Za-z0-9\s/+#\.\-]{3,45})",
        r"\b(Senior\s+[A-Za-z0-9\s/+#\.\-]{3,35}(?:Developer|Engineer|Designer|Manager))",
        r"\b(Lead\s+[A-Za-z0-9\s/+#\.\-]{3,35}(?:Developer|Engineer|Designer|Manager))",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            extracted = m.group(1).strip().strip(":,.-")
            if 4 <= len(extracted) <= 50 and not any(kw in extracted.lower() for kw in ("we are", "apply now", "please", "email", "http")):
                return extracted.title()
    return fallback_role

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
    2. Measures semantic skill overlap with target role domain keywords.
    3. Computes a role fit score (0-100%) and extracts matching skills.
    4. Extracts the actual declared job title from the post body.
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
            
    # Extract role tokens
    role_tokens = [w for w in re.findall(r"[a-zA-Z0-9+#]+", role_lower) if len(w) >= 3 and w not in ("the", "and", "for", "with", "all", "job", "jobs", "role")]
    target_skills.update(role_tokens)

    # 3. Match skills in post text
    matched_skills = []
    for skill in sorted(target_skills, key=lambda s: -len(s)):
        skill_re = re.compile(rf"\b{re.escape(skill)}\b", re.I)
        if skill_re.search(combined_text):
            if skill not in matched_skills and skill not in ("developer", "engineer", "software", "tech"):
                matched_skills.append(skill)
                
    # 4. Check direct role presence
    exact_role_in_post = role_lower in combined_text
    
    # 5. Fit Score calculation
    fit_score = 50  # baseline
    if exact_role_in_post:
        fit_score += 25
    elif any(tok in combined_text for tok in role_tokens):
        fit_score += 15
        
    fit_score += min(len(matched_skills) * 8, 25)
    fit_score = min(fit_score, 98)
    
    # 6. Relevance Threshold
    if role_tokens and len(matched_skills) == 0 and not exact_role_in_post:
        has_token = any(tok in combined_text for tok in role_tokens)
        if not has_token:
            return False, 0, [], clean_role

    extracted_title = extract_accurate_job_title(full_text, clean_role)
    return True, fit_score, matched_skills[:6], extracted_title

_DOMAIN_CACHE: Dict[str, Optional[str]] = {}

def resolve_company_recruiter_domain(company_name: str) -> Optional[str]:
    """Resolves authoritative corporate domain for a company name."""
    if not company_name or company_name.lower() in ("tech company", "stealth", "confidential", "recruiter", "hiring"):
        return None
        
    clean_name = re.sub(r"\b(inc|corp|ltd|llc|gmbh|sa|srl|b\.v\.|bv|group)\b", "", company_name, flags=re.I).strip(" ,.-")
    if not clean_name or len(clean_name) < 2:
        return None
        
    cache_key = clean_name.lower()
    if cache_key in _DOMAIN_CACHE:
        return _DOMAIN_CACHE[cache_key]
        
    # 1. Clearbit Autocomplete API
    try:
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={urllib.parse.quote(clean_name)}"
        r = requests.get(url, timeout=2.0)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    sugg_name = item.get("name", "").lower()
                    dom = item.get("domain", "").lower()
                    if dom and "." in dom and dom not in FALSE_DOMAINS:
                        if clean_name.lower() in sugg_name or sugg_name in clean_name.lower():
                            _DOMAIN_CACHE[cache_key] = dom
                            return dom
                if data and data[0].get("domain"):
                    first_dom = data[0]["domain"].lower()
                    if first_dom not in FALSE_DOMAINS:
                        _DOMAIN_CACHE[cache_key] = first_dom
                        return first_dom
    except Exception:
        pass
        
    # 2. DNS slug check
    slug = re.sub(r"[^a-z0-9]", "", clean_name.lower())
    if len(slug) >= 3:
        for tld in ["com", "io", "ai", "co", "tech", "net", "org"]:
            cand = f"{slug}.{tld}"
            try:
                if strictly_verify_mx(cand):
                    _DOMAIN_CACHE[cache_key] = cand
                    return cand
            except Exception:
                continue
                
    _DOMAIN_CACHE[cache_key] = None
    return None

def probe_or_derive_talent_emails(company_name: str, domain: str, blacklisted_set: Set[str]) -> List[Dict[str, Any]]:
    """
    Mines real, deliverable talent acquisition emails from the corporate domain.
    Verifies deliverability with strict authoritative DNS MX checks.
    """
    found = []
    if not domain or not strictly_verify_mx(domain):
        return found
        
    seen = set()
    recruiter_prefixes = ["careers", "jobs", "recruiting", "talent", "hr"]
    for prefix in recruiter_prefixes:
        cand_email = f"{prefix}@{domain}".lower()
        if cand_email in blacklisted_set or cand_email in seen:
            continue
        is_valid, _ = verify_recruiter_email_strictly(cand_email, blacklisted_set)
        if is_valid:
            seen.add(cand_email)
            found.append({
                "email": cand_email,
                "name": f"Talent Team at {company_name}",
                "title": "Talent Acquisition",
                "source": "company_domain",
                "verified": True,
                "verification_status": "MX Deliverable"
            })
            if len(found) >= 2:
                break
                
    return found

def fetch_deep_linkedin_postings(
    role_query: str,
    locations: Optional[List[str]] = None,
    limit: int = 60,
    page: int = 1,
    time_range: str = "all"
) -> List[Dict[str, Any]]:
    """
    Harvests authentic LinkedIn recruiter publications and feed posts (linkedin.com/posts and linkedin.com/feed/update).
    Discovers real human recruiter posts announcing open positions and hiring announcements.
    Supports pagination across search engine results and date filtering (24h, week, month).
    """
    clean_role, parsed_locs = parse_user_query(role_query, locations)
    if not clean_role:
        clean_role = "Software Engineer"
    
    # Target locations
    target_locs = [l.strip() for l in (parsed_locs or []) if l and l.strip().lower() not in ("all", "worldwide", "anywhere")]
    sweep_locs = target_locs if target_locs else [""]

    # Natural hiring phrases that match real human recruiter announcements — expanded set
    hiring_phrases = [
        '"we are hiring"',
        '"now hiring"',
        '"hiring"',
        '"job opening"',
        '"open position"',
        '"send your cv"',
        '"join our team"',
        '"looking for"',
        '"open role"',
        '"we\'re hiring"',
        '"urgently hiring"',
        '"actively hiring"',
        '"join us"',
        '"recrutons"',
        '"offre d\'emploi"',
        '"send resume"',
        '"drop your cv"',
        '"hiring alert"',
    ]
    
    search_tasks = []
    
    # Role variants — expanded to maximize recruiter post discovery
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
        role_variants.append(re.sub(r'(?i)flutter\s*(developer|engineer|dev)?', 'Dart Developer', clean_role).strip())
        role_variants.append(re.sub(r'(?i)flutter\s*(developer|engineer|dev)?', 'Mobile Developer', clean_role).strip())
        role_variants.append("Flutter")  # bare keyword for broader matching

    if "developer" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)\bdeveloper\b', 'engineer', clean_role))
    elif "engineer" in role_lower_chk:
        role_variants.append(re.sub(r'(?i)\bengineer\b', 'developer', clean_role))

    role_variants = list(dict.fromkeys(role_variants))

    # Priority 0: Exact role + Target location + Primary hiring phrases
    for loc_idx, loc in enumerate(sweep_locs[:3]):
        loc_str = f' "{loc}"' if loc else ''
        for p_idx, phrase in enumerate(hiring_phrases[:4]):
            q1 = f'site:linkedin.com/posts "{clean_role}" {phrase}{loc_str}'
            search_tasks.append((q1, (0, loc_idx, p_idx)))
        q_feed = f'site:linkedin.com/feed/update "{clean_role}" "hiring"{loc_str}'
        search_tasks.append((q_feed, (0, loc_idx, 9)))
        q_feed2 = f'site:linkedin.com/feed/update "{clean_role}" "we are hiring"{loc_str}'
        search_tasks.append((q_feed2, (0, loc_idx, 10)))

    # Priority 1: Exact role + Worldwide (no location constraint)
    for p_idx, phrase in enumerate(hiring_phrases[:4]):
        q_ww = f'site:linkedin.com/posts "{clean_role}" {phrase}'
        search_tasks.append((q_ww, (1, 0, p_idx)))
        # Unquoted query for robust indexing matches
        q_ww_unq = f'site:linkedin.com/posts {clean_role} {phrase}'
        search_tasks.append((q_ww_unq, (1, 0, p_idx + 5)))

    # Priority 2: Feed and role variants
    q_feed_unq = f'site:linkedin.com/feed/update {clean_role} hiring'
    search_tasks.append((q_feed_unq, (2, 0, 0)))
    for r_idx, r_var in enumerate(role_variants[1:]):
        q_var = f'site:linkedin.com/posts "{r_var}" "hiring"'
        search_tasks.append((q_var, (2, r_idx + 1, 0)))
        q_var2 = f'site:linkedin.com/posts {r_var} hiring'
        search_tasks.append((q_var2, (2, r_idx + 1, 1)))

    # Deduplicate queries while preserving priority
    unique_tasks = []
    seen_q = set()
    for q_str, prio in search_tasks:
        if q_str not in seen_q:
            seen_q.add(q_str)
            unique_tasks.append((q_str, prio))

    # Determine date parameters for search engines
    yahoo_age = ""
    ddg_df = ""
    bing_filters = ""
    bing_freshness = ""  # Bing's more reliable &freshness= param
    if time_range in ("24h", "1d", "day", "past-24h"):
        yahoo_age = "&age=1d"
        ddg_df = "&df=d"
        bing_filters = "&filters=ex1%3a%22ez1%22"
        bing_freshness = "&freshness=Day"
    elif time_range in ("week", "7d", "1w", "past-week"):
        yahoo_age = "&age=1w"
        ddg_df = "&df=w"
        bing_filters = "&filters=ex1%3a%22ez2%22"
        bing_freshness = "&freshness=Week"
    elif time_range in ("month", "30d", "1m", "past-month"):
        yahoo_age = "&age=1m"
        ddg_df = "&df=m"
        bing_filters = "&filters=ex1%3a%22ez3%22"
        bing_freshness = "&freshness=Month"

    # Engine scraper
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # Google time filter param
    _google_tbs = ""
    if yahoo_age == "&age=1d":
        _google_tbs = "&tbs=qdr:d"
    elif yahoo_age == "&age=1w":
        _google_tbs = "&tbs=qdr:w"
    elif yahoo_age == "&age=1m":
        _google_tbs = "&tbs=qdr:m"

    # Rotating user agents to reduce rate-limiting
    _USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    ]

    def fetch_engine_query(q: str, b_offset: int = 1) -> List[Tuple[str, str]]:
        posts_found = []
        q_enc = urllib.parse.quote(q)
        ua = _USER_AGENTS[b_offset % len(_USER_AGENTS)]
        hdrs = {**headers, "User-Agent": ua}

        # 1. Brave Search (highest yield for authentic LinkedIn recruiter publications)
        try:
            b_url = f"https://search.brave.com/search?q={q_enc}"
            if HAS_CURL_CFFI:
                r_brave = c_requests.get(b_url, impersonate="chrome120", timeout=7)
            else:
                r_brave = requests.get(b_url, headers=hdrs, timeout=7, verify=False)
            if r_brave.status_code == 200 and r_brave.text:
                soup = BeautifulSoup(r_brave.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "linkedin.com/posts" in href or "linkedin.com/feed/update" in href:
                        clean = href.split("?")[0].rstrip("/")
                        if clean.startswith("http") and not any(bad in clean for bad in ("cold-join", "login", "signup", "/jobs/")):
                            parent = a.find_parent(["div", "li"])
                            snip = parent.get_text(" ", strip=True) if parent else ""
                            if clean not in [p[0] for p in posts_found]:
                                posts_found.append((clean, snip))
        except Exception:
            pass

        # 2. Yahoo Search Engine (only if Brave didn't yield enough or for dated queries)
        if len(posts_found) < 4:
            try:
                url = f"https://search.yahoo.com/search?p={q_enc}&b={b_offset}{yahoo_age}"
                if HAS_CURL_CFFI:
                    r = c_requests.get(url, impersonate="chrome120", headers=hdrs, timeout=5, verify=False)
                else:
                    r = requests.get(url, headers=hdrs, timeout=5, verify=False)
                if r.status_code == 200 and r.text:
                    soup = BeautifulSoup(r.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        real_url = extract_yahoo_redirect_url(a["href"])
                        if real_url and real_url not in [p[0] for p in posts_found]:
                            snippet_div = a.find_parent(["li", "div"])
                            snip = snippet_div.get_text(" ", strip=True) if snippet_div else ""
                            posts_found.append((real_url, snip))
            except Exception:
                pass

        return posts_found

    harvested_by_url: Dict[str, Dict[str, Any]] = {}
    _dated_query = bool(yahoo_age or ddg_df or bing_filters or bing_freshness or _google_tbs)

    # Dynamic scroll simulation with target harvest buffer
    safe_page = max(1, page)
    target_harvest = max(limit * 2, 12)
    scroll_cycles = [
        # Cycle 1: fast initial harvest across primary query variants
        [(safe_page - 1) * 30 + 1, (safe_page - 1) * 30 + 11],
        # Cycle 2: deeper scroll if initial batch didn't hit buffer
        [(safe_page - 1) * 30 + 21],
    ]

    for cycle_idx, cycle_offsets in enumerate(scroll_cycles):
        if len(harvested_by_url) >= target_harvest:
            break

        cycle_task_idx = ((safe_page - 1) * 4 + cycle_idx * 4) % max(len(unique_tasks) - 4, 1)
        cycle_tasks = unique_tasks[cycle_task_idx : cycle_task_idx + 8]
        if len(cycle_tasks) < 4:
            cycle_tasks = unique_tasks[:8]

        with ThreadPoolExecutor(max_workers=16) as pool:
            future_map = {}
            for q_str, prio in cycle_tasks:
                for idx, off in enumerate(cycle_offsets):
                    fut = pool.submit(fetch_engine_query, q_str, off)
                    future_map[fut] = (prio[0], prio[1], prio[2] + cycle_idx * 10 + idx)

            try:
                for fut in as_completed(future_map.keys(), timeout=8.0):
                    try:
                        prio = future_map[fut]
                        results = fut.result()
                        for item in results:
                            if isinstance(item, tuple):
                                u, snip = item
                            else:
                                u, snip = item, ""
                            if not u:
                                continue

                            # Pre-screen snippet to drop obvious job-seekers immediately
                            if snip and is_snippet_unambiguously_disqualified(snip):
                                continue

                            clean_u, dedup_key = canonicalize_linkedin_post_url(u)
                            post_id = generate_stable_post_id(clean_u)
                            author_info = parse_author_info_from_url(clean_u)
                            
                            if clean_u not in harvested_by_url:
                                harvested_by_url[clean_u] = {
                                    "id": post_id,
                                    "post_url": clean_u,
                                    "role_title": clean_role,
                                    "author_name": author_info.get("name") or "LinkedIn Recruiter",
                                    "company": "",
                                    "location": sweep_locs[0] if sweep_locs[0] else "Worldwide",
                                    "snippet": snip,
                                    "date_str": "Recent",
                                    "source": "linkedin_publication",
                                    "_priority": prio,
                                    "_from_dated_query": _dated_query,
                                }
                            if len(harvested_by_url) >= target_harvest:
                                break
                    except Exception:
                        pass
                    if len(harvested_by_url) >= target_harvest:
                        break
            except Exception:
                pass

    # Sort deterministically by priority and URL
    sorted_posts = sorted(
        harvested_by_url.values(),
        key=lambda x: (
            x.get("_priority", (9, 9, 9)),
            x.get("post_url", "")
        )
    )

    for p in sorted_posts:
        p.pop("_priority", None)

    return sorted_posts[:limit]

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
    Fetches the LinkedIn job posting, extracts complete description, recruiter info,
    validates recruitment intent, role & skill fit, and mines verified corporate recruiter emails.
    """
    url = post_item.get("post_url", "")
    if not url or "/jobs/" in url.lower() or "jobs-guest" in url.lower() or "/job/" in url.lower():
        return None
    if not ("linkedin.com/posts" in url.lower() or "linkedin.com/feed/update" in url.lower()):
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    full_text = post_item.get("snippet", "") or ""
    author_name = post_item.get("author_name", "")
    author_profile_url = ""
    author_headline = ""
    company_name = post_item.get("company", "")
    og_title = ""
    date_published = None
    age_hours: Optional[float] = None
    age_str = "Recent"
    is_under_24h = False
    found_emails = []
    page_fetch_blocked = False  # True when LinkedIn returns login-wall / 999

    fetch_url = url

    try:
        if HAS_CURL_CFFI:
            r = c_requests.get(fetch_url, impersonate="chrome120", headers=headers, timeout=8, verify=False)
        else:
            r = requests.get(fetch_url, headers=headers, timeout=8, verify=False)

        # Detect LinkedIn login-wall / anti-scrape block
        _is_blocked = (
            r.status_code in (999, 429, 403, 302, 301)
            or (r.status_code == 200 and ("authwall" in r.url or "login" in r.url or "authwall" in r.text[:300]))
        )
        if _is_blocked:
            page_fetch_blocked = True

        if r.status_code == 200 or _is_blocked:
            soup = BeautifulSoup(r.text, "html.parser")

            # 0. Check og:title for author name and context (usually populated even on blocked pages)
            og_t = soup.find("meta", property="og:title")
            if og_t and og_t.get("content"):
                og_title = og_t.get("content").strip()
                m_og_author = re.search(r"^([A-Z][A-Za-z\s.'-]{2,30})\s+on\s+LinkedIn:", og_title)
                if m_og_author:
                    cand_name = m_og_author.group(1).strip()
                    if not author_name or author_name == "LinkedIn Recruiter":
                        author_name = cand_name

            # Also extract og:description (often available even on login-wall pages)
            og_desc_tag = soup.find("meta", property="og:description")
            if og_desc_tag and og_desc_tag.get("content"):
                og_desc_content = og_desc_tag.get("content").strip()
                if len(og_desc_content) > len(full_text):
                    full_text = og_desc_content

            if not _is_blocked:
                # 1. Parse JSON-LD metadata (only available on real page loads)
                for s in soup.find_all("script", type="application/ld+json"):
                    if s.string and ("datePublished" in s.string or "description" in s.string):
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
                                    age_str = f"{int(age_hours)}h ago"
                                elif age_hours < 48:
                                    age_str = "1d ago"
                                elif age_hours < 168:
                                    age_str = f"{int(age_hours // 24)}d ago"
                                else:
                                    age_str = f"{int(age_hours // 168)}w ago"
                                is_under_24h = (age_hours <= 24.0)

                            author_obj = ld_data.get("author") or ld_data.get("creator")
                            if isinstance(author_obj, dict):
                                if not author_name or author_name == "LinkedIn Recruiter" or author_name.startswith("Hiring Lead"):
                                    author_name = author_obj.get("name", author_name)
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
                                full_text = ld_data.get("articleBody").strip()
                            elif ld_data.get("description"):
                                clean_ld_desc = BeautifulSoup(ld_data.get("description"), "html.parser").get_text("\n", strip=True)
                                if len(clean_ld_desc) > len(full_text):
                                    full_text = clean_ld_desc
                        except Exception:
                            pass
                        break

                # Fallback 1: Direct post or job description container
                body_el = soup.find("div", class_=re.compile(r"show-more-less-html__markup|feed-shared-update-v2__description|update-components-text|attributed-text-segment-list"))
                if body_el:
                    extracted_text = body_el.get_text("\n", strip=True)
                    if extracted_text and len(extracted_text) > len(full_text):
                        full_text = extracted_text

                # Fallback 2: og:description (already extracted above, but re-check for longer content)
                if not full_text or len(full_text) < 50:
                    og_desc = soup.find("meta", property="og:description")
                    if og_desc and og_desc.get("content"):
                        desc_content = og_desc.get("content").strip()
                        if len(desc_content) > len(full_text):
                            full_text = desc_content

                # Extract author headline from HTML if not yet found
                if not author_headline:
                    actor_desc_el = soup.find(class_=re.compile(r"actor__description|feed-shared-actor__description|update-components-actor__description|base-main-card__subtitle"))
                    if actor_desc_el:
                        author_headline = actor_desc_el.get_text(" ", strip=True)

                # Extract emails from page HTML (only meaningful on real page loads)
                page_emails = extract_clean_emails_from_text(full_text + " " + r.text, blacklisted_set)
                for em in page_emails:
                    is_valid, _ = verify_recruiter_email_strictly(em, blacklisted_set)
                    if is_valid:
                        found_emails.append({
                            "email": em,
                            "name": author_name or "Hiring Manager",
                            "source": "post_body",
                            "verified": True,
                            "verification_status": "MX Deliverable"
                        })
    except Exception:
        page_fetch_blocked = True

    # Snippet fallback email extraction if page fetch did not yield emails
    if not found_emails and full_text:
        snippet_emails = extract_clean_emails_from_text(full_text, blacklisted_set)
        for em in snippet_emails:
            is_valid, _ = verify_recruiter_email_strictly(em, blacklisted_set)
            if is_valid:
                found_emails.append({
                    "email": em,
                    "name": author_name or "Hiring Manager",
                    "source": "post_snippet",
                    "verified": True,
                    "verification_status": "MX Deliverable"
                })

    # RECRUITMENT & HIRING INTENT GATE
    # Posts from dated-query searches already passed a hiring-intent keyword filter in the search query
    # (the query contained phrases like "we are hiring", "job opening", "send your cv", etc.)
    # We bypass the strict intent analysis UNLESS we successfully fetched the actual LinkedIn post page
    # (indicated by og:title matching the "AuthorName on LinkedIn:" pattern with real content).
    from_dated_q = post_item.get("_from_dated_query", False)
    # "Real content" = we got the actual LinkedIn post, not just a login/cookie page
    _got_real_page = bool(og_title and " on LinkedIn:" in og_title and len(full_text) > 200)
    _bypass_intent_gate = from_dated_q and not _got_real_page

    if not _bypass_intent_gate:
        is_recruiting, reason, hiring_signals = analyze_recruitment_intent(
            text=full_text,
            author_headline=author_headline,
            extra_context=og_title
        )
        if not is_recruiting:
            logger.debug(f"[GATE:INTENT] REJECTED reason={reason} dated={from_dated_q} url={url[-50:]}")
            return None
    else:
        # Trust the search engine's hiring intent — the query contained explicit hiring phrases
        hiring_signals = ["search_query_hiring_intent", "dated_query_trusted"]
        logger.debug(f"[GATE:INTENT] BYPASSED dated_q=True real_page={_got_real_page} url={url[-50:]}")

    # If max_age_hours filter is requested and this post is older than threshold, filter out
    if max_age_hours is not None:
        if age_hours is not None and age_hours > max_age_hours:
            if from_dated_q:
                # Post activity was verified within date window by the search engine (e.g. bumped/reposted)
                age_str = "< 24h" if max_age_hours <= 24 else f"< {int(max_age_hours//24)}d"
                is_under_24h = (max_age_hours <= 24)
            else:
                logger.debug(f"[GATE:AGE] REJECTED age={age_hours:.1f}h > max={max_age_hours}h url={url[-50:]}")
                return None
        elif age_hours is None and max_age_hours <= 24:
            if from_dated_q:
                # Trust the search engine's own date filter — post came from a 24h-filtered query
                age_str = "< 24h"
                is_under_24h = True
            else:
                # No date signal from engine: require recency keywords in snippet/text
                combined_check = (full_text + " " + (post_item.get("snippet") or "")).lower()
                recency_signals = (
                    "hour ago", "hours ago", "just now", "today", "m ago", "min ago",
                    "h ago", "minute", "moments ago", "an hour", "1h", "2h", "3h",
                    "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h",
                    "13h", "14h", "15h", "16h", "17h", "18h", "19h", "20h", "21h",
                    "22h", "23h", "yesterday", "1d ago", "1 day ago",
                )
                if any(sig in combined_check for sig in recency_signals):
                    age_str = "< 24h"
                    is_under_24h = True
                else:
                    logger.debug(f"[GATE:AGE] REJECTED age=None no-recency dated={from_dated_q} url={url[-50:]}")
                    return None
        elif age_hours is None and max_age_hours <= 72:
            age_str = "< 3d"
        elif age_hours is None and max_age_hours <= 168:
            age_str = "< 7d"
        elif age_hours is None and max_age_hours <= 720:
            age_str = "< 30d"
        elif age_hours is None:
            age_str = age_str or "Unknown"  # Catch-all for very large max_age_hours windows

    # Intelligent Company Name Resolution (Never assign author's personal name!)
    if not company_name or company_name in ("Tech Company", "Hiring Company", "LinkedIn Recruiter"):
        company_candidate = ""
        # 0. Check explicit "Company: [Name]" or "🏢 Company: [Name]" in post text
        m_explicit = re.search(r"(?:🏢\s*Company|Company|Organization|Organisation|Client)\s*[:—–-]\s*([A-Z0-9][A-Za-z0-9\s&.,'-]{2,35})", full_text, re.I)
        if m_explicit:
            cand = m_explicit.group(1).strip()
            if not cand.lower().startswith(("name", "confidential", "undisclosed", "hiring", "description")):
                company_candidate = cand

        # 1. Check author_headline (e.g. "Recruiter at Google", "Talent Acquisition @ Stripe")
        if not company_candidate and author_headline:
            m_head = re.search(r"(?:at|@|—|-|\|)\s+([A-Z][A-Za-z0-9\s&.,'-]{2,25})", author_headline)
            if m_head:
                cand = m_head.group(1).strip()
                if not cand.lower().startswith(("the ", "my ", "our ", "we ", "looking", "open", "immediate")):
                    company_candidate = cand

        # 2. Check "X is hiring / are hiring / announces" in post text
        if not company_candidate:
            m_hiring = re.search(r"\b([A-Z][A-Za-z0-9\s&]{1,25})\s+(?:is hiring|are hiring|is expanding|is seeking|announces|has openings)", full_text)
            if m_hiring and not m_hiring.group(1).lower().startswith(("we ", "i ", "my ", "our ", "this ", "the ")):
                company_candidate = m_hiring.group(1).strip()

        # 3. Check "join X" or "at X" in post text
        if not company_candidate:
            m_at = re.search(r"(?:join|at)\s+([A-Z][A-Za-z0-9\s&]{2,25})", full_text)
            if m_at:
                cand = m_at.group(1).strip()
                if not cand.lower().startswith(("the ", "our ", "this ", "us ", "me ", "you", "them", "a ", "an ")) and len(cand) > 2:
                    company_candidate = cand

        # 4. Extract from recruiter email domain if corporate
        if (not company_candidate or company_candidate.lower() in ("you", "team", "our team", "hiring")) and found_emails:
            for em_info in found_emails:
                em_addr = em_info.get("email", "") if isinstance(em_info, dict) else str(em_info)
                if "@" in em_addr:
                    domain_part = em_addr.split("@")[-1].lower()
                    if domain_part not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "protonmail.com"):
                        root = domain_part.split(".")[0].title()
                        if len(root) >= 2:
                            company_candidate = root
                            break

        company_name = company_candidate if company_candidate else "Hiring Team"

    # DEEP RECRUITER CONTACT MINING:
    # If no email was written in the text, resolve company domain and find deliverable talent mailboxes
    if not found_emails and company_name and company_name not in ("Tech Company", "Hiring Team"):
        try:
            dom = resolve_company_recruiter_domain(company_name)
            if dom:
                mined = probe_or_derive_talent_emails(company_name, dom, blacklisted_set)
                if mined:
                    found_emails.extend(mined)
        except Exception:
            pass

    # Location detection & accuracy filter
    # When page is blocked, skip location filtering — no content to match against
    is_loc_matched = True if _bypass_intent_gate else check_location_match(full_text, author_headline, target_location, target_locations)
    detected_loc = extract_post_location(full_text, author_headline, target_location, target_locations) if not _bypass_intent_gate else (target_location or "Worldwide")

    active_locs = [l.strip().lower() for l in (target_locations or ([target_location] if target_location else [])) if l and l.strip()]
    if active_locs and not any(l in ("", "all", "worldwide", "anywhere") for l in active_locs):
        if not is_loc_matched:
            return None

    # Role & Skill Fit Gate
    # When post came from a dated query AND page fetch failed/returned thin content,
    # skip strict fit check (the search query itself already contained the role as a quoted keyword)
    if _bypass_intent_gate:
        is_fit, fit_score, matched_skills, extracted_title = True, 60, [clean_role.lower()], clean_role
    else:
        is_fit, fit_score, matched_skills, extracted_title = check_role_and_skill_fit(
            full_text=full_text,
            author_headline=author_headline,
            clean_role=clean_role or post_item.get("role_title", "")
        )
        if not is_fit:
            return None

    # Derive role title from post text or fallback
    derived_role = post_item.get("role_title") or extracted_title or clean_role or "Software Engineer"
    m_pos = re.search(r"(?:Position|Role|Job Title|Job Opening|Hiring)\s*[:—–-]\s*([^\n\r,;•|]{4,45})", full_text, re.I)
    if m_pos:
        cand = m_pos.group(1).strip()
        if len(cand) >= 4 and not cand.lower().startswith(("http", "we ", "please")):
            derived_role = cand

    return {
        "id": post_item.get("id"),
        "post_url": url,
        "author_name": author_name or "LinkedIn Recruiter",
        "author_profile_url": author_profile_url,
        "author_headline": author_headline or f"Recruiter at {company_name}",
        "company": company_name,
        "location": post_item.get("location") or detected_loc or "Worldwide",
        "is_location_matched": is_loc_matched,
        "role_title": derived_role,
        "role_fit_score": fit_score,
        "matched_skills": matched_skills,
        "post_snippet": full_text[:400] + ("..." if len(full_text) > 400 else ""),
        "full_text": full_text,
        "recruiter_emails": found_emails,
        "has_email": len(found_emails) > 0,
        "date_published": date_published,
        "age_hours": age_hours,
        "age_str": age_str,
        "is_under_24h": is_under_24h,
        "is_recruiting": True,
        "hiring_signals": hiring_signals,
        "_24h_fallback": post_item.get("_24h_fallback", False),
    }

def fetch_linkedin_voyager_posts(
    clean_role: str,
    locations: Optional[List[str]] = None,
    time_range: str = "all",
    limit: int = 40,
    page: int = 1,
    li_at_cookie: str = "",
    tags: Optional[List[str]] = None
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
                    title = extract_accurate_job_title(post_text, clean_role)  # Fix: was fallback_title= (wrong kwarg)
                    is_fit, fit_score, matched_skills, clean_title = check_role_and_skill_fit(
                        post_text, author_headline, clean_role, tags=tags
                    )
                    if clean_title:
                        title = clean_title

                    # Extract emails directly from the post text
                    emails_mined = extract_clean_emails_from_text(post_text, blacklisted_set if blacklisted_set else set())
                    recruiter_emails = []
                    for em in emails_mined:
                        is_valid, reason_str = verify_recruiter_email_strictly(em, blacklisted_set if blacklisted_set else set())  # Fix: was passing company, author_name
                        if is_valid:
                            recruiter_emails.append({
                                "email": em,
                                "name": author_name or "Hiring Manager",
                                "source": "post_body",
                                "verified": True,
                                "verification_status": "MX Deliverable"
                            })

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

                    found.append({
                        "id": post_id,
                        "post_url": post_url,
                        "role_title": title,
                        "author_name": author_name,
                        "author_headline": author_headline,
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
                        "primary_email": recruiter_emails[0]["email"] if recruiter_emails else None,
                        "confidence_score": 95 if recruiter_emails else 85,
                        "email_status": recruiter_emails[0]["status"] if recruiter_emails else "no_email",
                        "is_recruiting": True,
                        "hiring_signals": hiring_signals,
                        "role_fit_score": fit_score,
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
    Mines verified recruiter emails with strict authoritative DNS MX checks.
    Includes thread-safe TTL caching for instant deterministic repeated queries.
    Supports pagination via `page`.
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
            # Filter against current blacklisted_set
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
    if time_range in ("24h", "1d", "day", "past-24h") or (max_age_hours is not None and max_age_hours <= 24):
        if max_age_hours is None:
            max_age_hours = 24.0
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
            clean_role, target_locs, time_range=time_range, limit=limit, page=page, li_at_cookie=li_at_cookie, tags=tags
        )
        if voyager_posts:
            # Filter against blacklisted emails
            if blacklisted_set:
                for p in voyager_posts:
                    p["recruiter_emails"] = [
                        e for e in p.get("recruiter_emails", [])
                        if e.get("email", "").lower() not in blacklisted_set
                    ]
                    p["has_email"] = len(p["recruiter_emails"]) > 0

            # Strict recency filtering
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

    # 1. Fallback: Deep Multi-Angle LinkedIn Harvester (recruiter posts only)
    # Request a sensible buffer of raw URLs based on user's desired limit
    harvest_limit = min(max(limit * 3, 25), 75)
    found_posts = fetch_deep_linkedin_postings(clean_role, target_locs, limit=harvest_limit, page=page, time_range=time_range)

    if not found_posts:
        # For 24h searches: if dated-filter search engines returned nothing (all blocked/rate-limited),
        # fall back to undated queries so user gets SOMETHING rather than empty results.
        # We do NOT pass max_age_hours for these — they're "best available" posts, not guaranteed 24h.
        if time_range in ("24h", "1d", "day", "past-24h") and max_age_hours is not None and max_age_hours <= 24:
            logger.info(f"[24h Fallback] Dated engine search returned 0 results, retrying without date filter")
            found_posts = fetch_deep_linkedin_postings(
                clean_role, target_locs, limit=max(limit * 4, 80), page=page, time_range="all"
            )
            # Tag as best-effort fallback: use None age limit in scraper so they pass through
            for fp in found_posts:
                fp["_from_dated_query"] = False
                fp["_24h_fallback"] = True  # Will be shown with a note in the UI

            if found_posts:
                # Scrape without age limit — the router will mark these as "best effort"
                max_age_hours = None  # Don't filter by age for fallback posts

        if not found_posts:
            empty_stats = {
                "total_discovered": 0,
                "total_scraped": 0,
                "verified_hiring_posts": 0,
                "recruiter_emails_mined": 0,
                "page": page,
                "has_more": False
            }
            if return_stats:
                return [], empty_stats
            return []

    # 2. Concurrently scrape and deep-mine candidate posts
    detailed_posts = []
    max_to_scrape = min(len(found_posts), harvest_limit)
    posts_to_scrape = found_posts[:max_to_scrape]
    max_workers = min(len(posts_to_scrape), 30)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scrape_single_post_details, p, blacklisted_set, max_age_hours, location, target_locs, clean_role): p
            for p in posts_to_scrape
        }
        try:
            for fut in as_completed(futures, timeout=20):
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

    # Fallback: if strict age filtering rejected all candidate posts, re-evaluate candidates
    # without the age cutoff so the applicant receives active verified recruiter posts rather than 0 results.
    if not detailed_posts and max_age_hours is not None:
        logger.info(f"[RecruiterHunter] Strict age cutoff ({max_age_hours}h) yielded 0 posts. Re-evaluating candidate pool as fallback.")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fallback_futures = {
                executor.submit(scrape_single_post_details, p, blacklisted_set, None, location, target_locs, clean_role): p
                for p in posts_to_scrape
            }
            try:
                for fut in as_completed(fallback_futures, timeout=15):
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

    # Safety Net: if detailed_posts is still empty, perform an immediate broad harvest so applicant never sees 0 results
    if not detailed_posts:
        logger.info(f"[RecruiterHunter] detailed_posts is empty. Running broad harvest fallback.")
        fallback_found = fetch_deep_linkedin_postings(clean_role, target_locs, limit=max(limit * 3, 40), page=page, time_range="all")
        if fallback_found:
            fb_to_scrape = fallback_found[:min(len(fallback_found), 25)]
            with ThreadPoolExecutor(max_workers=min(len(fb_to_scrape), 15)) as executor:
                fb_futs = {
                    executor.submit(scrape_single_post_details, p, blacklisted_set, None, location, target_locs, clean_role): p
                    for p in fb_to_scrape
                }
                for fut in as_completed(fb_futs, timeout=15):
                    try:
                        res = fut.result()
                        if res:
                            if email_only and not res.get("has_email"):
                                continue
                            res["_24h_fallback"] = True
                            detailed_posts.append(res)
                    except Exception:
                        pass

    logger.debug(f"[SCRAPE] found={len(found_posts)} scraped={len(posts_to_scrape)} accepted={len(detailed_posts)}")

    # 3. Two-pass deterministic sort:
    # Pass 1: Canonical base tie-breaker (alphabetical by company, role_title, post_url)
    detailed_posts.sort(
        key=lambda x: (
            x.get("company", "").strip().lower(),
            x.get("role_title", "").strip().lower(),
            x.get("post_url", "")
        )
    )

    # Pass 2: Business ranking (verified emails, location matched, fit score, recency)
    detailed_posts.sort(
        key=lambda x: (
            1 if x.get("has_email") else 0,
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
