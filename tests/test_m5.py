import json
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from checker import app, pipeline, review
from checker.runner import Runner, _files

ROOT = Path(__file__).resolve().parent.parent


def _block(text: str, name: str) -> str:
    m = re.search(r'<file path="' + re.escape(name) + r'">\n(.*?)\n</file>', text, re.S)
    return m.group(1) if m else ""


class FakeClaude:
    """Plays every agent from scripted rules; records each call."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def turn(self, system, messages):
        with self.lock:
            self.calls.append((system[:4000], len(messages)))
        first = messages[0]["content"]
        turns = sum(1 for m in messages if m["role"] == "assistant")
        if "You audit academic prose" in system:
            ids = re.findall(r"(u\d+)/masked\.txt", first)
            return "".join(f'<file path="{u}/issues.md">\n# Issues · {u}\n| 1 | x |\n</file>\n' for u in ids), []
        if "You rewrite exactly one paragraph" in system:
            masked = _block(first, "masked.txt")
            good = masked.replace("clearly ", "").replace("In recent years, the", "The")
            if turns == 0 and "feedback.md" not in first and "350" in masked:
                bad = good.replace("350", "351")  # first try breaks a number
                return f'<file path="masked_revised.txt">\n{bad}\n</file>\n<file path="changes.md">\nv1\n</file>', []
            assert turns == 0 or "Gate result" in messages[-1]["content"]
            return f'<file path="masked_revised.txt">\n{good}\n</file>\n<file path="changes.md">\nv2\n</file>', []
        if "You check claims against evidence" in system:
            return ('<file path="claims.md">\n| Unit | x |\n## Reopen\n- u05: keep the hedge in the last sentence\n</file>'), []
        if "You answer one reviewer comment" in system:
            quote = "We now examine its effect on nucleation with molecular dynamics simulations."
            return (f'<file path="response.md">\nResponse: The opening was rewritten.\nChange: opening '
                    f'sentence rewritten\nLocation: Results and discussion\nQuote: {quote}\n</file>'), []
        raise AssertionError("unexpected agent")


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        pipeline.split((ROOT / "examples" / "section.tex").read_text(), self.run, name="t",
                       journal="IJHMT", level="light", style="ijhmt")
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_paper_run(self):
        fake = FakeClaude()
        final = Runner(fake, log=self.log.append, workers=2).run_paper(self.run)
        self.assertTrue(final["passed"], final)
        state = pipeline.load(self.run)
        u03 = pipeline._unit(state, "u03")
        self.assertEqual(u03["attempts"], 2)               # bad try, gate feedback, fixed
        self.assertFalse(u03["gates"][0]["passed"])
        self.assertIn("u05: reopened", " ".join(state["decisions"]))
        self.assertTrue((self.run / "claims.md").exists())
        self.assertNotIn("clearly", (self.run / "revised.tex").read_text())
        self.assertIn("351", "".join(json.dumps(g) for g in u03["gates"]))  # error was reported
        self.assertTrue(any("done" in line for line in self.log))
        # standalone preamble + agent file body are the system prompt
        self.assertTrue(all("running inside a program" in c[0] for c in fake.calls))

    def test_file_blocks_are_restricted(self):
        out = _files('<file path="../../etc/passwd">x</file><file path="masked_revised.txt">\nok\n</file>',
                     {"masked_revised.txt"})
        self.assertEqual(out, {"masked_revised.txt": "ok"})

    def test_review_run(self):
        rrun = Path(self.tmp.name) / "rev"
        review.split(ROOT / "examples" / "reviewer_comments.txt", ROOT / "examples" / "section.tex",
                     ROOT / "runs" / "demo-style" / "revised.tex", rrun)
        out = Runner(FakeClaude(), log=self.log.append, workers=3).run_review(rrun)
        self.assertEqual(out["items"], 3)
        self.assertEqual(out["verified"], 3)
        self.assertTrue((rrun / "response_letter.docx").exists())


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.runs = Path(cls.tmp.name) / "runs"
        cls.runs.mkdir()
        shutil.copytree(ROOT / "runs" / "demo-docx", cls.runs / "demo-docx")
        shutil.copytree(ROOT / "runs" / "demo-section", cls.runs / "demo-section")
        shutil.copytree(ROOT / "runs" / "demo-review", cls.runs / "demo-review")
        for p in (cls.runs / "demo-docx").glob("final*"):
            p.unlink()
        (cls.runs / "demo-docx" / "decisions.json").unlink(missing_ok=True)
        cls.srv = app.make_server(cls.runs, 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.read(), r.headers

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"status": e.code, **json.loads(e.read())}

    def test_index_and_runs(self):
        html, _ = self.get("/")
        self.assertIn(b"<title>", html)
        runs = json.loads(self.get("/api/runs")[0])
        kinds = {r["name"]: r["kind"] for r in runs}
        self.assertEqual(kinds["demo-review"], "review")
        self.assertEqual(kinds["demo-docx"], "paper")

    def test_paper_view_has_segments_and_labels(self):
        v = json.loads(self.get("/api/run/demo-docx")[0])
        u = next(x for x in v["units"] if x["id"] == "u03")
        self.assertTrue(any(s["op"] == "change" for s in u["segments"]))
        self.assertEqual(u["labels"]["⟦FMT1⟧"], "θ")
        composed = "".join(s["text"] if s["op"] == "equal" else s["new"] for s in u["segments"])
        self.assertEqual(composed, u["proposed"])

    def test_bad_decision_is_refused(self):
        v = json.loads(self.get("/api/run/demo-docx")[0])
        u = next(x for x in v["units"] if x["id"] == "u03")
        bad = u["proposed"].replace("⟦CITE1⟧", "").replace("350", "530")
        r = self.post("/api/run/demo-docx/decide", {"uid": "u03", "text": bad})
        self.assertFalse(r["passed"])
        self.assertFalse((self.runs / "demo-docx" / "decisions.json").exists()
                         and "u03" in json.loads((self.runs / "demo-docx" / "decisions.json").read_text()))

    def test_decision_and_docx_export(self):
        v = json.loads(self.get("/api/run/demo-docx")[0])
        u = next(x for x in v["units"] if x["id"] == "u03")
        # reject the change that removed "Our results clearly demonstrate", accept the rest
        rej = next(s["id"] for s in u["segments"] if s["op"] == "change" and "clearly" in s["old"])
        text = "".join(s["text"] if s["op"] == "equal" else (s["old"] if s["id"] == rej else s["new"])
                       for s in u["segments"])
        r = self.post("/api/run/demo-docx/decide", {"uid": "u03", "text": text})
        self.assertTrue(r["passed"], r)
        out = self.post("/api/run/demo-docx/export", {})
        self.assertTrue(out["passed"], out)
        self.assertEqual(out["files"], ["final_tracked.docx", "final_clean.docx"])
        x = zipfile.ZipFile(self.runs / "demo-docx" / "final_clean.docx").read("word/document.xml").decode()
        self.assertIn("Our results clearly demonstrate", x)  # the rejected change kept the original words
        data, headers = self.get("/api/run/demo-docx/file/final_tracked.docx")
        self.assertTrue(data.startswith(b"PK"))
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_latex_export(self):
        out = self.post("/api/run/demo-section/export", {})
        self.assertTrue(out["passed"], out)
        self.assertTrue((self.runs / "demo-section" / "final.tex").exists())

    def test_live_check(self):
        v = json.loads(self.get("/api/run/demo-section")[0])
        u = next(x for x in v["units"] if x["id"] == "u03")
        r = self.post("/api/run/demo-section/check", {"uid": "u03", "text": u["proposed"].replace("125", "152")})
        self.assertIn("L2-number", {f["layer"] for f in r["findings"]})

    def test_review_respond(self):
        r = self.post("/api/run/demo-review/respond",
                      {"item": "R2.01", "text": "Response: Added.\nChange: added\nQuote: not in the paper"})
        self.assertEqual(r["status"], "failed")
        v = json.loads(self.get("/api/run/demo-review")[0])
        self.assertTrue(next(i for i in v["items"] if i["id"] == "R2.01")["needs_author"])

    def test_path_traversal_blocked(self):
        for p in ("/api/run/..%2F..%2Fetc", "/api/run/demo-docx/file/..%2Frun.json",
                  "/api/run/demo-docx/file/run.py"):
            with self.assertRaises(urllib.error.HTTPError):
                self.get(p)

    def test_new_run_without_sdk_reports_error(self):
        try:
            import anthropic  # noqa: F401
            self.skipTest("SDK installed")
        except ImportError:
            pass
        r = self.post("/api/new", {"kind": "paper", "filename": "x.txt", "data": ""})
        self.assertIn("pip install anthropic", r["error"])


if __name__ == "__main__":
    unittest.main()
