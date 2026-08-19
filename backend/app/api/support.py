from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import EmailStr

from app.config import settings
from app.core.limiter import limiter
from app.services.email_service import send_support_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["Support"])

SUPPORTED_ATTACHMENT_TYPES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".mp4", ".mov", ".avi",
    ".pdf", ".txt", ".log",
    ".zip",
}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
MAX_ATTACHMENTS = 5


@router.post("/contact")
@limiter.limit(settings.support_contact_rate_limit)
async def contact_support(
    request: Request,
    name: str = Form(""),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    category: str = Form("Feedback"),
    website: str = Form(""),
    attachments: list[UploadFile] = File(default_factory=list),
):
    # Honeypot: legitimate clients leave this hidden field empty. Returning a
    # generic success avoids teaching bots which field triggered the block.
    website_value = website if isinstance(website, str) else ""
    if website_value.strip():
        return {"ok": True, "status": "success", "message": "Message received."}
    name = name.strip()
    email = email.strip()
    subject = subject.strip()
    message = message.strip()
    category_value = category if isinstance(category, str) else "Feedback"
    category = category_value.strip() or "Feedback"
    if len(name) > settings.support_max_name_chars:
        raise HTTPException(status_code=422, detail="Name is too long")
    if len(subject) > settings.support_max_subject_chars:
        raise HTTPException(status_code=422, detail="Subject is too long")
    if len(message) > settings.support_max_message_chars:
        raise HTTPException(status_code=422, detail="Message is too long")
    if not email:
        raise HTTPException(status_code=422, detail="Valid email is required")
    import re
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        raise HTTPException(status_code=422, detail="Valid email is required")

    if not subject:
        raise HTTPException(status_code=422, detail="Subject is required")

    if not message:
        raise HTTPException(status_code=422, detail="Message is required")

    saved_paths: list[str] = []
    if attachments:
        raise HTTPException(
            status_code=403,
            detail="Support attachments are not available. Please send a text-only request.",
        )

    try:
        ok = send_support_email(
            name=name,
            from_email=email,
            subject=subject,
            message=message,
            category=category,
            attachment_paths=saved_paths,
        )
        if not ok:
            raise HTTPException(
                status_code=500,
                detail="Failed to send support email. Please try again later.",
            )
        return {"ok": True, "status": "success", "message": "Message sent. We will get back to you within 24-48 hours."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to send support email: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to send support email. Please try again later.",
        )
