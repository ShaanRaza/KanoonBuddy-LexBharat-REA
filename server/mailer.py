"""Outgoing email (verification and password-reset links).

Production: set SMTP_HOST (and normally SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM). Port 465 uses SSL,
anything else uses STARTTLS. Any SMTP provider works (Amazon SES, Brevo, Zoho, Gmail app password ...).
Development (LEXBHARAT_ENV=dev, no SMTP_HOST): the message is written to data/outbox/ instead of being sent,
so the full sign-up flow can be tried and tested without a mail account.
If neither applies, sending is reported as unavailable and self-service sign-up switches itself off.
"""
import logging
import os
import smtplib
import threading
import time
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger("lexbharat.mail")
ROOT = Path(__file__).resolve().parent.parent


def outbox_dir() -> Path:
    return Path(os.environ.get("LEXBHARAT_DATA", ROOT / "data")) / "outbox"


def configured() -> bool:
    """True when we can actually deliver (or capture, in dev) email."""
    return bool(os.environ.get("SMTP_HOST")) or os.environ.get("LEXBHARAT_ENV", "production").lower() == "dev"


def base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:8000" if os.environ.get("LEXBHARAT_ENV", "").lower() == "dev" else "").rstrip("/")


def _deliver(to: str, subject: str, text: str) -> None:
    sender = os.environ.get("MAIL_FROM", "LexBharat <no-reply@lexbharat.ai>")
    host = os.environ.get("SMTP_HOST")
    if not host:  # dev: capture to disk
        d = outbox_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{time.time_ns()}-{to.replace('/', '_')}.txt").write_text(
            f"To: {to}\nFrom: {sender}\nSubject: {subject}\n\n{text}\n", encoding="utf-8")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(text)
    port = int(os.environ.get("SMTP_PORT", "587"))
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            if user:
                s.login(user, pw or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            if user:
                s.login(user, pw or "")
            s.send_message(msg)


def send(to: str, subject: str, text: str, wait: bool = False) -> None:
    """Send in the background so the request returns at the same speed whether or not the address exists."""
    def run():
        try:
            _deliver(to, subject, text)
        except Exception:
            log.exception("could not send email to a user (subject: %s)", subject)  # never log the link itself

    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------- message bodies
def verify_email_text(name: str, link: str) -> tuple[str, str]:
    return ("Confirm your email for LexBharat",
            f"Hello {name or 'there'},\n\nPlease confirm your email address to finish creating your LexBharat account:\n\n{link}\n\n"
            "This link works once and expires in 24 hours. If you did not create an account, ignore this email and nothing will happen.\n\n"
            "LexBharat is a research aid, not legal advice.")


def reset_email_text(name: str, link: str) -> tuple[str, str]:
    return ("Reset your LexBharat password",
            f"Hello {name or 'there'},\n\nWe received a request to reset your LexBharat password. Choose a new one here:\n\n{link}\n\n"
            "This link works once and expires in 1 hour. If you did not ask for this, ignore this email; your password has not changed.")


def deletion_email_text(name: str, days: int) -> tuple[str, str]:
    return ("Your LexBharat account is scheduled for deletion",
            f"Hello {name or 'there'},\n\nYour account and its saved chats and documents will be permanently deleted in {days} days. "
            "To keep it, sign in and cancel the deletion in Account settings before then.")
