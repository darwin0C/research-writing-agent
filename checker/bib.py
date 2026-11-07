"""L6: citation keys against a BibTeX file (offline; never adds or edits references)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .latex_mask import mask

_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.I)


def parse_bib(text: str) -> dict[str, dict]:
    """key -> {"type", "has_doi", "has_year", "count"}; tolerant of messy files."""
    entries: dict[str, dict] = {}
    for m in _ENTRY.finditer(text):
        etype, key = m.group(1).lower(), m.group(2)
        if etype in ("comment", "string", "preamble"):
            continue
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i]
        e = entries.setdefault(key, {"type": etype, "count": 0})
        e["count"] += 1
        e["has_doi"] = bool(re.search(r"\bdoi\s*=", body, re.I))
        e["has_year"] = bool(re.search(r"\b(year|date)\s*=", body, re.I))
    return entries


def load_bib(path: Path | str | None) -> dict[str, dict] | None:
    if not path:
        return None
    p = Path(path)
    return parse_bib(p.read_text(encoding="utf-8", errors="replace")) if p.exists() else None


def cited_keys(text: str) -> Counter:
    keys: Counter = Counter()
    for orig in mask(text).mapping.values():
        if orig.lstrip("\\").startswith(("cite", "parencite", "Parencite", "textcite",
                                           "Textcite", "autocite", "footcite", "nocite")):
            body = orig[orig.rfind("{") + 1: orig.rfind("}")]
            keys.update(k.strip() for k in body.split(",") if k.strip() and k.strip() != "*")
    return keys


def bib_hints(text: str, bib: dict[str, dict] | None) -> list[str]:
    if bib is None:
        return []
    hints = []
    for key in sorted(cited_keys(text)):
        if key not in bib:
            hints.append(f"citation: '{key}' is not in the .bib file")
        else:
            e = bib[key]
            if e["count"] > 1:
                hints.append(f"citation: '{key}' is defined {e['count']} times in the .bib")
            if e["type"] == "article" and not e.get("has_doi"):
                hints.append(f"citation: '{key}' (article) has no DOI")
    return hints


def bib_findings(original: str, revised: str, bib: dict[str, dict] | None) -> list[tuple[str, str, str]]:
    if bib is None:
        return []
    out = []
    before = set(cited_keys(original))
    for key in sorted(set(cited_keys(revised))):
        if key not in bib:
            level = "warning" if key in before else "error"
            note = " (already missing in the original)" if key in before else ""
            out.append((level, "L6-cite", f"'{key}' not found in .bib{note}"))
    return out
