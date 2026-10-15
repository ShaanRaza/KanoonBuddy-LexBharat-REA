"""Template library: every template renders cleanly, fields are escaped, and chat requests map to the right template."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import templates as T  # noqa: E402


def full_values(t):
    v = {}
    for f in t["fields"]:
        if f["kind"] == "choice":
            v[f["key"]] = f["choices"][0]
        elif f["kind"] == "textarea":
            v[f["key"]] = "line one\nline two"
        else:
            v[f["key"]] = "TESTVALUE"
    return v


class TemplateTests(unittest.TestCase):
    def test_ids_unique_and_complete(self):
        ids = [t["id"] for t in T.TEMPLATES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)
        for t in T.TEMPLATES:
            self.assertTrue(t["fields"] and t["notes"] and t["description"], t["id"])

    def test_every_placeholder_has_a_field(self):
        for t in T.TEMPLATES:
            keys = {f["key"] for f in t["fields"]}
            used = set(re.findall(r"\{\{(\w+)(?::\w+)?\}\}", t["body"])) | set(re.findall(r"^[?!](\w+)\s", t["body"], re.M))
            self.assertLessEqual(used, keys, f"{t['id']}: undefined fields {used - keys}")

    def test_filled_template_has_no_leftover_markers(self):
        for t in T.TEMPLATES:
            r = T.render(t["id"], full_values(t))
            self.assertEqual(r["missing"], [], t["id"])
            self.assertNotIn("{{", r["text"], t["id"])
            self.assertNotRegex(r["text"], r"\[[A-Z][A-Z '/()\-]+\]", f"{t['id']} left a placeholder")
            self.assertIn("TESTVALUE", r["text"], t["id"])

    def test_empty_template_shows_brackets_and_reports_missing(self):
        for t in T.TEMPLATES:
            r = T.render(t["id"], {})
            self.assertTrue(r["missing"], t["id"])
            self.assertRegex(r["text"], r"\[[A-Z]")

    def test_optional_paragraph_dropped_and_numbering_continuous(self):
        t = T.BY_ID["affidavit_residence"]
        v = full_values(t)
        v.pop("previous_address"); v.pop("documents")
        txt = T.render("affidavit_residence", v)["text"]
        nums = [int(n) for n in re.findall(r"(?m)^(\d+)\. ", txt)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))
        self.assertNotIn("before shifting", txt)

    def test_advocate_mode_changes_the_wording(self):
        for tid in ("legal_notice_cheque", "legal_notice_general"):
            v = full_values(T.BY_ID[tid])
            v.pop("advocate", None); v.pop("advocate_details", None)
            own = T.render(tid, v)["text"]
            self.assertNotIn("on behalf of my client", own, tid)
            v["advocate"] = "Priya Nair"
            adv = T.render(tid, v)["text"]
            self.assertIn("on behalf of my client", adv, tid)
            self.assertIn("I, Priya Nair, Advocate", adv, tid)
            self.assertNotIn("?advocate", adv, tid)
            self.assertNotRegex(adv, r"\[[A-Z][A-Z '/()\-]+\]", f"{tid} left a placeholder")

    def test_html_is_escaped(self):
        r = T.render("affidavit_general", {"name": "<script>alert(1)</script>", "facts": "a < b & c"})
        self.assertNotIn("<script>", r["html"])
        self.assertIn("&lt;script&gt;", r["html"])

    def test_unknown_template(self):
        with self.assertRaises(KeyError):
            T.render("nope", {})

    def test_chat_matching(self):
        cases = {"Draft a home affidavit": "affidavit_residence", "write a legal notice for cheque bounce": "legal_notice_cheque",
                 "prepare a rent agreement": "rent_agreement", "I need an NDA": "nda", "make a power of attorney": "poa_general",
                 "draft an income affidavit": "affidavit_income", "draft a name change affidavit": "affidavit_name_change",
                 "draft a legal notice for unpaid dues": "legal_notice_general", "draft an affidavit": "affidavit_general"}
        for q, want in cases.items():
            self.assertEqual(T.match_template(q), want, q)
        for q in ("what is an affidavit?", "draft a severability clause", "explain section 138", "BNS 103"):
            self.assertIsNone(T.match_template(q), q)

    def test_cheque_notice_states_the_rules(self):
        txt = T.render("legal_notice_cheque", full_values(T.BY_ID["legal_notice_cheque"]))["text"]
        self.assertIn("Section 138", txt)
        self.assertIn("fifteen (15) days", txt)


if __name__ == "__main__":
    unittest.main()
