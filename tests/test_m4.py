import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from checker import docx, hook, pipeline, review
from checker.invariants import compare
from checker.latex_mask import text_format

ROOT = Path(__file__).resolve().parent.parent


def make_docx(tmp: Path) -> Path:
    subprocess.run([sys.executable, str(ROOT / "examples" / "make_demo_docx.py")], check=True,
                   capture_output=True)
    return ROOT / "examples" / "section.docx"


class DocxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = make_docx(Path(cls.tmp.name))
        cls.doc = docx.read(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_paragraphs_and_placeholders(self):
        ps = self.doc.paragraphs
        self.assertTrue(ps[0].heading)
        self.assertIn("⟦CITE1⟧", ps[1].text)
        self.assertNotIn("ZOTERO", ps[1].text)
        self.assertEqual(ps[2].display["⟦FMT1⟧"], "θ")
        self.assertEqual(ps[2].display["⟦REF1⟧"], "Fig. 1")
        self.assertEqual(ps[3].text, "⟦EQ1⟧")
        self.assertIn("garnered significant", ps[1].text)  # proofErr dropped, runs merged

    def _write(self, tracked):
        p = self.doc.paragraphs[2]
        new = p.text.replace("Our results clearly demonstrate that the", "The")
        out = Path(self.tmp.name) / f"o{tracked}.docx"
        self.assertEqual(docx.write(self.doc, {2: new}, out, tracked=tracked), 1)
        x = zipfile.ZipFile(out).read("word/document.xml").decode()
        ET.fromstring(x)
        return out, x

    def test_tracked_output(self):
        out, x = self._write(True)
        self.assertIn("<w:ins ", x)
        self.assertIn("<w:delText", x)
        self.assertIn("clearly demonstrate", x)  # kept as deleted text
        self.assertEqual(x.count("ZOTERO_ITEM"), 2)
        self.assertIn('mc:Ignorable="w14"', x)
        self.assertIn("<w:tbl>", x)

    def test_clean_output_rereads(self):
        out, x = self._write(False)
        self.assertNotIn("<w:ins ", x)
        d2 = docx.read(out)
        self.assertTrue(d2.paragraphs[2].text.startswith("⟦REF1⟧ presents"))
        self.assertIn("The hydrophilic surface", d2.paragraphs[2].text)
        self.assertEqual(d2.paragraphs[1].text, self.doc.paragraphs[1].text)  # untouched

    def test_untouched_package_parts_identical(self):
        out, _ = self._write(True)
        a, b = zipfile.ZipFile(self.path), zipfile.ZipFile(out)
        for n in a.namelist():
            if n != "word/document.xml":
                self.assertEqual(a.read(n), b.read(n))

    def test_write_refuses_missing_object(self):
        p = self.doc.paragraphs[1]
        with self.assertRaises(ValueError):
            docx.write(self.doc, {1: p.text.replace("⟦CITE1⟧", "")}, Path(self.tmp.name) / "x.docx")


class DocxPipelineTest(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            src = make_docx(Path(tmp))
            state = pipeline.split_docx(src, run, name="d", journal="", level="light")
            self.assertEqual(state["format"], "docx")
            self.assertEqual(state["section_type"], "results")
            kinds = [u["kind"] for u in state["units"]]
            self.assertEqual(kinds, ["frozen", "prose", "prose", "frozen", "prose"])
            self.assertTrue((run / "units" / "u03" / "legend.md").exists())
            for u in ("u02", "u03", "u05"):
                d = run / "units" / u
                (d / "issues.md").write_text("x")
                t = (d / "masked.txt").read_text()
                (d / "masked_revised.txt").write_text(
                    t.replace("Our results clearly demonstrate that the", "The")
                     .replace("In recent years, the", "The"))
            self.assertEqual(pipeline.gate(run, "u03")["status"], "passed")
            # losing a protected object fails the gate
            d = run / "units" / "u02"
            (d / "masked_revised.txt").write_text((d / "masked.txt").read_text().replace("⟦CITE1⟧", ""))
            self.assertEqual(pipeline.gate(run, "u02")["status"], "failed")
            (d / "masked_revised.txt").write_text((d / "masked.txt").read_text().replace("In recent years, the", "The"))
            pipeline.gate(run, "u02")
            pipeline.gate(run, "u05")
            final = pipeline.assemble(run)
            self.assertTrue(final["passed"], final)
            self.assertEqual(final["docx"]["paragraphs_changed"], 2)
            x = zipfile.ZipFile(run / "revised_tracked.docx").read("word/document.xml").decode()
            ET.fromstring(x)
            self.assertIn("<w:ins ", x)


class TextFormatTest(unittest.TestCase):
    def test_percent_is_not_a_comment(self):
        with text_format("text"):
            self.assertTrue(compare("提高了38%。", "提高了38%。").passed)
            self.assertFalse(compare("提高了38%。", "提高了48%。").passed)

    def test_text_split_keeps_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "r"
            pipeline.split("临界热流密度提高了38%，在本研究条件下壁面过热度从12 K降低到8 K，结果表明亲水表面可能延缓干涸。\n",
                           run, name="t", journal="", level="light", fmt="text", style="nsfc")
            self.assertIn("38%", (run / "units" / "u01" / "masked.txt").read_text())

    def test_chinese_style_corpus_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc = Path(tmp) / "sc"
            from checker import style
            style.build([str(ROOT / "examples" / "author_corpus")], sc)
            with self.assertRaises(pipeline.PipelineError):
                pipeline.split("近年来，沸腾传热受到广泛关注，具有重要意义。" * 3, Path(tmp) / "r",
                               name="t", journal="", level="light", fmt="text", style_corpus=str(sc))


class SuperscriptUnitTest(unittest.TestCase):
    def test_m2_equals_m_superscript_2(self):
        with text_format("text"):
            self.assertTrue(compare("质量流速为200 kg/(m2·s)。", "质量流速为200 kg/(m²·s)。").passed)
            self.assertTrue(compare("q = 2 MW/m2.", "q = 2 MW/m².").passed)


class ChineseChecksTest(unittest.TestCase):
    O = "在本研究条件下，壁面过热度从12 K降低到8 K，结果表明亲水表面可能延缓了干涸。误差小于1.5 K。"

    def layers(self, new):
        with text_format("text"):
            r = compare(self.O, new)
        return {(f.level, f.layer) for f in r.findings}

    def test_faithful(self):
        self.assertEqual(self.layers("在本研究条件下，壁面过热度由12 K降至8 K。结果表明，亲水表面可能延缓了干涸。误差小于1.5 K。"), set())

    def test_errors(self):
        self.assertIn(("error", "L3-direction"), self.layers(self.O.replace("从12 K降低到8 K", "从8 K降低到12 K")))
        self.assertIn(("error", "L5-claim"), self.layers(self.O.replace("表明", "证明")))
        self.assertIn(("error", "L4-qualifier"), self.layers(self.O.replace("小于1.5 K", "为1.5 K")))

    def test_approx_with_particle_kept(self):
        with text_format("text"):
            r = compare("约 3.7k star。", "约有 3.7k star。")
        self.assertNotIn("L4-qualifier", {f.layer for f in r.findings})

    def test_warnings(self):
        self.assertIn(("warning", "L5-claim"), self.layers(self.O.replace("可能", "")))
        self.assertIn(("warning", "L4-scope"), self.layers(self.O.replace("在本研究条件下，", "")))


class ReviewTest(unittest.TestCase):
    ORIG = "\\section{Results}\n\nOur results clearly prove that onset decreases from 350 ps to 125 ps.\n\nThe mechanism is unclear.\n"
    REV = "\\section{Results}\n\nThe results indicate that onset decreased from 350 ps to 125 ps at 300 K.\n\nThe mechanism is unclear.\n"
    COMMENTS = "Reviewer 1\n\n1. Tone down 'prove'.\n\n2. Explain the mechanism.\n\nReviewer 2\n\n1. Give the wall temperature.\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        (t / "o.tex").write_text(self.ORIG)
        (t / "r.tex").write_text(self.REV)
        (t / "c.txt").write_text(self.COMMENTS)
        self.run = t / "run"
        self.st = review.split(t / "c.txt", t / "o.tex", t / "r.tex", self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def respond(self, item, text):
        (self.run / "items" / item / "response.md").write_text(text)
        return review.check(self.run, item)

    def test_parse_and_diff(self):
        self.assertEqual([i["id"] for i in self.st["items"]], ["R1.01", "R1.02", "R2.01"])
        changes = json.loads((self.run / "changes.json").read_text())
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["section"], "Results")

    def test_honest_change_passes(self):
        r = self.respond("R1.01", "Response: Done.\nChange: 'prove' softened to 'indicate'\n"
                                  "Quote: The results indicate that onset decreased")
        self.assertEqual(r["status"], "passed", r)

    def test_invented_change_fails(self):
        r = self.respond("R1.02", "Response: We have added an explanation of the mechanism.\n"
                                  "Change: mechanism explained\nQuote: The mechanism is unclear.")
        self.assertIn("R-change-unbacked", {f["layer"] for f in r["findings"]})

    def test_missing_quote_fails(self):
        r = self.respond("R1.02", "Response: Revised.\nChange: added\nQuote: barrier is lower on hydrophobic walls")
        self.assertIn("R-quote-missing", {f["layer"] for f in r["findings"]})

    def test_change_none_is_allowed(self):
        r = self.respond("R1.02", "Response: We agree the mechanism is open; the authors will decide.\n"
                                  "Change: none")
        self.assertEqual(r["status"], "passed", r)

    def test_needs_author_after_three(self):
        for n in range(3):
            r = self.respond("R2.01", f"Response: Added {n}.\nChange: added\nQuote: nowhere {n}")
        self.assertEqual(r["status"], "needs-author")

    def test_assemble_letter(self):
        self.respond("R1.01", "Response: Done.\nChange: softened\nQuote: The results indicate that onset decreased")
        out = review.assemble(self.run)
        self.assertEqual(out["verified"], 1)
        letter = (self.run / "response_letter.md").read_text()
        self.assertIn("UNVERIFIED", letter)
        ET.fromstring(zipfile.ZipFile(self.run / "response_letter.docx").read("word/document.xml"))

    def test_hook_routes_response(self):
        p = self.run / "items" / "R1.01" / "response.md"
        p.write_text("Response: Revised.\nChange: x\nQuote: not there")
        out = io.StringIO()
        hook.main(io.StringIO(json.dumps({"tool_input": {"file_path": str(p)}})), out)
        self.assertEqual(json.loads(out.getvalue())["decision"], "block")

    def test_chinese_comment_parsing(self):
        items = review.parse_comments("审稿人 1\n1、请补充实验条件。\n2、结论过强。\n审稿人 2\n1. 图2不清楚。")
        self.assertEqual([i["id"] for i in items], ["R1.01", "R1.02", "R2.01"])


class GrantProfileTest(unittest.TestCase):
    def test_profiles_load(self):
        from checker.invariants import load_style
        self.assertEqual(load_style("nsfc")["kind"], "grant")
        self.assertEqual(load_style("nsf")["spelling"], "US")


if __name__ == "__main__":
    unittest.main()
