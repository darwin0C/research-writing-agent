---
name: academic-writing
description: Polish a paragraph, section or manuscript part of a scientific paper (LaTeX or plain text) so it reads naturally and fits the target journal, while provably keeping numbers, units, equations, citations and claim strength unchanged. Use when the user asks to polish, revise, de-template, or "humanize" academic text, an abstract, or a manuscript section.
---

# Academic writing — section pipeline (M1)

You are the **orchestrator**. You plan, delegate and integrate; subagents do the
judgement work; code decides what passed. Never rewrite paragraphs yourself and never
weaken a check to get a pass.

All commands run from the project root (the folder holding `checker/`).

## 0. Inputs — ask one question only if something missing would change the result

- Text: file path (whole file or a section of it) or pasted text.
- Target journal (default: International Journal of Heat and Mass Transfer).
- Rewrite level: `light` (default), `medium`, `heavy`.
- Journal style key from `config/journals/` (`ijhmt`, `ate`; default `ijhmt`).
- The paper's `.bib` file, if there is one — look next to the .tex before asking.
- Style corpus: if `style_corpus/index.json` exists, use it (personal style calibration).
  If the user wants it and none exists, build it from their earlier papers:
  `python3 -m checker style-build <folder-or-files> --out style_corpus` (needs ≥5
  paragraphs; 3+ papers recommended) and show them `style_corpus/profile.md`.

Save the exact text to polish to a file first if it was pasted or is a part of a file.

## Three kinds of documents

| Document | Input | Mode |
|---|---|---|
| Paper section (LaTeX) | `.tex` | steps 1–6 below |
| Paper section (Word) | `.docx` | steps 1–6; output is `revised_tracked.docx` (tracked changes) + `revised_clean.docx` |
| Grant proposal | `.tex`, `.docx`, `.txt`/`.md` (Chinese or English) | steps 1–6 with `--style nsfc` or `--style nsf` |
| Response to reviewers | comments file + original + revised manuscript | section **R** at the end |

Plain-text input (`.txt`/`.md`) is not LaTeX: `%` is a percent sign. Style calibration
(step 3b) is English-only for now — do not pass `--style-corpus` for Chinese text.

## 1. Split (code node)

```bash
RUN=runs/$(date +%Y%m%d-%H%M)-<short-name>
python3 -m checker split <input.tex> --run "$RUN" --style <key> --level <level> [--bib <refs.bib>] [--style-corpus style_corpus]
```

This writes `graph.md` (nodes, edges, done-criteria), `progress.md`,
`section_notes.txt` (abbreviations, spelling, citations across the section) and
`units/uNN/` with `masked.txt`, `map.json`, `audit.txt`. The run remembers the style,
.bib and glossary; every gate uses them. Headings, figures, tables,
display equations and very short paragraphs become **frozen** units and pass through
unchanged. Tell the user in one line how many prose units there are.

**Resuming:** if a run already exists, read `graph.md` and `progress.md`, run
`python3 -m checker status "$RUN"`, and continue from **Next**.

## 2. Audit (A1 — one `auditor` subagent for all prose units)

Task: run folder, the prose unit ids, the journal. Wait for it. Each prose unit now
has `issues.md`.

## 3. Rewrite + gate (A2 — one `rewriter` subagent per unit, in parallel)

Launch all rewriters in one message. Each task gives: run folder, unit id, journal,
level. Larger runs: at most ~8 at a time, then the next batch.

Saving `masked_revised.txt` triggers the gate automatically (PostToolUse hook in
`.claude/settings.json`). Gates are cached by file content, so running one again by
hand is safe. After 3 failed gates a unit is **reverted** (original kept).

When all rewriters return:

```bash
python3 -m checker status "$RUN"
```

- `needs-gate` → `python3 -m checker gate "$RUN" <id>`.
- `failed` (attempts left) or `needs-rewrite` → send that unit to a new `rewriter`.
  Only failed units are re-run, never the whole batch.

## 3b. Style calibration (A4 — only when the run has a style corpus)

When every prose unit has passed its gate, `status` says
`spawn one style-calibrator per unit`. Launch one `style-calibrator` per unit, in
parallel (task: run folder, unit id). Each writes `masked_styled.txt`; the style gate
(hook, or `python3 -m checker style-gate "$RUN" <id>`) checks it against the original
with every content check plus a text-recycling check against the earlier papers.
Two failed tries keep the rewriter's version (`style-kept-rewrite`) — never the original.

## 4. Assemble + section gate (code node)

```bash
python3 -m checker assemble "$RUN"
```

Joins passed units (revised) with frozen/reverted units (original) and runs `compare`
on the whole section. A FAIL here means units interact (e.g. a number moved between
paragraphs): find the unit, `reopen` it with the reason, rewrite, gate, assemble again.

## 5. Claim check (A3 — one `claim-checker` subagent)

It writes `claims.md`. For each line under `## Reopen`:

```bash
python3 -m checker reopen "$RUN" <id> --reason "<its instruction>"
```

then run a `rewriter` for those units (step 3) and `assemble` again. Do the claim
check **once** per run; a second round only if the user asks. Attempts keep counting,
so a unit can never loop forever.

## 6. Deliver

`assemble` writes `report.md` (revised text, per-unit changes, claims, gates, metrics).
Run `assemble` one last time after claims.md exists so the report includes it. Then
show the user:

1. The revised text (or, for long sections, the path to `revised.tex`).
2. One-line totals: units passed / reverted, section gate, AI-phrase density before → after,
   and (with a style corpus) style distance before → after.
3. The **For the author** items and `author` verdicts from claims.md.
4. Paths: `report.md`, `checks.md`, `progress.md`.
5. With a style corpus: offer the blind check —
   `python3 -m checker style-blind "$RUN"` writes `blind.md` (rewrite vs styled as A/B in
   random order); the user rates it, then `python3 -m checker style-unblind "$RUN"`.
   Do not open `blind_key.json` or tell the user which version is which before they rate.

Report token use only if you measured it. Mention once that AI-assisted editing should
be disclosed per the journal's policy; never frame the goal as evading AI detection.

## R. Response to reviewers

Inputs: the reviewer comments (text file), the original and the revised manuscript
(`.tex`, `.docx` or `.txt`), letter language (`en`/`zh`). If the user has not revised the
manuscript yet, polish/revise it first (steps 1–6) and use that output as "revised".

```bash
RUN=runs/$(date +%Y%m%d-%H%M)-response
python3 -m checker review-split comments.txt --original <orig> --revised <rev> --run "$RUN" [--lang zh]
```

This writes `items/<id>/comment.md`, `manuscript.md` (revised text with `[changed]`
marks) and `changes.md` (before/after of every changed paragraph). Tell the user how
many comments and changed paragraphs were found — if 0 changes, stop and ask whether
the right files were given.

Launch one `responder` per item, in parallel (task: run folder, item id, letter
language). Saving `response.md` triggers the check (hook) — quotes must exist
verbatim in the revised manuscript and any claimed change must be backed by new text.
Then:

```bash
python3 -m checker review-status "$RUN"     # re-run failed items with a new responder
python3 -m checker review-assemble "$RUN"   # response_letter.md + response_letter.docx + review_checks.md
```

Show the user: how many replies were verified, every item marked `needs author`, and
every reply with `Change: none` or a partial change — those are decisions for the author
(e.g. a reviewer's physics objection the revision only hedged).

## Done when

Every prose unit is `passed`/`styled`/`style-kept-rewrite` or `reverted`, the section gate passes, claims.md exists
with every reopen resolved, and report.md is regenerated — or a limit stopped the run,
in which case say exactly which units are open (`assemble --partial` gives a report).
