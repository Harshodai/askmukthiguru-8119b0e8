from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from pydantic import EmailStr

from app.config import settings
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
async def contact_support(
    name: str = Form(""),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    category: str = Form("Feedback"),
    attachments: list[UploadFile] = File(default_factory=list),
):
    if not email:
        raise HTTPException(status_code=422, detail="Valid email is required")
    import re
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        raise HTTPException(status_code=422, detail="Valid email is required")

    if not subject.strip():
        raise HTTPException(status_code=422, detail="Subject is required")

    if not message.strip():
        raise HTTPException(status_code=422, detail="Message is required")

    saved_paths: list[str] = []
    tmp_dir = f"/tmp/support_attachments/{uuid.uuid4().hex}"
    try:
        os.makedirs(tmp_dir, exist_ok=True)

        for af in attachments:
            ext = os.path.splitext(af.filename or "")[1].lower()
            if ext not in SUPPORTED_ATTACHMENT_TYPES:
                logger.warning("Skipped unsupported attachment type: %s", ext)
                continue
            content = await af.read()
            if len(content) > MAX_ATTACHMENT_SIZE:
                logger.warning("Skipped oversized attachment: %s", af.filename)
                continue
            if ext in {".jpg", ".jpeg"}:
                if not content.startswith(b"\xff\xd8\xff"):
                    logger.warning("Skipped attachment with mismatched content type: %s", af.filename)
                    continue
            elif ext == ".png" and not content.startswith(b"\x89PNG"):
                logger.warning("Skipped attachment with mismatched content type: %s", af.filename)
                continue
            elif ext == ".pdf" and not content.startswith(b"%PDF"):
                logger.warning("Skipped attachment with mismatched content type: %s", af.filename)
                continue
            dest = os.path.join(tmp_dir, f"{uuid.uuid4().hex}{ext}")
            with open(dest, "wb") as f:
                f.write(content)
            saved_paths.append(dest)

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
                detail="Failed to send message. Please try again later or email us directly.",
            )

        return {"ok": True, "message": "Message sent. We will get back to you within 24-48 hours."}
    finally:
        import shutil
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
