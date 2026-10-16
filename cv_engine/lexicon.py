"""
Shared vocabulary for the CV engine: section headings (EN/FR), tech canonical names and
categories, role/degree/school keywords, language names and common CV typos.

Everything here is data — no logic — so it can be extended without touching the parser.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def norm_key(s: str) -> str:
    """Upper-case, accent-free, letters/digits/& only — used for fuzzy heading matching."""
    s = strip_accents(s or "").upper().replace("’", "'")
    s = re.sub(r"[^A-Z0-9&' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ─── Section headings ─────────────────────────────────────────────────────────

SECTION_HEADINGS: Dict[str, List[str]] = {
    "summary": [
        "SUMMARY", "PROFESSIONAL SUMMARY", "EXECUTIVE SUMMARY", "PROFILE", "PROFESSIONAL PROFILE",
        "ABOUT", "ABOUT ME", "CAREER SUMMARY", "OBJECTIVE", "CAREER OBJECTIVE", "PERSONAL STATEMENT",
        "PROFIL", "PROFIL PROFESSIONNEL", "RESUME", "A PROPOS", "A PROPOS DE MOI", "OBJECTIF",
        "PRESENTATION", "QUI SUIS JE",
    ],
    "experience": [
        "EXPERIENCE", "EXPERIENCES", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "EMPLOYMENT",
        "EMPLOYMENT HISTORY", "WORK HISTORY", "CAREER HISTORY", "RELEVANT EXPERIENCE", "INTERNSHIPS",
        "EXPERIENCE PROFESSIONNELLE", "EXPERIENCES PROFESSIONNELLES", "PARCOURS PROFESSIONNEL",
        "STAGES", "STAGES ET EXPERIENCES", "EXPERIENCE & PROJETS PERSONNELS", "EXPERIENCE & PROJECTS",
        "EXPERIENCE AND PROJECTS", "EXPERIENCES & PROJETS",
    ],
    "projects": [
        "PROJECTS", "PERSONAL PROJECTS", "ACADEMIC PROJECTS", "SELECTED PROJECTS", "KEY PROJECTS",
        "FEATURED PROJECTS", "SIDE PROJECTS", "PORTFOLIO", "PROJETS", "PROJETS PERSONNELS",
        "PROJETS REALISES", "PROJETS ACADEMIQUES", "PROJETS UNIVERSITAIRES", "REALISATIONS",
        "PROJETS ACADEMIQUES ET PERSONNELS",
    ],
    "education": [
        "EDUCATION", "ACADEMIC BACKGROUND", "EDUCATION & QUALIFICATIONS", "ACADEMIC QUALIFICATIONS",
        "QUALIFICATIONS", "FORMATION", "FORMATIONS", "EDUCATION ET FORMATION", "ETUDES", "DIPLOMES",
        "CURSUS", "CURSUS ACADEMIQUE", "PARCOURS ACADEMIQUE", "FORMATION ACADEMIQUE", "SCOLARITE",
    ],
    "skills": [
        "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "SKILLS & TECHNOLOGIES", "TECHNOLOGIES",
        "TECH STACK", "KEY SKILLS", "AREAS OF EXPERTISE", "PROGRAMMING SKILLS", "HARD SKILLS",
        "PROGRAMMING LANGUAGE SKILLS", "PROGRAMMING LANGUE SKILLS", "TECHNOLOGY SKILLS", "COMPETENCES",
        "COMPETENCES TECHNIQUES", "CONNAISSANCES", "CONNAISSANCES TECHNIQUES", "EXPERTISE TECHNIQUE",
        "COMPETENCES INFORMATIQUES", "OUTILS", "SAVOIR FAIRE", "TOOLS", "TECHNICAL PROFICIENCIES",
    ],
    "soft_skills": [
        "SOFT SKILLS", "SOFTSKILLS", "QUALITES", "QUALITES PERSONNELLES", "SAVOIR ETRE",
        "PERSONAL SKILLS", "INTERPERSONAL SKILLS", "COMPETENCES PERSONNELLES", "ATOUTS",
    ],
    "languages": [
        "LANGUAGES", "LANGUAGE", "LANGUAGE PROFICIENCY", "SPOKEN LANGUAGES", "LANGUES",
        "COMPETENCES LINGUISTIQUES", "LANGUES PARLEES",
    ],
    "certifications": [
        "CERTIFICATIONS", "CERTIFICATION", "CERTIFICATES", "LICENSES & CERTIFICATIONS",
        "TRAINING & CERTIFICATIONS", "CERTIFICATIONS & AWARDS", "COURSES", "TRAINING", "CERTIFICATS",
        "FORMATIONS COMPLEMENTAIRES",
    ],
    "awards": ["AWARDS", "HONORS", "HONOURS", "ACHIEVEMENTS", "PRIX", "DISTINCTIONS", "PRIX ET DISTINCTIONS"],
    "activities": [
        "ACTIVITIES", "EXTRACURRICULAR ACTIVITIES", "VOLUNTEERING", "VOLUNTEER EXPERIENCE", "LEADERSHIP",
        "CLUBS", "ASSOCIATIONS", "VIE ASSOCIATIVE", "ACTIVITES", "ACTIVITES PARASCOLAIRES",
        "ACTIVITES EXTRA PROFESSIONNELLES", "BENEVOLAT", "ENGAGEMENTS", "VIE ASSOCIATIVE ET CLUBS",
    ],
    "interests": [
        "INTERESTS", "HOBBIES", "HOBBIES & INTERESTS", "CENTRES D'INTERET", "CENTRES D INTERET",
        "CENTRE D'INTERET", "LOISIRS", "PASSIONS", "CENTRES D'INTERETS",
    ],
    "contact": ["CONTACT", "CONTACTS", "CONTACT INFO", "CONTACT INFORMATION", "COORDONNEES", "INFORMATIONS PERSONNELLES", "PERSONAL INFORMATION", "PERSONAL DETAILS", "DETAILS"],
    "references": ["REFERENCES", "REFERENCE", "RECOMMANDATIONS"],
    "publications": ["PUBLICATIONS", "RESEARCH", "RECHERCHE", "PUBLICATIONS SCIENTIFIQUES"],
}

HEADING_INDEX: Dict[str, str] = {norm_key(h): sec for sec, hs in SECTION_HEADINGS.items() for h in hs}


# ─── Tech lexicon: canonical display name → (category, aliases) ───────────────

LANG = "Languages"
FRONT = "Frontend"
BACK = "Backend"
MOBILE = "Mobile"
DB = "Databases"
CLOUD = "Cloud & DevOps"
DATA = "Data & AI"
TEST = "Testing & QA"
TOOLS = "Tools"
METHOD = "Methodologies"
DESIGN = "Design"

CATEGORY_ORDER = [LANG, FRONT, BACK, MOBILE, DB, DATA, CLOUD, TEST, TOOLS, DESIGN, METHOD]

CATEGORY_FR = {
    LANG: "Langages", FRONT: "Frontend", BACK: "Backend", MOBILE: "Mobile", DB: "Bases de données",
    DATA: "Data & IA", CLOUD: "Cloud & DevOps", TEST: "Tests & Qualité", TOOLS: "Outils",
    DESIGN: "Design", METHOD: "Méthodologies", "Other": "Autres",
}

TECH: Dict[str, Tuple[str, List[str]]] = {
    # Languages
    "Python": (LANG, ["python3", "python 3", "py"]),
    "Java": (LANG, []),
    "JavaScript": (LANG, ["js", "javascript es6", "es6", "ecmascript"]),
    "TypeScript": (LANG, ["ts"]),
    "C": (LANG, []),
    "C++": (LANG, ["cpp", "c/c++"]),
    "C#": (LANG, ["csharp", "c sharp"]),
    "Dart": (LANG, []),
    "Kotlin": (LANG, []),
    "Swift": (LANG, []),
    "Go": (LANG, ["golang"]),
    "Rust": (LANG, []),
    "PHP": (LANG, ["php8", "php 8"]),
    "Ruby": (LANG, []),
    "Scala": (LANG, []),
    "R": (LANG, []),
    "MATLAB": (LANG, ["matlab"]),
    "SQL": (LANG, ["pl/sql", "plsql", "t-sql"]),
    "Bash": (LANG, ["shell", "shell scripting", "bash scripting"]),
    "Objective-C": (LANG, ["objective c"]),
    "VBA": (LANG, []),
    "Assembly": (LANG, ["assembleur"]),
    # Frontend
    "HTML": (FRONT, ["html5", "html 5"]),
    "CSS": (FRONT, ["css3", "css 3"]),
    "SCSS": (FRONT, ["sass"]),
    "React": (FRONT, ["reactjs", "react.js", "react js"]),
    "Next.js": (FRONT, ["nextjs", "next js"]),
    "Angular": (FRONT, ["angularjs", "angular.js", "angular js"]),
    "Angular Material": (FRONT, ["angular-material"]),
    "Vue.js": (FRONT, ["vue", "vuejs", "vue js"]),
    "Nuxt.js": (FRONT, ["nuxt", "nuxtjs"]),
    "Svelte": (FRONT, []),
    "Redux": (FRONT, []),
    "jQuery": (FRONT, ["jquery"]),
    "Bootstrap": (FRONT, []),
    "Tailwind CSS": (FRONT, ["tailwind", "tailwindcss"]),
    "Material UI": (FRONT, ["mui", "material-ui"]),
    "Styled Components": (FRONT, ["styled-components"]),
    "Vite": (FRONT, []),
    "Webpack": (FRONT, []),
    "Three.js": (FRONT, ["threejs"]),
    "XML": (FRONT, []),
    "JSON": (FRONT, []),
    # Backend
    "Node.js": (BACK, ["nodejs", "node js", "node"]),
    "Express.js": (BACK, ["express", "expressjs", "express js"]),
    "NestJS": (BACK, ["nest.js", "nest js", "nestjs"]),
    "Django": (BACK, []),
    "Flask": (BACK, []),
    "FastAPI": (BACK, []),
    "Spring Boot": (BACK, ["springboot", "spring-boot"]),
    "Spring": (BACK, []),
    "J2EE": (BACK, ["jee", "java ee", "jakarta ee"]),
    "Hibernate": (BACK, []),
    ".NET": (BACK, ["dotnet", "dot net", ".net framework"]),
    ".NET Core": (BACK, ["dotnet core", "asp.net core", ".net core"]),
    "ASP.NET": (BACK, ["asp.net mvc", "asp .net", "asp net"]),
    "Laravel": (BACK, []),
    "Symfony": (BACK, ["symphony"]),
    "Ruby on Rails": (BACK, ["rails", "ror"]),
    "GraphQL": (BACK, []),
    "REST APIs": (BACK, ["rest", "restful", "rest api", "restful api", "restful apis", "api rest", "rest apis", "restapi", "rest/json apis"]),
    "gRPC": (BACK, []),
    "WebSockets": (BACK, ["websocket", "socket.io"]),
    "Microservices": (BACK, ["micro-services", "microservice"]),
    "JWT": (BACK, []),
    "OAuth": (BACK, ["oauth2", "oauth 2.0"]),
    "Scrapy": (BACK, []),
    "Selenium": (TEST, []),
    "Beautiful Soup": (BACK, ["beautifulsoup", "beautiful soup", "bs4"]),
    "SQLAlchemy": (BACK, []),
    "MERN": (BACK, ["mern stack"]),
    "MEAN": (BACK, ["mean stack"]),
    "Strapi": (BACK, []),
    "WordPress": (BACK, ["wordpress"]),
    # Mobile
    "Flutter": (MOBILE, []),
    "React Native": (MOBILE, ["react-native"]),
    "Android": (MOBILE, ["android sdk"]),
    "iOS": (MOBILE, ["ios"]),
    "SwiftUI": (MOBILE, []),
    "Jetpack Compose": (MOBILE, []),
    "Ionic": (MOBILE, []),
    "Xamarin": (MOBILE, []),
    "BLoC": (MOBILE, ["bloc"]),
    "Riverpod": (MOBILE, []),
    "Provider": (MOBILE, []),
    "GetX": (MOBILE, []),
    "Hive": (MOBILE, []),
    "Expo": (MOBILE, []),
    "GoRouter": (MOBILE, ["go_router", "go router"]),
    "Material Design": (MOBILE, ["material", "material 3", "material3", "material ui design"]),
    "Firebase Cloud Messaging": (MOBILE, ["fcm", "push notifications"]),
    "Less": (FRONT, ["less css"]),
    "Firebase Auth": (DB, ["firebase authentication"]),
    "Cloud Functions": (CLOUD, ["firebase cloud functions"]),
    # Databases
    "MySQL": (DB, []),
    "PostgreSQL": (DB, ["postgres", "postgre", "postgresql"]),
    "MongoDB": (DB, ["mongo", "mongo db"]),
    "SQLite": (DB, []),
    "Oracle": (DB, ["oracle db", "oracle database"]),
    "SQL Server": (DB, ["mssql", "microsoft sql server", "sqlserver"]),
    "Redis": (DB, []),
    "Firebase": (DB, ["fire base", "firebase firestore"]),
    "Firestore": (DB, ["cloud firestore"]),
    "Elasticsearch": (DB, ["elastic search"]),
    "Cassandra": (DB, []),
    "DynamoDB": (DB, []),
    "Supabase": (DB, []),
    "MariaDB": (DB, []),
    "NoSQL": (DB, []),
    # Data & AI
    "Machine Learning": (DATA, ["ml", "apprentissage automatique"]),
    "Deep Learning": (DATA, []),
    "AI": (DATA, ["artificial intelligence", "intelligence artificielle", "ia"]),
    "NLP": (DATA, ["natural language processing"]),
    "Computer Vision": (DATA, ["vision par ordinateur"]),
    "TensorFlow": (DATA, []),
    "PyTorch": (DATA, []),
    "Keras": (DATA, []),
    "scikit-learn": (DATA, ["sklearn", "scikit learn"]),
    "Pandas": (DATA, []),
    "NumPy": (DATA, []),
    "OpenCV": (DATA, []),
    "Tesseract OCR": (DATA, ["tesseract"]),
    "OCR": (DATA, []),
    "LLMs": (DATA, ["llm", "large language models"]),
    "LangChain": (DATA, []),
    "Big Data": (DATA, []),
    "Apache Kafka": (DATA, ["kafka"]),
    "Apache Spark": (DATA, ["spark", "pyspark"]),
    "Hadoop": (DATA, []),
    "Power BI": (DATA, ["powerbi"]),
    "Tableau": (DATA, []),
    "Jupyter": (DATA, ["jupyter notebook"]),
    "Data Analysis": (DATA, ["analyse de données"]),
    "Statistics": (DATA, ["statistiques"]),
    # Cloud & DevOps
    "AWS": (CLOUD, ["amazon web services", "amazon aws"]),
    "AWS S3": (CLOUD, ["amazon s3", "s3", "amazon simple storage service"]),
    "Azure": (CLOUD, ["microsoft azure"]),
    "Google Cloud": (CLOUD, ["gcp", "google cloud platform"]),
    "Docker": (CLOUD, []),
    "Kubernetes": (CLOUD, ["k8s"]),
    "Jenkins": (CLOUD, []),
    "GitHub Actions": (CLOUD, []),
    "GitLab CI": (CLOUD, ["gitlab ci/cd"]),
    "CI/CD": (CLOUD, ["ci cd", "cicd"]),
    "Terraform": (CLOUD, []),
    "Ansible": (CLOUD, []),
    "Linux": (CLOUD, ["ubuntu", "linux (ubuntu)", "debian", "unix"]),
    "Windows": (CLOUD, []),
    "Nginx": (CLOUD, []),
    "Heroku": (CLOUD, []),
    "DigitalOcean": (CLOUD, ["digital ocean"]),
    "Vercel": (CLOUD, []),
    "Netlify": (CLOUD, []),
    # Testing
    "Unit Testing": (TEST, ["unit tests", "tests unitaires"]),
    "Jest": (TEST, []),
    "Cypress": (TEST, []),
    "JUnit": (TEST, []),
    "PyTest": (TEST, ["pytest"]),
    "Postman": (TEST, []),
    # Tools
    "Git": (TOOLS, []),
    "GitHub": (TOOLS, []),
    "GitLab": (TOOLS, []),
    "Bitbucket": (TOOLS, []),
    "Jira": (TOOLS, []),
    "Trello": (TOOLS, []),
    "Confluence": (TOOLS, []),
    "VS Code": (TOOLS, ["vscode", "visual studio code"]),
    "Visual Studio": (TOOLS, []),
    "IntelliJ IDEA": (TOOLS, ["intellij", "intellij idea"]),
    "Eclipse": (TOOLS, []),
    "NetBeans": (TOOLS, []),
    "Android Studio": (TOOLS, []),
    "Xcode": (TOOLS, []),
    "LaTeX": (TOOLS, ["latex"]),
    "Draw.io": (TOOLS, ["drawio", "draw io"]),
    "Spyder": (TOOLS, []),
    "Swagger": (TOOLS, ["openapi"]),
    "Selenium WebDriver": (TEST, []),
    "FFmpeg": (TOOLS, []),
    "Crashlytics": (TOOLS, []),
    "Google Play Console": (TOOLS, ["play console"]),
    "App Store Connect": (TOOLS, []),
    "UML": (METHOD, ["modélisation uml"]),
    # Design
    "Figma": (DESIGN, []),
    "Adobe XD": (DESIGN, ["xd"]),
    "Photoshop": (DESIGN, ["adobe photoshop", "adobe photoshop cc", "photoshop cc"]),
    "Illustrator": (DESIGN, ["adobe illustrator"]),
    "After Effects": (DESIGN, ["adobe after effects", "adobe aftereffect", "adobe aftereffects"]),
    "Sketch": (DESIGN, []),
    "UI/UX Design": (DESIGN, ["ui/ux", "ux/ui", "ui ux"]),
    # Methodologies
    "Agile": (METHOD, ["agile methodologies", "méthodes agiles", "methodologie agile"]),
    "Scrum": (METHOD, []),
    "Kanban": (METHOD, []),
    "Clean Architecture": (METHOD, []),
    "MVC": (METHOD, []),
    "MVVM": (METHOD, []),
    "OOP": (METHOD, ["poo", "object-oriented programming", "programmation orientée objet"]),
    "Design Patterns": (METHOD, []),
    "TDD": (METHOD, []),
    "Code Review": (METHOD, []),
}

# alias (lower) → canonical
TECH_ALIAS: Dict[str, str] = {}
for _canon, (_cat, _aliases) in TECH.items():
    TECH_ALIAS[_canon.lower()] = _canon
    for _a in _aliases:
        TECH_ALIAS[_a.lower()] = _canon

# Single letters / ambiguous words only count as tech inside a skills list, never in prose
AMBIGUOUS_TECH = {"c", "r", "go", "less", "material", "hive", "provider", "flask", "spring", "provider", "hive", "spring", "expo", "ia", "ai", "ml", "node", "rest", "xd", "py", "ts", "js", "s3", "sketch", "oracle", "windows", "statistics"}


def canonical_tech(token: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", (token or "").strip().strip(";:,·|-–—()[]").rstrip(".").strip()).lower()
    t = t.replace("’", "'")
    if not t:
        return None
    if t in TECH_ALIAS:
        return TECH_ALIAS[t]
    # "Python 3" / "Angular 12" / "PHP8" → strip versions
    t2 = re.sub(r"\s*v?\d+(\.\d+)*$", "", t).strip()
    if t2 and t2 in TECH_ALIAS:
        return TECH_ALIAS[t2]
    return None


def tech_category(canon: str) -> str:
    return TECH.get(canon, ("Other", []))[0]


# ─── Roles, degrees, schools, locations ───────────────────────────────────────

ROLE_WORDS = re.compile(
    r"\b(developer|developpeur|développeur|développeuse|engineer|ingenieur|ingénieur|intern|internship|"
    r"stagiaire|stage|alternant|alternance|apprenti|consultant|analyst|analyste|architect|architecte|"
    r"manager|designer|technician|technicien|freelance|freelancer|lead|cto|ceo|founder|fondateur|"
    r"co-founder|programmer|programmeur|scientist|administrator|administrateur|specialist|"
    r"spécialiste|trainee|assistant|teacher|enseignant|formateur|tutor|researcher|chercheur|"
    r"full[ -]?stack|front[ -]?end|back[ -]?end|devops|data|mobile|web|software|qa|tester|testeur|"
    r"product owner|scrum master|chef de projet|project manager|summer|été|graduation|"
    r"pfe|projet de fin d'études?|fin d'études?|fin d'etude)\b",
    re.I,
)

DEGREE_WORDS = re.compile(
    r"\b(licence|license|bachelor'?s?|bsc|b\.sc|master'?s?|mast[eè]re|msc|m\.sc|mba|phd|ph\.d|doctorat|"
    r"doctorate|ing[ée]nieur|ing[ée]nierie|engineering degree|engineer'?s degree|cycle (?:d'|des )?ing[ée]nieurs?|"
    r"baccalaur[ée]at|baccalaureate|bac\b|dipl[oô]me|diploma|degree|bts|dut|deug|cpge|pr[ée]pa|"
    r"classes? pr[ée]paratoires?|high school diploma|associate degree|certificate|certificat)\b",
    re.I,
)

SCHOOL_WORDS = re.compile(
    r"\b(universit[yée]|faculty|facult[ée]|school|[ée]cole|institute|institut|lyc[ée]e|high school|college|"
    r"coll[eè]ge|academy|acad[ée]mie|polytechnic|polytechnique|iset|enit|ensi|esprit|epi|isimm|issat|"
    r"isg|insat|enis|enicar|fsm|fst|fss|ihec|supcom|isi|isamm|sup'?com|campus|politehnica)\b",
    re.I,
)

COUNTRIES = {
    "tunisia": "Tunisia", "tunisie": "Tunisia", "france": "France", "morocco": "Morocco", "maroc": "Morocco",
    "algeria": "Algeria", "algérie": "Algeria", "romania": "Romania", "roumanie": "Romania",
    "germany": "Germany", "allemagne": "Germany", "canada": "Canada", "belgium": "Belgium",
    "belgique": "Belgium", "switzerland": "Switzerland", "suisse": "Switzerland", "spain": "Spain",
    "espagne": "Spain", "italy": "Italy", "italie": "Italy", "uk": "UK", "united kingdom": "UK",
    "usa": "USA", "united states": "USA", "saudi arabia": "Saudi Arabia", "arabie saoudite": "Saudi Arabia",
    "uae": "UAE", "qatar": "Qatar", "egypt": "Egypt", "egypte": "Egypt", "netherlands": "Netherlands",
    "portugal": "Portugal", "luxembourg": "Luxembourg", "ireland": "Ireland", "poland": "Poland",
}

CITIES = {
    "tunis", "sousse", "monastir", "sfax", "mahdia", "bizerte", "nabeul", "ariana", "ben arous", "gabes",
    "kairouan", "ksar hellal", "ksibet el mediouni", "akouda", "hammamet", "manouba", "la marsa",
    "paris", "lyon", "marseille", "toulouse", "lille", "nantes", "bordeaux", "nice", "montpellier",
    "strasbourg", "rennes", "grenoble", "bucharest", "bucarest", "casablanca", "rabat", "algiers", "alger",
    "riyadh", "jeddah", "dubai", "doha", "cairo", "berlin", "munich", "london", "madrid", "barcelona",
    "brussels", "bruxelles", "montreal", "montréal", "toronto", "geneva", "genève", "zurich",
    "amsterdam", "lisbon", "lisbonne", "milan", "rome",
}

REMOTE_WORDS = re.compile(r"\b(remote|à distance|a distance|télétravail|teletravail|full[- ]remote|hybrid|hybride)\b", re.I)


# ─── Languages (spoken) ───────────────────────────────────────────────────────

SPOKEN_LANGS = {
    "english": ("English", "Anglais"), "anglais": ("English", "Anglais"),
    "french": ("French", "Français"), "français": ("French", "Français"), "francais": ("French", "Français"),
    "arabic": ("Arabic", "Arabe"), "arabe": ("Arabic", "Arabe"),
    "german": ("German", "Allemand"), "allemand": ("German", "Allemand"),
    "spanish": ("Spanish", "Espagnol"), "espagnol": ("Spanish", "Espagnol"),
    "italian": ("Italian", "Italien"), "italien": ("Italian", "Italien"),
    "portuguese": ("Portuguese", "Portugais"), "portugais": ("Portuguese", "Portugais"),
    "turkish": ("Turkish", "Turc"), "turc": ("Turkish", "Turc"),
    "chinese": ("Chinese", "Chinois"), "chinois": ("Chinese", "Chinois"),
    "russian": ("Russian", "Russe"), "russe": ("Russian", "Russe"),
    "japanese": ("Japanese", "Japonais"), "japonais": ("Japanese", "Japonais"),
    "romanian": ("Romanian", "Roumain"), "roumain": ("Romanian", "Roumain"),
    "dutch": ("Dutch", "Néerlandais"), "korean": ("Korean", "Coréen"),
}

# (regex, EN label, FR label) — first match wins
LANG_LEVELS: List[Tuple[str, str, str]] = [
    (r"\b(native|mother tongue|maternel+e?|natale?|langue maternelle|langage maternelle|natif|native speaker)\b", "Native", "Langue maternelle"),
    (r"\b(c2|bilingual|bilingue)\b", "Bilingual (C2)", "Bilingue (C2)"),
    (r"\b(c1|fluent|courant|excellent|excellente|bonne ma[iî]trise|full professional|ma[iî]trise)\b", "Fluent (C1)", "Courant (C1)"),
    (r"\b(b2|advanced|avanc[ée]|professional working|upper[- ]intermediate)\b", "Advanced (B2)", "Avancé (B2)"),
    (r"\b(b1|intermediate|interm[ée]diaire|good|bon|bonne|conversational)\b", "Intermediate (B1)", "Intermédiaire (B1)"),
    (r"\b(a1|a2|beginner|d[ée]butant|basic|notions|elementary|scolaire)\b", "Basic (A2)", "Notions (A2)"),
]


# ─── Typos frequently seen in CVs (lower-case key → replacement) ──────────────

TYPOS: Dict[str, str] = {
    # English
    "presnt": "present", "pressent": "present", "desing": "design", "managment": "management",
    "developement": "development", "devlopment": "development", "enviroment": "environment",
    "experiance": "experience", "experince": "experience", "responsabilities": "responsibilities",
    "acheived": "achieved", "succesfully": "successfully", "sucessfully": "successfully",
    "recieved": "received", "seperate": "separate", "langue skills": "language skills",
    "scrapping": "scraping", "scrapper": "scraper", "scrappers": "scrapers", "programing": "programming",
    "aplication": "application", "applicaton": "application", "databse": "database",
    "knowlege": "knowledge", "comunication": "communication", "colaboration": "collaboration",
    "teh": "the", "framwork": "framework", "frameworkd": "framework",
    # French
    "travaill": "travail", "remplasser": "remplacer", "différantes": "différentes", "differantes": "différentes",
    "assouciative": "associative", "developpement": "développement", "developpeur": "développeur",
    "colecter": "collecter", "réaliser au sein": "réalisé au sein", "ingenieur": "ingénieur",
    "competences": "compétences", "experience professionnelle": "expérience professionnelle",
    "facilité la consultation": "faciliter la consultation", "developper": "développer",
    "applicaiton": "application",
    "c'étais": "c'était",
}

# Words that must be removed when duplicated back-to-back ("for for", "Jquery Jquery")
DOUBLE_WORD_RE = re.compile(r"\b(\w{2,})(\s+\1\b)+", re.I)


# ─── Phrases that weaken a CV (used by the diagnosis) ─────────────────────────

WEAK_OPENERS = re.compile(
    r"^(responsible for|in charge of|worked on|helped|assisted|participated in|tasks?:?|duties|"
    r"chargé de|charge de|responsable de|participation à|participation a|aide à|j'ai|i was|i am|i have)\b",
    re.I,
)

BUZZWORDS = re.compile(
    r"\b(hard[- ]working|team player|highly motivated|motivated|dynamic|passionate|go[- ]getter|"
    r"self[- ]starter|detail[- ]oriented|results[- ]driven|dynamique|motivé|motivée|sérieux|sérieuse|"
    r"rigoureux|rigoureuse|autodidacte|polyvalent|polyvalente)\b",
    re.I,
)

PERSONAL_INFO = re.compile(
    r"(\b\d{2}\s*(?:years old|ans)\b|\bage\s*:|\bâge\s*:|\bnationalit[yée]|\bmarital|\bsituation familiale|"
    r"\bcélibataire|\bmarié|\bsingle\b|\bmarried\b|\bdriving licen[cs]e|\bpermis\s+(?:de conduire|b)\b|"
    r"\bdate of birth\b|\bdate de naissance\b|\bné le\b|\bnée le\b|\btunisian\b|\btunisienne?\b)",
    re.I,
)

OBJECTIVE_RE = re.compile(
    r"(à la recherche d['’]un|a la recherche d['’]un|looking for an?|seeking an?|en recherche d['’]|"
    r"recherche (?:un|une) (?:stage|alternance|emploi|poste)|disponible pour)",
    re.I,
)

ACTION_VERBS_EN = {
    "built", "designed", "developed", "implemented", "created", "led", "launched", "shipped", "delivered",
    "optimized", "optimised", "improved", "reduced", "increased", "automated", "migrated", "integrated",
    "deployed", "architected", "engineered", "refactored", "maintained", "managed", "owned", "drove",
    "established", "streamlined", "accelerated", "scaled", "analyzed", "analysed", "researched", "proposed",
    "crawled", "extracted", "trained", "tested", "debugged", "hosted", "configured", "collaborated",
    "mentored", "coordinated", "organized", "authored", "published", "cut", "achieved", "won",
    "build", "design", "develop", "implement", "create", "lead", "launch", "ship", "deliver", "optimize",
    "improve", "reduce", "increase", "automate", "migrate", "integrate", "deploy", "maintain", "manage",
    "own", "drive", "analyze", "test", "debug", "host", "configure", "collaborate", "mentor", "coordinate",
    "conducted", "utilized", "applied", "orchestrated", "demonstrated", "simplified", "released",
}

ACTION_NOUNS_FR = re.compile(
    r"^(conception|développement|developpement|réalisation|mise en place|mise en œuvre|mise en oeuvre|"
    r"création|intégration|optimisation|amélioration|automatisation|migration|déploiement|gestion|"
    r"analyse|étude|implémentation|maintenance|refonte|pilotage|encadrement|coordination|animation|"
    r"rédaction|test|tests|modélisation|hébergement|stockage|affichage|contrôle|utilisation|clonage|"
    r"conçu|développé|réalisé|créé|intégré|optimisé|amélioré|automatisé|déployé|géré|mis en place|"
    r"concevoir|développer|réaliser|créer|intégrer|optimiser|améliorer|automatiser|déployer|gérer|"
    r"proposition|extraction|implementation|participation)\b",
    re.I,
)

# EN noun/gerund openers → past-tense verb (safe, mechanical rewrites)
EN_OPENER_REWRITES: List[Tuple[str, str]] = [
    (r"^developing\b", "Developed"), (r"^development of\b", "Developed"), (r"^develop\b", "Developed"),
    (r"^designing\b", "Designed"), (r"^design of\b", "Designed"),
    (r"^implementing\b", "Implemented"), (r"^implementation of\b", "Implemented"),
    (r"^creating\b", "Created"), (r"^creation of\b", "Created"),
    (r"^building\b", "Built"), (r"^integrating\b", "Integrated"), (r"^integration of\b", "Integrated"),
    (r"^hosting\b", "Hosted"), (r"^debugging\b", "Debugged"), (r"^deploying\b", "Deployed"),
    (r"^deployment of\b", "Deployed"), (r"^managing\b", "Managed"), (r"^management of\b", "Managed"),
    (r"^analysing\b", "Analysed"), (r"^analyzing\b", "Analyzed"), (r"^extracting\b", "Extracted"),
    (r"^testing\b", "Tested"), (r"^maintaining\b", "Maintained"), (r"^improving\b", "Improved"),
    (r"^optimizing\b", "Optimized"), (r"^automating\b", "Automated"), (r"^working on\b", "Worked on"),
    (r"^use of\b", "Used"), (r"^using\b", "Used"), (r"^utilization of\b", "Used"),
    (r"^debugging and improve\b", "Debugged and improved"), (r"^improve\b", "Improved"),
]
