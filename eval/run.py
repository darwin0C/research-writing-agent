"""Planted-error benchmark for the checker.

    python3 -m eval.run            # table to stdout, writes eval/results.md, exit 1 if a target is missed

Each injector plants one error of a known type into a faithful revision; we then ask
whether compare() reports it in the expected layer:
  blocked = an [error] in that layer (the revision is rejected)
  flagged = an [error] or [warning] in that layer (a human is told)

Targets
  hard types (must be rejected)          blocked ≥ 95%
  soft types (judgement, must be seen)   flagged ≥ 80%
  faithful revisions                     0 errors (no false rejections)
  gap types                              reported only — known blind spots
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from checker.invariants import compare, load_context
from checker.latex_mask import mask, unmask
from checker.semantics import NUM, SCOPE_PATTERNS, _FROM_TO

from .corpus import PAIRS

HERE = Path(__file__).resolve().parent
CTX = load_context(bib=str(HERE / "refs.bib"))

_PROSE_NUM = re.compile(r"(?<![\w.⟦])\d+(?:\.\d+)?(?![\w⟧])")


def _on_prose(text: str, fn):
    """Apply fn to the masked prose so LaTeX constructs are never touched."""
    res = mask(text)
    new = fn(res.text)
    return None if new is None or new == res.text else unmask(new, res.mapping, strict=False)


def _sub_first(pattern: str, repl, text: str, flags=re.I):
    new, n = re.subn(pattern, repl, text, count=1, flags=flags)
    return new if n else None


# ------------------------------------------------------------------ injectors

def number_change(t):
    def f(p):
        m = _PROSE_NUM.search(p)
        if not m:
            return None
        s = m.group(0)
        new = s[:-1] + str((int(s[-1]) + 1) % 10)
        return p[: m.start()] + new + p[m.end():]
    return _on_prose(t, f)


UNIT_SWAP = [("kW/m2", "W/m2"), ("kPa", "MPa"), ("mm", "μm"), ("μm", "mm"), ("nm", "μm"),
             ("ns", "ps"), ("ps", "ns"), ("Hz", "kHz"), ("K", "°C"), ("°", " K")]


def unit_change(t):
    def f(p):
        for a, b in UNIT_SWAP:
            m = re.search(r"(\d)(\s*)" + re.escape(a) + r"(?![A-Za-z])", p)
            if m:
                return p[: m.start()] + m.group(1) + m.group(2) + b + p[m.end():]
        return None
    return _on_prose(t, f)


def cite_drop(t):
    m = re.search(r"\\cite\{([^}]*)\}", t)
    if not m:
        return None
    keys = m.group(1).split(",")
    if len(keys) > 1:
        return t[: m.start()] + "\\cite{" + ",".join(keys[:-1]) + "}" + t[m.end():]
    return t[: m.start()].rstrip() + t[m.end():]


def cite_fake(t):
    return _sub_first(r"\\cite\{([^}]*)\}", lambda m: "\\cite{" + m.group(1) + ",smith2099}", t)


def eq_edit(t):
    m = re.search(r"\$([^$]+)\$", t)
    if not m:
        return None
    body = m.group(1)
    d = re.search(r"\d", body)
    body = body[: d.start()] + str((int(d.group()) + 1) % 10) + body[d.end():] if d else body + "+1"
    return t[: m.start()] + "$" + body + "$" + t[m.end():]


def from_to_swap(t):
    def f(p):
        m = _FROM_TO.search(p)
        if not m:
            return None
        a, b = m.span("a"), m.span("b")
        return p[: a[0]] + p[b[0]:b[1]] + p[a[1]: b[0]] + p[a[0]:a[1]] + p[b[1]:]
    return _on_prose(t, f)


FLIP = [("increased", "decreased"), ("decreased", "increased"), ("increases", "decreases"),
        ("decreases", "increases"), ("reduced", "increased"), ("rose", "fell"), ("fell", "rose"),
        ("grew", "shrank"), ("higher", "lower"), ("lower", "higher"), ("lowered", "raised"),
        ("raised", "lowered"), ("delayed", "advanced"), ("enhanced", "reduced")]


def direction_flip(t):
    """Flip the first direction word in a sentence that carries a number."""
    def f(p):
        for sent in re.split(r"(?<=[.!?])\s+", p):
            if not _PROSE_NUM.search(sent):
                continue
            for a, b in FLIP:
                m = re.search(r"\b" + a + r"\b", sent)
                if m:
                    new_sent = sent[: m.start()] + b + sent[m.end():]
                    return p.replace(sent, new_sent, 1)
        return None
    return _on_prose(t, f)


def bound_drop(t):
    return _on_prose(t, lambda p: _sub_first(
        r"\b(?:less than|more than|greater than|below|above|at least|at most|up to)\s+(?=" + NUM + ")",
        "", p))


def approx_drop(t):
    return _on_prose(t, lambda p: _sub_first(
        r"\b(?:approximately|about|nearly|roughly|around)\s+(?=" + NUM + ")", "", p))


def scope_drop(t):
    def f(p):
        m = re.search("|".join(f"(?:{x})" for x in SCOPE_PATTERNS), p, re.I)
        if not m:
            return None
        start, end = m.start(), m.end()
        if p[end:end + 1] == ",":
            end += 1
        return (p[:start] + p[end:]).replace("  ", " ").replace(" .", ".")
    return _on_prose(t, f)


CLAIM_UP = [("suggesting", "proving"), ("suggests", "proves"), ("suggest", "prove"),
            ("indicating", "demonstrating"), ("indicates", "demonstrates"),
            ("indicate", "demonstrate"), ("shows", "proves"), ("show", "prove")]


def claim_up(t):
    def f(p):
        for a, b in CLAIM_UP:
            m = re.search(r"\b" + a + r"\b", p)
            if m:
                return p[: m.start()] + b + p[m.end():]
        return None
    return _on_prose(t, f)


def hedge_drop(t):
    return _on_prose(t, lambda p: _sub_first(r"\b(?:may|might|could)\s+(?:be\s+)?", "", p))


def intensifier_add(t):
    return _on_prose(t, lambda p: _sub_first(
        r"\b(increased|decreased|reduced|rose|suggest\w*|indicat\w*|show\w*)\b",
        lambda m: "significantly " + m.group(1) if m.group(1).startswith(("inc", "dec", "red", "ros"))
        else "clearly " + m.group(1), p))


def term_drift(t):
    def f(p):
        for term in CTX.glossary:
            if not term.variants:
                continue
            m = re.search(r"\b" + re.escape(term.preferred) + r"\b", p, re.I)
            if m:
                return p[: m.start()] + term.variants[0] + p[m.end():]
        return None
    return _on_prose(t, f)


def rebind_swap(t):
    """Swap two numbers with the same unit inside one sentence (not a from–to pair)."""
    def f(p):
        unit_num = re.compile(r"(?<![\w.⟦])(\d+(?:\.\d+)?)\s*(ns|ps|mm|μm|nm|kPa|K|%)(?![A-Za-z])")
        for sent in re.split(r"(?<=[.!?])\s+", p):
            if _FROM_TO.search(sent):
                continue
            ms = list(unit_num.finditer(sent))
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    a, b = ms[i], ms[j]
                    if a.group(2) == b.group(2) and a.group(1) != b.group(1):
                        s = (sent[: a.start(1)] + b.group(1) + sent[a.end(1): b.start(1)]
                             + a.group(1) + sent[b.end(1):])
                        return p.replace(sent, s, 1)
        return None
    return _on_prose(t, f)


# name, injector, expected layer prefixes, kind
INJECTORS = [
    ("number_change", number_change, ("L2",), "hard"),
    ("unit_change", unit_change, ("L2-unit",), "hard"),
    ("cite_drop", cite_drop, ("L1-CITE",), "hard"),
    ("cite_fake", cite_fake, ("L1-CITE", "L6"), "hard"),
    ("eq_edit", eq_edit, ("L1-EQ",), "hard"),
    ("from_to_swap", from_to_swap, ("L3",), "hard"),
    ("bound_drop", bound_drop, ("L4-qualifier",), "hard"),
    ("claim_up", claim_up, ("L5",), "soft"),
    ("direction_flip", direction_flip, ("L3",), "soft"),
    ("approx_drop", approx_drop, ("L4-qualifier",), "soft"),
    ("scope_drop", scope_drop, ("L4-scope",), "soft"),
    ("hedge_drop", hedge_drop, ("L5",), "soft"),
    ("intensifier_add", intensifier_add, ("L5",), "soft"),
    ("term_drift", term_drift, ("T-term",), "soft"),
    ("rebind_swap", rebind_swap, ("L2-binding", "L3"), "gap"),
]

STRONGER_THAN_ORIGINAL = {"claim_up", "intensifier_add"}


def _stronger(original: str, bad: str, name: str) -> bool:
    """Only count claim injections that make the text stronger than the original."""
    from checker.semantics import INTENSIFIERS, _count_words, _levels, _prose
    p0, p1 = _prose(original), _prose(bad)
    if name == "claim_up":
        l0, l1 = _levels(p0), _levels(p1)
        return any(sum(v for k, v in l1.items() if k >= lv) > sum(v for k, v in l0.items() if k >= lv)
                   for lv in (5, 4, 3))
    return bool(_count_words(p1, INTENSIFIERS) - _count_words(p0, INTENSIFIERS))


TARGET = {"hard": ("blocked", 0.95), "soft": ("flagged", 0.80)}


def evaluate() -> dict:
    clean = []
    for pid, original, faithful in PAIRS:
        rep = compare(original, faithful, CTX)
        clean.append({"id": pid,
                      "errors": [f"{f.layer}: {f.message}" for f in rep.findings if f.level == "error"],
                      "warnings": [f"{f.layer}: {f.message}" for f in rep.findings if f.level == "warning"]})

    rows, misses = [], []
    for name, inj, layers, kind in INJECTORS:
        n = blocked = flagged = 0
        for pid, original, faithful in PAIRS:
            bad = inj(faithful)
            if bad is None or bad == faithful:
                continue
            if name in STRONGER_THAN_ORIGINAL and not _stronger(original, bad, name):
                continue  # injection only restored the original's own wording
            n += 1
            hits = [f for f in compare(original, bad, CTX).findings if f.layer.startswith(layers)]
            b = any(f.level == "error" for f in hits)
            blocked += b
            flagged += bool(hits)
            if (kind == "hard" and not b) or (kind != "hard" and not hits):
                misses.append((name, pid))
        rows.append({"type": name, "kind": kind, "n": n, "blocked": blocked, "flagged": flagged})

    ok = all(not c["errors"] for c in clean)
    for r in rows:
        if r["kind"] in TARGET and r["n"]:
            metric, thr = TARGET[r["kind"]]
            r["pass"] = r[metric] / r["n"] >= thr
            ok &= r["pass"]
    return {"clean": clean, "rows": rows, "misses": misses, "ok": ok}


def render(res: dict) -> str:
    pct = lambda a, n: f"{100 * a / n:.0f}%" if n else "—"
    lines = ["# Checker benchmark", "",
             f"Corpus: {len(PAIRS)} paragraph pairs · overall: **{'PASS' if res['ok'] else 'FAIL'}**", "",
             "## Faithful revisions (false-positive check)", "",
             "| Paragraph | Errors | Warnings |", "|---|---|---|"]
    for c in res["clean"]:
        lines.append(f"| {c['id']} | {len(c['errors'])} | {len(c['warnings'])} |")
    warn_total = sum(len(c["warnings"]) for c in res["clean"])
    lines += ["", f"False rejections: {sum(len(c['errors']) for c in res['clean'])} · "
              f"warnings to review: {warn_total}", "",
              "## Planted errors", "",
              "| Type | Kind | Cases | Blocked | Flagged | Target |", "|---|---|---|---|---|---|"]
    for r in res["rows"]:
        tgt = ("—" if r["kind"] == "gap" else
               f"{TARGET[r['kind']][0]} ≥ {TARGET[r['kind']][1]:.0%} "
               f"{'✓' if r.get('pass') else '✗'}")
        lines.append(f"| {r['type']} | {r['kind']} | {r['n']} | {pct(r['blocked'], r['n'])} | "
                     f"{pct(r['flagged'], r['n'])} | {tgt} |")
    if res["misses"]:
        lines += ["", "## Misses", "", *(f"- {t} in {p}" for t, p in res["misses"])]
    for c in res["clean"]:
        if c["errors"] or c["warnings"]:
            lines += ["", f"### {c['id']}", *(f"- error {e}" for e in c["errors"]),
                      *(f"- warning {w}" for w in c["warnings"])]
    return "\n".join(lines) + "\n"


def main() -> int:
    res = evaluate()
    text = render(res)
    (HERE / "results.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
