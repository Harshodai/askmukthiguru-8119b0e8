"""Machine-readable public capability states for truthful product behaviour."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from starlette import status as http_status

import app.dependencies as app_dependencies
from app.config import settings
from app.dependencies import ServiceContainer, get_container

router = APIRouter(tags=["Capabilities"])


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
            "teacher_voice": _state(settings.langhanam_voice_enabled),
            "serene_mind": _state(True, getattr(container, "serene_mind", None) is not None),
            "guided_meditation": "available",
            "text_attachments": "available",
            "voice_input": "available",
            "whatsapp": "disabled_by_policy",
            "support_attachments": "disabled_by_policy",
            "waitlist": _state(
                settings.waitlist_enabled,
                getattr(container, "supabase_client", None) is not None,
            ),
            "google_sso": _state(settings.google_sso_enabled),
            "push_notifications": _state(settings.push_notifications_enabled),
        },
    }


@router.get("/capabilities")
async def capabilities_endpoint(
    container: ServiceContainer = Depends(get_container),
) -> JSONResponse:
    """Expose current safe capability state for UI, operational checks, and release evidence."""
    if not app_dependencies.startup_complete:
        return JSONResponse(
            {"ready": False, "capabilities": {}},
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse({"ready": True, "capabilities": build_capability_manifest(container)})
