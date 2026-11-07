"""PostToolUse hook: when a rewriter saves units/uNN/masked_revised.txt, run that
unit's gate immediately and feed the result back to the agent that wrote it.

Gates are idempotent per file content, so a later manual `gate` call on the same
file does not burn an extra attempt.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .pipeline import PipelineError, gate, style_gate

_TARGET = re.compile(r"^(?P<run>.+)/units/(?P<uid>u\d+)/masked_(?P<stage>revised|styled)\.txt$")


def _summary(res: dict) -> str:
    errs = [f for f in res.get("findings", []) if f["level"] == "error"]
    warns = [f for f in res.get("findings", []) if f["level"] == "warning"]
    label = "Style gate" if res["status"] in ("styled", "kept-rewrite") or res.get("stage") == "style" else "Gate"
    head = (f"{label} {res['unit']}: {res['status'].upper()} "
            f"(attempt {res.get('attempts', '?')}/{res.get('max', '?')})")
    body = [f"  [error] {f['layer']}: {f['message']}" for f in errs]
    body += [f"  [warning] {f['layer']}: {f['message']}" for f in warns]
    if res["status"] == "failed":
        body.append("  Fix only the sentences involved and save the same file again.")
    elif res["status"] == "kept-rewrite":
        body.append("  Style attempts used up: the rewriter's passed version is kept. Stop editing this unit.")
    elif res["status"] == "styled":
        body.append("  Style version accepted." + (" Address each warning in style_changes.md." if warns else ""))
    elif res["status"] == "reverted":
        body.append("  Attempt limit reached: the original paragraph is kept. Stop editing this unit.")
    elif warns:
        body.append("  Passed. Address each warning in changes.md.")
    return "\n".join([head, *body])


_REVIEW = re.compile(r"^(?P<run>.+)/items/(?P<item>R[^/]+)/response\.md$")


def _review_hook(m, stdout) -> int:
    from . import review
    run = Path(m.group("run"))
    if not (run / "review.json").exists():
        return 0
    try:
        res = review.check(run, m.group("item"))
    except ValueError as e:
        json.dump({"decision": "block", "reason": f"Review check error: {e}"}, stdout)
        return 0
    text = review_summary(res)
    if res["status"] == "failed":
        json.dump({"decision": "block", "reason": text}, stdout)
    else:
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                          "additionalContext": text}}, stdout)
    return 0


def review_summary(res: dict) -> str:
    lines = [f"Review check {res['item']}: {res['status'].upper()} "
             f"(attempt {res['attempts']}/{res['max']})"]
    lines += [f"  [{f['level']}] {f['layer']}: {f['message']}" for f in res["findings"]]
    if res["status"] == "failed":
        lines.append("  Fix response.md: quote the revised manuscript exactly, and only claim "
                     "changes that exist (see changes.md). If nothing was changed, write 'Change: none'.")
    elif res["status"] == "needs-author":
        lines.append("  Attempts used up — the item is marked for the author. Stop.")
    return "\n".join(lines)


def main(stdin=sys.stdin, stdout=sys.stdout) -> int:
    try:
        event = json.load(stdin)
    except json.JSONDecodeError:
        return 0
    path = (event.get("tool_input") or {}).get("file_path") or ""
    rm = _REVIEW.match(str(Path(path)))
    if rm:
        return _review_hook(rm, stdout)
    m = _TARGET.match(str(Path(path)))
    if not m:
        return 0
    run = Path(m.group("run"))
    if not (run / "run.json").exists():
        return 0
    try:
        res = (style_gate if m.group("stage") == "styled" else gate)(run, m.group("uid"))
    except PipelineError as e:
        json.dump({"decision": "block", "reason": f"Gate error: {e}"}, stdout)
        return 0

    text = _summary(res)
    if res["status"] == "failed":
        json.dump({"decision": "block", "reason": text}, stdout)
    else:
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                          "additionalContext": text}}, stdout)
    return 0
