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
        host_low = parsed.hostname.strip().lower()
        if host_low in ("localhost", "0.0.0.0") or host_low.endswith((".local", ".internal", ".localhost")):
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


def safe_http_get(session, url: str, max_redirects: int = 5, **kwargs):
    """
    SSRF-safe HTTP GET wrapper that validates `is_safe_public_url` on the initial URL
    and on every 301/302/303/307/308 redirect hop before following it.
    """
    from urllib.parse import urljoin
    current_url = (url or "").strip()
    kwargs = dict(kwargs)
    kwargs["allow_redirects"] = False
    for _ in range(max_redirects + 1):
        if not is_safe_public_url(current_url):
            raise ValueError(f"Blocked unsafe or private URL: {current_url}")
        resp = session.get(current_url, **kwargs)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = (resp.headers.get("Location") or "").strip()
            if not loc:
                return resp
            current_url = urljoin(current_url, loc)
            continue
        resp.url = current_url
        return resp
    raise ValueError("Too many redirects")


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
    (scoped so user-created manual blacklist entries only affect their own account).
    """
    from sqlalchemy import or_
    from . import models

    bl_q = db.query(models.EmailBlacklist.email, models.EmailBlacklist.user_id, models.EmailBlacklist.source)
    if user_id is not None:
        bl_q = bl_q.filter(
            or_(
                models.EmailBlacklist.user_id == user_id,
                models.EmailBlacklist.user_id.is_(None),
                models.EmailBlacklist.source != "manual",
            )
        )
    bl_rows = bl_q.all()
    if not bl_rows:
        return 0

    global_blacklist = {
        r[0].strip().lower()
        for r in bl_rows
        if r and r[0] and (r[1] is None or (r[2] and r[2] != "manual"))
    }
    by_user_blacklist: dict[int, set[str]] = {}
    for em_val, uid_val, src_val in bl_rows:
        if em_val and uid_val is not None:
            by_user_blacklist.setdefault(uid_val, set()).add(em_val.strip().lower())

    effective_for_user = (
        global_blacklist | by_user_blacklist.get(user_id, set())
        if user_id is not None
        else global_blacklist
    )
    if not effective_for_user and not by_user_blacklist:
        return 0

    # Find linked application IDs before decoupling EmailLog
    linked_log_ids = set()
    if effective_for_user:
        linked_q = db.query(models.EmailLog.application_id).filter(
            models.EmailLog.application_id.isnot(None),
            models.EmailLog.to_email.in_(list(effective_for_user)),
        )
        if user_id is not None:
            linked_q = linked_q.filter(models.EmailLog.user_id == user_id)
        linked_log_ids.update(r[0] for r in linked_q.all() if r and r[0])

        # Mark matching EmailLog rows as bounced
        update_q = db.query(models.EmailLog).filter(models.EmailLog.to_email.in_(list(effective_for_user)))
        if user_id is not None:
            update_q = update_q.filter(models.EmailLog.user_id == user_id)
        update_q.update({"status": "bounced", "application_id": None}, synchronize_session=False)

    app_q = db.query(models.Application)
    if user_id is not None:
        app_q = app_q.filter(models.Application.user_id == user_id)

    purged_count = 0
    for app in app_q.all():
        user_bl = global_blacklist | by_user_blacklist.get(app.user_id, set())
        if not user_bl:
            continue
        notes_emails = set(extract_emails(app.notes or ""))
        url_lower = (app.url or "").lower()
        is_dead = (
            (app.id in linked_log_ids)
            or bool(notes_emails & user_bl)
            or any(bl in url_lower for bl in user_bl)
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


def get_active_cv(db: Session, user_id: int):
    """Returns the user's currently active CV persona (or most recent CV upload)."""
    from . import models
    active = (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id, models.CvUpload.is_active == True)
        .order_by(models.CvUpload.uploaded_at.desc())
        .first()
    )
    if active:
        return active
    return (
        db.query(models.CvUpload)
        .filter(models.CvUpload.user_id == user_id)
        .order_by(models.CvUpload.uploaded_at.desc())
        .first()
    )

