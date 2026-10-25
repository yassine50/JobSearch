import imaplib
import email
from email.header import decode_header
import re
import html
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
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

def parse_bounce_message(raw_bytes: bytes, db_session: Optional[Session] = None, user_id: Optional[int] = None, user_email: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Parses bounce, NDR (Non-Delivery Report), and delivery failure messages across:
    - Office 365 / Outlook ("Your message to ... couldn't be delivered", "wasn't found at")
    - Microsoft Exchange NDR ("Delivery has failed to these recipients or groups:")
    - Postfix / Sendmail ("The mail system <email>:", "permanent fatal errors")
    - French Google Mail Delivery Subsystem ("Message bloqué", "Adresse introuvable", "Impossible de distribuer votre message")
    - Standard RFC 3464 DSN headers (Final-Recipient, Original-Recipient)
    - Auto-reply bounce notifications (e.g. bounce@company.com with inactive account notice)
    """
    try:
        msg = email.message_from_bytes(raw_bytes)
        subj = decode_mime_words(msg.get('Subject', ''))
        from_header = decode_mime_words(msg.get('From', ''))

        # Accuracy gate: only genuine delivery-failure reports may blacklist an address
        fh, sl = from_header.lower(), subj.lower()
        is_report = msg.get_content_type() == 'multipart/report' or any(
            p.get_content_type() == 'message/delivery-status' for p in msg.walk())
        is_daemon = any(d in fh for d in ['mailer-daemon', 'postmaster', 'mail delivery'])
        bounce_subject = any(s in sl for s in [
            'undeliverable', 'undelivered', 'delivery status notification', 'delivery failure',
            'failure notice', 'returned mail', 'address not found', 'message bloqué', 'adresse introuvable',
            'non remis', 'non distribuable', 'unzustellbar', 'mail delivery failed', 'delivery has failed'])
        is_inactive_autoreply = 'bounce' in fh and 'no longer' in (str(msg.get_payload(decode=False))[:4000]).lower()
        if not (is_report or is_daemon or bounce_subject or is_inactive_autoreply):
            return None

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ('text/plain', 'text/html', 'message/delivery-status', 'message/rfc822-headers', 'message/rfc822'):
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode('utf-8', errors='replace') + "\n"
                    except Exception:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='replace')

        # Clean HTML tags and decode HTML entities for reliable regex matching
        clean_text = html.unescape(body)
        # Normalize all Unicode quotes and apostrophes to standard ASCII '
        clean_text = re.sub(r'[\u2018\u2019\u201a\u201b\u2032\u2035`´]', "'", clean_text)
        # Strip all HTML tags
        clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        body_lower = clean_text.lower()

        target_email = None
        reason = None

        # 1. English Google Mail: "Your message wasn't delivered to <email> because the address couldn't be found" (User's Screenshot 1)
        m_en_google = re.search(r"(?:your message wasn'?t delivered to|message wasn'?t delivered to|wasn'?t delivered to|couldn'?t be delivered to|delivery to)\s+<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?", clean_text, re.I)
        if m_en_google:
            target_email = m_en_google.group(1).strip()
            if "couldn't be found" in body_lower or "unable to receive mail" in body_lower or "address not found" in body_lower or "address couldn't be found" in body_lower:
                reason = "Adresse introuvable (Address not found / 550)"
            elif "blocked" in body_lower or "denied" in body_lower or "rejected" in body_lower:
                reason = "Message bloqué / Access Denied"
            else:
                reason = "Adresse introuvable (Google Delivery Failure)"

        # 2. French Google Mail: "Votre message à <email> a été bloqué" (User's Screenshot 2)
        if not target_email:
            m_fr1 = re.search(r"(?:votre message [aà]|message [aà]|impossible d'?envoyer [aà]|distribution [aà])\s+<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?\s+a [eé]t[eé] bloqu[eé]", clean_text, re.I)
            if m_fr1:
                target_email = m_fr1.group(1).strip()
                reason = "Message bloqué (550 5.4.1 Recipient address rejected: Access denied)"

        # 2b. French Google Mail: "Votre message n'est pas parvenu à <email>" / "Impossible de distribuer..."
        if not target_email:
            m_fr2 = re.search(r"(?:votre message n'?est pas parvenu [aà]|impossible de distribuer votre message [aà]|un probl[èe]me(?:\s+temporaire)?\s+est survenu lors de la distribution de votre message [aà]|distribution de votre message [aà])\s+<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?", clean_text, re.I)
            if m_fr2:
                target_email = m_fr2.group(1).strip()
                if "introuvable" in body_lower or "inconnu" in body_lower or "not found" in body_lower:
                    reason = "Adresse introuvable"
                elif "bloqu" in body_lower or "access denied" in body_lower or "rejected" in body_lower:
                    reason = "Message bloqué"
                else:
                    reason = "Message non distribué"

        # 3. Remote Server 550 Rejection: "550 5.4.1 Recipient address rejected: Access denied" / "550 5.1.1 User unknown"
        if not target_email:
            m_rej = re.search(r"550\s+5\.[0-9]\.[0-9]+.*?(?:Recipient address rejected|User unknown|Address rejected|Access denied|does not exist).*?(?:<([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>|([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+))", clean_text, re.I)
            if m_rej:
                target_email = (m_rej.group(1) or m_rej.group(2)).strip()
                reason = "Message bloqué (550 Recipient address rejected)"

        # 4. Office 365 NDR: Your message to <email> couldn't be delivered.
        if not target_email:
            m_o365 = re.search(r"Your message to\s+<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?\s+couldn'?t be delivered", clean_text, re.I)
            if m_o365:
                target_email = m_o365.group(1).strip()
                reason = "Adresse introuvable (Office 365)"

        # 4b. Office 365: <user> wasn't found at <domain>.
        if not target_email:
            m_nf = re.search(r"([a-zA-Z0-9_.+-]+)\s+wasn'?t found at\s+([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", clean_text, re.I)
            if m_nf:
                target_email = f"{m_nf.group(1).strip()}@{m_nf.group(2).strip()}"
                reason = "Adresse introuvable (Office 365)"

        # 5. Microsoft Exchange / Postmaster NDR: Delivery has failed to these recipients or groups:
        if not target_email:
            idx = body_lower.find("delivery has failed to these recipients or groups")
            if idx != -1:
                snippet = clean_text[idx:idx+600]
                m_em = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", snippet)
                if m_em:
                    target_email = m_em.group(1).strip()
                    reason = "Adresse introuvable (Exchange NDR)"

        # 6. Postfix / Unix Mail System: The mail system <email>:
        if not target_email:
            m_pfx = re.search(r"The mail system\s*<([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>:", clean_text, re.I)
            if m_pfx:
                target_email = m_pfx.group(1).strip()
                reason = "Undelivered Mail (Postfix)"

        # 7. Sendmail / Permanent Fatal Errors:
        if not target_email:
            m_fatal = re.search(r"The following addresses had permanent fatal errors[^\n]*\s*<([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>", clean_text, re.I)
            if m_fatal:
                target_email = m_fatal.group(1).strip()
                reason = "Message bloqué / Access Denied (550)"

        # 8. Standard RFC 3464 / RFC 822 DSN headers
        if not target_email:
            m_dsn = re.search(r"(?:Final-Recipient|Original-Recipient):\s*rfc822;\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", body, re.I)
            if m_dsn:
                target_email = m_dsn.group(1).strip()
                reason = "Delivery Failure (DSN)"

        # 9. Mailer-daemon general extraction: if from mailer-daemon / googlemail and has bounce indicators
        is_daemon_bounce = any(d in from_header.lower() for d in ['mailer-daemon', 'postmaster', 'bounce@', 'googlemail.com']) or \
                           any(s in subj.lower() for s in ['delivery status', 'undeliverable', 'failure notice', 'returned mail', 'message bloqué', 'address not found'])
        if not target_email and is_daemon_bounce:
            all_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
            for em in all_emails:
                em_clean = em.lower().strip().rstrip('.')
                if user_email and em_clean == user_email.lower().strip():
                    continue
                if any(ign in em_clean for ign in ['mailer-daemon', 'postmaster', 'googlemail.com', 'google.com', 'bounce', 'noreply', 'no-reply']):
                    continue
                target_email = em_clean
                reason = "Message bloqué / Adresse introuvable"
                break

        # 10. Auto-reply bounce / Inactive account lookup via EmailLog
        if not target_email and db_session and user_id and ("does not appear to be active" in body_lower or "no longer be working at" in body_lower or "bounce" in from_header.lower()):
            clean_subj = re.sub(r'^(?:re|fwd|undeliverable):\s*', '', subj, flags=re.I).strip()
            if clean_subj:
                match_log = db_session.query(models.EmailLog).filter(
                    models.EmailLog.user_id == user_id,
                    models.EmailLog.subject.ilike(f"%{clean_subj}%")
                ).first()
                if match_log:
                    target_email = match_log.to_email
                    reason = "Adresse introuvable (Compte Inactif / Auto-Reply)"

        # Clean, validate, and sanitize target_email
        if target_email and "@" in target_email:
            target_email = target_email.lower().strip().rstrip('.')
            # Never blacklist sender's own email address
            if user_email and target_email == user_email.lower().strip():
                return None
            # Never blacklist daemon addresses
            if target_email.startswith("postmaster@") or target_email.startswith("mailer-daemon@") or target_email.startswith("bounce@"):
                return None
            
            # Default reason fallback if not set
            if not reason:
                if "bloqué" in body_lower or "message blocked" in body_lower:
                    reason = "Message bloqué"
                elif "adresse introuvable" in body_lower or "address not found" in body_lower or "recipientnotfound" in body_lower:
                    reason = "Adresse introuvable"
                else:
                    reason = "Bounced / Undeliverable"

            return {
                "target_email": target_email,
                "reason": reason,
                "subject": subj
            }
        return None
    except Exception as e:
        print(f"[BounceCleaner] Parsing error: {e}")
        return None

def find_sent_folder(mail: imaplib.IMAP4_SSL) -> Optional[str]:
    """Finds the user's Gmail Sent mailbox dynamically across languages (English, French, etc.)."""
    try:
        status, folders = mail.list()
        if status != 'OK' or not folders:
            return None
        for f in folders:
            f_str = f.decode(errors='replace')
            if r'\Sent' in f_str or r'\sent' in f_str:
                m = re.search(r'\"([^\"]+)\"$', f_str)
                if m:
                    return m.group(1)
                parts = f_str.split(' "/" ')
                if len(parts) > 1:
                    return parts[-1].strip('\"')
        for candidate in ['[Gmail]/Messages envoy&AOk-s', '[Gmail]/Sent Mail', 'Sent', 'Sent Messages', '[Gmail]/Sent']:
            try:
                st, _ = mail.select(f'"{candidate}"', readonly=True)
                if st == 'OK':
                    return candidate
            except Exception:
                pass
    except Exception as e:
        print(f"[BounceCleaner] find_sent_folder error: {e}")
    return None

def find_trash_folder(mail: imaplib.IMAP4_SSL) -> Optional[str]:
    """Finds the user's Gmail Trash / Corbeille folder dynamically across languages."""
    try:
        status, folders = mail.list()
        if status != 'OK' or not folders:
            return None
        for f in folders:
            f_str = f.decode(errors='replace')
            if r'\Trash' in f_str or r'\trash' in f_str or r'\Bin' in f_str:
                m = re.search(r'\"([^\"]+)\"$', f_str)
                if m:
                    return m.group(1)
                parts = f_str.split(' "/" ')
                if len(parts) > 1:
                    return parts[-1].strip('\"')
        for candidate in ['[Gmail]/Corbeille', '[Gmail]/Trash', '[Gmail]/Bin', '[Gmail]/Messages supprim&AOk-s', 'Trash', 'Corbeille']:
            try:
                st, _ = mail.select(f'"{candidate}"', readonly=True)
                if st == 'OK':
                    return candidate
            except Exception:
                pass
    except Exception as e:
        print(f"[BounceCleaner] find_trash_folder error: {e}")
    return None

def move_to_trash_and_expunge(mail: imaplib.IMAP4_SSL, msg_ids: List[Any], trash_folder: Optional[str] = None) -> int:
    """
    In Gmail IMAP, setting \\Deleted alone DOES NOT remove messages from Sent Mail or Inbox!
    To actually remove messages from Sent and Inbox, they MUST be copied/moved to Trash (Corbeille).
    This function copies the messages to Trash, sets \\Deleted on the source folder, and expunges.
    """
    if not msg_ids:
        return 0
    if not trash_folder:
        trash_folder = find_trash_folder(mail)

    count = 0
    clean_ids = []
    for mid in msg_ids:
        mid_str = mid.decode() if isinstance(mid, bytes) else str(mid)
        if mid_str:
            clean_ids.append(mid_str)

    if not clean_ids:
        return 0

    target_box = f'"{trash_folder}"' if (trash_folder and not trash_folder.startswith('"')) else trash_folder

    # High-speed batch copy and delete in chunks of 50
    chunk_size = 50
    count = 0
    for i in range(0, len(clean_ids), chunk_size):
        chunk = clean_ids[i:i+chunk_size]
        id_seq = ','.join(chunk)
        if target_box:
            try:
                mail.copy(id_seq, target_box)
            except Exception:
                for single_id in chunk:
                    try:
                        mail.copy(single_id, target_box)
                    except Exception:
                        pass
        try:
            mail.store(id_seq, '+FLAGS', r'(\Deleted)')
            count += len(chunk)
        except Exception:
            for single_id in chunk:
                try:
                    mail.store(single_id, '+FLAGS', r'(\Deleted)')
                    count += 1
                except Exception:
                    pass

    try:
        mail.expunge()
    except Exception as ee:
        print(f"[BounceCleaner] Expunge error: {ee}")

    return count

def purge_sent_bounced_messages(mail: imaplib.IMAP4_SSL, blacklisted_emails: Set[str], trash_folder: Optional[str] = None) -> int:
    """
    Searches the user's Gmail Sent mailbox for any messages dispatched to blacklisted / bounced
    email addresses ("Message bloqué" or "Adresse introuvable") and removes them completely.
    """
    if not blacklisted_emails:
        return 0
    sent_folder = find_sent_folder(mail)
    if not sent_folder:
        return 0

    try:
        st, _ = mail.select(f'"{sent_folder}"')
        if st != 'OK':
            return 0

        if not trash_folder:
            trash_folder = find_trash_folder(mail)

        bl_list = [e.strip().lower() for e in blacklisted_emails if e and "@" in e]
        if not bl_list:
            return 0

        del_ids = set()

        # Strategy 1: High-speed Gmail X-GM-RAW search in chunks of 25
        chunk_size = 25
        for i in range(0, len(bl_list), chunk_size):
            chunk = bl_list[i:i + chunk_size]
            query = 'to:(' + ' OR '.join(chunk) + ')'
            try:
                st_q, data_q = mail.search(None, 'X-GM-RAW', f'"{query}"')
                if st_q == 'OK' and data_q and data_q[0]:
                    del_ids.update(data_q[0].split())
            except Exception:
                pass

        # Strategy 2: Targeted standard TO for priority addresses
        for addr in bl_list[:25]:
            addr_safe = addr.encode('ascii', errors='ignore').decode('ascii')
            try:
                st_s, data_s = mail.search(None, f'(TO "{addr_safe}")')
                if st_s == 'OK' and data_s and data_s[0]:
                    del_ids.update(data_s[0].split())
            except Exception:
                pass

        # Strategy 3: Priority domains (tide-forecast.com, rib-software.es)
        for dom in ['tide-forecast.com', 'rib-software.es']:
            try:
                st_d, data_d = mail.search(None, f'(TEXT "{dom}")')
                if st_d == 'OK' and data_d and data_d[0]:
                    del_ids.update(data_d[0].split())
            except Exception:
                pass

        if not del_ids:
            return 0

        id_list = list(del_ids)
        deleted_count = move_to_trash_and_expunge(mail, id_list, trash_folder)
        print(f"[BounceCleaner] Purged {deleted_count} blocked/bounced message(s) from Gmail Sent mailbox ({sent_folder}).")
        return deleted_count
    except Exception as e:
        print(f"[BounceCleaner] Error purging Sent folder: {e}")
        return 0

def sync_gmail_bounces(db: Session, user_id: int, delete_from_gmail: bool = True) -> Dict[str, Any]:
    """
    1. Connects to Gmail via IMAP using the user's stored App Password.
    2. Searches all delivery failure, NDR, and postmaster emails in INBOX.
    3. Extracts bounced target email addresses and reasons.
    4. Records each dead address in SQLite `email_blacklist` globally.
    5. Keeps sent history in EmailLog (status='bounced') and purges dead applications from Tracker.
    6. Deletes bounce notifications from INBOX (moves to Trash & expunges).
    7. Searches Gmail Sent mailbox for messages sent to blocked/dead addresses and deletes them from Sent!
    """
    settings = db.query(models.EmailSettings).filter(models.EmailSettings.user_id == user_id).first()
    if not settings or not settings.smtp_user or not settings.smtp_password:
        raise ValueError("Gmail credentials not configured. Please enter your Gmail address and App Password in Settings.")

    clean_pwd = ''.join(settings.smtp_password.split())

    try:
        mail = imaplib.IMAP4_SSL(settings.smtp_host.replace("smtp.", "imap.") if "smtp." in settings.smtp_host else "imap.gmail.com", 993, timeout=20)
        mail.login(settings.smtp_user, clean_pwd)
    except Exception as e:
        raise ValueError(f"Gmail IMAP connection failed: {str(e)}. Ensure IMAP is enabled in your Gmail settings.")

    try:
        mail.select('INBOX')
        search_queries = [
            '(FROM "mailer-daemon")',
            '(FROM "postmaster")',
            '(SUBJECT "Address not found")',
            '(SUBJECT "bloqu")',
            '(SUBJECT "Delivery Status Notification")',
            '(SUBJECT "Undeliverable")',
            '(SUBJECT "Delivery Status")',
            '(SUBJECT "Delivery Failure")',
            '(SUBJECT "Failure Notice")',
            '(SUBJECT "Undelivered")',
            '(SUBJECT "Returned mail")',
            '(SUBJECT "distribu")',
            '(TEXT "Address not found")',
            '(TEXT "bloqu")',
            '(TEXT "wasn\'t delivered to")',
            '(TEXT "couldn\'t be found")',
            '(TEXT "Recipient address rejected")',
            '(TEXT "550 5.4.1")',
            '(TEXT "550 5.1.1")',
            '(TEXT "tide-forecast.com")',
            '(TEXT "rib-software.es")',
            '(TEXT "distribution")',
        ]

        all_ids = set()
        for q in search_queries:
            try:
                q_safe = q.encode('ascii', errors='ignore').decode('ascii')
                status, data = mail.search(None, q_safe)
                if status == 'OK' and data and data[0]:
                    all_ids.update(data[0].split())
            except Exception as se:
                print(f"[BounceCleaner] Search query {q} failed: {se}")

        extracted_bounces = []
        gmail_del_ids = []
        blacklisted_added = 0
        tracker_purged_count = 0
        details = []

        trash_folder = find_trash_folder(mail)

        existing_bl = db.query(models.EmailBlacklist.email).all()
        full_blacklist = {r[0].strip().lower() for r in existing_bl if r[0]}
        # Destructive actions (marking logs bounced, deleting tracker apps, trashing Gmail Sent)
        # must only use THIS user's entries + system entries — never another user's manual entries.
        own_bl = db.query(models.EmailBlacklist.email).filter(
            (models.EmailBlacklist.user_id == user_id) | (models.EmailBlacklist.user_id.is_(None))
        ).all()
        destructive_blacklist = {r[0].strip().lower() for r in own_bl if r[0]}

        if all_ids:
            msg_ids = sorted(list(all_ids), key=lambda x: int(x))
            scanned_count = len(msg_ids)

            # Cap parsing to 30 most recent candidate messages for high speed
            target_ids = msg_ids[-30:] if len(msg_ids) > 30 else msg_ids

            for mid in reversed(target_ids):
                try:
                    fetch_res, mdata = mail.fetch(mid, '(RFC822)')
                    if fetch_res != 'OK' or not mdata or not mdata[0]:
                        continue

                    raw_body = mdata[0][1]
                    parsed = parse_bounce_message(raw_body, db_session=db, user_id=user_id, user_email=settings.smtp_user)
                    if parsed:
                        parsed["msg_id"] = mid.decode()
                        extracted_bounces.append(parsed)
                        gmail_del_ids.append(mid)
                    else:
                        raw_str = raw_body.decode(errors='ignore').lower() if isinstance(raw_body, bytes) else str(raw_body).lower()
                        msg_obj = email.message_from_bytes(raw_body)
                        from_hdr = decode_mime_words(msg_obj.get('From', '')).lower()
                        subj_hdr = decode_mime_words(msg_obj.get('Subject', '')).lower()
                        is_strict_daemon = any(d in from_hdr for d in ['mailer-daemon', 'postmaster']) and any(
                            s in subj_hdr or s in raw_str for s in [
                                'delivery status notification', 'undeliverable', 'address not found',
                                '550 5.4.1', '550 5.1.1', 'recipient address rejected',
                                'message bloqué', 'adresse introuvable', 'failure notice', 'returned mail'
                            ]
                        )
                        if is_strict_daemon:
                            gmail_del_ids.append(mid)
                except Exception as fe:
                    print(f"[BounceCleaner] Fetch error for msg {mid}: {fe}")

            for b in extracted_bounces:
                target = b["target_email"]
                reason = b["reason"]
                # Global platform-wide deduplication: check across all users
                existing = db.query(models.EmailBlacklist).filter(
                    models.EmailBlacklist.email == target
                ).first()

                if not existing:
                    bl_entry = models.EmailBlacklist(
                        user_id=user_id,
                        email=target,
                        reason=reason,
                        source="gmail_bounce",
                        created_at=datetime.utcnow()
                    )
                    db.add(bl_entry)
                    blacklisted_added += 1

                details.append({
                    "email": target,
                    "reason": reason,
                    "subject": b["subject"]
                })

            db.commit()
        else:
            scanned_count = 0

        # 2. Keep track of all sent emails and safely purge dead applications from Tracker
        all_blacklisted_emails = {b["target_email"] for b in extracted_bounces}
        full_blacklist = full_blacklist.union(all_blacklisted_emails)
        destructive_blacklist = destructive_blacklist.union(all_blacklisted_emails)

        # Mark only THIS user's OUTBOUND sent emails to dead addresses as 'bounced' (NEVER mark recruiter_reply as bounced)
        db.query(models.EmailLog).filter(
            models.EmailLog.user_id == user_id,
            models.EmailLog.to_email.in_(list(destructive_blacklist)),
            models.EmailLog.template_type != "recruiter_reply"
        ).update({"status": "bounced"}, synchronize_session=False)

        # Collect application IDs where ALL outbound emails bounced (and no valid recruiter reply exists)
        from .utils import extract_emails
        linked_log_app_ids = {
            r[0] for r in db.query(models.EmailLog.application_id).filter(
                models.EmailLog.user_id == user_id,
                models.EmailLog.application_id.isnot(None),
                models.EmailLog.to_email.in_(list(destructive_blacklist)),
                models.EmailLog.template_type != "recruiter_reply"
            ).all() if r[0]
        }

        apps_with_replies = {
            r[0] for r in db.query(models.EmailLog.application_id).filter(
                models.EmailLog.application_id.isnot(None),
                models.EmailLog.template_type == "recruiter_reply"
            ).all() if r[0]
        }

        # Find applications whose exact recipient email is blacklisted (never fuzzy domain/company substring!)
        user_apps = db.query(models.Application).filter(models.Application.user_id == user_id).all()
        for app in user_apps:
            if app.id in apps_with_replies or "📥 Recruiter Reply:" in (app.notes or ""):
                continue
            notes_emails = set(extract_emails(app.notes or ""))
            is_dead = (app.id in linked_log_app_ids) or bool(notes_emails and notes_emails.issubset(destructive_blacklist))
            if is_dead:
                db.query(models.EmailLog).filter(
                    models.EmailLog.application_id == app.id,
                    models.EmailLog.template_type != "recruiter_reply"
                ).update(
                    {"application_id": None, "status": "bounced"},
                    synchronize_session=False
                )
                db.delete(app)
                tracker_purged_count += 1

        db.commit()

        # Reload hunter blacklist cache for immediate global immunity
        try:
            import recruiter_hunter
            recruiter_hunter.load_blacklisted_emails(force_reload=True)
        except Exception:
            pass

        # 3. Batch delete bounce notifications from INBOX (la réception)
        deleted_gmail_count = 0
        if delete_from_gmail and gmail_del_ids:
            deleted_gmail_count = move_to_trash_and_expunge(mail, gmail_del_ids, trash_folder)
            print(f"[BounceCleaner] Purged {deleted_gmail_count} bounce notification(s) from INBOX (la réception).")

        # 4. Remove sent messages to blocked/dead addresses from Gmail Sent mailbox (la boîte mail envoyée)
        deleted_sent_count = 0
        if delete_from_gmail:
            deleted_sent_count = purge_sent_bounced_messages(mail, destructive_blacklist, trash_folder)

        # 5. Expunge Trash folder to permanently wipe deleted messages forever
        if trash_folder:
            try:
                st, _ = mail.select(f'"{trash_folder}"')
                if st == 'OK':
                    mail.expunge()
            except Exception:
                pass

        total_blacklisted = db.query(models.EmailBlacklist).count()

        mail.logout()

        return {
            "scanned_messages": scanned_count,
            "bounced_found": len(extracted_bounces),
            "blacklisted_added": blacklisted_added,
            "total_blacklisted": total_blacklisted,
            "tracker_purged": tracker_purged_count,
            "deleted_from_gmail": deleted_gmail_count,
            "deleted_from_sent": deleted_sent_count,
            "details": details[:50]
        }
    except Exception as e:
        try:
            mail.logout()
        except Exception:
            pass
        raise e

def get_blacklisted_emails(db: Session, user_id: Optional[int] = None) -> Set[str]:
    """Returns a set of lowercased blacklisted emails across the entire platform."""
    # All dead and blocked emails protect every user globally
    q = db.query(models.EmailBlacklist.email)
    return {row[0].strip().lower() for row in q.all() if row[0]}
