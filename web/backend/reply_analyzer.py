"""
reply_analyzer.py
Accurate recruiter-reply synchronisation for the Application Tracker.

Pipeline:
  1. Collect candidate INBOX messages (recent, non-promotional) and fetch headers only.
  2. Keep messages whose sender / subject relate to an email we actually sent.
  3. Fetch full bodies read-only (BODY.PEEK) so nothing is marked as read.
  4. Match each reply to the right application with a confidence score.
  5. Classify only the *new* recruiter text (quoted history and conditional
     sentences removed; spam and out-of-office replies never change status).
  6. Apply safe, chronological status transitions (oldest -> newest).
  7. Reconcile previously stored replies with the improved classifier.
"""
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime, parseaddr
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from . import models


# ─────────────────────────────── helpers ────────────────────────────────

def decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        decoded = []
        for content, encoding in decode_header(s):
            if isinstance(content, bytes):
                decoded.append(content.decode(encoding or 'utf-8', errors='replace'))
            else:
                decoded.append(str(content))
        return ''.join(decoded)
    except Exception:
        return str(s)


IGNORED_DOMAINS = {
    'stripe.com', 'wizznews.com', 'emag.ro', 'auchan.ro', 'skyscanner.net', 'skyscanner.com',
    'freelancer.com', 'bringo.ro', 'unicredit.ro', 'beehiiv.com', 'substack.com',
    'lastminute.com', 'resumeworded.com', 'joinrs.com', 'efinancialcareers.com',
    'efinancialcareers.fr', 'google.com', 'googlemail.com', 'bestjobs.eu', 'jobgether.com',
    'pulsjob.com', 'indeed.com', 'd.kajabimail.net', 'glassdoor.com', 'careerbuilder.com',
    'unstop.news', 'github.com', 'openai.com', 'uber.com', 'bolt.eu', 'wolt.com',
    'mega-image.ro', 'penny.ro', 'sezamo.ro', 'envato.com', 'heygen.com', 'mrbit.ro',
    'similarweb.com', 'uxpilot.ai', 'infojobs.net', 'jobassist.com', 'linkedin.com',
}

ATS_DOMAINS = {
    'greenhouse-mail.io', 'greenhouse.io', 'lever.co', 'myworkday.com', 'workday.com',
    'recruitee-mailbox.com', 'bamboohr.com', 'ashbyhq.com', 'smartrecruiters.com',
    'workablemail.com', 'hireclick.com', 'teamtailor-mail.com', 'jobvite.com', 'icims.com',
}

GENERIC_DOMAINS = {
    'gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'icloud.com', 'live.com',
    'aol.com', 'proton.me', 'protonmail.com', 'yandex.com', 'mail.com', 'gmx.com',
}

EMAIL_RE = re.compile(r'[a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
MEANINGFUL = {"rejected", "review", "interview", "offer"}


def _domain(addr: str) -> str:
    return addr.split('@')[-1].lower().strip() if addr and '@' in addr else ""


def _root_domain(dom: str) -> str:
    """hr.company.co.uk -> company.co.uk ; mail.company.com -> company.com"""
    parts = dom.split('.')
    if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov') and len(parts[-1]) == 2:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:]) if len(parts) >= 2 else dom


def _is_company_domain(dom: str) -> bool:
    return bool(dom) and dom not in GENERIC_DOMAINS and _root_domain(dom) not in ATS_DOMAINS


SUBJ_PREFIX_RE = re.compile(
    r'^\s*(?:(?:re|fw|fwd|sv|aw|antw|vs|tr|wg|rv|ref|réf|automatic reply|auto reply|autoreply|'
    r'automatische antwort|réponse automatique|out of office)\s*:\s*|\[[^\]]{0,30}\]\s*)',
    re.I,
)


def normalize_subject(subj: str) -> str:
    """Strips reply/forward prefixes, [EXT] tags and follow-up markers to a comparable core."""
    s = (subj or "").replace('\xa0', ' ').replace('\r', ' ').replace('\n', ' ')
    prev = None
    while prev != s:
        prev = s
        s = SUBJ_PREFIX_RE.sub('', s)
    s = re.sub(r'^\s*follow[- ]?up\s*(?:#\d+)?\s*:\s*', '', s, flags=re.I)
    s = re.sub(r'^\s*application\s*(?:for|:)\s*', '', s, flags=re.I)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def extract_portal_url(body_text: str, fallback_url: Optional[str] = None) -> Optional[str]:
    """Extracts official career page or portal application link from body text, falling back to app position link."""
    urls = re.findall(r'https?://[^\s<>"\'\)]+', body_text or "")
    for u in urls:
        u_clean = u.rstrip('.,;:')
        if any(k in u_clean.lower() for k in ['career', 'karriere', 'job', 'opening', 'apply', 'workday',
                                               'greenhouse', 'lever', 'emply', 'recruitee', 'vacanc']):
            return u_clean
    for u in urls:
        u_clean = u.rstrip('.,;:')
        if not any(k in u_clean.lower() for k in ['linkedin.com/company', 't.me', 'twitter.com', 'facebook.com',
                                                   'instagram.com', 'youtube.com', 'unsubscribe']):
            return u_clean
    return fallback_url


def extract_meeting_link(body_text: str) -> Optional[str]:
    """Extracts Google Meet, Zoom, Microsoft Teams, or Webex video call URL from text/html."""
    if not body_text:
        return None
    m = re.search(r'https?://meet\.google\.com/[a-zA-Z0-9?=_&-]+', body_text)
    if m:
        return m.group(0).rstrip('.,;:')
    m = re.search(r'\bmeet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}', body_text)
    if m:
        return f"https://{m.group(0)}"
    m = re.search(r'https?://[a-zA-Z0-9-]+\.zoom\.us/j/[0-9]+[^\s<>"\'\)]*', body_text)
    if m:
        return m.group(0).rstrip('.,;:')
    m = re.search(r'https?://teams\.microsoft\.com/l/meetup-join/[^\s<>"\'\)]+', body_text)
    if m:
        return m.group(0).rstrip('.,;:')
    m = re.search(r'https?://[a-zA-Z0-9-]+\.webex\.com/[^\s<>"\'\)]+', body_text)
    if m:
        return m.group(0).rstrip('.,;:')
    return None


# ───────────────────────────── text cleanup ─────────────────────────────

QUOTE_MARKERS = [
    re.compile(r'\bOn\s.{5,260}?\bwrote\s*:', re.S),                 # Gmail / Apple Mail (EN)
    re.compile(r'\bLe\s.{5,260}?\ba\s+écrit\s*:', re.S),             # FR
    re.compile(r'\bAm\s.{5,260}?\bschrieb\s.{0,80}?:', re.S),        # DE
    re.compile(r'\bDen\s.{5,260}?\bskrev\s.{0,80}?:', re.S),         # SV/NO/DA
    re.compile(r'-{2,}\s*Original Message\s*-{2,}', re.I),
    re.compile(r'-{2,}\s*Message d\'origine\s*-{2,}', re.I),
    re.compile(r'\n\s*From:\s.{0,200}\n\s*(?:Sent|Date):', re.I),     # Outlook
    re.compile(r'\n\s*De\s*:\s.{0,200}\n\s*(?:Envoyé|Date)\s*:', re.I),
    re.compile(r'\n\s*Från:\s', re.I),
    re.compile(r'\n_{8,}'),
]


def strip_quoted_history(text: str) -> str:
    """Returns only the newly written part of a reply (drops quoted thread history)."""
    if not text:
        return ""
    cut = len(text)
    for rx in QUOTE_MARKERS:
        m = rx.search(text)
        if m and m.start() < cut and m.start() > 0:
            cut = m.start()
    text = text[:cut]
    lines = [ln for ln in text.split('\n') if not ln.strip().startswith('>')]
    return '\n'.join(lines).strip()


CONDITIONAL_RE = re.compile(r'\b(if|should|once|in case|whenever|si|lorsque|falls|wenn)\b', re.I)
CONDITIONAL_TARGET_RE = re.compile(
    r'shortlist|selected|successful|suitable|match|qualif|move forward|progress|considered|'
    r'retenu|sélectionn|in touch|reach out|contact you|next step', re.I)


def remove_conditional_sentences(text: str) -> str:
    """Drops sentences like 'we will schedule an interview IF you are shortlisted'."""
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    kept = [s for s in sentences if not (CONDITIONAL_RE.search(s) and CONDITIONAL_TARGET_RE.search(s))]
    return ' '.join(kept)


# ─────────────────────────────── classifier ─────────────────────────────

OOO_PHRASES = [
    "out of the office", "out of office", "ooo until", "currently away", "i am away",
    "on annual leave", "on vacation", "on holiday", "limited access to email", "will respond to emails upon my return",
    "will return on", "back in the office", "absent du bureau", "en congé", "abwesend", "nicht im büro",
    "inbox is managed by", "this mailbox is not monitored",
]
OOO_SUBJECT = ["automatic reply", "auto reply", "autoreply", "out of office", "automatische antwort",
               "réponse automatique", "abwesenheit", "absence"]

SPAM_PHRASES = [
    "we're hiring", "we’re hiring", "remote opportunities", "get paid in usd", "work remotely |",
    "earn money", "unsubscribe from this list", "view this email in your browser", "limited time offer",
    "registration fee", "pay a fee", "training fee",
]

OFFER_PHRASES = [
    "pleased to offer you", "formal offer of employment", "offer letter", "extend an offer",
    "extend you an offer", "we would like to offer you", "offer of employment",
    "offre d'emploi ci-jointe", "proposition d'embauche", "promesse d'embauche",
]

REJECTION_PHRASES = [
    "not be proceeding", "will not be proceeding", "won't be proceeding", "cannot consider",
    "not moving forward", "not to move forward", "decided not to move forward", "will not be moving forward",
    "pursue other candidates", "pursuing other candidates", "selected another candidate",
    "moved forward with other candidates", "proceed with other candidates", "other candidates whose",
    "not an ideal match", "not a match at this stage", "not a good fit", "not the right fit",
    "do not have any suitable openings", "don't have any suitable openings", "no suitable openings",
    "not have any suitable", "no suitable vacancies", "no open positions", "no current openings",
    "position has been filled", "role has been filled", "role has been closed", "decided to close this role",
    "regret to inform", "unfortunately, we", "unfortunately we", "we are unable to offer",
    "unsuccessful on this occasion", "not been successful", "were not successful",
    "doubt that currently we have relevant positions", "not have relevant positions",
    "malheureusement", "n'a pas été retenue", "pas été retenue", "ne pouvons donner suite",
    "ne pas donner suite", "profil ne correspond pas", "leider", "absage", "tyvärr", "dessverre",
]

STRONG_INTERVIEW_PHRASES = [
    "invite you to an interview", "invite you for an interview", "invited for an interview",
    "invitation to interview", "like to invite you", "would like to schedule", "let's schedule",
    "please book a time", "book a slot", "pick a time", "choose a time", "sent you a time",
    "sent a time for", "time for next week", "available for a call", "your availability",
    "are you available", "when are you available", "introductory call", "intro call", "phone screen",
    "screening call", "initial conversation", "like to speak with you", "love to connect", "quick call",
    "technical assessment", "coding challenge", "take-home", "home assignment", "calendly.com",
    "set up an interview", "set up a call", "set up a time", "internship meeting", "let's meet",
    "join the meeting", "zoom meeting", "teams meeting", "google meet", "calendar invitation",
    "invitation de google agenda", "participer avec google meet", "rejoindre la réunion",
    "entretien", "test technique", "échange téléphonique", "rendez-vous", "vorstellungsgespräch",
]

PORTAL_PHRASES = [
    "careers website", "careers page", "career site", "career website", "careers site",
    "apply through our", "apply directly on our", "apply on our website", "apply via our",
    "apply for the role via", "applications must be directed through", "applications portal",
    "application portal", "submit your application through", "submit your application via",
    "explore available vacancies", "please visit our careers", "if you are emailing about applying",
]

REVIEW_PHRASES = [
    "received your email", "received your application", "receipt of your application",
    "thank you for your application", "thank you for applying", "thanks for applying",
    "thank you for your interest", "thanks for your interest", "will review your application",
    "will review the information", "team will review", "reviewing it now", "under review", "in review",
    "currently reviewing", "being reviewed", "actively reviewing", "will be in touch", "get back to you",
    "successfully received", "application received", "bien reçu votre candidature", "en cours d'examen",
    "accusons réception", "étudions votre candidature", "bewerbung erhalten", "eingegangen",
]


def classify_email_intent(body_text: str, subject: str) -> Tuple[Optional[str], str]:
    """
    Classifies a recruiter response into:
      'offer' | 'rejected' | 'interview' | 'review' | 'auto_reply' | 'ignore' | None
    Only newly written text is considered; conditional statements never trigger interview/offer.
    """
    subj_lower = (subject or "").lower()
    main_text = strip_quoted_history(body_text or "")
    main_lower = re.sub(r'\s+', ' ', main_text.replace('\xa0', ' ')).lower()

    # 1. Out-of-office / automatic replies never change status
    if any(p in subj_lower for p in OOO_SUBJECT) or any(p in main_lower for p in OOO_PHRASES):
        return "auto_reply", "Automatic / out-of-office reply"

    # 2. Mass-marketing / spam masquerading as a reply
    if sum(1 for p in SPAM_PHRASES if p in main_lower) >= 1 and not any(p in main_lower for p in REVIEW_PHRASES[:6]):
        return "ignore", "Marketing / spam message"

    decisive = remove_conditional_sentences(main_lower)

    # 3. Offer
    for p in OFFER_PHRASES:
        if p in decisive:
            return "offer", f"Offer indicator: '{p}'"

    # 4. Rejection (beats any interview wording)
    for p in REJECTION_PHRASES:
        if p in main_lower:
            return "rejected", f"Rejection indicator: '{p}'"

    # 5. Interview: real meeting link or concrete scheduling language
    meet = extract_meeting_link(main_text) or extract_meeting_link(subject or "")
    if meet:
        return "interview", f"Video interview link: {meet}"
    if any(k in subj_lower for k in ["invitation:", "invitation mise à jour", "interview", "entretien"]) and \
            not any(k in subj_lower for k in ["application received", "thank you"]):
        if "interview" in subj_lower or "invitation" in subj_lower or "entretien" in subj_lower:
            return "interview", f"Interview / calendar invitation subject: '{subject.strip()[:80]}'"
    for p in STRONG_INTERVIEW_PHRASES:
        if p in decisive:
            return "interview", f"Interview scheduling indicator: '{p}'"

    # 6. Redirect to official careers portal -> under review
    for p in PORTAL_PHRASES:
        if p in main_lower:
            return "review", f"Asked to apply via official portal: '{p}'"

    # 7. Acknowledgement / under review
    for p in REVIEW_PHRASES:
        if p in main_lower or p in subj_lower:
            return "review", f"Application acknowledged / under review: '{p}'"

    return None, "General correspondence"


# ─────────────────────────────── matching ───────────────────────────────

def _title_from_subject(subject: str) -> str:
    core = normalize_subject(subject)
    return re.split(r'\s+[—–-]\s+', core)[0].strip() if core else ""


def _score_log(log, cand_emails: List[str], cand_domains: List[str], subj_core: str,
               from_h: str, body_lower: str) -> Tuple[int, List[str]]:
    score, why = 0, []
    to_em = (log.to_email or "").strip().lower()
    to_dom = _domain(to_em)

    if to_em and to_em in cand_emails:
        score += 60; why.append(f"sender={to_em}")
    elif to_dom and _is_company_domain(to_dom) and any(_root_domain(d) == _root_domain(to_dom) for d in cand_domains):
        score += 30; why.append(f"domain={_root_domain(to_dom)}")

    log_core = normalize_subject(log.subject or "")
    if subj_core and log_core:
        if subj_core == log_core:
            score += 45; why.append("subject=exact")
        elif len(subj_core) > 12 and (subj_core in log_core or log_core in subj_core):
            score += 30; why.append("subject~")

    app = log.application
    if app:
        title = (app.title or "").lower().strip()
        comp = (app.company or "").lower().strip()
        if title and len(title) > 3 and title in subj_core:
            score += 15; why.append("title")
        comp_key = re.sub(r'\b(inc|ltd|llc|gmbh|sa|sas|corp|co|limited|the)\b\.?', '', comp).strip(' .,')
        if comp_key and len(comp_key) > 2 and (comp_key in from_h.lower() or comp_key in body_lower[:3000]):
            score += 10; why.append("company")
    return score, why


def _match_application(cand_emails, cand_domains, subj, from_h, body, outbound_logs, user_apps):
    subj_core = normalize_subject(subj)
    body_lower = (body or "").lower()

    best, best_score, best_why = None, 0, []
    for log in outbound_logs:
        sc, why = _score_log(log, cand_emails, cand_domains, subj_core, from_h, body_lower)
        if sc > best_score or (sc == best_score and best is not None and sc > 0 and
                               (log.sent_at or datetime.min) > (best.sent_at or datetime.min)):
            best, best_score, best_why = log, sc, why

    if best is not None and best_score >= 50:
        return best, best.application, best_score, ", ".join(best_why)

    # Fallback for imported applications without outbound logs
    for a in user_apps:
        notes_emails = {m.group(0).lower() for m in EMAIL_RE.finditer(a.notes or "")}
        if notes_emails & set(cand_emails):
            return None, a, 60, "notes email"
        comp = (a.company or "").lower()
        title = (a.title or "").lower()
        if comp and len(comp) > 2 and comp in from_h.lower() and title and title in subj_core:
            return None, a, 55, "company+title"
    return None, None, best_score, ""


# ─────────────────────────── status transitions ─────────────────────────

def _was_auto_closed(app) -> bool:
    notes = app.notes or ""
    return "⏱️ Auto-Closed" in notes and "Status -> 'rejected'" not in notes


def _apply_transition(app, new_status: str) -> bool:
    """Returns True if the application status changed. Never downgrades offer/accepted."""
    cur = app.status or "applied"
    if cur in ("accepted",):
        return False
    if new_status == "offer":
        target = "offer"
    elif new_status == "rejected":
        if cur == "offer":
            return False
        target = "rejected"
    elif new_status == "interview":
        if cur in ("offer",) or (cur == "rejected" and not _was_auto_closed(app)):
            return False
        target = "interview"
    elif new_status == "review":
        if cur in ("applied", "sent", "saved") or (cur == "rejected" and _was_auto_closed(app)):
            target = "review"
        else:
            return False
    else:
        return False
    if target != cur:
        app.status = target
        return True
    return False


# ───────────────────────────── IMAP utilities ────────────────────────────

def _message_body(msg) -> str:
    parts = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_disposition() == 'attachment' and ctype != 'text/calendar':
            continue
        if ctype in ('text/plain', 'text/html', 'text/calendar'):
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or 'utf-8'
            try:
                text = payload.decode(charset, errors='replace')
            except LookupError:
                text = payload.decode('utf-8', errors='replace')
            if ctype == 'text/html':
                text = BeautifulSoup(text, 'html.parser').get_text(separator='\n')
            parts.append((ctype, text))
    # Prefer plain text (keeps quote markers intact); fall back to html; always add calendar
    plain = [t for c, t in parts if c == 'text/plain']
    html = [t for c, t in parts if c == 'text/html']
    cal = [t for c, t in parts if c == 'text/calendar']
    main = "\n".join(plain) if plain else "\n".join(html)
    return (main + ("\n" + "\n".join(cal) if cal else "")).strip()


def _msg_datetime(date_h: str) -> datetime:
    try:
        dt = parsedate_to_datetime(date_h)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()


def _collect_candidate_ids(mail, days_back: int) -> List[bytes]:
    ids = set()
    since = (datetime.utcnow() - timedelta(days=days_back)).strftime('%d-%b-%Y')
    try:
        st, data = mail.search(None, 'X-GM-RAW',
                               f'"newer_than:{days_back}d -category:promotions -category:social -category:forums"')
        if st == 'OK' and data and data[0]:
            ids.update(data[0].split())
    except Exception:
        pass
    for q in [f'(SINCE {since} SUBJECT "Application")', f'(SINCE {since} SUBJECT "Candidature")',
              f'(SINCE {since} SUBJECT "Interview")', f'(SINCE {since} SUBJECT "Invitation")',
              f'(SINCE {since} SUBJECT "Re:")', f'(SINCE {since} TEXT "meet.google.com")']:
        try:
            st, data = mail.search(None, q)
            if st == 'OK' and data and data[0]:
                ids.update(data[0].split())
        except Exception:
            pass
    return sorted(ids, key=lambda x: int(x))


def _fetch_headers(mail, ids: List[bytes]) -> Dict[bytes, Any]:
    out = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            st, data = mail.fetch(b','.join(chunk).decode(),
                                  '(BODY.PEEK[HEADER.FIELDS (FROM REPLY-TO SUBJECT DATE AUTO-SUBMITTED)])')
        except Exception:
            continue
        if st != 'OK' or not data:
            continue
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2:
                m = re.match(rb'(\d+)\s', item[0])
                if m:
                    out[m.group(1)] = email.message_from_bytes(item[1])
    return out


# ───────────────────────────── main entrypoint ───────────────────────────

def sync_recruiter_replies(db: Session, user_id: int, max_messages: int = 400, days_back: int = 60) -> Dict[str, Any]:
    """
    Scans the user's INBOX for responses to applications they sent, matches each reply to the
    correct application, classifies the outcome, and updates the Tracker accurately.
    """
    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == user_id).first()
    if not settings or not settings.smtp_user or not settings.smtp_password:
        raise ValueError("Gmail credentials not configured. Please enter your Gmail address and App Password in Settings.")
    own_email = settings.smtp_user.strip().lower()
    clean_pwd = ''.join(settings.smtp_password.split())
    host = settings.smtp_host.replace("smtp.", "imap.") if settings.smtp_host and "smtp." in settings.smtp_host else "imap.gmail.com"

    try:
        mail = imaplib.IMAP4_SSL(host, 993, timeout=30)
        mail.login(settings.smtp_user, clean_pwd)
    except Exception as e:
        raise ValueError(f"Gmail IMAP connection failed: {str(e)}. Ensure IMAP is enabled in your Gmail settings.")

    breakdown = {"rejected": 0, "review": 0, "interview": 0, "offer": 0, "auto_reply": 0, "ignored": 0}
    updates: List[Dict[str, Any]] = []
    matched_app_ids = set()
    restored = linked = 0

    try:
        mail.select('INBOX', readonly=True)

        from .bounce_cleaner import get_blacklisted_emails
        blacklist = get_blacklisted_emails(db)

        outbound_logs = db.query(models.EmailLog).filter(
            models.EmailLog.user_id == user_id,
            models.EmailLog.template_type != "recruiter_reply",
        ).all()
        user_apps = db.query(models.Application).filter(models.Application.user_id == user_id).all()

        sent_emails = {(l.to_email or "").strip().lower() for l in outbound_logs if l.to_email}
        sent_domains = {_root_domain(_domain(e)) for e in sent_emails if _is_company_domain(_domain(e))}
        sent_cores = {normalize_subject(l.subject) for l in outbound_logs if l.subject}
        sent_cores.discard("")

        candidate_ids = _collect_candidate_ids(mail, days_back)[-max_messages:]
        headers = _fetch_headers(mail, candidate_ids)

        # Pre-filter using headers only (fast, read-only)
        relevant: List[Tuple[datetime, bytes]] = []
        for mid, h in headers.items():
            from_h = decode_mime_words(h.get('From', ''))
            subj = decode_mime_words(h.get('Subject', ''))
            from_email = parseaddr(from_h)[1].lower()
            reply_email = parseaddr(decode_mime_words(h.get('Reply-To', '')))[1].lower()
            if not from_email or from_email == own_email:
                continue
            if any(d in from_email for d in ('mailer-daemon', 'postmaster')):
                continue
            dom = _domain(from_email)
            is_known_sender = from_email in sent_emails or reply_email in sent_emails or \
                _root_domain(dom) in sent_domains or _root_domain(_domain(reply_email)) in sent_domains
            is_thread_reply = normalize_subject(subj) in sent_cores
            is_calendar = 'calendar' in from_email or subj.lower().startswith(('invitation', 'updated invitation'))
            if not (is_known_sender or is_thread_reply or is_calendar):
                if _root_domain(dom) in IGNORED_DOMAINS or dom in IGNORED_DOMAINS:
                    continue
                if not re.search(r'application|candidature|interview|entretien|your cv|your resume|bewerbung',
                                 subj, re.I):
                    continue
            relevant.append((_msg_datetime(h.get('Date', '')), mid))

        relevant.sort(key=lambda x: x[0])  # oldest -> newest so the latest outcome wins

        for msg_dt, mid in relevant:
            try:
                st, mdata = mail.fetch(mid.decode(), '(BODY.PEEK[])')
                if st != 'OK' or not mdata or not isinstance(mdata[0], tuple):
                    continue
                msg = email.message_from_bytes(mdata[0][1])
                subj = decode_mime_words(msg.get('Subject', '')).replace('\r', '').replace('\n', ' ').strip()
                from_h = decode_mime_words(msg.get('From', ''))
                from_email = parseaddr(from_h)[1].lower()
                reply_email = parseaddr(decode_mime_words(msg.get('Reply-To', '')))[1].lower()
                body = _message_body(msg)

                organizer = ""
                m_org = re.search(r'ORGANIZER[^:\n]*:mailto:([^\s\r\n]+)', body, re.I) or \
                    re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\s*[-–]\s*(?:Organisateur|Organizer)', body, re.I)
                if m_org:
                    organizer = m_org.group(1).strip().lower()

                cand_emails = [e for e in dict.fromkeys([from_email, reply_email, organizer])
                               if e and e != own_email and not any(x in e for x in ('google.com', 'calendar-notification', 'mailer-daemon'))]
                cand_domains = [_domain(e) for e in cand_emails if _is_company_domain(_domain(e))]

                log, app, score, match_note = _match_application(
                    cand_emails, cand_domains, subj, from_h, body, outbound_logs, user_apps)

                new_status, reason = classify_email_intent(body, subj)
                if new_status == "ignore":
                    breakdown["ignored"] += 1
                    continue

                # Restore applications that were wrongly purged (orphaned outbound logs, not blacklisted)
                if app is None and log is not None and log.application_id is None and \
                        new_status in MEANINGFUL and (log.to_email or "").lower() not in blacklist:
                    app = _restore_application(db, user_id, log, outbound_logs)
                    if app:
                        user_apps.append(app)
                        restored += 1

                if app is None:
                    continue
                matched_app_ids.add(app.id)

                main_text = strip_quoted_history(body)
                snippet = re.sub(r'\s+', ' ', main_text)[:240].strip()
                portal_url = extract_portal_url(main_text, app.url)
                meet_url = extract_meeting_link(main_text) or extract_meeting_link(subj)

                # De-duplicate: same sender + subject + body start, or same message timestamp
                existing = db.query(models.EmailLog).filter(
                    models.EmailLog.template_type == "recruiter_reply",
                    models.EmailLog.user_id == user_id,
                    models.EmailLog.subject == subj,
                ).all()
                dup = None
                for e in existing:
                    same_sender = (e.to_email or "").lower() == (from_email or "").lower()
                    same_body = (e.body or "")[:160].strip() == (main_text or body)[:160].strip()
                    same_time = e.sent_at and abs((e.sent_at - msg_dt).total_seconds()) < 120
                    if same_sender and (same_body or same_time):
                        dup = e
                        break

                old_status = app.status
                changed = False
                if new_status in MEANINGFUL:
                    is_new = dup is None or dup.application_id != app.id or dup.status in ("bounced", None)
                    if is_new:
                        breakdown[new_status] += 1
                        changed = _apply_transition(app, new_status)
                elif new_status == "auto_reply" and dup is None:
                    breakdown["auto_reply"] += 1

                if dup is None and new_status in MEANINGFUL | {"auto_reply"}:
                    db.add(models.EmailLog(
                        user_id=user_id, application_id=app.id,
                        to_email=from_email or from_h, to_name=from_h, subject=subj,
                        body=main_text or snippet, template_type="recruiter_reply",
                        status=new_status if new_status != "auto_reply" else "auto_reply",
                        sent_at=msg_dt,
                    ))
                elif dup is not None:
                    if dup.application_id != app.id:
                        dup.application_id = app.id
                        linked += 1
                    dup.status = new_status or dup.status
                    dup.sent_at = msg_dt

                if changed:
                    ts = msg_dt.strftime('%Y-%m-%d %H:%M')
                    meet_text = f" 📹 Meeting Link: {meet_url}." if meet_url else ""
                    link_text = f" Portal / Position Link: {portal_url}." if (portal_url and new_status == 'review') else ""
                    app.notes = (app.notes or "") + (
                        f"\n[{ts}] 📥 Recruiter Reply: Status -> '{app.status}'.{meet_text}{link_text} "
                        f"From: {from_h}. \"{snippet}\""
                    )
                    updates.append({
                        "app_id": app.id, "company": app.company, "title": app.title,
                        "old_status": old_status, "new_status": app.status, "from": from_h,
                        "reason": reason, "match": f"{match_note} (score {score})",
                        "snippet": snippet, "portal_url": portal_url, "meet_url": meet_url,
                    })
            except Exception as fe:
                print(f"[ReplyAnalyzer] Message processing error {mid}: {fe}")

        db.commit()
        reclassified = reconcile_stored_replies(db, user_id)
        db.commit()
        try:
            mail.logout()
        except Exception:
            pass

        return {
            "scanned_messages": len(headers),
            "relevant_messages": len(relevant),
            "matched_applications": len(matched_app_ids),
            "updated_applications": len(updates),
            "restored_applications": restored,
            "relinked_replies": linked,
            "reclassified": reclassified,
            "breakdown": breakdown,
            "updates": updates,
        }
    except Exception:
        try:
            mail.logout()
        except Exception:
            pass
        raise


def _restore_application(db: Session, user_id: int, log, outbound_logs) -> Optional[models.Application]:
    """Recreates an application whose card was wrongly purged, re-linking its outbound history."""
    to_em = (log.to_email or "").lower()
    core = normalize_subject(log.subject or "")
    title = _title_from_subject(log.subject or "") or "Application"
    name = (log.to_name or "").strip()
    company = ""
    for l in [log] + [x for x in outbound_logs if (x.to_email or "").lower() == to_em]:
        m = re.search(r'^\s*Dear\s+.{1,80}?\s+at\s+([^,\n]{2,80}),', l.body or "", re.I | re.M)
        if m and m.group(1).strip().lower() not in ("kannur", "remote"):
            company = m.group(1).strip()
            break
    if not company:
        dom = _domain(to_em)
        if _is_company_domain(dom):
            company = _root_domain(dom).split('.')[0].replace('-', ' ').title()
        else:
            company = name or to_em
    app = models.Application(
        user_id=user_id, title=title.title() if title.islower() else title, company=company,
        status="applied", applied_at=log.sent_at or datetime.utcnow(),
        notes=f"♻️ Restored by Mailbox Sync — recruiter replied to your application sent to {to_em}",
    )
    db.add(app)
    db.flush()
    for l in outbound_logs:
        if (l.to_email or "").lower() == to_em and l.application_id is None and normalize_subject(l.subject or "") == core:
            l.application_id = app.id
            if l.status == "bounced":
                l.status = "sent"
            l.application = app
    return app


def reconcile_stored_replies(db: Session, user_id: int) -> int:
    """
    Re-evaluates stored recruiter replies with the current classifier and corrects
    application statuses that were set by an earlier, less accurate analysis
    (only when the user has not manually changed the status since).
    """
    fixed = 0
    logs = db.query(models.EmailLog).filter(
        models.EmailLog.user_id == user_id,
        models.EmailLog.template_type == "recruiter_reply",
        models.EmailLog.application_id.isnot(None),
    ).order_by(models.EmailLog.sent_at.asc()).all()

    by_app: Dict[int, List[Any]] = {}
    for l in logs:
        by_app.setdefault(l.application_id, []).append(l)

    for app_id, app_logs in by_app.items():
        app = db.query(models.Application).filter(models.Application.id == app_id).first()
        if not app:
            continue
        latest_meaningful = None
        for l in app_logs:
            new_status, _ = classify_email_intent(l.body or "", l.subject or "")
            prev = l.status
            l.status = new_status if new_status else prev
            if new_status in MEANINGFUL:
                latest_meaningful = (l, prev, new_status)
        if not latest_meaningful:
            continue
        l, prev, new_status = latest_meaningful
        # Correct only statuses our analyzer set (app still equals what the old analysis wrote)
        if app.status == prev and prev != new_status and app.status not in ("offer", "accepted"):
            old = app.status
            app.status = new_status
            if app.status != old:
                ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                app.notes = (app.notes or "") + f"\n[{ts}] 🔎 Sync correction: '{old}' -> '{app.status}' (re-analysed recruiter reply)"
                fixed += 1
    return fixed
