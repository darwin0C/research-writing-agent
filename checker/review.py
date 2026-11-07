"""Point-by-point response to reviewers, with every claimed change verified.

  review-split   comments + original + revised manuscript → items/<id>/comment.md,
                 manuscript.md (revised text with section names) and changes.md (what changed)
  (responder agent, one per item) → items/<id>/response.md
  review-gate    checks one response against the manuscripts
  review-assemble → response_letter.md + response_letter.docx + review_checks.md

response.md format (written by the responder):

    Response: <reply to the reviewer>
    Change: <one line: what was changed — or "none" with the reason in Response>
    Location: <section name>
    Quote: <exact text from the revised manuscript>      (one line per quote; 0+)

Checks (errors fail the gate; 3 attempts, then the item is marked for the author):
  quote-missing    a quote is not found verbatim in the revised manuscript
  change-unbacked  the reply says something was revised/added/… but no quote lies in
                   text that actually changed between original and revised
  empty            no response text
Warnings: numbers in the reply that appear in neither manuscript nor comment;
"we will" promises; quotes outside the stated section; template phrasing.
"""

from __future__ import annotations

import contextlib
import difflib
import fcntl
import hashlib
import json
import re
import time
from pathlib import Path

from . import docx as dx
from .audit import audit
from .latex_mask import text_format
from .style import _HEADING, readable

MAX_ATTEMPTS = 3

CLAIMS_CHANGE = re.compile(
    r"\b(?:revised|rewritten|rephrased|added|inserted|modified|changed|updated|corrected|"
    r"clarified|expanded|extended|removed|deleted|replaced|included|reworded|toned down|"
    r"softened|now (?:states?|reads?|reports?|includes?|gives?|shows?))\b"
    r"|已(?:修改|补充|增加|删除|更正|改写|修正|调整|完善)|进行了(?:修改|补充|修正)", re.I)


# ------------------------------------------------------------------ manuscripts

def _norm(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("–", "-").replace("—", "-").replace("~", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def load_manuscript(path: Path | str) -> list[dict]:
    """Paragraphs with their section: [{"section", "text"}] (text readable, LaTeX removed)."""
    path = Path(path)
    out, section = [], "front"
    if path.suffix == ".docx":
        doc = dx.read(path)
        for p in doc.paragraphs:
            text = p.text
            for k, v in p.display.items():
                text = text.replace(k, v)
            if p.heading:
                section = text.strip() or section
                continue
            if text.strip():
                out.append({"section": section, "text": re.sub(r"\s+", " ", text).strip()})
        return out
    raw = path.read_text(encoding="utf-8")
    fmt = "latex" if path.suffix == ".tex" else "text"
    with text_format(fmt):
        for chunk in re.split(r"\n[ \t]*\n+", raw):
            for h in _HEADING.finditer(chunk):
                section = h.group(1) if h.group(1) else "Abstract"
            md = re.match(r"^\s*#+\s+(.+)$", chunk)
            if fmt == "text" and md:
                section = md.group(1).strip()
                continue
            text = readable(chunk) if fmt == "latex" else re.sub(r"\s+", " ", chunk).strip()
            text = re.sub(r"\\(?:section|subsection|chapter)\*?\{[^}]*\}", "", text).strip()
            if len(text.split()) >= 3 or len(text) >= 12:
                out.append({"section": section, "text": text})
    return out


def diff_manuscripts(orig: list[dict], rev: list[dict]) -> list[dict]:
    """Changed paragraphs of the revised manuscript (added or modified)."""
    a = [_norm(p["text"]) for p in orig]
    b = [_norm(p["text"]) for p in rev]
    changes = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for j in range(j1, j2):
            before = ""
            if op == "replace" and i1 < i2:
                best = max(range(i1, i2), key=lambda i: difflib.SequenceMatcher(a=a[i], b=b[j]).ratio())
                before = orig[best]["text"]
            changes.append({"index": j, "section": rev[j]["section"],
                            "kind": "modified" if before else "added",
                            "before": before, "after": rev[j]["text"]})
    return changes


# ------------------------------------------------------------------ comments

_REVIEWER = re.compile(r"^\s*(?:#+\s*)?(?:Reviewer|Referee|审稿人|评审专家)\s*#?\s*(\d+|[A-Z一二三四五])\b.*$",
                       re.I | re.M)
_ITEM = re.compile(r"^\s*(?:Comment\s*|Point\s*|Q|问题\s*|意见\s*)?\(?(\d{1,2})[\.\):：、](?:\s+|(?=[^\d\s]))",
                   re.I | re.M)


def parse_comments(text: str) -> list[dict]:
    blocks = []
    heads = list(_REVIEWER.finditer(text))
    if heads:
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            blocks.append((h.group(1), text[h.end():end]))
    else:
        blocks.append(("1", text))
    items = []
    for rid, body in blocks:
        rnum = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}.get(rid, rid)
        marks = list(_ITEM.finditer(body))
        if marks:
            parts = [(m.group(1), body[m.end(): marks[k + 1].start() if k + 1 < len(marks) else len(body)])
                     for k, m in enumerate(marks)]
        else:
            parts = [(str(k + 1), p) for k, p in enumerate(re.split(r"\n\s*\n", body)) if p.strip()]
        for num, ctext in parts:
            ctext = ctext.strip()
            if ctext:
                items.append({"id": f"R{rnum}.{int(num):02d}", "reviewer": rnum, "comment": ctext})
    return items


# ------------------------------------------------------------------ run

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@contextlib.contextmanager
def _locked(run: Path):
    """Responders run in parallel; serialise read-modify-write of review.json."""
    with open(run / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _load(run: Path) -> dict:
    return json.loads((run / "review.json").read_text(encoding="utf-8"))


def _save(run: Path, st: dict) -> None:
    (run / "review.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def split(comments_path: Path | str, original: Path | str, revised: Path | str, run: Path,
          letter_lang: str = "en") -> dict:
    if (run / "review.json").exists():
        raise ValueError(f"{run} already has a review run")
    items = parse_comments(Path(comments_path).read_text(encoding="utf-8"))
    if not items:
        raise ValueError("no comments found")
    orig, rev = load_manuscript(original), load_manuscript(revised)
    changes = diff_manuscripts(orig, rev)
    run.mkdir(parents=True, exist_ok=True)
    (run / "manuscript.json").write_text(json.dumps(rev, ensure_ascii=False), encoding="utf-8")
    (run / "manuscript_original.json").write_text(json.dumps(orig, ensure_ascii=False), encoding="utf-8")
    (run / "changes.json").write_text(json.dumps(changes, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Revised manuscript (readable text, by section)", ""]
    last = None
    for i, p in enumerate(rev):
        if p["section"] != last:
            md += [f"## {p['section']}", ""]
            last = p["section"]
        mark = " **[changed]**" if any(c["index"] == i for c in changes) else ""
        md += [f"[P{i}]{mark} {p['text']}", ""]
    (run / "manuscript.md").write_text("\n".join(md), encoding="utf-8")
    cm = ["# What changed between original and revised", ""]
    for c in changes:
        cm += [f"## P{c['index']} · {c['section']} · {c['kind']}", ""]
        if c["before"]:
            cm += [f"**Before:** {c['before']}", ""]
        cm += [f"**After:** {c['after']}", ""]
    if not changes:
        cm.append("(no differences found)")
    (run / "changes.md").write_text("\n".join(cm), encoding="utf-8")
    for it in items:
        d = run / "items" / it["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "comment.md").write_text(f"# {it['id']} (Reviewer {it['reviewer']})\n\n{it['comment']}\n",
                                      encoding="utf-8")
        it.update(attempts=0, last_hash=None, passed=None, findings=[], needs_author=False)
    st = {"items": items, "original": str(original), "revised": str(revised),
          "lang": letter_lang, "created": time.strftime("%Y-%m-%d %H:%M")}
    _save(run, st)
    return st


def parse_response(text: str) -> dict:
    out = {"response": "", "change": "", "location": "", "quotes": []}
    key = None
    for line in text.splitlines():
        m = re.match(r"^\s*(Response|Change|Location|Quote)\s*[:：]\s*(.*)$", line, re.I)
        if m:
            key = m.group(1).lower()
            val = m.group(2).strip()
            if key == "quote":
                out["quotes"].append(val.strip().strip('"“”'))
            else:
                out[key] = val
        elif key in ("response", "change") and line.strip():
            out[key] += " " + line.strip()
    return out


def check(run: Path, item_id: str) -> dict:
    with _locked(run):
        return _check(run, item_id)


def _check(run: Path, item_id: str) -> dict:
    st = _load(run)
    it = next((x for x in st["items"] if x["id"] == item_id), None)
    if it is None:
        raise ValueError(f"unknown item {item_id}")
    path = run / "items" / item_id / "response.md"
    if not path.exists():
        raise ValueError(f"{item_id}: response.md not written yet")
    text = path.read_text(encoding="utf-8")
    h = _hash(text)
    if h == it["last_hash"]:
        return {"item": item_id, "status": "passed" if it["passed"] else "failed", "cached": True,
                "attempts": it["attempts"], "max": MAX_ATTEMPTS, "findings": it["findings"]}
    if it["needs_author"]:
        return {"item": item_id, "status": "needs-author", "cached": True,
                "attempts": it["attempts"], "max": MAX_ATTEMPTS, "findings": it["findings"]}

    f = evaluate(run, it, text)
    passed = not any(x["level"] == "error" for x in f)
    it["attempts"] += 1
    it.update(last_hash=h, passed=passed, findings=f)
    if not passed and it["attempts"] >= MAX_ATTEMPTS:
        it["needs_author"] = True
    _save(run, st)
    status = "passed" if passed else ("needs-author" if it["needs_author"] else "failed")
    return {"item": item_id, "status": status, "cached": False, "attempts": it["attempts"],
            "max": MAX_ATTEMPTS, "findings": f}


def set_by_author(run: Path, item_id: str, text: str) -> dict:
    """The author edited the reply (review app): check it, save it, no attempt limit."""
    with _locked(run):
        return _set_by_author(run, item_id, text)


def _set_by_author(run: Path, item_id: str, text: str) -> dict:
    st = _load(run)
    it = next((x for x in st["items"] if x["id"] == item_id), None)
    if it is None:
        raise ValueError(f"unknown item {item_id}")
    f = evaluate(run, it, text)
    passed = not any(x["level"] == "error" for x in f)
    (run / "items" / item_id / "response.md").write_text(text, encoding="utf-8")
    it.update(last_hash=_hash(text), passed=passed, findings=f, needs_author=not passed,
              by_author=True)
    _save(run, st)
    return {"item": item_id, "status": "passed" if passed else "failed", "findings": f}


def evaluate(run: Path, it: dict, text: str) -> list[dict]:
    """All response checks for one reply text, without touching state."""
    rev = json.loads((run / "manuscript.json").read_text(encoding="utf-8"))
    changes = json.loads((run / "changes.json").read_text(encoding="utf-8"))
    changed_idx = {c["index"] for c in changes}
    original_text = _norm(" ".join(p["text"] for p in json.loads(
        (run / "manuscript_original.json").read_text(encoding="utf-8"))))
    r = parse_response(text)
    f: list[dict] = []
    add = lambda lvl, layer, msg: f.append({"level": lvl, "layer": layer, "message": msg})

    if not r["response"].strip():
        add("error", "R-empty", "no 'Response:' text")
    found_in_changed = False
    for q in r["quotes"]:
        nq = _norm(q)
        hits = [i for i, p in enumerate(rev) if nq and nq in _norm(p["text"])]
        if not hits:
            add("error", "R-quote-missing", f"not in the revised manuscript: “{q[:80]}”")
            continue
        if any(i in changed_idx for i in hits) and nq not in original_text:
            found_in_changed = True  # new text, not something that was already there
        if r["location"] and not any(_norm(r["location"]) in _norm(rev[i]["section"]) or
                                     _norm(rev[i]["section"]) in _norm(r["location"]) for i in hits):
            add("warning", "R-location", f"quote is in “{rev[hits[0]]['section']}”, "
                                         f"not “{r['location']}”")
    claims_change = bool(CLAIMS_CHANGE.search(r["response"] + " " + r["change"])) and \
        not re.match(r"^\s*(?:none|no change|无)\b", r["change"], re.I)
    if claims_change and not found_in_changed:
        add("error", "R-change-unbacked",
            "the reply says the manuscript was changed, but no quote is new text in the revised "
            "manuscript (each quote either is missing or was already in the original)")
    if claims_change and r["quotes"]:
        generic = {"added", "revised", "changed", "modified", "updated", "clarified", "removed",
                   "deleted", "text", "paragraph", "section", "sentence", "sentences", "wording",
                   "manuscript", "softened", "toned", "down", "now", "statement", "claim", "claims",
                   "corrected", "rewritten", "rephrased", "included", "inserted", "expanded"}
        want = {w for w in re.findall(r"[a-z]{5,}", r["change"].lower()) if w not in generic}
        quoted = _norm(" ".join(r["quotes"]))
        if want and not any(w[:5] in quoted for w in want):
            add("warning", "R-relevance",
                f"none of the quotes mention what 'Change:' says ({', '.join(sorted(want))})")
    manuscript = _norm(" ".join(p["text"] for p in rev))
    comment = _norm(it["comment"])
    for num in set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", r["response"])):
        if num not in manuscript and num not in comment and len(num) > 1:
            add("warning", "R-number", f"number {num} appears in neither the manuscript nor the comment")
    if re.search(r"\bwe will\b|\bwill be (?:added|revised|included)|将在|后续将", r["response"], re.I):
        add("warning", "R-promise", "promises a future change — reviewers expect the change to be made now")
    a = audit(r["response"])
    if a["ai_phrases"]:
        add("warning", "R-style", "template phrasing: " + ", ".join(sorted({x["term"] for x in a["hits"]
                                                                          if x["kind"] == "ai-phrase"})))
    return f


def status(run: Path) -> dict:
    st = _load(run)
    by: dict[str, list[str]] = {}
    for it in st["items"]:
        p = run / "items" / it["id"] / "response.md"
        if it["needs_author"]:
            s = "needs-author"
        elif not p.exists():
            s = "needs-response"
        elif _hash(p.read_text(encoding="utf-8")) != it["last_hash"]:
            s = "needs-check"
        else:
            s = "passed" if it["passed"] else "failed"
        by.setdefault(s, []).append(it["id"])
    if by.get("needs-response") or by.get("failed"):
        nxt = "spawn one responder per item (parallel): " + " ".join(by.get("needs-response", []) + by.get("failed", []))
    elif by.get("needs-check"):
        nxt = "run review-gate for: " + " ".join(by["needs-check"])
    else:
        nxt = "review-assemble"
    return {"by_status": by, "next": nxt}


def assemble(run: Path) -> dict:
    st = _load(run)
    zh = st.get("lang") == "zh"
    L = (lambda en, cn: cn if zh else en)
    md = [f"# {L('Response to reviewers', '审稿意见回复')}", ""]
    body = [dx.para((L("Response to reviewers", "审稿意见回复"), "b"))]
    rows = ["| Item | Status | Checks |", "|---|---|---|"]
    last_rev = None
    for it in st["items"]:
        p = run / "items" / it["id"] / "response.md"
        r = parse_response(p.read_text(encoding="utf-8")) if p.exists() else None
        if it["reviewer"] != last_rev:
            title = L(f"Reviewer {it['reviewer']}", f"审稿人 {it['reviewer']}")
            md += [f"## {title}", ""]
            body.append(dx.para((title, "b")))
            last_rev = it["reviewer"]
        ok = it["passed"] and not it["needs_author"]
        flag = "" if ok else L(" [UNVERIFIED — author must check]", " [未通过核实——请作者确认]")
        md += [f"**{L('Comment', '意见')} {it['id']}.** {it['comment']}", ""]
        body.append(dx.para((f"{L('Comment', '意见')} {it['id']}. ", "b"), (it["comment"], "i")))
        if r:
            md += [f"**{L('Response', '回复')}{flag}:** {r['response']}", ""]
            body.append(dx.para((f"{L('Response', '回复')}{flag}: ", "b"), (r["response"], "")))
            for q in r["quotes"]:
                loc = f" ({r['location']})" if r["location"] else ""
                md += [f"> {q}{loc}", ""]
                body.append(dx.para((f"“{q}”{loc}", "u")))
        else:
            md += [f"**{L('Response', '回复')}{flag}:** {L('(missing)', '（缺失）')}", ""]
            body.append(dx.para((f"{L('Response', '回复')}{flag}: ", "b"), (L("(missing)", "（缺失）"), "")))
        warns = [x["message"] for x in it["findings"] if x["level"] == "warning"]
        errs = [x["message"] for x in it["findings"] if x["level"] == "error"]
        rows.append(f"| {it['id']} | {'verified' if ok else 'needs author'} | "
                    f"{'; '.join(errs + warns).replace('|', '/') or '—'} |")
    (run / "response_letter.md").write_text("\n".join(md), encoding="utf-8")
    dx.write_document(run / "response_letter.docx", "".join(body))
    (run / "review_checks.md").write_text("# Response checks\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    verified = sum(1 for it in st["items"] if it["passed"] and not it["needs_author"])
    return {"items": len(st["items"]), "verified": verified,
            "letter": "response_letter.md", "docx": "response_letter.docx"}
