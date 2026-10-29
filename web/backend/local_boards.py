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
from datetime import datetime, date
from typing import Dict, List, Optional
from urllib.parse import urlparse, unquote

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
_adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
_LOCAL_SESSION.mount("https://", _adapter)
_LOCAL_SESSION.mount("http://", _adapter)

_LOCAL_POOL = ThreadPoolExecutor(max_workers=12)

FRENCH_MONTHS = {
    "janvier": 1, "janv": 1, "février": 2, "fevrier": 2, "févr": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7,
    "août": 8, "aout": 8, "septembre": 9, "sept": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "décembre": 12, "decembre": 12, "déc": 12,
}


def _parse_local_date(raw: str) -> str:
    """Convert DD/MM/YYYY or French '16 octobre' / 'Hier' / 'Aujourd'hui' into YYYY-MM-DD or relative string."""
    if not raw:
        return ""
    s = raw.strip()
    low = s.lower()
    today = datetime.now().date()
    if "aujourd" in low or "today" in low or "azi" in low:
        return today.isoformat()
    if "hier" in low or "yesterday" in low or "ieri" in low:
        return "1 day ago"
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
    return s


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
            url = f"https://www.hipo.ro/locuri-de-munca/cautajob/Toate-Domeniile/Toate-Orasele/{urllib.parse.quote(term)}"
            r = _LOCAL_SESSION.get(url, headers=HEADERS, timeout=4.2)
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
        except Exception as e:
            logger.debug(f"[Hipo.ro] {term}: {e}")
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
            params={"q": first_w},
            headers=HEADERS,
            timeout=4.5,
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.find_all("li", attrs={"data-testid": "jobs-item"})[:10]:
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue
            href = a_tag["href"].split("?")[0]
            job_url = f"https://emploitic.com{href}" if href.startswith("/") else href
            parts = [p.strip() for p in li.get_text(" | ", strip=True).split("|") if p.strip()]
            if len(parts) < 2:
                continue
            title = parts[0]
            comp_el = li.find(attrs={"data-testid": "jobs-item-company"})
            company = comp_el.get_text(" ", strip=True) if comp_el else parts[1]
            if company.lower() in ("entreprise anonyme", "anonyme", "confidentiel"):
                company = "Entreprise (Emploitic)"
            location = parts[2] if len(parts) > 2 else "Alger, Algérie"
            if "algérie" not in location.lower() and "algeria" not in location.lower():
                location = f"{location}, Algérie"
            date_posted = _parse_local_date(parts[3]) if len(parts) > 3 else ""
            desc = " ".join(parts[4:]) if len(parts) > 4 else ""
            out.append({
                "site": "emploitic",
                "title": title,
                "company": company,
                "location": location,
                "job_url": job_url,
                "job_url_direct": job_url,
                "description": re.sub(r"<[^>]+>", " ", desc).strip(),
                "date_posted": date_posted,
                "is_remote": "télétravail" in location.lower(),
            })
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
    elif "moj-posao.net" in host:
        if "/posao/" not in low_link or not re.search(r"/posao/\d+/", low_link):
            return None
        board_site = "moj-posao.net"
        parts = [p.strip() for p in raw_title.split(" - ") if p.strip()]
        title = parts[0] if parts else raw_title
        company = parts[1] if len(parts) > 1 else "Employer via MojPosao"
        location = "Zagreb, Croatia"
    elif "kariyer.net" in host or "yenibiris.com" in host:
        if "/is-ilani/" not in low_link or not re.search(r"-\d+$", low_link.split("?")[0].rstrip("/")):
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


def _external_direct_scrapers(canon_country: str) -> list:
    """Collect direct scrapers registered for a country in the per-region scraper modules."""
    fns: list = []
    for mod_name in ("local_scrapers_eu", "local_scrapers_world"):
        try:
            mod = __import__(f"{__package__}.{mod_name}", fromlist=["DIRECT_SCRAPERS"])
            fns.extend(getattr(mod, "DIRECT_SCRAPERS", {}).get(canon_country, []) or [])
        except Exception as e:
            logger.debug(f"[LocalBoards] could not load {mod_name}: {e}")
    return fns


def _safe_scrape(fn, query: str) -> List[dict]:
    """Run a direct scraper and normalise its rows (single postings only, country-tagged, ISO dates)."""
    try:
        rows = fn(query) or []
    except Exception as e:
        logger.debug(f"[LocalBoards] {getattr(fn, '__name__', fn)} failed: {e}")
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("title") or not r.get("job_url"):
            continue
        r.setdefault("job_url_direct", r["job_url"])
        r["date_posted"] = _parse_local_date(str(r.get("date_posted") or ""))
        out.append(r)
    return out


def fetch_country_local_boards(
    queries: List[str],
    country: str,
    hours_old: Optional[int] = None,
    serper_key: str = "",
) -> List[dict]:
    """
    Scrape and discover jobs from the selected country's local job boards
    (e.g. Tanitjobs & Keejob in Tunisia; eJobs, BestJobs, Hipo & DevJob in Romania;
    Welcome to the Jungle, APEC, HelloWork & Free-Work in France).
    """
    c_raw = (country or "").strip().lower()
    if not c_raw or c_raw in ("worldwide", "global", "all", "remote", "anywhere") or c_raw.startswith("remote "):
        return []

    canon_country = COUNTRY_KEY_ALIASES.get(c_raw, c_raw)
    cfg = COUNTRY_LOCAL_BOARDS.get(canon_country)
    if not cfg or not queries:
        return []

    primary_q = queries[0].strip()
    first_word = primary_q.split()[0].lower() if primary_q.split() else primary_q.lower()

    from .search_engine import SINGLE_TECH_TO_ROLE, best_relevance
    core_kw = first_word if first_word in SINGLE_TECH_TO_ROLE else primary_q

    futs = []
    # 1. Launch direct HTML scrapers for countries with fast public local boards
    if canon_country == "tunisia":
        futs.append(_LOCAL_POOL.submit(_scrape_tanitjobs, core_kw))
        futs.append(_LOCAL_POOL.submit(_scrape_keejob, core_kw))
    elif canon_country == "romania":
        futs.append(_LOCAL_POOL.submit(_scrape_hipo_romania, core_kw))
    elif canon_country == "france":
        futs.append(_LOCAL_POOL.submit(_scrape_freework_france, core_kw))
    elif canon_country == "algeria":
        futs.append(_LOCAL_POOL.submit(_scrape_emploitic_algeria, core_kw))

    # 1b. Additional direct scrapers for each country's own job sites (local_scrapers_eu / local_scrapers_world)
    for ext_fn in _external_direct_scrapers(canon_country):
        futs.append(_LOCAL_POOL.submit(_safe_scrape, ext_fn, core_kw))

    # 2. Launch Serper targeted discovery across all local boards for the selected country
    if serper_key and cfg.get("serper_clauses"):
        clauses = " OR ".join(cfg["serper_clauses"])
        if hours_old:
            tbs = "qdr:d" if hours_old <= 24 else ("qdr:w" if hours_old <= 168 else "qdr:m")
        else:
            tbs = "qdr:m3"

        serper_queries = [f"{core_kw} ({clauses}) -inurl:similar -inurl:all"]
        # In local markets where specific framework roles may be titled 'Mobile Developer' / 'Développeur Mobile'
        if first_word in ("flutter", "dart", "kotlin", "swift", "react"):
            alt_term = (
                f'("{first_word}" OR "développeur mobile" OR "mobile developer")'
                if canon_country in ("tunisia", "france", "morocco", "algeria")
                else f'("{first_word}" OR "mobile developer")'
            )
            serper_queries.append(f"{alt_term} ({clauses}) -inurl:similar -inurl:all")

        def _run_serper_local(q_str: str) -> List[dict]:
            payload = {"q": q_str, "gl": cfg["gl"], "num": 10, "tbs": tbs}
            try:
                resp = _LOCAL_SESSION.post(
                    "https://google.serper.dev/search",
                    json=payload,
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    timeout=4.2,
                )
                if resp.status_code != 200:
                    return []
                out_s = []
                for it in resp.json().get("organic", []):
                    parsed = _parse_local_serper_item(it, canon_country, cfg["country_label"])
                    if parsed:
                        out_s.append(parsed)
                return out_s
            except Exception as e:
                logger.debug(f"[LocalBoards Serper] {canon_country}: {e}")
                return []

        for sq in serper_queries[:2]:
            futs.append(_LOCAL_POOL.submit(_run_serper_local, sq))

    wait(futs, timeout=4.8)
    raw_rows: List[dict] = []
    for f in futs:
        if f.done() and not f.exception():
            raw_rows.extend(f.result() or [])

    # Deduplicate by canonical local URL first so we never enrich the same posting twice
    unique_rows: List[dict] = []
    seen_keys: Dict[str, dict] = {}
    for r in raw_rows:
        u_key = (r.get("job_url") or "").split("?")[0].rstrip("/").lower()
        m_tj = re.search(r"tanitjobs\.com/job/(\d+)", u_key)
        if m_tj:
            u_key = f"tanitjobs:{m_tj.group(1)}"
        m_kj = re.search(r"keejob\.com/offres-emploi/(\d+)", u_key)
        if m_kj:
            u_key = f"keejob:{m_kj.group(1)}"
        m_mcf = re.search(r"mycareersfuture\.gov\.sg/job/.*-([0-9a-f]{32})", u_key)
        if m_mcf:
            u_key = f"mycareersfuture:{m_mcf.group(1)}"
        if not u_key:
            continue
        if u_key in seen_keys:
            prev = seen_keys[u_key]
            if (prev.get("company") or "").startswith(("Entreprise (", "Employer via ")) and not (r.get("company") or "").startswith(("Entreprise (", "Employer via ")):
                prev["company"] = r["company"]
            if len(r.get("description") or "") > len(prev.get("description") or ""):
                prev["description"] = r["description"]
            continue
        seen_keys[u_key] = r
        unique_rows.append(r)

    # Enrich all unique Tanitjobs rows in parallel (verify open/closed status + extract real company & full description)
    tj_all = [r for r in unique_rows if r.get("site") == "tanitjobs"]
    tj_all.sort(key=lambda r: (
        0 if first_word in (r.get("title") or "").lower() else 1,
        0 if (r.get("company") or "").startswith("Entreprise (") else 1,
    ))
    tj_rows = tj_all[:14]
    if tj_rows:
        def _verify_tj(row: dict):
            det = fetch_tanitjobs_detail(row["job_url"])
            if det.get("is_closed"):
                row["is_closed"] = True
            if det.get("company") and det["company"].lower() not in ("société anonyme", "anonyme", "confidentiel"):
                row["company"] = det["company"]
            if det.get("location") and ("tunisie" in det["location"].lower() or "tunisia" in det["location"].lower()):
                row["location"] = det["location"]
            if det.get("description") and len(det["description"]) > len(row.get("description") or ""):
                row["description"] = det["description"]
        with ThreadPoolExecutor(max_workers=8) as tj_pool:
            wait([tj_pool.submit(_verify_tj, r) for r in tj_rows], timeout=3.2)

    # Filter out closed postings and verify relevance against the user's queries
    deduped: List[dict] = []
    for r in unique_rows:
        if r.get("is_closed"):
            continue
        rel = best_relevance(queries, r.get("title", ""), r.get("description", ""), r.get("company", ""))
        if rel < 20:
            continue
        deduped.append(r)

    return deduped
