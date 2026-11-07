import unittest

from checker.audit import audit
from checker.invariants import compare, extract_quantities
from checker.latex_mask import UnmaskError, mask, unmask

PARA = (
    r"The onset of nucleation decreased from 350 ps to 125 ps when the wall "
    r"temperature increased to 400 K \cite{smith2020,li2021}. As shown in "
    r"Fig.~\ref{fig:onset}, the contact angle $\theta_c = 35^\circ$ governs "
    r"this trend (see Eq.~\eqref{eq:rate}). % TODO check angle" "\n"
    r"\begin{equation}J = J_0 \exp(-\Delta G / k_B T)\label{eq:rate}\end{equation}" "\n"
    r"The heat flux reached \SI{120}{\kilo\watt\per\meter\squared} for three cases."
)


def layers(rep, level="error"):
    return {f.layer for f in rep.findings if f.level == level}


class MaskTest(unittest.TestCase):
    def test_round_trip(self):
        res = mask(PARA)
        self.assertEqual(unmask(res.text, res.mapping), PARA)

    def test_protected_content_hidden(self):
        text = mask(PARA).text
        for s in (r"\cite", r"\ref", r"\eqref", r"\label", "$", r"\SI", "TODO", r"\begin"):
            self.assertNotIn(s, text)
        self.assertIn("350 ps", text)  # prose numbers stay visible to the model

    def test_escaped_dollar_and_percent_are_prose(self):
        res = mask(r"It costs \$5 and rose 20\% overall.")
        self.assertEqual(res.mapping, {})

    def test_unmask_rejects_missing_placeholder(self):
        res = mask(PARA)
        broken = res.text.replace("⟦CITE1⟧", "")
        with self.assertRaises(UnmaskError):
            unmask(broken, res.mapping)

    def test_unmask_rejects_invented_placeholder(self):
        res = mask(PARA)
        with self.assertRaises(UnmaskError):
            unmask(res.text + " ⟦CITE9⟧", res.mapping)


class CompareTest(unittest.TestCase):
    def test_faithful_rewrite_passes(self):
        revised = PARA.replace(
            "The onset of nucleation decreased from 350 ps to 125 ps",
            "Nucleation onset shortened from 350 ps to 125 ps",
        ).replace(r"\cite{smith2020,li2021}", r"\cite{li2021, smith2020}")
        rep = compare(PARA, revised)
        self.assertTrue(rep.passed, rep.to_dict())

    def test_changed_number_fails(self):
        rep = compare(PARA, PARA.replace("125 ps", "152 ps"))
        self.assertFalse(rep.passed)
        self.assertIn("L2-number", layers(rep))

    def test_changed_unit_fails(self):
        rep = compare(PARA, PARA.replace("125 ps", "125 ns"))
        self.assertFalse(rep.passed)
        self.assertIn("L2-unit", layers(rep))

    def test_dropped_citation_fails(self):
        rep = compare(PARA, PARA.replace(r"\cite{smith2020,li2021}", r"\cite{smith2020}"))
        self.assertIn("L1-CITE", layers(rep))

    def test_edited_equation_fails(self):
        rep = compare(PARA, PARA.replace(r"\exp(-\Delta G", r"\exp(\Delta G"))
        self.assertIn("L1-EQ", layers(rep))

    def test_edited_inline_math_fails(self):
        rep = compare(PARA, PARA.replace("35^\\circ", "53^\\circ"))
        self.assertIn("L1-EQ", layers(rep))

    def test_changed_si_quantity_fails(self):
        rep = compare(PARA, PARA.replace(r"\SI{120}", r"\SI{12}"))
        self.assertIn("L1-QTY", layers(rep))

    def test_number_word_converted_fails(self):
        rep = compare(PARA, PARA.replace("three cases", "four cases"))
        self.assertIn("L2-number", layers(rep))

    def test_number_word_to_digit_is_fine(self):
        self.assertTrue(compare(PARA, PARA.replace("three cases", "3 cases")).passed)

    def test_split_numbers_warn(self):
        orig = "The onset time decreased from 350 ps to 125 ps under 400 K."
        revised = "The onset time was 350 ps. At 400 K it dropped to 125 ps."
        rep = compare(orig, revised)
        self.assertTrue(rep.passed)
        self.assertIn("L2-binding", layers(rep, "warning"))

    def test_stronger_claim_blocks(self):
        orig = "These results suggest that the surface improves heat transfer."
        revised = "These results prove that the surface improves heat transfer."
        rep = compare(orig, revised)
        self.assertIn("L5-claim", layers(rep))

    def test_figure_numbers_are_tracked(self):
        rep = compare("As shown in Fig. 3, the flux rises.", "As shown in Fig. 4, the flux rises.")
        self.assertFalse(rep.passed)

    def test_units_normalised(self):
        q = extract_quantities("Grooves of 5 µm and 5 um and 25 ℃ and 10 percent.")
        self.assertEqual([x.unit for x in q], ["μm", "μm", "°C", "%"])


class AuditTest(unittest.TestCase):
    def test_finds_template_phrases(self):
        res = audit("In recent years, nanostructured surfaces have attracted increasing "
                    "attention. Notably, this paves the way for new designs. It is worth "
                    "noting that this proves the mechanism.")
        terms = {h["term"] for h in res["hits"]}
        self.assertIn("in recent years", terms)
        self.assertIn("notably,", terms)
        self.assertIn("paves the way", terms)
        self.assertIn("it is worth noting that", terms)
        self.assertIn("proves", terms)
        self.assertGreaterEqual(res["ai_phrases"], 4)

    def test_ignores_text_inside_comments(self):
        res = audit("Plain sentence. % in recent years")
        self.assertEqual(res["ai_phrases"], 0)


if __name__ == "__main__":
    unittest.main()
