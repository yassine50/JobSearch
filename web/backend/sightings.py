"""
Repost / ghost-job tracking (career-ops detect-reposts + scan-history).

Every search records each posting under a company+title fingerprint. When the
same fingerprint later shows up under *new* URLs, or keeps showing up for
weeks, the job is flagged as a likely ghost / evergreen posting.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from . import models
from .search_engine import canonical_url

logger = logging.getLogger("jobsearcher.sightings")


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|sarl|sas|co|company|group)\b\.?", "", s)
    s = re.sub(r"\b(senior|sr|junior|jr|remote|hybrid|on-?site|contract|full[- ]?time|part[- ]?time)\b", "", s)
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def fingerprint(job: dict) -> str:
    c, t = _norm(job.get("company", "")), _norm(job.get("title", ""))
    return f"{c}|{t}" if c and t else ""


def record_and_annotate(db: Session, jobs: List[dict]) -> None:
    """Upsert sightings for this batch and annotate each job with repost info (in place)."""
    try:
        now = datetime.utcnow()
        fps = {}
        for j in jobs:
            fp = fingerprint(j)
            uk = canonical_url(j.get("url") or j.get("job_url_direct") or "")
            if fp and uk:
                fps.setdefault(fp, []).append((j, uk))
        if not fps:
            return
        existing = db.query(models.JobSighting).filter(models.JobSighting.fingerprint.in_(list(fps))).all()
        by_fp: Dict[str, List[models.JobSighting]] = {}
        for s in existing:
            by_fp.setdefault(s.fingerprint, []).append(s)

        for fp, items in fps.items():
            rows = by_fp.get(fp, [])
            by_url = {r.url_key: r for r in rows}
            for j, uk in items:
                r = by_url.get(uk)
                if r:
                    if (now - (r.last_seen or now)).total_seconds() > 3600:
                        r.times_seen = (r.times_seen or 1) + 1
                    r.last_seen = now
                else:
                    r = models.JobSighting(fingerprint=fp, url_key=uk, title=j.get("title"),
                                           company=j.get("company"), first_seen=now, last_seen=now)
                    db.add(r)
                    by_url[uk] = r
                    rows.append(r)
            first = min((r.first_seen or now) for r in rows)
            info = {"distinct_urls": len(by_url), "days_tracked": (now - first).days,
                    "first_seen": first.strftime("%Y-%m-%d")}
            for j, _ in items:
                j["sighting"] = info
                j["repost_count"] = max(0, info["distinct_urls"] - 1)
        db.commit()
    except Exception as e:
        logger.warning(f"[Sightings] skipped: {e}")
        db.rollback()


def lookup(db: Session, job: dict) -> dict:
    fp = fingerprint(job)
    if not fp:
        return {}
    rows = db.query(models.JobSighting).filter(models.JobSighting.fingerprint == fp).all()
    if not rows:
        return {}
    first = min(r.first_seen for r in rows if r.first_seen)
    return {"distinct_urls": len({r.url_key for r in rows}), "days_tracked": (datetime.utcnow() - first).days,
            "first_seen": first.strftime("%Y-%m-%d")}
