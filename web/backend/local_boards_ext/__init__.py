"""
Country local-board scraper plugins.

Every ``<region>.py`` module in this package exposes ``DIRECT_SCRAPERS`` (authoritative per-country
scraper lists) and ``BOARDS`` (board names per country). See ``_common.py`` for the plugin contract.
Modules are discovered automatically by :func:`load_plugins`; a broken module never breaks search.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger("jobsearcher.local_boards_ext")

_LOADED: Tuple[Dict[str, List[Callable]], Dict[str, List[str]]] = ({}, {})
_DONE = False


def load_plugins(force: bool = False) -> Tuple[Dict[str, List[Callable]], Dict[str, List[str]]]:
    """Return (scrapers_by_country, boards_by_country) merged from every plugin module."""
    global _LOADED, _DONE
    if _DONE and not force:
        return _LOADED
    scrapers: Dict[str, List[Callable]] = {}
    boards: Dict[str, List[str]] = {}
    for mod_info in pkgutil.iter_modules(__path__):
        name = mod_info.name
        if name.startswith("_") or name in ("selftest",):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as e:
            logger.warning(f"[local_boards_ext] plugin '{name}' failed to import: {e}")
            continue
        for country, fns in (getattr(mod, "DIRECT_SCRAPERS", {}) or {}).items():
            lst = scrapers.setdefault(country, [])
            for fn in fns or []:
                if fn not in lst:
                    lst.append(fn)
        for country, names in (getattr(mod, "BOARDS", {}) or {}).items():
            bl = boards.setdefault(country, [])
            for n in names or []:
                if n not in bl:
                    bl.append(n)
    _LOADED, _DONE = (scrapers, boards), True
    return _LOADED
