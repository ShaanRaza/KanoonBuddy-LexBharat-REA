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

    def test_public_tool_pages_go_home_but_tools_is_served(self):
        for p in ("/affidavit", "/rent-agreement", "/cause-list", "/formats"):
            self.assertEqual(self.c.get(p).status_code, 302, p)
        self.assertEqual(self.c.get("/tools").status_code, 200)        # the signed-in AI Tools page; the browser sends signed-out visitors home


if __name__ == "__main__":
    unittest.main()
