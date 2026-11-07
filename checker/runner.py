"""Standalone runner: the same pipeline as the Claude Code skill, driven by Python and
the Claude API instead of Claude Code.

    pip install anthropic          # only needed for this module
    python3 -m checker run paper.docx --style ijhmt [--level medium] [--bib refs.bib]
    python3 -m checker run-review comments.txt --original old.tex --revised new.tex

Each LLM node (auditor, rewriter, style-calibrator, claim-checker, responder) uses its
instruction file from .claude/agents/ as the system prompt. The program gives the node
its input files and reads back the files it returns as <file path="…">…</file>
blocks; every gate, retry limit and revert stays in code, exactly as in the skill.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from . import pipeline, review
from .hook import _summary, review_summary
from .invariants import load_style

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
DEFAULT_MODEL = "claude-opus-5-5"

STANDALONE = """You are running inside a program, not an interactive coding tool. You cannot run
commands or open files: the program has already given you every file you need below,
and it runs every check (gate) itself and reports the result back to you. Wherever the
instructions say to run a command or read a file, use what you were given instead.

Return each file you write in this exact form, nothing else around the content:

<file path="NAME">
…content…
</file>

NAME is the file name only (e.g. masked_revised.txt), exactly as the instructions name
it. Do not wrap the content in code fences. After the files, finish with the one-line
status the instructions ask for.

--- Your instructions ---
"""

_FILE = re.compile(r'<file path="([^"]+)">\n?(.*?)\n?</file>', re.S)


from .llm import AnthropicProvider as Claude  # kept for the CLI and older callers
from .llm import LLMError, providers_for_nodes  # noqa: F401  (re-exported)
from .rules import compose as compose_rules


def _system(agent: str, packs: list[str] | None = None) -> str:
    body = (AGENTS / f"{agent}.md").read_text(encoding="utf-8")
    body = re.sub(r"^---.*?---\s*", "", body, count=1, flags=re.S)
    # the agent file's own "read the rule packs" note is for Claude Code (which can read
    # files); here the packs are appended directly
    body = body.split("\n## Reference rules (rule packs)")[0]
    rules = compose_rules(packs)
    return STANDALONE + body + ("\n\n" + rules if rules else "")


def _files(text: str, allowed: set[str]) -> dict[str, str]:
    out = {}
    for path, content in _FILE.findall(text):
        name = Path(path.strip()).name
        if name in allowed:
            out[name] = content
    return out


def _block(name: str, content: str) -> str:
    return f'<file path="{name}">\n{content}\n</file>'


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ------------------------------------------------------------------ nodes

class Runner:
    """llm: one provider for every node, or {node: provider} (see llm.providers_for_nodes).
    packs: active rule packs (None = default, [] = none)."""

    def __init__(self, llm, log: Callable[[str], None] = print, workers: int = 4,
                 packs: list[str] | None = None):
        self.llms = llm if isinstance(llm, dict) else {"default": llm}
        self.log, self.workers, self.packs = log, workers, packs

    def _llm(self, agent: str):
        return self.llms.get(agent) or self.llms["default"]

    def usage(self) -> dict:
        tot = {"input": 0, "output": 0, "cache_read": 0, "calls": 0}
        for p in {id(p): p for p in self.llms.values()}.values():
            for k in tot:
                tot[k] += getattr(p, "usage", {}).get(k, 0)
        return tot

    def _converse(self, agent: str, first: str, allowed: set[str],
                  on_files: Callable[[dict], tuple[bool, str]], max_turns: int) -> dict:
        """Ask, apply returned files, report the gate result back; repeat until on_files
        says done or the turn limit is reached. History is append-only."""
        system = _system(agent, self.packs)
        llm = self._llm(agent)
        messages: list = [{"role": "user", "content": first}]
        files: dict = {}
        for _ in range(max_turns):
            text, content = llm.turn(system, messages)
            messages.append({"role": "assistant", "content": content})
            files = _files(text, allowed)
            if not files:
                messages.append({"role": "user", "content":
                                 "No <file path=…> blocks were found. Return the files in the "
                                 "required form."})
                continue
            done, feedback = on_files(files)
            if done:
                return files
            messages.append({"role": "user", "content": feedback})
        return files

    # -- paper ---------------------------------------------------------------

    def _context(self, run: Path, state: dict) -> str:
        parts = [_block("run.json (summary)", json.dumps(
            {k: state.get(k) for k in ("journal", "style", "level", "format", "section_type")},
            ensure_ascii=False, indent=1))]
        if state.get("style"):
            p = ROOT / "config" / "journals" / f"{state['style']}.toml"
            parts.append(_block(f"config/journals/{state['style']}.toml", _read(p)))
        parts.append(_block("config/glossary.toml", _read(ROOT / "config" / "glossary.toml")))
        return "\n\n".join(parts)

    def audit(self, run: Path, state: dict, uids: list[str]) -> None:
        self.log(f"auditor: {len(uids)} paragraphs")
        parts = [f"Run folder: {run.name}. Prose unit ids: {' '.join(uids)}. "
                 f"Return one issues.md per unit as <file path=\"<unit id>/issues.md\">.",
                 self._context(run, state),
                 _block("section_notes.txt", _read(run / "section_notes.txt"))]
        for u in uids:
            d = run / "units" / u
            for name in ("masked.txt", "audit.txt", "legend.md"):
                if (d / name).exists():
                    parts.append(_block(f"{u}/{name}", _read(d / name)))
        system = _system("auditor", self.packs)
        text, _ = self._llm("auditor").turn(system, [{"role": "user", "content": "\n\n".join(parts)}])
        for path, content in _FILE.findall(text):
            m = re.match(r"(u\d+)/issues\.md$", path.strip())
            if m and m.group(1) in uids:
                (run / "units" / m.group(1) / "issues.md").write_text(content, encoding="utf-8")
        for u in uids:  # a unit the auditor skipped still needs a file to move on
            p = run / "units" / u / "issues.md"
            if not p.exists():
                p.write_text("# Issues\n\n(auditor returned nothing for this unit)\n", encoding="utf-8")

    def rewrite(self, run: Path, state: dict, uid: str) -> str:
        d = run / "units" / uid
        parts = [f"Run folder: {run.name}. Unit id: {uid}. Journal: {state['journal']}. "
                 f"Rewrite level: {state['level']}.", self._context(run, state)]
        for name in ("masked.txt", "issues.md", "feedback.md", "legend.md"):
            if (d / name).exists():
                parts.append(_block(name, _read(d / name)))
        result = {"status": "?"}

        def on_files(files):
            if "changes.md" in files:
                (d / "changes.md").write_text(files["changes.md"], encoding="utf-8")
            if "masked_revised.txt" not in files:
                return False, "masked_revised.txt is missing — return it."
            (d / "masked_revised.txt").write_text(files["masked_revised.txt"], encoding="utf-8")
            res = pipeline.gate(run, uid)
            result["status"] = res["status"]
            if res["status"] in ("passed", "reverted"):
                return True, ""
            return False, "Gate result:\n" + _summary(res)

        self._converse("rewriter", "\n\n".join(parts), {"masked_revised.txt", "changes.md"},
                       on_files, max_turns=state["max_attempts"] + 1)
        self.log(f"rewriter {uid}: {result['status']}")
        return result["status"]

    def calibrate(self, run: Path, state: dict, uid: str) -> str:
        from . import style
        from .latex_mask import text_format
        d = run / "units" / uid
        index = style.load(state["style_corpus"])
        fref = load_style(state["style"]).get("figure_ref") if state.get("style") else None
        with text_format(state.get("format", "latex")):
            brief = style.brief(index, style.prose_of(_read(d / "revised.tex")),
                                state.get("section_type"), figure_ref=fref)
        parts = [f"Run folder: {run.name}. Unit id: {uid}.", self._context(run, state),
                 _block("style brief (output of style-brief)", brief)]
        for name in ("masked_revised.txt", "changes.md", "legend.md"):
            if (d / name).exists():
                parts.append(_block(name, _read(d / name)))
        result = {"status": "?"}

        def on_files(files):
            if "style_changes.md" in files:
                (d / "style_changes.md").write_text(files["style_changes.md"], encoding="utf-8")
            if "masked_styled.txt" not in files:
                return False, "masked_styled.txt is missing — return it."
            (d / "masked_styled.txt").write_text(files["masked_styled.txt"], encoding="utf-8")
            res = pipeline.style_gate(run, uid)
            result["status"] = res["status"]
            if res["status"] in ("styled", "kept-rewrite"):
                return True, ""
            return False, "Style gate result:\n" + _summary(res)

        self._converse("style-calibrator", "\n\n".join(parts),
                       {"masked_styled.txt", "style_changes.md"}, on_files,
                       max_turns=state.get("max_style_attempts", 2) + 1)
        self.log(f"style-calibrator {uid}: {result['status']}")
        return result["status"]

    def claims(self, run: Path, state: dict) -> list[tuple[str, str]]:
        self.log("claim-checker: whole section")
        parts = [f"Run folder: {run.name}.", _block("original.tex", _read(run / "original.tex")),
                 _block("revised.tex", _read(run / "revised.tex")),
                 _block("checks.md", _read(run / "checks.md"))]
        for u in state["units"]:
            for name in ("changes.md", "style_changes.md", "legend.md"):
                p = run / "units" / u["id"] / name
                if p.exists():
                    parts.append(_block(f"units/{u['id']}/{name}", _read(p)))
        text, _ = self._llm("claim-checker").turn(_system("claim-checker", self.packs),
                                                  [{"role": "user", "content": "\n\n".join(parts)}])
        files = _files(text, {"claims.md"})
        claims = files.get("claims.md", text)
        (run / "claims.md").write_text(claims, encoding="utf-8")
        section = claims.split("## Reopen", 1)[-1] if "## Reopen" in claims else ""
        return [(m.group(1), m.group(2).strip())
                for m in re.finditer(r"^\s*-\s*(u\d+)\s*[:：]\s*(.+)$", section, re.M)]

    def _parallel(self, fn, items):
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(fn, items))

    def run_paper(self, run: Path) -> dict:
        t0 = time.time()
        state = pipeline.load(run)
        prose = [u["id"] for u in state["units"] if u["kind"] == "prose"]
        if not prose:
            raise LLMError("no prose paragraphs to work on")
        self.audit(run, state, prose)
        self._parallel(lambda u: self.rewrite(run, pipeline.load(run), u), prose)
        if state.get("style_corpus"):
            ok = [u["id"] for u in pipeline.load(run)["units"]
                  if pipeline._base_status(run, u) == "passed"]
            self._parallel(lambda u: self.calibrate(run, pipeline.load(run), u), ok)
        pipeline.assemble(run, partial=True)
        reopen = self.claims(run, pipeline.load(run))
        for uid, reason in reopen:
            try:
                pipeline.reopen(run, uid, reason)
            except pipeline.PipelineError as e:
                self.log(f"reopen {uid} skipped: {e}")
                continue
            self.log(f"reopened {uid}: {reason[:80]}")
            if self.rewrite(run, pipeline.load(run), uid) == "passed" and pipeline.load(run).get("style_corpus"):
                self.calibrate(run, pipeline.load(run), uid)
        final = pipeline.assemble(run, partial=True)
        self.log(f"done in {time.time() - t0:.0f}s — section gate {'PASS' if final['passed'] else 'FAIL'}")
        return final

    # -- review ----------------------------------------------------------------

    def respond(self, run: Path, item_id: str, lang: str) -> str:
        d = run / "items" / item_id
        parts = [f"Run folder: {run.name}. Item id: {item_id}. Letter language: "
                 f"{'Chinese' if lang == 'zh' else 'English'}.",
                 _block("comment.md", _read(d / "comment.md")),
                 _block("changes.md", _read(run / "changes.md")),
                 _block("manuscript.md", _read(run / "manuscript.md"))]
        result = {"status": "?"}

        def on_files(files):
            if "response.md" not in files:
                return False, "response.md is missing — return it."
            (d / "response.md").write_text(files["response.md"], encoding="utf-8")
            res = review.check(run, item_id)
            result["status"] = res["status"]
            if res["status"] in ("passed", "needs-author"):
                return True, ""
            return False, "Check result:\n" + review_summary(res)

        self._converse("responder", "\n\n".join(parts), {"response.md"}, on_files,
                       max_turns=review.MAX_ATTEMPTS + 1)
        self.log(f"responder {item_id}: {result['status']}")
        return result["status"]

    def run_review(self, run: Path) -> dict:
        st = json.loads((run / "review.json").read_text(encoding="utf-8"))
        self._parallel(lambda i: self.respond(run, i["id"], st.get("lang", "en")), st["items"])
        out = review.assemble(run)
        self.log(f"done — {out['verified']}/{out['items']} replies verified")
        return out
