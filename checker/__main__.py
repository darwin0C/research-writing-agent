"""Command line entry: python3 -m checker <command> ...

  mask    in.tex  --out masked.txt --map map.json   hide protected LaTeX behind ⟦..⟧
  unmask  masked_revised.txt --map map.json --out revised.tex
  audit   in.tex  [--json]                          AI phrases + strong claims
  compare original.tex revised.tex [--json]         invariant check; exit 1 on error

Exit codes: 0 ok, 1 check failed, 2 usage / input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import DEFAULT_PHRASES, audit
from .invariants import compare
from .latex_mask import UnmaskError, mask, unmask


def _read(p: str) -> str:
    return sys.stdin.read() if p == "-" else Path(p).read_text(encoding="utf-8")


def _write(p: str | None, text: str) -> None:
    if p in (None, "-"):
        sys.stdout.write(text)
    else:
        Path(p).write_text(text, encoding="utf-8")


def _ctx_args(p) -> None:
    p.add_argument("--bib", default=None, help=".bib file: check cited keys exist")
    p.add_argument("--glossary", default="default", help="glossary .toml (default: config/glossary.toml)")
    p.add_argument("--style", default=None, help="journal style key in config/journals/ (e.g. ijhmt)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="checker", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mask")
    m.add_argument("input")
    m.add_argument("--out", default="-")
    m.add_argument("--map", required=True)

    u = sub.add_parser("unmask")
    u.add_argument("input")
    u.add_argument("--map", required=True)
    u.add_argument("--out", default="-")

    a = sub.add_parser("audit")
    a.add_argument("input")
    a.add_argument("--phrases", default=str(DEFAULT_PHRASES))
    a.add_argument("--json", action="store_true")
    _ctx_args(a)

    c = sub.add_parser("compare")
    c.add_argument("original")
    c.add_argument("revised")
    c.add_argument("--json", action="store_true")
    _ctx_args(c)

    # ---- M1 section pipeline
    s = sub.add_parser("split", help="start a run: split a section into paragraph units")
    s.add_argument("input")
    s.add_argument("--run", required=True)
    s.add_argument("--name", default=None)
    s.add_argument("--journal", default="International Journal of Heat and Mass Transfer")
    s.add_argument("--level", choices=["light", "medium", "heavy"], default="light")
    _ctx_args(s)
    s.add_argument("--style-corpus", default=None, help="style index folder (enables style calibration)")
    s.add_argument("--format", choices=["latex", "docx", "text"], default=None,
                   help="default: from the file extension (.docx, .txt/.md, else LaTeX)")

    st = sub.add_parser("status", help="unit statuses and the next action")
    st.add_argument("run")
    st.add_argument("--json", action="store_true")

    g = sub.add_parser("gate", help="check one unit's masked_revised.txt")
    g.add_argument("run")
    g.add_argument("unit")
    g.add_argument("--json", action="store_true")
    g.add_argument("--recheck", action="store_true", help="re-run checks on the same file without using an attempt")

    r = sub.add_parser("reopen", help="send a passed unit back to the rewriter")
    r.add_argument("run")
    r.add_argument("unit")
    r.add_argument("--reason", required=True)

    asm = sub.add_parser("assemble", help="join units, run the section gate, write report.md")
    asm.add_argument("run")
    asm.add_argument("--partial", action="store_true")

    sub.add_parser("hook", help="PostToolUse hook entry (reads event JSON on stdin)")

    # ---- M3 personal style
    sb = sub.add_parser("style-build", help="build the style index from your earlier papers")
    sb.add_argument("paths", nargs="+")
    sb.add_argument("--out", default="style_corpus")

    sd = sub.add_parser("style-distance", help="how far a text is from your style")
    sd.add_argument("input")
    sd.add_argument("--corpus", default="style_corpus")
    sd.add_argument("--section", default=None)

    sbr = sub.add_parser("style-brief", help="style targets + similar paragraphs for one unit")
    sbr.add_argument("run")
    sbr.add_argument("unit")

    sg = sub.add_parser("style-gate", help="check one unit's masked_styled.txt")
    sg.add_argument("run")
    sg.add_argument("unit")

    sbl = sub.add_parser("style-blind", help="write a blind A/B rating sheet")
    sbl.add_argument("run")
    sbl.add_argument("--seed", type=int, default=None)

    su = sub.add_parser("style-unblind", help="score the filled-in blind sheet")
    su.add_argument("run")

    # ---- M4 reviewer response
    rs = sub.add_parser("review-split", help="start a reviewer-response run")
    rs.add_argument("comments")
    rs.add_argument("--original", required=True)
    rs.add_argument("--revised", required=True)
    rs.add_argument("--run", required=True)
    rs.add_argument("--lang", choices=["en", "zh"], default="en")
    for name, helptext in (("review-status", "item statuses and next action"),
                           ("review-assemble", "write the response letter (.md + .docx)")):
        x = sub.add_parser(name, help=helptext)
        x.add_argument("run")
    rg = sub.add_parser("review-gate", help="check one item's response.md")
    rg.add_argument("run")
    rg.add_argument("item")

    # ---- M5 standalone runner + review app
    for name in ("run", "run-review"):
        x = sub.add_parser(name, help=("standalone: split + full pipeline via the Claude API"
                                       if name == "run" else "standalone: reviewer response via the Claude API"))
        if name == "run":
            x.add_argument("input")
            x.add_argument("--run", default=None)
            x.add_argument("--name", default=None)
            x.add_argument("--journal", default="International Journal of Heat and Mass Transfer")
            x.add_argument("--level", choices=["light", "medium", "heavy"], default="light")
            x.add_argument("--format", choices=["latex", "docx", "text"], default=None)
            x.add_argument("--style-corpus", default=None)
            _ctx_args(x)
        else:
            x.add_argument("comments")
            x.add_argument("--original", required=True)
            x.add_argument("--revised", required=True)
            x.add_argument("--run", default=None)
            x.add_argument("--lang", choices=["en", "zh"], default="en")
        x.add_argument("--profile", default=None,
                       help="use this model profile for every agent (default: [nodes] in config/models.toml)")
        x.add_argument("--no-rules", action="store_true", help="do not append rule packs")
        x.add_argument("--workers", type=int, default=4)
    ap_app = sub.add_parser("app", help="open the review app in the browser")
    ap_app.add_argument("--port", type=int, default=8765)
    ap_app.add_argument("--runs", default="runs")
    ap_app.add_argument("--no-browser", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd in ("run", "run-review"):
        return _standalone(args)
    if args.cmd == "app":
        from .app import serve
        return serve(Path(args.runs), args.port, open_browser=not args.no_browser)
    if args.cmd.startswith("review-"):
        return _review(args)

    if args.cmd in ("split", "status", "gate", "reopen", "assemble", "hook"):
        return _pipeline(args)
    if args.cmd.startswith("style-"):
        return _style(args)

    try:
        if args.cmd == "mask":
            res = mask(_read(args.input))
            _write(args.out, res.text)
            Path(args.map).write_text(json.dumps(res.mapping, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            print(f"masked {len(res.mapping)} items → {args.map}", file=sys.stderr)
            return 0

        if args.cmd == "unmask":
            mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
            try:
                _write(args.out, unmask(_read(args.input), mapping))
            except UnmaskError as e:
                print(f"FAIL {e}", file=sys.stderr)
                return 1
            return 0

        if args.cmd == "audit":
            from .bib import bib_hints
            from .invariants import load_context
            from .terms import term_hints
            text = _read(args.input)
            res = audit(text, Path(args.phrases))
            ctx = load_context(args.bib, args.glossary, args.style)
            res["hints"] = term_hints(text, ctx.glossary, ctx.spelling) + bib_hints(text, ctx.bib)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"{res['words']} words · {res['ai_phrases']} AI phrases "
                      f"({res['ai_phrases_per_1000_words']}/1000 words) · "
                      f"{res['strong_claims']} strong-claim words")
                for h in res["hits"]:
                    print(f"  L{h['line']:<4} [{h['kind']}] {h['term']!r}: …{h['excerpt']}…")
                for h in res["hints"]:
                    print(f"  [hint] {h}")
            return 0

        if args.cmd == "compare":
            from .invariants import load_context
            rep = compare(_read(args.original), _read(args.revised),
                          load_context(args.bib, args.glossary, args.style))
            if args.json:
                print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
            else:
                d = rep.to_dict()
                print(f"{'PASS' if rep.passed else 'FAIL'} · {d['errors']} errors · "
                      f"{d['warnings']} warnings")
                for f in rep.findings:
                    print(f"  [{f.level}] {f.layer}: {f.message}")
            return 0 if rep.passed else 1

    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


def _pipeline(args) -> int:
    from . import hook, pipeline

    if args.cmd == "hook":
        return hook.main()
    try:
        if args.cmd == "split":
            run = Path(args.run)
            fmt = args.format or ("docx" if args.input.endswith(".docx") else
                                  "text" if args.input.endswith((".txt", ".md")) else "latex")
            kw = dict(name=args.name or run.name, journal=args.journal, level=args.level,
                      bib=args.bib, glossary=args.glossary, style=args.style,
                      style_corpus=args.style_corpus)
            if fmt == "docx":
                state = pipeline.split_docx(args.input, run, **kw)
            else:
                state = pipeline.split(_read(args.input), run, source=args.input, fmt=fmt, **kw)
            prose = [u["id"] for u in state["units"] if u["kind"] == "prose"]
            frozen = [u["id"] for u in state["units"] if u["kind"] == "frozen"]
            print(f"{len(prose)} prose units: {' '.join(prose)}")
            print(f"{len(frozen)} frozen units: {' '.join(frozen) or '—'}")
            print(f"next: {pipeline.status(run)['next']}")
            return 0

        if args.cmd == "status":
            st = pipeline.status(Path(args.run))
            if args.json:
                print(json.dumps(st, ensure_ascii=False, indent=2))
            else:
                print((Path(args.run) / "progress.md").read_text(encoding="utf-8"))
            return 0

        if args.cmd == "gate":
            from .hook import _summary
            res = pipeline.gate(Path(args.run), args.unit, recheck=args.recheck)
            print(json.dumps(res, ensure_ascii=False, indent=2) if args.json
                  else _summary(res) if "findings" in res else res["message"])
            return 0 if res["status"] in ("passed", "frozen") else 1

        if args.cmd == "reopen":
            res = pipeline.reopen(Path(args.run), args.unit, args.reason)
            print(f"{res['unit']}: needs-rewrite ({res['attempts_left']} attempts left)")
            return 0

        if args.cmd == "assemble":
            f = pipeline.assemble(Path(args.run), partial=args.partial)
            print(f"section gate: {'PASS' if f['passed'] else 'FAIL'}"
                  f"{' (partial)' if f['partial'] else ''} · report: {Path(args.run) / 'report.md'}")
            for x in f["findings"]:
                print(f"  [{x['level']}] {x['layer']}: {x['message']}")
            return 0 if f["passed"] else 1
    except pipeline.PipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


def _standalone(args) -> int:
    import time as _t
    from . import pipeline, review
    from .llm import load_config, providers_for_nodes
    from .runner import LLMError, Runner
    stamp = _t.strftime("%Y%m%d-%H%M")
    try:
        cfg = load_config()
        llms = providers_for_nodes(cfg, override=args.profile)
        packs = [] if args.no_rules else cfg["rules"]["packs"]
        r = Runner(llms, workers=args.workers, packs=packs)
        names = sorted({getattr(p, "label", "?") for p in llms.values()})
        print(f"models: {', '.join(names)} · rule packs: {', '.join(packs) or 'none'}")
        if args.cmd == "run":
            run = Path(args.run or f"runs/{stamp}-{Path(args.input).stem}")
            fmt = args.format or ("docx" if args.input.endswith(".docx") else
                                  "text" if args.input.endswith((".txt", ".md")) else "latex")
            kw = dict(name=args.name or run.name, journal=args.journal, level=args.level,
                      bib=args.bib, glossary=args.glossary, style=args.style,
                      style_corpus=args.style_corpus)
            if fmt == "docx":
                pipeline.split_docx(args.input, run, **kw)
            else:
                pipeline.split(_read(args.input), run, source=args.input, fmt=fmt, **kw)
            final = r.run_paper(run)
            print(f"report: {run}/report.md · section gate {'PASS' if final['passed'] else 'FAIL'}")
        else:
            run = Path(args.run or f"runs/{stamp}-response")
            review.split(args.comments, args.original, args.revised, run, args.lang)
            out = r.run_review(run)
            print(f"letter: {run}/response_letter.md ({out['verified']}/{out['items']} verified)")
        u = r.usage()
        print(f"API usage: {u['calls']} calls · {u['input']} input tokens "
              f"({u['cache_read']} from cache) · {u['output']} output tokens")
        print(f"review it: python3 -m checker app")
        return 0
    except (LLMError, pipeline.PipelineError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _review(args) -> int:
    from . import review
    from .hook import review_summary
    try:
        if args.cmd == "review-split":
            st = review.split(args.comments, args.original, args.revised, Path(args.run), args.lang)
            changes = json.loads((Path(args.run) / "changes.json").read_text(encoding="utf-8"))
            print(f"{len(st['items'])} comments: {' '.join(i['id'] for i in st['items'])}")
            print(f"{len(changes)} changed paragraphs in the revised manuscript (see changes.md)")
            print(f"next: {review.status(Path(args.run))['next']}")
            return 0
        if args.cmd == "review-status":
            print(json.dumps(review.status(Path(args.run)), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "review-gate":
            res = review.check(Path(args.run), args.item)
            print(review_summary(res))
            return 0 if res["status"] == "passed" else 1
        if args.cmd == "review-assemble":
            r = review.assemble(Path(args.run))
            print(f"{r['verified']}/{r['items']} responses verified → {args.run}/{r['letter']}, "
                  f"{args.run}/{r['docx']}, {args.run}/review_checks.md")
            return 0
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


def _style(args) -> int:
    from . import blind, pipeline, style
    from .hook import _summary
    try:
        if args.cmd == "style-build":
            idx = style.build(args.paths, Path(args.out))
            secs = {k: v["n"] for k, v in idx["profile"].items()}
            print(f"{len(idx['paragraphs'])} paragraphs from {len(idx['files'])} files → "
                  f"{args.out}/index.json; profiles: {secs}")
            print(f"see {args.out}/profile.md")
            return 0
        if args.cmd == "style-distance":
            idx = style.load(args.corpus)
            d = style.distance(idx, style.prose_of(_read(args.input)), args.section)
            print(f"style distance {d['score']} (profile: {d['profile_used']})")
            for r in d["rows"]:
                print(f"  {r['label']:<42} {r['value']:>7} vs {r['target']:<7} z={r['z']:+.1f}")
            for p in d["prefs"]:
                print(f"  preference: {p}")
            return 0
        if args.cmd == "style-brief":
            run = Path(args.run)
            state = pipeline.load(run)
            if not state.get("style_corpus"):
                raise pipeline.PipelineError("this run has no style corpus")
            d = pipeline._udir(run, args.unit)
            src = d / "masked_styled.txt" if (d / "masked_styled.txt").exists() else d / "revised.tex"
            text = src.read_text(encoding="utf-8")
            from .invariants import load_style
            fref = load_style(state["style"]).get("figure_ref") if state.get("style") else None
            print(style.brief(style.load(state["style_corpus"]), style.prose_of(text),
                              state.get("section_type"), figure_ref=fref))
            return 0
        if args.cmd == "style-gate":
            res = pipeline.style_gate(Path(args.run), args.unit)
            print(_summary(res))
            return 0 if res["status"] in ("styled", "kept-rewrite") else 1
        if args.cmd == "style-blind":
            print(f"wrote {blind.make_sheet(Path(args.run), args.seed)} — "
                  "fill it in without opening blind_key.json")
            return 0
        if args.cmd == "style-unblind":
            r = blind.score(Path(args.run))
            print(f"sounds like me — styled: {r['styled_mean']} · rewrite: {r['rewrite_mean']}")
            print(f"preferred — styled: {r['prefer_styled']} · rewrite: {r['prefer_rewrite']}"
                  + (f" · unrated: {', '.join(r['unrated'])}" if r["unrated"] else ""))
            return 0
    except (pipeline.PipelineError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
