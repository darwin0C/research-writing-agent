"""Rule packs: writing knowledge (e.g. Academic Humanizer) appended to every agent.

The pack text is kept verbatim. This module adds one precedence note so the pack's
process/output instructions never override the pipeline's, and so its "add an evidence
pointer" advice can never turn into an invented figure, table or citation.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"
DEFAULT_PACKS = ["academic-humanizer"]

PRECEDENCE = """\
## Reference rules (rule packs)

The rule packs below are reference knowledge about good academic writing. Use them for
*what to fix and how*. Where they disagree with your instructions above, your instructions
win — in particular:

- Process and output: follow your own steps and return only the files your instructions
  name. Ignore any pack instruction to return text inline, ask the user questions, or
  confirm things yourself — the program checks numbers, equations and citations itself.
- Evidence pointers: you may point to a figure, table, section or citation **only if it
  already appears in the text you were given**. If a claim needs evidence that is not
  there, do not invent it: either soften the claim or insert the marker
  `[[EVIDENCE: <what the author must supply>]]` right after the claim. Markers are
  reported to the author and block final submission until resolved.
- Never turn a vague magnitude into a number that is not in the text.
- Grant proposals: vision language is allowed when the text gives its feasibility basis;
  if the basis is missing, add an `[[EVIDENCE: …]]` marker rather than inventing it.
"""


def available() -> list[dict]:
    out = []
    if not RULES.exists():
        return out
    for d in sorted(p for p in RULES.iterdir() if p.is_dir()):
        main = d / "SKILL.md"
        if not main.exists():
            mds = sorted(d.glob("*.md"))
            main = next((m for m in mds if m.name not in ("NOTICE.md", "README.md")), None)
        if main is None:
            continue
        head = main.read_text(encoding="utf-8")
        m = re.search(r"^description:\s*\|?[ \t]*\n((?:[ \t]+.+\n)+)|^description:\s*(.+)$", head, re.M)
        v = re.search(r"^version:\s*(\S+)", head, re.M)
        out.append({"name": d.name, "file": str(main.relative_to(ROOT)),
                    "version": v.group(1) if v else "",
                    "description": (" ".join((m.group(1) or m.group(2) or "").split()) if m else "")[:240],
                    "license": (d / "LICENSE").exists()})
    return out


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.S).strip()


def compose(packs: list[str] | None = None) -> str:
    """Text appended to an agent's instructions; '' when no packs are active."""
    packs = DEFAULT_PACKS if packs is None else packs
    by_name = {p["name"]: p for p in available()}
    parts = []
    for name in packs:
        p = by_name.get(name)
        if p:
            parts.append(f"### Rule pack: {name}"
                         + (f" (v{p['version']})" if p["version"] else "") + "\n\n"
                         + _body(ROOT / p["file"]))
    return (PRECEDENCE + "\n" + "\n\n".join(parts)) if parts else ""
