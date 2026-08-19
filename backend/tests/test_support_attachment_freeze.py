"""Regression tests for the text-only public support boundary."""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from app.api import support


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/support/contact",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


@pytest.mark.asyncio
async def test_support_attachments_are_rejected_by_default() -> None:
    attachment = UploadFile(filename="untrusted.txt", file=BytesIO(b"untrusted content"))

    with pytest.raises(HTTPException) as exc_info:
        await support.contact_support(
            request=_request(),
            name="Seeker",
            email="seeker@example.com",
            subject="Question",
            message="Please help.",
            attachments=[attachment],
        )

    assert exc_info.value.status_code == 403
    assert "text-only" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_text_only_support_request_is_still_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "send_support_email", lambda **_: True)

    response = await support.contact_support(
        request=_request(),
        name="Seeker",
        email="seeker@example.com",
        subject="Question",
        message="Please help.",
        attachments=[],
    )

    assert response["ok"] is True


@pytest.mark.asyncio
async def test_support_honeypot_is_accepted_without_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _send(**_: object) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(support, "send_support_email", _send)
    response = await support.contact_support(
        request=_request(),
        name="Seeker",
        email="seeker@example.com",
        subject="Question",
        message="Please help.",
        website="https://bot.example",
        attachments=[],
    )

    assert response["ok"] is True
    assert called is False
