"""
Date parsing for CV entries (English + French, many real-world formats).

Handles: "Dec 2024 – Present", "Sep, 2019 - Juin, 2022", "Sep/2019 - presnt", "09/2019 – 06/2022",
"From March 2022 to May 2022", "Août 2024 – Septembre 2024", "summer2021", "été 2023",
"2019 – current", "2017", "Févr 2022 - Mai 2022", "November , 2022 - Present", "(Jul/2021)".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

TODAY = date.today()

MONTHS = {
    # English
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # French
    "janv": 1, "janvier": 1, "fév": 2, "févr": 2, "fev": 2, "fevr": 2, "février": 2, "fevrier": 2,
    "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6, "juil": 7, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "déc": 12, "dec.": 12, "décembre": 12, "decembre": 12,
}
SEASONS = {"summer": 7, "été": 7, "ete": 7, "winter": 1, "hiver": 1, "spring": 4, "printemps": 4, "autumn": 10, "fall": 10, "automne": 10}

MONTH_EN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_FR = ["", "Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."]

_MONTH_ALT = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
_SEASON_ALT = "|".join(sorted((re.escape(s) for s in SEASONS), key=len, reverse=True))
PRESENT_RE = r"(?:present|presnt|pr[ée]sent|current|currently|now|today|ongoing|aujourd'?hui|actuel(?:lement)?|en cours|à ce jour|a ce jour)"

# A single point in time
_POINT = (
    rf"(?:(?:{_SEASON_ALT})\s*,?\s*(?:19|20)\d{{2}}"                    # summer 2021 / summer2021
    rf"|(?:{_MONTH_ALT})\.?\s*[,/\-]?\s*(?:19|20)\d{{2}}"                 # Mar 2022 / Sep, 2019 / Sep/2019
    rf"|(?:0?[1-9]|1[0-2])\s*[/.\-]\s*(?:19|20)\d{{2}}"                   # 09/2019
    rf"|(?:19|20)\d{{2}}\s*[/.\-]\s*(?:0?[1-9]|1[0-2])(?!\d)"             # 2019-09
    rf"|(?<![\d/])(?:19|20)\d{{2}}(?![\d/])"                              # 2019
    rf")"
)
_SEP = r"\s*(?:–|—|-|−|to|au|à|a|until|jusqu'?à|->|→|>|\|)\s*"
RANGE_RE = re.compile(
    rf"(?:(?:from|de|du|depuis|since)\s+)?(?P<start>{_POINT})(?:{_SEP}(?P<end>{_POINT}|{PRESENT_RE}))?",
    re.I,
)
DANGLING_FROM_RE = re.compile(rf"(?:from|de|du)\s+(?P<start>{_POINT}|(?:{_MONTH_ALT}))\s*(?:to|au|à|-|–)?\s*$", re.I)
LEADING_END_RE = re.compile(rf"^\s*(?:(?:to|au|à|-|–)\s+)?(?P<end>{_POINT}|{PRESENT_RE})\b", re.I)
SINCE_RE = re.compile(rf"(?:since|depuis)\s+(?P<start>{_POINT})", re.I)


@dataclass
class DatePoint:
    year: int
    month: Optional[int] = None
    present: bool = False

    def as_tuple(self) -> Tuple[int, int]:
        return (self.year, self.month or 6)


@dataclass
class DateSpan:
    start: Optional[DatePoint]
    end: Optional[DatePoint]
    raw: str = ""

    @property
    def is_present(self) -> bool:
        return bool(self.end and self.end.present)

    def months(self) -> int:
        if not self.start:
            return 0
        s = self.start
        e = self.end or self.start
        if e.present:
            e = DatePoint(TODAY.year, TODAY.month)
        sm = s.month or (1 if self.end and self.end is not self.start else 6)
        em = e.month or (12 if (self.end and not self.end.present and e.month is None) else 6)
        if self.end is None:  # single point: count as 1 month (or 3 for a season/year-only internship)
            return 3 if s.month is None else 1
        return max(1, (e.year - s.year) * 12 + (em - sm) + 1)

    def display(self, lang: str = "en") -> str:
        def fmt(p: Optional[DatePoint]) -> str:
            if p is None:
                return ""
            if p.present:
                return "Présent" if lang == "fr" else "Present"
            if p.month:
                return f"{(MONTH_FR if lang == 'fr' else MONTH_EN)[p.month]} {p.year}"
            return str(p.year)
        s, e = fmt(self.start), fmt(self.end)
        if s and e and s != e:
            return f"{s} – {e}"
        return s or e

    def sort_key(self) -> Tuple[int, int]:
        p = self.end or self.start
        if p is None:
            return (0, 0)
        if p.present:
            return (9999, 12)
        return p.as_tuple()


def _parse_point(txt: str) -> Optional[DatePoint]:
    t = (txt or "").strip().lower().replace(",", " ")
    if not t:
        return None
    if re.fullmatch(PRESENT_RE, t, re.I):
        return DatePoint(TODAY.year, TODAY.month, present=True)
    m = re.search(r"(19|20)\d{2}", t)
    if not m:
        return None
    year = int(m.group(0))
    month = None
    for name, num in sorted(SEASONS.items(), key=lambda kv: -len(kv[0])):
        if t.startswith(name):
            month = num
            break
    if month is None:
        mm = re.match(rf"({_MONTH_ALT})", t, re.I)
        if mm:
            month = MONTHS.get(mm.group(1).lower().rstrip("."))
    if month is None:
        mm = re.match(r"(0?[1-9]|1[0-2])\s*[/.\-]\s*(19|20)\d{2}", t)
        if mm:
            month = int(mm.group(1))
        else:
            mm = re.match(r"(19|20)\d{2}\s*[/.\-]\s*(0?[1-9]|1[0-2])$", t)
            if mm:
                month = int(mm.group(2))
    if year > TODAY.year + 6 or year < 1960:
        return None
    return DatePoint(year, month)


def find_date_span(text: str) -> Optional[Tuple[DateSpan, int, int]]:
    """Return the most complete date span in `text` with its (start, end) character offsets."""
    if not text:
        return None
    best = None
    for m in RANGE_RE.finditer(text):
        start = _parse_point(m.group("start"))
        if not start:
            continue
        end_txt = m.group("end")
        end = _parse_point(end_txt) if end_txt else None
        # Reject things like "2 mars 1934" street names or "5000 Monastir" — require plausible years
        span = DateSpan(start, end, m.group(0).strip())
        score = (2 if end else 1) + (1 if start.month else 0)
        if best is None or score > best[0]:
            best = (score, span, m.start(), m.end())
    if not best:
        return None
    return best[1], best[2], best[3]


def strip_dates(text: str) -> str:
    """Remove the date span (and dangling separators/brackets) from a header line."""
    found = find_date_span(text)
    if not found:
        return text.strip()
    _, a, b = found
    out = (text[:a] + " " + text[b:]).strip()
    out = re.sub(r"\(\s*\)|\[\s*\]", "", out)
    out = re.sub(r"\s*(?:\||–|—|-|:|,)\s*$", "", out)
    out = re.sub(r"^\s*(?:\||–|—|-|:|,)\s*", "", out)
    out = re.sub(r"\b(?:from|de|du|depuis|since|en)\s*$", "", out, flags=re.I).strip()
    return re.sub(r"\s{2,}", " ", out).strip(" |–—-,:")


def dangling_start(text: str) -> Optional[DatePoint]:
    m = DANGLING_FROM_RE.search(text or "")
    if not m:
        return None
    return _parse_point(m.group("start"))


def leading_end(text: str) -> Optional[Tuple[DatePoint, int]]:
    m = LEADING_END_RE.match(text or "")
    if not m:
        return None
    p = _parse_point(m.group("end"))
    return (p, m.end()) if p else None


def total_months(spans: List[DateSpan]) -> int:
    """Union of month intervals (overlaps counted once)."""
    intervals = []
    for s in spans:
        if not s or not s.start:
            continue
        sy, sm = s.start.year, s.start.month or 1
        e = s.end or s.start
        if e.present:
            ey, em = TODAY.year, TODAY.month
        else:
            ey, em = e.year, e.month or (12 if s.end else (sm + 2 if s.start.month is None else sm))
        a, b = sy * 12 + sm, ey * 12 + em
        if b < a:
            a, b = b, a
        intervals.append((a, b))
    intervals.sort()
    total, cur = 0, None
    for a, b in intervals:
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0] + 1
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        total += cur[1] - cur[0] + 1
    return total
