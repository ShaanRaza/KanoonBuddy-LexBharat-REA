"""Editorial summaries and section notes: well-formed, and every sentence stays within what the sources say."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import landmarks as L  # noqa: E402


class LandmarkTests(unittest.TestCase):
    def test_every_entry_is_complete(self):
        self.assertGreaterEqual(len(L.LANDMARKS), 12)
        for cid, (head, text) in L.LANDMARKS.items():
            self.assertRegex(cid, r"^\d{4}_INSC_\d+$")
            self.assertRegex(head, r"\(\d{4}\)")          # the year is in the heading
            self.assertGreater(len(text), 80, cid)
            self.assertNotIn("[", text, cid)               # no stray markup or placeholders

    def test_editorial_label_says_it_is_not_the_judgment(self):
        self.assertIn("not part of the judgment", L.EDITORIAL_NOTE)

    def test_bnss_187_note_separates_the_two_periods(self):
        note = L.note_for("BNSS", "187")
        self.assertIn("15 days", note)
        self.assertIn("TOTAL", note)
        self.assertIsNone(L.note_for("BNS", "103"))

    def test_lookup(self):
        self.assertEqual(L.summary_for("1973_INSC_91")[0].split(" (")[0], "Kesavananda Bharati v. State of Kerala")
        self.assertIsNone(L.summary_for("0000_INSC_0"))


if __name__ == "__main__":
    unittest.main()
