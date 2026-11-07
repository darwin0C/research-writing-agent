"""C2: compare original and revised text for content that must not change.

Layer 1  protected content: equations, citations (by key), refs, labels, quantities.
Layer 2  prose numbers: value multiset (error), value+unit pairing (error when a
         unit changes, warning when only its attachment moves), and numbers that
         shared a sentence still sharing one (warning — possible re-binding).
L3–L6    direction, scope/qualifiers, claim strength, citations — see semantics.py, bib.py
T        terminology and spelling drift — see terms.py

Errors mean the revision must not be accepted; warnings need a human look.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .latex_mask import PLACEHOLDER_RE, mask, strip_placeholders

# ---------------------------------------------------------------- layer 1

def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _cite_keys(cmd: str) -> list[str]:
    body = cmd[cmd.rfind("{") + 1 : cmd.rfind("}")]
    return [k.strip() for k in body.split(",") if k.strip()]


def protected_items(text: str) -> dict[str, Counter]:
    result = mask(text)
    groups: dict[str, Counter] = {}
    for key, original in result.mapping.items():
        kind = PLACEHOLDER_RE.match(key).group(1)
        if kind == "MATH":
            kind = "EQ"
        bucket = groups.setdefault(kind, Counter())
        if kind == "CITE":
            bucket.update(_cite_keys(original))  # \cite{a,b} == \cite{b,a}
        else:
            bucket[_norm_ws(original)] += 1
    return groups


# ---------------------------------------------------------------- layer 2

_UNITS = [
    # composite first so the longest match wins
    r"W\s*/\s*\(m\^?2\s*[·.]?\s*K\)", r"W\s*m\^?-2\s*K\^?-1", r"W\s*/\s*m\^?2", r"kW\s*/\s*m\^?2",
    r"MW\s*/\s*m\^?2", r"W\s*m\^?-2", r"kg\s*/\s*\(m\^?2\s*[·.]?\s*s\)", r"kg\s*m\^?-2\s*s\^?-1",
    r"kg\s*/\s*m\^?3", r"m\s*/\s*s", r"mm\s*/\s*s", r"J\s*/\s*m\^?2", r"mJ\s*/\s*m\^?2",
    r"mN\s*/\s*m", r"ml\s*/\s*min", r"mL\s*/\s*min", r"g\s*/\s*s", r"L\s*/\s*min",
    r"°C", r"℃", r"°", r"K", r"\\%", r"%", r"percent",
    r"fs", r"ps", r"ns", r"μs", r"µs", r"us", r"ms", r"s", r"min", r"h",
    r"pm", r"Å", r"nm", r"μm", r"µm", r"um", r"mm", r"cm", r"m",
    r"mW", r"kW", r"MW", r"W", r"kJ", r"MJ", r"J", r"eV", r"meV", r"kcal/mol", r"kJ/mol",
    r"Pa", r"kPa", r"MPa", r"GPa", r"bar", r"atm",
    r"mg", r"kg", r"g", r"mol", r"Hz", r"kHz", r"MHz", r"V", r"mV", r"A", r"mA",
]
_UNIT_RE = "|".join(_UNITS)

_NUMBER_WORDS = {
    w: str(i) for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())
}
_NUM_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<num>[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"(?:\s*(?P<unit>" + _UNIT_RE + r")(?![A-Za-z]))?"
)
_WORD_NUM_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.I)

_ABBREV = re.compile(
    r"\b(Figs?|Eqs?|Refs?|Tabs?|Secs?|No|Nos|vs|approx|ca|cf|resp|et al|i\.e|e\.g)\.",
    re.I,
)

_UNIT_ALIASES = {"\\%": "%", "℃": "°C", "µs": "μs", "us": "μs", "µm": "μm", "um": "μm", "percent": "%"}


def _norm_unit(u: str | None) -> str:
    if not u:
        return ""
    u = re.sub(r"\s+", "", u).replace("^", "")
    return _UNIT_ALIASES.get(u, u)


def _norm_num(n: str) -> str:
    n = n.replace(",", "").replace("−", "-").lstrip("+")
    try:
        return repr(float(n)).removesuffix(".0") if "e" not in n.lower() else repr(float(n))
    except ValueError:
        return n


_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def split_sentences(prose: str) -> list[str]:
    protected = _ABBREV.sub(lambda m: m.group(0)[:-1] + "∯", prose)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9⟦(\\])|(?<=[。！？；])\s*|\n\s*\n", protected)
    return [p.replace("∯", ".").strip() for p in parts if p.strip()]


@dataclass(frozen=True)
class Quantity:
    value: str
    unit: str
    sentence: int


def extract_quantities(text: str) -> list[Quantity]:
    """Numbers in prose (placeholders already removed)."""
    prose = strip_placeholders(mask(text).text)
    out = []
    prose = prose.translate(_SUPERSCRIPTS)  # m² ≡ m2, 10⁻³ ≡ 10-3
    for si, sent in enumerate(split_sentences(prose)):
        sent = _WORD_NUM_RE.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], sent)
        for m in _NUM_RE.finditer(sent):
            out.append(Quantity(_norm_num(m.group("num")), _norm_unit(m.group("unit")), si))
    return out


# ---------------------------------------------------------------- strong-claim words (audit hints)

STRONG_CLAIMS_ZH = ["证明", "证实", "充分说明", "毫无疑问", "显著", "极大", "大幅", "首次",
                    "国际领先", "国际先进", "突破性", "革命性", "颠覆性", "彻底", "完全解决"]

STRONG_CLAIMS = [
    "prove", "proves", "proved", "proven", "demonstrate", "demonstrates", "demonstrated",
    "confirm", "confirms", "confirmed", "establish", "establishes", "clearly", "undoubtedly",
    "definitely", "always", "never", "dramatically", "remarkably", "significantly",
    "first time", "novel", "unprecedented", "superior", "breakthrough",
]
# ---------------------------------------------------------------- compare

@dataclass
class Finding:
    level: str   # "error" | "warning"
    layer: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(f.level == "error" for f in self.findings)

    def add(self, level: str, layer: str, message: str) -> None:
        self.findings.append(Finding(level, layer, message))

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": sum(f.level == "error" for f in self.findings),
            "warnings": sum(f.level == "warning" for f in self.findings),
            "findings": [f.__dict__ for f in self.findings],
        }


def _diff(before: Counter, after: Counter) -> tuple[Counter, Counter]:
    return before - after, after - before


def compare(original: str, revised: str, ctx: "Context | None" = None) -> Report:
    rep = Report()

    # layer 0: placeholders already in the text (docx objects) must survive unchanged
    ph0, ph1 = Counter(PLACEHOLDER_RE.findall(original)), Counter(PLACEHOLDER_RE.findall(revised))
    if ph0 != ph1:
        for (kind, n), k in (ph0 - ph1).items():
            rep.add("error", f"L1-{kind}", f"protected object ⟦{kind}{n}⟧ removed or duplicated")
        for (kind, n), k in (ph1 - ph0).items():
            rep.add("error", f"L1-{kind}", f"protected object ⟦{kind}{n}⟧ added or duplicated")

    # layer 1
    p0, p1 = protected_items(original), protected_items(revised)
    for kind in sorted(set(p0) | set(p1)):
        removed, added = _diff(p0.get(kind, Counter()), p1.get(kind, Counter()))
        for item, n in removed.items():
            level = "warning" if kind == "COMMENT" else "error"
            rep.add(level, f"L1-{kind}", f"removed or altered ({n}×): {item}")
        for item, n in added.items():
            if kind == "COMMENT":  # usually an unescaped % that hides the rest of the line
                rep.add("error", "L1-COMMENT",
                        f"new LaTeX comment ({n}×) — unescaped % hides text from the PDF: {item[:60]}")
            else:
                rep.add("error", f"L1-{kind}", f"added ({n}×): {item}")

    # layer 2
    q0, q1 = extract_quantities(original), extract_quantities(revised)
    removed, added = _diff(Counter(q.value for q in q0), Counter(q.value for q in q1))
    for v, n in removed.items():
        rep.add("error", "L2-number", f"number missing ({n}×): {v}")
    for v, n in added.items():
        rep.add("error", "L2-number", f"number added ({n}×): {v}")

    vu0 = Counter((q.value, q.unit) for q in q0)
    vu1 = Counter((q.value, q.unit) for q in q1)
    if not removed and not added and vu0 != vu1:
        gone, new = _diff(vu0, vu1)
        for value in sorted({v for v, _ in gone} | {v for v, _ in new}):
            u0 = sorted({u for v, u in gone if v == value})
            u1 = sorted({u for v, u in new if v == value})
            real_units_differ = [u for u in u0 if u] and [u for u in u1 if u]
            rep.add(
                "error" if real_units_differ else "warning",
                "L2-unit",
                f"{value}: unit {u0 or ['—']} → {u1 or ['—']}",
            )

    def groups(qs: list[Quantity]) -> list[frozenset]:
        by_sent: dict[int, set] = {}
        for q in qs:
            by_sent.setdefault(q.sentence, set()).add((q.value, q.unit))
        return [frozenset(s) for s in by_sent.values()]

    g1 = groups(q1)
    for group in groups(q0):
        if len(group) >= 2 and not any(group <= g for g in g1):
            shown = ", ".join(f"{v} {u}".strip() for v, u in sorted(group))
            rep.add("warning", "L2-binding",
                    f"numbers that shared a sentence are now split — check what each refers to: {shown}")

    # evidence markers: requests to the author, never silently left in a final text
    from .latex_mask import EVIDENCE_RE
    new_markers = Counter(EVIDENCE_RE.findall(revised)) - Counter(EVIDENCE_RE.findall(original))
    for m, n in new_markers.items():
        rep.add("warning", "L4-evidence", f"author must supply evidence: {m[12:-2].strip()}")

    # L3–L6 + terminology (imported here: those modules import this one)
    from .bib import bib_findings
    from .semantics import claim_findings, direction_findings, scope_findings
    from .terms import term_findings

    ctx = ctx or Context()
    for level, layer, msg in (direction_findings(original, revised)
                              + scope_findings(original, revised)
                              + claim_findings(original, revised)
                              + bib_findings(original, revised, ctx.bib)
                              + term_findings(original, revised, ctx.glossary)):
        rep.add(level, layer, msg)

    return rep


@dataclass
class Context:
    """Optional project knowledge used by compare: .bib entries and glossary."""
    bib: dict | None = None
    glossary: list = field(default_factory=list)
    spelling: str | None = None


def load_context(bib: str | None = None, glossary: str | None = "default",
                 style: str | None = None) -> Context:
    from .bib import load_bib
    from .terms import DEFAULT_GLOSSARY, load_glossary

    spelling = None
    if style:
        prof = load_style(style)
        spelling = prof.get("spelling") if prof.get("spelling") in ("US", "UK") else None
    gpath = DEFAULT_GLOSSARY if glossary == "default" else glossary
    return Context(bib=load_bib(bib), glossary=load_glossary(gpath), spelling=spelling)


STYLE_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "config" / "journals"


def load_style(key_or_path: str) -> dict:
    import tomllib
    from pathlib import Path

    p = Path(key_or_path)
    if not p.exists():
        p = STYLE_DIR / f"{key_or_path}.toml"
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))
