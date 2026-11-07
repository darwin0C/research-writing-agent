"""C4: scan for template-like AI phrasing and strong claims (input for the Auditor)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .invariants import STRONG_CLAIMS, STRONG_CLAIMS_ZH
from .latex_mask import mask, strip_placeholders

DEFAULT_PHRASES = Path(__file__).resolve().parent.parent / "config" / "ai_phrases.txt"
ZH_PHRASES = DEFAULT_PHRASES.with_name("ai_phrases_zh.txt")


def _ascii_word(c: str) -> bool:
    return c.isascii() and c.isalnum()


def cjk_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def load_phrases(path: Path = DEFAULT_PHRASES) -> list[tuple[str, re.Pattern[str]]]:
    """One phrase per line; lines starting with 're:' are regexes; '#' comments."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            pat = line[3:].strip()
        else:
            body = re.escape(line).replace(r"\ ", r"\s+")
            pat = (r"\b" if _ascii_word(line[0]) else "") + body + (r"\b" if _ascii_word(line[-1]) else "")
        out.append((line, re.compile(pat, re.I)))
    return out


@dataclass
class Hit:
    kind: str     # "ai-phrase" | "strong-claim"
    term: str
    line: int
    excerpt: str


def audit(text: str, phrases_path: Path = DEFAULT_PHRASES) -> dict:
    masked = mask(text).text
    hits: list[Hit] = []
    lines = masked.splitlines()

    strong = [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.I)) for t in STRONG_CLAIMS]
    strong += [(t, re.compile(re.escape(t))) for t in STRONG_CLAIMS_ZH]
    phrases = load_phrases(phrases_path)
    if ZH_PHRASES.exists() and cjk_chars(text):
        phrases += load_phrases(ZH_PHRASES)
    for kind, patterns in (("ai-phrase", phrases), ("strong-claim", strong)):
        taken: list[tuple[int, int, int]] = []  # (line, start, end) already reported
        for term, pat in patterns:
            for ln, line in enumerate(lines, 1):
                for m in pat.finditer(line):
                    if any(l == ln and m.start() < e and s < m.end() for l, s, e in taken):
                        continue  # overlapping rules count once
                    taken.append((ln, m.start(), m.end()))
                    shown = m.group(0) if term.startswith("re:") else term
                    a, b = max(0, m.start() - 40), min(len(line), m.end() + 40)
                    hits.append(Hit(kind, shown.lower(), ln, line[a:b].strip()))

    plain = strip_placeholders(masked)
    # length unit: English words + Chinese characters/1.5 (≈ words)
    words = len(re.findall(r"[A-Za-z]+", plain)) + round(cjk_chars(plain) / 1.5)
    n_ai = sum(h.kind == "ai-phrase" for h in hits)
    return {
        "words": words,
        "ai_phrases": n_ai,
        "ai_phrases_per_1000_words": round(n_ai * 1000 / words, 1) if words else 0.0,
        "strong_claims": sum(h.kind == "strong-claim" for h in hits),
        "hits": [h.__dict__ for h in sorted(hits, key=lambda h: (h.line, h.kind))],
    }
