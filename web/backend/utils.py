"""
Shared Backend Utilities for Job Searcher API
Centralizes project root path resolution, email extraction, and safe blacklist purging.
"""

import os
import re
import sys
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger("jobsearcher.utils")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def ensure_project_root_on_path() -> str:
    """Ensures the repository root is on sys.path exactly once."""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    return PROJECT_ROOT


EMAIL_REGEX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)


def is_safe_public_url(url: str) -> bool:
    """
    SSRF guard: only allow http(s) URLs whose host resolves exclusively to public
    IP addresses (blocks localhost, private LANs, link-local cloud metadata 169.254.x.x, etc.).
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse
    try:
        parsed = urlparse((url or "").strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def extract_emails(text: str) -> List[str]:
    """Extracts unique lowercase email addresses from arbitrary text."""
    if not text:
        return []
    found = EMAIL_REGEX.findall(text)
    seen = set()
    result = []
    for em in found:
        clean = em.strip().lower().rstrip(".,;:)>]\"'")
        if "@" in clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def purge_blacklisted_applications(db: Session, user_id: Optional[int] = None) -> int:
    """
    Safely marks EmailLogs to blacklisted addresses as 'bounced' and removes
    dead applications that explicitly reference a blacklisted email address
    (without dangerous fuzzy company-name substring deletions).
    """
    from . import models

    bl_rows = db.query(models.EmailBlacklist.email).all()
    full_blacklist = {r[0].strip().lower() for r in bl_rows if r and r[0]}
    if not full_blacklist:
        return 0

    bl_list = list(full_blacklist)

    # Find linked application IDs before decoupling EmailLog
    linked_q = db.query(models.EmailLog.application_id).filter(
        models.EmailLog.application_id.isnot(None),
        models.EmailLog.to_email.in_(bl_list),
    )
    if user_id is not None:
        linked_q = linked_q.filter(models.EmailLog.user_id == user_id)
    linked_log_ids = {r[0] for r in linked_q.all() if r and r[0]}

    # Mark matching EmailLog rows as bounced
    update_q = db.query(models.EmailLog).filter(models.EmailLog.to_email.in_(bl_list))
    if user_id is not None:
        update_q = update_q.filter(models.EmailLog.user_id == user_id)
    update_q.update({"status": "bounced", "application_id": None}, synchronize_session=False)

    app_q = db.query(models.Application)
    if user_id is not None:
        app_q = app_q.filter(models.Application.user_id == user_id)

    purged_count = 0
    for app in app_q.all():
        notes_emails = set(extract_emails(app.notes or ""))
        url_lower = (app.url or "").lower()
        is_dead = (
            (app.id in linked_log_ids)
            or bool(notes_emails & full_blacklist)
            or any(bl in url_lower for bl in full_blacklist)
        )
        if is_dead:
            db.query(models.EmailLog).filter(models.EmailLog.application_id == app.id).update(
                {"application_id": None, "status": "bounced"},
                synchronize_session=False,
            )
            db.delete(app)
            purged_count += 1

    if purged_count > 0 or linked_log_ids:
        db.commit()

    return purged_count
