import io
import json
import tempfile
import unittest
from pathlib import Path

from checker import hook, pipeline

SECTION = (
    "\\section{Results}\\label{sec:results}\n\n"
    "In recent years, wettability has attracted increasing attention. Our results clearly "
    "demonstrate that the onset time decreased from 350 ps to 125 ps at 300 K "
    "\\cite{kim2015}.\n\n"
    "\\begin{figure}[t]\n\\includegraphics{onset.pdf}\n\\caption{Onset.}\\label{fig:onset}\n"
    "\\end{figure}\n\n"
    "It is worth noting that the bubble radius grew to 12 nm within 0.5 ns on the "
    "hydrophilic wall, as shown in Fig.~\\ref{fig:onset}.\n"
)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"
        self.state = pipeline.split(SECTION, self.run, name="t", journal="IJHMT", level="light")
        self.prose = [u["id"] for u in self.state["units"] if u["kind"] == "prose"]

    def tearDown(self):
        self.tmp.cleanup()

    # helpers
    def masked(self, uid):
        return (self.run / "units" / uid / "masked.txt").read_text()

    def write(self, uid, name, text):
        (self.run / "units" / uid / name).write_text(text)

    def audited(self):
        for uid in self.prose:
            self.write(uid, "issues.md", "# Issues\n")

    def good(self, uid):
        t = self.masked(uid)
        return (t.replace("In recent years, wettability has attracted increasing attention. ", "")
                 .replace("Our results clearly demonstrate", "The results show")
                 .replace("It is worth noting that the", "The"))

    # tests
    def test_split_classifies_units(self):
        kinds = [u["kind"] for u in self.state["units"]]
        self.assertEqual(kinds, ["frozen", "prose", "frozen", "prose"])
        for f in ("graph.md", "progress.md", "checks.md", "run.json"):
            self.assertTrue((self.run / f).exists(), f)
        self.assertTrue(pipeline.status(self.run)["next"].startswith("spawn auditor"))
        self.assertEqual(pipeline.status(self.run)["by_status"]["needs-audit"], self.prose)

    def test_refuses_existing_run(self):
        with self.assertRaises(pipeline.PipelineError):
            pipeline.split(SECTION, self.run, name="t", journal="x", level="light")

    def test_status_flow_and_pass(self):
        self.audited()
        self.assertEqual(pipeline.status(self.run)["by_status"]["needs-rewrite"], self.prose)
        u = self.prose[0]
        self.write(u, "masked_revised.txt", self.good(u))
        self.assertIn(u, pipeline.status(self.run)["by_status"]["needs-gate"])
        res = pipeline.gate(self.run, u)
        self.assertEqual(res["status"], "passed", res)
        self.assertTrue((self.run / "units" / u / "revised.tex").exists())

    def test_gate_is_cached_per_content(self):
        self.audited()
        u = self.prose[0]
        self.write(u, "masked_revised.txt", self.masked(u).replace("350", "530"))
        self.assertEqual(pipeline.gate(self.run, u)["status"], "failed")
        again = pipeline.gate(self.run, u)
        self.assertTrue(again["cached"])
        self.assertEqual(pipeline.load(self.run)["units"][1]["attempts"], 1)

    def test_recheck_does_not_use_an_attempt(self):
        self.audited()
        u = self.prose[0]
        self.write(u, "masked_revised.txt", self.good(u))
        pipeline.gate(self.run, u)
        res = pipeline.gate(self.run, u, recheck=True)
        self.assertFalse(res["cached"])
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(len(pipeline.load(self.run)["units"][1]["gates"]), 1)

    def test_three_failures_revert(self):
        self.audited()
        u = self.prose[0]
        for n, bad in enumerate(("351", "352", "353"), 1):
            self.write(u, "masked_revised.txt", self.masked(u).replace("350", bad))
            res = pipeline.gate(self.run, u)
        self.assertEqual(res["status"], "reverted")
        self.assertIn("original text kept", pipeline.load(self.run)["decisions"][-1])
        self.assertEqual(pipeline.status(self.run)["by_status"]["reverted"], [u])
        self.assertIn("unresolved", (self.run / "checks.md").read_text())

    def test_lost_placeholder_fails(self):
        self.audited()
        u = self.prose[0]
        self.write(u, "masked_revised.txt", self.masked(u).replace("⟦CITE1⟧", ""))
        res = pipeline.gate(self.run, u)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["findings"][0]["layer"], "L0-placeholder")

    def test_assemble_requires_all_units_unless_partial(self):
        self.audited()
        u0, u1 = self.prose
        self.write(u0, "masked_revised.txt", self.good(u0))
        pipeline.gate(self.run, u0)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.assemble(self.run)
        final = pipeline.assemble(self.run, partial=True)
        self.assertTrue(final["partial"])
        self.assertTrue(final["passed"])

    def test_full_run_assembles_byte_exact_frame(self):
        self.audited()
        for u in self.prose:
            self.write(u, "masked_revised.txt", self.good(u))
            self.assertEqual(pipeline.gate(self.run, u)["status"], "passed")
        final = pipeline.assemble(self.run)
        self.assertTrue(final["passed"], final)
        revised = (self.run / "revised.tex").read_text()
        self.assertTrue(revised.startswith("\\section{Results}\\label{sec:results}\n\n"))
        self.assertIn("\\begin{figure}[t]", revised)
        self.assertNotIn("In recent years", revised)
        self.assertIn("The results show", revised)
        self.assertLess(final["audit_after"]["ai_phrases"], final["audit_before"]["ai_phrases"])
        report = (self.run / "report.md").read_text()
        self.assertIn("PASS", report)
        self.assertEqual(pipeline.status(self.run)["next"], "spawn claim-checker")
        (self.run / "claims.md").write_text("ok")
        self.assertTrue(pipeline.status(self.run)["next"].startswith("done"))

    def test_trailing_newline_from_rewriter_is_normalised(self):
        self.audited()
        for u in self.prose:
            self.write(u, "masked_revised.txt", "\n" + self.good(u) + "\n\n")
            pipeline.gate(self.run, u)
        pipeline.assemble(self.run)
        revised = (self.run / "revised.tex").read_text()
        self.assertNotIn("\n\n\n", revised)
        self.assertIn("\\cite{kim2015}.\n\n\\begin{figure}", revised)

    def test_reopen_sends_unit_back(self):
        self.audited()
        u = self.prose[0]
        self.write(u, "masked_revised.txt", self.good(u))
        pipeline.gate(self.run, u)
        res = pipeline.reopen(self.run, u, "keep 'at 300 K' next to the result")
        self.assertEqual(res["attempts_left"], 2)
        st = pipeline.status(self.run)["by_status"]
        self.assertIn(u, st["needs-rewrite"])
        d = self.run / "units" / u
        self.assertIn("300 K", (d / "feedback.md").read_text())
        self.assertTrue((d / "attempts" / "masked_revised.1.txt").exists())

    def test_hook_runs_gate_and_blocks_on_failure(self):
        self.audited()
        u = self.prose[1]
        path = self.run / "units" / u / "masked_revised.txt"
        path.write_text(self.masked(u).replace("12 nm", "12 μm"))
        out = io.StringIO()
        hook.main(io.StringIO(json.dumps({"tool_input": {"file_path": str(path)}})), out)
        msg = json.loads(out.getvalue())
        self.assertEqual(msg["decision"], "block")
        self.assertIn("FAILED", msg["reason"])

        path.write_text(self.good(u))
        out = io.StringIO()
        hook.main(io.StringIO(json.dumps({"tool_input": {"file_path": str(path)}})), out)
        msg = json.loads(out.getvalue())
        self.assertIn("PASSED", msg["hookSpecificOutput"]["additionalContext"])

    def test_hook_ignores_other_files(self):
        out = io.StringIO()
        hook.main(io.StringIO(json.dumps({"tool_input": {"file_path": "/tmp/x.txt"}})), out)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
