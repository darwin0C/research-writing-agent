"""M3: personal style library — profile, retrieval, distance, recycling check.

Built from the author's own earlier papers (style_corpus/), with no third-party
packages:

  profile   measurable habits per section type (sentence length, "we" vs passive,
            "Figure" vs "Fig.", tense, connectives, hedging, nominalisations …)
  retrieve  BM25 over paragraphs: the author's most similar earlier paragraphs
  distance  how far a text sits from the author's habits (mean |z|, per feature)
  recycle   10-word sequences copied from earlier papers (text recycling)
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

from .invariants import split_sentences
from .latex_mask import mask, strip_placeholders
from .terms import spelling_profile

# ------------------------------------------------------------------ text helpers

STOP = set("""a an the and or but if of in on at to for from by with without within into onto
over under between among as is are was were be been being this that these those it its
we our us they their them he she his her which who whom whose what when where while than
then there here so such not no nor can could may might will would shall should do does did
has have had also both each either more most other some any all very about above below up
down out off only own same too just via et al i e g fig figs eq eqs ref refs""".split())

SECTION_KEYS = [
    ("abstract", r"abstract"),
    ("conclusion", r"conclu|summary|outlook"),
    ("results", r"result|discussion|analysis"),
    ("methods", r"method|model|simulation|numerical|experiment|setup|set-up|procedure|material"),
    ("intro", r"introduc|background|literature|motivation"),
]

_HEADING = re.compile(r"\\(?:section|chapter)\*?\s*\{([^{}]*)\}|\\begin\{abstract\}", re.I)


def section_type(heading: str) -> str:
    h = heading.lower()
    for name, pat in SECTION_KEYS:
        if re.search(pat, h):
            return name
    return "other"


def prose_of(tex: str) -> str:
    """Readable prose: protected LaTeX removed, remaining commands unwrapped."""
    p = strip_placeholders(mask(tex).text)
    p = re.sub(r"\\(?:emph|textit|textbf|textrm|mathrm|text)\{([^{}]*)\}", r"\1", p)
    p = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", p)
    p = p.replace("~", " ").replace("{", "").replace("}", "")
    return re.sub(r"[ \t]+", " ", p).strip()


def readable(tex: str) -> str:
    """For human reading (blind sheets): citations → [cite], refs → [ref], math kept."""
    from .latex_mask import PLACEHOLDER_RE
    res = mask(tex)

    def sub(m):
        kind = m.group(1)
        orig = res.mapping.get(m.group(0), "")
        if kind == "CITE":
            return "[cite]"
        if kind == "REF":
            return "[ref]"
        if kind in ("MATH", "EQ", "QTY"):
            return orig or "[eq]"
        if not res.mapping:  # docx/text: placeholders were never LaTeX
            return {"FMT": "[x]", "LINK": "[link]", "SEQ": "[n]"}.get(kind, "")
        return ""
    t = PLACEHOLDER_RE.sub(sub, res.text).replace("~", " ")
    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"[ \t]+", " ", t)).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text)


def _stem(w: str) -> str:
    w = w.lower()
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(text: str) -> list[str]:
    return [_stem(w) for w in words(text) if w.lower() not in STOP and len(w) > 2]


# ------------------------------------------------------------------ features

CONNECTIVES = ["however", "moreover", "furthermore", "therefore", "thus", "hence",
               "in addition", "consequently", "whereas", "nevertheless", "meanwhile",
               "in contrast", "accordingly", "notably", "additionally"]
HEDGE_WORDS = ["may", "might", "could", "likely", "possibly", "suggest", "suggests",
               "appear", "appears", "presumably"]
STUDY_PHRASES = ["this work", "this study", "the present study", "the present work",
                 "this paper", "the current study"]
_PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?"
                      r"(?:\w+ed|\w+en|made|done|shown|seen|found|given|taken|known|built|"
                      r"set|put|kept|held|run|led|left|brought|thought|sought)\b", re.I)
_PAST_AUX = re.compile(r"\b(?:was|were|had)\b", re.I)
_PRES_AUX = re.compile(r"\b(?:is|are|has|have|shows|show|indicates|suggests)\b", re.I)
_NOMINAL = re.compile(r"\b\w{3,}(?:tion|tions|ment|ments|ance|ances|ence|ences|ity|ities)\b", re.I)

# (feature key, label, how to read a high value)
NUMERIC = [
    ("sent_len", "mean sentence length (words)"),
    ("long_share", "share of sentences > 35 words"),
    ("we_rate", "we/our/us per 1000 words"),
    ("passive_share", "share of sentences with passive voice"),
    ("past_share", "past-tense share of auxiliaries"),
    ("connective_rate", "connectives per 1000 words"),
    ("hedge_rate", "hedges per 1000 words"),
    ("nominal_rate", "nominalisations per 100 words"),
]


def features(prose: str) -> dict:
    ws = words(prose)
    n = max(len(ws), 1)
    sents = [s for s in split_sentences(prose) if words(s)]
    lens = [len(words(s)) for s in sents] or [0]
    low = prose.lower()

    def rate(terms, per=1000):
        c = sum(len(re.findall(r"\b" + re.escape(t) + r"\b", low)) for t in terms)
        return c * per / n

    past, pres = len(_PAST_AUX.findall(prose)), len(_PRES_AUX.findall(prose))
    fig_full = len(re.findall(r"\bFigures?\b", prose))
    fig_abbr = len(re.findall(r"\bFigs?\.", prose))
    openers = Counter()
    for s in sents:
        w = words(s)[:2]
        if w:
            openers[" ".join(x.lower() for x in w)] += 1
    sp = spelling_profile(prose)
    return {
        "words": len(ws),
        "sentences": len(sents),
        "sent_len": statistics.mean(lens),
        "long_share": sum(l > 35 for l in lens) / max(len(sents), 1),
        "we_rate": rate(["we", "our", "us"]),
        "passive_share": sum(bool(_PASSIVE.search(s)) for s in sents) / max(len(sents), 1),
        "past_share": past / (past + pres) if past + pres else None,
        "connective_rate": rate(CONNECTIVES),
        "hedge_rate": rate(HEDGE_WORDS),
        "nominal_rate": len(_NOMINAL.findall(prose)) * 100 / n,
        "fig_full": fig_full, "fig_abbr": fig_abbr,
        "study_phrase": {p: low.count(p) for p in STUDY_PHRASES if p in low},
        "openers": dict(openers),
        "spelling_us": len(sp["US"]), "spelling_uk": len(sp["UK"]),
    }


# ------------------------------------------------------------------ corpus build

def _paragraphs_with_sections(tex: str) -> list[tuple[str, str]]:
    body = tex
    m = re.search(r"\\begin\{document\}", tex)
    if m:
        body = tex[m.end():]
    body = re.split(r"\\begin\{thebibliography\}|\\bibliography\{|\\printbibliography", body)[0]
    out, current = [], "other"
    for chunk in re.split(r"\n[ \t]*\n+", body):
        for h in _HEADING.finditer(chunk):
            current = "abstract" if h.group(0).startswith("\\begin") else section_type(h.group(1))
        prose = prose_of(chunk)
        if len(words(prose)) >= 25:
            out.append((current, prose))
    return out


def build(paths: list[str], out_dir: Path) -> dict:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(x for x in p.rglob("*") if x.suffix in (".tex", ".txt", ".md")
                            and not x.name.lower().startswith("readme"))
        elif p.exists():
            files.append(p)
    if not files:
        raise FileNotFoundError("no .tex/.txt/.md files found in: " + ", ".join(paths))

    paras = []
    for f in files:
        for sec, prose in _paragraphs_with_sections(f.read_text(encoding="utf-8", errors="replace")):
            paras.append({"id": f"p{len(paras) + 1:04d}", "source": f.name, "section": sec,
                          "text": prose, "features": features(prose)})
    if len(paras) < 5:
        raise ValueError(f"only {len(paras)} usable paragraphs — add more of your papers")

    index = {"files": [f.name for f in files], "paragraphs": paras,
             "profile": _profile(paras), "built": __import__("time").strftime("%Y-%m-%d %H:%M")}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "profile.md").write_text(render_profile(index), encoding="utf-8")
    return index


def _agg(paras: list[dict]) -> dict:
    out = {"n": len(paras)}
    for key, _ in NUMERIC:
        vals = [p["features"][key] for p in paras if p["features"].get(key) is not None]
        if vals:
            out[key] = {"mean": statistics.mean(vals),
                        "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0}
    fig_full = sum(p["features"]["fig_full"] for p in paras)
    fig_abbr = sum(p["features"]["fig_abbr"] for p in paras)
    out["fig_pref"] = ("Figure" if fig_full > fig_abbr else "Fig." if fig_abbr > fig_full else None)
    study = Counter()
    openers = Counter()
    us = uk = 0
    for p in paras:
        study.update(p["features"]["study_phrase"])
        openers.update(p["features"]["openers"])
        us += p["features"]["spelling_us"]
        uk += p["features"]["spelling_uk"]
    out["study_phrase"] = study.most_common(1)[0][0] if study else None
    out["openers"] = [o for o, _ in openers.most_common(8)]
    out["spelling"] = "UK" if uk > us else "US" if us > uk else None
    return out


def _profile(paras: list[dict]) -> dict:
    prof = {"all": _agg(paras)}
    for sec in {p["section"] for p in paras}:
        group = [p for p in paras if p["section"] == sec]
        if len(group) >= 3:
            prof[sec] = _agg(group)
    return prof


def load(corpus_dir: Path | str) -> dict:
    p = Path(corpus_dir) / "index.json"
    if not p.exists():
        raise FileNotFoundError(f"no style index at {p} — run `python3 -m checker style-build`")
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ retrieval (BM25)

def retrieve(index: dict, query: str, k: int = 3, section: str | None = None,
             k1: float = 1.5, b: float = 0.75) -> list[tuple[float, dict]]:
    paras = index["paragraphs"]
    docs = [tokens(p["text"]) for p in paras]
    avg = sum(map(len, docs)) / max(len(docs), 1)
    df = Counter(t for d in docs for t in set(d))
    N = len(docs)
    q = set(tokens(query))
    scored = []
    for p, d in zip(paras, docs):
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        if section and p["section"] == section:
            s *= 1.25
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return [x for x in scored[:k] if x[0] > 0]


# ------------------------------------------------------------------ distance

def _target(index: dict, section: str | None) -> tuple[dict, str]:
    prof = index["profile"]
    if section and section in prof and prof[section]["n"] >= 5:
        return prof[section], section
    return prof["all"], "all"


def distance(index: dict, prose: str, section: str | None = None,
             figure_ref: str | None = None) -> dict:
    """figure_ref: the journal's house style ("Fig."/"Figure"), which overrides the author."""
    f = features(prose)
    target, used = _target(index, section)
    if figure_ref in ("Fig.", "Figure"):
        target = {**target, "fig_pref": figure_ref}
    rows, zs = [], []
    for key, label in NUMERIC:
        v, t = f.get(key), target.get(key)
        if v is None or not t:
            continue
        sd = max(t["sd"], 0.15 * abs(t["mean"]), 0.02)
        z = max(-3.0, min(3.0, (v - t["mean"]) / sd))
        zs.append(abs(z))
        rows.append({"feature": key, "label": label, "value": round(v, 2),
                     "target": round(t["mean"], 2), "z": round(z, 2)})
    prefs = []
    who = "the journal uses" if figure_ref in ("Fig.", "Figure") else "you write"
    if target.get("fig_pref") == "Figure" and f["fig_abbr"]:
        prefs.append(f"{who} 'Figure', this text uses 'Fig.'")
    if target.get("fig_pref") == "Fig." and f["fig_full"]:
        prefs.append(f"{who} 'Fig.', this text uses 'Figure'")
    sp = target.get("study_phrase")
    other = [p for p in f["study_phrase"] if p != sp]
    if sp and other:
        prefs.append(f"you write '{sp}', this text uses '{other[0]}'")
    if target.get("spelling") == "UK" and f["spelling_us"]:
        prefs.append("you use UK spelling, this text has US forms")
    if target.get("spelling") == "US" and f["spelling_uk"]:
        prefs.append("you use US spelling, this text has UK forms")
    score = statistics.mean(zs) if zs else 0.0
    return {"score": round(score + 0.5 * len(prefs), 2), "rows": rows, "prefs": prefs,
            "profile_used": used, "words": f["words"]}


# ------------------------------------------------------------------ recycling

def _shingles(prose: str, n: int = 10) -> dict[tuple, str]:
    ws = [w.lower() for w in words(prose)]
    return {tuple(ws[i:i + n]): " ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def recycled(index: dict, original_prose: str, new_prose: str, n: int = 10) -> list[str]:
    """10-word sequences in the new text that come from the corpus but not from the original."""
    new = _shingles(new_prose, n)
    if not new:
        return []
    fresh = set(new) - set(_shingles(original_prose, n))
    if not fresh:
        return []
    corpus = set()
    for p in index["paragraphs"]:
        corpus |= set(_shingles(p["text"], n))
    hits = [new[s] for s in fresh if s in corpus]
    return sorted(hits)


# ------------------------------------------------------------------ rendering

def _hint(row: dict) -> str:
    z = row["z"]
    if abs(z) < 1:
        return "close"
    more = z > 0
    return {
        "sent_len": "shorter sentences" if more else "longer sentences",
        "long_share": "split long sentences" if more else "fine",
        "we_rate": "less first person" if more else "more 'we' (active voice)",
        "passive_share": "fewer passives" if more else "more passives",
        "past_share": "more present tense" if more else "more past tense",
        "connective_rate": "fewer connectives" if more else "more connectives",
        "hedge_rate": "fewer hedges (never remove needed ones)" if more else "fine — never add hedges that weaken claims",
        "nominal_rate": "more verbs, fewer -tion/-ment nouns" if more else "fine",
    }.get(row["feature"], "")


def render_profile(index: dict) -> str:
    lines = ["# Style profile", "",
             f"Built {index['built']} from {len(index['files'])} files, "
             f"{len(index['paragraphs'])} paragraphs.", ""]
    for sec, prof in index["profile"].items():
        lines += [f"## {sec} ({prof['n']} paragraphs)", "", "| Feature | Mean | SD |", "|---|---|---|"]
        for key, label in NUMERIC:
            if key in prof:
                lines.append(f"| {label} | {prof[key]['mean']:.2f} | {prof[key]['sd']:.2f} |")
        lines += ["", f"Figure style: {prof.get('fig_pref') or '—'} · study phrase: "
                  f"{prof.get('study_phrase') or '—'} · spelling: {prof.get('spelling') or '—'}",
                  f"Common sentence openers: {', '.join(prof.get('openers', [])) or '—'}", ""]
    return "\n".join(lines) + "\n"


def brief(index: dict, prose: str, section: str | None, k: int = 3,
          figure_ref: str | None = None) -> str:
    d = distance(index, prose, section, figure_ref)
    target, used = _target(index, section)
    lines = [f"# Style brief (profile: {used}, {target['n']} paragraphs)", "",
             f"Style distance of the current text: **{d['score']}** (0 = typical for you; "
             "below ~1 is close).", "",
             "| Feature | This text | Your typical | Direction |", "|---|---|---|---|"]
    for r in d["rows"]:
        lines.append(f"| {r['label']} | {r['value']} | {r['target']} | {_hint(r)} |")
    lines += ["", "Preferences:"]
    lines += [f"- {p}" for p in d["prefs"]] or ["- (no conflicts)"]
    if target.get("openers"):
        lines += ["", f"Your common sentence openers: {', '.join(target['openers'][:6])}"]
    lines += ["", "## Your most similar earlier paragraphs",
              "Use them for rhythm, voice and connectives only. **Do not copy wording** — "
              "10-word overlaps with earlier papers fail the gate.", ""]
    for score, p in retrieve(index, prose, k=k, section=section):
        text = " ".join(p["text"].split()[:140])
        lines += [f"**{p['source']} · {p['section']} · match {score:.1f}**", "", f"> {text}", ""]
    return "\n".join(lines) + "\n"
