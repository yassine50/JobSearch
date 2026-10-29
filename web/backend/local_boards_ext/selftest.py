"""
Self-test for local-board plugins.

    cd /Users/yassine/Downloads/JobSpy-main
    python3 -m web.backend.local_boards_ext.selftest <module|all> [country,...] [query;query;...]

Example:
    python3 -m web.backend.local_boards_ext.selftest west_europe uk,ireland "flutter;python;data analyst;accountant"

For every scraper it prints raw rows, rows KEPT by the engine's relevance (>=20) + country verification,
latency, and contract violations (query injected into description, board name used as company,
non-absolute URL, duplicate URLs, missing country in location, too slow).
"""
from __future__ import annotations

import importlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from ..search_engine import (
    SINGLE_TECH_TO_ROLE, best_relevance, expand_queries, is_aggregator_or_non_posting,
    job_matches_selected_countries,
)


def _check(fn, country: str, query: str):
    variants = expand_queries(query, country, max_variants=2) or [query]
    first = query.split()[0].lower()
    core = first if first in SINGLE_TECH_TO_ROLE else query
    t = time.time()
    try:
        rows = fn(core) or []
        err = ""
    except Exception as e:  # contract violation: scrapers must never raise
        rows, err = [], f"RAISED {e!r}"
    dt = time.time() - t
    issues, kept, urls = [], [], set()
    if err:
        issues.append(err)
    if dt > 4.0:
        issues.append(f"slow {dt:.1f}s")
    for r in rows:
        u = r.get("job_url") or ""
        if not u.startswith("http"):
            issues.append(f"bad url {u[:60]}")
        if u in urls:
            issues.append(f"dup url {u[:60]}")
        urls.add(u)
        d = (r.get("description") or "").lower()
        if f"({core.lower()})" in d or d.endswith(core.lower()):
            issues.append("query injected into description")
        if is_aggregator_or_non_posting(r.get("title", ""), u, r.get("company", "")):
            continue
        ok_country = job_matches_selected_countries(
            {"title": r.get("title", ""), "location": r.get("location", ""), "url": u, "job_url": u}, [country])
        if not ok_country:
            issues.append(f"country mismatch: {r.get('location')!r}")
            continue
        rel = best_relevance(variants, r.get("title", ""), r.get("description", ""), r.get("company", ""))
        if rel >= 20:
            kept.append((rel, r))
    return rows, kept, dt, sorted(set(issues))[:6]


def main():
    mod_name = sys.argv[1] if len(sys.argv) > 1 else "all"
    countries_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    queries = (sys.argv[3] if len(sys.argv) > 3 else "flutter;python;data analyst").split(";")

    if mod_name == "all":
        from . import load_plugins
        registry = load_plugins(force=True)[0]
    else:
        registry = importlib.import_module(f"{__package__}.{mod_name}").DIRECT_SCRAPERS
    countries = [c.strip() for c in countries_arg.split(",") if c.strip()] or list(registry)

    jobs = [(c, fn, q) for c in countries for fn in registry.get(c, []) for q in queries]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda a: (a, _check(*a)), jobs))
    for (c, fn, q), (rows, kept, dt, issues) in results:
        flag = "OK " if kept else "-- "
        print(f"{flag}{c:14s} {fn.__name__:32s} q={q!r:18s} raw={len(rows):3d} kept={len(kept):3d} {dt:5.2f}s"
              + (f"  ISSUES: {issues}" if issues else ""))
        for rel, r in sorted(kept, key=lambda x: -x[0])[:2]:
            print(f"      [{rel:3d}] {r['title'][:55]} | {r.get('company','')[:25]} | {r.get('location','')[:35]} | "
                  f"{r.get('date_posted','')} | {r['job_url'][:70]}")


if __name__ == "__main__":
    main()
