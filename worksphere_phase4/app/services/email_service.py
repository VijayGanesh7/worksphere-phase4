"""Email integration (Module 25). Sends via SMTP when EMAIL_ENABLED=true, otherwise just logs."""
import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from typing import Iterable

from ..config import settings

log = logging.getLogger("worksphere.email")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mailer")
_BATCH = 50


def _clean(text: str) -> str:
    return " ".join(text.split())  # strips CR/LF so headers cannot be injected


def send_email(recipients: Iterable[str], subject: str, body: str) -> bool:
    recipients = sorted(set(recipients))
    if not recipients:
        return False
    subject = _clean(subject)[:200]
    if not settings.email_enabled:
        log.info("Email disabled; would send %r to %d recipient(s)", subject, len(recipients))
        return False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            for i in range(0, len(recipients), _BATCH):
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = settings.smtp_from
                msg["To"] = settings.smtp_from
                msg["Bcc"] = ", ".join(recipients[i : i + _BATCH])
                msg.set_content(body)
                smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Failed to send email %r", subject)
        return False


def send_email_async(recipients: Iterable[str], subject: str, body: str) -> None:
    """Fire-and-forget so API requests never wait on SMTP."""
    recipients = list(recipients)
    if recipients:
        _pool.submit(send_email, recipients, subject, body)
