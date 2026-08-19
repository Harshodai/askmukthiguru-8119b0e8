from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.metrics import REQUEST_COUNT
from app.runtime_metrics import observe_request_resources

logger = logging.getLogger(__name__)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Logs all API requests with method, path, status, duration.

    Structured JSON logging for SIEM/audit trail ingestion.
    Skips health checks and static file mounts.
    """

    SKIP_PATHS = frozenset(
        {
            "/api/health",
            "/metrics",
            "/static-ingest",
            "/static-chat",
            "/favicon.ico",
        }
    )

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        cpu_start = time.process_time()
        method = request.method
        path = request.url.path

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration = time.monotonic() - start
            observe_request_resources(time.process_time() - cpu_start)
            logger.error(
                "AUDIT %s %s -> EXCEPTION (%.3fs): %s",
                method,
                path,
                duration,
                exc,
            )
            raise

        duration = time.monotonic() - start

        observe_request_resources(time.process_time() - cpu_start)
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return response

        REQUEST_COUNT.labels(status=f"{response.status_code // 100}xx").inc()

        logger.info(
            "AUDIT %s %s -> %s (%.3fs)",
            method,
            path,
            response.status_code,
            duration,
        )
        return response
