"""
Mukthi Guru — First-Person Verbatim Teaching Route

Serves verified teacher clips (Sri Preethaji / Sri Krishnaji) with exact
timestamps, strictly gated behind FIRST_PERSON_MODE and first_person_route_enabled.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Optional

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container_async
from services.first_person_pipeline import FirstPersonPipeline
from services.first_person_store import FirstPersonStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["First-Person Verbatim Teachings"])


class FirstPersonQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="The seeker question")
    teacher_id: Optional[str] = Field("both", description="'preethaji', 'krishnaji', or 'both'")
    max_clips: int = Field(3, ge=1, le=5, description="Max verified clips to return (max 1 per video)")


class FirstPersonQueryResponse(BaseModel):
    answer_text: str
    citations: list[dict[str, Any]]
    status: str
    is_direct_answer: bool
    latency_ms: float
    cached: bool = False
    error: Optional[str] = None


def _build_redis_client() -> Optional[redis.Redis]:
    """Build the exact-cache Redis client from the same settings.redis_url the
    rest of the backend uses (see services/cache/redis_adapter.py).

    redis.from_url() connects lazily -- no socket I/O happens here, so this
    never blocks the event loop. A bad URL (the only way construction itself
    can fail) degrades to no cache rather than a 500; a reachable-but-down
    server surfaces on the first real .get()/.set() call inside
    FirstPersonPipeline, which already catches and logs (Redis Degradation
    invariant, root CLAUDE.md SPOF policy).
    """
    try:
        return redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
        )
    except Exception as e:
        logger.warning(f"[FirstPersonRoute] Redis client construction failed; exact cache disabled: {e}")
        return None


@lru_cache(maxsize=2)
def _pipeline(collection: str, serene_mind: Any) -> FirstPersonPipeline:
    """One pipeline per process: reuses the container's crisis engine and loads
    the calibration profile once. ponytail: a new profile file needs a restart."""
    return FirstPersonPipeline(
        store=FirstPersonStore(collection=collection),
        redis_client=_build_redis_client(),
        serene_mind_engine=serene_mind,
    )


@router.post("/first-person/query", response_model=FirstPersonQueryResponse)
@limiter.limit(settings.chat_rate_limit)
async def query_first_person_teaching(
    req: FirstPersonQueryRequest,
    request: Request,
    container: ServiceContainer = Depends(get_container_async),
) -> FirstPersonQueryResponse:
    """
    Query first-person verbatim recordings of Sri Preethaji and Sri Krishnaji.
    Returns exact timestamped pointers to authentic teacher discourse.
    """
    if not getattr(settings, "first_person_route_enabled", False) or getattr(
        settings, "first_person_mode", "disabled"
    ) == "disabled":
        raise HTTPException(
            status_code=404,
            detail="First-person verbatim mode is currently disabled.",
        )

    try:
        encoded = await container.embedding.encode_single_full_async(req.query)
    except Exception as e:
        logger.error(f"[FirstPersonRoute] Failed to embed query: {e}")
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from None

    dense_vec = encoded["dense"]
    raw_sparse = encoded.get("sparse") or {}
    sparse_vec = (
        {"indices": list(raw_sparse.keys()), "values": list(raw_sparse.values())}
        if raw_sparse
        else None
    )

    pipeline = _pipeline(settings.first_person_collection, getattr(container, "serene_mind", None))

    try:
        result = await asyncio.to_thread(
            pipeline.execute,
            query=req.query,
            query_dense_vector=dense_vec,
            query_sparse_vector=sparse_vec,
            teacher_id=req.teacher_id,
            max_clips=req.max_clips,
        )
    except Exception as e:
        # Anything that escapes the pipeline's own try/except (e.g. a
        # missing/unbuilt Qdrant collection) never leaks exception text.
        logger.error(f"[FirstPersonRoute] Pipeline execution failed: {e}")
        raise HTTPException(status_code=503, detail="First-person retrieval unavailable") from None

    if result.status == "error":
        # The pipeline already logged the real cause (e.g. Qdrant collection
        # not found) internally; the client only sees an honest 503.
        raise HTTPException(status_code=503, detail="First-person retrieval unavailable")

    return FirstPersonQueryResponse(**result.to_dict())
