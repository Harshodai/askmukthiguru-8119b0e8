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
from app.language_utils import guardrail_text_for
from app.orchestrator_utils import _translate_cached
from services.first_person_pipeline import FirstPersonPipeline
from services.first_person_store import FirstPersonStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["First-Person Verbatim Teachings"])


class FirstPersonQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="The seeker question")
    teacher_id: Optional[str] = Field("both", description="'preethaji', 'krishnaji', or 'both'")
    max_clips: int = Field(
        3, ge=1, le=5, description="Max verified clips to return (max 1 per video)"
    )
    language: Optional[str] = Field(
        None,
        max_length=10,
        description="Seeker's selected language (e.g. 'hi'). When not English, each citation "
        "gets a 'translated_text' gloss; 'verbatim_text' always stays the teacher's own words.",
    )


class FirstPersonQueryResponse(BaseModel):
    answer_text: str
    citations: list[dict[str, Any]]
    status: str
    is_direct_answer: bool
    latency_ms: float
    cached: bool = False
    error: Optional[str] = None
    # Phase 2 answerability gate verdict: 'yes' | 'no' | 'indeterminate';
    # None when the gate did not run (flag off, weak match, zero-clip abstention).
    answerability: Optional[str] = None


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
        logger.warning(
            f"[FirstPersonRoute] Redis client construction failed; exact cache disabled: {e}"
        )
        return None


def _make_rerank_fn(embedding: Any, loop: asyncio.AbstractEventLoop, timeout_s: float = 5.0):
    """Sync (query, texts) -> scores adapter over the chat path's async cross-encoder.

    The pipeline runs in a worker thread (asyncio.to_thread), so the coroutine is
    scheduled back onto the request loop rather than a new one."""

    def rerank(query: str, texts: list[str]) -> list[float]:
        docs = [{"text": t} for t in texts]
        asyncio.run_coroutine_threadsafe(
            embedding.rerank(query, docs, top_k=len(docs), min_score=0.0), loop
        ).result(timeout=timeout_s)
        return [d["rerank_score"] for d in docs]  # rerank() scores the dicts in place

    return rerank


@lru_cache(maxsize=4)
def _pipeline(
    collection: str,
    serene_mind: Any,
    rerank_embedding: Any = None,
    llm_service: Any = None,
) -> FirstPersonPipeline:
    """One pipeline per process: reuses the container's crisis engine and loads
    the calibration profile once. ponytail: a new profile file needs a restart.
    First call must come from the request loop when a reranker is passed (it
    binds to that loop). The gate's loop capture below degrades to its
    persistent fallback when constructed outside any loop (tests, sync tooling)
    — D1 §6.2: `asyncio.get_running_loop()` at construction time made the
    factory uncallable without a running loop, breaking 2 first-person-route
    tests, while `_answerability_check` already accepts `request_loop=None`
    (persistent gate loop)."""
    rerank_fn = (
        _make_rerank_fn(rerank_embedding, asyncio.get_running_loop())
        if rerank_embedding is not None
        else None
    )
    # Prod path (async route): loop captured — the answerability gate schedules
    # its LLM call here from the worker thread, keeping the shared Redis
    # limiter/budget-ledger clients on their birth loop. No running loop →
    # None → _answerability_check's documented persistent-loop fallback.
    try:
        gate_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        gate_loop = None
    return FirstPersonPipeline(
        store=FirstPersonStore(collection=collection),
        redis_client=_build_redis_client(),
        serene_mind_engine=serene_mind,
        rerank_fn=rerank_fn,
        llm_service=llm_service,
        llm_loop=gate_loop,
    )


async def _english_query(query: str, container: ServiceContainer) -> str:
    """The question in English, for embedding against English transcripts.

    Reuses the chat path's translate-to-English helper (detection + cache). On a
    translation timeout the raw text is used: BGE-M3 is multilingual, so this
    degrades ranking quality, not safety (safety checks see the raw text too)."""
    try:
        return await asyncio.wait_for(
            guardrail_text_for(query, getattr(container, "translation", None), "en"),
            timeout=settings.first_person_translation_timeout_s,
        )
    except TimeoutError:
        logger.warning(
            "[FirstPersonRoute] Query translation timed out; embedding the raw question."
        )
        return query


async def _add_glosses(
    citations: list[dict[str, Any]], language: str, container: ServiceContainer
) -> None:
    """Attach a 'translated_text' gloss per citation. 'verbatim_text' is never touched;
    a gloss that fails is omitted, never faked."""
    service = getattr(container, "translation", None)
    if service is None:
        logger.warning("[FirstPersonRoute] No translation service; glosses omitted.")
        return
    results = await asyncio.gather(
        *(
            _translate_cached(
                service,
                text=c["verbatim_text"],
                source_lang="en",
                target_lang=language,
                timeout=settings.first_person_translation_timeout_s,
            )
            for c in citations
        ),
        return_exceptions=True,
    )
    for cit, res in zip(citations, results):
        if isinstance(res, str) and res.strip() and res.strip() != cit["verbatim_text"].strip():
            cit["translated_text"] = res.strip()
            cit["translated_language"] = language
        elif isinstance(res, BaseException):
            logger.warning(f"[FirstPersonRoute] Gloss translation failed: {res}")


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
    if (
        not getattr(settings, "first_person_route_enabled", False)
        or getattr(settings, "first_person_mode", "disabled") == "disabled"
    ):
        raise HTTPException(
            status_code=404,
            detail="First-person verbatim mode is currently disabled.",
        )

    retrieval_query = await _english_query(req.query, container)

    try:
        encoded = await container.embedding.encode_single_full_async(retrieval_query)
    except Exception as e:
        logger.error(f"[FirstPersonRoute] Failed to embed query: {e}")
        raise HTTPException(status_code=503, detail="Embedding service unavailable") from None

    dense_vec = encoded["dense"]
    raw_sparse = encoded.get("sparse") or {}
    sparse_vec = (
        {
            "indices": [int(k) for k in raw_sparse.keys()],
            "values": [float(v) for v in raw_sparse.values()],
        }
        if raw_sparse
        else None
    )

    llm_service = (
        getattr(container, "openrouter", None)
        or getattr(container, "nim", None)
        or getattr(container, "ollama", None)
    )

    pipeline = _pipeline(
        settings.first_person_collection,
        getattr(container, "serene_mind", None),
        container.embedding if settings.first_person_rerank_enabled else None,
        llm_service,
    )

    try:
        result = await asyncio.to_thread(
            pipeline.execute,
            query=req.query,
            query_dense_vector=dense_vec,
            query_sparse_vector=sparse_vec,
            teacher_id=req.teacher_id,
            max_clips=req.max_clips,
            retrieval_query=retrieval_query,
            language=req.language or "en",
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

    payload = result.to_dict()
    language = (req.language or "en").lower().split("-")[0]
    if language != "en" and payload["citations"]:
        # Copies: the pipeline's cached citation dicts must stay language-free.
        payload["citations"] = [dict(c) for c in payload["citations"]]
        await _add_glosses(payload["citations"], language, container)

    return FirstPersonQueryResponse(**payload)
