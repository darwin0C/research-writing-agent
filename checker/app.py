"""Review app: a local web page for checking a run paragraph by paragraph.

    python3 -m checker app            # http://127.0.0.1:8765, opens the browser

No third-party packages; listens on 127.0.0.1 only. For a paper run you see each
paragraph's original and proposed version as a word-level diff, accept or reject each
change (or edit by hand), and every decision is re-checked against the original with the
same gates as the pipeline before it is saved. Export writes final.tex / final.txt, or
final_tracked.docx + final_clean.docx for Word. For a reviewer-response run you can edit
each reply; quotes and claimed changes are re-verified.
"""

from __future__ import annotations

import base64
import difflib
import json
import mimetypes
import re
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import pipeline, review
from .invariants import compare
from .latex_mask import PLACEHOLDER_RE, UnmaskError, text_format, unmask

STATIC = Path(__file__).resolve().parent / "static"
_NAME = re.compile(r"^[\w.\-]+$")
_TOKEN = re.compile(r"⟦[A-Z]+\d+⟧|\s+|\w+|[^\w\s]")
DOWNLOADABLE = {".tex", ".txt", ".md", ".docx", ".json"}


class AppError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def _r(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _fmt(state: dict) -> str:
    return state.get("format", "latex")


# ------------------------------------------------------------------ paper runs

def _labels(d: Path, fmt: str) -> dict[str, str]:
    if (d / "display.json").exists():
        disp = json.loads(_r(d / "display.json"))
        return {k: (v or PLACEHOLDER_RE.match(k).group(1).lower()) for k, v in disp.items()}
    if (d / "legend.md").exists():  # runs made before display.json existed
        rows = re.findall(r"^\|\s*(⟦[A-Z]+\d+⟧)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|", _r(d / "legend.md"), re.M)
        return {k: (shown if shown not in ("", "—") else what) for k, what, shown in rows}
    mapping = json.loads(_r(d / "map.json") or "{}")
    return {k: (v if len(v) <= 40 else v[:37] + "…") for k, v in mapping.items() if k != v}


def _proposed(run: Path, u: dict, state: dict) -> tuple[str, str]:
    """(masked text, source) of the version the pipeline settled on."""
    d = run / "units" / u["id"]
    s = pipeline.unit_status(run, u, state)
    if s == "styled":
        return _r(d / "masked_styled.txt"), "styled"
    if pipeline._base_status(run, u) == "passed":
        return _r(d / "masked_revised.txt"), "rewrite"
    return _r(d / "masked.txt"), "original"


def _glue(text: str) -> bool:
    """An unchanged stretch too small to stand between two changes on its own."""
    words = re.findall(r"\w+", text)
    return "⟦" not in text and (not words or (len(words) == 1 and len(words[0]) <= 4))


def segments(old: str, new: str) -> list[dict]:
    """Word-level diff, with changes that are only separated by a space or a short word
    ("the", "of") merged — a reordered sentence becomes one decision, not twenty."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    raw = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            raw.append({"op": "equal", "text": "".join(a[i1:i2])})
        else:
            raw.append({"op": "change", "old": "".join(a[i1:i2]), "new": "".join(b[j1:j2])})
    merged: list[dict] = []
    k = 0
    while k < len(raw):
        s = raw[k]
        if (s["op"] == "equal" and merged and merged[-1]["op"] == "change" and k + 1 < len(raw)
                and raw[k + 1]["op"] == "change" and _glue(s["text"])):
            nxt = raw[k + 1]
            merged[-1]["old"] += s["text"] + nxt["old"]
            merged[-1]["new"] += s["text"] + nxt["new"]
            k += 2
            continue
        merged.append(dict(s))
        k += 1
    n = 0
    for s in merged:
        if s["op"] == "change":
            n += 1
            s["id"] = n
    return merged


def _decisions(run: Path) -> dict:
    p = run / "decisions.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def check_paragraph(run: Path, uid: str, masked_text: str) -> dict:
    state = pipeline.load(run)
    d = run / "units" / uid
    if not (d / "masked.txt").exists():
        raise AppError(f"{uid} is not a prose paragraph")
    mapping = json.loads(_r(d / "map.json") or "{}")
    with text_format(_fmt(state)):
        try:
            tex = unmask(masked_text, mapping)
        except UnmaskError as e:
            return {"passed": False, "findings": [{"level": "error", "layer": "L0-placeholder",
                                                   "message": str(e)}]}
        rep = compare(_r(d / "original.tex"), tex, pipeline._ctx(run, state))
    return {"passed": rep.passed, "findings": [f.__dict__ for f in rep.findings], "tex": tex}


def decide(run: Path, uid: str, masked_text: str | None) -> dict:
    dec = _decisions(run)
    if masked_text is None:
        dec.pop(uid, None)
        res = {"passed": True, "findings": [], "cleared": True}
    else:
        res = check_paragraph(run, uid, masked_text)
        if not res["passed"]:
            return res  # never save a paragraph that fails the content checks
        dec[uid] = {"masked": masked_text, "time": time.strftime("%Y-%m-%d %H:%M"),
                    "warnings": len(res["findings"])}
    (run / "decisions.json").write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def paper_view(run: Path) -> dict:
    state = pipeline.load(run)
    dec = _decisions(run)
    fmt = _fmt(state)
    units = []
    for u in state["units"]:
        d = run / "units" / u["id"]
        item = {"id": u["id"], "kind": u["kind"], "status": pipeline.unit_status(run, u, state)}
        if u["kind"] != "prose":
            item["text"] = _r(d / "original.tex")
            units.append(item)
            continue
        original = _r(d / "masked.txt")
        proposed, source = _proposed(run, u, state)
        gates = (u.get("style_gates") or []) if source == "styled" else (u.get("gates") or [])
        item.update(original=original, proposed=proposed, source=source,
                    segments=segments(original, proposed), labels=_labels(d, fmt),
                    findings=gates[-1]["findings"] if gates else [],
                    attempts=u["attempts"], changes=_r(d / "changes.md"),
                    style_changes=_r(d / "style_changes.md"), issues=_r(d / "issues.md"),
                    decision=dec.get(u["id"]))
        units.append(item)
    final = state.get("final") or {}
    exports = [p.name for p in run.iterdir() if p.name.startswith("final")] if run.exists() else []
    return {"kind": "paper", "name": run.name, "format": fmt, "journal": state.get("journal"),
            "level": state.get("level"), "style": state.get("style"), "final": final,
            "claims": _r(run / "claims.md"), "units": units, "exports": sorted(exports),
            "files": _user_files(run)}


def _user_files(run: Path) -> list[str]:
    hidden = {"run.json", "review.json", "decisions.json", "changes.json", "manuscript.json",
              "manuscript_original.json"}
    return sorted(p.name for p in run.iterdir() if p.is_file() and p.suffix in DOWNLOADABLE
                  and not p.name.startswith(".") and p.name not in hidden)


def export_paper(run: Path) -> dict:
    state = pipeline.load(run)
    dec = _decisions(run)
    fmt = _fmt(state)
    texts: dict[str, str] = {}
    with text_format(fmt):
        for u in state["units"]:
            d = run / "units" / u["id"]
            original = _r(d / "original.tex")
            if u["kind"] == "prose" and u["id"] in dec:
                body = unmask(dec[u["id"]]["masked"], json.loads(_r(d / "map.json") or "{}"))
                lead = original[: len(original) - len(original.lstrip())]
                trail = original[len(original.rstrip()):]
                body = lead + body.strip() + trail
            elif u["kind"] == "prose" and pipeline.unit_status(run, u, state) == "styled":
                body = _r(d / "styled.tex")
            elif u["kind"] == "prose" and pipeline._base_status(run, u) == "passed":
                body = _r(d / "revised.tex")
            else:
                body = original
            texts[u["id"]] = body
        full = "".join(texts[u["id"]] + u["sep"] for u in state["units"])
        rep = compare(_r(run / "original.tex"), full, pipeline._ctx(run, state))
    files = []
    if fmt == "docx":
        from . import docx as dx
        doc = dx.read(run / "original.docx")
        new = {u["docx_index"]: texts[u["id"]] for u in state["units"]
               if u["kind"] == "prose" and u.get("docx_index") is not None}
        dx.write(doc, new, run / "final_tracked.docx", tracked=True)
        dx.write(doc, new, run / "final_clean.docx", tracked=False)
        files = ["final_tracked.docx", "final_clean.docx"]
    else:
        name = "final.tex" if fmt == "latex" else "final.txt"
        (run / name).write_text(full, encoding="utf-8")
        files = [name]
    from .latex_mask import EVIDENCE_RE
    evidence = [m[12:-2].strip() for m in EVIDENCE_RE.findall(full)]
    return {"passed": rep.passed, "findings": [f.__dict__ for f in rep.findings], "files": files,
            "decisions": len(dec), "evidence": evidence}


# ------------------------------------------------------------------ review runs

def review_view(run: Path) -> dict:
    st = json.loads(_r(run / "review.json"))
    items = []
    for it in st["items"]:
        text = _r(run / "items" / it["id"] / "response.md")
        items.append({"id": it["id"], "reviewer": it["reviewer"], "comment": it["comment"],
                      "response": text, "parsed": review.parse_response(text) if text else None,
                      "passed": bool(it.get("passed")) and not it.get("needs_author"),
                      "needs_author": it.get("needs_author", False),
                      "by_author": it.get("by_author", False), "findings": it.get("findings", [])})
    return {"kind": "review", "name": run.name, "lang": st.get("lang"), "items": items,
            "changes": json.loads(_r(run / "changes.json") or "[]"),
            "files": _user_files(run)}


# ------------------------------------------------------------------ jobs (standalone runs)

JOBS: dict[str, threading.Thread] = {}


def models_view() -> dict:
    from . import llm, rules
    cfg = llm.load_config()
    profiles = [{"name": n, "label": p.get("label") or n, "type": p.get("type"), "model": p.get("model", ""),
                 "base_url": p.get("base_url", ""), "key_env": p.get("key_env", ""),
                 "effort": p.get("effort", ""), "key": llm.key_status(n, p)}
                for n, p in cfg["profiles"].items()]
    nodes = {n: cfg["nodes"].get(n) or cfg["nodes"].get("default") for n in llm.NODES}
    try:
        import anthropic  # noqa: F401
        sdk = True
    except ImportError:
        sdk = False
    return {"profiles": profiles, "nodes": nodes, "default": cfg["nodes"].get("default"),
            "packs": rules.available(), "active_packs": cfg["rules"]["packs"], "anthropic_sdk": sdk}


def models_save(body: dict) -> dict:
    from . import llm
    allowed = {"type", "model", "base_url", "key_env", "effort", "label", "max_tokens", "temperature",
               "max_tokens_param"}
    profiles = {}
    for name, prof in (body.get("profiles") or {}).items():
        if not re.match(r"^[\w.\-]{1,40}$", name):
            raise AppError("profile names: letters, digits, . _ -")
        if prof is None:
            profiles[name] = None
            continue
        if prof.get("type") not in (None, "anthropic", "openai"):
            raise AppError("type must be anthropic or openai")
        profiles[name] = {k: v for k, v in prof.items() if k in allowed}
    cfg = llm.load_config()
    known = set(cfg["profiles"]) | {k for k, v in profiles.items() if v}
    nodes = body.get("nodes") or {}
    for node, prof in nodes.items():
        if node not in llm.NODES + ["default"] or prof not in known:
            raise AppError(f"bad node assignment {node} → {prof}")
    try:
        llm.save_local({"profiles": profiles, "nodes": nodes,
                        **({"rules": {"packs": body["packs"]}} if "packs" in body else {})})
    except llm.LLMError as e:
        raise AppError(str(e))
    return models_view()


def start_job(runs: Path, body: dict) -> dict:
    from .llm import LLMError, load_config, providers_for_nodes
    from .runner import Runner
    try:
        cfg = load_config()
        llms = providers_for_nodes(cfg, override=body.get("profile") or None)
    except LLMError as e:
        raise AppError(str(e))
    stem = re.sub(r"[^\w.\-]+", "-", Path(body.get("filename", "upload")).stem)[:40] or "upload"
    name = time.strftime("%Y%m%d-%H%M%S-") + stem
    run = runs / name
    up = runs / f".upload-{name}"
    up.mkdir(parents=True)
    log = run.parent / f".log-{name}.txt"

    def write_log(msg: str) -> None:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    def save(field: str, fname: str) -> Path:
        p = up / Path(fname).name
        p.write_bytes(base64.b64decode(body[field]))
        return p

    def work() -> None:
        try:
            r = Runner(llms, log=write_log, workers=int(body.get("workers") or 4),
                       packs=cfg["rules"]["packs"])
            write_log("models: " + ", ".join(f"{n}={getattr(p, 'label', '?')}" for n, p in llms.items()
                                             if n != "default"))
            write_log("rule packs: " + (", ".join(cfg["rules"]["packs"]) or "none"))
            if body.get("kind") == "review":
                review.split(save("comments", body["comments_name"]), save("original", body["original_name"]),
                             save("revised", body["revised_name"]), run, body.get("lang") or "en")
                r.run_review(run)
            else:
                src = save("data", body["filename"])
                kw = dict(name=name, journal=body.get("journal") or "", level=body.get("level") or "light",
                          style=body.get("style") or None, bib=None, glossary="default", style_corpus=None)
                if src.suffix == ".docx":
                    pipeline.split_docx(src, run, **kw)
                else:
                    fmt = "text" if src.suffix in (".txt", ".md") else "latex"
                    pipeline.split(src.read_text(encoding="utf-8"), run, source=str(src), fmt=fmt, **kw)
                r.run_paper(run)
            u = r.usage()
            write_log(f"API usage: {u['calls']} calls, {u['input']} in / {u['output']} out tokens")
            write_log("FINISHED")
        except Exception as e:  # reported to the page, not swallowed
            write_log(f"FAILED: {e}")

    t = threading.Thread(target=work, daemon=True)
    JOBS[name] = t
    t.start()
    return {"name": name}


# ------------------------------------------------------------------ HTTP

def list_runs(runs: Path) -> list[dict]:
    out = []
    if not runs.exists():
        return out
    for d in sorted(runs.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        if (d / "run.json").exists():
            st = json.loads(_r(d / "run.json"))
            prose = [u for u in st["units"] if u["kind"] == "prose"]
            out.append({"name": d.name, "kind": "paper", "format": st.get("format", "latex"),
                        "style": st.get("style"), "units": len(prose),
                        "gate": (st.get("final") or {}).get("passed")})
        elif (d / "review.json").exists():
            st = json.loads(_r(d / "review.json"))
            out.append({"name": d.name, "kind": "review", "items": len(st["items"]),
                        "verified": sum(1 for i in st["items"] if i.get("passed") and not i.get("needs_author"))})
    jobs = [{"name": n, "kind": "job", "running": t.is_alive()} for n, t in JOBS.items()
            if not (runs / n / "run.json").exists() and not (runs / n / "review.json").exists()]
    return jobs + out


def make_handler(runs: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _run(self, name: str) -> Path:
            if not _NAME.match(name):
                raise AppError("bad run name")
            p = runs / name
            if not p.is_dir():
                raise AppError("no such run", 404)
            return p

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 60 * 1024 * 1024:
                raise AppError("upload too large", 413)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            try:
                path = unquote(urlparse(self.path).path)
                if path in ("/", "/index.html"):
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/api/runs":
                    return self._json(list_runs(runs))
                if path == "/api/models":
                    return self._json(models_view())
                m = re.match(r"^/api/run/([^/]+)$", path)
                if m:
                    run = self._run(m.group(1))
                    if (run / "review.json").exists():
                        return self._json(review_view(run))
                    with text_format(_fmt(pipeline.load(run))):
                        return self._json(paper_view(run))
                m = re.match(r"^/api/log/([^/]+)$", path)
                if m:
                    if not _NAME.match(m.group(1)):
                        raise AppError("bad name")
                    return self._json({"log": _r(runs / f".log-{m.group(1)}.txt")})
                m = re.match(r"^/api/run/([^/]+)/file/([^/]+)$", path)
                if m:
                    run = self._run(m.group(1))
                    name = m.group(2)
                    p = run / name
                    if not _NAME.match(name) or p.suffix not in DOWNLOADABLE or not p.is_file():
                        raise AppError("file not available", 404)
                    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    return self._send(200, p.read_bytes(), ctype,
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
                raise AppError("not found", 404)
            except AppError as e:
                self._json({"error": str(e)}, e.status)
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_POST(self):
            try:
                path = unquote(urlparse(self.path).path)
                body = self._body()
                if path == "/api/new":
                    return self._json(start_job(runs, body))
                if path == "/api/models":
                    return self._json(models_save(body))
                if path == "/api/models/key":
                    from . import llm
                    if body.get("profile") not in llm.load_config()["profiles"]:
                        raise AppError("unknown profile")
                    try:
                        llm.save_key(body["profile"], (body.get("key") or "").strip() or None)
                    except OSError as e:
                        raise AppError(f"无法写入密钥文件 {llm.KEYS}（{e.strerror}）。请改用环境变量，"
                                       f"例如在 ~/.zshrc 中设置后重新启动应用。", 500)
                    return self._json(models_view())
                if path == "/api/models/test":
                    from . import llm
                    return self._json(llm.test_profile(body.get("profile", "")))
                m = re.match(r"^/api/run/([^/]+)/(check|decide|export|respond)$", path)
                if not m:
                    raise AppError("not found", 404)
                run, action = self._run(m.group(1)), m.group(2)
                if action == "respond":
                    return self._json(review.set_by_author(run, body["item"], body["text"]))
                if action == "export" and (run / "review.json").exists():
                    return self._json(review.assemble(run))
                if action == "check":
                    return self._json(check_paragraph(run, body["uid"], body["text"]))
                if action == "decide":
                    return self._json(decide(run, body["uid"], body.get("text")))
                return self._json(export_paper(run))
            except AppError as e:
                self._json({"error": str(e)}, e.status)
            except (KeyError, ValueError, pipeline.PipelineError) as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return Handler


def make_server(runs: Path, port: int = 8765) -> ThreadingHTTPServer:
    runs.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(runs.resolve()))


def serve(runs: Path, port: int = 8765, open_browser: bool = True) -> int:
    srv = make_server(runs, port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"review app: {url}  (runs from {runs.resolve()}; Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
