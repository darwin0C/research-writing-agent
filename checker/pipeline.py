"""M1 task graph: split a section into paragraph units, gate each rewrite,
retry or revert, assemble, and render graph.md / progress.md / checks.md / report.md.

Everything here is deterministic. LLM nodes (auditor, rewriter, claim-checker)
only read and write files inside the run folder; this module decides what
passed. run.json is the single source of truth; the .md files are views of it.

Run folder layout
  run.json  original.tex  graph.md  progress.md  checks.md
  units/uNN/ original.tex masked.txt map.json audit.txt      (written by split)
             issues.md                                       (auditor)
             masked_revised.txt changes.md                   (rewriter)
             revised.tex                                     (gate)
             feedback.md  attempts/                          (reopen)
  claims.md                                                  (claim-checker)
  revised.tex  report.md                                     (assemble)
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import shutil
import hashlib
import json
import re
import time
from pathlib import Path

from .audit import audit
from .bib import bib_hints
from .invariants import compare, load_context, load_style
from .terms import term_hints
from .latex_mask import (PLACEHOLDER_RE, UnmaskError, mask, strip_placeholders, text_format,
                         unmask)

MAX_ATTEMPTS = 3
MAX_STYLE_ATTEMPTS = 2
FINAL = {"frozen", "reverted", "passed", "styled", "style-kept-rewrite"}
MIN_PROSE_WORDS = 8

_FROZEN_ENV = re.compile(
    r"\s*\\begin\{(figure|table|equation|align|alignat|gather|multline|flalign|eqnarray|"
    r"displaymath|lstlisting|verbatim|minted|algorithm|tabular|tikzpicture|thebibliography)\*?\}"
)


class PipelineError(RuntimeError):
    pass


# ------------------------------------------------------------------ state io

def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@contextlib.contextmanager
def _locked(run: Path):
    """Parallel rewriters trigger gates at the same time; serialise state writes."""
    with open(run / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def load(run: Path) -> dict:
    p = run / "run.json"
    if not p.exists():
        raise PipelineError(f"no run.json in {run} — run `split` first")
    return json.loads(p.read_text(encoding="utf-8"))


def _save(run: Path, state: dict) -> None:
    tmp = run / "run.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(run / "run.json")
    render_progress(run, state)
    render_checks(run, state)


def _with_format(fn):
    """Run fn with the run's text format (latex / docx / text) active for all checks."""
    @functools.wraps(fn)
    def wrapper(run: Path, *a, **k):
        p = Path(run) / "run.json"
        fmt = json.loads(p.read_text(encoding="utf-8")).get("format", "latex") if p.exists() else "latex"
        with text_format(fmt):
            return fn(run, *a, **k)
    return wrapper


def _unit(state: dict, uid: str) -> dict:
    for u in state["units"]:
        if u["id"] == uid:
            return u
    raise PipelineError(f"unknown unit {uid}")


def _udir(run: Path, uid: str) -> Path:
    return run / "units" / uid


# ------------------------------------------------------------------ C1 split

def _classify(content: str) -> tuple[str, int]:
    if not content.strip():
        return "frozen", 0
    if _FROZEN_ENV.match(content):
        return "frozen", 0
    prose = strip_placeholders(mask(content).text)
    prose = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " ", prose)
    words = len(re.findall(r"[A-Za-z]{2,}", prose)) + round(len(re.findall(r"[\u4e00-\u9fff]", prose)) / 1.5)
    return ("prose" if words >= MIN_PROSE_WORDS else "frozen"), words


def _section_of(text: str) -> str:
    from .style import _HEADING, section_type
    m = _HEADING.search(text)
    if not m:
        return "other"
    return "abstract" if m.group(0).startswith("\\begin") else section_type(m.group(1))


def _ctx(run: Path, state: dict):
    return load_context(bib=state.get("bib"), glossary=state.get("glossary", "default"),
                        style=state.get("style"))


def split(source_text: str, run: Path, *, name: str, journal: str, level: str,
          source: str = "", bib: str | None = None, glossary: str = "default",
          style: str | None = None, style_corpus: str | None = None, fmt: str = "latex",
          _chunks: list | None = None, _unit_extra: list | None = None,
          _state_extra: dict | None = None) -> dict:
    with text_format(fmt):
        return _split(source_text, run, name=name, journal=journal, level=level, source=source,
                      bib=bib, glossary=glossary, style=style, style_corpus=style_corpus, fmt=fmt,
                      _chunks=_chunks, _unit_extra=_unit_extra, _state_extra=_state_extra)


def _split(source_text: str, run: Path, *, name, journal, level, source, bib, glossary, style,
           style_corpus, fmt, _chunks, _unit_extra, _state_extra) -> dict:
    if style_corpus:
        from . import style as stylemod
        try:
            stylemod.load(style_corpus)
        except FileNotFoundError as e:
            raise PipelineError(str(e)) from None
    if (run / "run.json").exists():
        raise PipelineError(f"{run} already has a run — resume it or choose a new folder")
    run.mkdir(parents=True, exist_ok=True)
    (run / "original.tex").write_text(source_text, encoding="utf-8")

    if _chunks is None:
        head, body = "", source_text
        doc = re.search(r"\\begin\{document\}[^\n]*\n?", source_text) if fmt == "latex" else None
        if doc:  # the preamble is never touched
            head, body = source_text[: doc.end()], source_text[doc.end():]
        parts = re.split(r"(\n[ \t]*\n+)", body)
        chunks = [(parts[i], parts[i + 1] if i + 1 < len(parts) else "", None)
                  for i in range(0, len(parts), 2)]
        if head:
            chunks = [(head, "", "frozen")] + chunks
    else:
        chunks = _chunks

    if style_corpus and len(re.findall(r"[\u4e00-\u9fff]", source_text)) > 0.3 * max(len(source_text), 1):
        raise PipelineError("style calibration supports English text only for now — omit --style-corpus")
    profile = load_style(style) if style else {}
    if style and not profile:
        raise PipelineError(f"journal style '{style}' not found in config/journals/")
    journal = profile.get("name", journal)
    ctx = load_context(bib=bib, glossary=glossary, style=style)
    if bib and ctx.bib is None:
        raise PipelineError(f".bib file not found: {bib}")
    extra = Path(run / ".extra_phrases.txt")
    phrases = None
    if profile.get("extra_phrases"):
        from .audit import DEFAULT_PHRASES
        extra.write_text(DEFAULT_PHRASES.read_text(encoding="utf-8") + "\n"
                         + "\n".join(profile["extra_phrases"]) + "\n", encoding="utf-8")
        phrases = extra

    # section-wide notes: abbreviations, spelling, citations need the whole text
    notes = term_hints(source_text, ctx.glossary, ctx.spelling) + bib_hints(source_text, ctx.bib)
    (run / "section_notes.txt").write_text(
        "\n".join(notes) + "\n" if notes else "(no section-level notes)\n", encoding="utf-8")

    width = max(2, len(str(len(chunks))))
    units = []
    for n, (content, sep, kind_override) in enumerate(chunks, 1):
        uid = f"u{n:0{width}d}"
        kind, words = _classify(content)
        if kind_override:
            kind = kind_override
        extra = (_unit_extra or [{}] * len(chunks))[n - 1]
        d = _udir(run, uid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "original.tex").write_text(content, encoding="utf-8")
        if kind == "prose":
            res = mask(content)
            # latex: placeholder -> LaTeX; docx/text: placeholders already in the text map to themselves
            mapping = res.mapping or {m.group(0): m.group(0) for m in PLACEHOLDER_RE.finditer(content)}
            (d / "masked.txt").write_text(res.text, encoding="utf-8")
            (d / "map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
            if extra.get("display"):
                (d / "legend.md").write_text(_legend(extra["display"]), encoding="utf-8")
                (d / "display.json").write_text(json.dumps(extra["display"], ensure_ascii=False),
                                                encoding="utf-8")
            a = audit(content, phrases) if phrases else audit(content)
            lines = [f"{a['words']} words · {a['ai_phrases']} AI phrases · "
                     f"{a['strong_claims']} strong-claim words"]
            lines += [f"[{h['kind']}] {h['term']!r}: …{h['excerpt']}…" for h in a["hits"]]
            lines += [f"[hint] {h}" for h in term_hints(content, ctx.glossary, ctx.spelling)
                      if not h.startswith("abbreviation")]  # abbreviations are section-level
            (d / "audit.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        units.append({
            "id": uid, "kind": kind, "words": words, "sep": sep,
            "attempts": 0, "last_hash": None, "last_passed": None, "reverted": False,
            "gates": [], "reopened": 0,
            "style_attempts": 0, "style_hash": None, "style_passed": None,
            "style_done": False, "style_gates": [],
            **{k: v for k, v in extra.items() if k != "display"},
        })

    state = {
        "name": name, "source": source, "journal": journal, "level": level,
        "style": style, "bib": bib, "glossary": glossary,
        "style_corpus": style_corpus, "section_type": _section_of(source_text),
        "max_style_attempts": MAX_STYLE_ATTEMPTS, "format": fmt,
        "created": _now(), "max_attempts": MAX_ATTEMPTS,
        "units": units, "decisions": [], "final": None,
    }
    state.update(_state_extra or {})
    render_graph(run, state)
    _save(run, state)
    return state


_KIND_NAMES = {"EQ": "equation", "CITE": "citation", "REF": "cross-reference", "SEQ": "caption number",
               "FLD": "field", "FMT": "formatted text", "LINK": "hyperlink", "OBJ": "object",
               "BM": "bookmark (invisible)", "MK": "comment anchor (invisible)"}


def _legend(display: dict) -> str:
    lines = ["# Protected objects in this paragraph", "",
             "Keep every placeholder exactly once. Move one only with the words it belongs to.", "",
             "| Placeholder | What it is | Shows as |", "|---|---|---|"]
    for k, v in display.items():
        kind = PLACEHOLDER_RE.match(k).group(1)
        lines.append(f"| {k} | {_KIND_NAMES.get(kind, kind)} | {v.replace('|', '/') or '—'} |")
    return "\n".join(lines) + "\n"


def split_docx(path: Path | str, run: Path, **kw) -> dict:
    from . import docx as dx
    from .style import section_type
    doc = dx.read(path)
    run.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, run / "original.docx")
    paras = doc.paragraphs
    chunks = [(p.text, "\n\n" if i < len(paras) - 1 else "",
               "frozen" if (p.heading or p.tracked) else None) for i, p in enumerate(paras)]
    extra = [{"docx_index": p.index, "display": p.display} for p in paras]
    head = next((p.text for p in paras if p.heading and p.text.strip()), "")
    return split("\n\n".join(p.text for p in paras), run, fmt="docx", source=str(path),
                 _chunks=chunks, _unit_extra=extra,
                 _state_extra={"section_type": section_type(head) if head else "other"}, **kw)


def _export_docx(run: Path, state: dict) -> dict:
    from . import docx as dx
    doc = dx.read(run / "original.docx")
    new = {}
    for u in state["units"]:
        if u.get("docx_index") is None or u["kind"] != "prose":
            continue
        d = _udir(run, u["id"])
        s = unit_status(run, u, state)
        if s == "styled":
            new[u["docx_index"]] = (d / "styled.tex").read_text(encoding="utf-8")
        elif _base_status(run, u) == "passed":
            new[u["docx_index"]] = (d / "revised.tex").read_text(encoding="utf-8")
    n = dx.write(doc, new, run / "revised_tracked.docx", tracked=True)
    dx.write(doc, new, run / "revised_clean.docx", tracked=False)
    return {"paragraphs_changed": n, "tracked": "revised_tracked.docx", "clean": "revised_clean.docx"}


# ------------------------------------------------------------------ status

def unit_status(run: Path, u: dict, state: dict | None = None) -> str:
    base = _base_status(run, u)
    if base != "passed" or not (state and state.get("style_corpus")):
        return base
    ms = _udir(run, u["id"]) / "masked_styled.txt"
    if u.get("style_done"):
        changed = ms.exists() and _hash(ms.read_text(encoding="utf-8")) != u.get("style_hash")
        left = u.get("style_attempts", 0) < state.get("max_style_attempts", MAX_STYLE_ATTEMPTS)
        if changed and left:
            return "needs-style-gate"  # edited after acceptance: must be checked again
        return "styled" if u.get("style_passed") else "style-kept-rewrite"
    if ms.exists() and _hash(ms.read_text(encoding="utf-8")) != u.get("style_hash"):
        return "needs-style-gate"
    return "style-failed" if u.get("style_attempts") else "needs-style"


def _base_status(run: Path, u: dict) -> str:
    if u["kind"] == "frozen":
        return "frozen"
    if u["reverted"]:
        return "reverted"
    d = _udir(run, u["id"])
    if not (d / "issues.md").exists():
        return "needs-audit"
    mr = d / "masked_revised.txt"
    if not mr.exists():
        return "needs-rewrite"
    if _hash(mr.read_text(encoding="utf-8")) != u["last_hash"]:
        return "needs-gate"
    return "passed" if u["last_passed"] else "failed"


def status(run: Path) -> dict:
    state = load(run)
    by: dict[str, list[str]] = {}
    for u in state["units"]:
        by.setdefault(unit_status(run, u, state), []).append(u["id"])
    prose_open = [s for s in by if s not in FINAL]
    if by.get("needs-audit"):
        nxt = "spawn auditor for: " + " ".join(by["needs-audit"])
    elif by.get("needs-rewrite") or by.get("failed"):
        ids = by.get("needs-rewrite", []) + by.get("failed", [])
        nxt = "spawn one rewriter per unit (parallel): " + " ".join(ids)
    elif by.get("needs-gate"):
        nxt = "run gate for: " + " ".join(by["needs-gate"])
    elif by.get("needs-style") or by.get("style-failed"):
        ids = by.get("needs-style", []) + by.get("style-failed", [])
        nxt = "spawn one style-calibrator per unit (parallel): " + " ".join(ids)
    elif by.get("needs-style-gate"):
        nxt = "run style-gate for: " + " ".join(by["needs-style-gate"])
    elif not state["final"]:
        nxt = "assemble"
    elif not (run / "claims.md").exists():
        nxt = "spawn claim-checker"
    else:
        nxt = "done — present report.md"
    return {"by_status": by, "open": bool(prose_open), "next": nxt, "final": state["final"]}


# ------------------------------------------------------------------ gate

@_with_format
def gate(run: Path, uid: str, recheck: bool = False) -> dict:
    """recheck=True re-runs the checks on an already-gated file (e.g. after the checker
    itself was updated) without using up an attempt."""
    with _locked(run):
        state = load(run)
        u = _unit(state, uid)
        if u["kind"] == "frozen":
            return {"unit": uid, "status": "frozen", "message": "frozen unit — nothing to gate"}
        if u["reverted"]:
            return {"unit": uid, "status": "reverted",
                    "message": "attempt limit reached; original text kept"}
        d = _udir(run, uid)
        mr = d / "masked_revised.txt"
        if not mr.exists():
            raise PipelineError(f"{uid}: masked_revised.txt not written yet")
        text = mr.read_text(encoding="utf-8")
        h = _hash(text)

        if h == u["last_hash"] and not recheck:  # same file gated before (hook + manual call)
            last = u["gates"][-1]
            return {"unit": uid, "status": "passed" if last["passed"] else "failed",
                    "cached": True, "attempts": u["attempts"], "max": state["max_attempts"],
                    "findings": last["findings"]}

        rechecking = recheck and h == u["last_hash"]
        if not rechecking:
            u["attempts"] += 1
        mapping = json.loads((d / "map.json").read_text(encoding="utf-8"))
        try:
            revised = unmask(text, mapping)
        except UnmaskError as e:
            findings = [{"level": "error", "layer": "L0-placeholder", "message": str(e)}]
            passed = False
        else:
            original = (d / "original.tex").read_text(encoding="utf-8")
            # keep the original paragraph's surrounding whitespace so assembly is byte-faithful
            lead = original[: len(original) - len(original.lstrip())]
            trail = original[len(original.rstrip()):]
            revised = lead + revised.strip() + trail
            (d / "revised.tex").write_text(revised, encoding="utf-8")
            rep = compare(original, revised, _ctx(run, state))
            findings = [f.__dict__ for f in rep.findings]
            passed = rep.passed

        entry = {"attempt": u["attempts"], "hash": h, "passed": passed,
                 "findings": findings, "time": _now()}
        if rechecking:
            entry["recheck"] = True
            u["gates"][-1] = entry
            state["decisions"].append(f"{_now()} {uid}: re-checked with updated checker — "
                                      f"{'pass' if passed else 'fail'}")
        else:
            u["gates"].append(entry)
        u["last_hash"], u["last_passed"] = h, passed

        if not passed and u["attempts"] >= state["max_attempts"]:
            u["reverted"] = True
            state["decisions"].append(
                f"{_now()} {uid}: failed {u['attempts']} gates — original text kept")

        _save(run, state)
        st = "passed" if passed else ("reverted" if u["reverted"] else "failed")
        return {"unit": uid, "status": st, "cached": False, "attempts": u["attempts"],
                "max": state["max_attempts"], "findings": findings}


def reopen(run: Path, uid: str, reason: str) -> dict:
    """Correction loop: send a passed unit back to the rewriter with a reason
    (e.g. from the claim-checker). Attempts keep counting toward the limit."""
    with _locked(run):
        state = load(run)
        u = _unit(state, uid)
        if u["kind"] == "frozen":
            raise PipelineError(f"{uid} is frozen")
        if u["reverted"]:
            raise PipelineError(f"{uid} already hit the attempt limit")
        if u["attempts"] >= state["max_attempts"]:
            raise PipelineError(f"{uid} has no attempts left ({u['attempts']}/{state['max_attempts']})")
        d = _udir(run, uid)
        mr = d / "masked_revised.txt"
        if mr.exists():
            (d / "attempts").mkdir(exist_ok=True)
            mr.replace(d / "attempts" / f"masked_revised.{u['attempts']}.txt")
        with open(d / "feedback.md", "a", encoding="utf-8") as fh:
            fh.write(f"- ({_now()}) {reason.strip()}\n")
        ms = d / "masked_styled.txt"
        if ms.exists():
            (d / "attempts").mkdir(exist_ok=True)
            ms.replace(d / "attempts" / f"masked_styled.{u['attempts']}.txt")
        u.update(style_attempts=0, style_hash=None, style_passed=None, style_done=False)
        u["reopened"] += 1
        u["last_hash"] = None
        state["final"] = None  # section must be reassembled
        state["decisions"].append(f"{_now()} {uid}: reopened — {reason.strip()}")
        _save(run, state)
        return {"unit": uid, "status": "needs-rewrite", "attempts_left":
                state["max_attempts"] - u["attempts"]}


# ------------------------------------------------------------------ assemble + final gate

@_with_format
def assemble(run: Path, partial: bool = False) -> dict:
    with _locked(run):
        state = load(run)
        out, open_units = [], []
        for u in state["units"]:
            d = _udir(run, u["id"])
            s = unit_status(run, u, state)
            if s not in FINAL:
                open_units.append(f"{u['id']}({s})")
            if s == "styled":
                body = (d / "styled.tex").read_text(encoding="utf-8")
            elif _base_status(run, u) == "passed":
                body = (d / "revised.tex").read_text(encoding="utf-8")
            else:
                body = (d / "original.tex").read_text(encoding="utf-8")
            out.append(body + u["sep"])
        if open_units and not partial:
            raise PipelineError("units not finished: " + ", ".join(open_units)
                                + " — finish them or pass --partial")

        original = (run / "original.tex").read_text(encoding="utf-8")
        revised = "".join(out)
        (run / "revised.tex").write_text(revised, encoding="utf-8")
        rep = compare(original, revised, _ctx(run, state))
        a0, a1 = audit(original), audit(revised)
        state["final"] = {
            "passed": rep.passed, "partial": bool(open_units), "open_units": open_units,
            "findings": [f.__dict__ for f in rep.findings], "time": _now(),
            "audit_before": {k: a0[k] for k in ("words", "ai_phrases",
                                                "ai_phrases_per_1000_words", "strong_claims")},
            "audit_after": {k: a1[k] for k in ("words", "ai_phrases",
                                               "ai_phrases_per_1000_words", "strong_claims")},
        }
        if state.get("style_corpus"):
            state["final"]["style"] = _style_metrics(run, state)
        if state.get("format") == "docx":
            state["final"]["docx"] = _export_docx(run, state)
        _save(run, state)
        render_report(run, state)
        return state["final"]


def _style_metrics(run: Path, state: dict) -> dict:
    from . import style as stylemod
    index = stylemod.load(state["style_corpus"])
    sec = state.get("section_type")
    fref = load_style(state["style"]).get("figure_ref") if state.get("style") else None
    dist = lambda tex: stylemod.distance(index, stylemod.prose_of(tex), sec, fref)["score"]
    units = {}
    for u in state["units"]:
        if u["kind"] != "prose":
            continue
        d = _udir(run, u["id"])
        row = {"original": dist((d / "original.tex").read_text(encoding="utf-8"))}
        if (d / "revised.tex").exists() and _base_status(run, u) == "passed":
            row["rewrite"] = dist((d / "revised.tex").read_text(encoding="utf-8"))
        if unit_status(run, u, state) == "styled":
            row["styled"] = dist((d / "styled.tex").read_text(encoding="utf-8"))
        units[u["id"]] = row
    return {"section_before": dist((run / "original.tex").read_text(encoding="utf-8")),
            "section_after": dist((run / "revised.tex").read_text(encoding="utf-8")),
            "units": units, "section_type": sec}


# ------------------------------------------------------------------ style gate (A4)

@_with_format
def style_gate(run: Path, uid: str) -> dict:
    """Check a style-calibrated paragraph against the ORIGINAL with every content
    check, plus text recycling from the author's earlier papers. Failing twice keeps
    the rewriter's passed version — it never reverts to the original."""
    from . import style as stylemod
    with _locked(run):
        state = load(run)
        if not state.get("style_corpus"):
            raise PipelineError("this run has no style corpus (split --style-corpus)")
        u = _unit(state, uid)
        if _base_status(run, u) != "passed":
            raise PipelineError(f"{uid}: the rewrite must pass its gate before style calibration")
        mx = state.get("max_style_attempts", MAX_STYLE_ATTEMPTS)
        d = _udir(run, uid)
        ms = d / "masked_styled.txt"
        if not ms.exists():
            raise PipelineError(f"{uid}: masked_styled.txt not written yet")
        text = ms.read_text(encoding="utf-8")
        h = _hash(text)
        if u["style_done"]:
            if h != u["style_hash"] and u["style_attempts"] < mx:
                u["style_done"] = False  # edited after acceptance: check the new version
            else:
                last = u["style_gates"][-1]["findings"] if u["style_gates"] else []
                note = ([{"level": "warning", "layer": "S-ignored",
                          "message": "no style attempts left — this edit was NOT checked and is "
                                     "ignored; the last accepted version is kept"}]
                        if h != u["style_hash"] else [])
                return {"unit": uid, "status": "styled" if u["style_passed"] else "kept-rewrite",
                        "cached": True, "attempts": u["style_attempts"], "max": mx,
                        "findings": last + note, "stage": "style"}
        if h == u["style_hash"] and u["style_gates"]:
            last = u["style_gates"][-1]
            return {"unit": uid, "status": "styled" if last["passed"] else "failed",
                    "cached": True, "attempts": u["style_attempts"], "max": mx,
                    "findings": last["findings"]}

        u["style_attempts"] += 1
        mapping = json.loads((d / "map.json").read_text(encoding="utf-8"))
        original = (d / "original.tex").read_text(encoding="utf-8")
        try:
            styled = unmask(text, mapping)
        except UnmaskError as e:
            findings = [{"level": "error", "layer": "L0-placeholder", "message": str(e)}]
        else:
            lead = original[: len(original) - len(original.lstrip())]
            trail = original[len(original.rstrip()):]
            styled = lead + styled.strip() + trail
            findings = [f.__dict__ for f in compare(original, styled, _ctx(run, state)).findings]
            index = stylemod.load(state["style_corpus"])
            for seq in stylemod.recycled(index, stylemod.prose_of(original), stylemod.prose_of(styled)):
                findings.append({"level": "error", "layer": "L7-recycle",
                                 "message": f"copied from an earlier paper: '{seq}'"})
            revised = (d / "revised.tex").read_text(encoding="utf-8")
            if audit(styled)["ai_phrases"] > audit(revised)["ai_phrases"]:
                findings.append({"level": "warning", "layer": "S-ai-phrase",
                                 "message": "style pass re-introduced template phrasing"})
        passed = not any(f["level"] == "error" for f in findings)
        if passed:
            (d / "styled.tex").write_text(styled, encoding="utf-8")
        u["style_gates"].append({"attempt": u["style_attempts"], "hash": h, "passed": passed,
                                 "findings": findings, "time": _now()})
        u["style_hash"], u["style_passed"] = h, passed
        if passed:
            u["style_done"] = True
        elif u["style_attempts"] >= mx:
            u["style_done"] = True
            state["decisions"].append(
                f"{_now()} {uid}: style pass failed {u['style_attempts']} gates — rewrite kept")
        _save(run, state)
        st = "styled" if passed else ("kept-rewrite" if u["style_done"] else "failed")
        return {"unit": uid, "status": st, "cached": False, "attempts": u["style_attempts"],
                "max": mx, "findings": findings, "stage": "style"}


# ------------------------------------------------------------------ views

def render_graph(run: Path, state: dict) -> None:
    prose = [u["id"] for u in state["units"] if u["kind"] == "prose"]
    frozen = [u["id"] for u in state["units"] if u["kind"] == "frozen"]
    lines = [
        f"# Task graph · {state['name']}", "",
        f"Journal: {state['journal']} (style: {state.get('style') or '—'}) · "
        f"bib: {state.get('bib') or '—'} · level: {state['level']} · "
        f"max attempts per unit: {state['max_attempts']}", "",
        "## Done when",
        "- Every prose unit is `passed` or `reverted` (original kept after "
        f"{state['max_attempts']} failed gates).",
        "- Final section gate passes (no `[error]`).",
        "- claims.md exists and every reopen it caused is resolved.",
        "- report.md is generated.", "",
        "## Nodes", "",
        "| Node | Type | Input | Output | Check |",
        "|---|---|---|---|---|",
        "| C1 split | code | original.tex | units/*, audit.txt | — |",
        f"| A1 audit | LLM ×1 (auditor) | masked.txt + audit.txt of {len(prose)} units | issues.md per unit | each issue quotes its sentence |",
        "| A2 rewrite uNN | LLM ×N parallel (rewriter) | masked.txt, issues.md, feedback.md | masked_revised.txt, changes.md | G uNN |",
        "| G uNN | code (hook) | masked_revised.txt | revised.tex, run.json | unmask + compare: 0 errors |",
        *(["| A4 style uNN | LLM ×N parallel (style-calibrator) | masked_revised.txt, style brief | masked_styled.txt, style_changes.md | S uNN |",
            "| S uNN | code (hook) | masked_styled.txt | styled.tex | compare vs original + no 10-word recycling; ≤2 tries, else keep rewrite |"]
          if state.get("style_corpus") else []),
        "| C assemble + G* | code | units | revised.tex | full-section compare: 0 errors |",
        "| A3 claims | LLM ×1 (claim-checker) | revised.tex + original.tex | claims.md, reopen requests | claim never stronger than evidence |",
        "| C5 report | code | run.json, changes.md, claims.md | report.md | — |", "",
        "## Edges", "",
        "```",
        "C1 → A1 → A2[uNN] → G[uNN] ─fail(≤3)→ A2[uNN]",
        "                         └pass→ C assemble → G* → A3 ─reopen→ A2[uNN]",
        "                                                   └ok→ C5",
        "```", "",
        f"Prose units: {' '.join(prose) or '—'}  ",
        f"Frozen units (passed through unchanged): {' '.join(frozen) or '—'}", "",
        "## Code nodes (never delegated to a model)",
        "split, mask/unmask, audit scan, gate (compare), retry/revert bookkeeping, "
        "assemble, report merge.",
    ]
    (run / "graph.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_progress(run: Path, state: dict) -> None:
    rows = ["| Unit | Kind | Words | Status | Attempts | Reopened |", "|---|---|---|---|---|---|"]
    for u in state["units"]:
        rows.append(f"| {u['id']} | {u['kind']} | {u['words']} | {unit_status(run, u, state)} | "
                    f"{u['attempts']}/{state['max_attempts']} | {u['reopened']} |")
    st = status(run) if (run / "run.json").exists() else {"next": "?"}
    final = state["final"]
    final_line = ("not assembled" if not final else
                  f"{'PASS' if final['passed'] else 'FAIL'}"
                  f"{' (partial)' if final['partial'] else ''} at {final['time']}")
    lines = [f"# Progress · {state['name']}", "", *rows, "",
             f"**Final gate:** {final_line}  ", f"**Next:** {st['next']}", "",
             "## Decisions", *(f"- {d}" for d in state["decisions"] or ["(none)"]), "",
             "Resume: read graph.md and this file, then run "
             f"`python3 -m checker status {run}`."]
    (run / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evidence(findings: list[dict], limit: int = 3) -> str:
    if not findings:
        return "no findings"
    shown = "; ".join(f"{f['layer']}: {f['message']}" for f in findings[:limit])
    more = f" (+{len(findings) - limit} more)" if len(findings) > limit else ""
    return (shown + more).replace("|", "\\|")


def render_checks(run: Path, state: dict) -> None:
    rows = ["| Node | Check | Result | Evidence |", "|---|---|---|---|"]
    for u in state["units"]:
        for g in u["gates"]:
            errs = [f for f in g["findings"] if f["level"] == "error"]
            warns = [f for f in g["findings"] if f["level"] == "warning"]
            result = "pass" if g["passed"] else "fail"
            if warns and g["passed"]:
                result = f"pass ({len(warns)} warnings)"
            rows.append(f"| G {u['id']} #{g['attempt']} | unmask + compare | {result} | "
                        f"{_evidence(errs or warns)} |")
        if u["reverted"]:
            rows.append(f"| G {u['id']} | attempt limit | unresolved | original text kept |")
        for g in u.get("style_gates", []):
            errs = [f for f in g["findings"] if f["level"] == "error"]
            warns = [f for f in g["findings"] if f["level"] == "warning"]
            result = "pass" if g["passed"] else "fail"
            if warns and g["passed"]:
                result = f"pass ({len(warns)} warnings)"
            rows.append(f"| S {u['id']} #{g['attempt']} | style: compare + recycle | {result} | "
                        f"{_evidence(errs or warns)} |")
    f = state["final"]
    if f:
        res = ("pass" if f["passed"] else "fail") + (" (partial)" if f["partial"] else "")
        rows.append(f"| G* section | full compare | {res} | {_evidence(f['findings'])} |")
    (run / "checks.md").write_text(f"# Checks · {state['name']}\n\n" + "\n".join(rows) + "\n",
                                   encoding="utf-8")


def render_report(run: Path, state: dict) -> None:
    f = state["final"]
    revised = (run / "revised.tex").read_text(encoding="utf-8")
    out = [f"# 修改报告 · {state['name']}", "",
           f"目标期刊：{state['journal']} · 改写程度：{state['level']}", "",
           "## 1. 修改后文本", "", "```latex", revised.rstrip(), "```", "",
           "## 2. 各段修改", ""]
    for u in state["units"]:
        if u["kind"] != "prose":
            continue
        d = _udir(run, u["id"])
        s = unit_status(run, u, state)
        out.append(f"### {u['id']} · {s} · 校验 {u['attempts']} 次"
                   + (f" · 重开 {u['reopened']} 次" if u["reopened"] else ""))
        out.append("")
        if s == "reverted":
            last = u["gates"][-1]["findings"] if u["gates"] else []
            errs = [x for x in last if x["level"] == "error"]
            out.append(f"已保留原文：{u['attempts']} 次校验未通过。最后一次错误：{_evidence(errs, 5)}")
        elif (d / "changes.md").exists():
            out.append((d / "changes.md").read_text(encoding="utf-8").strip())
        else:
            out.append("（无 changes.md）")
        warns = [x for x in (u["gates"][-1]["findings"] if u["gates"] else [])
                 if x["level"] == "warning"] if _base_status(run, u) == "passed" else []
        if state.get("style_corpus") and s in ("styled", "style-kept-rewrite"):
            sm = (state["final"] or {}).get("style", {}).get("units", {}).get(u["id"], {})
            dist = " → ".join(f"{k} {v}" for k, v in sm.items())
            out += ["", f"风格校准：{'已采用' if s == 'styled' else '未通过校验，保留改写版'}"
                    f"（风格距离 {dist}）"]
            sc = d / "style_changes.md"
            if s == "styled" and sc.exists():
                out += ["", sc.read_text(encoding="utf-8").strip()]
        if warns:
            out += ["", "校验提醒：", *(f"- {w['layer']}: {w['message']}" for w in warns)]
        out.append("")

    out += ["## 3. 论断检查", ""]
    claims = run / "claims.md"
    out.append(claims.read_text(encoding="utf-8").strip() if claims.exists() else "（尚未运行）")
    out.append("")

    b, a = f["audit_before"], f["audit_after"]
    reverted = [u["id"] for u in state["units"] if u["reverted"]]
    out += ["## 4. 校验与指标", "",
            f"- 整节终审：{'PASS' if f['passed'] else 'FAIL'}"
            + ("（部分完成：" + ", ".join(f["open_units"]) + " 未完成，使用原文）"
               if f["partial"] else ""),
            *(f"  - [{x['level']}] {x['layer']}: {x['message']}" for x in f["findings"]),
            f"- AI 套话密度：{b['ai_phrases_per_1000_words']} → {a['ai_phrases_per_1000_words']}"
            f"（每千词）；强论断词：{b['strong_claims']} → {a['strong_claims']}",
            f"- 字数：{b['words']} → {a['words']}",
            *([f"- 风格距离（越小越像你，按 {f['style']['section_type']} 段落画像）："
               f"{f['style']['section_before']} → {f['style']['section_after']}"]
              if f.get("style") else []),
            f"- 保留原文的段落：{', '.join(reverted) or '无'}",
            *([f"- Word 输出：{f['docx']['tracked']}（修订模式，可在 Word 中逐条接受/拒绝）、"
               f"{f['docx']['clean']}（干净版）；改动段落 {f['docx']['paragraphs_changed']} 个"]
              if f.get("docx") else []),
            "- 逐次校验记录见 checks.md", "",
            "> 投稿时请按期刊政策说明 AI 辅助编辑的使用情况。"]
    (run / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
