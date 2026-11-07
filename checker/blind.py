"""Blind A/B rating: does the style-calibrated version sound more like you?

style-blind   writes blind.md (each paragraph's rewrite and styled version as A/B in
              random order) and blind_key.json (which is which — don't open it).
style-unblind reads your filled-in blind.md and reports which version won.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .pipeline import PipelineError, _udir, _with_format, load, unit_status
from .style import readable


@_with_format
def make_sheet(run: Path, seed: int | None = None) -> Path:
    state = load(run)
    items = []
    for u in state["units"]:
        if unit_status(run, u, state) != "styled":
            continue
        d = _udir(run, u["id"])
        items.append((u["id"], readable((d / "revised.tex").read_text(encoding="utf-8")),
                      readable((d / "styled.tex").read_text(encoding="utf-8"))))
    if not items:
        raise PipelineError("no styled paragraphs to compare yet")
    rng = random.Random(seed if seed is not None else sum(map(ord, state["name"])))
    key, lines = {}, [
        f"# Blind rating · {state['name']}", "",
        "For each item, read A and B. Rate how much each **sounds like you** (1–5) and pick the",
        "one you would rather submit. Fill in after the colons; leave everything else as is.",
        "Then run `python3 -m checker style-unblind <run>`.", ""]
    for n, (uid, rewrite, styled) in enumerate(items, 1):
        flip = rng.random() < 0.5
        a, b = (styled, rewrite) if flip else (rewrite, styled)
        key[str(n)] = {"unit": uid, "A": "styled" if flip else "rewrite",
                       "B": "rewrite" if flip else "styled"}
        lines += [f"## Item {n}", "", "**A**", "", a, "", "**B**", "", b, "",
                  "- A sounds like me (1–5): ", "- B sounds like me (1–5): ",
                  "- Prefer (A/B): ", ""]
    sheet = run / "blind.md"
    sheet.write_text("\n".join(lines), encoding="utf-8")
    (run / "blind_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    return sheet


def score(run: Path) -> dict:
    key = json.loads((run / "blind_key.json").read_text(encoding="utf-8"))
    text = (run / "blind.md").read_text(encoding="utf-8")
    results = {"styled": [], "rewrite": [], "prefer": {"styled": 0, "rewrite": 0}, "unrated": []}
    for block in re.split(r"^## Item ", text, flags=re.M)[1:]:
        n = block.split("\n", 1)[0].strip()
        k = key.get(n)
        if not k:
            continue
        a = re.search(r"A sounds like me \(1–5\):\s*([1-5])", block)
        b = re.search(r"B sounds like me \(1–5\):\s*([1-5])", block)
        p = re.search(r"Prefer \(A/B\):\s*([ABab])", block)
        if not (a or b or p):
            results["unrated"].append(k["unit"])
            continue
        if a:
            results[k["A"]].append(int(a.group(1)))
        if b:
            results[k["B"]].append(int(b.group(1)))
        if p:
            results["prefer"][k[p.group(1).upper()]] += 1
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return {"styled_mean": mean(results["styled"]), "rewrite_mean": mean(results["rewrite"]),
            "prefer_styled": results["prefer"]["styled"],
            "prefer_rewrite": results["prefer"]["rewrite"], "unrated": results["unrated"]}
