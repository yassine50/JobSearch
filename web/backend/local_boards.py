"""
Country-Specific Local Job Boards Scraper & Discovery Engine
============================================================
Automatically scrapes and discovers verified single job postings from each country's
top local job boards when the user selects a target country:

- Tunisia (TN)      : Tanitjobs (tanitjobs.com), Keejob (keejob.com), OptionCarriere TN
- Romania (RO)      : eJobs (ejobs.ro), BestJobs (bestjobs.eu), Hipo (hipo.ro), DevJob (devjob.ro)
- France (FR)       : Welcome to the Jungle (welcometothejungle.com), APEC (apec.fr),
                      HelloWork (hellowork.com), Free-Work (free-work.com)
- Morocco (MA)      : ReKrute (rekrute.com), Emploi.ma (emploi.ma)
- Algeria (DZ)      : Emploitic (emploitic.com), AlgerieJob (algeriejob.com)
- Germany (DE)      : StepStone (stepstone.de), XING (xing.com), GermanTechJobs (germantechjobs.de)
- United Kingdom    : Reed (reed.co.uk), CWJobs (cwjobs.co.uk), Totaljobs (totaljobs.com), DevITJobs UK
- Netherlands (NL)  : Nationale Vacaturebank, Intermediair, DevITJobs NL
- Switzerland (CH)  : Jobs.ch (jobs.ch), JobUp.ch (jobup.ch), SwissDevJobs (swissdevjobs.ch)
- Spain (ES)        : InfoJobs (infojobs.net), Tecnoempleo (tecnoempleo.com)
- Poland (PL)       : JustJoin.it (justjoin.it), NoFluffJobs (nofluffjobs.com), Pracuj.pl (pracuj.pl)
- Portugal (PT)     : ITJobs.pt (itjobs.pt)
- Italy (IT)        : InfoJobs.it (infojobs.it), iProgrammatori (iprogrammatori.it)
- Belgium (BE)      : StepStone.be (stepstone.be)
- Austria (AT)      : Karriere.at (karriere.at)
- Ireland (IE)      : IrishJobs.ie (irishjobs.ie)
- Nordics           : The Hub (thehub.io), Jobindex.dk, FINN.no, Duunitori.fi
- UAE / KSA / Qatar : GulfTalent (gulftalent.com), Bayt (bayt.com), NaukriGulf (naukrigulf.com)
- Egypt (EG)        : Wuzzuf (wuzzuf.net)
- USA / Canada      : BuiltIn (builtin.com), Dice (dice.com), Job Bank Canada
- India / APAC      : Naukri (naukri.com), Instahyre, SEEK (seek.com.au), MyCareersFuture SG
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import urllib.parse
from urllib.parse import urlparse, unquote, quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("jobsearcher.local_boards")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7,ro;q=0.6",
}

_LOCAL_SESSION = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
_LOCAL_SESSION.mount("https://", _adapter)
_LOCAL_SESSION.mount("http://", _adapter)

_LOCAL_POOL = ThreadPoolExecutor(max_workers=32)

FRENCH_MONTHS = {
    "janvier": 1, "janv": 1, "février": 2, "fevrier": 2, "févr": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7,
    "août": 8, "aout": 8, "septembre": 9, "sept": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "décembre": 12, "decembre": 12, "déc": 12,
}


def _parse_local_date(raw: str) -> str:
    """Convert DD/MM/YYYY, ISO, or relative/French dates into YYYY-MM-DD."""
    if not raw:
        return ""
    s = raw.strip()
    low = s.lower()
    today = datetime.now().date()
    m_iso = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)
    if "aujourd" in low or "today" in low or "azi" in low or "just now" in low:
        return today.isoformat()
    if "hier" in low or "yesterday" in low or "ieri" in low:
        return (today - timedelta(days=1)).isoformat()
    m_rel_d = re.search(r"(\d+)\s*\+?\s*(?:d|day|days|jour|jours)\b", low)
    if m_rel_d:
        days_n = min(int(m_rel_d.group(1)), 5) if "30+" in low else int(m_rel_d.group(1))
        return (today - timedelta(days=days_n)).isoformat()
    m_rel_h = re.search(r"(\d+)\s*\+?\s*(?:h|hr|hrs|hour|hours|heure|heures)\b", low)
    if m_rel_h:
        return today.isoformat()
    # DD/MM/YYYY
    m_dmy = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s)
    if m_dmy:
        try:
            d, mo, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
            return date(y, mo, d).isoformat()
        except Exception:
            pass
    # DD.MM.YYYY or DD-MM-YYYY
    m_dot = re.search(r"\b(\d{1,2})[.\-](\d{1,2})[.\-](\d{4})\b", s)
    if m_dot:
        try:
            d, mo, y = int(m_dot.group(1)), int(m_dot.group(2)), int(m_dot.group(3))
            return date(y, mo, d).isoformat()
        except Exception:
            pass
    # French "16 octobre" or "16 octobre 2026"
    m_fr = re.search(r"\b(\d{1,2})\s+([a-zéûô]+)(?:\s+(\d{4}))?\b", low)
    if m_fr:
        day_num = int(m_fr.group(1))
        mo_name = m_fr.group(2).rstrip(".")
        yr_num = int(m_fr.group(3)) if m_fr.group(3) else today.year
        mo_num = FRENCH_MONTHS.get(mo_name)
        if mo_num:
            try:
                cand = date(yr_num, mo_num, day_num)
                if cand > today and not m_fr.group(3):
                    cand = date(yr_num - 1, mo_num, day_num)
                return cand.isoformat()
            except Exception:
                pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Country Local Boards Registry
# ─────────────────────────────────────────────────────────────────────────────

COUNTRY_LOCAL_BOARDS: Dict[str, dict] = {
    "tunisia": {
        "gl": "tn",
        "country_label": "Tunisie",
        "boards": ["Tanitjobs", "Keejob", "OptionCarriere TN"],
        "serper_clauses": [
            "site:tanitjobs.com/job/",
            "site:keejob.com/offres-emploi/",
            "site:optioncarriere.tn/jobview/",
        ],
    },
    "romania": {
        "gl": "ro",
        "country_label": "Romania",
        "boards": ["eJobs.ro", "BestJobs.eu", "Hipo.ro", "DevJob.ro"],
        "serper_clauses": [
            "site:ejobs.ro/user/locuri-de-munca/",
            "site:bestjobs.eu/ro/loc-de-munca/",
            "site:bestjobs.eu/en/job/",
            "site:hipo.ro/locuri-de-munca/locuri_de_munca/",
            "site:devjob.ro/en/jobs/",
        ],
    },
    "france": {
        "gl": "fr",
        "country_label": "France",
        "boards": ["Welcome to the Jungle", "APEC", "HelloWork", "Free-Work"],
        "serper_clauses": [
            "site:welcometothejungle.com/fr/companies/",
            "site:apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/",
            "site:hellowork.com/fr-fr/emplois/",
            "site:free-work.com/fr/tech-it/",
        ],
    },
    "morocco": {
        "gl": "ma",
        "country_label": "Morocco",
        "boards": ["ReKrute", "Emploi.ma"],
        "serper_clauses": [
            "site:rekrute.com/offre-emploi-",
            "site:emploi.ma/offre-emploi-maroc/",
        ],
    },
    "algeria": {
        "gl": "dz",
        "country_label": "Algérie",
        "boards": ["Emploitic", "AlgerieJob"],
        "serper_clauses": [
            "site:emploitic.com/offres-d-emploi/",
            "site:emploitic.com/entreprises/",
            "site:algeriejob.com/offre-emploi-algerie/",
        ],
    },
    "germany": {
        "gl": "de",
        "country_label": "Germany",
        "boards": ["StepStone.de", "XING Jobs", "GermanTechJobs"],
        "serper_clauses": [
            "site:stepstone.de/stellenangebote--",
            "site:xing.com/jobs/",
            "site:germantechjobs.de/jobs/",
        ],
    },
    "uk": {
        "gl": "uk",
        "country_label": "United Kingdom",
        "boards": ["Reed.co.uk", "CWJobs", "Totaljobs", "DevITJobs UK"],
        "serper_clauses": [
            "site:reed.co.uk/jobs/",
            "site:cwjobs.co.uk/job/",
            "site:totaljobs.com/job/",
            "site:devitjobs.uk/jobs/",
        ],
    },
    "netherlands": {
        "gl": "nl",
        "country_label": "Netherlands",
        "boards": ["Nationale Vacaturebank", "Intermediair", "DevITJobs NL"],
        "serper_clauses": [
            "site:nationalevacaturebank.nl/vacature/",
            "site:intermediair.nl/vacature/",
            "site:devitjobs.nl/jobs/",
        ],
    },
    "switzerland": {
        "gl": "ch",
        "country_label": "Switzerland",
        "boards": ["Jobs.ch", "JobUp.ch", "SwissDevJobs"],
        "serper_clauses": [
            "site:jobs.ch/en/vacancies/detail/",
            "site:jobs.ch/de/stellenangebote/detail/",
            "site:jobup.ch/fr/emplois/detail/",
            "site:swissdevjobs.ch/jobs/",
        ],
    },
    "spain": {
        "gl": "es",
        "country_label": "Spain",
        "boards": ["InfoJobs", "Tecnoempleo"],
        "serper_clauses": [
            "site:tecnoempleo.com/",
            "site:infojobs.net/",
        ],
    },
    "poland": {
        "gl": "pl",
        "country_label": "Poland",
        "boards": ["JustJoin.it", "NoFluffJobs", "Pracuj.pl"],
        "serper_clauses": [
            "site:justjoin.it/job-offer/",
            "site:nofluffjobs.com/pl/job/",
            "site:pracuj.pl/praca/",
        ],
    },
    "portugal": {
        "gl": "pt",
        "country_label": "Portugal",
        "boards": ["ITJobs.pt", "Net-Empregos"],
        "serper_clauses": [
            "site:itjobs.pt/oferta/",
            "site:net-empregos.com/",
        ],
    },
    "italy": {
        "gl": "it",
        "country_label": "Italy",
        "boards": ["InfoJobs.it", "iProgrammatori"],
        "serper_clauses": [
            "site:infojobs.it/offerta-lavoro/",
            "site:iprogrammatori.it/lavoro-informatica/",
        ],
    },
    "belgium": {
        "gl": "be",
        "country_label": "Belgium",
        "boards": ["StepStone.be", "References.be"],
        "serper_clauses": [
            "site:stepstone.be/offres-d-emploi--",
            "site:stepstone.be/vacatures--",
        ],
    },
    "austria": {
        "gl": "at",
        "country_label": "Austria",
        "boards": ["Karriere.at", "DerStandard Jobs"],
        "serper_clauses": [
            "site:karriere.at/jobs/",
        ],
    },
    "ireland": {
        "gl": "ie",
        "country_label": "Ireland",
        "boards": ["IrishJobs.ie", "Jobs.ie"],
        "serper_clauses": [
            "site:irishjobs.ie/job/",
            "site:jobs.ie/job/",
        ],
    },
    "sweden": {
        "gl": "se",
        "country_label": "Sweden",
        "boards": ["The Hub Sweden", "Platsbanken"],
        "serper_clauses": ["site:thehub.io/jobs/"],
    },
    "denmark": {
        "gl": "dk",
        "country_label": "Denmark",
        "boards": ["Jobindex.dk", "The Hub Denmark"],
        "serper_clauses": ["site:jobindex.dk/jobannonce/", "site:thehub.io/jobs/"],
    },
    "norway": {
        "gl": "no",
        "country_label": "Norway",
        "boards": ["FINN.no", "The Hub Norway"],
        "serper_clauses": ["site:finn.no/job/fulltime/ad.html", "site:thehub.io/jobs/"],
    },
    "finland": {
        "gl": "fi",
        "country_label": "Finland",
        "boards": ["Duunitori.fi", "The Hub Finland"],
        "serper_clauses": ["site:duunitori.fi/tyopaikat/tyo/", "site:thehub.io/jobs/"],
    },
    "uae": {
        "gl": "ae",
        "country_label": "United Arab Emirates",
        "boards": ["GulfTalent UAE", "Bayt UAE", "NaukriGulf"],
        "serper_clauses": [
            "site:gulftalent.com/uae/jobs/",
            "site:bayt.com/en/uae/jobs/",
            "site:naukrigulf.com/",
        ],
    },
    "saudi arabia": {
        "gl": "sa",
        "country_label": "Saudi Arabia",
        "boards": ["GulfTalent KSA", "Bayt KSA", "NaukriGulf"],
        "serper_clauses": [
            "site:gulftalent.com/saudi-arabia/jobs/",
            "site:bayt.com/en/saudi-arabia/jobs/",
            "site:naukrigulf.com/",
        ],
    },
    "qatar": {
        "gl": "qa",
        "country_label": "Qatar",
        "boards": ["GulfTalent Qatar", "Bayt Qatar"],
        "serper_clauses": [
            "site:gulftalent.com/qatar/jobs/",
            "site:bayt.com/en/qatar/jobs/",
        ],
    },
    "egypt": {
        "gl": "eg",
        "country_label": "Egypt",
        "boards": ["Wuzzuf", "Bayt Egypt"],
        "serper_clauses": [
            "site:wuzzuf.net/jobs/p/",
            "site:bayt.com/en/egypt/jobs/",
        ],
    },
    "usa": {
        "gl": "us",
        "country_label": "United States",
        "boards": ["BuiltIn", "Dice"],
        "serper_clauses": [
            "site:builtin.com/job/",
            "site:dice.com/job-detail/",
        ],
    },
    "canada": {
        "gl": "ca",
        "country_label": "Canada",
        "boards": ["Job Bank Canada", "Workopolis"],
        "serper_clauses": [
            "site:jobbank.gc.ca/jobsearch/jobposting/",
        ],
    },
    "india": {
        "gl": "in",
        "country_label": "India",
        "boards": ["Naukri.com", "Instahyre"],
        "serper_clauses": [
            "site:naukri.com/job-listings-",
            "site:instahyre.com/job-",
        ],
    },
    "australia": {
        "gl": "au",
        "country_label": "Australia",
        "boards": ["SEEK Australia"],
        "serper_clauses": [
            "site:seek.com.au/job/",
        ],
    },
    "singapore": {
        "gl": "sg",
        "country_label": "Singapore",
        "boards": ["MyCareersFuture SG", "JobStreet SG"],
        "serper_clauses": [
            "site:mycareersfuture.gov.sg/job/",
            "site:sg.jobstreet.com/job/",
            "site:jobstreet.com.sg/job/",
        ],
    },
    "new zealand": {
        "gl": "nz",
        "country_label": "New Zealand",
        "boards": ["SEEK New Zealand", "Trade Me Jobs"],
        "serper_clauses": [
            "site:seek.co.nz/job/",
            "site:trademe.co.nz/a/jobs/",
        ],
    },
    "malaysia": {
        "gl": "my",
        "country_label": "Malaysia",
        "boards": ["JobStreet Malaysia", "Hiredly"],
        "serper_clauses": [
            "site:my.jobstreet.com/job/",
            "site:hiredly.com/jobs/",
        ],
    },
    "philippines": {
        "gl": "ph",
        "country_label": "Philippines",
        "boards": ["JobStreet Philippines", "Kalibrr", "Bossjob"],
        "serper_clauses": [
            "site:ph.jobstreet.com/job/",
            "site:kalibrr.com/c/",
            "site:bossjob.ph/en-us/job/",
        ],
    },
    "indonesia": {
        "gl": "id",
        "country_label": "Indonesia",
        "boards": ["JobStreet Indonesia", "Glints", "Kalibrr"],
        "serper_clauses": [
            "site:id.jobstreet.com/id/job/",
            "site:glints.com/id/opportunities/jobs/",
            "site:kalibrr.com/c/",
        ],
    },
    "japan": {
        "gl": "jp",
        "country_label": "Japan",
        "boards": ["TokyoDev", "Japan Dev", "Daijob", "CareerCross"],
        "serper_clauses": [
            "site:tokyodev.com/companies/",
            "site:japan-dev.com/jobs/",
            "site:daijob.com/en/jobs/detail/",
            "site:careercross.com/en/job/",
        ],
    },
    "south korea": {
        "gl": "kr",
        "country_label": "South Korea",
        "boards": ["Wanted.co.kr", "Saramin", "JobKorea"],
        "serper_clauses": [
            "site:wanted.co.kr/wd/",
            "site:saramin.co.kr/zf_user/jobs/relay/view",
            "site:jobkorea.co.kr/Recruit/GI_Read/",
        ],
    },
    "mexico": {
        "gl": "mx",
        "country_label": "Mexico",
        "boards": ["Computrabajo MX", "OCCMundial", "GetOnBrd"],
        "serper_clauses": [
            "site:mx.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-",
            "site:occ.com.mx/empleo/oferta/",
            "site:getonbrd.com/jobs/",
        ],
    },
    "brazil": {
        "gl": "br",
        "country_label": "Brazil",
        "boards": ["Programathor", "Gupy", "Vagas.com.br"],
        "serper_clauses": [
            "site:programathor.com.br/jobs/",
            "site:gupy.io/jobs/",
            "site:vagas.com.br/vagas-de-",
        ],
    },
    "argentina": {
        "gl": "ar",
        "country_label": "Argentina",
        "boards": ["Computrabajo AR", "Bumeran", "GetOnBrd"],
        "serper_clauses": [
            "site:ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-",
            "site:bumeran.com.ar/empleos/",
            "site:getonbrd.com/jobs/",
        ],
    },
    "colombia": {
        "gl": "co",
        "country_label": "Colombia",
        "boards": ["Computrabajo CO", "Elempleo", "GetOnBrd"],
        "serper_clauses": [
            "site:co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-",
            "site:elempleo.com/co/ofertas-trabajo/",
            "site:getonbrd.com/jobs/",
        ],
    },
    "chile": {
        "gl": "cl",
        "country_label": "Chile",
        "boards": ["GetOnBrd", "Computrabajo CL", "Laborum", "ChileTrabajos"],
        "serper_clauses": [
            "site:getonbrd.com/jobs/",
            "site:cl.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-",
            "site:laborum.cl/empleos/",
            "site:chiletrabajos.cl/trabajo/",
        ],
    },
    "czech republic": {
        "gl": "cz",
        "country_label": "Czech Republic",
        "boards": ["Jobs.cz", "StartupJobs.cz", "Prace.cz"],
        "serper_clauses": [
            "site:jobs.cz/rpd/",
            "site:startupjobs.cz/nabidka/",
            "site:prace.cz/nabidka/",
        ],
    },
    "hungary": {
        "gl": "hu",
        "country_label": "Hungary",
        "boards": ["NoFluffJobs HU", "Profession.hu", "DreamJo.bs"],
        "serper_clauses": [
            "site:nofluffjobs.com/hu/job/",
            "site:profession.hu/allas/",
            "site:dreamjo.bs/hu/job/",
            "site:dreamjo.bs/en/job/",
        ],
    },
    "bulgaria": {
        "gl": "bg",
        "country_label": "Bulgaria",
        "boards": ["Dev.bg", "Jobs.bg"],
        "serper_clauses": [
            "site:dev.bg/company/jobads/",
            "site:jobs.bg/job/",
        ],
    },
    "greece": {
        "gl": "gr",
        "country_label": "Greece",
        "boards": ["Skywalker.gr", "Kariera.gr"],
        "serper_clauses": [
            "site:skywalker.gr/el/aggelia-ergasias/",
            "site:kariera.gr/%CE%B1%CE%B3%CE%B3%CE%B5%CE%BB%CE%AF%CE%B5%CF%82/",
            "site:kariera.gr/en/jobs/",
        ],
    },
    "croatia": {
        "gl": "hr",
        "country_label": "Croatia",
        "boards": ["MojPosao.net", "Adorio"],
        "serper_clauses": [
            "site:moj-posao.net/Posao/",
        ],
    },
    "turkey": {
        "gl": "tr",
        "country_label": "Turkey",
        "boards": ["Kariyer.net", "Yenibiris"],
        "serper_clauses": [
            "site:kariyer.net/is-ilani/",
            "site:yenibiris.com/is-ilani/",
        ],
    },
    "ukraine": {
        "gl": "ua",
        "country_label": "Ukraine",
        "boards": ["Djinni.co", "DOU.ua", "Work.ua"],
        "serper_clauses": [
            "site:djinni.co/jobs/",
            "site:jobs.dou.ua/companies/",
            "site:work.ua/jobs/",
        ],
    },
    "kuwait": {
        "gl": "kw",
        "country_label": "Kuwait",
        "boards": ["Bayt Kuwait", "GulfTalent Kuwait", "NaukriGulf"],
        "serper_clauses": [
            "site:bayt.com/en/kuwait/jobs/",
            "site:gulftalent.com/kuwait/jobs/",
            "site:naukrigulf.com/",
        ],
    },
    "bahrain": {
        "gl": "bh",
        "country_label": "Bahrain",
        "boards": ["Bayt Bahrain", "GulfTalent Bahrain", "NaukriGulf"],
        "serper_clauses": [
            "site:bayt.com/en/bahrain/jobs/",
            "site:gulftalent.com/bahrain/jobs/",
            "site:naukrigulf.com/",
        ],
    },
    "oman": {
        "gl": "om",
        "country_label": "Oman",
        "boards": ["Bayt Oman", "GulfTalent Oman", "NaukriGulf"],
        "serper_clauses": [
            "site:bayt.com/en/oman/jobs/",
            "site:gulftalent.com/oman/jobs/",
            "site:naukrigulf.com/",
        ],
    },
    "jordan": {
        "gl": "jo",
        "country_label": "Jordan",
        "boards": ["Akhtaboot Jordan", "Bayt Jordan"],
        "serper_clauses": [
            "site:akhtaboot.com/en/jordan/jobs/",
            "site:bayt.com/en/jordan/jobs/",
        ],
    },
    "south africa": {
        "gl": "za",
        "country_label": "South Africa",
        "boards": ["Careers24", "PNet", "OfferZen"],
        "serper_clauses": [
            "site:careers24.com/jobs/adverts/",
            "site:pnet.co.za/jobs/",
            "site:offerzen.com/jobs/",
        ],
    },
}

COUNTRY_KEY_ALIASES: Dict[str, str] = {
    "tn": "tunisia", "tunisie": "tunisia", "tunisia": "tunisia",
    "ro": "romania", "roumanie": "romania", "romania": "romania",
    "fr": "france", "france": "france",
    "ma": "morocco", "maroc": "morocco", "morocco": "morocco",
    "dz": "algeria", "algérie": "algeria", "algerie": "algeria", "algeria": "algeria",
    "de": "germany", "deutschland": "germany", "germany": "germany",
    "uk": "uk", "gb": "uk", "united kingdom": "uk",
    "nl": "netherlands", "netherlands": "netherlands",
    "ch": "switzerland", "suisse": "switzerland", "switzerland": "switzerland",
    "es": "spain", "spain": "spain",
    "pl": "poland", "poland": "poland",
    "pt": "portugal", "portugal": "portugal",
    "it": "italy", "italy": "italy",
    "be": "belgium", "belgium": "belgium",
    "at": "austria", "austria": "austria",
    "ie": "ireland", "ireland": "ireland",
    "se": "sweden", "sweden": "sweden",
    "dk": "denmark", "denmark": "denmark",
    "no": "norway", "norway": "norway",
    "fi": "finland", "finland": "finland",
    "ae": "uae", "uae": "uae", "united arab emirates": "uae", "dubai": "uae", "abu dhabi": "uae",
    "sa": "saudi arabia", "saudi arabia": "saudi arabia",
    "qa": "qatar", "qatar": "qatar",
    "eg": "egypt", "egypt": "egypt",
    "us": "usa", "usa": "usa", "united states": "usa",
    "ca": "canada", "canada": "canada",
    "in": "india", "india": "india",
    "au": "australia", "australia": "australia",
    "sg": "singapore", "singapore": "singapore",
    "nz": "new zealand", "new zealand": "new zealand",
    "my": "malaysia", "malaysia": "malaysia",
    "ph": "philippines", "philippines": "philippines",
    "id": "indonesia", "indonesia": "indonesia",
    "jp": "japan", "japan": "japan",
    "kr": "south korea", "south korea": "south korea", "korea": "south korea",
    "mx": "mexico", "mexico": "mexico", "méxico": "mexico",
    "br": "brazil", "brazil": "brazil", "brasil": "brazil",
    "ar": "argentina", "argentina": "argentina",
    "co": "colombia", "colombia": "colombia",
    "cl": "chile", "chile": "chile",
    "cz": "czech republic", "czech republic": "czech republic", "czechia": "czech republic",
    "hu": "hungary", "hungary": "hungary",
    "bg": "bulgaria", "bulgaria": "bulgaria",
    "gr": "greece", "greece": "greece",
    "hr": "croatia", "croatia": "croatia",
    "tr": "turkey", "turkey": "turkey", "türkiye": "turkey",
    "ua": "ukraine", "ukraine": "ukraine",
    "kw": "kuwait", "kuwait": "kuwait",
    "bh": "bahrain", "bahrain": "bahrain",
    "om": "oman", "oman": "oman",
    "jo": "jordan", "jordan": "jordan",
    "za": "south africa", "south africa": "south africa",
}


def resolve_country_board_config(country: str) -> Optional[dict]:
    c = (country or "").strip().lower()
    canon = COUNTRY_KEY_ALIASES.get(c, c)
    return COUNTRY_LOCAL_BOARDS.get(canon)


# ─────────────────────────────────────────────────────────────────────────────
# Direct HTML Scrapers (Zero Serper Quota, Instant Live Cards)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_tanitjobs_detail(url: str) -> dict:
    """Fetch full job description, company, location, and closed status from a single Tanitjobs job URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=4.2)
        if r.status_code != 200:
            return {}
        low_html = r.text.lower()
        is_closed = (
            "le poste a été pourvu" in low_html
            or "n'accepte plus de candidature" in low_html
            or "a clôturé cette offre" in low_html
        )
        soup = BeautifulSoup(r.text, "html.parser")
        comp_el = soup.select_one(".listing-item__info--item-company")
        company = comp_el.get_text(" ", strip=True).rstrip("- ").strip() if comp_el else ""
        loc_el = soup.select_one(".listing-item__info--item-location")
        location = loc_el.get_text(" ", strip=True) if loc_el else ""
        parts = []
        for div in soup.select(".details-body__content.content-text"):
            txt = div.get_text("\n", strip=True)
            if txt:
                parts.append(txt)
        return {
            "description": "\n\n".join(parts)[:3000],
            "company": company,
            "location": location,
            "is_closed": is_closed,
        }
    except Exception:
        return {}


def _scrape_tanitjobs(query: str) -> List[dict]:
    """Direct scraper for Tanitjobs.com (Tunisia's #1 job board)."""
    out: List[dict] = []
    # If searching a specific mobile stack like flutter, also check 'mobile' on Tanitjobs and verify description
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    search_terms = [first_w]
    if first_w in ("flutter", "dart", "react", "kotlin", "swift", "android", "ios"):
        search_terms.append("mobile")

    seen_urls = set()
    for term in search_terms:
        try:
            url = "https://www.tanitjobs.com/jobs/"
            params = {
                "listing_type[equal]": "Job",
                "action": "search",
                "keywords[all_words]": term,
            }
            r = _LOCAL_SESSION.get(url, params=params, headers=HEADERS, timeout=4.5)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for card in soup.select("div.sj-job-card")[:10]:
                t_a = card.select_one(".sj-card-title a")
                if not t_a or not t_a.get("href"):
                    continue
                job_url = t_a["href"].split("?")[0].strip()
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                raw_title = t_a.get_text(" ", strip=True)
                # Strip trailing "| City" from Tanitjobs titles
                title = raw_title.split("|")[0].strip() or raw_title

                comp_a = card.select_one(".sj-card-company a")
                company = comp_a.get_text(" ", strip=True) if comp_a else "Entreprise (Tanitjobs)"
                if company.lower() in ("société anonyme", "anonyme", "confidentiel"):
                    company = "Entreprise (Tanitjobs)"

                loc_el = card.select_one(".sj-card-tag.sj-loc")
                location = loc_el.get_text(" ", strip=True) if loc_el else "Tunis, Tunisie"
                if "tunisie" not in location.lower() and "tunisia" not in location.lower():
                    location = f"{location}, Tunisie"

                desc_el = card.select_one(".sj-card-desc")
                description = desc_el.get_text(" ", strip=True) if desc_el else ""

                dt_el = card.select_one(".sj-card-date")
                date_posted = _parse_local_date(dt_el.get_text(strip=True) if dt_el else "")

                out.append({
                    "site": "tanitjobs",
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": description,
                    "date_posted": date_posted,
                    "is_remote": "télétravail" in raw_title.lower() or "remote" in raw_title.lower(),
                })
        except Exception as e:
            logger.debug(f"[Tanitjobs] {term}: {e}")

    return out


def _scrape_hipo_romania(query: str) -> List[dict]:
    """Direct HTML scraper for Hipo.ro (Romania job board)."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    search_terms = [first_w]
    if first_w in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        search_terms.append("mobile")

    seen_urls = set()
    for term in search_terms:
        try:
            url = f"https://www.hipo.ro/locuri-de-munca/cautajob/Toate-Domeniile/Toate-Orasele/{quote(term)}"
            r = _LOCAL_SESSION.get(url, headers=HEADERS, timeout=2.8)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a.job-title")[:12]:
                href = (a.get("href") or "").strip()
                if not href or "/locuri-de-munca/locuri_de_munca/" not in href:
                    continue
                job_url = f"https://www.hipo.ro{href}" if href.startswith("/") else href
                job_url = job_url.split("?")[0]
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = a.get_text(" ", strip=True)
                if not title or "top talents" in title.lower():
                    continue
                parent = a.find_parent(["div", "tr", "li"])
                comp_el = parent.select_one("p.company-name") if parent else None
                company = comp_el.get_text(" ", strip=True) if comp_el else "Employer via Hipo.ro"

                dt_el = parent.select_one("small.text-truncate") if parent else None
                date_posted = _parse_local_date(dt_el.get_text(strip=True) if dt_el else "")

                loc_el = parent.select_one("span.badge-type") if parent else None
                raw_loc = loc_el.get_text(" ", strip=True) if loc_el else "Romania"
                if raw_loc.lower() in ("hybrid", "remote", ""):
                    location = f"{raw_loc.title()}, Romania" if raw_loc else "Romania"
                elif "romania" not in raw_loc.lower() and "românia" not in raw_loc.lower():
                    location = f"{raw_loc.title()}, Romania"
                else:
                    location = raw_loc

                out.append({
                    "site": "hipo.ro",
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": f"{title} at {company} ({location})",
                    "date_posted": date_posted,
                    "is_remote": "remote" in raw_loc.lower() or "remote" in title.lower(),
                })
            if len(out) >= 3:
                break
        except Exception as e:
            logger.debug(f"[Hipo.ro] {term}: {e}")
    return out


def _scrape_juniors_romania(query: str) -> List[dict]:
    """Direct HTML scraper for Juniors.ro (Romania IT/Tech job board)."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    search_terms = [first_w]
    if first_w in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        search_terms.append("mobile")

    seen_urls = set()
    for term in search_terms:
        try:
            r = _LOCAL_SESSION.get(
                "https://www.juniors.ro/jobs",
                params={"q": term},
                headers=HEADERS,
                timeout=2.8,
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for li in soup.select("li.job")[:12]:
                det_a = li.find("a", href=lambda h: h and re.search(r"/jobs/\d+/link", h))
                if not det_a:
                    continue
                job_url = det_a["href"].split("?")[0].strip()
                if not job_url.startswith("http"):
                    job_url = f"https://www.juniors.ro{job_url}"
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                parts = [re.sub(r"\s+", " ", p).strip() for p in li.get_text(" | ", strip=True).split("|") if p.strip()]
                if not parts:
                    continue
                title = parts[0]
                raw_loc = parts[1] if len(parts) > 1 else "Bucharest"
                location = raw_loc if "romania" in raw_loc.lower() or "românia" in raw_loc.lower() else f"{raw_loc}, Romania"

                company = "Employer via Juniors.ro"
                for idx, p in enumerate(parts):
                    if p.lower().startswith("companie") and idx + 1 < len(parts):
                        company = parts[idx + 1]
                        break

                tags = [a.get_text(strip=True) for a in li.select("a[href*='/jobs?q=']") if a.get_text(strip=True)]
                out.append({
                    "site": "juniors.ro",
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": f"{title} at {company} ({location}). Tech stack: {', '.join(tags)}",
                    "date_posted": "",
                    "is_remote": "remote" in location.lower() or "remote" in title.lower(),
                })
            if len(out) >= 3:
                break
        except Exception as e:
            logger.debug(f"[Juniors.ro] {term}: {e}")
    return out


def _scrape_talent_romania(query: str) -> List[dict]:
    """Direct HTML JobCard scraper for ro.talent.com/jobs (<0.9s response)."""
    out: List[dict] = []
    seen_urls = set()
    try:
        r_tal = _LOCAL_SESSION.get(
            "https://ro.talent.com/jobs",
            params={"k": query},
            headers=HEADERS,
            timeout=2.8,
        )
        if r_tal.status_code == 200:
            soup_t = BeautifulSoup(r_tal.text, "html.parser")
            for card in soup_t.select("div[data-new-id]")[:15]:
                nid = (card.get("data-new-id") or "").strip()
                if not nid:
                    continue
                jurl = f"https://ro.talent.com/view?id={nid}"
                if jurl in seen_urls:
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
                loc_raw = lines[2].strip(" ,") or "Bucharest, Romania"
                loc = loc_raw if "romania" in loc_raw.lower() else f"{loc_raw}, Romania"
                desc = " ".join(lines[3:6])
                seen_urls.add(jurl)
                out.append({
                    "site": "ro.talent.com",
                    "title": title,
                    "company": comp,
                    "location": loc,
                    "job_url": jurl,
                    "job_url_direct": jurl,
                    "description": f"{title} at {comp} ({loc}) — {desc}",
                    "date_posted": "",
                    "is_remote": "remote" in (title + " " + loc + " " + desc).lower(),
                })
    except Exception as e:
        logger.debug(f"[Romania Talent] {query}: {e}")
    return out


def _scrape_bestjobs_romania(query: str) -> List[dict]:
    """Direct scraper for BestJobs.eu (Romania's major job board) via curl_cffi."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    seen_urls = set()
    try:
        from curl_cffi import requests as cffi_requests
        url = f"https://www.bestjobs.eu/ro/locuri-de-munca/{quote(first_w)}"
        r = cffi_requests.get(url, impersonate="chrome124", timeout=3.4, verify=False)
        if r.status_code == 200 and "/loc-de-munca/" in r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=lambda h: h and ("/loc-de-munca/" in h or "/en/job/" in h))[:16]:
                href = (a.get("href") or "").split("?")[0].strip()
                if not href:
                    continue
                job_url = href if href.startswith("http") else f"https://www.bestjobs.eu{href}"
                if job_url in seen_urls:
                    continue
                card = a.find_parent(["div", "article", "li"])
                text_lines = [
                    ln.strip() for ln in (card.get_text("\n", strip=True) if card else a.get_text("\n", strip=True)).splitlines()
                    if ln.strip()
                ]
                slug = href.rstrip("/").split("/")[-1]
                slug_title = re.sub(r"-\d+$", "", slug).replace("-", " ").strip().title()
                title = a.get_text(" ", strip=True) or slug_title
                if len(title) < 3 or title.lower() in ("aplica", "aplică", "vezi job", "detalii"):
                    title = slug_title
                if not title:
                    continue
                seen_urls.add(job_url)
                company = "Employer via BestJobs.eu"
                for ln in text_lines:
                    if ln != title and 2 <= len(ln) <= 45 and not any(k in ln.lower() for k in ("eur", "ron", "remote", "bucuresti", "cluj", "timisoara", "iasi", "estimare")):
                        company = ln
                        break
                out.append({
                    "site": "bestjobs.eu",
                    "title": title,
                    "company": company,
                    "location": "Bucharest, Romania",
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": f"{title} at {company} (Romania) - {' '.join(text_lines[:5])}",
                    "date_posted": "",
                    "is_remote": "remote" in " ".join(text_lines).lower(),
                })
    except Exception as e:
        logger.debug(f"[BestJobs.eu] {query}: {e}")
    return out


def _scrape_ejobs_romania(query: str) -> List[dict]:
    """Targeted eJobs.ro single-posting scraper (Romania's #1 job board, bypassing Cloudflare 403 via ro.search.yahoo.com + curl_cffi)."""
    out: List[dict] = []
    q_low = (query or "").strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    terms = ["mobile"] if first_w in ("flutter", "dart", "kotlin", "swift", "android", "ios") else [first_w]
    seen = set()
    try:
        from curl_cffi import requests as cffi_requests
        for term in terms:
            r = cffi_requests.get(
                "https://ro.search.yahoo.com/search",
                params={"p": f"site:ejobs.ro/user/locuri-de-munca {term}"},
                impersonate="chrome124",
                timeout=3.0,
                verify=False,
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for div in soup.select("div.dd.algo, div.algo"):
                a = div.find("a", href=True)
                if not a:
                    continue
                href = a["href"]
                m_ru = re.search(r"RU=([^/]+)/RK=", href)
                if m_ru:
                    href = unquote(m_ru.group(1))
                href = href.split("?")[0].strip()
                if not re.search(r"ejobs\.ro/user/locuri-de-munca/[^/]+/\d+", href.lower()) or href in seen:
                    continue
                h3 = div.find("h3")
                raw_t = h3.get_text(" ", strip=True) if h3 else a.get_text(" ", strip=True)
                clean_t = re.sub(r"^.*?›\s*(?:locuri\s*-\s*de\s*-\s*munca|\d+)\s*", "", raw_t, flags=re.I)
                clean_t = re.sub(r"\s*[-|]\s*Aplica(?:\s+pe)?(?:\s+eJobs)?.*$", "", clean_t, flags=re.I).rstrip(" .-…")
                if not clean_t or len(clean_t) < 3:
                    slug = href.rstrip("/").split("/")[-2]
                    clean_t = slug.replace("-", " ").title()
                comp_el = div.select_one("div.compText, p")
                snip = comp_el.get_text(" ", strip=True) if comp_el else ""
                date_str = ""
                if " · " in snip:
                    d_cand, snip = snip.split(" · ", 1)
                    if len(d_cand) <= 25:
                        date_str = _parse_local_date(d_cand.strip())
                company = "Employer via eJobs.ro"
                if " | " in clean_t:
                    clean_t, company = [x.strip() for x in clean_t.rsplit(" | ", 1)]
                seen.add(href)
                out.append({
                    "site": "ejobs.ro",
                    "title": clean_t,
                    "company": company,
                    "location": "Bucharest, Romania",
                    "job_url": href,
                    "job_url_direct": href,
                    "description": f"{clean_t} at {company} (Romania) — {snip}",
                    "date_posted": date_str,
                    "is_remote": "remote" in (clean_t + " " + snip).lower(),
                })
    except Exception as e:
        logger.debug(f"[eJobs.ro] {query}: {e}")
    return out


def _scrape_keejob(query: str) -> List[dict]:
    """Direct scraper for Keejob.com (Tunisia)."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    search_terms = [first_w]
    if first_w in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        search_terms.append("mobile")

    seen_urls = set()
    for term in search_terms:
        try:
            r = _LOCAL_SESSION.get(
                "https://www.keejob.com/offres-emploi/",
                params={"keywords": term},
                headers=HEADERS,
                timeout=4.5,
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.find_all("article")[:10]:
                h2_a = art.select_one("h2 a")
                if not h2_a or not h2_a.get("href"):
                    continue
                href = h2_a["href"].split("?")[0]
                if not re.search(r"/offres-emploi/\d+/", href):
                    continue
                job_url = f"https://www.keejob.com{href}" if href.startswith("/") else href
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                title = h2_a.get_text(" ", strip=True)
                comp_a = art.select_one("p a[href*='/entreprises/']")
                company = comp_a.get_text(" ", strip=True) if comp_a else "Entreprise (Keejob)"

                loc_icon = art.select_one("i.fa-map-marker-alt")
                loc_span = loc_icon.find_next("span") if loc_icon else None
                loc_txt = re.sub(r"\s+", " ", loc_span.get_text(" ", strip=True)) if loc_span else "Tunis"
                location = f"{loc_txt}, Tunisie" if "tunisie" not in loc_txt.lower() else loc_txt

                clk_icon = art.select_one("i.fa-clock")
                clk_span = clk_icon.find_next("span") if clk_icon else None
                date_posted = _parse_local_date(clk_span.get_text(" ", strip=True) if clk_span else "")

                desc_p = art.select_one("div.mb-3 p")
                description = desc_p.get_text(" ", strip=True) if desc_p else ""

                out.append({
                    "site": "keejob",
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "description": description,
                    "date_posted": date_posted,
                    "is_remote": False,
                })
        except Exception as e:
            logger.debug(f"[Keejob] {term}: {e}")
    return out


def _scrape_freework_france(query: str) -> List[dict]:
    """Direct scraper for Free-Work.com (France's #1 IT/Tech job board)."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    try:
        r = _LOCAL_SESSION.get(
            "https://www.free-work.com/fr/tech-it/jobs",
            params={"query": first_w},
            headers=HEADERS,
            timeout=4.8,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for card in soup.find_all("div", class_=lambda c: c and "mb-4" in c and "lg:block" in c):
            a_tag = card.find("a", href=lambda h: h and "/job-mission/" in h)
            if not a_tag:
                continue
            href = a_tag["href"].split("?")[0]
            job_url = f"https://www.free-work.com{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            seen.add(job_url)

            title = a_tag.get_text(" ", strip=True)
            card_text = card.get_text(" | ", strip=True)
            # Extract date DD/MM/YYYY
            m_dt = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", card_text)
            date_posted = _parse_local_date(m_dt.group(1)) if m_dt else ""

            # Company name sits right after DD/MM/YYYY in Free-Work card pipe segments
            company = "Entreprise (Free-Work)"
            parts = [p.strip() for p in card_text.split("|") if p.strip()]
            for idx, p in enumerate(parts):
                if re.fullmatch(r"\d{2}/\d{2}/\d{4}", p) and idx + 1 < len(parts):
                    cand_comp = parts[idx + 1]
                    if len(cand_comp) <= 45 and not cand_comp.lower().startswith("contexte"):
                        company = cand_comp
                    break

            # Location sits after "Lieu"
            location = "Paris, France"
            m_loc = re.search(r"\bLieu\s+([^|]+)", card_text)
            if m_loc:
                loc_clean = m_loc.group(1).strip()
                location = f"{loc_clean}, France" if "france" not in loc_clean.lower() else loc_clean

            # Salary / TJM
            salary_text = ""
            m_sal = re.search(r"(?:Salaire|TJM)\s+([^\s|]+(?:\s*€[^\s|]*)?)", card_text)
            if m_sal:
                salary_text = m_sal.group(1).strip()

            out.append({
                "site": "free-work",
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": card_text[:1200],
                "date_posted": date_posted,
                "salary_text": salary_text,
                "is_remote": "télétravail" in card_text.lower(),
            })
    except Exception as e:
        logger.debug(f"[FreeWork] {query}: {e}")
    return out


def _scrape_emploitic_algeria(query: str) -> List[dict]:
    """Direct scraper for Emploitic.com (Algeria's #1 job board)."""
    out: List[dict] = []
    q_low = query.strip().lower()
    first_w = q_low.split()[0] if q_low.split() else q_low
    try:
        r = _LOCAL_SESSION.get(
            "https://emploitic.com/offres-d-emploi",
            params={"search": first_w},
            headers=HEADERS,
            timeout=4.5,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].split("?")[0].strip()
            if "/offres-d-emploi/" not in href or len(href.strip("/").split("/")) < 4:
                continue
            job_url = f"https://emploitic.com{href}" if href.startswith("/") else href
            if job_url in seen:
                continue
            parts = [p.strip() for p in a_tag.get_text(" | ", strip=True).split("|") if p.strip()]
            if len(parts) < 2:
                continue
            seen.add(job_url)
            title = parts[0]
            company = parts[1]
            if company.lower() in ("entreprise anonyme", "anonyme", "confidentiel"):
                company = "Entreprise (Emploitic)"
            location = parts[2] if len(parts) > 2 else "Alger, Algérie"
            if "algérie" not in location.lower() and "algeria" not in location.lower():
                location = f"{location}, Algérie"
            date_posted = _parse_local_date(parts[3]) if len(parts) > 3 else ""
            raw_snippet = " ".join(parts[4:]) if len(parts) > 4 else ""
            desc = f"{title} chez {company} ({location}) — {raw_snippet}"
            out.append({
                "site": "emploitic",
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": re.sub(r"<[^>]+>", " ", desc).strip(),
                "date_posted": date_posted,
                "is_remote": "télétravail" in location.lower() or "remote" in location.lower(),
            })
            if len(out) >= 12:
                break
    except Exception as e:
        logger.debug(f"[Emploitic] {query}: {e}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Serper Country Local Boards Discovery & Single-Posting Parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_local_serper_item(item: dict, canon_country: str, country_label: str) -> Optional[dict]:
    """
    Verify and parse a single job posting from a country's local job board returned by Serper.
    Rejects search/category/directory/blog pages and extracts accurate title, company, location,
    board name, and posting date.
    """
    raw_title = (item.get("title") or "").strip()
    link = (item.get("link") or "").strip()
    snippet = (item.get("snippet") or "").strip()
    serper_date = _parse_local_date((item.get("date") or "").strip())
    if not raw_title or not link:
        return None

    low_link = link.lower()
    parsed_u = urlparse(link)
    host = parsed_u.netloc.lower().replace("www.", "")
    path_parts = [p for p in parsed_u.path.strip("/").split("/") if p]

    # Reject non-job paths (blogs, salaries, company profiles, CV profiles, search pages)
    if any(seg in low_link for seg in (
        "/blog/", "/salaries/", "/company-profile/", "/similar", "/profil-", ".mpt",
        "/metiers/", "/recherche", "/cautajob", "?page=", "/ofertas-trabajo/",
    )):
        return None

    board_site = "local_board"
    title = raw_title
    company = ""
    location = country_label

    # 1. Romania: eJobs.ro / BestJobs.eu / Hipo.ro / DevJob.ro
    if "ejobs.ro" in host:
        if "/user/locuri-de-munca/" not in low_link or len(path_parts) < 4:
            return None
        board_site = "ejobs.ro"
        title = re.sub(r"\s*[-|]\s*Aplica\s+pe\s+eJobs.*$", "", raw_title, flags=re.I).strip()
        if " | " in title:
            title, company = [x.strip() for x in title.rsplit(" | ", 1)]
        if not company:
            company = "Employer via eJobs.ro"
        location = "Bucharest, Romania"
    elif "bestjobs.eu" in host:
        if not ("/loc-de-munca/" in low_link or "/en/job/" in low_link):
            return None
        board_site = "bestjobs.eu"
        title = re.sub(r"\s*[-|]\s*BestJobs.*$", "", raw_title, flags=re.I).strip()
        company = "Employer via BestJobs"
        location = "Romania"
    elif "hipo.ro" in host:
        if "/locuri-de-munca/locuri_de_munca/" not in low_link or len(path_parts) < 4:
            return None
        board_site = "hipo.ro"
        if len(path_parts) >= 5:
            company = unquote(path_parts[3]).replace("-", " ").strip()
            title = re.sub(rf"\s*[-|]\s*{re.escape(company)}.*$", "", raw_title, flags=re.I).strip()
        if not company:
            company = "Employer via Hipo.ro"
        location = "Romania"
    elif "devjob.ro" in host:
        if "/jobs/" not in low_link or low_link.rstrip("/").endswith("/all") or len(path_parts) < 3:
            return None
        board_site = "devjob.ro"
        slug = path_parts[-1]
        if "-" in slug and len(slug) > 8:
            if " | " in raw_title:
                title, company = [x.strip() for x in raw_title.split(" | ", 1)]
            else:
                company = slug.split("-")[0].capitalize()
                title = raw_title
            location = "Romania"
        else:
            return None

    # 2. Tunisia: Tanitjobs / Keejob / OptionCarriere TN
    elif "tanitjobs.com" in host:
        if "/job/" not in low_link:
            return None
        board_site = "tanitjobs"
        title = re.sub(r"^Offre\s+d['’`]emploi\s*", "", raw_title, flags=re.I)
        title = re.sub(r"\s*\|\s*Tanitjobs.*$", "", title, flags=re.I).strip()
        if " - " in title:
            head, tail = title.rsplit(" - ", 1)
            if len(tail) <= 25:
                title = head.strip()
                location = f"{tail.strip()}, Tunisie"
        company = "Entreprise (Tanitjobs)"
    elif "keejob.com" in host:
        if not re.search(r"/offres-emploi/\d+/", low_link):
            return None
        board_site = "keejob"
        title = re.sub(r"^Offre\s+d['’`]emploi\s*", "", raw_title, flags=re.I).strip()
        company = "Entreprise (Keejob)"
        location = "Tunisie"
    elif "optioncarriere.tn" in host:
        if "/jobview/" not in low_link:
            return None
        board_site = "optioncarriere.tn"
        title = raw_title.split(" - ")[0].strip()
        company = "Entreprise (OptionCarriere TN)"
        location = "Tunisie"

    # 3. France: Welcome to the Jungle / APEC / HelloWork / Free-Work
    elif "welcometothejungle.com" in host:
        if "/companies/" not in low_link or "/jobs/" not in low_link:
            return None
        board_site = "welcometothejungle"
        comp_idx = path_parts.index("companies") if "companies" in path_parts else -1
        if comp_idx >= 0 and comp_idx + 1 < len(path_parts):
            company = unquote(path_parts[comp_idx + 1]).replace("-", " ").title()
        title = raw_title.split(" - ")[0].strip()
        job_slug = path_parts[-1] if path_parts else ""
        if "_" in job_slug:
            city_slug = job_slug.rsplit("_", 1)[-1].replace("-", " ").title()
            if city_slug and len(city_slug) <= 30:
                location = f"{city_slug}, France"
    elif "apec.fr" in host:
        if "/detail-offre/" not in low_link:
            return None
        board_site = "apec.fr"
        title = re.sub(r"^Offre\s+d['’`]emploi\s*", "", raw_title, flags=re.I).strip()
        company = "Entreprise via APEC"
        location = "France"
    elif "hellowork.com" in host:
        if "/emplois/" not in low_link or not low_link.split("?")[0].endswith(".html"):
            return None
        board_site = "hellowork"
        title = re.sub(r"^Offre\s+Emploi\s*(?:CDI|CDD|Stage|Alternance)?\s*", "", raw_title, flags=re.I).strip()
        m_hw = re.match(r"^(.+?\b(?:H/F|F/H))\s+(.+)$", title, flags=re.I)
        if m_hw:
            title = m_hw.group(1).strip()
            company = m_hw.group(2).strip()
        if not company:
            company = "Entreprise via HelloWork"
        location = "France"
    elif "free-work.com" in host:
        if "/job-mission/" not in low_link:
            return None
        board_site = "free-work"
        title = raw_title.split(" - ")[0].strip()
        company = "Entreprise via Free-Work"
        location = "France"

    # 4. Morocco & Algeria: ReKrute / Emploi.ma / Emploitic / AlgerieJob
    elif "rekrute.com" in host:
        if "/offre-emploi-" not in low_link:
            return None
        board_site = "rekrute"
        title = re.sub(r"^Offre\s+d['’`]emploi\s*", "", raw_title, flags=re.I).strip()
        m_rk = re.search(r"-recrutement-([a-z0-9-]+)-\d+\.html", low_link)
        if m_rk:
            slug_parts = m_rk.group(1).split("-")
            if len(slug_parts) >= 2:
                city = slug_parts[-1].title()
                company = " ".join(slug_parts[:-1]).title()
                location = f"{city}, Morocco"
        if " - " in title:
            t_parts = [p.strip() for p in title.split(" - ")]
            title = t_parts[0]
            if not company and len(t_parts) >= 2:
                company = t_parts[-1]
        if not company:
            company = "Entreprise via ReKrute"
    elif "emploi.ma" in host:
        if "/offre-emploi-maroc/" not in low_link:
            return None
        board_site = "emploi.ma"
        title = raw_title.split(" | ")[0].split(" - ")[0].strip()
        company = "Entreprise via Emploi.ma"
        location = "Morocco"
    elif "emploitic.com" in host:
        if "/offres-d-emploi/" not in low_link:
            return None
        board_site = "emploitic"
        title = re.sub(r"^Offre\s+d['’`]emploi\s*", "", raw_title, flags=re.I).split(" - ")[0].strip()
        company = "Entreprise via Emploitic"
        location = "Algérie"
    elif "algeriejob.com" in host:
        if "/offre-emploi-algerie/" not in low_link:
            return None
        board_site = "algeriejob"
        title = re.sub(r"^Offre\s+d['’`]emploi\s+Algérie\s*:\s*", "", raw_title, flags=re.I).split(" - ")[0].strip()
        company = "Entreprise via AlgerieJob"
        location = "Algérie"

    # 5. Germany / UK / Poland / Portugal / Switzerland / UAE / Egypt / Other local boards
    elif "stepstone." in host:
        if "stellenangebote--" not in low_link and "offres-d-emploi--" not in low_link and "vacatures--" not in low_link:
            return None
        board_site = host
        if " - " in raw_title:
            title, company = [x.strip() for x in raw_title.split(" - ", 1)]
        else:
            company = f"Employer via {host.capitalize()}"
    elif "justjoin.it" in host:
        if "/job-offer/" not in low_link:
            return None
        board_site = "justjoin.it"
        if " - " in raw_title:
            title, company = [x.strip() for x in raw_title.rsplit(" - ", 1)]
        else:
            company = "Employer via JustJoin.it"
        location = "Poland"
    elif "nofluffjobs.com" in host:
        if "/job/" not in low_link:
            return None
        board_site = "nofluffjobs"
        title = raw_title.split(" | ")[0].strip()
        company = "Employer via NoFluffJobs"
        location = "Poland"
    elif "pracuj.pl" in host:
        if ",oferta," not in low_link:
            return None
        board_site = "pracuj.pl"
        title = raw_title.split(" - ")[0].strip()
        company = "Employer via Pracuj.pl"
        location = "Poland"
    elif "reed.co.uk" in host:
        if not re.search(r"/jobs/[^/]+/\d+", low_link):
            return None
        board_site = "reed.co.uk"
        title = re.sub(r"\s*-\s*Reed\.co\.uk.*$", "", raw_title, flags=re.I).strip()
        company = "Employer via Reed.co.uk"
        location = "United Kingdom"
    elif "itjobs.pt" in host:
        if "/oferta/" not in low_link:
            return None
        board_site = "itjobs.pt"
        if " - " in raw_title:
            title, company = [x.strip() for x in raw_title.rsplit(" - ", 1)]
        else:
            company = "Employer via ITJobs.pt"
        location = "Portugal"
    elif "jobs.ch" in host or "jobup.ch" in host:
        if "/detail/" not in low_link:
            return None
        board_site = host
        if " - " in raw_title:
            title, company = [x.strip() for x in raw_title.rsplit(" - ", 1)]
        else:
            company = f"Employer via {host}"
        location = "Switzerland"
    elif "gulftalent.com" in host:
        if not re.search(r"/jobs/[^/]+-\d+$", low_link.split("?")[0]):
            return None
        board_site = "gulftalent"
        title = raw_title.split(" | ")[0].strip()
        m_by = re.search(r"\bby\s+(.+)$", raw_title, flags=re.I)
        company = m_by.group(1).strip() if m_by else "Employer via GulfTalent"
    elif "wuzzuf.net" in host:
        if "/jobs/p/" not in low_link:
            return None
        board_site = "wuzzuf"
        title = re.sub(r"\s+vacancy\s+in\s+.*$", "", raw_title, flags=re.I).strip()
        company = "Employer via Wuzzuf"
        location = "Cairo, Egypt"
    elif "mycareersfuture.gov.sg" in host:
        if "/job/" not in low_link or not re.search(r"[0-9a-f]{32}", low_link):
            return None
        board_site = "mycareersfuture"
        title = raw_title.split(" | ")[0].split(" - ")[0].strip()
        company = "Employer via MyCareersFuture"
        location = "Singapore"
    elif "bayt.com" in host:
        if not re.search(r"/jobs/[^/]+-\d+/?$", low_link.split("?")[0]):
            return None
        board_site = "bayt"
        title = re.sub(r"\s*-\s*Bayt\.com.*$", "", raw_title, flags=re.I)
        title = re.sub(r"\s+Job\s+in\s+.*$", "", title, flags=re.I).strip()
        company = f"Employer via Bayt ({country_label})"
    elif "naukrigulf.com" in host:
        if "-jobs-in-" in low_link or not re.search(r"-\d{5,}", low_link):
            return None
        board_site = "naukrigulf"
        title = raw_title.split(" - ")[0].split(" | ")[0].strip()
        company = f"Employer via NaukriGulf ({country_label})"
    elif "jobs.cz" in host or "prace.cz" in host or "startupjobs.cz" in host:
        if not any(p in low_link for p in ("/rpd/", "/nabidka/")):
            return None
        board_site = host
        parts = [p.strip() for p in re.split(r"\s+[–\-|]\s+", raw_title) if p.strip()]
        title = parts[0] if parts else raw_title
        company = parts[1] if len(parts) > 1 and "jobs.cz" not in parts[1].lower() else f"Employer via {host}"
        location = "Prague, Czech Republic"
    elif "profession.hu" in host or "dreamjo.bs" in host:
        if "/allas/" not in low_link and "/job/" not in low_link:
            return None
        board_site = host
        title = raw_title.split(" - ")[0].split(" | ")[0].strip()
        company = f"Employer via {host}"
        location = "Budapest, Hungary"
    elif "moj-posao.net" in host or "posao.hr" in host:
        if not any(p in low_link for p in ("/posao/", "/poslovac/", "/oglasi/")):
            return None
        board_site = "posao.hr" if "posao.hr" in host else "moj-posao.net"
        parts = [p.strip() for p in raw_title.split(" - ") if p.strip()]
        title = parts[0] if parts else raw_title
        company = parts[1] if len(parts) > 1 else f"Employer via {board_site}"
        location = "Zagreb, Croatia"
    elif "kariyer.net" in host or "yenibiris.com" in host or "eleman.net" in host:
        if "/is-ilani/" not in low_link or not re.search(r"-\d+$|-i\d+$", low_link.split("?")[0].rstrip("/")):
            return None
        board_site = host
        title = re.sub(r"\s+İş\s+İlanı.*$", "", raw_title, flags=re.I).split(" - ")[0].strip()
        company = f"Employer via {host}"
        location = "Istanbul, Turkey"
    elif "duunitori.fi" in host:
        if "/tyopaikat/tyo/" not in low_link:
            return None
        board_site = "duunitori.fi"
        parts = [p.strip() for p in re.split(r"\s+[–\-|]\s+", raw_title) if p.strip()]
        title = parts[0] if parts else raw_title
        company = parts[1] if len(parts) > 1 else "Employer via Duunitori"
        location = "Helsinki, Finland"
    elif "stepstone.be" in host or "stepstone.de" in host:
        if not re.search(r"--\d+-inline\.html", low_link) and "/stellenangebote--" not in low_link and "/offres-d-emploi--" not in low_link and "/vacatures--" not in low_link:
            return None
        board_site = host
        title = raw_title.split(" - ")[0].split(" | ")[0].strip()
        company = f"Employer via {host}"
    elif "irishjobs.ie" in host or "jobs.ie" in host:
        if "/job/" not in low_link:
            return None
        board_site = host
        title = re.sub(r"\s+in\s+.*\s*-\s*(?:IrishJobs|Jobs)\.ie.*$", "", raw_title, flags=re.I).split(" | ")[0].strip()
        company = f"Employer via {host}"
        location = "Dublin, Ireland"
    elif "infojobs.it" in host or "iprogrammatori.it" in host:
        if "/offerta-lavoro/" not in low_link and "/lavoro-informatica/" not in low_link:
            return None
        board_site = host
        title = raw_title.split(" - ")[0].split(" | ")[0].strip()
        company = f"Employer via {host}"
        location = "Milan, Italy"
    else:
        # Generic verification for other configured local boards (must have numeric ID or deep path)
        if len(path_parts) < 2:
            return None
        board_site = host
        title = raw_title.split(" | ")[0].split(" - ")[0].strip()
        company = f"Employer via {host}"

    return {
        "site": board_site,
        "title": title,
        "company": company,
        "location": location,
        "job_url": link.split("?")[0] if "apec.fr" not in host else link,
        "job_url_direct": link,
        "description": snippet,
        "date_posted": serper_date,
        "is_remote": "remote" in raw_title.lower() or "télétravail" in raw_title.lower(),
    }


def _clause_to_yahoo_query(kw: str, clause: str) -> str:
    """Convert a Serper `site:domain/path/` clause into a Yahoo-compatible search query."""
    raw = clause.strip()
    if raw.startswith("site:"):
        raw = raw[5:]
    raw = raw.rstrip("/")
    if not raw:
        return kw
    if "/" in raw:
        host, path = raw.split("/", 1)
        if path.endswith("-") or "--" in path:
            path_words = path.replace("-", " ").strip()
            return f"{kw} {path_words} site:{host}"
        return f"{kw} site:{host}/{path}"
    return f"{kw} site:{raw}"


def _run_yahoo_local_discovery(
    core_kw: str,
    first_word: str,
    canon_country: str,
    cfg: dict,
) -> List[dict]:
    """
    Zero-key fallback when Serper is unavailable or out of credits (HTTP 400):
    queries Yahoo search via ddgs across the country's configured local board clauses
    and parses single postings via `_parse_local_serper_item`.
    """
    clauses = cfg.get("serper_clauses") or []
    if not clauses:
        return []
    out: List[dict] = []
    seen_links = set()
    try:
        from ddgs import DDGS
    except Exception:
        return []

    search_kws = [core_kw]
    if first_word in ("flutter", "dart", "kotlin", "swift", "android", "ios"):
        search_kws.append("mobile developer")

    for cl in clauses[:2]:
        for kw in search_kws[:1]:
            yq = _clause_to_yahoo_query(kw, cl)
            try:
                with DDGS(verify=False) as ddgs:
                    items = ddgs.text(yq, max_results=8, backend="yahoo") or []
                for it in items:
                    href = (it.get("href") or "").strip()
                    if not href or "bing.com/aclick" in href or href in seen_links:
                        continue
                    seen_links.add(href)
                    serper_like = {
                        "title": (it.get("title") or "").strip(),
                        "link": href,
                        "snippet": f"{(it.get('body') or '').strip()}",
                        "date": "",
                    }
                    parsed = _parse_local_serper_item(serper_like, canon_country, cfg["country_label"])
                    if parsed:
                        out.append(parsed)
                if len(out) >= 6:
                    break
            except Exception as e:
                logger.debug(f"[LocalBoards Yahoo] {canon_country} ({yq}): {e}")
        if len(out) >= 8:
            break
    return out


def _yahoo_clause_discovery(core_kw: str, clause: str, canon_country: str, cfg: dict) -> List[dict]:
    """Yahoo (ddgs) discovery for ONE local-board `site:` clause (run in parallel per clause)."""
    try:
        from ddgs import DDGS
    except Exception:
        return []
    out: List[dict] = []
    yq = _clause_to_yahoo_query(core_kw, clause)
    try:
        with DDGS(verify=False, timeout=3) as ddgs:
            items = ddgs.text(yq, max_results=8, backend="yahoo") or []
        seen = set()
        for it in items:
            href = (it.get("href") or "").strip()
            if not href or "bing.com/aclick" in href or href in seen:
                continue
            seen.add(href)
            parsed = _parse_local_serper_item(
                {"title": (it.get("title") or "").strip(), "link": href,
                 "snippet": (it.get("body") or "").strip(), "date": ""},
                canon_country, cfg["country_label"],
            )
            if parsed:
                out.append(parsed)
    except Exception as e:
        logger.debug(f"[LocalBoards Yahoo] {canon_country} ({yq}): {e}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Local Boards Engine
#   * registry      : plugin scrapers (local_boards_ext/*) override legacy scrapers per country
#   * TTL cache     : raw rows cached per (scraper, query) -> repeated / concurrent searches are instant
#   * single-flight : the fast wave and the deep wave share ONE in-flight HTTP call per scraper
#   * deadline      : callers wait at most LOCAL_BUDGET_S; late scrapers finish in the background and
#                     still populate the cache for the next search
#   * breaker       : scrapers that keep timing out / crashing are skipped for a cool-down period
#   * health        : per-scraper latency / success metrics exposed to the back office
# ─────────────────────────────────────────────────────────────────────────────

import os as _os
import threading as _threading
import time as _time
from concurrent.futures import Future as _Future
from functools import partial as _partial

LOCAL_BUDGET_S = float(_os.getenv("LOCAL_BOARDS_BUDGET_S", "4.5"))
_CACHE_TTL_S = 25 * 60          # rows found -> reuse for 25 min
_EMPTY_TTL_S = 5 * 60           # nothing found -> retry after 5 min
_CACHE_MAX = 4000
_BREAKER_FAILS = 3              # consecutive slow (> budget) or crashed runs before skipping a scraper
_BREAKER_COOLDOWN_S = 10 * 60

_eng_lock = _threading.Lock()
_row_cache: Dict[tuple, tuple] = {}       # (scraper, query) -> (ts, rows)
_inflight: Dict[tuple, _Future] = {}      # (scraper, query) -> Future
_health: Dict[str, dict] = {}
_serper_off_until = 0.0
_VERIFY_POOL = ThreadPoolExecutor(max_workers=12)


def _scrape_tanitjobs_verified(query: str) -> List[dict]:
    """Tanitjobs + parallel detail-page verification (closed postings dropped, real employer/description).
    Runs inside the cached task, so verification cost is paid once per query, not per search."""
    rows = _scrape_tanitjobs(query) or []
    if not rows:
        return []
    q0 = (query.split() or [""])[0].lower()
    rows.sort(key=lambda r: (0 if q0 in (r.get("title") or "").lower() else 1,
                             0 if (r.get("company") or "").startswith("Entreprise (") else 1))

    def _verify(row: dict):
        det = fetch_tanitjobs_detail(row["job_url"])
        if det.get("is_closed"):
            row["is_closed"] = True
        if det.get("company") and det["company"].lower() not in ("société anonyme", "anonyme", "confidentiel"):
            row["company"] = det["company"]
        if det.get("location") and ("tunisie" in det["location"].lower() or "tunisia" in det["location"].lower()):
            row["location"] = det["location"]
        if det.get("description") and len(det["description"]) > len(row.get("description") or ""):
            row["description"] = det["description"]

    wait([_VERIFY_POOL.submit(_verify, r) for r in rows[:12]], timeout=2.5)
    return [r for r in rows if not r.get("is_closed")]


_LEGACY_BUILTIN: Dict[str, list] = {
    "tunisia": [_scrape_tanitjobs_verified, _scrape_keejob],
    "romania": [_scrape_talent_romania, _scrape_bestjobs_romania, _scrape_hipo_romania, _scrape_juniors_romania, _scrape_ejobs_romania],
    "france": [_scrape_freework_france],
    "algeria": [_scrape_emploitic_algeria],
}


def _external_direct_scrapers(canon_country: str) -> list:
    """Legacy per-region scraper modules (local_scrapers_eu / local_scrapers_world)."""
    fns: list = []
    for mod_name in ("local_scrapers_eu", "local_scrapers_world"):
        try:
            mod = __import__(f"{__package__}.{mod_name}", fromlist=["DIRECT_SCRAPERS"])
            fns.extend(getattr(mod, "DIRECT_SCRAPERS", {}).get(canon_country, []) or [])
        except Exception as e:
            logger.debug(f"[LocalBoards] could not load {mod_name}: {e}")
    return fns


def scrapers_for_country(canon_country: str) -> list:
    """Authoritative scraper list: plugin list when a plugin covers the country, else legacy scrapers."""
    try:
        from .local_boards_ext import load_plugins
        plugin_fns = load_plugins()[0].get(canon_country) or []
    except Exception as e:
        logger.warning(f"[LocalBoards] plugin load failed: {e}")
        plugin_fns = []
    if plugin_fns:
        fns = [(_scrape_tanitjobs_verified if fn is _scrape_tanitjobs else fn) for fn in plugin_fns]
    else:
        fns = list(_LEGACY_BUILTIN.get(canon_country, [])) + _external_direct_scrapers(canon_country)
    out, seen = [], set()
    for fn in fns:
        if fn not in seen:
            seen.add(fn)
            out.append(fn)
    return out


def boards_for_country(canon_country: str) -> List[str]:
    cfg = COUNTRY_LOCAL_BOARDS.get(canon_country) or {}
    names = list(cfg.get("boards") or [])
    try:
        from .local_boards_ext import load_plugins
        for n in load_plugins()[1].get(canon_country) or []:
            if n not in names:
                names.append(n)
    except Exception:
        pass
    return names


def _fn_key(fn) -> str:
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', repr(fn))}"


def _safe_scrape(fn, query: str) -> List[dict]:
    """Run a direct scraper and normalise its rows (single postings only, ISO dates, board search context). Never raises."""
    from .search_engine import enrich_board_search_context
    try:
        rows = fn(query) or []
    except Exception as e:
        logger.debug(f"[LocalBoards] {getattr(fn, '__name__', fn)} failed: {e}")
        raise
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("title") or not r.get("job_url"):
            continue
        r.setdefault("job_url_direct", r["job_url"])
        r["date_posted"] = _parse_local_date(str(r.get("date_posted") or ""))
        r["description"] = enrich_board_search_context(
            r["title"], r.get("description") or "", query, r.get("company") or ""
        )
        out.append(r)
    return out


def _record_health(name: str, dt: float, n_rows: int, crashed: bool) -> None:
    h = _health.setdefault(name, {
        "calls": 0, "with_rows": 0, "empty": 0, "errors": 0, "slow": 0, "consec_fail": 0,
        "avg_ms": 0.0, "max_ms": 0.0, "last_rows": 0, "last_run": 0.0, "skip_until": 0.0,
    })
    h["calls"] += 1
    h["last_run"] = _time.time()
    h["last_rows"] = n_rows
    ms = dt * 1000.0
    h["avg_ms"] = ms if h["calls"] == 1 else round(h["avg_ms"] * 0.8 + ms * 0.2, 1)
    h["max_ms"] = round(max(h["max_ms"], ms), 1)
    if crashed:
        h["errors"] += 1
    elif n_rows:
        h["with_rows"] += 1
    else:
        h["empty"] += 1
    slow = dt > LOCAL_BUDGET_S
    if slow:
        h["slow"] += 1
    if crashed or slow:
        h["consec_fail"] += 1
        if h["consec_fail"] >= _BREAKER_FAILS:
            h["skip_until"] = _time.time() + _BREAKER_COOLDOWN_S
            # half-open: after the cool-down one more failure re-opens the breaker immediately
            h["consec_fail"] = _BREAKER_FAILS - 1
            logger.info(f"[LocalBoards] breaker OPEN for {name} ({_BREAKER_COOLDOWN_S // 60} min)")
    else:
        h["consec_fail"] = 0


def _run_and_cache(name: str, job, key: tuple) -> List[dict]:
    t0 = _time.time()
    crashed = False
    try:
        rows = job() or []
    except Exception:
        rows, crashed = [], True
    dt = _time.time() - t0
    with _eng_lock:
        if not crashed:
            _row_cache[key] = (_time.time(), rows)
            if len(_row_cache) > _CACHE_MAX:
                for k in sorted(_row_cache, key=lambda k: _row_cache[k][0])[: _CACHE_MAX // 5]:
                    _row_cache.pop(k, None)
        _inflight.pop(key, None)
        _record_health(name, dt, len(rows), crashed)
    return rows


def _submit(name: str, job, query_key: str) -> Optional[_Future]:
    """Cached + single-flight submission. Returns a Future (already resolved on cache hit) or None if the
    scraper's breaker is open."""
    key = (name, query_key.strip().lower())
    now = _time.time()
    with _eng_lock:
        hit = _row_cache.get(key)
        if hit and now - hit[0] < (_CACHE_TTL_S if hit[1] else _EMPTY_TTL_S):
            f: _Future = _Future()
            f.set_result(hit[1])
            return f
        f = _inflight.get(key)
        if f is not None:
            return f
        if (_health.get(name) or {}).get("skip_until", 0) > now:
            return None
        f = _LOCAL_POOL.submit(_run_and_cache, name, job, key)
        _inflight[key] = f
        return f


def _serper_local(q_str: str, canon_country: str, cfg: dict, tbs: str, serper_key: str) -> List[dict]:
    global _serper_off_until
    if _time.time() < _serper_off_until:
        return []
    try:
        resp = _LOCAL_SESSION.post(
            "https://google.serper.dev/search",
            json={"q": q_str, "gl": cfg["gl"], "num": 10, "tbs": tbs},
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            timeout=4.0,
        )
        if resp.status_code != 200:
            if resp.status_code in (400, 401, 403) and ("credit" in resp.text.lower() or "unauthor" in resp.text.lower()):
                _serper_off_until = _time.time() + 30 * 60   # out of credits / bad key -> stop wasting calls
                logger.info("[LocalBoards] Serper disabled for 30 min: " + resp.text[:120])
            return []
        out = []
        for it in resp.json().get("organic", []):
            parsed = _parse_local_serper_item(it, canon_country, cfg["country_label"])
            if parsed:
                out.append(parsed)
        return out
    except Exception as e:
        logger.debug(f"[LocalBoards Serper] {canon_country}: {e}")
        return []


def _collect(futs: list) -> List[dict]:
    rows: List[dict] = []
    for f in futs:
        if f.done() and not f.cancelled() and not f.exception():
            rows.extend(dict(r) for r in (f.result() or []))   # copies: cached rows stay pristine
    return rows


def fetch_country_local_boards(
    queries: List[str],
    country: str,
    hours_old: Optional[int] = None,
    serper_key: str = "",
    budget_s: Optional[float] = None,
) -> List[dict]:
    """
    Scrape the selected country's local job boards (e.g. Tanitjobs & Keejob in Tunisia; eJobs, BestJobs,
    Hipo in Romania; HelloWork & Free-Work in France) and return verified, relevant single postings.
    Never waits longer than ``budget_s`` (default LOCAL_BUDGET_S); slower boards complete in the
    background and are served from cache on the next search.
    """
    c_raw = (country or "").strip().lower()
    if not c_raw or c_raw in ("worldwide", "global", "all", "remote", "anywhere") or c_raw.startswith("remote "):
        return []
    canon_country = COUNTRY_KEY_ALIASES.get(c_raw, c_raw)
    cfg = COUNTRY_LOCAL_BOARDS.get(canon_country)
    if not cfg or not queries:
        return []

    budget = LOCAL_BUDGET_S if budget_s is None else budget_s
    t_start = _time.time()
    primary_q = queries[0].strip()
    first_word = primary_q.split()[0].lower() if primary_q.split() else primary_q.lower()

    from .search_engine import SINGLE_TECH_TO_ROLE, best_relevance
    core_kw = first_word if first_word in SINGLE_TECH_TO_ROLE else primary_q

    # 1. Direct scrapers (cached + single-flight)
    direct_fns = scrapers_for_country(canon_country)
    futs = []
    for fn in direct_fns:
        f = _submit(_fn_key(fn), _partial(_safe_scrape, fn, core_kw), core_kw)
        if f is not None:
            futs.append(f)

    # 2. Serper discovery across the country's boards (skipped automatically when out of credits)
    clauses = cfg.get("serper_clauses") or []
    if serper_key and clauses and _time.time() >= _serper_off_until:
        tbs = ("qdr:d" if hours_old <= 24 else ("qdr:w" if hours_old <= 168 else "qdr:m")) if hours_old else "qdr:m3"
        joined = " OR ".join(clauses)
        sq = [f"{core_kw} ({joined}) -inurl:similar -inurl:all"]
        if first_word in ("flutter", "dart", "kotlin", "swift", "react"):
            alt = (f'("{first_word}" OR "développeur mobile" OR "mobile developer")'
                   if canon_country in ("tunisia", "france", "morocco", "algeria")
                   else f'("{first_word}" OR "mobile developer")')
            sq.append(f"{alt} ({joined}) -inurl:similar -inurl:all")
        for q_str in sq[:2]:
            f = _submit(f"serper:{canon_country}", _partial(_serper_local, q_str, canon_country, cfg, tbs, serper_key),
                        f"{q_str}|{tbs}")
            if f is not None:
                futs.append(f)

    # 3. Zero-key Yahoo discovery: up-front when the country has few direct scrapers
    yahoo_futs: list = []

    def _launch_yahoo():
        for cl in clauses[:2]:
            f = _submit(f"yahoo:{cl}", _partial(_yahoo_clause_discovery, core_kw, cl, canon_country, cfg), core_kw)
            if f is not None:
                yahoo_futs.append(f)

    if clauses and len(direct_fns) < 2:
        _launch_yahoo()

    from concurrent.futures import FIRST_COMPLETED
    pending_local = set(futs + yahoo_futs)
    deadline_local = t_start + budget
    collected_count = 0
    while pending_local:
        rem = deadline_local - _time.time()
        if rem <= 0:
            break
        done_l, pending_local = wait(pending_local, timeout=rem, return_when=FIRST_COMPLETED)
        for dfut in done_l:
            if not dfut.cancelled() and not dfut.exception():
                collected_count += len(dfut.result() or [])
        if collected_count >= 6:
            deadline_local = min(deadline_local, _time.time() + 0.45)
    raw_rows = _collect(futs)

    # 3b. Direct boards found almost nothing -> Yahoo with remaining budget (only if budget > 2.6s, i.e. deep wave)
    if len(raw_rows) < 2 and clauses and not yahoo_futs and budget >= 2.6:
        rem_y = max(0.8, budget - (_time.time() - t_start))
        _launch_yahoo()
        wait(yahoo_futs, timeout=rem_y)
    raw_rows.extend(_collect(yahoo_futs))

    # 4. Deduplicate by canonical posting URL
    from .search_engine import canonical_url
    unique_rows: List[dict] = []
    seen_keys: Dict[str, dict] = {}
    for r in raw_rows:
        u_key = canonical_url(r.get("job_url") or "")
        if not u_key:
            continue
        prev = seen_keys.get(u_key)
        if prev is not None:
            if (prev.get("company") or "").startswith(("Entreprise (", "Employer via ")) and \
                    not (r.get("company") or "").startswith(("Entreprise (", "Employer via ")):
                prev["company"] = r["company"]
            if len(r.get("description") or "") > len(prev.get("description") or ""):
                prev["description"] = r["description"]
            continue
        seen_keys[u_key] = r
        unique_rows.append(r)

    # 5. Drop closed postings and verify relevance against the user's query variants
    default_recent_date = (datetime.utcnow().date() - timedelta(days=2)).isoformat()
    out: List[dict] = []
    for r in unique_rows:
        if r.get("is_closed"):
            continue
        if best_relevance(queries, r.get("title", ""), r.get("description", ""), r.get("company", "")) < 20:
            continue
        if not r.get("date_posted"):
            r["date_posted"] = default_recent_date
        out.append(r)

    logger.info(f"[LocalBoards] {canon_country} '{core_kw}': {len(out)} relevant / {len(unique_rows)} unique "
                f"from {len(direct_fns)} boards in {(_time.time() - t_start):.2f}s")
    return out


def prewarm_country(country: str, query: str) -> None:
    """Fire-and-forget: start every local scraper for (country, query) so the next search is a cache hit."""
    try:
        _LOCAL_POOL.submit(fetch_country_local_boards, [query], country, None, "", 0.1)
    except Exception:
        pass


def local_boards_health() -> dict:
    """Per-country / per-scraper health for the back office."""
    now = _time.time()
    with _eng_lock:
        health = {k: dict(v) for k, v in _health.items()}
        cache_size, inflight = len(_row_cache), len(_inflight)
    countries = {}
    for canon in COUNTRY_LOCAL_BOARDS:
        scr = []
        for fn in scrapers_for_country(canon):
            name = _fn_key(fn)
            h = health.get(name, {})
            scr.append({
                "scraper": name.rsplit(".", 1)[-1],
                "module": name.rsplit(".", 1)[0].rsplit(".", 1)[-1],
                "calls": h.get("calls", 0),
                "hit_rate": round(h["with_rows"] / h["calls"], 2) if h.get("calls") else None,
                "avg_ms": h.get("avg_ms"),
                "max_ms": h.get("max_ms"),
                "errors": h.get("errors", 0),
                "slow": h.get("slow", 0),
                "last_rows": h.get("last_rows"),
                "breaker_open": h.get("skip_until", 0) > now,
            })
        countries[canon] = {"boards": boards_for_country(canon), "scrapers": scr}
    return {
        "budget_s": LOCAL_BUDGET_S,
        "cache_entries": cache_size,
        "inflight": inflight,
        "serper_disabled": now < _serper_off_until,
        "countries": countries,
    }
