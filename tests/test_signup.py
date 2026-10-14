"""Self-service sign-up tests. Run:  LEXBHARAT_ENV=dev ./.venv/bin/python -m unittest tests.test_signup -v

Email is captured to a throwaway outbox folder (dev mode), so no mail account is needed.
"""
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="lexbharat-test-")
os.environ.update({
    "LEXBHARAT_ENV": "dev", "LEXBHARAT_SECRET": "x" * 48, "LEXBHARAT_DATA": _TMP, "BASE_URL": "http://testserver",
    "AUTH_DB": f"{_TMP}/auth.sqlite", "NYRA_DB": f"{_TMP}/nyra.sqlite", "EDITOR_DB": f"{_TMP}/editor.sqlite",
})
os.environ.pop("SMTP_HOST", None)

from fastapi.testclient import TestClient  # noqa: E402

from server import auth, editor, mailer, nyra  # noqa: E402
from server.main import app  # noqa: E402

PW = "correct horse battery staple"
PW2 = "another entirely different phrase"


def mails_to(email):
    d = mailer.outbox_dir()
    return sorted(p for p in d.glob("*.txt") if f"To: {email}\n" in p.read_text()) if d.exists() else []


def wait_mail(email, n=1, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        found = mails_to(email)
        if len(found) >= n:
            return found
        time.sleep(0.05)
    return mails_to(email)


def link_token(path):
    m = re.search(r"token=([A-Za-z0-9_-]+)", path.read_text())
    assert m, path.read_text()
    return m.group(1)


class SignupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.c = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def setUp(self):
        auth.limiter.reset()
        conn = auth._db(); conn.execute("DELETE FROM attempts"); conn.execute("DELETE FROM mail_log"); conn.commit(); conn.close()

    def register(self, email, password=PW, name="Test User", terms=True, keep_limit=False):
        if not keep_limit:
            auth.limiter.reset()   # most tests are not about the per-IP limit
        return self.c.post("/api/auth/register", json={"email": email, "password": password, "name": name, "acceptTerms": terms})

    def signed_up(self, email):
        """Register, confirm via the emailed link, return a bearer header."""
        self.assertEqual(self.register(email).status_code, 200)
        self.assertEqual(self.c.post("/api/auth/verify-email", json={"token": link_token(wait_mail(email)[0])}).status_code, 200)
        r = self.c.post("/api/auth/login", json={"email": email, "password": PW})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": "Bearer " + r.json()["data"]["token"]}

    # ------------------------------------------------------------------ validation and consent
    def test_config_reports_signup_open(self):
        d = self.c.get("/api/auth/config").json()
        self.assertTrue(d["signupEnabled"])

    def test_rejects_bad_input(self):
        self.assertEqual(self.register("v1@example.com", terms=False).status_code, 400)
        self.assertEqual(self.register("v2@example.com", password="short").status_code, 400)
        self.assertEqual(self.register("not-an-email").status_code, 400)
        self.assertEqual(self.register("someone@mailinator.com").status_code, 400)
        self.assertEqual(self.register("tester@example.com", password="my-tester-passphrase", name="x").status_code, 400)  # contains the email name
        self.assertEqual(self.c.post("/api/auth/register", content=b"junk").status_code, 400)
        auth.limiter.reset()
        self.assertEqual(self.c.post("/api/auth/register", json={"email": "v4@example.com", "password": PW, "acceptTerms": "true"}).status_code, 400)  # must be the boolean true
        self.assertFalse(mails_to("v1@example.com") or mails_to("v2@example.com"))

    def test_consent_is_recorded_with_version(self):
        self.register("consent@example.com")
        conn = auth._db(); r = conn.execute("SELECT * FROM users WHERE email='consent@example.com'").fetchone(); conn.close()
        self.assertEqual(r["terms_version"], auth.TERMS_VERSION)
        self.assertLess(abs(r["terms_accepted_at"] - time.time()), 10)
        self.assertEqual(r["email_verified"], 0)

    def test_name_is_sanitised(self):
        self.register("name@example.com", name="<script>alert(1)</script>" + "x" * 200)
        conn = auth._db(); r = conn.execute("SELECT name FROM users WHERE email='name@example.com'").fetchone(); conn.close()
        self.assertNotIn("<", r["name"]); self.assertLessEqual(len(r["name"]), 80)

    # ------------------------------------------------------------------ email confirmation
    def test_cannot_sign_in_until_email_is_confirmed(self):
        self.register("unconfirmed@example.com")
        r = self.c.post("/api/auth/login", json={"email": "unconfirmed@example.com", "password": PW})
        self.assertEqual((r.status_code, r.json()["code"]), (403, "email_not_verified"))
        wrong = self.c.post("/api/auth/login", json={"email": "unconfirmed@example.com", "password": "wrong password here"})
        self.assertEqual(wrong.status_code, 401)   # a wrong password reveals nothing about the account state

    def test_register_response_is_identical_for_new_unverified_and_verified_emails(self):
        new = self.register("same1@example.com")
        again = self.register("same1@example.com")                       # exists, unverified
        self.signed_up("same2@example.com")
        verified = self.register("same2@example.com")                    # exists, verified
        self.assertEqual({new.status_code, again.status_code, verified.status_code}, {200})
        self.assertEqual(new.json(), again.json()); self.assertEqual(new.json(), verified.json())

    def test_existing_verified_owner_is_told_but_requester_is_not(self):
        self.signed_up("owner@example.com")
        self.register("owner@example.com")
        mails = wait_mail("owner@example.com", 2)
        self.assertTrue(any("already have an account" in m.read_text() for m in mails))

    def test_confirmation_link_works_once(self):
        self.register("once@example.com")
        tok = link_token(wait_mail("once@example.com")[0])
        self.assertEqual(self.c.post("/api/auth/verify-email", json={"token": tok}).status_code, 200)
        again = self.c.post("/api/auth/verify-email", json={"token": tok})
        self.assertEqual((again.status_code, again.json()["code"]), (400, "bad_token"))

    def test_garbage_and_wrong_purpose_tokens_are_rejected(self):
        self.signed_up("purpose@example.com")
        self.c.post("/api/auth/forgot-password", json={"email": "purpose@example.com"})
        reset_tok = link_token(wait_mail("purpose@example.com", 2)[-1])
        self.assertEqual(self.c.post("/api/auth/verify-email", json={"token": reset_tok}).status_code, 400)   # a reset link cannot confirm email
        for bad in ("", "abc", "x" * 500, "../../etc/passwd"):
            self.assertEqual(self.c.post("/api/auth/verify-email", json={"token": bad}).status_code, 400)

    def test_expired_link_is_rejected(self):
        self.register("expired@example.com")
        tok = link_token(wait_mail("expired@example.com")[0])
        conn = auth._db(); conn.execute("UPDATE tokens SET expires=?", (time.time() - 5,)); conn.commit(); conn.close()
        self.assertEqual(self.c.post("/api/auth/verify-email", json={"token": tok}).status_code, 400)

    def test_tokens_are_stored_hashed(self):
        self.register("hashed@example.com")
        tok = link_token(wait_mail("hashed@example.com")[0])
        conn = auth._db(); rows = [r["hash"] for r in conn.execute("SELECT hash FROM tokens")]; conn.close()
        self.assertNotIn(tok, rows); self.assertIn(auth._hash_token(tok), rows)

    def test_resend_is_generic_and_capped(self):
        self.register("resend@example.com")
        for _ in range(6):
            r = self.c.post("/api/auth/resend-verification", json={"email": "resend@example.com"})
            self.assertEqual(r.status_code, 200)
        time.sleep(0.3)
        self.assertEqual(len(mails_to("resend@example.com")), 3)         # 1 at sign-up + 2 more, then the per-address cap
        ghost = self.c.post("/api/auth/resend-verification", json={"email": "ghost@example.com"})
        self.assertEqual(ghost.json(), self.c.post("/api/auth/resend-verification", json={"email": "resend@example.com"}).json())
        self.assertEqual(mails_to("ghost@example.com"), [])

    def test_signup_rate_limit_per_ip(self):
        codes = [self.register(f"flood{i}@example.com", keep_limit=True).status_code for i in range(8)]
        self.assertEqual(codes[:5], [200] * 5); self.assertIn(429, codes[5:])

    # ------------------------------------------------------------------ password reset
    def test_forgot_password_is_generic(self):
        self.signed_up("known@example.com")
        a = self.c.post("/api/auth/forgot-password", json={"email": "known@example.com"})
        b = self.c.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))
        self.assertEqual(len(wait_mail("known@example.com", 2)), 2)
        self.assertEqual(mails_to("nobody@example.com"), [])

    def test_reset_changes_password_signs_out_everywhere_and_is_single_use(self):
        h = self.signed_up("reset@example.com")
        self.c.post("/api/auth/forgot-password", json={"email": "reset@example.com"})
        tok = link_token(wait_mail("reset@example.com", 2)[-1])
        weak = self.c.post("/api/auth/reset-password", json={"token": tok, "newPassword": "short"})
        self.assertEqual(weak.status_code, 400)                          # a weak password does not spend the link
        ok = self.c.post("/api/auth/reset-password", json={"token": tok, "newPassword": PW2})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(self.c.get("/api/me", headers=h).status_code, 401)            # the old session is gone
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "reset@example.com", "password": PW}).status_code, 401)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "reset@example.com", "password": PW2}).status_code, 200)
        self.assertEqual(self.c.post("/api/auth/reset-password", json={"token": tok, "newPassword": PW}).status_code, 400)   # single use

    def test_reset_also_lifts_a_lockout(self):
        self.signed_up("locked@example.com")
        for _ in range(6):
            auth.limiter.reset(); self.c.post("/api/auth/login", json={"email": "locked@example.com", "password": "bad password value"})
        auth.limiter.reset()
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "locked@example.com", "password": PW}).status_code, 429)
        self.c.post("/api/auth/forgot-password", json={"email": "locked@example.com"})
        tok = link_token(wait_mail("locked@example.com", 2)[-1])
        self.c.post("/api/auth/reset-password", json={"token": tok, "newPassword": PW2})
        auth.limiter.reset()
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "locked@example.com", "password": PW2}).status_code, 200)

    # ------------------------------------------------------------------ when email is not set up
    def test_signup_switches_off_without_email_in_production(self):
        env = {k: v for k, v in os.environ.items() if k != "SMTP_HOST"}
        env["LEXBHARAT_ENV"] = "production"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(auth.signup_enabled())
            r = self.register("nomail@example.com")
            self.assertEqual((r.status_code, r.json()["code"]), (503, "signup_disabled"))
            self.assertFalse(self.c.get("/api/auth/config").json()["signupEnabled"])
        self.assertEqual(mails_to("nomail@example.com"), [])

    # ------------------------------------------------------------------ daily allowance
    def _chat(self, h, msg):
        out = []
        with self.c.stream("POST", "/api/agent/chat", json={"message": msg}, headers=h) as r:
            name = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: ") and name:
                    out.append((name, json.loads(line[6:])))
        return out

    def test_daily_chat_allowance(self):
        h = self.signed_up("quota@example.com")
        with mock.patch.object(nyra, "FREE_DAILY_CHAT", 2):
            res = []
            for i in range(4):
                auth.limiter.reset()
                res.append(self._chat(h, f"zzqx flurbo wibble {i}")[-1])
        self.assertEqual([r[0] for r in res], ["done", "done", "error", "error"])
        self.assertEqual(res[2][1]["code"], "daily_limit")

    def test_site_wide_cap(self):
        h = self.signed_up("cap@example.com")
        with mock.patch.object(nyra, "GLOBAL_DAILY_CHAT", 0.5), mock.patch.object(nyra, "FREE_DAILY_CHAT", 50):
            self._chat(h, "zzqx first one")   # uses the allowance
            auth.limiter.reset()
            last = self._chat(h, "zzqx second one")[-1]
        self.assertEqual(last[1].get("code"), "site_capacity")

    # ------------------------------------------------------------------ privacy rights
    def test_export_profile_and_scheduled_deletion(self):
        h = self.signed_up("privacy@example.com")
        self._chat(h, "zzqx flurbo wibble gronk")
        self.c.post("/api/editor/documents", json={"content": json.dumps({"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "My draft"}]}]})}, headers=h)
        exp = self.c.get("/api/gdpr/export", headers=h).json()["data"]
        self.assertEqual(exp["account"]["email"], "privacy@example.com")
        self.assertNotIn("pw_hash", json.dumps(exp))
        self.assertTrue(exp["chatMessages"] and exp["editorDocuments"])
        prof = self.c.put("/api/gdpr/profile", json={"preferredLanguage": "hi", "isAdmin": True, "homeCourtId": "x" * 200}, headers=h).json()["data"]
        self.assertEqual(prof["preferredLanguage"], "hi"); self.assertNotIn("isAdmin", prof); self.assertEqual(len(prof["homeCourtId"]), 64)
        self.assertEqual(self.c.get("/api/me", headers=h).json()["preferredLanguage"], "hi")
        st = self.c.post("/api/gdpr/delete-account", headers=h).json()["data"]
        self.assertTrue(st["isScheduled"]); self.assertGreaterEqual(st["daysRemaining"], 29)
        self.assertTrue(self.c.get("/api/gdpr/deletion-status", headers=h).json()["data"]["isScheduled"])
        self.c.post("/api/gdpr/cancel-deletion", headers=h)
        self.assertFalse(self.c.get("/api/gdpr/deletion-status", headers=h).json()["data"]["isScheduled"])

    def test_deletion_after_grace_period_erases_everything(self):
        h = self.signed_up("erase@example.com")
        uid = self.c.get("/api/me", headers=h).json()["id"]
        self._chat(h, "zzqx flurbo wibble gronk")
        self.c.post("/api/editor/documents", json={"content": json.dumps({"type": "doc", "content": []})}, headers=h)
        self.c.post("/api/gdpr/delete-account", headers=h)
        self.assertNotIn(uid, auth.due_for_deletion())                      # still inside the grace period
        conn = auth._db(); conn.execute("UPDATE users SET deletion_scheduled_at=? WHERE id=?", (time.time() - 1, uid)); conn.commit(); conn.close()
        self.assertIn(uid, auth.due_for_deletion())
        for u in auth.due_for_deletion():                                   # what the daily housekeeping job does
            nyra.delete_user(u); editor.delete_user(u); auth.erase_user(u)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "erase@example.com", "password": PW}).status_code, 401)
        self.assertEqual(nyra.export_user(uid), {"chatSessions": [], "chatMessages": []})
        self.assertEqual(editor.export_user(uid), [])
        conn = auth._db(); left = conn.execute("SELECT count(*) FROM tokens WHERE user_id=?", (uid,)).fetchone()[0]; conn.close()
        self.assertEqual(left, 0)

    def test_chat_retention_removes_old_messages(self):
        h = self.signed_up("retain@example.com")
        uid = self.c.get("/api/me", headers=h).json()["id"]
        self._chat(h, "zzqx flurbo wibble gronk")
        c = nyra._conn(); c.execute("UPDATE messages SET created_at='2020-01-01T00:00:00.000Z' WHERE user_id=?", (uid,)); c.commit(); c.close()
        self.assertGreater(nyra.purge_old(180), 0)
        self.assertEqual(nyra.export_user(uid)["chatMessages"], [])

    # ------------------------------------------------------------------ pages
    def test_account_pages_are_served(self):
        for path in ("/signin", "/signup", "/verify", "/forgot-password", "/reset-password", "/auth.css", "/auth.js"):
            self.assertEqual(self.c.get(path).status_code, 200, path)
        self.assertIn("Create", self.c.get("/signup").text)

    def test_existing_admin_created_accounts_stay_usable(self):
        auth.create_user("admin-made@example.com", PW, "Admin Made")
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "admin-made@example.com", "password": PW}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
