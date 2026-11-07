"""C3: terminology (glossary), abbreviation definitions and spelling consistency.

Glossary format (config/glossary.toml):

    [[term]]
    preferred = "onset of nucleate boiling"
    abbr = "ONB"                       # optional, matched case-sensitively
    variants = ["nucleate boiling onset", "boiling incipience point"]   # discouraged
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .latex_mask import mask, strip_placeholders

DEFAULT_GLOSSARY = Path(__file__).resolve().parent.parent / "config" / "glossary.toml"


@dataclass
class Term:
    preferred: str
    abbr: str | None = None
    variants: list[str] = field(default_factory=list)


def load_glossary(path: Path | str | None = DEFAULT_GLOSSARY) -> list[Term]:
    if not path or not Path(path).exists():
        return []
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return [Term(t["preferred"], t.get("abbr"), list(t.get("variants", [])))
            for t in data.get("term", [])]


def _prose(text: str) -> str:
    return strip_placeholders(mask(text).text)


def _phrase_re(phrase: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(w) for w in phrase.split())
    if not phrase.isascii():
        return re.compile(body)  # Chinese terms: no word boundaries
    return re.compile(r"(?<![\w-])" + body + r"(?:s|es)?(?![\w-])", re.I)


def _abbr_re(abbr: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(abbr) + r"s?(?![\w-])")


def count_phrase(text: str, phrase: str) -> int:
    return len(_phrase_re(phrase).findall(text))


# ------------------------------------------------------------------ spelling

SPELLING_PAIRS = [  # (US stem, UK stem)
    ("behavior", "behaviour"), ("vaporiz", "vaporis"), ("color", "colour"),
    ("analyz", "analys"), ("normaliz", "normalis"), ("characteriz", "characteris"),
    ("modeling", "modelling"), ("modeled", "modelled"), ("center", "centre"),
    ("fiber", "fibre"), ("optimiz", "optimis"), ("utiliz", "utilis"),
    ("stabiliz", "stabilis"), ("minimiz", "minimis"), ("maximiz", "maximis"),
    ("homogeniz", "homogenis"), ("parameteriz", "parameteris"), ("labeled", "labelled"),
    ("favor", "favour"), ("aluminum", "aluminium"), ("sulfur", "sulphur"),
    ("vapor", "vapour"), ("ioniz", "ionis"), ("polariz", "polaris"), ("crystalliz", "crystallis"),
    ("generaliz", "generalis"), ("visualiz", "visualis"), ("summariz", "summaris"),
    ("gray", "grey"), ("meter", "metre"), ("liter", "litre"), ("artifact", "artefact"),
]


def spelling_profile(text: str) -> dict[str, list[str]]:
    prose = _prose(text)
    found: dict[str, list[str]] = {"US": [], "UK": []}
    for us, uk in SPELLING_PAIRS:
        found["US"] += re.findall(r"\b" + us + r"\w*", prose, re.I)
        found["UK"] += re.findall(r"\b" + uk + r"\w*", prose, re.I)
    return found


# ------------------------------------------------------------------ audit hints

def term_hints(text: str, terms: list[Term], spelling: str | None = None) -> list[str]:
    """Advisory notes for the auditor; never blocking."""
    prose = _prose(text)
    hints = []
    for t in terms:
        for v in t.variants:
            n = count_phrase(prose, v)
            if n:
                hints.append(f"term: '{v}' ({n}×) — glossary prefers '{t.preferred}'")
        if t.abbr:
            uses = [m.start() for m in _abbr_re(t.abbr).finditer(prose)]
            definition = re.search(r"(?<![\w-])" + r"\s+".join(map(re.escape, t.preferred.split()))
                                   + r"\s*\(\s*" + re.escape(t.abbr) + r"\s*\)", prose, re.I)
            if uses and not definition:
                hints.append(f"abbreviation: '{t.abbr}' used but not defined as "
                             f"'{t.preferred} ({t.abbr})' in this text")
            elif uses and definition:
                first_use = [u for u in uses if not (definition.start() <= u < definition.end())]
                if first_use and first_use[0] < definition.start():
                    hints.append(f"abbreviation: '{t.abbr}' used before its definition")
                defs = len(re.findall(r"\(\s*" + re.escape(t.abbr) + r"\s*\)", prose))
                if defs > 1:
                    hints.append(f"abbreviation: '{t.abbr}' defined {defs} times")
    sp = spelling_profile(text)
    if sp["US"] and sp["UK"]:
        hints.append(f"spelling: mixed US ({', '.join(sorted(set(sp['US']))[:4])}) and "
                     f"UK ({', '.join(sorted(set(sp['UK']))[:4])}) forms")
    elif spelling in ("US", "UK"):
        other = "UK" if spelling == "US" else "US"
        if sp[other]:
            hints.append(f"spelling: journal style is {spelling} but found {other} forms: "
                         f"{', '.join(sorted(set(sp[other]))[:5])}")
    return hints


# ------------------------------------------------------------------ compare

def term_findings(original: str, revised: str, terms: list[Term]) -> list[tuple[str, str, str]]:
    """Warnings for terminology drift introduced by the revision."""
    p0, p1 = _prose(original), _prose(revised)
    out = []
    for t in terms:
        for v in t.variants:
            n0, n1 = count_phrase(p0, v), count_phrase(p1, v)
            if n1 > n0:
                out.append(("warning", "T-term",
                            f"introduced '{v}' ({n1 - n0}×); glossary prefers '{t.preferred}'"))
        if t.abbr:
            a0 = len(_abbr_re(t.abbr).findall(p0))
            a1 = len(_abbr_re(t.abbr).findall(p1))
            if a0 and not a1 and count_phrase(p1, t.preferred) == 0:
                out.append(("warning", "T-term",
                            f"'{t.abbr}' / '{t.preferred}' no longer appears — check the term was not renamed"))
    s0, s1 = spelling_profile(original), spelling_profile(revised)
    for side, other in (("US", "UK"), ("UK", "US")):
        if s0[side] and not s0[other] and s1[other]:
            out.append(("warning", "T-spelling",
                        f"original uses {side} spelling; revision introduced {other}: "
                        f"{', '.join(sorted(set(s1[other])))}"))
    return out
