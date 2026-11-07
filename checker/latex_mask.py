"""C1: replace protected LaTeX content with placeholders such as ⟦EQ1⟧.

The model only ever sees the placeholders, so it cannot alter equations,
citations, cross-references, labels, siunitx quantities or comments.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
from dataclasses import dataclass, field

# "latex": mask LaTeX constructs. "docx"/"text": no LaTeX — the text is taken as is
# (docx paragraphs arrive with their protected objects already as placeholders).
FORMAT: contextvars.ContextVar[str] = contextvars.ContextVar("text_format", default="latex")


@contextlib.contextmanager
def text_format(fmt: str):
    tok = FORMAT.set(fmt or "latex")
    try:
        yield
    finally:
        FORMAT.reset(tok)

OPEN, CLOSE = "⟦", "⟧"
PLACEHOLDER_RE = re.compile(re.escape(OPEN) + r"([A-Z]+)(\d+)" + re.escape(CLOSE))

_MATH_ENVS = (
    r"equation\*?|align\*?|alignat\*?|gather\*?|multline\*?|flalign\*?"
    r"|eqnarray\*?|displaymath|math|split"
)
_OPT = r"(?:\s*\[[^\]]*\])*"  # optional [..] arguments

# Order matters: comments first, then math, then commands in the remaining prose.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("COMMENT", re.compile(r"(?<!\\)%[^\n]*")),
    # formal statements stay verbatim (theorem, definition, …)
    ("ENV", re.compile(r"\\begin\{(theorem|lemma|proposition|corollary|definition|assumption|conjecture|"
                       r"axiom|hypothesis|claim)\*?\}.*?\\end\{\1\*?\}", re.S)),
    ("EQ", re.compile(r"\\begin\{(" + _MATH_ENVS + r")\}.*?\\end\{\1\}", re.S)),
    ("EQ", re.compile(r"\$\$.+?\$\$", re.S)),
    ("EQ", re.compile(r"\\\[.+?\\\]", re.S)),
    ("MATH", re.compile(r"\\\(.+?\\\)", re.S)),
    ("MATH", re.compile(r"(?<![\\$])\$(?!\$)(?:\\.|[^$\\])+?\$")),
    ("CITE", re.compile(
        r"\\(?:cite[a-zA-Z]*|[pP]arencite|[tT]extcite|autocite|footcite|nocite)\*?"
        + _OPT + r"\s*\{[^{}]*\}")),
    ("REF", re.compile(
        r"\\(?:ref|eqref|autoref|[cC]ref|[cC]pageref|pageref|nameref|vref)\*?\s*\{[^{}]*\}")),
    ("LABEL", re.compile(r"\\label\s*\{[^{}]*\}")),
    ("QTY", re.compile(r"\\(?:SI|qty|SIrange|qtyrange)" + _OPT + r"(?:\s*\{[^{}]*\}){2,3}")),
    ("QTY", re.compile(r"\\(?:si|unit|num|numrange)" + _OPT + r"(?:\s*\{[^{}]*\}){1,2}")),
    ("HEAD", re.compile(
        r"\\(?:part|chapter|section|subsection|subsubsection|paragraph)\*?" + _OPT + r"\s*\{[^{}]*\}")),
    ("GFX", re.compile(r"\\includegraphics" + _OPT + r"\s*\{[^{}]*\}")),
    ("URL", re.compile(r"\\(?:url|href)\s*\{[^{}]*\}(?:\s*\{[^{}]*\})?")),
]


@dataclass
class MaskResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original


def mask(text: str) -> MaskResult:
    if FORMAT.get() != "latex":
        return MaskResult(text, {})
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    for kind, pattern in PATTERNS:
        def repl(m: re.Match[str], kind: str = kind) -> str:
            counters[kind] = counters.get(kind, 0) + 1
            key = f"{OPEN}{kind}{counters[kind]}{CLOSE}"
            mapping[key] = m.group(0)
            return key

        text = pattern.sub(repl, text)

    return MaskResult(text, mapping)


class UnmaskError(ValueError):
    pass


def unmask(text: str, mapping: dict[str, str], strict: bool = True) -> str:
    """Restore placeholders. In strict mode any missing, duplicated or invented
    placeholder raises UnmaskError instead of silently producing a broken file."""
    found = [m.group(0) for m in PLACEHOLDER_RE.finditer(text)]
    problems = []
    missing = [k for k in mapping if k not in found]
    invented = sorted({k for k in found if k not in mapping})
    duplicated = sorted({k for k in found if found.count(k) > 1})
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if invented:
        problems.append(f"unknown: {', '.join(invented)}")
    if duplicated:
        problems.append(f"duplicated: {', '.join(duplicated)}")
    if problems and strict:
        raise UnmaskError("placeholder check failed — " + "; ".join(problems))

    return PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


EVIDENCE_RE = re.compile(r"\[\[EVIDENCE:[^\]]*\]\]")


def strip_placeholders(text: str) -> str:
    """Prose only: drop placeholders (their index digits are not numbers) and
    [[EVIDENCE: …]] markers (their content is a note to the author, not text)."""
    return EVIDENCE_RE.sub(" ", PLACEHOLDER_RE.sub(" ", text))
