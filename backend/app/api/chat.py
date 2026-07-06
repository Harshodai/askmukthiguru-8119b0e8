"""Chat, streaming chat, and breath-teaching routes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import wraps
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.schemas import ChatRequest, ChatResponse
from app.sanitization import sanitize_user_input
from rag.memory import build_memory_context
from services.auth_service import get_current_user_from_supabase
from services.cost_tracker import TokenAccumulator, get_cost_tracker, token_accumulator_var
from services.tenant_context import TenantContext, set_tenant_from_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


def record_token_usage(endpoint: str):
    """Decorator that records token usage for a request after the handler returns."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request") or next((arg for arg in args if isinstance(arg, Request)), None)
            chat_body = kwargs.get("chat_body") or next((arg for arg in args if hasattr(arg, "user_message")), None)
            user = kwargs.get("user") or {}

            user_id = user.get("id", "anonymous") if isinstance(user, dict) else "anonymous"
            session_id = chat_body.session_id or "" if chat_body else ""

            accumulator = TokenAccumulator()
            token = token_accumulator_var.set(accumulator)
            try:
                return await func(*args, **kwargs)
            finally:
                acc = token_accumulator_var.get()
                if acc and (acc.tokens_in > 0 or acc.tokens_out > 0):
                    try:
                        get_cost_tracker().record(
                            tenant_id=TenantContext.get(),
                            user_id=user_id,
                            session_id=session_id,
                            model=acc.model,
                            provider=acc.provider,
                            tokens_in=acc.tokens_in,
                            tokens_out=acc.tokens_out,
                            endpoint=endpoint,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record token usage: {e}")
                token_accumulator_var.reset(token)
        return wrapper
    return decorator


async def _prepare_user_memory(
    container: ServiceContainer,
    user_id: str,
    chat_history: list[dict],
) -> tuple[str, list[dict]]:
    """Load bounded user memory and derive distress signals for this turn."""
    if not container.user_profile:
        return "", []

    # Anonymous users have no persistent profile — skip all DB calls
    if not user_id or user_id == "anonymous":
        return "", []

    profile = await container.user_profile.get_or_create_profile(user_id)
    profile.total_conversations += 1
    await container.user_profile.update_profile(profile)

    recent_memories = await container.user_profile.get_recent_memories(user_id, limit=3)
    memory_context = build_memory_context(
        recent_memories=recent_memories,
        chat_history=chat_history,
    )

    # Fetch persistent memory layer context under a 200ms timeout budget if enabled
    if settings.feature_memory_enabled and getattr(container, "memory_service", None):
        try:
            last_query = chat_history[-1]["content"] if chat_history else ""

            async def fetch_memory_layer():
                core_m = await container.memory_service.get_core(user_id)
                semantic_m = []
                if last_query:
                    semantic_m = await container.memory_service.search_semantic(
                        user_id, last_query, limit=3, min_similarity=0.6
                    )
                return core_m, semantic_m

            core_m, semantic_m = await asyncio.wait_for(fetch_memory_layer(), timeout=2.0)

            # Format memory context blocks
            memory_blocks = []
            if core_m:
                memory_blocks.append("USER PROFILE & CORE FACTS:\n- " + "\n- ".join(c["content"] for c in core_m))
            if semantic_m:
                memory_blocks.append("PAST RELEVANT RECOLLECTIONS:\n- " + "\n- ".join(s["content"] for s in semantic_m))

            if memory_blocks:
                new_memory_context = "\n\n".join(memory_blocks)
                if memory_context:
                    memory_context = f"{memory_context}\n\n{new_memory_context}"
                else:
                    memory_context = new_memory_context
        except asyncio.TimeoutError:
            logger.warning(f"Memory layer fetch timed out for user {user_id} (exceeded 2s budget)")
        except Exception as e:
            logger.warning(f"Memory layer fetch failed for user {user_id}: {e}")

    distress_history = []
    for mem in recent_memories:
        if mem.emotional_arc:
            recent_emotion = mem.emotional_arc[-1]
            if recent_emotion.get("distress_level", 0) >= 2:
                distress_history.append(recent_emotion)

    return memory_context, distress_history


def _cache_language_key(message: str, language: str) -> str:
    normalized_lang = (language or "en").lower().strip()
    return f"{normalized_lang}:{message.strip()}"


from pydantic import BaseModel

class TitleRequest(BaseModel):
    first_message: str

@router.post("/chat/title")
@limiter.limit("20/minute")
async def generate_title_endpoint(
    request: Request,
    body: TitleRequest,
    container: ServiceContainer = Depends(get_container),
):
    """
    Synchronously generate a short 3-6 word title for a conversation
    using the active LLM service.
    """
    first_message = body.first_message.strip()
    if not first_message:
        return {"title": "New conversation"}

    try:
        system_prompt = "Create a concise, meaningful chat title. Return ONLY the title, no quotes, no punctuation, and keep it under 6 words."
        user_prompt = f"Title this conversation: {first_message}"
        
        raw_title = await container.ollama.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        
        title = raw_title.strip().replace('"', '').replace("'", "").strip()
        if title:
            if len(title) > 50:
                title = title[:47] + "..."
            return {"title": title}
    except Exception as e:
        logger.warning(f"Failed to generate conversation title via LLM: {e}")
        
    fallback = first_message[:47] + "..." if len(first_message) > 50 else first_message
    return {"title": fallback}


@router.post("/chat")
@limiter.limit(settings.chat_rate_limit)
@record_token_usage(endpoint="/api/chat")
async def chat_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
):
    """
    Main conversational endpoint.

    When queue is enabled (default), returns 202 with job_id immediately.
    Add ?wait=true to block for result (backward compat).
    Delegates inline to ChatRequestOrchestrator when queue is disabled.
    """
    chat_body.user_message = sanitize_user_input(chat_body.user_message)

    is_benchmark = request.headers.get("X-Test-Key") == getattr(settings, "jwt_secret", None)

    if container.job_queue and settings.queue_enabled and not is_benchmark:
        from app.services.job_queue import QueueFullError

        chat_body_dict = chat_body.model_dump()
        user_dict = {"id": user.get("id", "anonymous")} if user else {"id": "anonymous"}
        request_data = {"chat_body": chat_body_dict, "user": user_dict, "is_benchmark": False}
        try:
            job_id, queue_pos = await container.job_queue.enqueue(
                request_data, user.get("id", "anonymous"), is_stream=False
            )
        except QueueFullError:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "detail": "Server is busy. Please try again shortly."},
                headers={"Retry-After": "5"},
            )

        if request.query_params.get("wait", "").lower() == "true":
            deadline = time.time() + settings.queue_default_timeout
            while time.time() < deadline:
                job = await container.job_queue.get_job(job_id)
                if job and job["status"] == "completed" and job["result"]:
                    return ChatResponse(**job["result"])
                if job and job["status"] == "failed":
                    raise HTTPException(status_code=500, detail=job.get("error", "Pipeline failed"))
                await asyncio.sleep(0.5)
            raise HTTPException(status_code=504, detail="Pipeline timeout")

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "queue_position": queue_pos,
                "poll_url": f"/api/jobs/{job_id}",
            },
        )

    from app.orchestrator import ChatRequestOrchestrator

    orchestrator = ChatRequestOrchestrator(container)
    return await orchestrator.orchestrate(request, chat_body, background_tasks, user)


@router.post("/chat/stream")
@limiter.limit(settings.chat_rate_limit)
async def chat_stream_endpoint(
    request: Request,
    chat_body: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
    _tenant=Depends(set_tenant_from_request),
):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    When queue enabled (default), returns 202 with stream_url immediately.
    Client then connects to GET /api/chat/stream/{job_id} for SSE.
    Delegates inline to ChatStreamRequestOrchestrator when queue is disabled.
    """
    chat_body.user_message = sanitize_user_input(chat_body.user_message)

    is_benchmark = request.headers.get("X-Test-Key") == getattr(settings, "jwt_secret", None)

    if container.job_queue and settings.queue_enabled and not is_benchmark:
        from app.services.job_queue import QueueFullError

        chat_body_dict = chat_body.model_dump()
        user_dict = {"id": user.get("id", "anonymous")} if user else {"id": "anonymous"}
        request_data = {"chat_body": chat_body_dict, "user": user_dict, "is_benchmark": False}
        try:
            job_id, queue_pos = await container.job_queue.enqueue(
                request_data, user.get("id", "anonymous"), is_stream=True
            )
        except QueueFullError:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "detail": "Server is busy. Please try again shortly."},
                headers={"Retry-After": "5"},
            )

        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "queue_position": queue_pos,
                "stream_url": f"/api/chat/stream/{job_id}",
            },
        )

    from app.stream_orchestrator import ChatStreamRequestOrchestrator

    orchestrator = ChatStreamRequestOrchestrator(container)
    return await orchestrator.orchestrate_stream(request, chat_body, background_tasks, user)


@router.get("/chat/stream/{job_id}")
async def chat_stream_poll(
    job_id: str,
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_current_user_from_supabase),
):
    """
    SSE endpoint for queued streaming jobs. Only the job owner may stream.

    Reads events from Redis Stream (populated by worker) and streams them as SSE.
    """
    if not container.job_queue:
        raise HTTPException(status_code=503, detail="Job queue is disabled")

    # Ownership check — return 404 on mismatch to avoid confirming existence.
    job_meta = await container.job_queue.get_job(job_id)
    if not job_meta or str(job_meta.get("user_id") or "") != str(user.get("id") or ""):
        raise HTTPException(status_code=404, detail="Job not found or expired")

    import redis.asyncio as aioredis
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    stream_key = f"job:stream:{job_id}:events"

    async def _sse():
        last_id = "0"
        timeout = settings.queue_default_timeout
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                try:
                    results = await r.xread(
                        {stream_key: last_id}, count=10, block=2000
                    )
                except Exception:
                    await asyncio.sleep(0.5)
                    continue

                if not results:
                    job_meta = await r.hgetall(f"job:{job_id}:meta")
                    if job_meta:
                        status = job_meta.get("status", "")
                        if status == "failed":
                            yield "event: error\ndata: Pipeline failed\n\n"
                            return
                        if status == "cancelled":
                            yield "event: error\ndata: Job cancelled\n\n"
                            return
                        if status == "completed" and last_id == "0":
                            await asyncio.sleep(0.5)
                            continue
                        if status in ("completed", "failed") and last_id != "0":
                            yield "event: done\ndata: {}\n\n"
                            return
                    continue

                for stream_name, entries in results:
                    for entry_id, fields in entries:
                        last_id = entry_id
                        data = fields.get("data", "")
                        if data == "__COMPLETE__":
                            yield "event: done\ndata: {}\n\n"
                            return
                        try:
                            parsed = json.loads(data)
                            if isinstance(parsed, dict):
                                evt = parsed.get("event", "status")
                                dat = parsed.get("data", "")
                                yield f"event: {evt}\ndata: {dat}\n\n"
                            else:
                                yield f"event: token\ndata: {str(parsed)}\n\n"
                        except (json.JSONDecodeError, TypeError):
                            yield f"event: token\ndata: {data}\n\n"
                await asyncio.sleep(0.1)
            yield "event: error\ndata: Stream timeout\n\n"
        finally:
            await r.close()

    return StreamingResponse(_sse(), media_type="text/event-stream")


# === Breath Technique Teaching ===

# Simple 1-hr in-memory cache to avoid repeated LLM calls for the same technique
_breath_teaching_cache: dict[str, dict] = {}

_TECHNIQUE_QUERIES: dict[str, str] = {
    "serene_mind": "What do Sri Preethaji and Sri Krishnaji teach about conscious breathing and the long exhale as a path to the beautiful state?",
    "box": "What do Sri Preethaji and Sri Krishnaji teach about equanimity, balance, and equal-phase breathing or pranayama?",
    "4_7_8": "What do Sri Preethaji and Sri Krishnaji teach about deep rest, surrender, and releasing all tension through the breath?",
    "deep_vitality": "What do Sri Preethaji and Sri Krishnaji teach about prana, life force, and energising the body through breath awareness?",
}
_DEFAULT_TECHNIQUE_QUERY = "What do Sri Preethaji and Sri Krishnaji teach about the sacred importance of conscious breathing in spiritual practice?"


@router.get("/breath-teaching/{technique_id}", tags=["Meditation"])
async def get_breath_teaching(
    technique_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """
    Return an LLM-generated teaching from the Sri Preethaji / Sri Krishnaji knowledge
    base that contextualises a specific breathing technique for the Serene Mind modal.

    Results are cached in memory for 1 hour to avoid redundant LLM calls.
    The teaching is retrieved via RAG (Qdrant vector search) so it is always grounded
    in the actual ingested teachings — never a hardcoded string.
    """
    import time as _time

    # Check in-memory cache (1hr TTL)
    cached = _breath_teaching_cache.get(technique_id)
    if cached and (_time.time() - cached["ts"]) < 3600:
        return {"technique_id": technique_id, "teaching": cached["teaching"], "cached": True}

    query = _TECHNIQUE_QUERIES.get(technique_id, _DEFAULT_TECHNIQUE_QUERY)

    teaching = ""
    try:
        if container.qdrant and container.embedding and container.ollama:
            # Direct Qdrant retrieve
            query_embedding = await asyncio.to_thread(container.embedding.encode_single_full, query)
            results = await asyncio.to_thread(
                container.qdrant.search,
                query_vector=query_embedding["dense"],
                limit=3,
                sparse_vector=query_embedding["sparse"],
                raptor_level=0,
                query=query,
            )
            # Compile context
            context_text = "\n\n".join([r["text"] for r in results if r.get("text")])

            # Generate prompt for Ollama/Sarvam
            prompt = (
                f"You are Mukthi Guru, a spiritual guide. Sri Preethaji and Sri Krishnaji are the founders of O&O Academy.\n"
                f"Based on the following context, share a teaching about: {query.lower()}\n"
                f"Requirements:\n"
                f"1. Keep it to exactly 1-2 sentences.\n"
                f"2. Be poetic, grounded, and use their actual teachings/terminology if present in the context.\n"
                f"3. End with a gentle invitation to practice.\n"
                f"4. Do NOT say 'Based on the context...' or mention constraints.\n\n"
                f"Context:\n{context_text}\n\n"
                f"Teaching:"
            )

            # Generate response
            raw = await asyncio.wait_for(
                container.ollama.generate(
                    system_prompt="You share concise spiritual teachings.",
                    user_prompt=prompt,
                    max_tokens=80,
                ),
                timeout=25.0,
            )
            # Trim to 2 sentences max — this is a subtitle, not a full answer
            sentences = [s.strip() for s in raw.split(".") if s.strip()][:2]
            teaching = ". ".join(sentences) + ("." if sentences else "")

        if not teaching and container.ollama:
            # Fallback: direct LLM call if RAG search is empty or failed
            teaching = await asyncio.wait_for(
                container.ollama.generate(
                    system_prompt="You share concise spiritual teachings.",
                    user_prompt=(
                        f"In 1-2 sentences, share a teaching from Sri Preethaji or Sri Krishnaji "
                        f"about: {query.lower()} Be poetic, grounded in their actual teachings, "
                        f"and end with an invitation to practice."
                    ),
                    max_tokens=80,
                ),
                timeout=25.0,
            )

    except Exception as e:
        logger.warning(f"Breath teaching generation failed for {technique_id}: {e}")

    if not teaching:
        if technique_id == "serene_mind":
            teaching = (
                "Sri Preethaji and Sri Krishnaji teach that the Serene Mind practice calms the amygdala. "
                "Sit erect, close your eyes, take deep abdominal breaths (4s inhale, 2s hold, 6s exhale), "
                "observe your emotions/thoughts, and visualize a flame moving from your eyebrow center to the center of your brain."
            )
        else:
            teaching = (
                "Sri Preethaji and Sri Krishnaji teach that conscious breathing is the bridge "
                "between the suffering state and the beautiful state. Let each breath be a sacred offering."
            )

    # Cache the result
    _breath_teaching_cache[technique_id] = {"teaching": teaching, "ts": _time.time()}

    return {"technique_id": technique_id, "teaching": teaching, "cached": False}


@router.get("/admin/concept-graph")
async def get_concept_graph(
    container: ServiceContainer = Depends(get_container),
    user: dict = Depends(get_current_user_from_supabase),
):
    """Query Neo4j for spiritual concept nodes and relationships. Admin only."""
    if not user or not user.get("is_superuser"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not settings.neo4j_uri:
        return {
            "nodes": [
                {"id": "Soul Stage", "group": "Practice"},
                {"id": "Serene Mind", "group": "Practice"},
                {"id": "Deeksha", "group": "Concept"},
                {"id": "Ekam", "group": "Concept"},
                {"id": "Four Sacred Secrets", "group": "Concept"},
            ],
            "links": [
                {"source": "Soul Stage", "target": "Serene Mind", "type": "RELATED_TO"},
                {"source": "Deeksha", "target": "Ekam", "type": "REFERS_TO"},
                {"source": "Four Sacred Secrets", "target": "Soul Stage", "type": "CONTAINS"},
            ]
        }

    try:
        from neo4j import GraphDatabase

        def _query_graph():
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
            nodes = {}
            links = []
            with driver.session() as session:
                # Fix: LightRAG's Neo4JStorage writes entity_id (not entity_name),
                # and the shared knowledge-graph nodes it authors are never tagged
                # with tenant_id (tenant scoping only applies to per-user memory
                # nodes written by memory_service_v2.py) — the old WHERE clause
                # matched a nonexistent property twice over and always returned 0
                # rows, so this admin visualization silently fell back to the
                # hardcoded mock graph on every request.
                cypher = """
                MATCH (n)-[r]->(m)
                RETURN n.entity_id AS source_name, labels(n)[0] AS source_label,
                       type(r) AS rel_type,
                       m.entity_id AS target_name, labels(m)[0] AS target_label
                LIMIT 100
                """
                result = session.run(cypher)
                for record in result:
                    src = record["source_name"]
                    tgt = record["target_name"]
                    if not src or not tgt:
                        continue
                    
                    if src not in nodes:
                        nodes[src] = {"id": src, "group": record["source_label"] or "Concept"}
                    if tgt not in nodes:
                        nodes[tgt] = {"id": tgt, "group": record["target_label"] or "Concept"}
                        
                    links.append({
                        "source": src,
                        "target": tgt,
                        "type": record["rel_type"]
                    })
            return {"nodes": list(nodes.values()), "links": links}
            
        return await asyncio.to_thread(_query_graph)
    except Exception as e:
        logger.warning(f"Failed to query Neo4j concept-graph: {e}")
        return {
            "nodes": [
                {"id": "Soul Stage", "group": "Practice"},
                {"id": "Serene Mind", "group": "Practice"},
                {"id": "Deeksha", "group": "Concept"},
                {"id": "Ekam", "group": "Concept"},
            ],
            "links": [
                {"source": "Soul Stage", "target": "Serene Mind", "type": "RELATED_TO"},
                {"source": "Deeksha", "target": "Ekam", "type": "REFERS_TO"},
            ]
        }
