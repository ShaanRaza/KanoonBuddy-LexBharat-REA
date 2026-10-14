"""Administer LexBharat accounts. There is no public sign-up, so users are created here.

  python -m server.manage_users add you@example.com --name "Your Name"     # prompts for a password
  python -m server.manage_users add you@example.com --generate             # prints a random one, once
  python -m server.manage_users list
  python -m server.manage_users passwd you@example.com
  python -m server.manage_users disable you@example.com                    # also signs them out everywhere
  python -m server.manage_users enable you@example.com
  python -m server.manage_users delete you@example.com

Set LEXBHARAT_ENV=dev (or LEXBHARAT_DATA / AUTH_DB) to match the server you are administering.
"""
import argparse
import getpass
import secrets
import sys
import time

from server import auth


def _row(email):
    c = auth._db()
    try:
        return c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    finally:
        c.close()


def _ask_password(email):
    while True:
        a = getpass.getpass("New password (12+ characters): ")
        msg = auth.check_password_policy(a, email)
        if msg:
            print(msg)
            continue
        if a != getpass.getpass("Repeat: "):
            print("Passwords did not match.")
            continue
        return a


def main(argv=None):
    ap = argparse.ArgumentParser(prog="manage_users", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("email")
    a.add_argument("--name", default="")
    a.add_argument("--generate", action="store_true", help="generate a strong password and print it once")
    for name in ("passwd", "disable", "enable", "delete"):
        sub.add_parser(name).add_argument("email")
    sub.add_parser("list")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        c = auth._db()
        rows = c.execute("SELECT email,name,disabled,last_login FROM users ORDER BY created_at").fetchall()
        c.close()
        for r in rows:
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["last_login"])) if r["last_login"] else "never"
            print(f"{r['email']:40} {'DISABLED' if r['disabled'] else 'active':9} last login: {last}")
        print(f"{len(rows)} account(s)")
        return 0

    if args.cmd == "add":
        pw = secrets.token_urlsafe(18) if args.generate else _ask_password(args.email)
        try:
            auth.create_user(args.email, pw, args.name)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"Created {args.email.strip().lower()}")
        if args.generate:
            print(f"Password (shown once, change it after first sign-in): {pw}")
        return 0

    row = _row(args.email)
    if row is None:
        print("error: no such account", file=sys.stderr)
        return 1
    c = auth._db()
    try:
        if args.cmd == "passwd":
            pw = _ask_password(args.email)
            c.execute("UPDATE users SET pw_hash=?, token_version=token_version+1 WHERE id=?", (auth.hash_password(pw), row["id"]))
            print("Password changed; existing sessions are signed out.")
        elif args.cmd == "disable":
            c.execute("UPDATE users SET disabled=1, token_version=token_version+1 WHERE id=?", (row["id"],))
            print("Disabled; existing sessions are signed out.")
        elif args.cmd == "enable":
            c.execute("UPDATE users SET disabled=0 WHERE id=?", (row["id"],))
            print("Enabled.")
        elif args.cmd == "delete":
            if input(f"Delete {row['email']}? Type the email to confirm: ").strip().lower() != row["email"]:
                print("Cancelled.")
                return 1
            c.execute("DELETE FROM users WHERE id=?", (row["id"],))
            print("Deleted.")
        c.commit()
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
