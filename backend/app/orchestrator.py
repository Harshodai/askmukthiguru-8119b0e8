"""Mukthi Guru — Chat Request Orchestrator (thin wrapper)

Design Patterns:
  - Facade: Delegates all pipeline logic to PipelineCoordinator
  - Telemetry: Adds background trace logging after coordinator result
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import asdict
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, Request

from app.coalescer import build_coalescer
from app.config import settings
from app.dependencies import ServiceContainer
from app.grounding import grounding_state_for
from app.pipeline import PipelineCoordinator
from app.release_manifest import get_release_manifest
from app.schemas import ChatRequest, ChatResponse
from app.security_utils import is_benchmark_request
from app.telemetry_sink import SupabaseTelemetrySink
from rag.memory import normalize_session_id

logger = logging.getLogger(__name__)

# Module-level coalescer for concurrent RAG pipeline deduplication
_coalescer = build_coalescer(redis_url=getattr(settings, "redis_url", None), ttl=60.0)


class ChatRequestOrchestrator:
    """Thin orchestrator that delegates pipeline work to PipelineCoordinator."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container
        self.coordinator = PipelineCoordinator(container)
        self.telemetry_sink = SupabaseTelemetrySink()

    async def orchestrate(
        self,
        request: Request,
        chat_body: ChatRequest,
        background_tasks: BackgroundTasks,
        user: dict,
    ) -> ChatResponse:
        """Execute full pipeline and log telemetry."""
        user_msg = chat_body.user_message.strip()
        preferred_lang = chat_body.language or "en"
        user_id = user.get("id", "anonymous") if user else "anonymous"
        session_id = normalize_session_id(chat_body.session_id, user_id)
        assistant_slug = chat_body.assistant.slug if chat_body.assistant else None

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        if len(user_msg) > settings.max_input_length:
            raise HTTPException(
                status_code=400,
                detail=f"Message too long. Please keep it under {settings.max_input_length} characters.",
            )

        is_benchmark = is_benchmark_request(request)

        # Coalesce identical concurrent RAG pipelines (e.g. double-submit) to avoid
        # redundant LLM calls. Scoped to user+session so two different users never
        # share a personalized result, and hashed with sha256 (not hash()) since
        # hash() is randomized per-process and would break cross-pod dedup.
        assistant_tag = assistant_slug or "default"
        _msg_digest = hashlib.sha256(user_msg.encode("utf-8")).hexdigest()[:16]
        _manifest = get_release_manifest()
        _coalesce_key = f"rag:v3:{_manifest.release_id}:{_manifest.policy_version}:{preferred_lang}:{assistant_tag}:{user_id}:{session_id}:{_msg_digest}"

        async def _run_pipeline():
            return await self.coordinator.execute(
                user_msg=user_msg,
                preferred_lang=preferred_lang,
                chat_body=chat_body,
                meditation_step=chat_body.meditation_step,
                session_id=chat_body.session_id,
                user=user,
                is_benchmark=is_benchmark,
            )

        try:
            result = (
                await _run_pipeline()
                if chat_body.incognito
                else await _coalescer.get_or_run(_coalesce_key, _run_pipeline)
            )
        except TimeoutError:
            logger.error(f"Pipeline timeout for user {user_id}: message='{user_msg[:60]}...'")
            raise HTTPException(
                status_code=504,
                detail="The Guru took too long to respond. Please try again.",
            )

        if not chat_body.incognito:
            # Content-bearing telemetry is disabled for ephemeral chats.
            background_tasks.add_task(
                self._log_telemetry,
                result=result,
                user_id=user_id,
                session_id=session_id,
                user_msg=user_msg,
                assistant_slug=assistant_slug,
            )

            # Increment turn counter for batched layered memory processing.
            background_tasks.add_task(
                _increment_turn_counter,
                user_id,
            )

        response_grounding_state = grounding_state_for(result)
        logger.info(
            "CHAT_STAGE_TIMING trace_id=%s total_ms=%s node_timings=%s cache_hit=%s "
            "query_tier=%s grounding_state=%s provider=%s",
            result.trace_id,
            result.latency_ms,
            result.node_timings or {},
            bool(result.cache_hit),
            result.query_tier or "unknown",
            response_grounding_state,
            result.model_provider or "unknown",
        )

        return ChatResponse(
            response=result.final_answer,
            intent=result.intent,
            meditation_step=result.meditation_step,
            citations=_coerce_citations(result.citations),
            blocked=result.blocked,
            block_reason=result.block_reason,
            trace_id=result.trace_id,
            latency_ms=result.latency_ms,
            model_used=result.model_used,
            model_provider=result.model_provider,
            route_decision=result.route_decision,
            query_tier=result.query_tier,
            cache_hit=result.cache_hit,
            proactive_serene_mind=result.proactive_serene_mind,
            faithfulness_score=result.faithfulness_score,
            hallucination_flag=result.hallucination_flag,
            verification=result.verification,
            node_timings=result.node_timings,
            audio_url=result.audio_url,
            kg_concept_nodes=result.kg_concept_nodes,
            daily_practice_card=result.daily_practice_card,
            live_logistics_events=result.live_logistics_events,
            answer_evidence=(
                None if result.answer_evidence is None else asdict(result.answer_evidence)
            ),
            guidance_plan=(None if result.guidance_plan is None else asdict(result.guidance_plan)),
            grounding_state=response_grounding_state,
            release_manifest=result.release_manifest or get_release_manifest().to_dict(),
            provenance_manifest=_provenance_manifest_for_result(result),
        )

    async def _log_telemetry(
        self,
        result,
        user_id: str,
        session_id: str,
        user_msg: str,
        assistant_slug: Optional[str] = None,
    ) -> None:
        """Log query trace to telemetry sink."""
        try:
            await self.telemetry_sink.log_query_trace(
                query_id=result.trace_id,
                session_id=session_id,
                user_id=user_id,
                query_text=user_msg,
                model=result.model_used or "unknown",
                latency_ms=result.latency_ms,
                status="ok" if result.intent != "ERROR" else "error",
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                response_text=result.final_answer,
                citations=result.citations,
                faithfulness=result.faithfulness_score,
                answer_relevancy=result.answer_relevancy,
                context_precision=result.context_precision,
                context_recall=result.context_recall,
                hallucination_flag=result.hallucination_flag,
                confidence_score=result.confidence_score,
                judge_reasoning=result.judge_reasoning,
                retrieval_metadata=result.retrieval_metadata,
                spans=result.spans,
                trigger_events=result.trigger_events,
                safety_events=result.safety_events,
                provider=result.model_provider,
                route_decision=result.route_decision,
                cache_hit=result.cache_hit,
                tokens_per_second=round(
                    max(1, len(result.final_answer.split())) / max(result.latency_ms / 1000, 0.001),
                    2,
                )
                if result.latency_ms
                else 0.0,
                evaluation_trace=result.evaluation_trace,
                assistant_slug=assistant_slug,
                citations_verified=result.citations_verified,
                orphan_citations_stripped=result.orphan_citations_stripped,
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-fatal): {e}")


# ── Job Queue Worker Factory ─────────────────────────────────────────────


async def _release_anon_quota(container, user: dict, reservation_id: str | None) -> None:
    """Give a queued job's quota reservation back when the job failed."""
    if not reservation_id:
        return
    try:
        await container.anon_quota_service.release(user, reservation_id)
    except Exception as exc:
        logger.debug(f"anon quota release failed (non-fatal): {exc}")


async def _claim_anon_quota(container, user: dict, reservation_id: str | None) -> None:
    """Commit a queued job's quota reservation when the job succeeded."""
    if not reservation_id:
        return
    try:
        await container.anon_quota_service.claim(user, reservation_id)
    except Exception as exc:
        logger.debug(f"anon quota claim failed (non-fatal): {exc}")


async def queue_worker_factory(
    request_data: dict,
    is_stream: bool,
    job_id: str,
) -> dict:
    """Called by JobQueueService workers to execute pipeline jobs.

    Reconstructs orchestrator state from serialized request_data.
    """
    from app.dependencies import get_container
    from app.schemas import ChatRequest

    container = get_container()
    user = request_data.get("user", {})
    chat_body = ChatRequest(**request_data.get("chat_body", {}))
    # Reservation made atomically at the endpoint gate; committed on success
    # (claim) and released when the job fails or is cancelled.
    quota_reservation_id = request_data.get("quota_reservation_id")

    if is_stream:
        from app.stream_orchestrator import ChatStreamRequestOrchestrator

        orch = ChatStreamRequestOrchestrator(container)
        stream_queue: asyncio.Queue = asyncio.Queue()
        pipeline_task = asyncio.create_task(
            orch.coordinator.execute(
                user_msg=chat_body.user_message.strip(),
                preferred_lang=chat_body.language or "en",
                chat_body=chat_body,
                meditation_step=chat_body.meditation_step,
                session_id=chat_body.session_id,
                user=user,
                is_benchmark=False,
                stream_queue=stream_queue,
            )
        )
        drain_task = asyncio.create_task(
            _drain_stream_to_redis(stream_queue, pipeline_task, job_id, container)
        )
        try:
            await pipeline_task
            await drain_task
            await _claim_anon_quota(container, user, quota_reservation_id)
        except Exception as _e:
            logger.error(f"Queue worker: job {job_id} stream pipeline failed: {_e}")
            await _release_anon_quota(container, user, quota_reservation_id)
            try:
                await drain_task
            except Exception:
                # drain_task typically fails with the same root cause; suppress
                # its exception so the original failure is what propagates.
                logger.debug("Queue worker: drain task also failed for %s", job_id, exc_info=True)
            raise
        return {"job_id": job_id, "status": "streamed"}

    orch = ChatRequestOrchestrator(container)
    try:
        from unittest.mock import MagicMock

        fake_request = MagicMock()
        fake_request.headers.get.return_value = None
        from fastapi import BackgroundTasks

        fake_bg = BackgroundTasks()
        response = await orch.orchestrate(fake_request, chat_body, fake_bg, user)
        await fake_bg()
        await _claim_anon_quota(container, user, quota_reservation_id)
        return _response_to_dict(response)
    except HTTPException as exc:
        await _release_anon_quota(container, user, quota_reservation_id)
        return {"error": exc.detail, "status_code": exc.status_code}
    except Exception as exc:
        logger.error(f"Queue worker: job {job_id} failed: {exc}")
        await _release_anon_quota(container, user, quota_reservation_id)
        return {"error": str(exc)}


async def _drain_stream_to_redis(
    stream_queue: asyncio.Queue,
    pipeline_task: asyncio.Task,
    job_id: str,
    container: ServiceContainer,
) -> None:
    """Drain SSE events from stream_queue into Redis Stream, best-effort.

    The pipeline and drain tasks run concurrently. A completed pipeline can make
    ``stream_queue.empty()`` true for a short interval before its final result is
    observable through ``Task.result()``. Never call ``result()`` from this
    cleanup path without first awaiting the task; otherwise a successful answer
    can be downgraded to a misleading ``Stream drain failed ... Result is not
    set`` warning and the queued SSE client may miss its terminal ``done`` event.
    """
    import json

    r = None
    try:
        if container.job_queue:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.redis_url, decode_responses=True)
        stream_key = f"job:stream:{job_id}:events"
        HEARTBEAT_INTERVAL = 5.0
        while True:
            if pipeline_task.done() and stream_queue.empty():
                break
            try:
                if pipeline_task.done():
                    item = stream_queue.get_nowait()
                else:
                    get_task = asyncio.create_task(stream_queue.get())
                    heartbeat = asyncio.create_task(asyncio.sleep(HEARTBEAT_INTERVAL))
                    done, pending = await asyncio.wait(
                        [pipeline_task, get_task, heartbeat],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if get_task in done:
                        heartbeat.cancel()
                        item = get_task.result()
                    else:
                        get_task.cancel()
                        heartbeat.cancel()
                        try:
                            await get_task
                        except asyncio.CancelledError:
                            pass
                        # A heartbeat is only a progress tick. Keep waiting when
                        # there are no events yet; exiting here could skip tokens
                        # and race the pipeline's terminal result publication.
                        if stream_queue.empty() and not pipeline_task.done():
                            continue
                        if stream_queue.empty():
                            break
                        item = stream_queue.get_nowait()
            except (asyncio.QueueEmpty, ValueError):
                if not pipeline_task.done():
                    continue
                break
            if r:
                payload = json.dumps(item, default=str) if isinstance(item, dict) else item
                try:
                    await r.xadd(stream_key, {"data": payload}, maxlen=1000)
                except Exception as _e:
                    logger.debug("[orchestrator cleanup] suppressed non-critical error: %s", _e)

        if r:
            try:
                # Awaiting is idempotent for an already-finished task and closes
                # the completion-vs-drain race for tasks finishing at this point.
                try:
                    pipeline_result = await pipeline_task
                except asyncio.CancelledError:
                    completion_payload = "__ERROR__"
                except Exception:
                    completion_payload = "__ERROR__"
                else:
                    # Queued workers drain raw generation chunks directly and
                    # therefore do not pass through ChatStreamRequestOrchestrator
                    # (which emits the authoritative normalized final event).
                    # Always persist that final event here, including cache hits
                    # where the queue contains no text chunks at all.
                    final_payload = json.dumps(
                        {
                            "event": "final",
                            "data": json.dumps(
                                getattr(pipeline_result, "final_answer", "") or "",
                                ensure_ascii=False,
                            ),
                        },
                        ensure_ascii=False,
                    )
                    await r.xadd(stream_key, {"data": final_payload}, maxlen=1000)
                    completion_payload = json.dumps(
                        {
                            "event": "done",
                            "data": json.dumps(_stream_done_metadata(pipeline_result)),
                        },
                        ensure_ascii=False,
                    )
                await r.xadd(stream_key, {"data": completion_payload}, maxlen=1000)
                await r.expire(stream_key, max(600, settings.queue_job_ttl))
            finally:
                await r.close()
    except Exception as exc:
        logger.warning(f"Stream drain failed for {job_id}: {exc}")


def _response_to_dict(response) -> dict:
    """Convert ChatResponse to a JSON-serializable dict."""
    import dataclasses

    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    if dataclasses.is_dataclass(response):
        return dataclasses.asdict(response)
    return {"response": str(response)}


def _coerce_citations(citations) -> list[dict]:
    """Coerce citation objects to the `{"url": str, "title": str | None}` shape
    ChatResponse.citations (list[Citation]) expects.

    The graph's main path (`_sanitize_citations` in rag/nodes/generation.py)
    already emits this shape with a real title resolved from the retrieved
    doc's Qdrant payload. This stays defensive for earlier-exit branches
    (e.g. citation_extractor's raw {doc_id, quote, source_url, title, ...}
    dicts, or a bare url string) that can still reach this boundary.

    Entries with no resolvable http(s) URL are dropped — the schema requires
    one, matching the graph's own citation contract.
    """
    if not citations:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for c in citations:
        if isinstance(c, dict):
            source_url = c.get("source_url")
            url = c.get("url")
            title = c.get("title")
            valid_url: str | None = None
            for cand in (source_url, url):
                if cand and str(cand).startswith(("http://", "https://")):
                    valid_url = str(cand)
                    break
        else:
            valid_url = str(c) if str(c or "").startswith(("http://", "https://")) else None
            title = None
        if not valid_url or valid_url in seen:
            continue
        seen.add(valid_url)
        out.append({"url": valid_url, "title": str(title).strip() if title else None})
    return out


_PUBLIC_PROVENANCE_FIELDS = frozenset(
    {
        "text",
        "band",
        "score",
        "source_url",
        "source_segment_id",
        "entity_ids",
        "relation",
        "hop",
        "confidence",
        "ontology_version",
        "rights_status",
        "channel",
        "corroborated",
    }
)


def _public_provenance_context(context: dict) -> dict:
    """Return only bounded, user-visible provenance fields.

    Provenance is intentionally useful in the UI, but it is not a general state
    dump. Keep this projection allowlisted so a future retrieval or memory
    adapter cannot accidentally stream ``memory_context``, attachment text,
    prompts, safety state, or other private fields to the browser.
    """
    public_bands = {}
    bands = context.get("bands")
    if isinstance(bands, dict):
        for band, items in bands.items():
            if not isinstance(band, str) or not isinstance(items, list):
                continue
            public_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                public_items.append(
                    {key: value for key, value in item.items() if key in _PUBLIC_PROVENANCE_FIELDS}
                )
            public_bands[band] = public_items
    entities = context.get("entities_touched", [])
    if not isinstance(entities, list):
        entities = []
    return {
        "bands": public_bands,
        "total_tokens": context.get("total_tokens", 0),
        "evidence_count": context.get("evidence_count", 0),
        "entities_touched": [str(value) for value in entities if value][:64],
    }


def _provenance_manifest_for_result(result) -> dict | None:
    """Project retrieval evidence into a public compliance manifest contract."""
    context = getattr(result, "provenance_context", None)
    if not isinstance(context, dict) or not context.get("evidence_count"):
        return None
    public_context = _public_provenance_context(context)
    return {
        "manifest_id": getattr(result, "trace_id", None),
        "model_name": getattr(result, "model_used", None),
        "model_provider": getattr(result, "model_provider", None),
        "metadata": {
            "provenance_context": public_context,
            "evidence_count": public_context.get("evidence_count"),
            "entities_touched": public_context.get("entities_touched", []),
        },
    }


def _stream_done_metadata(result) -> dict:
    """Return the JSON-safe completion metadata shared by direct and queued SSE."""
    answer_evidence = getattr(result, "answer_evidence", None)
    guidance_plan = getattr(result, "guidance_plan", None)
    return {
        "intent": result.intent,
        "citations": _coerce_citations(result.citations),
        "meditation_step": result.meditation_step,
        "proactive_serene_mind": result.proactive_serene_mind,
        "trace_id": result.trace_id,
        "latency_ms": result.latency_ms,
        "model_used": result.model_used,
        "model_provider": result.model_provider,
        "route_decision": result.route_decision,
        "query_tier": result.query_tier,
        "cache_hit": result.cache_hit,
        "faithfulness_score": result.faithfulness_score,
        "hallucination_flag": result.hallucination_flag,
        "follow_up_suggestions": result.follow_up_suggestions,
        "confidence_score": result.confidence_score,
        "citations_verified": result.citations_verified,
        "orphan_citations_stripped": result.orphan_citations_stripped,
        "live_logistics_events": getattr(result, "live_logistics_events", []),
        "answer_evidence": None if answer_evidence is None else asdict(answer_evidence),
        "guidance_plan": None if guidance_plan is None else asdict(guidance_plan),
        "grounding_state": grounding_state_for(result),
        "verification": getattr(result, "verification", None),
        "release_manifest": getattr(result, "release_manifest", None)
        or get_release_manifest().to_dict(),
        "provenance_manifest": _provenance_manifest_for_result(result),
    }


async def _increment_turn_counter(user_id: str) -> None:
    """Increment the Redis turn counter for batched layered memory processing."""
    import json
    import time

    try:
        import redis.asyncio as aredis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = aredis.from_url(redis_url, decode_responses=True)
        key = f"turn_counter:{user_id}"
        data = await r.get(key)
        if data:
            parsed = json.loads(data)
            parsed["count"] = parsed.get("count", 0) + 1
            parsed["last_ts"] = time.time()
        else:
            parsed = {"count": 1, "last_ts": time.time()}
        await r.set(key, json.dumps(parsed), ex=7200)
        await r.aclose()
    except Exception:
        pass  # non-critical
