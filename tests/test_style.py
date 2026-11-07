import io
import json
import tempfile
import unittest
from pathlib import Path

from checker import blind, hook, pipeline, style

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "examples" / "author_corpus"

SECTION = (
    "\\section{Results}\n\n"
    "It was observed that the evaporation of the liquid film was accelerated on the "
    "hydrophilic wall, with the rupture time decreasing from 4.2 ns to 2.8 ns, as shown "
    "in Fig.~\\ref{fig:a}, which is attributed to the reduction of the interfacial resistance.\n"
)


class StyleModuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.index = style.build([str(CORPUS)], Path(cls.tmp.name) / "sc")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_reads_sections_and_skips_readme(self):
        self.assertEqual(len(self.index["files"]), 3)
        self.assertIn("results", self.index["profile"])
        self.assertTrue((Path(self.tmp.name) / "sc" / "profile.md").exists())

    def test_profile_captures_habits(self):
        prof = self.index["profile"]["all"]
        self.assertEqual(prof["fig_pref"], "Figure")
        self.assertEqual(prof["study_phrase"], "this work")
        self.assertEqual(prof["spelling"], "UK")
        self.assertGreater(prof["we_rate"]["mean"], 20)

    def test_retrieval_finds_topical_paragraph(self):
        hits = style.retrieve(self.index, "pressure drop oscillations restrictors microchannel", k=1)
        self.assertIn("paper_b", hits[0][1]["source"])
        hits = style.retrieve(self.index, "film rupture contact angle hydrophobic wall", k=1)
        self.assertIn("paper_a", hits[0][1]["source"])

    def test_distance_prefers_authors_voice(self):
        far = style.prose_of(SECTION)
        near = ("We find that the film ruptures sooner on the hydrophilic wall. "
                "Figure 2 shows this. The rupture time falls from 4.2 ns to 2.8 ns. "
                "We think the lower interfacial resistance causes it.")
        d_far = style.distance(self.index, far, "results")
        d_near = style.distance(self.index, near, "results")
        self.assertLess(d_near["score"], d_far["score"])
        self.assertTrue(any("Fig." in p for p in d_far["prefs"]))

    def test_journal_figure_style_overrides_author(self):
        text = "We find that Figure 2 shows the trend clearly enough for this."
        self.assertFalse(style.distance(self.index, text, "results")["prefs"])
        prefs = style.distance(self.index, text, "results", figure_ref="Fig.")["prefs"]
        self.assertTrue(any("journal uses 'Fig.'" in p for p in prefs))

    def test_recycling_detected_only_for_new_overlap(self):
        copied = self.index["paragraphs"][0]["text"]
        seq = " ".join(copied.split()[:14])
        self.assertTrue(style.recycled(self.index, "unrelated original text here", seq))
        self.assertEqual(style.recycled(self.index, seq, seq), [])  # already in the original

    def test_brief_lists_exemplars(self):
        b = style.brief(self.index, style.prose_of(SECTION), "results")
        self.assertIn("Your most similar earlier paragraphs", b)
        self.assertIn("Do not copy wording", b)


class StylePipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.sc = base / "sc"
        self.index = style.build([str(CORPUS)], self.sc)
        self.run = base / "run"
        pipeline.split(SECTION, self.run, name="s", journal="", level="light",
                       style_corpus=str(self.sc))
        self.uid = "u02"
        self.d = self.run / "units" / self.uid
        (self.d / "issues.md").write_text("# Issues\n")
        masked = (self.d / "masked.txt").read_text()
        self.rewrite = masked.replace("It was observed that the", "The")
        (self.d / "masked_revised.txt").write_text(self.rewrite)
        self.assertEqual(pipeline.gate(self.run, self.uid)["status"], "passed")

    def tearDown(self):
        self.tmp.cleanup()

    def styled_ok(self):
        return (
            "We find that the liquid film evaporated faster on the hydrophilic wall. "
            "The rupture time decreased from 4.2 ns to 2.8 ns, as shown in Figure~⟦REF1⟧. "
            "We attribute this to the lower interfacial resistance.")

    def status(self):
        return pipeline.status(self.run)

    def test_section_type_detected(self):
        self.assertEqual(pipeline.load(self.run)["section_type"], "results")

    def test_status_asks_for_style_after_pass(self):
        self.assertIn(self.uid, self.status()["by_status"]["needs-style"])
        self.assertTrue(self.status()["next"].startswith("spawn one style-calibrator"))

    def test_style_pass_is_used_in_assembly(self):
        (self.d / "masked_styled.txt").write_text(self.styled_ok())
        res = pipeline.style_gate(self.run, self.uid)
        self.assertEqual(res["status"], "styled", res)
        final = pipeline.assemble(self.run)
        self.assertTrue(final["passed"], final)
        self.assertIn("We attribute this", (self.run / "revised.tex").read_text())
        st = final["style"]
        self.assertLess(st["units"][self.uid]["styled"], st["units"][self.uid]["rewrite"])
        self.assertIn("风格距离", (self.run / "report.md").read_text())

    def test_edit_after_acceptance_is_rechecked(self):
        (self.d / "masked_styled.txt").write_text(self.styled_ok())
        self.assertEqual(pipeline.style_gate(self.run, self.uid)["status"], "styled")
        edited = self.styled_ok().replace("4.2 ns", "4.9 ns")
        (self.d / "masked_styled.txt").write_text(edited)
        self.assertIn(self.uid, self.status()["by_status"]["needs-style-gate"])
        res = pipeline.style_gate(self.run, self.uid)
        self.assertFalse(res["cached"])
        self.assertEqual(res["attempts"], 2)
        self.assertEqual(res["status"], "kept-rewrite")  # bad edit, no attempts left
        pipeline.assemble(self.run)
        self.assertNotIn("4.9", (self.run / "revised.tex").read_text())

    def test_edit_after_last_attempt_is_ignored(self):
        for text in (self.styled_ok().replace("4.2", "4.4"), self.styled_ok()):
            (self.d / "masked_styled.txt").write_text(text)
            pipeline.style_gate(self.run, self.uid)  # fail, then pass on attempt 2
        (self.d / "masked_styled.txt").write_text(self.styled_ok().replace("We find", "Clearly we find"))
        res = pipeline.style_gate(self.run, self.uid)
        self.assertTrue(res["cached"])
        self.assertIn("S-ignored", {f["layer"] for f in res["findings"]})
        pipeline.assemble(self.run)
        self.assertNotIn("Clearly", (self.run / "revised.tex").read_text())

    def test_style_failure_keeps_rewrite_not_original(self):
        bad = self.styled_ok().replace("4.2 ns", "4.3 ns")
        for _ in range(2):
            (self.d / "masked_styled.txt").write_text(bad)
            res = pipeline.style_gate(self.run, self.uid)
            bad = bad.replace("We find", "We see")  # new content, same error
        self.assertEqual(res["status"], "kept-rewrite")
        pipeline.assemble(self.run)
        out = (self.run / "revised.tex").read_text()
        self.assertNotIn("It was observed", out)  # rewrite kept, not the original
        self.assertNotIn("4.3", out)

    def test_recycled_wording_blocks(self):
        copied = " ".join(self.index["paragraphs"][3]["text"].split()[:12])
        (self.d / "masked_styled.txt").write_text(self.styled_ok() + " " + copied)
        res = pipeline.style_gate(self.run, self.uid)
        self.assertIn("L7-recycle", {f["layer"] for f in res["findings"]})

    def test_hook_routes_styled_file(self):
        path = self.d / "masked_styled.txt"
        path.write_text(self.styled_ok())
        out = io.StringIO()
        hook.main(io.StringIO(json.dumps({"tool_input": {"file_path": str(path)}})), out)
        self.assertIn("Style gate", json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"])

    def test_reopen_resets_style(self):
        (self.d / "masked_styled.txt").write_text(self.styled_ok())
        pipeline.style_gate(self.run, self.uid)
        pipeline.reopen(self.run, self.uid, "fix x")
        u = pipeline._unit(pipeline.load(self.run), self.uid)
        self.assertFalse(u["style_done"])
        self.assertFalse((self.d / "masked_styled.txt").exists())

    def test_blind_sheet_roundtrip(self):
        (self.d / "masked_styled.txt").write_text(self.styled_ok())
        pipeline.style_gate(self.run, self.uid)
        sheet = blind.make_sheet(self.run, seed=1)
        key = json.loads((self.run / "blind_key.json").read_text())
        styled_label = "A" if key["1"]["A"] == "styled" else "B"
        other = "B" if styled_label == "A" else "A"
        text = sheet.read_text()
        text = text.replace(f"- {styled_label} sounds like me (1–5): ", f"- {styled_label} sounds like me (1–5): 5")
        text = text.replace(f"- {other} sounds like me (1–5): ", f"- {other} sounds like me (1–5): 2")
        text = text.replace("- Prefer (A/B): ", f"- Prefer (A/B): {styled_label}")
        sheet.write_text(text)
        r = blind.score(self.run)
        self.assertEqual((r["styled_mean"], r["rewrite_mean"], r["prefer_styled"]), (5, 2, 1))

    def test_run_without_corpus_is_unchanged(self):
        run2 = Path(self.tmp.name) / "run2"
        pipeline.split(SECTION, run2, name="s2", journal="", level="light")
        d = run2 / "units" / "u02"
        (d / "issues.md").write_text("x")
        (d / "masked_revised.txt").write_text(self.rewrite)
        pipeline.gate(run2, "u02")
        self.assertEqual(pipeline.status(run2)["next"], "assemble")


if __name__ == "__main__":
    unittest.main()
