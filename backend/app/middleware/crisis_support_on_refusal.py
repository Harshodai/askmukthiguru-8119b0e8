"""Verified crisis-support lines on every 429 from the chat surface.

Found by the registered run of 2026-11-15: a crisis message that hit the rate
limiter got an empty 429. The limiter runs before any crisis check, so a
rate-limited or over-quota seeker was shown no helpline.

This middleware does not classify anything and exempts nothing from a limit.
It only adds one static field, ``crisis_support``, to a JSON 429 body. Status,
headers and every existing key stay as they were.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# The seeker-facing surface. Admin and ingestion refusals are left alone.
CHAT_SURFACE_PREFIXES = ("/api/chat", "/api/auth/anon-session", "/api/first-person")


def crisis_support_field() -> dict[str, str] | None:
    """The phone-verified helpline block, or None when the source cannot be read."""
    from services import crisis_helplines

    try:
        return {"text": crisis_helplines.format_helplines_block(verified_only=True)}
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        logger.warning("crisis support lines unavailable for a 429 body: %s", type(exc).__name__)
        return None


def with_crisis_support(body: bytes) -> bytes:
    """Return ``body`` with ``crisis_support`` added when it is a JSON object."""
    try:
        payload: Any = json.loads(body) if body else {}
    except (ValueError, UnicodeDecodeError):
        return body
    if not isinstance(payload, dict) or "crisis_support" in payload:
        return body
    field = crisis_support_field()
    if field is None:
        return body
    payload["crisis_support"] = field
    return json.dumps(payload).encode("utf-8")


class CrisisSupportOnRefusalMiddleware:
    """Pure ASGI: rewrite only 429 responses on the chat surface."""

    def __init__(self, app: Any, prefixes: tuple[str, ...] = CHAT_SURFACE_PREFIXES) -> None:
        self.app = app
        self.prefixes = prefixes

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith(self.prefixes):
            await self.app(scope, receive, send)
            return

        held_start: dict | None = None
        chunks: list[bytes] = []

        async def send_with_support(message: dict) -> None:
            nonlocal held_start
            if message["type"] == "http.response.start" and message["status"] == 429:
                held_start = message  # hold until the body is known
                return
            if message["type"] == "http.response.body" and held_start is not None:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = with_crisis_support(b"".join(chunks))
                headers = [
                    (k, v)
                    for k, v in held_start.get("headers", [])
                    if k.lower() != b"content-length"
                ]
                headers.append((b"content-length", str(len(body)).encode("ascii")))
                await send({**held_start, "headers": headers})
                await send({"type": "http.response.body", "body": body})
                held_start = None
                return
            await send(message)

        await self.app(scope, receive, send_with_support)


if __name__ == "__main__":
    out = json.loads(with_crisis_support(b'{"error": "rate_limited"}'))
    assert out["error"] == "rate_limited" and "14416" in out["crisis_support"]["text"], out
    assert with_crisis_support(b"not json") == b"not json"
    print("ok")
