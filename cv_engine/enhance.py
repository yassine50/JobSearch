"""
Honest CV enhancement — the polish a senior recruiter applies before a CV goes out.

Rules (non-negotiable):
  • never invent employers, dates, metrics, skills or responsibilities;
  • only rephrase mechanically (tense, casing, typos, duplicated words, filler removal);
  • every change is recorded in `changes` so the user can see what was done.
"""
from __future__ import annotations

import copy
import re
from typing import Dict, List, Tuple

from .lexicon import (
    AMBIGUOUS_TECH, CATEGORY_ORDER, DOUBLE_WORD_RE, EN_OPENER_REWRITES, TECH,
    TECH_ALIAS, TYPOS, canonical_tech, tech_category,
)
from .parse import CV, Entry, tech_tokens

# Present → past for ended roles (first verb of a bullet only)
_IRREGULAR_PAST = {
    "build": "built", "lead": "led", "write": "wrote", "drive": "drove", "run": "ran", "make": "made",
    "take": "took", "get": "got", "set": "set", "cut": "cut", "put": "put", "teach": "taught",
    "think": "thought", "bring": "brought", "buy": "bought", "find": "found", "give": "gave",
    "keep": "kept", "begin": "began", "choose": "chose", "do": "did", "have": "had", "hold": "held",
    "send": "sent", "spend": "spent", "win": "won", "ship": "shipped", "plan": "planned", "own": "owned",
}
_REGULAR_VERBS = {
    "develop", "design", "implement", "create", "launch", "deliver", "optimize", "optimise", "improve",
    "reduce", "increase", "automate", "migrate", "integrate", "deploy", "maintain", "manage", "analyze",
    "analyse", "test", "debug", "host", "configure", "collaborate", "mentor", "coordinate", "organize",
    "ensure", "support", "conduct", "utilize", "use", "apply", "contribute", "participate", "resolve",
    "streamline", "establish", "architect", "engineer", "refactor", "document", "monitor", "research",
    "propose", "extract", "train", "publish", "release", "simplify", "showcase", "focus", "work", "help",
    "assist", "handle", "deliver", "review", "secure", "scale", "model", "prototype", "present",
}
_VERB_FIRST_RE = re.compile(r"^([A-Za-z]+)\b(\s+and\s+([A-Za-z]+)\b)?")

_FILLER_BULLET_RE = re.compile(
    r"^(?:proficient in|experience (?:with|in)|experienced in|skilled in|knowledge of|familiar with|"
    r"utili[sz]ed (?:skills in )?|technologies used|tools used|ma[iî]trise de|connaissances? en)\b",
    re.I,
)


def _past(verb: str) -> str:
    low = verb.lower()
    if low in _IRREGULAR_PAST:
        out = _IRREGULAR_PAST[low]
    elif low in _REGULAR_VERBS:
        if low.endswith("e"):
            out = low + "d"
        elif low.endswith("y") and low[-2:-1] not in "aeiou":
            out = low[:-1] + "ied"
        else:
            out = low + "ed"
    else:
        return verb
    return out.capitalize() if verb[:1].isupper() else out


def _case_like(src: str, repl: str) -> str:
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


class Enhancer:
    def __init__(self, cv: CV):
        self.cv = copy.deepcopy(cv)
        self.changes: List[Dict[str, str]] = []
        self.fr = cv.lang == "fr"

    def log(self, kind: str, before: str, after: str = "") -> None:
        if len(self.changes) < 200:
            self.changes.append({"type": kind, "before": before[:160], "after": after[:160]})

    # ── text-level fixes ──────────────────────────────────────────────────
    def fix_text(self, t: str, where: str = "") -> str:
        if not t:
            return t
        orig = t
        # typos (case preserving, whole words / phrases)
        for bad, good in TYPOS.items():
            if bad.lower() in t.lower():
                t = re.sub(rf"(?<![\w-]){re.escape(bad)}(?![\w-])", lambda m: _case_like(m.group(0), good), t, flags=re.I)
        # glued duplicates: "forfor", "thethe"
        t = re.sub(r"\b(for|the|and|of|to|de|la|le|et|des|in|on)\1\b", r"\1", t, flags=re.I)
        # repeated words: "Jquery Jquery", "for for"
        t = DOUBLE_WORD_RE.sub(lambda m: m.group(1), t)
        # spacing around punctuation
        t = re.sub(r"\s+([,.;:!?)])", r"\1", t)
        t = re.sub(r"([(])\s+", r"\1", t)
        t = re.sub(r",(?=[A-Za-zÀ-ÿ])", ", ", t)
        t = re.sub(r"\s{2,}", " ", t).strip()
        # canonical tech casing for unambiguous names written in prose
        t = self._tech_casing(t)
        if t != orig and where:
            self.log("typo_or_format", orig, t)
        return t

    _TECH_PROSE_RE = None

    def _tech_casing(self, t: str) -> str:
        if Enhancer._TECH_PROSE_RE is None:
            keys = [k for k in TECH_ALIAS if k not in AMBIGUOUS_TECH and len(k) > 2 and re.fullmatch(r"[\w.#+/ -]+", k)]
            keys.sort(key=len, reverse=True)
            Enhancer._TECH_PROSE_RE = re.compile(r"(?<![\w./-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w/-])", re.I)

        def repl(m):
            word = m.group(1)
            canon = TECH_ALIAS.get(word.lower())
            if not canon:
                return word
            # only fix casing / spelling variants of the same name; never expand abbreviations
            if re.sub(r"[\s.\-]", "", canon.lower()) == re.sub(r"[\s.\-]", "", word.lower()):
                return canon
            return word
        return Enhancer._TECH_PROSE_RE.sub(repl, t)

    # ── bullets ───────────────────────────────────────────────────────────
    def polish_bullet(self, b: str, ended: bool, entry: Entry) -> Tuple[str, List[str]]:
        """Return (bullet or '', techs_to_move_to_stack)."""
        t = self.fix_text(b.strip(" .;•-–"))
        if not t:
            return "", []
        moved: List[str] = []
        # filler "Proficient in Flutter, Dart…" bullets → move techs to the stack line
        if _FILLER_BULLET_RE.match(t):
            techs, left = tech_tokens(_FILLER_BULLET_RE.sub("", t))
            if techs and len([w for w in left if len(w) > 3]) <= 3:
                self.log("filler_bullet_moved_to_stack", t, ", ".join(techs))
                return "", techs
        # duplicate of the title / org, or vague two-word fragments ("Flesk tasks")
        tl = t.lower()
        if tl in {entry.title.lower(), entry.org.lower(), f"{entry.title} .".lower()}:
            self.log("removed_duplicate_bullet", t)
            return "", []
        m = re.fullmatch(r"(.{2,40}?)\s+(project|projet)", t, re.I)
        if m:
            new = f"Contribution au projet {m.group(1)}" if self.fr else f"Contributed to the {m.group(1)} project"
            self.log("rephrased_fragment", t, new)
            return new, []
        if re.fullmatch(r"\S+\s+(tasks?|tâches|missions?)", t, re.I):
            self.log("removed_vague_bullet", t)
            return "", []
        # first person
        t2 = re.sub(r"^(?:I|we)\s+(?:have\s+)?", "", t)
        t2 = re.sub(r"^(?:j'ai|nous avons)\s+", "", t2, flags=re.I)
        if t2 != t:
            self.log("removed_first_person", t, t2)
            t = t2[:1].upper() + t2[1:]
        if not self.fr:
            for pat, rep in EN_OPENER_REWRITES:
                if re.match(pat, t, re.I):
                    new = re.sub(pat, rep, t, count=1, flags=re.I)
                    if new != t:
                        self.log("action_verb", t, new)
                        t = new
                    break
            if ended:
                mv = _VERB_FIRST_RE.match(t)
                if mv:
                    v1, v2 = mv.group(1), mv.group(3)
                    p1 = _past(v1)
                    p2 = _past(v2) if v2 else None
                    # Also handle gerunds in the second verb ("Designed and developing" -> "Designed and developed")
                    if v2 and v2.lower().endswith("ing") and len(v2) > 4:
                        stem = v2[:-3]
                        p2 = _past(stem) if _past(stem) != stem else (_past(stem + "e") if _past(stem + "e") != stem + "e" else v2)
                    if p1 != v1 or (v2 and p2 != v2):
                        new = p1 + (f" and {p2.lower()}" if v2 and p2 else "") + t[mv.end():]
                        self.log("past_tense", t, new)
                        t = new
            # Grammar cleanups seen in real CVs
            t = re.sub(r"^Developed\s+of\s+(an?\b)", r"Developed \1", t)
            t = re.sub(r"\band\s+extracting\b", "and extracted", t)
            t = re.sub(r"\bRechercher,\s*filter\s+and\s+managing\b", "filtering, searching, and managing", t, flags=re.I)
        else:
            # French: noun openers are idiomatic; fix English words or awkward infinitive openers
            t = re.sub(r"^Development\s+d", "Développement d", t)
            t = re.sub(r"^Developpement\b", "Développement", t)
            t = re.sub(r"^D[ée]velopper\s+d['’]", "Développement d'", t, flags=re.I)
            t = re.sub(r"^Concevoir\s+et\s+d[ée]velopper\b", "Conception et développement d'", t, flags=re.I)
            t = re.sub(r"\bd'\s+une\b", "d'une", t)
            t = re.sub(r"^Creation\b", "Création", t)
            t = re.sub(r"\bremplasser\b", "remplacer", t, flags=re.I)
            t = re.sub(r"\bdiff[ée]rantes\b", "différentes", t, flags=re.I)
            t = re.sub(r"\btravail\s+manuelle\b", "travail manuel", t, flags=re.I)
            t = re.sub(r"\bpour\s+facilit[ée]\b", "pour faciliter", t, flags=re.I)
        t = (t[:1].upper() + t[1:]).rstrip(" .;")
        if len(t.split()) >= 4 and not t.lower().startswith("live apps:") and not t.endswith(("!", "?")):
            t = t + "."
        return t, moved

    # ── main ──────────────────────────────────────────────────────────────
    def run(self) -> CV:
        cv = self.cv
        cv.name = cv.name.strip()
        if cv.headline:
            h = self.fix_text(cv.headline)
            cv.headline = h if not h.islower() else h.title()
        cv.summary = self.fix_text(cv.summary, "summary")
        for sec in ("experience", "projects"):
            for e in getattr(cv, sec):
                ended = not (e.dates and e.dates.is_present)
                e.title = self._title_case(self.fix_text(e.title))
                e.org = self.fix_text(e.org)
                new_bullets: List[str] = []
                for b in e.bullets:
                    if re.match(r"^(?:e\.?g\.?|ex\s*:|for example|par exemple)\b", b.strip(), re.I) and new_bullets:
                        joined = new_bullets[-1] + " — " + self.fix_text(b.strip())
                        self.log("merged_example_into_bullet", b, joined)
                        new_bullets[-1] = joined
                        continue
                    nb, techs = self.polish_bullet(b, ended, e)
                    for tch in techs:
                        if tch not in e.stack:
                            e.stack.append(tch)
                    if nb and nb not in new_bullets:
                        new_bullets.append(nb)
                e.bullets = new_bullets
                e.stack = self._dedupe_stack(e.stack)
        for e in cv.education:
            e.title = self._title_case(self.fix_text(e.title))
            e.org = self.fix_text(e.org)
            e.bullets = [self.fix_text(b) for b in e.bullets]
        cv.certifications = [self.fix_text(c) for c in cv.certifications]
        cv.activities = [self.fix_text(a).rstrip(":") for a in cv.activities if len(a.strip(" :")) > 3]
        if cv.skill_groups:
            cv.skill_groups = [
                (re.sub(r"\bDesing\b", "Design", self.fix_text(cat), flags=re.I), items)
                for cat, items in cv.skill_groups
            ]
        # skills: canonical, deduplicated, no generic noise
        skills = []
        for s in cv.skills:
            c = canonical_tech(s) or s
            if c not in skills and len(c) <= 40 and not re.search(r":", c):
                skills.append(c)
        if len(skills) != len(cv.skills):
            self.log("skills_deduplicated", f"{len(cv.skills)} items", f"{len(skills)} items")
        cv.skills = skills
        return cv

    @staticmethod
    def _title_case(t: str) -> str:
        if t and t.islower():
            small = {"and", "of", "for", "in", "at", "de", "du", "des", "et", "en", "à", "la", "le"}
            return " ".join(w if w in small and i else w.capitalize() for i, w in enumerate(t.split()))
        return t

    @staticmethod
    def _dedupe_stack(stack: List[str]) -> List[str]:
        out: List[str] = []
        for s in stack:
            s2 = s.strip(" .,")
            if not s2 or re.fullmatch(r"(?:apis?|n|framework|library)", s2, re.I):
                continue
            c = canonical_tech(s2) or s2
            if c.lower() not in {x.lower() for x in out}:
                out.append(c)
        return out


def group_skills(skills: List[str], lang: str = "en", unknown: List[str] = None) -> List[Tuple[str, List[str]]]:
    """Group canonical skills into recruiter-standard categories, in a stable order."""
    from .lexicon import CATEGORY_FR
    buckets: Dict[str, List[str]] = {}
    for s in skills:
        cat = tech_category(s) if s in TECH else "Other"
        buckets.setdefault(cat, [])
        if s not in buckets[cat]:
            buckets[cat].append(s)
    # merge tiny categories so the section stays compact
    order = [c for c in CATEGORY_ORDER if c in buckets] + (["Other"] if "Other" in buckets else [])
    out: List[Tuple[str, List[str]]] = []
    for c in order:
        label = CATEGORY_FR.get(c, c) if lang == "fr" else c
        out.append((label, buckets[c]))
    # fold single-item categories into a final "Other / Autres" row (except Languages)
    merged: List[Tuple[str, List[str]]] = []
    spill: List[str] = []
    for label, items in out:
        if len(items) == 1 and label not in ("Languages", "Langages") and len(out) > 4:
            spill.extend(items)
        else:
            merged.append((label, items))
    if spill:
        other = "Autres" if lang == "fr" else "Other"
        idx = next((i for i, (l, _) in enumerate(merged) if l in ("Other", "Autres")), None)
        if idx is None:
            merged.append((other, spill))
        else:
            merged[idx] = (merged[idx][0], merged[idx][1] + spill)
    return merged


def enhance(cv: CV) -> Tuple[CV, List[Dict[str, str]]]:
    e = Enhancer(cv)
    out = e.run()
    return out, e.changes
