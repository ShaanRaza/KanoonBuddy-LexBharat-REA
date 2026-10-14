"""Editor document tests. Run:  LEXBHARAT_ENV=dev ./.venv/bin/python -m unittest tests.test_editor -v"""
import json, os, tempfile, unittest

_TMP = tempfile.mkdtemp(prefix="lexbharat-test-")
os.environ.update({"LEXBHARAT_ENV": "dev", "LEXBHARAT_SECRET": "x" * 48, "LEXBHARAT_DATA": _TMP,
                   "AUTH_DB": f"{_TMP}/auth.sqlite", "NYRA_DB": f"{_TMP}/nyra.sqlite", "EDITOR_DB": f"{_TMP}/editor.sqlite"})

from fastapi.testclient import TestClient  # noqa: E402
from server import auth  # noqa: E402
from server.main import app  # noqa: E402

PW = "correct horse battery staple"


def doc(text):
    return json.dumps({"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]})


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app); cls.c = cls.ctx.__enter__()
        auth.create_user("a@example.com", PW); auth.create_user("b@example.com", PW)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def setUp(self):
        auth.limiter.reset()

    def tok(self, email):
        return {"Authorization": "Bearer " + self.c.post("/api/auth/login", json={"email": email, "password": PW}).json()["data"]["token"]}

    def test_requires_login(self):
        self.assertEqual(self.c.get("/api/editor/documents").status_code, 401)
        self.assertEqual(self.c.post("/api/editor/documents", json={"content": doc("x")}).status_code, 401)

    def test_create_list_get_update_delete(self):
        h = self.tok("a@example.com")
        r = self.c.post("/api/editor/documents", json={"content": doc("Bail application, State v. Kumar")}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json(); self.assertEqual(d["title"], "Bail application, State v. Kumar")
        lst = self.c.get("/api/editor/documents", headers=h).json()["documents"]
        self.assertIn(d["id"], [x["id"] for x in lst])
        got = self.c.get(f"/api/editor/documents/{d['id']}", headers=h).json()
        self.assertEqual(json.loads(got["content"])["type"], "doc")
        r2 = self.c.post("/api/editor/documents", json={"id": d["id"], "content": doc("Renamed draft")}, headers=h).json()
        self.assertEqual((r2["id"], r2["title"]), (d["id"], "Renamed draft"))
        self.assertEqual(len(self.c.get("/api/editor/documents", headers=h).json()["documents"]), len(lst))  # updated, not duplicated
        self.assertEqual(self.c.delete(f"/api/editor/documents/{d['id']}", headers=h).status_code, 200)
        self.assertEqual(self.c.get(f"/api/editor/documents/{d['id']}", headers=h).status_code, 404)

    def test_documents_are_private(self):
        a, b = self.tok("a@example.com"), self.tok("b@example.com")
        d = self.c.post("/api/editor/documents", json={"content": doc("A's private notes")}, headers=a).json()
        self.assertEqual(self.c.get(f"/api/editor/documents/{d['id']}", headers=b).status_code, 404)
        self.assertNotIn(d["id"], [x["id"] for x in self.c.get("/api/editor/documents", headers=b).json()["documents"]])
        self.assertEqual(self.c.post("/api/editor/documents", json={"id": d["id"], "content": doc("overwritten")}, headers=b).status_code, 404)
        self.c.delete(f"/api/editor/documents/{d['id']}", headers=b)
        self.assertEqual(json.loads(self.c.get(f"/api/editor/documents/{d['id']}", headers=a).json()["content"])["content"][0]["content"][0]["text"], "A's private notes")

    def test_rejects_bad_input(self):
        h = self.tok("a@example.com")
        self.assertEqual(self.c.post("/api/editor/documents", json={"content": "not json"}, headers=h).status_code, 400)
        self.assertEqual(self.c.post("/api/editor/documents", json={"content": 5}, headers=h).status_code, 400)
        self.assertEqual(self.c.post("/api/editor/documents", json={"content": doc("x" * 900_000)}, headers=h).status_code, 413)

    def test_untitled_and_download_not_pretended(self):
        h = self.tok("a@example.com")
        d = self.c.post("/api/editor/documents", json={"content": json.dumps({"type": "doc", "content": []})}, headers=h).json()
        self.assertEqual(d["title"], "Untitled document")
        self.assertEqual(self.c.get(f"/api/editor/documents/{d['id']}/download?format=pdf", headers=h).status_code, 501)


if __name__ == "__main__":
    unittest.main()
