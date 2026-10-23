
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .. import models
from ..auth import get_current_user
from ..utils import ensure_project_root_on_path
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

ensure_project_root_on_path()
router = APIRouter(prefix="/api/recruiter", tags=["recruiter"])

_RECRUITER_CACHE: dict = {}
_RECRUITER_LOCK = threading.Lock()
_RECRUITER_TTL_S = 1800  # 30 minutes


class RecruiterSearchRequest(BaseModel):
    job_title: str
    location: str = ""
    job_description: str
    required_skills: str = ""
    max_results: int = 30


@router.post("/search")
def recruiter_search(req: RecruiterSearchRequest,
                     current_user: models.User = Depends(get_current_user)):
    try:
        from ddgs import DDGS
        from cv_matcher import (_extract_skills, _skill_freq_in_text,
                                TECH_SKILLS, batch_candidate_match)

        jd_skills = _extract_skills(req.job_description, TECH_SKILLS)
        scored = sorted([(s, _skill_freq_in_text(req.job_description, s)) for s in jd_skills],
                        key=lambda x: (-x[1], x[0]))
        auto_skills = [s for s, _ in scored][:6]
        manual = [s.strip() for s in req.required_skills.split(",") if s.strip()]
        all_skills = list(dict.fromkeys(manual + auto_skills))

        t, l = req.job_title.strip(), req.location.strip()
        cache_key = f"{t.lower()}|{l.lower()}|{','.join(s.lower() for s in all_skills[:4])}|{req.max_results}"

        now = time.time()
        raw = None
        with _RECRUITER_LOCK:
            cached = _RECRUITER_CACHE.get(cache_key)
            if cached and (now - cached[0]) < _RECRUITER_TTL_S:
                raw = list(cached[1])

        if raw is None:
            base_q = f"site:linkedin.com/in/ {t}"
            if l:
                base_q += f" {l}"
            queries = [base_q]
            if all_skills:
                queries.append(base_q + " " + " ".join(f'"{s}"' for s in all_skills[:2]))
            if len(all_skills) >= 2:
                queries.append(base_q + " " + " ".join(f'"{s}"' for s in all_skills[1:3]))
            words = t.split()
            if len(words) > 1:
                rel_q = f"site:linkedin.com/in/ {chr(32).join(words[1:])}"
                if l:
                    rel_q += f" {l}"
                queries.append(rel_q)

            def _run_ddg(q_str: str):
                try:
                    return list(DDGS(verify=False).text(q_str, max_results=req.max_results))
                except Exception:
                    return []

            seen, raw = set(), []
            ex = ThreadPoolExecutor(max_workers=min(len(queries), 4))
            fut_map = {ex.submit(_run_ddg, q): idx for idx, q in enumerate(queries)}
            ordered_batches = [[] for _ in queries]
            try:
                for fut in as_completed(fut_map, timeout=6.5):
                    idx = fut_map[fut]
                    try:
                        ordered_batches[idx] = fut.result() or []
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                ex.shutdown(wait=False, cancel_futures=True)

            for batch in ordered_batches:
                for r in batch:
                    url = r.get("href", "")
                    if "linkedin.com/in/" in url and url not in seen:
                        seen.add(url)
                        raw.append(r)
                    if len(raw) >= req.max_results:
                        break
                if len(raw) >= req.max_results:
                    break

            if raw:
                with _RECRUITER_LOCK:
                    if len(_RECRUITER_CACHE) > 40:
                        _RECRUITER_CACHE.clear()
                    _RECRUITER_CACHE[cache_key] = (now, list(raw))

        candidates, meta = [], []
        for r in raw:
            ttl = r.get("title", "")
            url = r.get("href", "")
            snip = r.get("body", "")
            parts = ttl.split(" - ")
            name = parts[0].replace(" | LinkedIn", "").strip() if parts else "Unknown"
            headline = " - ".join(parts[1:]).strip() if len(parts) > 1 else ""
            candidates.append({"snippet": snip, "headline": headline})
            meta.append({"name": name, "headline": headline, "snippet": snip, "url": url})

        matches = batch_candidate_match(candidates, req.job_description, req.job_title, l, max_workers=8)
        rows = []
        for (score, bd), m in zip(matches, meta):
            rows.append({
                "score": score, "name": m["name"], "headline": m["headline"],
                "snippet": m["snippet"][:300], "url": m["url"],
                "matched_skills": bd.get("matched_tech", []),
                "missing_skills": bd.get("missing_tech", []),
                "required_skills": bd.get("required_skills", []),
                "available": bd.get("available", False),
                "seniority_gap": bd.get("seniority_gap", False),
                "breakdown": {k: v for k, v in bd.items() if k != "tips"},
                "tips": bd.get("tips", []),
            })
        rows.sort(key=lambda x: (-x["score"], x["name"]))
        return {"candidates": rows, "total": len(rows), "skills_used": all_skills[:4]}
    except Exception as e:
        raise HTTPException(500, str(e))
