from typing import Tuple, Optional

FR_INDICATORS = [
    " de ", " le ", " la ", " les ", " des ", " un ", " une ", " du ", " et ", " pour ",
    " avec ", " dans ", " sur ", " nous ", " vous ", " poste ", " équipe ", " profil ",
    " expérience ", " compétences ", " chez ", " télétravail ", " développeur ", " développeuse ",
    " ingénieur ", " recherchons ", " rejoignez ", " embauche ", " candidature ", " montréal ", " québec ",
    " à ", " au ", " aux ", " offre d'emploi ", " temps plein ", " cdi ", " cdd ", " stage ", " alternance ",
    " entreprise ", " mission ", " compétences requises ", " formation ", " rémunération "
]

def detect_language(text: Optional[str]) -> str:
    """Detects whether text is predominantly French or English. Returns 'fr' or 'en'."""
    if not text:
        return "en"
    t = f" {text.lower()} "
    # Direct strong indicators
    if any(k in t for k in [
        "développeur", "développeuse", "recherchons", "rejoignez notre équipe",
        "télétravail", "candidature", "offre d'emploi", "temps plein", "postuler", "salaire"
    ]):
        return "fr"
    # Word count matches
    matches = sum(1 for ind in FR_INDICATORS if ind in t)
    return "fr" if matches >= 2 else "en"

PLATFORM_PHRASES = {
    "job_bank": {
        "en": "referenced in your recent job posting on Job Bank",
        "fr": "suite à votre offre d'emploi sur Job Bank"
    },
    "indeed": {
        "en": "referenced in your recent job posting on Indeed",
        "fr": "suite à votre offre d'emploi sur Indeed"
    },
    "linkedin": {
        "en": "referenced in your recent publication on LinkedIn",
        "fr": "suite à votre publication sur LinkedIn"
    },
    "zip_recruiter": {
        "en": "referenced in your recent job posting on ZipRecruiter",
        "fr": "suite à votre offre d'emploi sur ZipRecruiter"
    },
    "glassdoor": {
        "en": "referenced in your recent job posting on Glassdoor",
        "fr": "suite à votre offre d'emploi sur Glassdoor"
    },
    "google": {
        "en": "referenced in your recent job posting on Google Jobs",
        "fr": "suite à votre offre d'emploi sur Google Jobs"
    },
    "generic": {
        "en": "referenced in your recent job posting",
        "fr": "suite à votre récente offre d'emploi"
    }
}

def detect_platform_source(
    site: Optional[str] = None,
    url: Optional[str] = None,
    text: Optional[str] = None
) -> str:
    """
    Identifies the hiring platform ('job_bank', 'indeed', 'linkedin', 'zip_recruiter', 'glassdoor', 'google', or 'generic').
    """
    combined = f"{site or ''} {url or ''} {text or ''}".lower()
    if any(k in combined for k in ["job_bank", "jobbank", "guichet", "jobbank.gc.ca"]):
        return "job_bank"
    if any(k in combined for k in ["indeed", "indeed.com"]):
        return "indeed"
    if any(k in combined for k in ["linkedin", "linkedin.com"]):
        return "linkedin"
    if any(k in combined for k in ["zip_recruiter", "ziprecruiter", "ziprecruiter.com"]):
        return "zip_recruiter"
    if any(k in combined for k in ["glassdoor", "glassdoor.com"]):
        return "glassdoor"
    if any(k in combined for k in ["google", "google jobs", "google.com"]):
        return "google"
    return "linkedin"

def get_application_email(
    role_title: str,
    company: str,
    recruiter_name: Optional[str] = None,
    post_text: Optional[str] = None,
    sender_name: Optional[str] = "Candidate",
    sender_email: Optional[str] = "",
    lang: Optional[str] = None,
    site: Optional[str] = None,
    url: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Generates a high-converting, professional email subject & body tailored
    to the job's detected or specified language ('en' or 'fr') and platform
    (Job Bank, LinkedIn, Indeed, etc.).
    Returns (subject, body, language).
    """
    clean_title = (role_title or "Software Developer").strip()
    clean_comp = (company or "Hiring Team").strip()
    clean_sender = (sender_name or "Candidate").strip()
    clean_email = (sender_email or "").strip()
    
    # Auto-detect language if not explicitly provided
    if not lang or lang not in ("en", "fr"):
        sample = f"{clean_title} {clean_comp} {post_text or ''}"
        lang = detect_language(sample)

    # Detect platform source (Job Bank, LinkedIn, Indeed, etc.)
    platform_key = detect_platform_source(site=site, url=url, text=post_text)
    phrases = PLATFORM_PHRASES.get(platform_key, PLATFORM_PHRASES["generic"])
    phrase_fr = phrases["fr"]
    phrase_en = phrases["en"]

    if lang == "fr":
        subject = f"Candidature : {clean_title} — {clean_sender}"
        salutation = f"Madame, Monsieur,\nÉquipe de recrutement de {clean_comp},"
        if recruiter_name and recruiter_name.strip() and recruiter_name.strip().lower() not in ("hiring team", "recruiter", "unknown", "team"):
            salutation = f"Bonjour {recruiter_name.strip()},"

        body = f"""{salutation}

Je vous soumets par la présente ma candidature pour le poste de {clean_title}, {phrase_fr}.

Ayant pris connaissance de vos exigences techniques, mon profil correspond étroitement aux compétences que vous recherchez.

Vous trouverez mon curriculum vitae ci-joint pour examen. Je me tiens à votre entière disposition pour un échange afin d'approfondir l'adéquation de mon parcours avec vos objectifs.

En vous remerciant de l'attention que vous porterez à ma démarche, je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

{clean_sender}
{clean_email}"""
    else:
        subject = f"Application: {clean_title} — {clean_sender}"
        r_name = (recruiter_name or "").strip()
        salutation = f"Dear {r_name} at {clean_comp}," if r_name and r_name.lower() not in ("hiring team", "recruiter", "unknown", "team") else f"Dear Hiring Team at {clean_comp},"

        body = f"""{salutation}

I am writing to formally submit my application for the {clean_title} position {phrase_en}.

Having reviewed your technical requirements, my experience aligns closely with the skills your team is seeking.

I have attached my resume for your review. Thank you for your time and consideration, and I look forward to the opportunity to speak with you.

Sincerely,

{clean_sender}
{clean_email}"""

    return subject, body, lang

def get_followup_email(
    role_title: str,
    company: str,
    recruiter_name: Optional[str] = None,
    applied_date_str: Optional[str] = None,
    sender_name: Optional[str] = "Candidate",
    sender_email: Optional[str] = "",
    lang: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Generates a professional follow-up email in French or English.
    Returns (subject, body, language).
    """
    clean_title = (role_title or "Software Developer").strip()
    clean_comp = (company or "Hiring Team").strip()
    clean_sender = (sender_name or "Candidate").strip()
    clean_email = (sender_email or "").strip()
    
    if not lang or lang not in ("en", "fr"):
        lang = detect_language(f"{clean_title} {clean_comp}")

    date_str = applied_date_str or ("récemment" if lang == "fr" else "recently")

    if lang == "fr":
        subject = f"Relance : Candidature au poste de {clean_title} — {clean_sender}"
        r_name = (recruiter_name or "").strip()
        salutation = f"Bonjour {r_name}," if r_name and r_name.lower() not in ("hiring team", "recruiter", "unknown", "team") else f"Madame, Monsieur,\nÉquipe de recrutement de {clean_comp},"

        body = f"""{salutation}

J'espère que vous allez bien.

Je me permets de revenir vers vous concernant ma candidature au poste de {clean_title} transmise {date_str}. Je réitère mon vif intérêt pour cette opportunité et pour collaborer avec l'équipe de {clean_comp}.

Je comprends parfaitement la charge que représente la sélection des profils, mais je souhaitais m'enquérir de l'état d'avancement de ma candidature. Je reste à votre disposition si vous souhaitez obtenir des compléments d'information ou des précisions techniques sur mes réalisations.

Vous trouverez de nouveau mon curriculum vitae ci-joint pour votre confort.

En vous remerciant sincèrement pour votre attention et votre considération, je vous prie d'agréer l'expression de mes salutations distinguées.

{clean_sender}
{clean_email}"""
    else:
        subject = f"Follow-up: Application for {clean_title} — {clean_sender}"
        r_name = (recruiter_name or "").strip()
        salutation = f"Dear {r_name} at {clean_comp}," if r_name and r_name.lower() not in ("hiring team", "recruiter", "unknown", "team") else f"Dear Hiring Team at {clean_comp},"

        body = f"""{salutation}

I hope this email finds you well.

I am following up on my application for the {clean_title} position submitted {date_str}. I remain very enthusiastic about the opportunity to join {clean_comp} and contribute to your team's initiatives.

I understand your team is busy reviewing candidates, but I wanted to kindly check in on the status of my application and reiterate my strong interest in the role. Please let me know if you would like any additional information or technical details from my end.

I have attached my resume again for your convenience.

Thank you very much for your time and consideration.

Best regards,

{clean_sender}
{clean_email}"""

    return subject, body, lang
