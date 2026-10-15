"""AI Tools endpoints (code converter, translate validation) and the landing pages around them."""
import os, tempfile, unittest

_TMP = tempfile.mkdtemp(prefix="lexbharat-test-")
os.environ.update({"LEXBHARAT_ENV": "dev", "LEXBHARAT_SECRET": "x" * 48, "LEXBHARAT_DATA": _TMP,
                   "AUTH_DB": f"{_TMP}/auth.sqlite", "NYRA_DB": f"{_TMP}/nyra.sqlite", "EDITOR_DB": f"{_TMP}/editor.sqlite"})

from fastapi.testclient import TestClient  # noqa: E402
from server import auth  # noqa: E402
from server.main import app  # noqa: E402

PW = "correct horse battery staple"


class ToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app, follow_redirects=False); cls.c = cls.ctx.__enter__()
        auth.create_user("t@example.com", PW)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def setUp(self):
        auth.limiter.reset()
        tok = self.c.post("/api/auth/login", json={"email": "t@example.com", "password": PW}).json()["data"]["token"]
        self.h = {"Authorization": "Bearer " + tok}

    def test_tools_need_login(self):
        self.assertEqual(self.c.get("/api/tools/code-converter").status_code, 401)
        self.assertEqual(self.c.post("/api/tools/translate", json={"text": "x", "sourceLang": "en", "targetLang": "hi"}).status_code, 401)

    def test_converter_pairs(self):
        r = self.c.get("/api/tools/code-converter?pair=ipc-bns", headers=self.h).json()
        m = {x["oldSection"]: x["newSection"] for x in r["results"]}
        self.assertGreater(len(m), 200)
        for old, new in {"302": "103", "420": "318", "379": "303", "498A": "85", "304B": "80"}.items():   # includes pairs whose headings differ
            self.assertEqual(m.get(old), new, f"IPC {old}")
        self.assertNotIn("124A", m)     # sedition was not re-enacted, so it must not be listed as replaced
        self.assertNotIn("377", m)

    def test_converter_crpc_uses_the_verified_table(self):
        m = {x["oldSection"]: x["newSection"] for x in self.c.get("/api/tools/code-converter?pair=crpc-bnss", headers=self.h).json()["results"]}
        self.assertEqual((m.get("438"), m.get("437"), m.get("482")), ("482", "480", "528"))

    def test_converter_rejects_unknown_pair(self):
        self.assertEqual(self.c.get("/api/tools/code-converter?pair=nope", headers=self.h).status_code, 400)

    def test_translate_validates_before_calling_the_model(self):
        post = lambda b: self.c.post("/api/tools/translate", json=b, headers=self.h)
        self.assertEqual(post({"text": "", "sourceLang": "en", "targetLang": "hi"}).status_code, 400)
        self.assertEqual(post({"text": "x", "sourceLang": "en", "targetLang": "en"}).status_code, 400)
        self.assertEqual(post({"text": "x", "sourceLang": "en", "targetLang": "zz"}).status_code, 400)
        self.assertEqual(post({"text": "a" * 4001, "sourceLang": "en", "targetLang": "hi"}).status_code, 400)

    def test_ocr_reads_an_image_and_rejects_other_files(self):
        import shutil, subprocess
        if not (shutil.which("tesseract") and shutil.which("pdftoppm") and shutil.which("cupsfilter")):
            self.skipTest("tesseract, poppler or cupsfilter not installed")
        d = tempfile.mkdtemp()
        open(f"{d}/a.txt", "w").write("IN THE SUPREME COURT OF INDIA\n\nAppeal under Section 302 of the IPC\n")
        with open(f"{d}/a.pdf", "wb") as f:
            subprocess.run(["cupsfilter", f"{d}/a.txt"], stdout=f, stderr=subprocess.DEVNULL)
        subprocess.run(["pdftoppm", "-r", "100", "-png", "-f", "1", "-l", "1", f"{d}/a.pdf", f"{d}/p"], check=True)
        png = open(f"{d}/p-1.png", "rb").read()
        r = self.c.post("/api/tools/ocr", files={"file": ("order.png", png, "image/png")}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("SUPREME COURT", r.json()["plainText"].upper())
        self.assertTrue(r.json()["metadata"]["isScanned"])
        self.assertEqual(self.c.post("/api/tools/ocr", files={"file": ("x.docx", b"x", "application/octet-stream")}, headers=self.h).status_code, 422)
        self.assertEqual(self.c.post("/api/tools/ocr", files={"file": ("x.png", b"x", "image/png")}).status_code, 401)

    def test_translate_other_languages_are_refused_not_guessed(self):
        post = lambda b: self.c.post("/api/tools/translate", json=b, headers=self.h)
        for lang in ("mr", "ta", "te", "bn", "gu", "kn"):
            r = post({"text": "bail", "sourceLang": "en", "targetLang": lang})
            self.assertEqual(r.status_code, 400, lang)
            self.assertIn("English and Hindi", r.json()["error"])
        self.assertEqual(post({"text": "x", "sourceLang": "hi", "targetLang": "mr"}).status_code, 400)

    def test_public_tool_pages_go_home_but_tools_is_served(self):
        for p in ("/affidavit", "/rent-agreement", "/cause-list", "/formats"):
            self.assertEqual(self.c.get(p).status_code, 302, p)
        self.assertEqual(self.c.get("/tools").status_code, 200)        # the signed-in AI Tools page; the browser sends signed-out visitors home


if __name__ == "__main__":
    unittest.main()
