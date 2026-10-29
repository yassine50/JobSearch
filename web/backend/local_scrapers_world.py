"""
Direct (no-Serper) scrapers for local job boards across MENA, North America, and APAC:
- Morocco (MA)    : ReKrute (rekrute.com), Emploi.ma (emploi.ma)
- Algeria (DZ)    : AlgerieJob (algeriejob.com)
- Australia (AU)  : SEEK API (seek.com.au)
- Singapore (SG)  : MyCareersFuture API (mycareersfuture.gov.sg)
- United States   : Dice (dice.com)
"""
from __future__ import annotations

import logging
import re
import unicodedata
import urllib.parse
from datetime import datetime, date, timedelta
from typing import Callable, Dict, List
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger("jobsearcher.local_scrapers_world")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}
JSON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_ROWS = 15

_GENERIC_ROLE_WORDS = {
    "developer", "developpeur", "engineer", "ingenieur",
    "software", "senior", "junior", "lead", "mid", "full", "stack", "fullstack",
    "frontend", "backend", "mobile", "web", "app", "application", "applications",
    "programmer", "programator", "specialist", "consultant", "stage", "intern",
    "hf", "fh", "mf",
}

_ROLE_EQUIV = {
    "developpeur": ("developpeur", "developer", "dev"),
    "developer": ("developpeur", "developer", "dev"),
    "ingenieur": ("ingenieur", "engineer"),
    "engineer": ("ingenieur", "engineer"),
}


def _fold(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _distinctive_tokens(query: str) -> List[str]:
    q_fold = _fold(query or "")
    raw = re.findall(r"[a-z0-9+#.]{2,}", q_fold)
    distinct = [t for t in raw if t not in _GENERIC_ROLE_WORDS]
    return distinct or raw


def _matches_query(query: str, *texts: str) -> bool:
    tokens = _distinctive_tokens(query)
    if not tokens:
        return True
    blob = _fold(" ".join(t or "" for t in texts))
    for tok in tokens:
        variants = _ROLE_EQUIV.get(tok, (tok,))
        if any(re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", blob) for v in variants):
            return True
    return False


def _iso_from_any(val: str) -> str:
    if not val:
        return ""
    s = str(val).strip()
    m_iso = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)
    m_dmy = re.search(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b", s)
    if m_dmy:
        try:
            return date(int(m_dmy.group(3)), int(m_dmy.group(2)), int(m_dmy.group(1))).isoformat()
        except Exception:
            pass
    low = s.lower()
    today = datetime.utcnow().date()
    if "today" in low or "aujourd" in low or "just posted" in low:
        return today.isoformat()
    if "yesterday" in low or "hier" in low:
        return (today - timedelta(days=1)).isoformat()
    m_d = re.search(r"(\d+)\s*(?:d|day|days|jour|jours)\s*ago", low)
    if m_d:
        return (today - timedelta(days=int(m_d.group(1)))).isoformat()
    m_h = re.search(r"(\d+)\s*(?:h|hr|hrs|hour|hours|heure|heures)\s*ago", low)
    if m_h:
        return today.isoformat()
    return s


# ─────────────────────────────────────────────────────────────────────────────
# 1. Morocco — ReKrute.com & Emploi.ma
# ─────────────────────────────────────────────────────────────────────────────

def scrape_rekrute_ma(query: str) -> List[dict]:
    """Direct scraper for ReKrute.com (Morocco)."""
    out: List[dict] = []
    q_clean = (query or "").strip()
    if not q_clean:
        return []
    first_w = _fold(q_clean.split()[0])
    search_kw = first_w if first_w not in _GENERIC_ROLE_WORDS else q_clean

    try:
        sess = requests.Session()
        sess.headers.update(HEADERS)
        # Set Morocco country scope in ReKrute session
        sess.get("https://www.rekrute.com/offres-emploi-maroc.html", timeout=4.0)
        r = sess.get(
            "https://www.rekrute.com/offres.html",
            params={"s": "1", "p": "1", "o": "1", "keyword": search_kw},
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li.post-id")
        if not items and first_w in ("flutter", "dart", "kotlin", "swift", "react", "angular", "vue", "python", "node", "nodejs"):
            r2 = sess.get(
                "https://www.rekrute.com/offres.html",
                params={"s": "1", "p": "1", "o": "1", "keyword": "developpeur"},
                timeout=4.2,
            )
            if r2.status_code == 200:
                soup = BeautifulSoup(r2.text, "html.parser")
                items = soup.select("li.post-id")
        seen = set()
        today = datetime.utcnow().date()
        for li in items:
            a = li.select_one("a.titreJob[href*='/offre-emploi-']")
            if not a:
                continue
            href = a["href"].split("?")[0].split("#")[0].strip()
            job_url = f"https://www.rekrute.com{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            seen.add(job_url)

            raw_title = a.get_text(" ", strip=True)
            parts = [p.strip() for p in raw_title.split("|") if p.strip()]
            title = parts[0] if parts else raw_title
            loc_part = parts[1] if len(parts) > 1 else "Casablanca, Maroc"
            # Skip non-Morocco postings if ReKrute mixes countries
            low_loc = loc_part.lower()
            if any(other in low_loc for other in ("tunisie", "tunis", "algérie", "alger", "sénégal", "dakar", "nairobi")):
                continue
            if "maroc" not in low_loc and "morocco" not in low_loc:
                loc_part = f"{loc_part}, Maroc"

            img = li.select_one("img.photo[alt]")
            company = (img.get("alt") or "").strip() if img else ""
            if company.lower() in ("confidentiel", "anonyme", "rekrute"):
                company = ""

            # Publication / expiry dates: Publication : du <span>28/10/2026</span> au <span>28/12/2026</span>
            date_spans = [sp.get_text(strip=True) for sp in li.select("em.date span")]
            date_posted = _iso_from_any(date_spans[0]) if date_spans else ""
            if len(date_spans) >= 2:
                exp_iso = _iso_from_any(date_spans[1])
                if exp_iso:
                    try:
                        if date.fromisoformat(exp_iso) < today:
                            continue
                    except Exception:
                        pass

            info_el = li.select_one("div.holder") or li.select_one("div.info")
            desc = info_el.get_text(" ", strip=True) if info_el else ""
            if not _matches_query(query, title, desc):
                continue

            out.append({
                "site": "rekrute",
                "title": title,
                "company": company,
                "location": loc_part,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc[:1500],
                "date_posted": date_posted,
                "is_remote": "télétravail" in (raw_title + " " + desc).lower() or "hybride" in desc.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[rekrute] {e}")
        return []
    return out


def _scrape_africawork_board(base_domain: str, path_prefix: str, site_id: str, country_label: str, query: str) -> List[dict]:
    """Shared direct scraper for Emploi.ma (Morocco) and AlgerieJob.com (Algeria)."""
    out: List[dict] = []
    try:
        r = requests.get(
            f"https://{base_domain}/{path_prefix}",
            params={"f[0]": "im_field_offre_metiers:31"},
            headers=HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for card in soup.select("div.card.card-job"):
            h3_a = card.select_one("h3 a[href]")
            if not h3_a:
                continue
            href = h3_a["href"].split("?")[0].strip()
            job_url = f"https://{base_domain}{href}" if href.startswith("/") else href
            if job_url in seen:
                continue

            title = h3_a.get_text(" ", strip=True)
            comp_el = card.select_one("a.card-job-company, .company-name")
            company = comp_el.get_text(" ", strip=True) if comp_el else ""
            desc_el = card.select_one("div.card-job-description")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
            ul_txt = " ".join(li.get_text(" ", strip=True) for li in card.select("ul li"))
            full_desc = f"{desc} {ul_txt}".strip()

            if not _matches_query(query, title, full_desc):
                continue
            seen.add(job_url)

            region = ""
            for li in card.select("ul li"):
                txt = li.get_text(" ", strip=True)
                if "région de" in txt.lower():
                    region = txt.split(":", 1)[-1].strip()
                    break
            location = f"{region}, {country_label}" if region else country_label

            t_el = card.select_one("time[datetime]")
            date_posted = _iso_from_any((t_el.get("datetime") or t_el.get_text(strip=True)) if t_el else "")

            out.append({
                "site": site_id,
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": full_desc[:1500],
                "date_posted": date_posted,
                "is_remote": "télétravail" in (title + " " + full_desc).lower() or "remote" in title.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[{site_id}] {e}")
        return []
    return out


def scrape_emploi_ma(query: str) -> List[dict]:
    return _scrape_africawork_board("www.emploi.ma", "recherche-jobs-maroc", "emploi.ma", "Maroc", query)


def scrape_algeriejob_dz(query: str) -> List[dict]:
    return _scrape_africawork_board("www.algeriejob.com", "recherche-jobs-algerie", "algeriejob", "Algérie", query)


# ─────────────────────────────────────────────────────────────────────────────
# 2. APAC — SEEK & JobStreet Official v5 JSON API (AU, NZ, MY, PH, ID, SG)
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_seek_market(
    host: str,
    site_key: str,
    country_code: str,
    country_label: str,
    site_name: str,
    job_path_prefix: str,
    query: str,
) -> List[dict]:
    """Unified JSON scraper for SEEK (AU, NZ) and JobStreet (MY, PH, ID, SG) v5 API."""
    out: List[dict] = []
    try:
        r = requests.get(
            f"https://{host}/api/jobsearch/v5/search",
            params={
                "siteKey": site_key,
                "keywords": query,
                "page": "1",
                "pageSize": "20",
            },
            headers=JSON_HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        items = (r.json() or {}).get("data") or []
        for it in items:
            jid = str(it.get("id") or "").strip()
            title = (it.get("title") or "").strip()
            if not jid or not title:
                continue
            locs = it.get("locations") or []
            if locs and isinstance(locs[0], dict):
                cc = (locs[0].get("countryCode") or country_code).upper()
                if cc and cc != country_code:
                    continue
                loc_label = (locs[0].get("label") or country_label).strip()
            else:
                loc_label = country_label
            if country_label.lower() not in loc_label.lower():
                loc_label = f"{loc_label}, {country_label}"

            company = (
                it.get("companyName")
                or (it.get("employer") or {}).get("name")
                or (it.get("advertiser") or {}).get("description")
                or ""
            ).strip()
            if company.lower() in ("private advertiser", "confidential", "company confidential"):
                company = f"Employer via {site_name}"

            teaser = (it.get("teaser") or "").strip()
            bullets = " · ".join(it.get("bulletPoints") or [])
            desc = f"{teaser} {bullets}".strip()
            sol_sec = ((it.get("solMetadata") or {}).get("section") or "MAIN").upper()
            is_ict = any(
                (c.get("classification") or {}).get("id") in ("6281", "6163")
                for c in (it.get("classifications") or [])
                if isinstance(c, dict)
            )
            if not _matches_query(query, title, desc, it.get("roleId") or "") and not (sol_sec == "MAIN" and is_ict):
                continue

            work_arr = ((it.get("workArrangements") or {}).get("displayText") or "").lower()
            job_url = f"https://{host}{job_path_prefix}{jid}"
            out.append({
                "site": site_name,
                "title": title,
                "company": company,
                "location": loc_label,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc[:1500] or f"{title} at {company} ({loc_label})",
                "date_posted": _iso_from_any(it.get("listingDate") or it.get("listingDateDisplay") or ""),
                "is_remote": "remote" in work_arr or "remote" in title.lower() or "work from home" in work_arr,
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[{site_name}] {e}")
        return []
    return out


def scrape_seek_au(query: str) -> List[dict]:
    return _scrape_seek_market("www.seek.com.au", "AU-Main", "AU", "Australia", "seek.com.au", "/job/", query)


def scrape_seek_nz(query: str) -> List[dict]:
    return _scrape_seek_market("www.seek.co.nz", "NZ-Main", "NZ", "New Zealand", "seek.co.nz", "/job/", query)


def scrape_jobstreet_my(query: str) -> List[dict]:
    return _scrape_seek_market("my.jobstreet.com", "MY-Main", "MY", "Malaysia", "jobstreet.my", "/job/", query)


def scrape_jobstreet_ph(query: str) -> List[dict]:
    return _scrape_seek_market("ph.jobstreet.com", "PH-Main", "PH", "Philippines", "jobstreet.ph", "/job/", query)


def scrape_jobstreet_id(query: str) -> List[dict]:
    return _scrape_seek_market("id.jobstreet.com", "ID-Main", "ID", "Indonesia", "jobstreet.id", "/id/job/", query)


def scrape_jobstreet_sg(query: str) -> List[dict]:
    return _scrape_seek_market("sg.jobstreet.com", "SG-Main", "SG", "Singapore", "jobstreet.sg", "/job/", query)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Singapore — MyCareersFuture Official API
# ─────────────────────────────────────────────────────────────────────────────

def scrape_mycareersfuture_sg(query: str) -> List[dict]:
    """Direct JSON scraper for MyCareersFuture Singapore (mycareersfuture.gov.sg)."""
    out: List[dict] = []
    try:
        r = requests.post(
            "https://api.mycareersfuture.gov.sg/v2/search?limit=15&page=0",
            json={"search": query, "sortBy": ["new_posting_date"]},
            headers={**JSON_HEADERS, "Content-Type": "application/json"},
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        results = (r.json() or {}).get("results") or []
        for it in results:
            uuid = (it.get("uuid") or "").strip()
            title = (it.get("title") or "").strip()
            if not uuid or not title:
                continue
            status_obj = it.get("status") or {}
            job_status = (status_obj.get("jobStatus") or "").lower()
            if "closed" in job_status or "expired" in job_status:
                continue

            company = (
                (it.get("hiringCompany") or {}).get("name")
                or (it.get("postedCompany") or {}).get("name")
                or ""
            ).strip()
            skills = ", ".join(
                s.get("skill", "") for s in (it.get("skills") or []) if isinstance(s, dict) and s.get("skill")
            )
            desc = f"{title} at {company}. Required skills: {skills}" if skills else f"{title} at {company}"
            if not _matches_query(query, title, skills):
                continue

            meta = it.get("metadata") or {}
            date_posted = _iso_from_any(meta.get("newPostingDate") or meta.get("updatedAt") or "")
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            job_url = f"https://www.mycareersfuture.gov.sg/job/{slug}-{uuid}"
            flex = " ".join(
                (f.get("flexibleWorkArrangement") if isinstance(f, dict) else str(f))
                for f in (it.get("flexibleWorkArrangements") or [])
            ).lower()

            out.append({
                "site": "mycareersfuture",
                "title": title,
                "company": company,
                "location": "Singapore",
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc[:1500],
                "date_posted": date_posted,
                "is_remote": "telecommuting" in flex or "remote" in title.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[mycareersfuture] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 4. United States — Dice.com
# ─────────────────────────────────────────────────────────────────────────────

def scrape_dice_us(query: str) -> List[dict]:
    """Direct HTML scraper for Dice.com (United States tech job board)."""
    out: List[dict] = []
    try:
        r = requests.get(
            "https://www.dice.com/jobs",
            params={"q": query, "countryCode": "US"},
            headers=HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for card in soup.select('[data-testid="job-card"]'):
            a = card.select_one('a[data-testid="job-search-job-detail-link"]') or card.select_one('a[href*="/job-detail/"]')
            if not a or not a.get("href"):
                continue
            href = a["href"].split("?")[0].strip()
            job_url = f"https://www.dice.com{href}" if href.startswith("/") else href
            if job_url in seen:
                continue

            title = a.get_text(" ", strip=True) or (a.get("aria-label") or "").replace("View Details for ", "").split("(")[0].strip()
            if not title:
                continue

            comp_el = card.select_one('p[data-testid="job-card-company-name"]') or card.select_one('a[href*="/company-profile/"]')
            company = comp_el.get_text(" ", strip=True) if comp_el else ""

            loc_raw = ""
            date_raw = ""
            extra_parts = []
            for p in card.find_all("p"):
                if p == comp_el:
                    continue
                ptxt = p.get_text(" ", strip=True)
                if not ptxt:
                    continue
                if "•" in ptxt and not loc_raw:
                    sp = [x.strip() for x in ptxt.split("•", 1)]
                    loc_raw = sp[0]
                    date_raw = sp[1] if len(sp) > 1 else ""
                else:
                    extra_parts.append(ptxt)

            desc = " · ".join(extra_parts)
            if not _matches_query(query, title, desc):
                continue
            seen.add(job_url)

            location = loc_raw or "United States"
            if "united states" not in location.lower() and "usa" not in location.lower():
                location = f"{location}, United States"

            out.append({
                "site": "dice",
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc[:1500] or f"{title} at {company} ({location})",
                "date_posted": _iso_from_any(date_raw),
                "is_remote": "remote" in location.lower() or "remote" in title.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[dice] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 5. South Korea (Wanted.co.kr API) & Japan (TokyoDev)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_wanted_kr(query: str) -> List[dict]:
    """Direct JSON scraper for Wanted.co.kr (South Korea's leading tech job board)."""
    out: List[dict] = []
    try:
        r = requests.get(
            "https://www.wanted.co.kr/api/chaos/search/v1/position",
            params={"query": query, "country": "kr", "limit": "15", "offset": "0"},
            headers={**JSON_HEADERS, "Referer": "https://www.wanted.co.kr/"},
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        items = ((r.json() or {}).get("data") or [])
        for it in items:
            jid = it.get("id")
            title = (it.get("position") or "").strip()
            if not jid or not title:
                continue
            comp = ((it.get("company") or {}).get("name") or "").strip()
            job_url = f"https://www.wanted.co.kr/wd/{jid}"
            out.append({
                "site": "wanted.co.kr",
                "title": title,
                "company": comp,
                "location": "Seoul, South Korea",
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": f"{title} at {comp} (Seoul, South Korea). Tech keyword: {query}.",
                "date_posted": "",
                "is_remote": "remote" in title.lower() or "재택" in title,
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[wanted.co.kr] {e}")
        return []
    return out


def scrape_tokyodev_jp(query: str) -> List[dict]:
    """Direct HTML scraper for TokyoDev.com (Japan tech jobs)."""
    out: List[dict] = []
    try:
        r = requests.get("https://www.tokyodev.com/jobs", headers=HEADERS, timeout=4.2)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select("a[href*='/companies/'][href*='/jobs/']"):
            href = a.get("href", "").split("?")[0].strip()
            if not re.match(r"^/companies/[^/]+/jobs/[^/]+$", href):
                continue
            job_url = f"https://www.tokyodev.com{href}"
            if job_url in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 3:
                continue
            m_comp = re.match(r"^/companies/([^/]+)/jobs/", href)
            comp_slug = m_comp.group(1).replace("-", " ").title() if m_comp else "TokyoDev Employer"
            li = a.find_parent("li") or a.find_parent("div")
            blob = li.get_text(" ", strip=True) if li else title
            if not _matches_query(query, title, blob, href):
                continue
            seen.add(job_url)
            out.append({
                "site": "tokyodev.com",
                "title": title,
                "company": comp_slug,
                "location": "Tokyo, Japan",
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": blob[:1500],
                "date_posted": "",
                "is_remote": "remote" in blob.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[tokyodev] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 6. Latin America — Computrabajo (MX, CO, AR, CL), GetOnBrd & Programathor (BR)
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_computrabajo(sub: str, country_label: str, query: str) -> List[dict]:
    """Direct HTML scraper for Computrabajo ({mx,co,ar,cl}.computrabajo.com)."""
    out: List[dict] = []
    q_slug = re.sub(r"[^a-z0-9]+", "-", _fold(query)).strip("-") or "developer"
    host = f"{sub}.computrabajo.com"
    try:
        r = requests.get(f"https://{host}/trabajo-de-{q_slug}", headers=HEADERS, timeout=4.2)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for art in soup.select("article.box_offer"):
            a = art.select_one("h2 a.js-o-link[href], a.js-o-link[href]")
            if not a or not a.get("href"):
                continue
            href = a["href"].split("?")[0].split("#")[0].strip()
            job_url = f"https://{host}{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(job_url)
            p_tags = art.select("p.fs16")
            company = p_tags[0].get_text(" ", strip=True) if p_tags else f"Empresa via Computrabajo"
            loc_raw = p_tags[1].get_text(" ", strip=True) if len(p_tags) > 1 else country_label
            if country_label.lower() not in loc_raw.lower():
                loc = f"{loc_raw}, {country_label}"
            else:
                loc = loc_raw
            if not _matches_query(query, title, art.get_text(" ", strip=True)):
                continue
            out.append({
                "site": f"computrabajo.{sub}",
                "title": title,
                "company": company,
                "location": loc,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": f"{title} at {company} ({loc})",
                "date_posted": "",
                "is_remote": "remoto" in loc.lower() or "remoto" in title.lower() or "home office" in title.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[computrabajo.{sub}] {e}")
        return []
    return out


def scrape_computrabajo_mx(query: str) -> List[dict]:
    return _scrape_computrabajo("mx", "Mexico", query)


def scrape_computrabajo_co(query: str) -> List[dict]:
    return _scrape_computrabajo("co", "Colombia", query)


def scrape_computrabajo_ar(query: str) -> List[dict]:
    return _scrape_computrabajo("ar", "Argentina", query)


def scrape_computrabajo_cl(query: str) -> List[dict]:
    return _scrape_computrabajo("cl", "Chile", query)


def _scrape_getonbrd(country_name: str, query: str) -> List[dict]:
    """Direct JSON API scraper for GetOnBrd (LATAM tech jobs)."""
    out: List[dict] = []
    try:
        r = requests.get(
            "https://www.getonbrd.com/api/v0/search/jobs",
            params={"query": query, "per_page": "20", "page": "1", "expand": '["company"]'},
            headers=JSON_HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        data = (r.json() or {}).get("data") or []
        for it in data:
            attrs = it.get("attributes") or {}
            title = (attrs.get("title") or "").strip()
            job_url = ((it.get("links") or {}).get("public_url") or "").strip()
            if not title or not job_url:
                continue
            countries = [str(c).lower() for c in (attrs.get("countries") or [])]
            if countries and country_name.lower() not in " ".join(countries) and not attrs.get("remote"):
                continue
            comp_data = ((attrs.get("company") or {}).get("data") or {}).get("attributes") or {}
            company = (comp_data.get("name") or "Employer via GetOnBrd").strip()
            desc = re.sub(r"<[^>]+>", " ", (attrs.get("description") or "") + " " + (attrs.get("functions") or ""))
            desc = re.sub(r"\s+", " ", desc).strip()
            if not _matches_query(query, title, desc):
                continue
            ts = attrs.get("published_at")
            date_iso = datetime.utcfromtimestamp(int(ts)).date().isoformat() if isinstance(ts, (int, float)) else ""
            out.append({
                "site": "getonbrd",
                "title": title,
                "company": company,
                "location": country_name,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc[:1500] or f"{title} at {company} ({country_name})",
                "date_posted": date_iso,
                "is_remote": bool(attrs.get("remote")),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[getonbrd/{country_name}] {e}")
        return []
    return out


def scrape_getonbrd_cl(query: str) -> List[dict]:
    return _scrape_getonbrd("Chile", query)


def scrape_getonbrd_co(query: str) -> List[dict]:
    return _scrape_getonbrd("Colombia", query)


def scrape_getonbrd_mx(query: str) -> List[dict]:
    return _scrape_getonbrd("Mexico", query)


def scrape_getonbrd_ar(query: str) -> List[dict]:
    return _scrape_getonbrd("Argentina", query)


def scrape_programathor_br(query: str) -> List[dict]:
    """Direct HTML scraper for Programathor.com.br (Brazil tech job board)."""
    out: List[dict] = []
    q_clean = _fold((query or "").strip()).split()[0] if (query or "").strip() else "developer"
    try:
        r = requests.get(f"https://programathor.com.br/jobs", params={"search": q_clean}, headers=HEADERS, timeout=4.2)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.select("a[href^='/jobs/']"):
            href = a.get("href", "").split("?")[0].strip()
            if not re.match(r"^/jobs/\d+-", href):
                continue
            if "vencida" in a.get_text(" ", strip=True).lower():
                continue
            job_url = f"https://programathor.com.br{href}"
            if job_url in seen:
                continue
            h3 = a.select_one("h3")
            title = h3.get_text(" ", strip=True) if h3 else a.get_text(" ", strip=True).split("  ")[0]
            title = re.sub(r"^NOVA\s+", "", title, flags=re.I).strip()
            if not title:
                continue
            seen.add(job_url)
            card_txt = a.get_text(" ", strip=True)
            if not _matches_query(query, title, card_txt):
                continue
            out.append({
                "site": "programathor.com.br",
                "title": title,
                "company": "Empresa via Programathor",
                "location": "São Paulo, Brazil",
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": card_txt[:1500],
                "date_posted": "",
                "is_remote": "remoto" in card_txt.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[programathor] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 7. Canada (Job Bank), South Africa (Careers24), Jordan (Akhtaboot)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_jobbank_ca(query: str) -> List[dict]:
    """Direct HTML scraper for Job Bank Canada (jobbank.gc.ca)."""
    out: List[dict] = []
    try:
        r = requests.get(
            "https://www.jobbank.gc.ca/jobsearch/jobsearch",
            params={"searchstring": query, "sort": "M"},
            headers=HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for art in soup.select("article[id^='article-']"):
            a = art.select_one("a.resultJobItem[href*='/jobsearch/jobposting/']")
            if not a or not a.get("href"):
                continue
            href = a["href"].split(";")[0].split("?")[0].strip()
            job_url = f"https://www.jobbank.gc.ca{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            seen.add(job_url)
            t_el = art.select_one("span.noctitle")
            title = t_el.get_text(" ", strip=True) if t_el else a.get_text(" ", strip=True)
            b_el = art.select_one("li.business")
            company = b_el.get_text(" ", strip=True) if b_el else "Employer via Job Bank"
            loc_el = art.select_one("li.location")
            loc_raw = loc_el.get_text(" ", strip=True).replace("Location", "").strip() if loc_el else "Canada"
            loc = f"{loc_raw}, Canada" if "canada" not in loc_raw.lower() else loc_raw
            d_el = art.select_one("li.date")
            date_posted = _iso_from_any(d_el.get_text(" ", strip=True) if d_el else "")
            desc = f"{title} at {company} ({loc}) — {query}"
            out.append({
                "site": "jobbank.gc.ca",
                "title": title,
                "company": company,
                "location": loc,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": desc,
                "date_posted": date_posted,
                "is_remote": "telework" in art.get_text(" ", strip=True).lower() or "remote" in title.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[jobbank.gc.ca] {e}")
        return []
    return out


def scrape_careers24_za(query: str) -> List[dict]:
    """Direct HTML scraper for Careers24 South Africa (careers24.com)."""
    out: List[dict] = []
    q_slug = re.sub(r"[^a-z0-9]+", "-", _fold(query)).strip("-") or "developer"
    try:
        r = requests.get(
            f"https://www.careers24.com/jobs/kw-{q_slug}/rmt-incl/",
            headers=HEADERS,
            timeout=4.2,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for card in soup.select("div.job-card"):
            a = card.select_one("a[data-control='vacancy-title'][href*='/jobs/adverts/']") or card.select_one("a[href*='/jobs/adverts/']")
            if not a or not a.get("href"):
                continue
            href = a["href"].split("?")[0].strip()
            job_url = f"https://www.careers24.com{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            h2 = a.select_one("h2")
            title = h2.get_text(" ", strip=True) if h2 else a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(job_url)
            lis = [li.get_text(" ", strip=True) for li in card.select("ul li")]
            loc_raw = lis[0] if lis else "Johannesburg"
            loc = f"{loc_raw}, South Africa" if "south africa" not in loc_raw.lower() else loc_raw
            posted_raw = next((x.replace("Posted:", "").strip() for x in lis if "posted:" in x.lower()), "")
            if not _matches_query(query, title, " ".join(lis)):
                continue
            out.append({
                "site": "careers24.com",
                "title": title,
                "company": "Employer via Careers24",
                "location": loc,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": f"{title} ({loc}) · {' · '.join(lis)}",
                "date_posted": _iso_from_any(posted_raw),
                "is_remote": "remote" in title.lower() or "remote" in loc.lower(),
            })
            if len(out) >= MAX_ROWS:
                break
    except Exception as e:
        logger.debug(f"[careers24] {e}")
        return []
    return out


def scrape_akhtaboot_jo(query: str) -> List[dict]:
    """Direct HTML scraper for Akhtaboot Jordan (akhtaboot.com)."""
    out: List[dict] = []
    try:
        seen = set()
        for kw_attempt in (query, "software", "engineer"):
            r = requests.get(
                "https://www.akhtaboot.com/en/jordan/jobs",
                params={"search[query]": kw_attempt},
                headers=HEADERS,
                timeout=4.2,
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href^='/en/jordan/jobs/']"):
                href = a.get("href", "").split("?")[0].strip()
                if not re.search(r"^/en/jordan/jobs/[^/]+/\d+-", href):
                    continue
                job_url = f"https://www.akhtaboot.com{href}"
                if job_url in seen:
                    continue
                title = a.get_text(" ", strip=True)
                if not title or len(title) < 3:
                    continue
                m_at = re.search(r"-at-([A-Za-z0-9\-]+)$", urllib.parse.unquote(href))
                company = m_at.group(1).replace("-", " ").strip() if m_at else "Employer via Akhtaboot"
                card = a.find_parent(["div", "article", "li"]) or a.parent
                blob = card.get_text(" ", strip=True) if card else title
                if not _matches_query(kw_attempt, title, blob, href):
                    continue
                seen.add(job_url)
                desc = f"{title} at {company} (Amman, Jordan) — {blob[:800]} ({query})"
                out.append({
                    "site": "akhtaboot.com",
                    "title": title,
                    "company": company,
                    "location": "Amman, Jordan",
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": desc[:1500],
                    "date_posted": "",
                    "is_remote": "remote" in title.lower(),
                })
                if len(out) >= MAX_ROWS:
                    break
            if out:
                break
    except Exception as e:
        logger.debug(f"[akhtaboot] {e}")
        return []
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

DIRECT_SCRAPERS: Dict[str, List[Callable[[str], List[dict]]]] = {
    "morocco": [scrape_rekrute_ma, scrape_emploi_ma],
    "algeria": [scrape_algeriejob_dz],
    "jordan": [scrape_akhtaboot_jo],
    "australia": [scrape_seek_au],
    "new zealand": [scrape_seek_nz],
    "malaysia": [scrape_jobstreet_my],
    "philippines": [scrape_jobstreet_ph],
    "indonesia": [scrape_jobstreet_id],
    "singapore": [scrape_mycareersfuture_sg, scrape_jobstreet_sg],
    "south korea": [scrape_wanted_kr],
    "japan": [scrape_tokyodev_jp],
    "mexico": [scrape_computrabajo_mx, scrape_getonbrd_mx],
    "colombia": [scrape_computrabajo_co, scrape_getonbrd_co],
    "argentina": [scrape_computrabajo_ar, scrape_getonbrd_ar],
    "chile": [scrape_computrabajo_cl, scrape_getonbrd_cl],
    "brazil": [scrape_programathor_br],
    "canada": [scrape_jobbank_ca],
    "south africa": [scrape_careers24_za],
    "usa": [scrape_dice_us],
}

__all__ = ["DIRECT_SCRAPERS"] + [f.__name__ for fs in DIRECT_SCRAPERS.values() for f in fs]
