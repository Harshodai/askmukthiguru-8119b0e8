"""Machine-readable public capability states for truthful product behaviour."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from starlette import status as http_status

import app.dependencies as app_dependencies
from app.config import settings
from app.dependencies import ServiceContainer, get_container_async

router = APIRouter(tags=["Capabilities"])
logger = logging.getLogger(__name__)


def _state(enabled: bool, available: bool = True) -> str:
    if not enabled:
        return "disabled_by_policy"
    return "available" if available else "unavailable"


def build_capability_manifest(container: Any) -> dict[str, Any]:
    """Describe capability policy and process-local availability without secrets."""
    vector_available = getattr(container, "qdrant", None) is not None
    embedding_available = getattr(container, "embedding", None) is not None
    graph_available = bool(getattr(container, "standard_graph", None)) and not getattr(
        container, "lightrag_degraded", True
    )
    # The chat endpoints use the Redis-backed job_queue controlled by
    # QUEUE_ENABLED. ``use_request_queue`` is a separate legacy in-process
    # request queue and must not be exposed as the public chat queue state.
    chat_queue_enabled = bool(getattr(settings, "queue_enabled", False))
    chat_queue_available = getattr(container, "job_queue", None) is not None
    ocr_service = getattr(container, "ocr", None)
    try:
        ocr_available = bool(ocr_service is not None and ocr_service.health_check())
    except Exception as exc:
        logger.debug("OCR capability probe failed: %s", exc)
        ocr_available = False
    media_runtime_available = shutil.which("ffmpeg") is not None

    return {
        "schema_version": 1,
        "llm_provider": settings.llm_provider,
        "features": {
            "chat_generation": _state(True, getattr(container, "ollama", None) is not None),
            "retrieval": _state(True, vector_available and embedding_available),
            "knowledge_graph": _state(settings.knowledge_graph_query_enabled, graph_available),
            "memory_write": _state(settings.feature_memory_write),
            "live_information": _state(
                settings.web_search_enabled, getattr(container, "web_search", None) is not None
            ),
            "live_logistics": _state(
                settings.live_logistics_enabled,
                settings.web_search_enabled and getattr(container, "web_search", None) is not None,
            ),
            "request_queue": _state(chat_queue_enabled, chat_queue_available),
            "teacher_voice": _state(True),
            "serene_mind": _state(True, getattr(container, "serene_mind", None) is not None),
            "guided_meditation": "available",
            "text_attachments": "available",
            "document_attachments": "available",
            "image_attachments": "available",
            "audio_attachments": _state(True, media_runtime_available),
            "video_attachments": _state(True, media_runtime_available),
            "ocr": _state(True, ocr_available),
            "voice_input": "available",
            "whatsapp": _state(settings.whatsapp_enabled),
            "support_attachments": "disabled_by_policy",
            "waitlist": _state(
                settings.waitlist_enabled,
                getattr(container, "supabase_client", None) is not None,
            ),
            "google_sso": _state(settings.google_sso_enabled),
            "push_notifications": _state(True),
        },
    }


# Rendered /api/capabilities body, reused for settings.capabilities_cache_ttl_s. The
# manifest holds booleans and state strings only (no secrets, no per-caller data), and the
# endpoint is public and polled by every page load and by bots, so one render serves all.
_manifest_cache: dict[str, Any] = {"until": 0.0, "body": None, "etag": None}


def _rendered_manifest(container: Any, ttl: float) -> tuple[bytes, str]:
    now = time.monotonic()
    if ttl > 0 and _manifest_cache["body"] is not None and now < _manifest_cache["until"]:
        return _manifest_cache["body"], _manifest_cache["etag"]
    body = json.dumps(
        {"ready": True, "capabilities": build_capability_manifest(container)},
        separators=(",", ":"),
    ).encode("utf-8")
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    if ttl > 0:
        _manifest_cache.update(until=now + ttl, body=body, etag=etag)
    return body, etag


@router.get("/capabilities")
async def capabilities_endpoint(
    request: Request,
    container: ServiceContainer = Depends(get_container_async),
) -> Response:
    """Expose current safe capability state for UI, operational checks, and release evidence.

    Cacheable: the body is rendered at most once per ``capabilities_cache_ttl_s`` and carries
    ``Cache-Control: public, max-age`` plus an ``ETag`` (``If-None-Match`` -> 304), so
    repeated polls cost no manifest work and almost no bytes. The not-ready 503 is never cached.
    """
    if not app_dependencies.startup_complete:
        return JSONResponse(
            {"ready": False, "capabilities": {}},
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Cache-Control": "no-store"},
        )
    ttl = float(settings.capabilities_cache_ttl_s)
    body, etag = _rendered_manifest(container, ttl)
    headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={int(ttl)}" if ttl > 0 else "no-cache",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=http_status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
