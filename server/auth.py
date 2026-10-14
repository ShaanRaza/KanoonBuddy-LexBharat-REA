"""Authentication for LexBharat: invite-only email + password, signed bearer tokens.

Design (all standard library, no new dependencies)
  * Accounts are created by an administrator with `python -m server.manage_users`. There is no
    public sign-up.
  * Passwords are stored as scrypt hashes (per-user random salt). Verification is constant time,
    and an unknown email costs the same as a wrong password, so responses do not reveal which
    emails exist.
  * Sessions are HS256 JWTs sent as `Authorization: Bearer`. The front end keeps them in
    localStorage, so cookies are never used for auth and CSRF does not apply.
  * Every /api route requires a valid token except a short public list (see PUBLIC_*).
  * Tokens can be revoked: logout denylists the token id, and changing a password or disabling an
    account bumps the user's `token_version`, which invalidates every token already issued.
  * Failed logins are throttled per email (persisted, same behaviour for unknown emails) and per IP.

Environment
  LEXBHARAT_ENV            production (default) or dev. production demands a secret and HTTPS-grade settings
  LEXBHARAT_SECRET         32+ chars, signs tokens. Required in production. In dev one is auto-generated
  TOKEN_TTL_MINUTES        access token lifetime, default 480
  REFRESH_GRACE_DAYS       an expired token may still be refreshed for this long, default 7
  SESSION_MAX_DAYS         hard limit on a login's total age, however often it is refreshed, default 30
  TRUST_PROXY              set to 1 only behind a proxy that overwrites X-Forwarded-For
  AUTH_DB                  sqlite path, default data/auth.sqlite
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Request

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("LEXBHARAT_DATA", ROOT / "data"))

# ----------------------------------------------------------------------------- configuration
def env() -> str:
    return os.environ.get("LEXBHARAT_ENV", "production").lower()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


TOKEN_TTL = lambda: _int("TOKEN_TTL_MINUTES", 480) * 60          # noqa: E731 (read at call time for tests)
REFRESH_GRACE = lambda: _int("REFRESH_GRACE_DAYS", 7) * 86400    # noqa: E731
SESSION_MAX = lambda: _int("SESSION_MAX_DAYS", 30) * 86400       # noqa: E731
MAX_FAILS, LOCK_SECONDS, FAIL_WINDOW = 5, 15 * 60, 15 * 60
ROTATE_OVERLAP = 60  # seconds an old token keeps working after a refresh (parallel requests, second tab)

# Reachable without a token. Everything else under /api needs one.
PUBLIC_EXACT = {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/refresh",
                "/api/config/features", "/api/track", "/api/subscription/plans"}
PUBLIC_GET_PREFIX = ("/api/statutes",)  # open-corpus legal text; IP rate limited

_secret: bytes | None = None


def load_secret() -> bytes:
    s = os.environ.get("LEXBHARAT_SECRET")
    if s:
        if len(s) < 32:
            raise RuntimeError("LEXBHARAT_SECRET must be at least 32 characters")
        return s.encode()
    if env() == "production":
        raise RuntimeError(
            "LEXBHARAT_SECRET is required (LEXBHARAT_ENV defaults to production). Generate one with:\n"
            "  python3 -c 'import secrets; print(secrets.token_urlsafe(48))'\n"
            "For local development set LEXBHARAT_ENV=dev instead.")
    f = DATA / ".secret"  # dev only: a stable generated secret so dev logins survive restarts
    if not f.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_urlsafe(48))
        os.chmod(f, 0o600)
    return f.read_text().strip().encode()


def init() -> None:
    """Called once at startup: fails fast on bad configuration."""
    global _secret
    _secret = load_secret()
    _db().close()


def secret() -> bytes:
    global _secret
    if _secret is None:
        _secret = load_secret()
    return _secret


# ----------------------------------------------------------------------------- storage
_lock = threading.Lock()


def db_path() -> Path:
    return Path(os.environ.get("AUTH_DB", DATA / "auth.sqlite"))


def _db() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(
        """CREATE TABLE IF NOT EXISTS users(
               id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, pw_hash TEXT NOT NULL,
               token_version INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0,
               created_at REAL, last_login REAL);
           CREATE TABLE IF NOT EXISTS revoked(jti TEXT PRIMARY KEY, exp REAL NOT NULL, at REAL NOT NULL DEFAULT 0);
           CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY, fails INTEGER NOT NULL DEFAULT 0,
               first_at REAL, locked_until REAL NOT NULL DEFAULT 0);"""
    )
    if "at" not in [r["name"] for r in c.execute("PRAGMA table_info(revoked)")]:  # migrate older databases
        c.execute("ALTER TABLE revoked ADD COLUMN at REAL NOT NULL DEFAULT 0")
        c.commit()
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return c


# ----------------------------------------------------------------------------- passwords
_N, _R, _P = 2 ** 16, 8, 1
COMMON = {"password", "123456789012", "qwertyuiopas", "letmein12345", "iloveyou1234", "administrator"}


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=256 * 1024 * 1024, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                              maxmem=256 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


_DUMMY = None


def _dummy_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(16))
    return _DUMMY


def check_password_policy(pw: str, email: str = "") -> str | None:
    """Length over composition rules (NIST 800-63B). Returns an error message or None."""
    if len(pw) < 12:
        return "Password must be at least 12 characters."
    if len(pw) > 256:
        return "Password is too long."
    if pw.lower() in COMMON or len(set(pw)) < 5:
        return "That password is too easy to guess."
    local = email.split("@")[0].lower()
    if local and len(local) >= 4 and local in pw.lower():
        return "Password must not contain your email name."
    return None


# ----------------------------------------------------------------------------- tokens (HS256 JWT)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(user_id: str, tv: int, sid: float | None = None, now: float | None = None) -> str:
    now = int(now or time.time())
    claims = {"sub": user_id, "tv": tv, "iat": now, "exp": now + TOKEN_TTL(),
              "sid": int(sid or now), "jti": uuid.uuid4().hex}
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


class AuthError(Exception):
    def __init__(self, message="Unauthorized", status=401, headers=None):
        self.message, self.status, self.headers = message, status, headers or {}


def decode_token(token: str, grace: int = 0) -> dict:
    """Verify signature, algorithm and expiry. `grace` allows a recently expired token (refresh only)."""
    try:
        head_b, body_b, sig_b = token.split(".")
        head = json.loads(_unb64(head_b))
        if head.get("alg") != "HS256":  # never trust the token's own idea of its algorithm ("none")
            raise ValueError("alg")
        good = hmac.new(secret(), f"{head_b}.{body_b}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(good, _unb64(sig_b)):
            raise ValueError("sig")
        claims = json.loads(_unb64(body_b))
    except Exception:
        raise AuthError("Invalid token")
    now = time.time()
    if not isinstance(claims.get("exp"), (int, float)) or now > claims["exp"] + grace:
        raise AuthError("Session expired")
    if now - claims.get("sid", claims.get("iat", 0)) > SESSION_MAX():
        raise AuthError("Session expired")
    return claims


def _user_row(user_id: str):
    c = _db()
    try:
        return c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    finally:
        c.close()


def _is_revoked(jti: str) -> bool:
    c = _db()
    try:
        c.execute("DELETE FROM revoked WHERE exp < ?", (time.time(),))
        c.commit()
        return c.execute("SELECT 1 FROM revoked WHERE jti=? AND at <= ?", (jti, time.time())).fetchone() is not None
    finally:
        c.close()


def authenticate_token(token: str, grace: int = 0) -> tuple[dict, sqlite3.Row]:
    claims = decode_token(token, grace)
    row = _user_row(claims.get("sub", ""))
    if row is None or row["disabled"] or row["token_version"] != claims.get("tv") or _is_revoked(claims.get("jti", "")):
        raise AuthError("Session is no longer valid")
    return claims, row


def bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h[:7].lower() == "bearer " else None


def public_user(row) -> dict:
    """The user object the front end expects (invite-only accounts are pre-verified and onboarded)."""
    return {"id": row["id"], "_id": row["id"], "email": row["email"], "name": row["name"] or row["email"].split("@")[0],
            "role": "advocate", "emailVerified": True, "phoneVerified": True,
            "onboardingCompletedAt": "2026-01-01T00:00:00.000Z", "onboardingComplete": True,
            "subscription": {"status": "active", "plan": "invite", "trialEndsAt": None}}


# ----------------------------------------------------------------------------- rate limiting
class Limiter:
    """Sliding-window counter, in memory (per process)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> None:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise AuthError("Too many requests. Please slow down.", 429,
                                {"Retry-After": str(max(1, int(window - (now - q[0]))))})
            q.append(now)
            if len(self.hits) > 20000:  # bound memory under a key-spraying attack
                for k in [k for k, v in self.hits.items() if not v][:5000]:
                    self.hits.pop(k, None)

    def reset(self):
        with self.lock:
            self.hits.clear()


limiter = Limiter()


def client_ip(request: Request) -> str:
    if os.environ.get("TRUST_PROXY") == "1":
        xf = request.headers.get("x-forwarded-for", "")
        if xf:
            return xf.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ----------------------------------------------------------------------------- request guard
def guard(request: Request) -> None:
    """Global dependency. Static files and the SPA are public; /api needs a token unless listed."""
    path = request.url.path
    if not path.startswith("/api/") and path != "/api":
        return
    ip = client_ip(request)
    if path in PUBLIC_EXACT or (request.method == "GET" and path.startswith(PUBLIC_GET_PREFIX)):
        limiter.hit(f"pub:{ip}", 120, 60)
        return
    token = bearer(request)
    if not token:
        raise AuthError("Authentication required", 401, {"WWW-Authenticate": "Bearer"})
    claims, row = authenticate_token(token)
    request.state.user = row
    request.state.claims = claims
    limiter.hit(f"user:{row['id']}", 600, 60)


# ----------------------------------------------------------------------------- login / refresh / logout
def _attempt_key(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _check_locked(c, key: str) -> None:
    r = c.execute("SELECT * FROM attempts WHERE key=?", (key,)).fetchone()
    if r and r["locked_until"] > time.time():
        raise AuthError("Too many failed attempts. Try again in a few minutes.", 429,
                        {"Retry-After": str(int(r["locked_until"] - time.time()))})


def _record_failure(c, key: str) -> None:
    now = time.time()
    r = c.execute("SELECT * FROM attempts WHERE key=?", (key,)).fetchone()
    if r is None or now - (r["first_at"] or 0) > FAIL_WINDOW:
        c.execute("INSERT OR REPLACE INTO attempts(key,fails,first_at,locked_until) VALUES (?,?,?,0)", (key, 1, now))
    else:
        fails = r["fails"] + 1
        c.execute("UPDATE attempts SET fails=?, locked_until=? WHERE key=?",
                  (fails, now + LOCK_SECONDS if fails >= MAX_FAILS else 0, key))
    c.commit()


def login(request: Request, email: str, password: str) -> dict:
    ip = client_ip(request)
    limiter.hit(f"login:{ip}", 10, 60)
    email = (email or "").strip().lower()
    if not email or not password or len(email) > 254 or len(password) > 256:
        raise AuthError("Invalid email or password", 401)
    key = _attempt_key(email)
    c = _db()
    try:
        _check_locked(c, key)  # same behaviour whether or not the account exists
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = verify_password(password, row["pw_hash"] if row else _dummy_hash())  # equal work either way
        if not (row and ok) or row["disabled"]:
            _record_failure(c, key)
            raise AuthError("Invalid email or password", 401)
        c.execute("DELETE FROM attempts WHERE key=?", (key,))
        c.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), row["id"]))
        c.commit()
        return {"token": sign_token(row["id"], row["token_version"]), "user": public_user(row)}
    finally:
        c.close()


def refresh(request: Request) -> dict:
    """Swap a valid (or recently expired) token for a fresh one. The login's total age is capped."""
    token = bearer(request)
    if not token:
        raise AuthError("Authentication required")
    claims, row = authenticate_token(token, grace=REFRESH_GRACE())
    c = _db()
    try:  # the old token is retired shortly after, not instantly: the app has requests in flight with it
        c.execute("INSERT OR IGNORE INTO revoked(jti, exp, at) VALUES (?,?,?)",
                  (claims["jti"], claims["exp"] + REFRESH_GRACE() + 60, time.time() + ROTATE_OVERLAP))
        c.commit()
    finally:
        c.close()
    return {"token": sign_token(row["id"], row["token_version"], sid=claims.get("sid")), "user": public_user(row)}


def logout(request: Request) -> None:
    token = bearer(request)
    if not token:
        return
    try:
        claims = decode_token(token, grace=REFRESH_GRACE())
    except AuthError:
        return
    c = _db()
    try:
        c.execute("INSERT OR REPLACE INTO revoked(jti, exp, at) VALUES (?,?,?)",
                  (claims["jti"], claims["exp"] + REFRESH_GRACE() + 60, 0))  # logout takes effect at once
        c.commit()
    finally:
        c.close()


def change_password(row, current: str, new: str) -> None:
    if not verify_password(current, row["pw_hash"]):
        raise AuthError("Current password is incorrect", 403)
    msg = check_password_policy(new, row["email"])
    if msg:
        raise AuthError(msg, 400)
    c = _db()
    try:  # bumping token_version signs the user out everywhere
        c.execute("UPDATE users SET pw_hash=?, token_version=token_version+1 WHERE id=?", (hash_password(new), row["id"]))
        c.commit()
    finally:
        c.close()


# ----------------------------------------------------------------------------- admin helpers (CLI)
def create_user(email: str, password: str, name: str = "") -> str:
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("That does not look like an email address")
    msg = check_password_policy(password, email)
    if msg:
        raise ValueError(msg)
    uid = uuid.uuid4().hex
    c = _db()
    try:
        c.execute("INSERT INTO users(id,email,name,pw_hash,created_at) VALUES (?,?,?,?,?)",
                  (uid, email, name or email.split("@")[0], hash_password(password), time.time()))
        c.commit()
    except sqlite3.IntegrityError:
        raise ValueError("An account with that email already exists")
    finally:
        c.close()
    return uid
