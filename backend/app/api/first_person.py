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
from services.auth_service import require_aal2
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
    cache_bypass: bool = Field(
        False,
        description="Evaluation control: skip the exact-answer cache read and write for "
        "this request (same meaning as ChatRequest.cache_bypass).",
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
    audio_playback_clip: Optional[dict[str, Any]] = None
    detected_concepts: list[str] = Field(default_factory=list)
    atma_vichara_inquiry: Optional[str] = None
    practice_recommendation: Optional[dict[str, Any]] = None


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
@limiter.limit(getattr(settings, "first_person_rate_limit", "120/minute"))
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

    # No cache read here: execute() reads the exact cache only AFTER its crisis
    # pre-check and topic rail. A read here, before them, served a cached clip
    # to a question a newer safety pattern would now redirect (2026-10-05).
    req_lang = (req.language or "en").strip().lower().split("-")[0]

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

    try:
        result = await asyncio.to_thread(
            pipeline.execute,
            query=req.query,
            query_dense_vector=dense_vec,
            query_sparse_vector=sparse_vec,
            teacher_id=req.teacher_id,
            max_clips=req.max_clips,
            retrieval_query=retrieval_query,
            language=req_lang,
            cache_bypass=req.cache_bypass,
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
    if payload.get("citations") and not await _output_rail_passes(container, result.answer_text):
        # Same output rail the chat bridge applies before serving a clip. A
        # blocked, missing or crashing rail abstains: no clip is served unchecked.
        payload = FirstPersonQueryResponse(
            answer_text=_UNVERIFIED_ABSTAIN_TEXT,
            citations=[],
            status="abstained",
            is_direct_answer=False,
            latency_ms=result.latency_ms,
            cached=result.cached,
        ).model_dump()
    language = (req.language or "en").lower().split("-")[0]
    if language != "en" and payload["citations"]:
        # Copies: the pipeline's cached citation dicts must stay language-free.
        payload["citations"] = [dict(c) for c in payload["citations"]]
        await _add_glosses(payload["citations"], language, container)

    return FirstPersonQueryResponse(**payload)


_UNVERIFIED_ABSTAIN_TEXT = "No verified first-person discourse found for this question."


async def _output_rail_passes(container: Any, text: str) -> bool:
    """True only when the output rail ran and did not block. Fails closed."""
    rail = getattr(container, "guardrails", None)
    if rail is None:
        logger.warning("[FirstPersonRoute] No output rail available; abstaining.")
        return False
    try:
        verdict = await rail.check_output(text or "")
    except Exception as e:  # noqa: BLE001 -- a crashed rail is not a passed rail
        logger.warning(f"[FirstPersonRoute] Output rail failed; abstaining: {e}")
        return False
    if not isinstance(verdict, dict) or verdict.get("blocked"):
        logger.info(
            "[FirstPersonRoute] Output rail blocked a clip answer (reason=%s).",
            verdict.get("reason") if isinstance(verdict, dict) else "malformed verdict",
        )
        return False
    return True


async def _require_admin(user: dict = Depends(require_aal2)) -> dict:
    """Ingest enqueues work that writes to Qdrant and asserts rights clearance, so
    it is admin-only (same contract as app/api/admin.py), never anonymous."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    allowlist = settings.admin_user_ids_list
    if allowlist and user.get("id") not in allowlist:
        raise HTTPException(status_code=403, detail="Admin access required (not allowlisted)")
    return user


class FirstPersonIngestRequest(BaseModel):
    video_url: str = Field(
        ..., min_length=5, max_length=500, description="YouTube URL or direct video ID"
    )
    teacher_id: Optional[str] = Field("both", description="'preethaji', 'krishnaji', or 'both'")
    rights_cleared: bool = Field(True, description="Whether discourse is rights-cleared")
    collection: Optional[str] = Field(None, description="Target Qdrant collection")


class FirstPersonIngestResponse(BaseModel):
    job_id: str
    video_url: str
    status: str
    message: str


class FirstPersonIngestStatusResponse(BaseModel):
    job_id: str
    video_url: Optional[str] = None
    status: str
    stage: Optional[str] = None
    progress_pct: int = 0
    clips_indexed: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.post(
    "/first-person/ingest/video",
    response_model=FirstPersonIngestResponse,
    status_code=202,
    summary="Enqueue video for distributed First-Person audio ingestion",
)
@limiter.limit("10/minute")
async def enqueue_first_person_video_ingest(
    request: Request,
    req: FirstPersonIngestRequest,
    _admin: dict = Depends(_require_admin),
) -> FirstPersonIngestResponse:
    """Enqueues video transcription and indexing to Celery worker off the HTTP path."""
    import uuid

    from services.first_person_ingest_service import (
        FPJobStage,
        FPJobStatus,
        extract_youtube_video_id,
        record_fp_job_progress,
    )
    from tasks.ingest_tasks import ingest_first_person_video_task

    video_id = extract_youtube_video_id(req.video_url)
    if not video_id:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid YouTube URL or video ID: {req.video_url}",
        )

    job_id = f"fp_ingest_{uuid.uuid4().hex[:12]}"
    redis_client = _build_redis_client()

    record_fp_job_progress(
        redis_client=redis_client,
        job_id=job_id,
        status=FPJobStatus.QUEUED,
        progress_pct=0,
        stage=FPJobStage.QUEUED,
        video_url=req.video_url,
    )

    try:
        ingest_first_person_video_task.apply_async(
            kwargs={
                "video_url": req.video_url,
                "job_id": job_id,
                "teacher_id": req.teacher_id,
                "collection": req.collection,
                "rights_cleared": req.rights_cleared,
            },
            queue="ingestion",
        )
    except Exception as exc:
        logger.error(f"[FirstPersonRoute] Failed to dispatch Celery ingest task: {exc}")
        record_fp_job_progress(
            redis_client=redis_client,
            job_id=job_id,
            status=FPJobStatus.FAILED,
            progress_pct=0,
            stage=FPJobStage.FAILED,
            error_message=f"Failed to enqueue task: {exc}",
            video_url=req.video_url,
        )
        raise HTTPException(
            status_code=503,
            detail="Ingestion queue temporarily unavailable",
        ) from exc

    return FirstPersonIngestResponse(
        job_id=job_id,
        video_url=req.video_url,
        status="queued",
        message="Video ingestion task enqueued to distributed Celery worker",
    )


@router.get(
    "/first-person/ingest/status/{job_id}",
    response_model=FirstPersonIngestStatusResponse,
    summary="Poll distributed ingestion job status",
)
async def get_first_person_ingest_status(
    job_id: str,
    _admin: dict = Depends(_require_admin),
) -> FirstPersonIngestStatusResponse:
    """Poll progress of a background first-person video ingestion task."""
    from services.first_person_ingest_service import get_fp_job_progress

    redis_client = _build_redis_client()
    data = get_fp_job_progress(redis_client, job_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found")

    return FirstPersonIngestStatusResponse(
        job_id=data.get("job_id", job_id),
        video_url=data.get("video_url"),
        status=data.get("status", "unknown"),
        stage=data.get("stage"),
        progress_pct=data.get("progress_pct", 0),
        clips_indexed=data.get("clips_indexed", 0),
        error_message=data.get("error_message") or None,
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )
