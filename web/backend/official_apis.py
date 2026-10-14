"""
Free official job-search APIs — real APIs with keys, so they are never blocked.

Providers (each is skipped silently when its key is missing)
---------
adzuna    : https://developer.adzuna.com      — ADZUNA_APP_ID + ADZUNA_APP_KEY  (~19 countries)
jooble    : https://jooble.org/api/about       — JOOBLE_API_KEY                  (worldwide)
careerjet : https://www.careerjet.com/partners — CAREERJET_AFFID                 (worldwide incl. MA/AE/FR)

Keys are read from environment variables first, then from scraper_config.json
(lower-case names, e.g. "adzuna_app_id"). They are server-side only — users never see them.
Rows are shaped like open_sources._row so they flow through the normal search pipeline.
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, wait
from typing import List, Optional

import requests

from .open_sources import _get, _row, _iso_date, html_to_text, HEADERS, TIMEOUT

logger = logging.getLogger("jobsearcher.official_apis")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "scraper_config.json")
KEY_NAMES = ["adzuna_app_id", "adzuna_app_key", "jooble_api_key", "careerjet_affid",
             "google_client_id", "google_client_secret"]


def get_key(name: str) -> str:
    v = os.getenv(name.upper(), "")
    if v:
        return v.strip()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return str(json.load(f).get(name, "") or "").strip()
    except Exception:
        return ""


def configured_providers() -> List[str]:
    out = []
    if get_key("adzuna_app_id") and get_key("adzuna_app_key"):
        out.append("adzuna")
    if get_key("jooble_api_key"):
        out.append("jooble")
    if get_key("careerjet_affid"):
        out.append("careerjet")
    return out


# ── country mapping ────────────────────────────────────────────────────────────
_ADZUNA = {
    "uk": "gb", "united kingdom": "gb", "gb": "gb", "usa": "us", "us": "us", "united states": "us",
    "canada": "ca", "germany": "de", "france": "fr", "netherlands": "nl", "spain": "es",
    "italy": "it", "belgium": "be", "switzerland": "ch", "austria": "at", "poland": "pl",
    "australia": "au", "new zealand": "nz", "singapore": "sg", "india": "in", "brazil": "br",
    "mexico": "mx", "south africa": "za",
}
_CAREERJET = {
    "uk": "en_GB", "united kingdom": "en_GB", "usa": "en_US", "us": "en_US", "united states": "en_US",
    "canada": "en_CA", "germany": "de_DE", "france": "fr_FR", "netherlands": "nl_NL", "spain": "es_ES",
    "italy": "it_IT", "belgium": "fr_BE", "switzerland": "de_CH", "austria": "de_AT", "poland": "pl_PL",
    "australia": "en_AU", "singapore": "en_SG", "india": "en_IN", "uae": "en_AE",
    "united arab emirates": "en_AE", "morocco": "fr_MA", "tunisia": "fr_TN", "saudi arabia": "en_SA",
    "qatar": "en_QA", "ireland": "en_IE", "south africa": "en_ZA",
}
_WORLDWIDE = ("", "worldwide", "global", "all", "remote")


def _is_ww(country: str) -> bool:
    return (country or "").strip().lower() in _WORLDWIDE


# ── providers ──────────────────────────────────────────────────────────────────
def _adzuna(query: str, country: str, location: str, hours_old: Optional[int]) -> List[dict]:
    app_id, app_key = get_key("adzuna_app_id"), get_key("adzuna_app_key")
    if not (app_id and app_key):
        return []
    c = (country or "").strip().lower()
    codes = ["us", "gb"] if _is_ww(c) else ([_ADZUNA[c]] if c in _ADZUNA else [])
    rows: List[dict] = []
    for code in codes:
        params = {"app_id": app_id, "app_key": app_key, "what": query, "results_per_page": 50,
                  "content-type": "application/json"}
        if location and not _is_ww(location):
            params["where"] = location
        if hours_old:
            params["max_days_old"] = max(1, round(hours_old / 24))
        data = _get(f"https://api.adzuna.com/v1/api/jobs/{code}/search/1", params=params) or {}
        for j in data.get("results", []):
            rows.append(_row(
                "adzuna", j.get("title", ""), (j.get("company") or {}).get("display_name", ""),
                (j.get("location") or {}).get("display_name", ""), j.get("redirect_url", ""),
                description=html_to_text(j.get("description", "")), date_posted=_iso_date(j.get("created")),
                min_amount=j.get("salary_min"), max_amount=j.get("salary_max"),
            ))
    return rows


def _jooble(query: str, country: str, location: str, hours_old: Optional[int]) -> List[dict]:
    key = get_key("jooble_api_key")
    if not key:
        return []
    where = location if location and not _is_ww(location) else ("" if _is_ww(country) else country)
    r = requests.post(f"https://jooble.org/api/{key}", json={"keywords": query, "location": where,
                      "page": "1", "ResultOnPage": "50"}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    rows = []
    for j in (r.json() or {}).get("jobs", []):
        rows.append(_row(
            "jooble", html_to_text(j.get("title", "")), j.get("company", ""), j.get("location", ""),
            j.get("link", ""), description=html_to_text(j.get("snippet", "")),
            date_posted=_iso_date(j.get("updated")),
            is_remote="remote" in (j.get("location", "") + j.get("type", "")).lower(),
        ))
    return rows


def _careerjet(query: str, country: str, location: str, hours_old: Optional[int]) -> List[dict]:
    affid = get_key("careerjet_affid")
    if not affid:
        return []
    c = (country or "").strip().lower()
    locale = "en_US" if _is_ww(c) else _CAREERJET.get(c, "en_GB")
    params = {"locale_code": locale, "keywords": query, "affid": affid, "pagesize": 50,
              "user_ip": "1.1.1.1", "user_agent": HEADERS["User-Agent"], "sort": "date"}
    if location and not _is_ww(location):
        params["location"] = location
    data = _get("http://public.api.careerjet.net/search", params=params) or {}
    rows = []
    for j in data.get("jobs", []):
        rows.append(_row(
            "careerjet", j.get("title", ""), j.get("company", ""), j.get("locations", ""), j.get("url", ""),
            description=html_to_text(j.get("description", "")), date_posted=_iso_date(j.get("date")),
            min_amount=j.get("salary_min"), max_amount=j.get("salary_max"),
        ))
    return rows


PROVIDERS = {"adzuna": _adzuna, "jooble": _jooble, "careerjet": _careerjet}


def fetch_official(query: str, country: str = "", location: str = "",
                   hours_old: Optional[int] = None) -> List[dict]:
    """Query every configured provider in parallel; failures are logged and skipped."""
    active = configured_providers()
    if not active:
        return []
    rows: List[dict] = []
    ex = ThreadPoolExecutor(max_workers=len(active))
    futs = {ex.submit(PROVIDERS[p], query, country, location, hours_old): p for p in active}
    wait(futs, timeout=15)
    for f, name in futs.items():
        if f.done() and not f.exception():
            rows.extend(f.result())
        elif f.done():
            logger.info(f"[OfficialAPIs] {name} failed: {f.exception()}")
    ex.shutdown(wait=False, cancel_futures=True)
    return rows
