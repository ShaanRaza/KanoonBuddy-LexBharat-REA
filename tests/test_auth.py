"""Authentication tests. Run:  LEXBHARAT_ENV=dev ./.venv/bin/python -m unittest tests.test_auth -v

Uses a throwaway data directory, so it never touches real accounts or chats. It needs the corpus
mounted only because the app loads it at startup.
"""
import base64
import json
import os
import tempfile
import time
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="lexbharat-test-")
os.environ.update({
    "LEXBHARAT_ENV": "dev", "LEXBHARAT_SECRET": "x" * 48, "LEXBHARAT_DATA": _TMP,
    "AUTH_DB": f"{_TMP}/auth.sqlite", "NYRA_DB": f"{_TMP}/nyra.sqlite",
})

from fastapi.testclient import TestClient  # noqa: E402

from server import auth  # noqa: E402
from server.main import app  # noqa: E402

PW = "correct horse battery staple"   # test-only value, used only against the throwaway database above
PW2 = "a completely different phrase"


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.c = cls.ctx.__enter__()
        auth.create_user("alice@example.com", PW, "Alice")
        auth.create_user("bob@example.com", PW, "Bob")

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def setUp(self):
        auth.limiter.reset()
        conn = auth._db(); conn.execute("DELETE FROM attempts"); conn.commit(); conn.close()

    def login(self, email="alice@example.com", pw=PW):
        return self.c.post("/api/auth/login", json={"email": email, "password": pw})

    def token(self, email="alice@example.com"):
        r = self.login(email)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["token"]

    @staticmethod
    def h(tok):
        return {"Authorization": f"Bearer {tok}"}

    # ------------------------------------------------------------------ access control
    def test_api_requires_a_token(self):
        for path in ("/api/me", "/api/cases", "/api/agent/sessions", "/api/research/citation-graph/lookup?q=maneka",
                     "/api/health/status", "/api/anything-else"):
            r = self.c.get(path)
            self.assertEqual(r.status_code, 401, path)
            self.assertEqual(r.json()["error"], "Authentication required")
        self.assertEqual(self.c.post("/api/agent/chat", json={"message": "hi"}).status_code, 401)

    def test_public_endpoints_stay_public(self):
        self.assertEqual(self.c.get("/api/health").json(), {"ok": True})   # reveals nothing else
        self.assertEqual(self.c.get("/api/statutes/search?q=IPC 302").status_code, 200)
        self.assertEqual(self.c.get("/api/statutes/BNS/103").status_code, 200)
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/signin").status_code, 200)

    def test_no_token_is_handed_out_by_unknown_auth_urls(self):
        tok = self.token()
        for path in ("/api/auth/google", "/api/auth/set-role", "/api/auth/anything"):
            anon = self.c.post(path, json={"credential": "x"})
            self.assertEqual(anon.status_code, 401, path)                       # turned away before any route runs
            self.assertNotIn("token", anon.text.lower().replace("invalid token", ""), path)
            self.assertEqual(self.c.post(path, json={"credential": "x"}, headers=self.h(tok)).status_code, 404, path)

    def test_api_docs_are_disabled(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            self.assertNotIn("openapi", self.c.get(path).text.lower()[:400], path)

    # ------------------------------------------------------------------ login
    def test_login_success_shape_matches_front_end(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["success"])
        user = d["data"]["user"]
        self.assertEqual(user["email"], "alice@example.com")
        self.assertTrue(user["emailVerified"] and user["onboardingCompletedAt"] and user["role"])
        self.assertNotIn("pw_hash", json.dumps(d))
        claims = json.loads(b64d(d["data"]["token"].split(".")[1]))
        self.assertIsInstance(claims["iat"], int)   # the front end decodes iat itself
        me = self.c.get("/api/me", headers=self.h(d["data"]["token"]))
        self.assertEqual(me.json()["email"], "alice@example.com")

    def test_wrong_password_and_unknown_email_look_identical(self):
        a = self.login("alice@example.com", "wrong password here")
        b = self.login("nobody@example.com", "wrong password here")
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))
        self.assertEqual(a.status_code, 401)

    def test_email_is_case_insensitive(self):
        self.assertEqual(self.login("ALICE@Example.com").status_code, 200)

    def test_lockout_after_repeated_failures_and_same_for_unknown_email(self):
        for email in ("alice@example.com", "ghost@example.com"):
            codes = []
            for _ in range(7):
                auth.limiter.reset()   # isolate the per-account lockout from the per-IP limit
                codes.append(self.login(email, "bad password value").status_code)
            self.assertEqual(codes[:5], [401] * 5, email)
            self.assertEqual(codes[5:], [429, 429], email)
        auth.limiter.reset()
        self.assertEqual(self.login("alice@example.com").status_code, 429)   # even the right password is refused while locked

    def test_per_ip_login_rate_limit(self):
        codes = [self.login(f"user{i}@example.com", "bad password value").status_code for i in range(14)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 401)

    def test_malformed_login_bodies(self):
        self.assertEqual(self.c.post("/api/auth/login", content=b"not json").status_code, 400)
        self.assertEqual(self.c.post("/api/auth/login", json=["a"]).status_code, 400)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "a@b.co"}).status_code, 401)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "x" * 500, "password": "y" * 500}).status_code, 401)

    # ------------------------------------------------------------------ token integrity
    def test_tampered_and_forged_tokens_are_rejected(self):
        tok = self.token()
        head, body, sig = tok.split(".")
        claims = json.loads(b64d(body)); claims["sub"] = "someone-else"
        forged_body = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        none_head = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
        for bad in (f"{head}.{forged_body}.{sig}", f"{none_head}.{body}.", f"{head}.{body}.AAAA", "garbage", ""):
            self.assertEqual(self.c.get("/api/me", headers=self.h(bad)).status_code, 401, bad[:30])

    def test_token_signed_with_another_secret_is_rejected(self):
        with mock.patch.object(auth, "_secret", b"y" * 48):
            foreign = auth.sign_token("whatever", 0)
        self.assertEqual(self.c.get("/api/me", headers=self.h(foreign)).status_code, 401)

    def test_expired_token_rejected_but_refreshable_in_grace(self):
        conn = auth._db(); uid = conn.execute("SELECT id, token_version FROM users WHERE email='alice@example.com'").fetchone(); conn.close()
        old = auth.sign_token(uid["id"], uid["token_version"], now=time.time() - 9 * 3600)   # ttl is 8h, so 1h expired
        self.assertEqual(self.c.get("/api/me", headers=self.h(old)).status_code, 401)
        r = self.c.post("/api/auth/refresh", headers=self.h(old))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get("/api/me", headers=self.h(r.json()["data"]["token"])).status_code, 200)

    def test_refresh_beyond_grace_or_session_cap_is_refused(self):
        conn = auth._db(); uid = conn.execute("SELECT id, token_version FROM users WHERE email='alice@example.com'").fetchone(); conn.close()
        stale = auth.sign_token(uid["id"], uid["token_version"], now=time.time() - 9 * 86400)
        self.assertEqual(self.c.post("/api/auth/refresh", headers=self.h(stale)).status_code, 401)
        capped = auth.sign_token(uid["id"], uid["token_version"], sid=time.time() - 40 * 86400)
        self.assertEqual(self.c.post("/api/auth/refresh", headers=self.h(capped)).status_code, 401)

    def test_refresh_returns_front_end_shape_and_retires_old_token(self):
        tok = self.token()
        r = self.c.post("/api/auth/refresh", headers=self.h(tok))
        d = r.json()["data"]
        self.assertTrue(d["token"] and d["user"]["email"] == "alice@example.com")
        self.assertEqual(self.c.get("/api/me", headers=self.h(d["token"])).status_code, 200)
        # in-flight requests still carrying the old token keep working during the short overlap ...
        self.assertEqual(self.c.get("/api/me", headers=self.h(tok)).status_code, 200)
        # ... and the old token is retired once it ends
        conn = auth._db(); conn.execute("UPDATE revoked SET at = 0"); conn.commit(); conn.close()
        self.assertEqual(self.c.get("/api/me", headers=self.h(tok)).status_code, 401)
        self.assertEqual(self.c.get("/api/me", headers=self.h(d["token"])).status_code, 200)

    def test_logout_revokes_the_token(self):
        tok = self.token()
        self.assertEqual(self.c.post("/api/auth/logout", headers=self.h(tok)).status_code, 200)
        self.assertEqual(self.c.get("/api/me", headers=self.h(tok)).status_code, 401)

    def test_changing_password_signs_out_other_sessions(self):
        auth.create_user("carol@example.com", PW, "Carol")
        t1, t2 = self.token("carol@example.com"), self.token("carol@example.com")
        r = self.c.post("/api/auth/change-password", headers=self.h(t1), json={"currentPassword": PW, "newPassword": PW2})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.c.get("/api/me", headers=self.h(t2)).status_code, 401)
        self.assertEqual(self.login("carol@example.com", PW).status_code, 401)
        self.assertEqual(self.login("carol@example.com", PW2).status_code, 200)

    def test_change_password_checks_current_and_policy(self):
        tok = self.token("bob@example.com")
        bad = self.c.post("/api/auth/change-password", headers=self.h(tok), json={"currentPassword": "nope nope nope", "newPassword": PW2})
        self.assertEqual(bad.status_code, 403)
        weak = self.c.post("/api/auth/change-password", headers=self.h(tok), json={"currentPassword": PW, "newPassword": "short"})
        self.assertEqual(weak.status_code, 400)

    def test_disabled_account_is_locked_out_immediately(self):
        auth.create_user("dave@example.com", PW, "Dave")
        tok = self.token("dave@example.com")
        conn = auth._db(); conn.execute("UPDATE users SET disabled=1, token_version=token_version+1 WHERE email='dave@example.com'"); conn.commit(); conn.close()
        self.assertEqual(self.c.get("/api/me", headers=self.h(tok)).status_code, 401)
        self.assertEqual(self.login("dave@example.com").status_code, 401)

    def test_client_supplied_user_id_header_is_ignored(self):
        tok = self.token("alice@example.com")
        r = self.c.get("/api/me", headers={**self.h(tok), "X-User-Id": "someone-else"})
        self.assertEqual(r.json()["email"], "alice@example.com")

    # ------------------------------------------------------------------ passwords
    def test_password_policy(self):
        for pw, email in (("short", "x@example.com"), ("aaaaaaaaaaaa", "x@example.com"), ("password", "x@example.com"),
                          ("a" * 300, "x@example.com"), ("my-alice-passphrase", "alice@example.com")):
            self.assertIsNotNone(auth.check_password_policy(pw, email), pw[:20])
        self.assertIsNone(auth.check_password_policy(PW, "alice@example.com"))
        with self.assertRaises(ValueError):
            auth.create_user("alice@example.com", PW)   # duplicate
        with self.assertRaises(ValueError):
            auth.create_user("not-an-email", PW)

    def test_passwords_are_hashed_with_random_salt(self):
        h1, h2 = auth.hash_password(PW), auth.hash_password(PW)
        self.assertNotEqual(h1, h2)
        self.assertTrue(h1.startswith("scrypt$") and PW not in h1)
        self.assertTrue(auth.verify_password(PW, h1) and not auth.verify_password(PW2, h1))

    # ------------------------------------------------------------------ headers & limits
    def test_security_headers(self):
        r = self.c.get("/api/health")
        for k in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy", "cache-control"):
            self.assertIn(k, r.headers, k)
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors", r.headers["content-security-policy"])

    def test_oversized_request_is_rejected(self):
        r = self.c.post("/api/auth/login", content=b"{" + b" " * 1_100_000 + b"}", headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_public_statutes_are_rate_limited_per_ip(self):
        codes = [self.c.get("/api/statutes/search?q=bail").status_code for _ in range(125)]
        self.assertEqual(codes[0], 200)
        self.assertIn(429, codes)

    # ------------------------------------------------------------------ KanoonBuddy isolation and limits
    def _chat(self, tok, message, session=None):
        body = {"message": message}
        if session:
            body["sessionId"] = session
        events = []
        with self.c.stream("POST", "/api/agent/chat", json=body, headers=self.h(tok)) as r:
            name = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: ") and name:
                    events.append((name, json.loads(line[6:])))
        return events

    def test_nyra_chats_are_private_to_their_owner(self):
        a, b = self.token("alice@example.com"), self.token("bob@example.com")
        # a message with no matching sources gets a fixed reply without needing the model
        ev = self._chat(a, "zzqx flurbo wibble gronk", session="alice-private-1")
        self.assertIn("done", [e[0] for e in ev], ev)
        mine = self.c.get("/api/agent/sessions", headers=self.h(a)).json()["sessions"]
        theirs = self.c.get("/api/agent/sessions", headers=self.h(b)).json()["sessions"]
        self.assertIn("alice-private-1", [s["sessionId"] for s in mine])
        self.assertNotIn("alice-private-1", [s["sessionId"] for s in theirs])
        self.assertEqual(self.c.get("/api/agent/history?sessionId=alice-private-1", headers=self.h(b)).json()["messages"], [])
        self.assertTrue(self.c.get("/api/agent/history?sessionId=alice-private-1", headers=self.h(a)).json()["messages"])
        # bob cannot write into, or delete, alice's conversation
        stolen = self._chat(b, "zzqx flurbo wibble gronk", session="alice-private-1")
        self.assertEqual(stolen[-1][0], "error")
        self.c.delete("/api/agent/history?sessionId=alice-private-1", headers=self.h(b))
        self.assertTrue(self.c.get("/api/agent/history?sessionId=alice-private-1", headers=self.h(a)).json()["messages"])

    def test_nyra_input_limits_and_rate_limit(self):
        tok = self.token("alice@example.com")
        long = self._chat(tok, "x" * 4001)
        self.assertEqual(long[-1][1]["code"], "too_long")
        self.assertEqual(self.c.post("/api/agent/chat", json={"message": "  "}, headers=self.h(tok)).status_code, 400)
        auth.limiter.reset()
        results = [self._chat(tok, f"zzqx flurbo wibble {i}")[-1][0] for i in range(14)]
        errs = [r for r in results if r == "error"]
        self.assertTrue(errs, "chat should be rate limited after 12 messages a minute")


class ConfigTests(unittest.TestCase):
    def test_production_refuses_to_start_without_a_secret(self):
        with mock.patch.dict(os.environ, {"LEXBHARAT_ENV": "production"}, clear=False):
            os.environ.pop("LEXBHARAT_SECRET", None)
            with self.assertRaises(RuntimeError) as cm:
                auth.load_secret()
            self.assertIn("LEXBHARAT_SECRET", str(cm.exception))

    def test_short_secret_is_refused(self):
        with mock.patch.dict(os.environ, {"LEXBHARAT_SECRET": "too short"}):
            with self.assertRaises(RuntimeError):
                auth.load_secret()

    def test_production_is_the_default_environment(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LEXBHARAT_ENV", None)
            self.assertEqual(auth.env(), "production")


if __name__ == "__main__":
    unittest.main()
