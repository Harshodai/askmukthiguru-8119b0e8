"""Official-source live logistics search node."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from app.config import settings
from app.schemas import LiveLogisticsEvent
from app.tracing import trace_rag_node
from rag.states import GraphState

logger = logging.getLogger(__name__)


@trace_rag_node("web_search")
async def web_search_node(state: GraphState, config: dict = None) -> dict:
    """Fetch official event, schedule, and booking results only.

    General temporal questions deliberately do not invoke live search. This
    avoids treating unverified snippets as current logistical facts.
    """
    if state.get("intent") != "LIVE_LOGISTICS":
        return {"web_search_results": []}
    if not settings.live_logistics_enabled:
        return {"web_search_results": []}

    from rag.nodes import _services

    service = getattr(_services, "_web_search", None)
    if service is None:
        logger.warning("Live logistics requested but WebSearchService is unavailable")
        return {"web_search_results": []}

    question = state.get("rewritten_query") or state["question"]
    user_id = state.get("user_id")
    try:
        results = await service.search(question, user_id=user_id)
    except Exception as exc:
        logger.warning("Official live logistics search failed: %s", exc)
        return {"web_search_results": []}

    verified_at = datetime.now(timezone.utc)
    expires_at = verified_at + timedelta(seconds=settings.live_logistics_ttl_seconds)
    typed_results: list[dict] = []
    for result in results:
        try:
            event = LiveLogisticsEvent(
                event_name=result.get("title") or "Official event information",
                official_source_url=result["source_url"],
                booking_url=result["source_url"],
                verified_at=verified_at,
                expires_at=expires_at,
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Ignoring invalid official live logistics result: %s", exc)
            continue
        typed = dict(result)
        typed["live_event"] = event.model_dump(mode="json")
        typed["content_type"] = "live_logistics"
        typed["verified_at"] = event.verified_at.isoformat()
        typed["expiry"] = event.expires_at.isoformat()
        typed["official_source_url"] = event.official_source_url
        typed_results.append(typed)
    return {"web_search_results": typed_results}
