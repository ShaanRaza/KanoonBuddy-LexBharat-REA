"""Translation guard rails: protected items survive, terms are never swapped, bad output is rejected. No model needed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import translate as T  # noqa: E402


class TranslateTests(unittest.TestCase):
    def test_protect_and_restore_round_trip(self):
        for text in ("Bail under section 480 of the BNSS.",
                     "Notice under Section 138 of the Negotiable Instruments Act, 1881 for cheque no. 004512 for Rs. 2,50,000.",
                     "See [1978] 2 S.C.R. 621 and AIR 1978 SC 597 on Article 21.",
                     "No numbers or acts here at all."):
            protected, items = T.protect(text)
            self.assertEqual(T.restore(protected, items), text)

    def test_numbers_and_acts_become_tokens(self):
        protected, items = T.protect("Section 480 of the BNSS, Rs. 2,50,000")
        self.assertNotIn("480", protected)
        self.assertNotIn("2,50,000", protected)
        self.assertNotIn("BNSS", protected)
        self.assertEqual(items[:2], ["480", "BNSS"])

    def test_prompt_mentions_tokens_only_when_there_are_some(self):
        with_items = T.build_messages("en", "hi", "x [[1]]", 1)[0]["content"]
        without = T.build_messages("en", "hi", "x", 0)[0]["content"]
        self.assertIn("[[1]]", with_items)
        self.assertNotIn("[[1]]", without)     # a model told about tokens that do not exist invents them

    def test_english_to_hindi_glossary_never_offers_bailable_inside_non_bailable(self):
        g = T.glossary_for("en", "hi", "The offence is non-bailable and the accused sought anticipatory bail.")
        joined = " | ".join(g)
        self.assertIn("non-bailable = अजमानतीय", joined)
        self.assertIn("anticipatory bail = अग्रिम जमानत", joined)
        self.assertNotIn("bailable = जमानतीय", joined.replace("non-bailable = अजमानतीय", ""))
        self.assertNotIn("bail = जमानत", joined.replace("anticipatory bail = अग्रिम जमानत", ""))

    def test_hindi_to_english_glossary_uses_the_longest_term(self):
        g = T.glossary_for("hi", "en", "यह अपराध असंज्ञेय और अजमानतीय है।")
        self.assertIn("अजमानतीय = non-bailable", g)
        self.assertIn("असंज्ञेय = non-cognizable", g)
        self.assertFalse(any(x.startswith("जमानत ") or x.startswith("संज्ञेय ") for x in g))   # the shorter terms inside them are dropped

    def test_validation_rejects_bad_output(self):
        self.assertIsNone(T.validate("hi", "जमानत [[1]] [[2]]", 2))
        self.assertIsNone(T.validate("en", "bail under [[1]]", 1))
        self.assertEqual(T.validate("hi", "bail [[1]]", 1), "wrong script")
        self.assertEqual(T.validate("hi", "जमानत [[1]]", 2), "a protected item was lost or changed")
        self.assertEqual(T.validate("hi", "जमानत [[1]] [[1]]", 1), "a protected item was lost or changed")
        self.assertEqual(T.validate("hi", "जमानत 保释", 0), "foreign script")
        self.assertEqual(T.validate("hi", "  ", 0), "empty")
        self.assertEqual(T.validate("hi", "जमानत [[1]]", 0), "a protected item was lost or changed")   # an invented token

    def test_sentence_splitting_keeps_abbreviations_together(self):
        s = T.split_sentences("The accused was arrested under FIR No. 214 of 2026. He is charged under Section 303 of the BNS. The cheque for Rs. 2,50,000 bounced. Hearing on 20 November.")
        self.assertEqual(len(s), 4)
        self.assertTrue(s[0].endswith("2026."))
        self.assertTrue(s[1].endswith("BNS."))
        self.assertEqual(len(T.split_sentences("अभियुक्त को हिरासत में भेजा गया। याचिकाकर्ता ने आवेदन दाखिल किया।")), 2)

    def test_place_and_court_names_are_kept_verbatim(self):
        p, items = T.protect("registered at Kothrud Police Station and heard by the Bombay High Court")
        self.assertIn("Kothrud Police Station", items)
        self.assertIn("Bombay High Court", items)

    def test_only_english_and_hindi_are_supported(self):
        self.assertEqual(T.SUPPORTED, {"en", "hi"})


if __name__ == "__main__":
    unittest.main()
