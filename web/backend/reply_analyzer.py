import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from . import models

def decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        parts = decode_header(s)
        decoded = []
        for content, encoding in parts:
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
    'google.com', 'googlemail.com', 'bestjobs.eu', 'jobgether.com', 'pulsjob.com',
    'indeed.com', 'd.kajabimail.net'
}

ATS_DOMAINS = {
    'greenhouse-mail.io', 'greenhouse.io', 'lever.co', 'myworkday.com',
    'recruitee-mailbox.com', 'bamboohr.com', 'ashbyhq.com', 'smartrecruiters.com',
    'workablemail.com'
}

def extract_portal_url(body_text: str, fallback_url: Optional[str] = None) -> Optional[str]:
    """Extracts official career page or portal application link from body text, falling back to app position link."""
    urls = re.findall(r'https?://[^\s<>"\'\)]+', body_text)
    for u in urls:
        u_clean = u.rstrip('.,;:')
        u_lower = u_clean.lower()
        if any(k in u_lower for k in ['career', 'job', 'opening', 'apply', 'workday', 'greenhouse', 'lever', 'emply', 'recruitee']):
            return u_clean
    for u in urls:
        u_clean = u.rstrip('.,;:')
        u_lower = u_clean.lower()
        if not any(k in u_lower for k in ['linkedin.com/company', 't.me', 'twitter.com', 'facebook.com', 'instagram.com', 'youtube.com']):
            return u_clean
    return fallback_url

def extract_meeting_link(body_text: str) -> Optional[str]:
    """Extracts Google Meet, Zoom, Microsoft Teams, or Webex video call URL from text/html."""
    if not body_text:
        return None
    # 1. Google Meet: meet.google.com/xxx-yyyy-zzz
    m_meet = re.search(r'https?://meet\.google\.com/[a-zA-Z0-9?=_&-]+', body_text)
    if m_meet:
        return m_meet.group(0).rstrip('.,;:')
    m_meet_raw = re.search(r'\bmeet\.google\.com/[a-zA-Z0-9?=_&-]+', body_text)
    if m_meet_raw:
        return f"https://{m_meet_raw.group(0).rstrip('.,;:')}"
    # 2. Zoom
    m_zoom = re.search(r'https?://[a-zA-Z0-9-]+\.zoom\.us/j/[0-9]+[^\s<>"\'\)]*', body_text)
    if m_zoom:
        return m_zoom.group(0).rstrip('.,;:')
    # 3. Microsoft Teams
    m_teams = re.search(r'https?://teams\.microsoft\.com/l/meetup-join/[^\s<>"\'\)]+', body_text)
    if m_teams:
        return m_teams.group(0).rstrip('.,;:')
    # 4. Webex
    m_webex = re.search(r'https?://[a-zA-Z0-9-]+\.webex\.com/[^\s<>"\'\)]+', body_text)
    if m_webex:
        return m_webex.group(0).rstrip('.,;:')
    return None

def classify_email_intent(body_text: str, subject: str) -> tuple[Optional[str], str]:
    """
    Classifies a recruiter response into one of:
    - 'rejected': Candidate not moving forward, role closed, or no suitable openings
    - 'review': Application received, official website submission requested, or in review
    - 'interview': Interview, Google Meet / video call, phone screening, coding assessment, or call scheduling
    - 'offer': Formal employment offer
    - 'auto_reply': Out of office or automatic delivery acknowledgment
    - None: Unclassified / General correspondence
    """
    body_lower = body_text.lower()
    subj_lower = subject.lower()

    # Split off quoted reply history to focus strictly on new recruiter text
    quote_split = re.split(r"-{3,}\s*original message\s*-{3,}|on\s+.+wrote:|from:\s*.+sent:\s*.+", body_lower, flags=re.I)
    main_text = quote_split[0] if quote_split else body_lower

    # 0. GOOGLE MEET / VIDEO CALL INTERVIEW INVITATION (Highest Priority)
    meet_url = extract_meeting_link(body_text) or extract_meeting_link(subject)
    if meet_url:
        return "interview", f"Google Meet / Video Interview Call detected: '{meet_url}'"

    google_meet_phrases = [
        "google meet", "participer avec google meet", "join with google meet",
        "lien de la réunion", "meeting link", "invitation de google agenda",
        "google agenda", "google calendar", "internship meeting", "sent you a time",
        "sent a time for", "let's meet", "zoom meeting", "teams meeting",
        "join the meeting", "rejoindre la réunion", "calendar invitation"
    ]
    for gmp in google_meet_phrases:
        if gmp in main_text or gmp in subj_lower:
            return "interview", f"Meeting / Video Interview Call detected: '{gmp}'"

    # 1. OFFICIAL WEBSITE / CAREERS PORTAL SUBMISSION REDIRECT (Under Review)
    portal_phrases = [
        "visit our careers website", "visit our careers page", "visit our career site",
        "visit our career website", "apply through our careers page", "apply directly on our career site",
        "upload your application through our careers", "apply on our website",
        "explore available vacancies that match your skills and location directly on our career site",
        "explore available vacancies", "apply for the role via our careers site", "apply via our careers site",
        "if you are emailing about applying for a position, please visit",
        "if you choose to apply, a member of our talent team will review",
        "apply on our careers page", "please visit our careers", "visit our careers",
        "submit your application through our career", "submit your application via our career",
        "apply via our careers", "apply via our career"
    ]
    for pp in portal_phrases:
        if pp in main_text:
            return "review", f"Official website / portal application requested: '{pp}'"

    # 2. REJECTION EVALUATION
    rej_phrases = [
        "not be proceeding", "will not be proceeding", "cannot consider", "not moving forward",
        "decided not to move forward", "pursue other candidates", "pursuing other candidates",
        "selected another candidate", "not an ideal match", "skills are not an ideal match",
        "not a match at this stage", "not a good fit", "do not have any suitable openings",
        "no suitable openings", "no suitable vacancies", "no open positions",
        "position has been filled", "role has been closed", "decided to close this role",
        "keep your profile in our records", "keep your resume on file", "keep your details on file",
        "regret to inform", "wish you all the best with your career", "wish you success in your job search",
        "wish you the best in your search", "doubt that currently we have relevant positions",
        "malheureusement", "candidature n'a pas été retenue", "pas été retenue", "ne pouvons donner de suite",
        "décidé de ne pas donner suite", "profil ne correspond pas"
    ]
    for rp in rej_phrases:
        if rp in main_text:
            return "rejected", f"Rejection indicator detected: '{rp}'"

    # 3. INTERVIEW EVALUATION
    int_phrases = [
        "invite you to an interview", "invited for an interview", "invitation to interview",
        "schedule an interview", "schedule a call", "schedule a quick chat", "schedule some time",
        "introductory call", "phone screen", "screening call", "initial conversation",
        "like to speak with you", "love to connect", "technical assessment", "coding challenge",
        "take-home test", "calendly.com", "entretien", "test technique", "échange téléphonique",
        "set up an interview", "set up an initial interview", "internship meeting", "meeting next week",
        "time for next week", "sent you a time", "discuss your application", "chat about your background",
        "quick call", "zoom call", "teams call", "video call", "rendez-vous"
    ]
    for ip in int_phrases:
        if ip in main_text:
            return "interview", f"Interview invitation detected: '{ip}'"

    # 4. OFFER EVALUATION
    offer_phrases = [
        "pleased to offer you", "formal offer of employment", "offer letter",
        "job offer", "extend an offer", "offre d'emploi", "proposition d'embauche"
    ]
    for op in offer_phrases:
        if op in main_text:
            return "offer", f"Offer indicator detected: '{op}'"

    # 5. REVIEW / UNDER REVIEW EVALUATION
    rev_phrases = [
        "received your email", "received your application", "thank you for your application",
        "thank you for your interest", "will review your application", "team will review",
        "under review", "in review", "currently reviewing", "will be in touch shortly",
        "will contact you shortly", "bien reçu votre candidature", "en cours d'examen",
        "accusons réception", "étudions votre candidature"
    ]
    for rp in rev_phrases:
        if rp in main_text:
            return "review", f"Application under review indicator: '{rp}'"

    # 6. AUTOMATIC / OUT OF OFFICE
    if "automatic reply" in subj_lower or "out of office" in subj_lower or "autoreply" in subj_lower:
        return "auto_reply", "Automatic out of office reply"

    return None, "General correspondence"

def sync_recruiter_replies(db: Session, user_id: int, max_messages: int = 150) -> Dict[str, Any]:
    """
    Scans incoming emails in the user's Gmail inbox, identifies responses to job applications,
    classifies the intent (Rejection, Review, Interview, Offer), and updates the corresponding
    Application record in the Tracker.
    """
    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == user_id).first()
    if not settings or not settings.smtp_user or not settings.smtp_password:
        raise ValueError("Gmail credentials not configured. Please enter your Gmail address and App Password in Settings.")

    clean_pwd = ''.join(settings.smtp_password.split())

    try:
        mail = imaplib.IMAP4_SSL(
            settings.smtp_host.replace("smtp.", "imap.") if "smtp." in settings.smtp_host else "imap.gmail.com",
            993, timeout=25
        )
        mail.login(settings.smtp_user, clean_pwd)
    except Exception as e:
        raise ValueError(f"Gmail IMAP connection failed: {str(e)}. Ensure IMAP is enabled in your Gmail settings.")

    try:
        mail.select('INBOX')

        search_queries = [
            '(SUBJECT "Application")',
            '(SUBJECT "Candidature")',
            '(SUBJECT "Interview")',
            '(SUBJECT "Entretien")',
            '(SUBJECT "Careers")',
            '(SUBJECT "Meeting")',
            '(SUBJECT "Invitation")',
            '(SUBJECT "Google Meet")',
            '(TEXT "meet.google.com")',
            '(TEXT "Google Meet")',
        ]

        candidate_ids = set()
        for q in search_queries:
            try:
                st, data = mail.search(None, q)
                if st == 'OK' and data and data[0]:
                    candidate_ids.update(data[0].split())
            except Exception:
                pass

        # Also search recent unread or recent messages in INBOX
        try:
            st, data = mail.search(None, 'ALL')
            if st == 'OK' and data and data[0]:
                candidate_ids.update(data[0].split()[-60:])
        except Exception:
            pass

        if not candidate_ids:
            mail.logout()
            return {
                "scanned_messages": 0,
                "matched_applications": 0,
                "updated_applications": 0,
                "breakdown": { "rejected": 0, "review": 0, "interview": 0, "offer": 0, "auto_reply": 0 },
                "updates": []
            }

        # Pick recent messages up to max_messages
        sorted_mids = sorted(list(candidate_ids), key=lambda x: int(x))[-max_messages:]
        scanned_count = len(sorted_mids)

        user_apps = db.query(models.Application).filter(models.Application.user_id == user_id).all()
        user_logs = db.query(models.EmailLog).filter(models.EmailLog.user_id == user_id).all()

        matched_app_ids = set()
        updated_apps = []
        breakdown = { "rejected": 0, "review": 0, "interview": 0, "offer": 0, "auto_reply": 0 }

        # Process messages newest first
        for mid in reversed(sorted_mids):
            try:
                fetch_res, mdata = mail.fetch(mid, '(RFC822)')
                if fetch_res != 'OK' or not mdata or not mdata[0]:
                    continue

                msg = email.message_from_bytes(mdata[0][1])
                subj = decode_mime_words(msg.get('Subject', ''))
                from_h = decode_mime_words(msg.get('From', ''))
                date_h = msg.get('Date', '')

                # Skip system daemons / bounces
                if any(d in from_h.lower() for d in ['mailer-daemon', 'postmaster', 'bounce@']):
                    continue

                # Skip known newsletters / irrelevant domains, EXCEPT calendar or meeting invitations
                is_calendar_or_meeting = bool(
                    'calendar' in from_h.lower() or 'calendar' in subj.lower() or
                    'agenda' in subj.lower() or 'meeting' in subj.lower() or
                    'invitation' in subj.lower() or 'entretien' in subj.lower()
                )
                if not is_calendar_or_meeting and any(ign in from_h.lower() for ign in IGNORED_DOMAINS):
                    continue

                m_from_em = re.search(r'<?([a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+))>?', from_h)
                from_email = m_from_em.group(1).lower() if m_from_em else ""
                from_domain = m_from_em.group(2).lower() if m_from_em else ""

                # Extract plain text / html text / calendar
                body = ""
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype in ('text/plain', 'text/html', 'text/calendar'):
                        p = part.get_payload(decode=True)
                        if p:
                            t = p.decode('utf-8', errors='replace')
                            if ctype == 'text/html':
                                soup = BeautifulSoup(t, 'html.parser')
                                t = soup.get_text(separator=' ')
                            body += t + "\n"

                clean_subj = re.sub(r'^(?:re|fwd|fw|sv|vs|antw|aw|automatic reply):\s*', '', subj, flags=re.I).strip()
                clean_subj = re.sub(r'^\[(?:external|externe)\]\s*', '', clean_subj, flags=re.I).strip()

                reply_to_h = decode_mime_words(msg.get('Reply-To', ''))
                m_reply_em = re.search(r'<?([a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+))>?', reply_to_h)
                reply_email = m_reply_em.group(1).lower() if m_reply_em else ""

                # Look for organizer in body or .ics if it's a calendar invite (e.g. dev@enclavia.ai - Organisateur)
                m_org_body = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\s*-\s*(?:Organisateur|Organizer)', body, re.I) or \
                             re.search(r'(?:Organisateur|Organizer):\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', body, re.I)
                organizer_email = m_org_body.group(1).lower() if m_org_body else ""

                candidate_recruiter_emails = [
                    e for e in [from_email, reply_email, organizer_email]
                    if e and not any(ign in e for ign in ['google.com', 'googlemail.com', 'mailer-daemon', 'postmaster'])
                ]

                matched_app = None
                match_note = ""

                # Strategy 0: Direct Match against EmailLog recipient email (Highest Confidence)
                for cand_em in candidate_recruiter_emails:
                    for l in user_logs:
                        if l.to_email and l.to_email.strip().lower() == cand_em.strip().lower():
                            if l.application:
                                matched_app = l.application
                                match_note = f"Direct Recruiter Email Match ({cand_em})"
                                break
                    if matched_app:
                        break

                # Strategy 0.5: Direct Match against non-generic domain in EmailLog
                if not matched_app:
                    cand_domains = [
                        e.split('@')[-1].lower() for e in candidate_recruiter_emails
                        if '@' in e and e.split('@')[-1].lower() not in ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'icloud.com'] and e.split('@')[-1].lower() not in ATS_DOMAINS
                    ]
                    for cd in cand_domains:
                        for l in user_logs:
                            if l.to_email and cd in l.to_email.lower():
                                if l.application:
                                    matched_app = l.application
                                    match_note = f"Direct Recruiter Domain Match ({cd})"
                                    break
                        if matched_app:
                            break

                # Strategy 1: Match by EmailLog (Subject + Domain/Company match)
                if not matched_app and clean_subj:
                    for l in user_logs:
                        if not l.subject: continue
                        clean_log_subj = re.sub(r'^(?:re|fwd|fw):\s*', '', l.subject, flags=re.I).strip()
                        if clean_subj.lower() == clean_log_subj.lower() or clean_subj.lower() in clean_log_subj.lower():
                            log_domain = l.to_email.split('@')[-1].lower() if '@' in l.to_email else ""
                            app = l.application
                            if app:
                                comp_name = app.company.lower() if app.company else ""
                                if from_domain and log_domain and from_domain == log_domain:
                                    matched_app = app
                                    match_note = f"EmailLog Exact Domain Match ({from_domain})"
                                    break
                                elif comp_name and (comp_name in from_h.lower() or comp_name in body.lower()):
                                    matched_app = app
                                    match_note = f"EmailLog Company Match ({comp_name})"
                                    break
                                elif from_domain in ATS_DOMAINS and comp_name in subj.lower():
                                    matched_app = app
                                    match_note = f"ATS Email ({from_domain}) Company Match ({comp_name})"
                                    break

                # Strategy 2: Direct Company & Title match in subject
                if not matched_app:
                    for a in user_apps:
                        if not a.title or not a.company: continue
                        if a.company.lower() in clean_subj.lower() or a.company.lower() in from_h.lower():
                            if a.title.lower() in clean_subj.lower() or clean_subj.lower() in a.title.lower():
                                matched_app = a
                                match_note = f"Direct Title & Company Match ({a.company})"
                                break

                # Strategy 3: Domain match in Application notes
                if not matched_app and from_domain and from_domain not in ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com'] and from_domain not in ATS_DOMAINS:
                    for a in user_apps:
                        if a.notes and from_domain in a.notes.lower():
                            matched_app = a
                            match_note = f"App Notes Domain Match ({from_domain})"
                            break

                if not matched_app:
                    continue

                matched_app_ids.add(matched_app.id)

                # Classify Intent
                new_status, intent_reason = classify_email_intent(body, subj)

                # Extract clean snippet
                lines = [l.strip() for l in body.split('\n') if l.strip() and not l.strip().startswith('>') and not l.strip().startswith('-----')]
                snippet = " ".join(lines[:3])[:220]

                # Determine if status should update
                should_update_status = False
                old_status = matched_app.status

                if new_status == "rejected":
                    breakdown["rejected"] += 1
                    if matched_app.status != "rejected":
                        matched_app.status = "rejected"
                        should_update_status = True
                elif new_status == "interview":
                    breakdown["interview"] += 1
                    if matched_app.status not in ("interview", "offer", "accepted"):
                        matched_app.status = "interview"
                        should_update_status = True
                elif new_status == "offer":
                    breakdown["offer"] += 1
                    if matched_app.status != "offer":
                        matched_app.status = "offer"
                        should_update_status = True
                elif new_status == "review":
                    breakdown["review"] += 1
                    if matched_app.status == "applied" or ("Official website" in intent_reason and matched_app.status == "interview"):
                        matched_app.status = "review"
                        should_update_status = True
                elif new_status == "auto_reply":
                    breakdown["auto_reply"] += 1

                # Append audit note if not already recorded (deduplicate using snippet core)
                timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                existing_notes = matched_app.notes or ""
                snippet_core = snippet[:40].strip()
                portal_url = extract_portal_url(body, matched_app.url)
                meet_url = extract_meeting_link(body) or extract_meeting_link(subj)
                link_text = f" Portal / Position Link: {portal_url}." if portal_url else ""
                meet_text = f" 📹 Google Meet Link: {meet_url}." if meet_url else ""

                if snippet_core and snippet_core not in existing_notes and new_status:
                    note_entry = f"\n[{timestamp_str}] 📥 Recruiter Reply: Status -> '{matched_app.status}'.{meet_text}{link_text} From: {from_h}. \"{snippet}\""
                    matched_app.notes = existing_notes + note_entry

                # Save full recruiter response in EmailLog for complete conversation thread display
                if new_status:
                    existing_reply_log = db.query(models.EmailLog).filter(
                        models.EmailLog.application_id == matched_app.id,
                        models.EmailLog.template_type == "recruiter_reply",
                        models.EmailLog.subject == subj
                    ).first()
                    if not existing_reply_log:
                        clean_lines = [l for l in body.split('\n') if not l.strip().startswith('-----Original Message-----')]
                        full_clean_body = "\n".join(clean_lines).strip()
                        reply_log = models.EmailLog(
                            user_id=user_id,
                            application_id=matched_app.id,
                            to_email=from_email or from_h,
                            to_name=from_h,
                            subject=subj,
                            body=full_clean_body or snippet,
                            template_type="recruiter_reply",
                            status=matched_app.status,
                            sent_at=datetime.utcnow()
                        )
                        db.add(reply_log)

                if should_update_status:
                    updated_apps.append({
                        "app_id": matched_app.id,
                        "company": matched_app.company,
                        "title": matched_app.title,
                        "old_status": old_status,
                        "new_status": matched_app.status,
                        "from": from_h,
                        "reason": intent_reason,
                        "snippet": snippet,
                        "portal_url": portal_url,
                        "meet_url": meet_url
                    })

            except Exception as fe:
                print(f"[ReplyAnalyzer] Message processing error {mid}: {fe}")

        db.commit()
        mail.logout()

        return {
            "scanned_messages": scanned_count,
            "matched_applications": len(matched_app_ids),
            "updated_applications": len(updated_apps),
            "breakdown": breakdown,
            "updates": updated_apps
        }

    except Exception as e:
        try:
            mail.logout()
        except Exception:
            pass
        raise e
