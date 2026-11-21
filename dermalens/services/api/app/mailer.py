"""Outgoing email. SMTP when SMTP_HOST is set; otherwise the message is written to
the API log so development works without a mail server. Bodies are never stored."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import models as M
from .config import settings
from .db import SessionLocal

log = logging.getLogger("dermalens.mail")
logging.basicConfig(level=logging.INFO)

FOOTER = ("\n\n--\nDermaLens, a skincare pre-screening service of ICONIC Aesthetic Clinic.\n"
          "If you did not expect this email, you can ignore it.")


def send(to: str, kind: str, subject: str, body: str) -> str:
    status, error = "logged", None
    if settings.smtp_host:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
        msg.set_content(body + FOOTER)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                if settings.smtp_port != 25:
                    s.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
            status = "sent"
        except Exception as e:  # delivery problems must not break the request
            status, error = "failed", str(e)[:500]
            log.error("email to %s failed: %s", to, e)
    else:
        log.info("DEV EMAIL to=%s subject=%r\n%s", to, subject, body)
    with SessionLocal() as db:
        db.add(M.EmailLog(to_addr=to, kind=kind, status=status, error=error))
        db.commit()
    return status
