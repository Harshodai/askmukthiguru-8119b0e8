from __future__ import annotations

import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _sanitize_header(value: str, max_len: int = 200) -> str:
    """Strip CR/LF/other control chars to prevent email-header injection (RFC 5322)."""
    if not value:
        return ""
    # Remove all control chars incl. \r \n \t and NUL
    cleaned = "".join(ch for ch in value if ch.isprintable() and ch not in "\r\n")
    return cleaned[:max_len].strip()


def send_support_email(
    name: str,
    from_email: str,
    subject: str,
    message: str,
    category: str,
    attachment_paths: Optional[list[str]] = None,
) -> bool:
    dest = settings.support_to_email
    safe_category = _sanitize_header(category) or "Feedback"
    safe_subject = _sanitize_header(subject) or "(no subject)"
    safe_from = _sanitize_header(from_email, max_len=254)
    full_subject = f"[AskMukthiGuru] {safe_category}: {safe_subject}"


    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        return _send_via_smtp(
            to=dest,
            subject=full_subject,
            body=_build_body(name, safe_from, message),
            from_email=safe_from,
            attachment_paths=attachment_paths or [],
        )

    return _save_to_disk(name, safe_from, safe_subject, message, safe_category, attachment_paths)


def _build_body(name: str, from_email: str, message: str) -> str:
    return (
        f"Name: {name or 'Not provided'}\n"
        f"From: {from_email}\n"
        f"---\n{message}\n"
    )


def _send_via_smtp(
    to: str,
    subject: str,
    body: str,
    from_email: str,
    attachment_paths: list[str],
) -> bool:
    try:
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        msg["Reply-To"] = from_email
        msg.attach(MIMEText(body, "plain", "utf-8"))

        for path in attachment_paths:
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={os.path.basename(path)}",
                )
                msg.attach(part)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

        logger.info("Support email sent to %s (subject=%s)", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send support email via SMTP: %s", e)
        return False


def _save_to_disk(
    name: str,
    from_email: str,
    subject: str,
    message: str,
    category: str,
    attachment_paths: Optional[list[str]],
) -> bool:
    try:
        os.makedirs(settings.support_storage_path, exist_ok=True)
        ts = int(time.time())
        entry = {
            "ts": ts,
            "name": name,
            "from_email": from_email,
            "subject": subject,
            "message": message,
            "category": category,
            "attachments": attachment_paths or [],
        }
        fname = f"{ts}_{from_email.replace('@', '_at_')}.json"
        path = os.path.join(settings.support_storage_path, fname)
        with open(path, "w") as f:
            json.dump(entry, f, indent=2)
        logger.info("Support message saved to %s", path)
        return True
    except Exception as e:
        logger.error("Failed to save support message to disk: %s", e)
        return False
