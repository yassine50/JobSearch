"""
Search Quality Engine
=====================
Pure-python helpers used by /api/jobs/search to get MORE results with BETTER quality:

1. Query expansion   – equivalent job titles (+ French variants for French-speaking markets)
                       so each board is searched with several phrasings of the same role.
2. Relevance scoring – whole-word, synonym-aware title/description matching. Stops false
                       positives such as "Developer" matching the company "Atlantic Developments".
3. Smart dedup/merge – the same job found on several boards / query variants is merged into
                       one card (best description, union of recruiter emails, freshest date).
4. Spam filtering    – drops commission-only / MLM / "earn $$$ from home" style listings.
5. Quality ranking   – relevance + freshness + description richness + salary + recruiter email.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary
# ─────────────────────────────────────────────────────────────────────────────

STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with", "on", "de", "des",
    "du", "la", "le", "les", "et", "en", "h", "f", "m", "x", "hf", "fh", "mf", "fm", "w",
}

# Seniority / contract words: useful for ranking but must never be *required* to match.
SOFT_WORDS: Set[str] = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "chief", "head", "mid",
    "entry", "level", "intern", "internship", "trainee", "graduate", "associate", "remote",
    "hybrid", "onsite", "contract", "freelance", "temporary", "temp", "permanent", "full",
    "part", "time", "i", "ii", "iii", "iv", "confirme", "confirmé", "stage", "stagiaire",
    "alternance", "cdi", "cdd", "new", "experienced",
}

# Tokens that are interchangeable inside a job title (across EN, FR, ES, PT, DE, IT, RO, PL, NL).
TOKEN_EQUIV: List[Set[str]] = [
    {"developer", "engineer", "programmer", "dev", "développeur", "developpeur", "ingénieur",
     "ingenieur", "coder", "swe", "sde", "desarrollador", "programador", "ingeniero",
     "desenvolvedor", "engenheiro", "entwickler", "softwareentwickler", "sviluppatore",
     "ingegnere", "programista", "inżynier", "inzynier", "programator", "dezvoltator",
     "inginer", "ontwikkelaar", "utvecklare", "udvikler", "utvikler"},
    {"software", "logiciel", "application", "applications", "app", "soft", "sistemas", "oprogramowania"},
    {"frontend", "front", "ui"},
    {"backend", "back", "server"},
    {"fullstack", "full-stack", "stack"},
    {"javascript", "js"},
    {"typescript", "ts"},
    {"react", "reactjs"},
    {"node", "nodejs"},
    {"vue", "vuejs"},
    {"angular", "angularjs"},
    {"golang", "go"},
    {"python", "django", "flask", "fastapi"},
    {"flutter", "dart"},
    {"android", "kotlin"},
    {"ios", "swift"},
    {"mobile", "móvil", "movil", "мобильный"},
    {"devops", "sre", "reliability", "platform"},
    {"cloud", "aws", "azure", "gcp"},
    {"ml", "machine", "ai", "artificial", "ia", "ki"},
    {"data", "données", "donnees", "analytics", "datos", "dados", "daten"},
    {"analyst", "analyste", "analista"},
    {"scientist", "science", "científico", "cientifico", "cientista"},
    {"manager", "management", "gestionnaire", "responsable", "gerente", "gestor"},
    {"designer", "design", "ux", "diseñador", "disenador"},
    {"security", "cybersecurity", "sécurité", "securite", "infosec", "seguridad", "sicherheit"},
    {"support", "helpdesk", "technician", "technicien", "soporte", "suporte"},
    {"administrator", "admin", "administrateur", "administrador"},
    {"network", "réseau", "reseau", "networking", "redes", "netzwerk"},
    {"qa", "quality", "test", "tester", "testing", "automation", "testeur", "pruebas"},
    {"accountant", "comptable", "accounting", "contador", "contable"},
    {"sales", "commercial", "vente", "ventas", "vendas", "vertrieb"},
    {"marketing", "marketeur"},
    {"consultant", "consulting", "consultor", "berater"},
    {"architect", "architecte", "architecture", "arquitecto", "arquiteto", "architekt"},
    {"product", "produit", "producto", "produto", "produkt"},
    {"project", "projet", "proyecto", "projeto", "projekt"},
    {"business", "bi"},
    {"web", "website"},
]

_EQUIV_INDEX: Dict[str, int] = {}
for _i, _grp in enumerate(TOKEN_EQUIV):
    for _w in _grp:
        _EQUIV_INDEX[_w] = _i

# Full-title synonym groups used for query expansion (first = canonical).
ROLE_SYNONYMS: List[List[str]] = [
    ["software developer", "software engineer", "application developer", "programmer"],
    ["full stack developer", "full stack engineer", "fullstack developer"],
    ["frontend developer", "front end developer", "frontend engineer", "react developer"],
    ["backend developer", "back end developer", "backend engineer"],
    ["web developer", "web engineer", "frontend developer"],
    ["mobile developer", "mobile engineer", "android developer", "ios developer"],
    ["flutter developer", "flutter engineer", "dart developer"],
    ["react developer", "frontend developer", "react engineer"],
    ["python developer", "python engineer", "backend developer"],
    ["java developer", "java engineer", "backend developer"],
    ["devops engineer", "site reliability engineer", "platform engineer", "cloud engineer"],
    ["cloud engineer", "devops engineer", "aws engineer"],
    ["data analyst", "business intelligence analyst", "bi analyst", "reporting analyst"],
    ["data scientist", "machine learning engineer", "ai engineer"],
    ["machine learning engineer", "ml engineer", "ai engineer", "data scientist"],
    ["ai engineer", "machine learning engineer", "llm engineer"],
    ["data engineer", "etl developer", "big data engineer"],
    ["qa engineer", "test automation engineer", "software tester", "quality assurance analyst"],
    ["ui ux designer", "product designer", "ux designer", "ui designer"],
    ["product manager", "product owner", "technical product manager"],
    ["project manager", "it project manager", "program manager"],
    ["it support", "help desk technician", "it technician", "desktop support"],
    ["system administrator", "systems administrator", "it administrator", "sysadmin"],
    ["network engineer", "network administrator", "network technician"],
    ["cybersecurity analyst", "security analyst", "information security analyst", "soc analyst"],
    ["business analyst", "it business analyst", "functional analyst"],
    ["accountant", "staff accountant", "bookkeeper"],
    ["digital marketing", "marketing specialist", "growth marketer"],
]

# French equivalents (searched additionally in French-speaking markets).
FRENCH_TITLES: Dict[str, List[str]] = {
    "software developer": ["développeur logiciel", "ingénieur logiciel"],
    "software engineer": ["ingénieur logiciel", "développeur logiciel"],
    "full stack developer": ["développeur full stack"],
    "frontend developer": ["développeur front-end"],
    "backend developer": ["développeur back-end"],
    "web developer": ["développeur web"],
    "mobile developer": ["développeur mobile"],
    "flutter developer": ["développeur flutter", "développeur mobile"],
    "react developer": ["développeur react"],
    "python developer": ["développeur python"],
    "java developer": ["développeur java"],
    "devops engineer": ["ingénieur devops"],
    "data analyst": ["analyste de données", "data analyst"],
    "data scientist": ["data scientist", "scientifique des données"],
    "data engineer": ["ingénieur data", "data engineer"],
    "machine learning engineer": ["ingénieur machine learning", "ingénieur ia"],
    "ai engineer": ["ingénieur ia", "ingénieur intelligence artificielle"],
    "qa engineer": ["ingénieur qa", "testeur logiciel"],
    "product manager": ["chef de produit", "product manager"],
    "project manager": ["chef de projet", "chef de projet informatique"],
    "it support": ["technicien support informatique", "support informatique"],
    "system administrator": ["administrateur système"],
    "network engineer": ["ingénieur réseau"],
    "cybersecurity analyst": ["analyste cybersécurité"],
    "business analyst": ["analyste fonctionnel", "business analyst"],
    "accountant": ["comptable"],
}

FRENCH_MARKETS: Set[str] = {"france", "fr", "morocco", "ma", "belgium", "switzerland", "quebec",
                            "luxembourg", "tunisia", "algeria", "senegal"}
SPANISH_MARKETS: Set[str] = {"spain", "es", "mexico", "mx", "colombia", "co", "argentina", "ar", "chile", "cl"}
PORTUGUESE_MARKETS: Set[str] = {"portugal", "pt", "brazil", "br"}
GERMAN_MARKETS: Set[str] = {"germany", "de", "austria", "at", "switzerland", "ch"}
ROMANIAN_MARKETS: Set[str] = {"romania", "ro"}
ITALIAN_MARKETS: Set[str] = {"italy", "it"}
POLISH_MARKETS: Set[str] = {"poland", "pl"}

SPANISH_TITLES: Dict[str, List[str]] = {
    "software developer": ["desarrollador de software", "ingeniero de software"],
    "software engineer": ["ingeniero de software", "desarrollador de software"],
    "full stack developer": ["desarrollador full stack"],
    "frontend developer": ["desarrollador frontend"],
    "backend developer": ["desarrollador backend"],
    "mobile developer": ["desarrollador móvil", "desarrollador mobile"],
    "flutter developer": ["desarrollador flutter", "desarrollador mobile"],
    "react developer": ["desarrollador react"],
    "python developer": ["desarrollador python"],
    "java developer": ["desarrollador java"],
    "data analyst": ["analista de datos"],
    "data engineer": ["ingeniero de datos"],
}

PORTUGUESE_TITLES: Dict[str, List[str]] = {
    "software developer": ["desenvolvedor de software", "programador"],
    "software engineer": ["engenheiro de software", "desenvolvedor de software"],
    "full stack developer": ["desenvolvedor full stack", "programador full stack"],
    "frontend developer": ["desenvolvedor frontend"],
    "backend developer": ["desenvolvedor backend"],
    "mobile developer": ["desenvolvedor mobile", "programador mobile"],
    "flutter developer": ["desenvolvedor flutter", "programador flutter"],
    "react developer": ["desenvolvedor react"],
    "python developer": ["desenvolvedor python", "programador python"],
    "java developer": ["desenvolvedor java", "programador java"],
}

GERMAN_TITLES: Dict[str, List[str]] = {
    "software developer": ["softwareentwickler", "software engineer"],
    "software engineer": ["softwareentwickler", "software ingenieur"],
    "full stack developer": ["full stack entwickler"],
    "frontend developer": ["frontend entwickler"],
    "backend developer": ["backend entwickler"],
    "mobile developer": ["mobile entwickler", "app entwickler"],
    "flutter developer": ["flutter entwickler", "mobile entwickler"],
    "python developer": ["python entwickler"],
    "java developer": ["java entwickler"],
}

SPAM_PATTERNS = re.compile(
    r"(commission[\s-]*only|100%\s*commission|earn\s+\$?\d{3,}|\$\d{3,}\s*(?:/|per)\s*(?:day|week)|"
    r"\bmlm\b|network\s+marketing|be\s+your\s+own\s+boss|work\s+from\s+home\s*!{1,}|"
    r"no\s+experience\s+needed\s*!|crypto\s+trading\s+signals|paid\s+surveys?|mystery\s+shopper|"
    r"data\s+entry\s*-\s*\$|sign[\s-]*on\s+bonus\s+\$\d{4,}.*driver)",
    re.IGNORECASE,
)

BAD_COMPANY = {
    "", "confidential", "n/a", "na", "none", "nan", "unknown", "private",
    "careers", "jobs", "job", "hiring", "recruitment", " work ", "mobile",
    "indeed", "linkedin", "glassdoor", "jooble", "adzuna", "careerjet",
    "ejobs", "ejobs.ro", "bestjobs", "bestjobs.eu", "devjob", "devjob.ro",
    "devjobsscanner", "hipo", "hipo.ro", "undelucram", "rubyonremote",
    "wellfound", "angellist", "upwork", "fiverr", "freelancer", "toptal",
    "ziprecruiter", "simplyhired", "monster", "talent", "talent.com",
    "neuvoo", "trovit", "mitula", "remotive", "remoteok", "weworkremotely",
    "himalayas", "jobicy", "workingnomads", "arbeitnow", "freehire",
    "ro", "fr", "de", "uk", "gb", "us", "ca", "nl", "es", "it", "pl", "pt", "in", "br", "au",
}

# Known job-search aggregator domains / URL patterns that are NOT single employer job postings
AGGREGATOR_URL_PATTERNS = re.compile(
    r"("
    r"devjobsscanner\.com|"
    r"rubyonremote\.com|"
    r"mobile\.career/locations|"
    r"devjob\.ro/(?:[a-z]{2}/)?jobs(?:/[^/]+)?(?:/all)?/?$|"
    r"ejobs\.ro/locuri-de-munca(?:/[^/]+)?/?$|"
    r"bestjobs\.eu/(?:[a-z]{2}/)?locuri-de-munca|"
    r"hipo\.ro/locuri-de-munca/cautajob|"
    r"undelucram\.ro|"
    r"glassdoor\.[a-z.]+/(?:Job|Jobs|Salaries|Overview|Reviews)/|"
    r"linkedin\.com/jobs/(?:search|collections|[^/]+-jobs)|"
    r"indeed\.[a-z.]+/(?:jobs|q-|m/jobs|companies)|"
    r"jooble\.org/(?:jobs-|SearchResult)|"
    r"careerjet\.[a-z.]+/(?:search|.*-jobs\.html)|"
    r"wellfound\.com/(?:role|jobs/?$)|"
    r"upwork\.com/(?:hire|freelance-jobs|nx/search)|"
    r"fiverr\.com/|freelancer\.com/jobs|"
    r"simplyhired\.[a-z.]+/search|"
    r"monster\.[a-z.]+/jobs/search|"
    r"ziprecruiter\.[a-z.]+/Jobs/|"
    r"talent\.com/jobs|"
    r"whatjobs\.[a-z.]+/|"
    r"trovit\.[a-z.]+/|mitula\.[a-z.]+/|neuvoo\.[a-z.]+/|"
    r"://[^/]+/(?:en/|ro/|fr/|de/)?(?:careers|jobs|vacancies|openings|locations/[^/]+)/?$"
    r")",
    re.IGNORECASE,
)

# Titles that indicate a job board search-results page or directory rather than an individual role
AGGREGATOR_TITLE_PATTERNS = re.compile(
    r"("
    r"^\d+\+?\s+.*\bjobs?\b|"
    r"\bjobs?\s+in\s+[a-z\s🇷🇴🇺🇸🇬🇧🇫🇷🇩🇪🇨🇦]+$|"
    r"^hire\s+the\s+best\b|"
    r"^find\s+your\s+(?:perfect|next)\s+role\b|"
    r"^jobs?\s+at\s+|"
    r"^locuri\s+de\s+munc[aă]\b|"
    r"^offres\s+d['’`]emploi\b|"
    r"^stellenangebote\b|"
    r"^ofertas\s+de\s+empleo\b|"
    r"^vacatures\b|"
    r"^urgent!\s+.*\bjobs?\b|"
    r"^browse\s+.*\bjobs?\b"
    r")",
    re.IGNORECASE,
)


def is_aggregator_or_non_posting(title: str, url: str = "", company: str = "") -> bool:
    """Return True if a scraped item is another job search platform / category page or has a fake aggregator company."""
    t = (title or "").strip()
    u = (url or "").strip()
    c = (company or "").strip().lower()
    if not t or len(t) <= 3:
        return True
    # Single-word city/country titles like "Cluj." or "Romania"
    if re.fullmatch(r"[A-Za-zÀ-ÿ\s.-]{1,18}\.", t):
        return True
    if AGGREGATOR_TITLE_PATTERNS.search(t):
        return True
    if u and AGGREGATOR_URL_PATTERNS.search(u):
        return True
    c_clean = re.sub(r"^www\.", "", c).strip()
    if c_clean in BAD_COMPANY and c_clean not in ("", "confidential", "unknown", "n/a", "na", "none"):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Country & City Location Verification
# ─────────────────────────────────────────────────────────────────────────────

COUNTRY_KEYWORDS: Dict[str, Dict[str, Set[str]]] = {
    "romania": {
        "names": {"romania", "roumanie", "românia", "rumänien"},
        "iso": {"ro", "rou"},
        "cities": {
            "bucharest", "bucuresti", "bucurești", "cluj", "cluj-napoca", "cluj napoca",
            "timisoara", "timișoara", "iasi", "iași", "brasov", "brașov", "constanta",
            "constanța", "sibiu", "oradea", "craiova", "galati", "galați", "ploiesti",
            "ploiești", "arad", "pitesti", "pitești", "bacau", "bacău", "targu mures",
            "târgu mureș", "baia mare", "suceava", "buzau", "buzău", "botosani",
            "botoșani", "satu mare", "ramnicu valcea", "alba iulia", "targoviste", "ilfov",
        },
    },
    "france": {
        "names": {"france", "frankreich"},
        "iso": {"fr", "fra"},
        "cities": {
            "paris", "lyon", "marseille", "toulouse", "nice", "nantes", "montpellier",
            "strasbourg", "bordeaux", "lille", "rennes", "grenoble", "sophia antipolis",
            "aix-en-provence", "courbevoie", "puteaux", "la defense", "la défense",
            "boulogne-billancourt", "issy-les-moulineaux", "levallois-perret", "saint-denis",
            "nanterre", "massy", "ile-de-france", "île-de-france",
        },
    },
    "germany": {
        "names": {"germany", "deutschland", "allemagne"},
        "iso": {"de", "deu"},
        "cities": {
            "berlin", "munich", "münchen", "munchen", "hamburg", "frankfurt", "cologne",
            "köln", "koln", "stuttgart", "düsseldorf", "dusseldorf", "leipzig", "dortmund",
            "essen", "bremen", "dresden", "hanover", "hannover", "nuremberg", "nürnberg",
            "karlsruhe", "mannheim", "bonn", "walldorf", "heidelberg", "darmstadt",
        },
    },
    "uk": {
        "names": {"united kingdom", "uk", "great britain", "britain", "england", "scotland", "wales", "northern ireland"},
        "iso": {"gb", "uk", "gbr"},
        "cities": {
            "london", "manchester", "birmingham", "leeds", "glasgow", "edinburgh",
            "bristol", "liverpool", "sheffield", "newcastle", "nottingham", "cardiff",
            "belfast", "cambridge", "oxford", "reading", "brighton", "southampton",
        },
    },
    "usa": {
        "names": {"united states", "usa", "u.s.", "u.s.a.", "america"},
        "iso": {"us", "usa"},
        "cities": {
            "new york", "san francisco", "los angeles", "chicago", "seattle", "austin",
            "boston", "denver", "atlanta", "dallas", "houston", "miami", "washington",
            "san jose", "san diego", "philadelphia", "phoenix", "palo alto", "mountain view",
            "sunnyvale", "menlo park", "cupertino", "redmond", "bellevue", "portland",
            "charlotte", "minneapolis", "detroit", "salt lake city", "raleigh", "pittsburgh",
        },
    },
    "canada": {
        "names": {"canada"},
        "iso": {"ca", "can"},
        "cities": {
            "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "edmonton",
            "quebec", "québec", "winnipeg", "hamilton", "waterloo", "kitchener", "MISSISSAUGA".lower(),
            "markham", "halifax", "victoria", "burnaby", "surrey", "laval", "ontario",
            "british columbia", "alberta",
        },
    },
    "netherlands": {
        "names": {"netherlands", "nederland", "holland", "pays-bas"},
        "iso": {"nl", "nld"},
        "cities": {"amsterdam", "rotterdam", "the hague", "den haag", "utrecht", "eindhoven", "delft", "groningen", "leiden", "haarlem"},
    },
    "spain": {
        "names": {"spain", "españa", "espana", "espagne"},
        "iso": {"es", "esp"},
        "cities": {"madrid", "barcelona", "valencia", "seville", "sevilla", "bilbao", "malaga", "málaga", "zaragoza", "alicante"},
    },
    "italy": {
        "names": {"italy", "italia", "italie"},
        "iso": {"it", "ita"},
        "cities": {"milan", "milano", "rome", "roma", "turin", "torino", "bologna", "florence", "firenze", "naples", "napoli", "genoa", "verona"},
    },
    "poland": {
        "names": {"poland", "polska", "pologne"},
        "iso": {"pl", "pol"},
        "cities": {"warsaw", "warszawa", "krakow", "kraków", "wroclaw", "wrocław", "gdansk", "gdańsk", "poznan", "poznań", "katowice", "lodz", "łódź"},
    },
    "portugal": {
        "names": {"portugal"},
        "iso": {"pt", "prt"},
        "cities": {"lisbon", "lisboa", "porto", "braga", "coimbra", "aveiro", "faro"},
    },
    "switzerland": {
        "names": {"switzerland", "schweiz", "suisse", "svizzera"},
        "iso": {"ch", "che"},
        "cities": {"zurich", "zürich", "geneva", "genève", "geneve", "basel", "bern", "lausanne", "zug", "lugano"},
    },
    "belgium": {
        "names": {"belgium", "belgique", "belgië", "belgie"},
        "iso": {"be", "bel"},
        "cities": {"brussels", "bruxelles", "antwerp", "antwerpen", "ghent", "gent", "leuven", "liege", "liège"},
    },
    "austria": {
        "names": {"austria", "österreich", "osterreich", "autriche"},
        "iso": {"at", "aut"},
        "cities": {"vienna", "wien", "graz", "linz", "salzburg", "innsbruck"},
    },
    "sweden": {
        "names": {"sweden", "sverige", "suède"},
        "iso": {"se", "swe"},
        "cities": {"stockholm", "gothenburg", "göteborg", "malmo", "malmö", "uppsala", "lund"},
    },
    "ireland": {
        "names": {"ireland", "éire"},
        "iso": {"ie", "irl"},
        "cities": {"dublin", "cork", "galway", "limerick", "waterford"},
    },
    "denmark": {
        "names": {"denmark", "danmark"},
        "iso": {"dk", "dnk"},
        "cities": {"copenhagen", "københavn", "aarhus", "odense", "aalborg"},
    },
    "norway": {
        "names": {"norway", "norge"},
        "iso": {"no", "nor"},
        "cities": {"oslo", "bergen", "trondheim", "stavanger"},
    },
    "finland": {
        "names": {"finland", "suomi"},
        "iso": {"fi", "fin"},
        "cities": {"helsinki", "espoo", "tampere", "oulu", "turku"},
    },
    "uae": {
        "names": {"united arab emirates", "uae", "emirates"},
        "iso": {"ae", "are"},
        "cities": {"dubai", "abu dhabi", "sharjah", "ajman"},
    },
    "saudi arabia": {
        "names": {"saudi arabia", "kingdom of saudi arabia", "ksa"},
        "iso": {"sa", "sau"},
        "cities": {"riyadh", "jeddah", "dammam", "khobar", "neom"},
    },
    "morocco": {
        "names": {"morocco", "maroc"},
        "iso": {"ma", "mar"},
        "cities": {"casablanca", "rabat", "marrakech", "tangier", "tanger", "fes", "fès", "agadir", "oujda", "kenitra", "tetouan"},
    },
    "tunisia": {
        "names": {"tunisia", "tunisie", "تونس"},
        "iso": {"tn", "tun"},
        "cities": {
            "tunis", "grand tunis", "sfax", "sousse", "ariana", "monastir", "nabeul",
            "hammamet", "bizerte", "ben arous", "manouba", "la marsa", "marsa", "carthage",
            "les berges du lac", "lac 1", "lac 2", "el ghazala", "ghazela", "technopole",
            "centre urbain nord", "charguia", "megrine", "mégrine", "mahdia", "kairouan",
            "gabes", "gabès", "gafsa", "djerba", "zarzis", "kasserine", "beja", "béja",
            "jendouba", "kef", "siliana", "sidi bouzid", "tozeur", "kebili", "tataouine",
            "medenine", "médenine", "zaghouan",
        },
    },
    "algeria": {
        "names": {"algeria", "algérie", "algerie", "الجزائر"},
        "iso": {"dz", "dza"},
        "cities": {"algiers", "alger", "oran", "constantine", "annaba", "blida", "setif", "sétif", "tlemcen", "bejaia", "béjaïa"},
    },
    "egypt": {
        "names": {"egypt", "égypte"},
        "iso": {"eg", "egy"},
        "cities": {"cairo", "giza", "alexandria", "new cairo", "maadi"},
    },
    "qatar": {
        "names": {"qatar"},
        "iso": {"qa", "qat"},
        "cities": {"doha", "lusail"},
    },
    "singapore": {
        "names": {"singapore"},
        "iso": {"sg", "sgp"},
        "cities": {"singapore"},
    },
    "india": {
        "names": {"india"},
        "iso": {"in", "ind"},
        "cities": {"bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "hyderabad", "pune", "chennai", "gurugram", "gurgaon", "noida", "kolkata", "ahmedabad", "kochi", "thiruvananthapuram"},
    },
    "australia": {
        "names": {"australia"},
        "iso": {"au", "aus"},
        "cities": {"sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra"},
    },
    "new zealand": {
        "names": {"new zealand", "aotearoa"},
        "iso": {"nz", "nzl"},
        "cities": {"auckland", "wellington", "christchurch", "hamilton", "tauranga", "dunedin"},
    },
    "japan": {
        "names": {"japan", "nippon", "日本"},
        "iso": {"jp", "jpn"},
        "cities": {"tokyo", "osaka", "yokohama", "nagoya", "fukuoka", "sapporo", "kyoto", "kobe", "shibuya", "minato"},
    },
    "south korea": {
        "names": {"south korea", "korea", "republic of korea", "대한민국", "한국"},
        "iso": {"kr", "kor"},
        "cities": {"seoul", "busan", "incheon", "daegu", "daejeon", "gwangju", "suwon", "pangyo", "seongnam", "gangnam"},
    },
    "malaysia": {
        "names": {"malaysia"},
        "iso": {"my", "mys"},
        "cities": {"kuala lumpur", "petaling jaya", "penang", "george town", "johor bahru", "cyberjaya", "selangor", "shah alam", "subang jaya"},
    },
    "philippines": {
        "names": {"philippines"},
        "iso": {"ph", "phl"},
        "cities": {"manila", "metro manila", "makati", "taguig", "bgc", "quezon city", "pasig", "cebu", "mandaluyong", "alabang", "davao"},
    },
    "indonesia": {
        "names": {"indonesia"},
        "iso": {"id", "idn"},
        "cities": {"jakarta", "south jakarta", "jakarta selatan", "bandung", "surabaya", "yogyakarta", "tangerang", "bali", "denpasar", "medan", "semarang"},
    },
    "mexico": {
        "names": {"mexico", "méxico"},
        "iso": {"mx", "mex"},
        "cities": {"mexico city", "ciudad de méxico", "cdmx", "guadalajara", "monterrey", "querétaro", "queretaro", "puebla", "tijuana", "merida", "mérida", "jalisco", "nuevo león"},
    },
    "brazil": {
        "names": {"brazil", "brasil"},
        "iso": {"br", "bra"},
        "cities": {"são paulo", "sao paulo", "rio de janeiro", "belo horizonte", "curitiba", "porto alegre", "florianópolis", "florianopolis", "brasília", "brasilia", "campinas", "recife", "fortaleza"},
    },
    "argentina": {
        "names": {"argentina"},
        "iso": {"ar", "arg"},
        "cities": {"buenos aires", "caba", "capital federal", "córdoba", "cordoba", "rosario", "mendoza", "la plata", "mar del plata"},
    },
    "colombia": {
        "names": {"colombia"},
        "iso": {"co", "col"},
        "cities": {"bogotá", "bogota", "medellín", "medellin", "cali", "barranquilla", "cartagena", "bucaramanga", "antioquia"},
    },
    "chile": {
        "names": {"chile"},
        "iso": {"cl", "chl"},
        "cities": {"santiago", "las condes", "providencia", "valparaíso", "valparaiso", "viña del mar", "concepción", "concepcion", "región metropolitana"},
    },
    "czech republic": {
        "names": {"czech republic", "czechia", "česká republika", "česko"},
        "iso": {"cz", "cze"},
        "cities": {"prague", "praha", "brno", "ostrava", "plzeň", "plzen", "liberec", "olomouc"},
    },
    "hungary": {
        "names": {"hungary", "magyarország"},
        "iso": {"hu", "hun"},
        "cities": {"budapest", "debrecen", "szeged", "miskolc", "pécs", "pecs", "győr", "gyor"},
    },
    "bulgaria": {
        "names": {"bulgaria", "българия"},
        "iso": {"bg", "bgr"},
        "cities": {"sofia", "софия", "plovdiv", "varna", "burgas", "ruse", "stara zagora"},
    },
    "greece": {
        "names": {"greece", "hellas", "ελλάδα"},
        "iso": {"gr", "grc"},
        "cities": {"athens", "αθήνα", "thessaloniki", "θεσσαλονίκη", "patras", "heraklion", "larissa", "marousi", "chalandri", "attica", "αττική"},
    },
    "croatia": {
        "names": {"croatia", "hrvatska"},
        "iso": {"hr", "hrv"},
        "cities": {"zagreb", "split", "rijeka", "osijek", "zadar", "pula", "varaždin"},
    },
    "turkey": {
        "names": {"turkey", "türkiye", "turkiye"},
        "iso": {"tr", "tur"},
        "cities": {"istanbul", "ankara", "izmir", "bursa", "antalya", "kocaeli", "adana", "gaziantep"},
    },
    "ukraine": {
        "names": {"ukraine", "україна"},
        "iso": {"ua", "ukr"},
        "cities": {"kyiv", "kiev", "київ", "lviv", "львів", "kharkiv", "харків", "odesa", "odessa", "dnipro", "дніпро", "vinnytsia", "ivano-frankivsk"},
    },
    "kuwait": {
        "names": {"kuwait", "الكويت"},
        "iso": {"kw", "kwt"},
        "cities": {"kuwait city", "al asimah", "hawalli", "salmiya", "farwaniya", "ahmadi"},
    },
    "bahrain": {
        "names": {"bahrain", "البحرين"},
        "iso": {"bh", "bhr"},
        "cities": {"manama", "muharraq", "riffa", "seef"},
    },
    "oman": {
        "names": {"oman", "عمان"},
        "iso": {"om", "omn"},
        "cities": {"muscat", "salalah", "sohar", "nizwa", "seeb", "bawshar"},
    },
    "jordan": {
        "names": {"jordan", "الأردن"},
        "iso": {"jo", "jor"},
        "cities": {"amman", "irbid", "zarqa", "aqaba", "abdali"},
    },
    "south africa": {
        "names": {"south africa"},
        "iso": {"za", "zaf"},
        "cities": {"johannesburg", "cape town", "durban", "pretoria", "sandton", "centurion", "midrand", "stellenbosch", "gauteng", "western cape"},
    },
}

COUNTRY_ALIAS_TO_CANON: Dict[str, str] = {}
for _canon, _info in COUNTRY_KEYWORDS.items():
    COUNTRY_ALIAS_TO_CANON[_canon] = _canon
    for _n in _info["names"]:
        COUNTRY_ALIAS_TO_CANON[_n] = _canon
    for _iso in _info["iso"]:
        COUNTRY_ALIAS_TO_CANON[_iso] = _canon


def _canonical_country(country_str: str) -> str:
    c = (country_str or "").strip().lower()
    return COUNTRY_ALIAS_TO_CANON.get(c, c)


def _text_matches_country_rules(text: str, canon_country: str) -> bool:
    """Return True if `text` (location string) contains the target country name, city, or trailing ISO code."""
    if not text:
        return False
    low = text.strip().lower()
    folded = _fold_ascii(low)
    rules = COUNTRY_KEYWORDS.get(canon_country)
    if not rules:
        return bool(re.search(rf"\b{re.escape(canon_country)}\b", low) or re.search(rf"\b{re.escape(_fold_ascii(canon_country))}\b", folded))

    for name in rules["names"]:
        if re.search(rf"\b{re.escape(name)}\b", low) or re.search(rf"\b{re.escape(_fold_ascii(name))}\b", folded):
            return True
    for city in rules["cities"]:
        if re.search(rf"\b{re.escape(city)}\b", low) or re.search(rf"\b{re.escape(_fold_ascii(city))}\b", folded):
            return True
    # Match uppercase/standalone ISO codes like "Cluj-Napoca, CJ, RO" or "RO"
    for iso in rules["iso"]:
        if low == iso or re.search(rf"(?:,\s*|\b){re.escape(iso)}$", low):
            return True
    return False


def _text_contradicts_country(text: str, canon_targets: List[str]) -> bool:
    """Return True if `text` explicitly names a different country or major foreign city (and none of `canon_targets`)."""
    if not text:
        return False
    low = text.strip().lower()
    folded = _fold_ascii(low)
    target_set = set(canon_targets)
    allowed_terms: Set[str] = set()
    for tc in target_set:
        tr = COUNTRY_KEYWORDS.get(tc)
        if tr:
            allowed_terms.update(tr.get("names", ()))
            allowed_terms.update(tr.get("cities", ()))

    for other_canon, rules in COUNTRY_KEYWORDS.items():
        if other_canon in target_set:
            continue
        for term in (*rules.get("names", ()), *rules.get("cities", ())):
            if len(term) >= 4 and term not in allowed_terms and (
                re.search(rf"\b{re.escape(term)}\b", low)
                or re.search(rf"\b{re.escape(_fold_ascii(term))}\b", folded)
            ):
                return True
    return False


def job_matches_selected_countries(job: dict, countries: Iterable[str], is_remote_requested: bool = False) -> bool:
    """
    Strictly verify that a job belongs to one of the user's selected countries.
    When the user selects a specific country (e.g. 'Romania'), generic 'Worldwide' or 'Remote'
    postings (or postings in other countries like 'Hybrid Porto' / 'Mexico City') are rejected
    unless their location explicitly matches the selected country/cities.
    """
    clean_countries = [c.strip() for c in (countries or []) if c and c.strip()]
    if not clean_countries:
        return True

    # If user selected Worldwide / Global / Remote as the location, allow global results
    low_set = {c.lower() for c in clean_countries}
    if low_set & {"worldwide", "global", "all", "remote", "anywhere"}:
        return True
    if any(c.startswith("remote ") for c in low_set):
        return True

    loc = (job.get("location") or "").strip()
    title = (job.get("title") or "").strip()
    url = (job.get("url") or job.get("job_url") or "").strip()
    loc_low = loc.lower()

    # Reject pure 'Worldwide', 'Global', 'Anywhere', or generic 'Remote' without a country match
    # when the user asked for a specific country!
    canon_targets = [_canonical_country(c) for c in clean_countries]

    # If either location or title explicitly names a foreign country/city (and does not name the target country), reject
    if _text_contradicts_country(loc, canon_targets) and not any(_text_matches_country_rules(loc, c) for c in canon_targets):
        return False
    if _text_contradicts_country(title, canon_targets) and not any(_text_matches_country_rules(title, c) for c in canon_targets):
        return False

    # First check if `loc` explicitly matches any of the requested countries
    for canon in canon_targets:
        if _text_matches_country_rules(loc, canon):
            return True

    # If `loc` is empty or generic, check if the title explicitly mentions a target city/country
    if loc_low in ("", "remote", "hybrid", "onsite") or loc_low in low_set:
        for canon in canon_targets:
            if _text_matches_country_rules(title, canon):
                return True

    # Check country-specific board domains (e.g. ro.indeed.com, de.indeed.com) when location wasn't contradicted
    for canon in canon_targets:
        rules = COUNTRY_KEYWORDS.get(canon)
        if rules:
            for iso in rules["iso"]:
                if len(iso) == 2 and f"://{iso}.indeed." in url.lower():
                    return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Tokenisation
# ─────────────────────────────────────────────────────────────────────────────

def _stem(tok: str) -> str:
    """Very light stemmer: only plural forms, so 'developments' ≠ 'developer'."""
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith(("ers", "ors", "ists", "ysts", "ants", "ents", "ects")):
        return tok[:-1]
    return tok


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    t = text.lower()
    t = t.replace("full-stack", "fullstack").replace("full stack", "fullstack")
    t = t.replace("front-end", "frontend").replace("front end", "frontend")
    t = t.replace("back-end", "backend").replace("back end", "backend")
    t = t.replace("node.js", "nodejs").replace("react.js", "reactjs").replace("vue.js", "vuejs")
    t = t.replace("c++", "cpp").replace("c#", "csharp").replace(".net", "dotnet")
    t = (
        t.replace("softwareentwickler", "software entwickler")
        .replace("softwareingenieur", "software ingenieur")
        .replace("webentwickler", "web entwickler")
        .replace("systemutvecklare", "software utvecklare")
    )
    raw = re.findall(r"[a-zà-ÿ0-9+#]+", t)
    return [_stem(w) for w in raw if w not in STOPWORDS]


def _equiv(tok: str) -> str:
    """Map a token to its equivalence-class key."""
    idx = _EQUIV_INDEX.get(tok)
    return f"#{idx}" if idx is not None else tok


def core_tokens(query: str) -> List[str]:
    toks = [t for t in tokenize(query) if t not in SOFT_WORDS]
    return toks or tokenize(query)


# ─────────────────────────────────────────────────────────────────────────────
# Query expansion
# ─────────────────────────────────────────────────────────────────────────────

SINGLE_TECH_TO_ROLE: Dict[str, List[str]] = {
    "flutter": ["Flutter Developer", "Flutter Mobile Developer"],
    "dart": ["Flutter Developer", "Dart Developer"],
    "react": ["React Developer", "Frontend React Engineer"],
    "reactjs": ["React Developer", "Frontend Engineer"],
    "angular": ["Angular Developer", "Frontend Engineer"],
    "vue": ["Vue Developer", "Frontend Engineer"],
    "vuejs": ["Vue Developer", "Frontend Engineer"],
    "node": ["Node.js Developer", "Backend Engineer"],
    "nodejs": ["Node.js Developer", "Backend Engineer"],
    "python": ["Python Developer", "Python Software Engineer"],
    "django": ["Python Django Developer", "Backend Python Engineer"],
    "fastapi": ["Python Backend Developer", "Python Software Engineer"],
    "java": ["Java Developer", "Java Software Engineer"],
    "kotlin": ["Kotlin Android Developer", "Android Engineer"],
    "swift": ["iOS Swift Developer", "iOS Engineer"],
    "ios": ["iOS Developer", "iOS Mobile Engineer"],
    "android": ["Android Developer", "Android Mobile Engineer"],
    "golang": ["Golang Developer", "Go Software Engineer"],
    "rust": ["Rust Developer", "Rust Software Engineer"],
    "dotnet": [".NET Developer", "C# .NET Engineer"],
    "c#": ["C# .NET Developer", ".NET Software Engineer"],
    "php": ["PHP Developer", "Backend PHP Engineer"],
    "laravel": ["Laravel PHP Developer", "PHP Developer"],
    "ruby": ["Ruby on Rails Developer", "Ruby Engineer"],
    "devops": ["DevOps Engineer", "Site Reliability Engineer"],
    "aws": ["AWS Cloud Engineer", "Cloud DevOps Engineer"],
}


def expand_queries(title: str, country: str = "", max_variants: int = 3) -> List[str]:
    """Return the original query followed by equivalent phrasings of the same role (including native language in local markets)."""
    base = (title or "").strip()
    if not base:
        return []
    low = re.sub(r"\s+", " ", base.lower())
    c_low = (country or "").strip().lower()

    # If the user entered a single technology name (e.g. "flutter", "react", "python"),
    # lead with the explicit "<Tech> Developer" query so boards don't match company names like "Flutter Entertainment"
    if low in SINGLE_TECH_TO_ROLE:
        variants: List[str] = list(SINGLE_TECH_TO_ROLE[low])
        nice_tech = _nice_case(low)
        local_role = ""
        if c_low in FRENCH_MARKETS:
            local_role = f"Développeur {nice_tech}"
        elif c_low in SPANISH_MARKETS:
            local_role = f"Desarrollador {nice_tech}"
        elif c_low in PORTUGUESE_MARKETS:
            local_role = f"Desenvolvedor {nice_tech}"
        elif c_low in GERMAN_MARKETS:
            local_role = f"{nice_tech} Entwickler"
        elif c_low in ROMANIAN_MARKETS:
            local_role = f"Programator {nice_tech}"
        elif c_low in ITALIAN_MARKETS:
            local_role = f"Sviluppatore {nice_tech}"
        elif c_low in POLISH_MARKETS:
            local_role = f"Programista {nice_tech}"
        if local_role and local_role.lower() not in {x.lower() for x in variants}:
            variants.insert(1, local_role)
        if base.lower() not in {x.lower() for x in variants}:
            variants.append(base)
        return variants[:max_variants]

    variants = [base]

    def _add(v: str):
        if v and v.lower() not in {x.lower() for x in variants}:
            variants.append(v)

    # Find the synonym group whose canonical/members best match the query.
    stripped = " ".join(core_tokens(low))
    matched_group: Optional[List[str]] = None
    for grp in ROLE_SYNONYMS:
        if low in grp or stripped in [" ".join(core_tokens(g)) for g in grp]:
            matched_group = grp
            break
    if matched_group is None:
        for grp in ROLE_SYNONYMS:
            if grp[0] in low:
                matched_group = grp
                break

    seniority = [w for w in low.split() if w in {"senior", "junior", "lead", "sr", "jr", "principal"}]
    prefix = (seniority[0] + " ") if seniority else ""
    key = matched_group[0] if matched_group else stripped

    # Native phrasing first in non-English markets (local boards index localized titles).
    if c_low in FRENCH_MARKETS:
        for loc_t in FRENCH_TITLES.get(key, [])[:1]:
            _add(loc_t)
    elif c_low in SPANISH_MARKETS:
        for loc_t in SPANISH_TITLES.get(key, [])[:1]:
            _add(loc_t)
    elif c_low in PORTUGUESE_MARKETS:
        for loc_t in PORTUGUESE_TITLES.get(key, [])[:1]:
            _add(loc_t)
    elif c_low in GERMAN_MARKETS:
        for loc_t in GERMAN_TITLES.get(key, [])[:1]:
            _add(loc_t)

    if matched_group:
        for syn in matched_group:
            if syn != low and syn != stripped:
                _add(_nice_case(prefix + syn))
    else:
        # Generic developer ↔ engineer swap keeps the user's technology keyword.
        if "developer" in low:
            _add(_nice_case(low.replace("developer", "engineer")))
        elif "engineer" in low:
            _add(_nice_case(low.replace("engineer", "developer")))

    return variants[:max_variants]


_ACRONYMS = {"bi": "BI", "qa": "QA", "ui": "UI", "ux": "UX", "ai": "AI", "ml": "ML", "it": "IT",
             "soc": "SOC", "etl": "ETL", "aws": "AWS", "ios": "iOS", "llm": "LLM", "sre": "SRE"}


def _nice_case(s: str) -> str:
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in s.split())


# ─────────────────────────────────────────────────────────────────────────────
# Relevance
# ─────────────────────────────────────────────────────────────────────────────

_COMPANY_BRAND_SUFFIX_RE = re.compile(
    r"(?:\s*[-–—|]\s*(?:flutter\s*(?:functions|studios|international|uk\s*&?\s*i|uki|entertainment|group|global|\.{2,}|…)|fanduel|sportsbet|betfair|pokerstars)[^,]*)",
    re.IGNORECASE,
)

_FLUTTER_CORP_NOISE_RE = re.compile(
    r"\bflutter\s+(?:entertainment|functions|studios|international|uk\s*&?\s*i|uki|group|global|plc|careers|division|brands?)\b",
    re.IGNORECASE,
)

# Specific technology / language / platform tokens that must anchor relevance when searched.
# Prevents "Java Developer" from scoring 65/100 on a "Python Developer" search just because "Developer" matched.
TECH_ANCHOR_TOKENS: Set[str] = {
    "flutter", "dart", "react", "reactjs", "angular", "angularjs", "vue", "vuejs",
    "node", "nodejs", "python", "django", "flask", "fastapi", "java", "spring",
    "kotlin", "swift", "ios", "android", "golang", "rust", "dotnet", "csharp", "cpp",
    "php", "laravel", "symfony", "ruby", "rails", "scala", "elixir", "devops", "sre",
    "kubernetes", "terraform", "aws", "azure", "gcp", "salesforce", "sap", "abap",
    "servicenow", "wordpress", "shopify", "magento", "unity", "unreal", "blockchain",
    "solidity", "qa", "cybersecurity",
}


def relevance_score(query: str, title: str, description: str = "", company: str = "") -> int:
    """0-100 score of how well a job matches the searched role.

    - Exact phrase in title                   → 100
    - All core words (synonym-aware) in title → 90
    - Partial title match                     → 40-80
    - Description-only match                  → ≤ 38
    """
    q_core = core_tokens(query)
    if not q_core:
        return 50
    # Strip known company-division suffixes (e.g. "- Flutter Functions" at Flutter Entertainment)
    # so a company name in the title or description is never mistaken for the technology/role.
    clean_title = _COMPANY_BRAND_SUFFIX_RE.sub("", title or "").strip()
    clean_title = _FLUTTER_CORP_NOISE_RE.sub("", clean_title).strip()
    clean_desc = _FLUTTER_CORP_NOISE_RE.sub("", (description or "")[:4000])

    # If the user is searching for Flutter (the mobile/UI framework), reject non-engineering roles
    # (Legal Counsel, SOX Analyst, Cyber Security, HR, Finance, Data Engineer) at Flutter Entertainment
    q_low = (query or "").lower().strip()
    if "flutter" in q_low:
        t_Check = clean_title.lower()
        if not re.search(r"\b(flutter|dart)\b", t_Check):
            comp_low = (company or "").lower()
            is_flutter_corp = bool(re.search(r"\b(flutter|betfair|fanduel|pokerstars|sportsbet|sisal)\b", comp_low))
            d_low = clean_desc.lower()
            if is_flutter_corp:
                if not re.search(r"\b(dart|bloc|riverpod|widget|flutter\s+sdk|flutter\s+app)\b", d_low):
                    return 0
                return 35
            is_sw_dev_title = bool(
                re.search(r"\b(developer|engineer|développeur|developpeur|ingénieur|ingenieur|desarrollador|desenvolvedor|programador|entwickler|programator|programista|mobile|fullstack|full-stack|frontend|front-end)\b", t_Check)
                and not re.search(r"\b(data|qa|rpa|devops|security|cyber|cloud|network|system|support|test|analyst|sales|marketing|finance|legal|hr|compliance|dynamics)\b", t_Check)
            )
            if is_sw_dev_title and re.search(r"\b(flutter|dart)\b", d_low):
                return 38
            # Allow generic "Mobile Developer / Développeur Mobile" postings (that don't specify native-only iOS/Android) as backfill
            if (
                re.search(r"\b(mobile|mobiles|móvil|movil)\b", t_Check)
                and re.search(r"\b(developer|engineer|développeur|developpeur|ingénieur|ingenieur|desarrollador|desenvolvedor|programador|entwickler|programator)\b", t_Check)
                and not re.search(r"\b(ios|android|swift|kotlin|react\s+native|objective-c)\b", t_Check)
            ):
                return 28
            return 0

    t_low = clean_title.lower()
    if q_low and re.search(r"\b" + re.escape(q_low) + r"\b", t_low):
        return 100

    t_tokens = tokenize(clean_title)
    t_classes = {_equiv(t) for t in t_tokens}
    q_classes = [_equiv(t) for t in q_core]

    # Check if the query specifies a concrete technology anchor (e.g. "python", "react", "java", "golang")
    q_anchors = {_equiv(t) for t in q_core if t in TECH_ANCHOR_TOKENS}
    if q_anchors:
        anchor_in_title = bool(q_anchors & t_classes)
        if not anchor_in_title:
            # If the title names a DIFFERENT tech anchor (e.g. "Java Developer" for a "Python Developer" query)
            # and doesn't mention our anchor in the title, only allow if description mentions our anchor
            d_classes = {_equiv(t) for t in tokenize(clean_desc)} if clean_desc else set()
            anchor_in_desc = bool(q_anchors & d_classes)
            if not anchor_in_desc:
                return 0
            # Anchor is in description; check if title is a general software/developer/engineer role
            role_in_title = _equiv("developer") in t_classes
            return 38 if role_in_title else 25

    hits = sum(1 for c in q_classes if c in t_classes)
    frac = hits / len(q_classes)

    if frac >= 1.0:
        return 90
    if hits:
        # The "role noun" (last word, e.g. developer / analyst) matters most.
        role_hit = q_classes[-1] in t_classes
        return int(40 + 30 * frac + (10 if role_hit else 0))

    if clean_desc:
        d_classes = {_equiv(t) for t in tokenize(clean_desc)}
        d_hits = sum(1 for c in q_classes if c in d_classes)
        phrase_in_desc = q_low and q_low in clean_desc.lower()
        if phrase_in_desc:
            return 35
        return int(25 * d_hits / len(q_classes))
    return 0


def best_relevance(queries: Iterable[str], title: str, description: str = "", company: str = "") -> int:
    return max((relevance_score(q, title, description, company) for q in queries if q), default=0)


def is_spam(title: str, description: str = "", company: str = "") -> bool:
    blob = f"{title} {company} {(description or '')[:1500]}"
    return bool(SPAM_PATTERNS.search(blob))


# ─────────────────────────────────────────────────────────────────────────────
# Dedup / merge (ported & expanded from ai-job-search tools/job_key.py)
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

_CHAR_MAP = str.maketrans({
    "ø": "o", "æ": "ae", "å": "aa",
    "ö": "o", "ä": "ae", "ü": "u", "ß": "ss", "œ": "oe",
})

_CORP_SUFFIX_RE = re.compile(
    r"\b("
    r"a/s|aps|i/s|p/s|k/s|"
    r"ab|oy|oyj|as|asa|ehf|"
    r"gmbh|ag|se|kg|ug|mbh|"
    r"bv|nv|sarl|sas|sa|srl|spa|sl|"
    r"plc|ltd|limited|llp|inc|incorporated|corp|corporation|llc|co|"
    r"company|group|holding|holdings|technologies|solutions|labs"
    r")\.?$"
)


def _fold_ascii(text: str) -> str:
    """Fold Nordic/European characters and strip Unicode combining marks."""
    s = (text or "").strip().lower().translate(_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def normalize_company_key(company: str) -> str:
    """Canonical company key resilient to legal suffixes, parentheticals, and diacritics."""
    s = _fold_ascii(company)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9/]+", " ", s).strip()
    prev = None
    while s != prev:
        prev = s
        s = _CORP_SUFFIX_RE.sub("", s).strip()
    return re.sub(r"[^a-z0-9]", "", s)


def normalize_title_key(title: str) -> str:
    """Canonical title key stripping gender markers (m/f/d, h/f) and trailing location tails."""
    s = _fold_ascii(title)
    s = re.sub(r"\([^)]*\)", " ", s)
    for sep in (" - ", " – ", " — ", ", "):
        if sep in s:
            head, tail = s.rsplit(sep, 1)
            # Strip trailing location/mode/gender tails while keeping real role qualifiers
            if len(head) >= 6 and (
                len(tail) <= 22 or any(w in tail for w in ("remote", "hybrid", "onsite", "h/f", "m/f", "f/h", "all genders"))
            ):
                s = head
                break
    return re.sub(r"[^a-z0-9+#]", "", s)


def _norm(s: str) -> str:
    return normalize_company_key(s)


def canonical_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    m = re.search(r"currentjobid=(\d+)", u) or re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", u)
    if m:
        return f"linkedin:{m.group(1)}"
    m = re.search(r"[?&]jk=([a-z0-9]+)", u)
    if m:
        return f"indeed:{m.group(1)}"
    m = re.search(r"jobbank\.gc\.ca/jobsearch/jobposting/(\d+)", u)
    if m:
        return f"jobbank:{m.group(1)}"
    m = re.search(r"[?&]gh_jid=(\d+)", u) or re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", u)
    if m:
        return f"greenhouse:{m.groups()[-1]}"
    m = re.search(r"jobs\.lever\.co/([^/?#]+)/([0-9a-f-]{16,})", u)
    if m:
        return f"lever:{m.group(1)}/{m.group(2)}"
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{16,})", u)
    if m:
        return f"ashby:{m.group(1)}/{m.group(2)}"
    m = re.search(r"tanitjobs\.com/job/(\d+)", u)
    if m:
        return f"tanitjobs:{m.group(1)}"
    m = re.search(r"keejob\.com/offres-emploi/(\d+)", u)
    if m:
        return f"keejob:{m.group(1)}"
    m = re.search(r"ejobs\.ro/user/locuri-de-munca/[^/?#]+/(\d+)", u)
    if m:
        return f"ejobs:{m.group(1)}"
    m = re.search(r"hipo\.ro/locuri-de-munca/locuri_de_munca/(\d+)", u)
    if m:
        return f"hipo:{m.group(1)}"
    m = re.search(r"hellowork\.com/fr-fr/emplois/(\d+)\.html", u)
    if m:
        return f"hellowork:{m.group(1)}"
    m = re.search(r"reed\.co\.uk/jobs/[^/?#]+/(\d+)", u)
    if m:
        return f"reed:{m.group(1)}"
    m = re.search(r"karriere\.at/jobs/(\d+)", u)
    if m:
        return f"karriere_at:{m.group(1)}"
    m = re.search(r"itjobs\.pt/oferta/(\d+)", u)
    if m:
        return f"itjobs_pt:{m.group(1)}"
    m = re.search(r"rekrute\.com/offre-emploi-[^/?#]*-(\d+)\.html", u)
    if m:
        return f"rekrute:{m.group(1)}"
    m = re.search(r"(?:seek\.com\.au|seek\.co\.nz|jobstreet\.com(?:\.[a-z]{2})?)/(?:id/)?job/(\d+)", u)
    if m:
        return f"seek:{m.group(1)}"
    m = re.search(r"mycareersfuture\.gov\.sg/job/[^/?#]*-([0-9a-f]{32})", u)
    if m:
        return f"mycareersfuture:{m.group(1)}"
    m = re.search(r"wanted\.co\.kr/wd/(\d+)", u)
    if m:
        return f"wanted_kr:{m.group(1)}"
    m = re.search(r"djinni\.co/jobs/(\d+)-", u)
    if m:
        return f"djinni:{m.group(1)}"
    m = re.search(r"finn\.no/job/[^/?#]+[?&]finnkode=(\d+)", u)
    if m:
        return f"finn:{m.group(1)}"
    u = re.sub(r"^https?://(www\.)?", "", u.split("#")[0])
    u = u.split("?")[0].rstrip("/")
    u = re.sub(r";jsessionid=[^/?]*", "", u)
    return u


def dedup_keys(job: dict) -> List[str]:
    keys = []
    cu = canonical_url(job.get("url") or "")
    if cu:
        keys.append("u:" + cu)
    du = canonical_url(job.get("job_url_direct") or "")
    if du and du != cu:
        keys.append("u:" + du)
    nt = normalize_title_key(job.get("title", ""))
    nc = normalize_company_key(job.get("company", ""))
    if nt and nc and nc not in {normalize_company_key(b) for b in BAD_COMPANY}:
        # Same normalized title at the same company in the same city = same opening across portals.
        city = _fold_ascii((job.get("location") or "").split(",")[0])
        city = re.sub(r"[^a-z0-9]", "", city)
        keys.append(f"tc:{nt}|{nc}|{city}")
        # Also match remote/unspecified city against concrete city when company+title are specific
        if len(nt) >= 12 and len(nc) >= 4:
            keys.append(f"tcr:{nt}|{nc}")
    return keys


def _email_list(job: dict) -> List[str]:
    out = []
    for e in job.get("emails") or []:
        em = (e.get("email") if isinstance(e, dict) else str(e)).strip().lower()
        if em and "@" in em:
            out.append(em)
    return out


def merge_jobs(primary: dict, other: dict) -> dict:
    """Merge `other` into `primary`, keeping the richest data from both."""
    if len(other.get("description") or "") > len(primary.get("description") or ""):
        primary["description"] = other["description"]
    p_comp = (primary.get("company") or "").strip()
    o_comp = (other.get("company") or "").strip()
    if o_comp and not o_comp.startswith(("Entreprise (", "Employer via ")) and (
        not p_comp or p_comp.startswith(("Entreprise (", "Employer via "))
    ):
        primary["company"] = o_comp
    have = set(_email_list(primary))
    for e in other.get("emails") or []:
        em = (e.get("email") if isinstance(e, dict) else str(e)).strip().lower()
        if em and em not in have:
            primary.setdefault("emails", []).append(e if isinstance(e, dict) else {"email": em, "source": "found"})
            have.add(em)
    for fld in ("salary", "job_url_direct", "company_url_direct", "company_url", "location"):
        if not primary.get(fld) and other.get(fld):
            primary[fld] = other[fld]
    pa, oa = primary.get("age_hours"), other.get("age_hours")
    if oa is not None and (pa is None or oa < pa):
        for fld in ("age_hours", "age_str", "date_posted", "is_under_24h"):
            primary[fld] = other.get(fld)
    for flag in ("easy_apply", "is_direct_apply", "is_international_eligible"):
        primary[flag] = bool(primary.get(flag) or other.get(flag))
    sites = set(primary.get("also_on") or [primary.get("site")])
    sites.add(other.get("site"))
    primary["also_on"] = sorted(s for s in sites if s)
    return primary


def dedup_and_merge(jobs: List[dict]) -> List[dict]:
    key_to_idx: Dict[str, int] = {}
    out: List[dict] = []
    for job in jobs:
        keys = dedup_keys(job)
        idx = next((key_to_idx[k] for k in keys if k in key_to_idx), None)
        if idx is None:
            out.append(job)
            idx = len(out) - 1
        else:
            out[idx] = merge_jobs(out[idx], job)
        for k in keys:
            key_to_idx.setdefault(k, idx)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Quality score
# ─────────────────────────────────────────────────────────────────────────────

def quality_score(job: dict) -> int:
    """0-100 composite: relevance 50 · freshness 20 · richness 10 · email 10 · salary 5 · company 5."""
    rel = job.get("relevance") or 0
    score = rel * 0.5

    age = job.get("age_hours")
    if age is None:
        score += 6
    elif age <= 24:
        score += 20
    elif age <= 72:
        score += 16
    elif age <= 168:
        score += 12
    elif age <= 720:
        score += 6
    else:
        score += 2

    dlen = len(job.get("description") or "")
    score += 10 if dlen >= 800 else (6 if dlen >= 250 else (2 if dlen >= 80 else 0))
    score += 10 if _email_list(job) else 0
    score += 5 if job.get("salary") else 0
    score += 0 if _norm(job.get("company", "")) in {_norm(b) for b in BAD_COMPANY} else 5
    if len(job.get("also_on") or []) > 1:
        score += 3  # confirmed on multiple boards = real, active opening
    return max(0, min(100, int(round(score))))
