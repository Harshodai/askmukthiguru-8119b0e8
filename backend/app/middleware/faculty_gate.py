"""Shared-secret access gate for the faculty preview.

When ``FACULTY_ACCESS_CODE`` is set, every request to a gated API prefix must
carry the same value in the ``X-Faculty-Code`` header, otherwise it gets 401
before any LLM call, retrieval or cost accrues. Unset (the default) means the
gate is off and the app behaves as before.

Fails closed: a configured gate with a missing or wrong header never reaches
the route. The comparison is constant-time. CORS preflights, health probes and
metrics (which have their own credentials) are exempt.

Pure ASGI on purpose: no body buffering, safe for SSE streaming responses.
"""

from __future__ import annotations

import hmac
import json
import logging

logger = logging.getLogger(__name__)

HEADER_NAME = "x-faculty-code"
GATED_PREFIXES: tuple[str, ...] = ("/api/chat", "/api/first-person", "/api/jobs")
_EXEMPT_PREFIXES: tuple[str, ...] = ("/api/health", "/api/healthz", "/metrics", "/internal/metrics")


def is_gated(path: str) -> bool:
    if path.startswith(_EXEMPT_PREFIXES):
        return False
    return path.startswith(GATED_PREFIXES)


class FacultyGateMiddleware:
    def __init__(self, app, access_code: str):
        if not access_code:
            raise ValueError("FacultyGateMiddleware requires a non-empty access_code")
        self.app = app
        self._code = access_code.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") == "OPTIONS"
            or not is_gated(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        supplied = b""
        for name, value in scope.get("headers", []):
            if name == HEADER_NAME.encode("ascii"):
                supplied = value
                break

        if not hmac.compare_digest(supplied, self._code):
            logger.warning("faculty gate rejected %s %s", scope.get("method"), scope.get("path"))
            body = json.dumps({"detail": "Faculty access code required."}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"x-faculty-gate", b"denied"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


if __name__ == "__main__":
    assert is_gated("/api/chat/stream") and not is_gated("/api/health")
    print("faculty_gate ok")
