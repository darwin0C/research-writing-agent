import tempfile
import unittest
from pathlib import Path

from checker.bib import bib_hints, parse_bib
from checker.invariants import Context, compare
from checker.terms import Term, term_hints


def layers(rep, level=None):
    return {f.layer for f in rep.findings if level is None or f.level == level}


class DirectionTest(unittest.TestCase):
    def test_from_to_reversed_blocks(self):
        rep = compare("The HTC rose from 12 kW to 18 kW.", "The HTC rose from 18 kW to 12 kW.")
        self.assertIn("L3-direction", layers(rep, "error"))

    def test_verb_contradicting_numbers_blocks(self):
        rep = compare("The pressure drop increased from 8.2 kPa to 15.6 kPa.",
                      "The pressure drop decreased from 8.2 kPa to 15.6 kPa.")
        self.assertIn("L3-direction", layers(rep, "error"))

    def test_antonym_swap_warns(self):
        rep = compare("At higher heat fluxes the deviation reached 2 K.",
                      "At lower heat fluxes the deviation reached 2 K.")
        self.assertIn("L3-direction", layers(rep, "warning"))

    def test_same_direction_reworded_is_clean(self):
        rep = compare("When subcooling was reduced from 20 K to 5 K, the diameter grew.",
                      "Reducing the subcooling from 20 K to 5 K enlarged the diameter.")
        self.assertNotIn("L3-direction", layers(rep))


class ScopeTest(unittest.TestCase):
    def test_bound_removed_blocks(self):
        rep = compare("The error was less than 1.5 K.", "The error was 1.5 K.")
        self.assertIn("L4-qualifier", layers(rep, "error"))

    def test_bound_flipped_blocks(self):
        rep = compare("Instabilities appear above 120 kW.", "Instabilities appear below 120 kW.")
        self.assertIn("L4-qualifier", layers(rep, "error"))

    def test_approximation_removed_warns(self):
        rep = compare("Nucleation took approximately 0.6 ns.", "Nucleation took 0.6 ns.")
        self.assertIn("L4-qualifier", layers(rep, "warning"))
        self.assertTrue(rep.passed)

    def test_under_condition_is_not_a_bound(self):
        rep = compare("Boiling under 400 K was stable.", "At 400 K, boiling was stable.")
        self.assertNotIn("L4-qualifier", layers(rep))

    def test_scope_phrase_dropped_warns(self):
        rep = compare("Under the investigated conditions, CHF increased by 40\\%.",
                      "CHF increased by 40\\%.")
        self.assertIn("L4-scope", layers(rep, "warning"))

    def test_scope_paraphrase_is_kept(self):
        rep = compare("Under the investigated conditions, CHF increased by 40\\%.",
                      "CHF increased by 40\\% for the conditions studied here.")
        self.assertNotIn("L4-scope", layers(rep))


class ClaimTest(unittest.TestCase):
    def test_ladder_rise_blocks(self):
        rep = compare("The data indicate a trend.", "The data demonstrate a trend.")
        self.assertIn("L5-claim", layers(rep, "error"))

    def test_suggest_replacing_vague_praise_is_fine(self):
        rep = compare("This finding sheds light on the interplay.",
                      "This result suggests that wettability matters.")
        self.assertNotIn("L5-claim", layers(rep, "error"))

    def test_weakening_is_fine(self):
        rep = compare("The data prove a trend.", "The data suggest a trend.")
        self.assertNotIn("L5-claim", layers(rep))

    def test_hedge_removed_warns(self):
        rep = compare("This may be caused by adsorption.", "This is caused by adsorption.")
        self.assertIn("L5-claim", layers(rep, "warning"))


class LatexSafetyTest(unittest.TestCase):
    def test_escaped_percent_is_a_unit(self):
        self.assertTrue(compare(r"It rose by 38\%.", r"It increased by 38\%.").passed)

    def test_unescaped_percent_blocks(self):
        rep = compare(r"It rose by 38\% at 12 K.", r"It rose by 38% at 12 K.")
        self.assertIn("L1-COMMENT", layers(rep, "error"))


class TermsAndBibTest(unittest.TestCase):
    TERMS = [Term("critical heat flux", "CHF", ["burnout heat flux"])]

    def test_variant_introduced_warns(self):
        rep = compare("The critical heat flux was 1 MW.", "The burnout heat flux was 1 MW.",
                      Context(glossary=self.TERMS))
        self.assertIn("T-term", layers(rep, "warning"))

    def test_abbreviation_hints(self):
        hints = term_hints("CHF rose. The critical heat flux (CHF) was high.", self.TERMS)
        self.assertTrue(any("before its definition" in h for h in hints))
        self.assertTrue(any("not defined" in h for h in term_hints("CHF rose.", self.TERMS)))

    def test_mixed_spelling_hint(self):
        hints = term_hints("The behavior of the vaporisation front.", [])
        self.assertTrue(any("mixed US" in h for h in hints))

    def test_vapour_counts_as_uk(self):
        self.assertTrue(any("mixed US" in h for h in term_hints("vapor and vapour", [])))

    def test_spelling_drift_warns(self):
        rep = compare("The behavior was stable.", "The behaviour was stable.")
        self.assertIn("T-spelling", layers(rep, "warning"))

    def test_bib_parse_and_hints(self):
        bib = parse_bib("@article{a1, title={x}, year={2020}}\n@book{b2,\n title={y {nested}},}\n"
                        "@article{a1, doi={10.1/x}}")
        self.assertEqual(set(bib), {"a1", "b2"})
        hints = bib_hints(r"See \cite{a1,zz9} and \citep[p.~3]{b2}.", bib)
        self.assertTrue(any("'zz9' is not in" in h for h in hints))
        self.assertTrue(any("'a1' is defined 2 times" in h for h in hints))

    def test_unknown_key_in_bib_check(self):
        bib = parse_bib("@article{a1, year={2020}}")
        rep = compare(r"As shown \cite{a1}.", r"As shown \cite{a1}.", Context(bib=bib))
        self.assertTrue(rep.passed)
        rep = compare(r"As shown \cite{zz9}.", r"As shown \cite{zz9}.", Context(bib=bib))
        self.assertIn("L6-cite", layers(rep, "warning"))  # already missing in original


class PipelineContextTest(unittest.TestCase):
    def test_split_with_style_and_bib(self):
        from checker import pipeline
        with tempfile.TemporaryDirectory() as tmp:
            bib = Path(tmp) / "r.bib"
            bib.write_text("@article{k1, year={2020}}")
            run = Path(tmp) / "run"
            text = ("The critical heat flux (CHF) increased by 40\\% under the investigated "
                    "conditions, as reported in previous work \\cite{k1,missing}.\n")
            state = pipeline.split(text, run, name="x", journal="", level="light",
                                   bib=str(bib), style="ijhmt")
            self.assertEqual(state["journal"], "International Journal of Heat and Mass Transfer")
            notes = (run / "section_notes.txt").read_text()
            self.assertIn("'missing' is not in the .bib", notes)

    def test_unknown_style_rejected(self):
        from checker import pipeline
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(pipeline.PipelineError):
                pipeline.split("x", Path(tmp) / "r", name="x", journal="", level="light",
                               style="nope")


class BenchmarkTest(unittest.TestCase):
    def test_benchmark_targets_met(self):
        from eval.run import evaluate
        res = evaluate()
        self.assertTrue(res["ok"], [r for r in res["rows"] if r.get("pass") is False]
                        or [c for c in res["clean"] if c["errors"]])


if __name__ == "__main__":
    unittest.main()
