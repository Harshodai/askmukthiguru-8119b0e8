"""User memory management routes."""

from __future__ import annotations

import asyncio
import datetime as _dt
import html
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.core.limiter import limiter
from app.dependencies import ServiceContainer, get_container
from app.memory_consent import require_active_memory_consent
from services import kg_analytics
from services.auth_service import auth_bridge, get_current_user_from_supabase
from services.tenant_context import TenantContext, get_tenant_id_from_user, set_tenant_from_request
from services.user_profile_service import SpiritualLevel

router = APIRouter(tags=["Memory"])

logger = logging.getLogger(__name__)


_SANITIZE_TITLE_RE = re.compile(r"[^A-Za-z0-9 _-]")
_MAX_EXPORT_TITLE_LEN = 120

async def _invalidate_personalized_answer_cache(container: Any, user_id: str) -> None:
    """Invalidate personal projections after a memory/privacy mutation.

    Private graph results contain memory text and are cached independently of
    exact answers. Evict those results first so an exact-cache failure cannot
    leave forgotten content replayable from the process-local graph cache.
    """
    from services.memory_service_v2 import MemoryServiceV2

    MemoryServiceV2.invalidate_personal_knowledge_graph_cache(
        user_id=user_id,
        all_tenants=True,
    )

    if getattr(container, "exact_cache", None) is not None:
        from services.cache.invalidation import invalidate_user_exact_cache

        await invalidate_user_exact_cache(container, user_id)



def _sanitize_filename(title: str) -> str:
    cleaned = _SANITIZE_TITLE_RE.sub("", title).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned or "wisdom_map").lower()


class EpisodeResponse(BaseModel):
    id: str
    query: str
    answer: str
    citations: list = []
    intent: Optional[str] = None
    created_at: str


class EpisodeListResponse(BaseModel):
    episodes: list[EpisodeResponse]
    total: int
    page: int
    page_size: int


def _episode_from_row(r: dict) -> EpisodeResponse:
    created = r.get("created_at")
    if not isinstance(created, str):
        created = created.isoformat() if created else ""
    citations = r.get("citations") or []
    if isinstance(citations, str):
        import json as _json

        try:
            citations = _json.loads(citations)
        except Exception:
            citations = []
    return EpisodeResponse(
        id=str(r.get("id", "")),
        query=r.get("query", ""),
        answer=r.get("answer", ""),
        citations=list(citations),
        intent=r.get("intent"),
        created_at=created,
    )


@router.get("/memory/episodes", response_model=EpisodeListResponse)
async def list_episodes_endpoint(
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> EpisodeListResponse:
    """List the authenticated user's recent conversation episodes, paginated."""
    svc = getattr(container, "episodic_memory_service", None)
    if svc is None or not svc.available:
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    rows = await svc.retrieve_recent(user["id"], limit=page_size)
    episodes = [_episode_from_row(r) for r in rows]
    return EpisodeListResponse(
        episodes=episodes, total=len(episodes), page=page, page_size=page_size
    )


@router.get("/memory/episodes/search", response_model=list[EpisodeResponse])
async def search_episodes_endpoint(
    q: str,
    limit: int = 20,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[EpisodeResponse]:
    """Substring search over the authenticated user's episodes (query + answer)."""
    svc = getattr(container, "episodic_memory_service", None)
    if svc is None or not svc.available:
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    if not q or not q.strip():
        return []
    rows = await svc.search(user["id"], q, limit=limit)
    return [_episode_from_row(r) for r in rows]


class GuruMemoryResponse(BaseModel):
    id: str
    claim: str
    confidence: float
    last_seen: str
    created_at: str
    decay_score: float
    source: str
    summary: Optional[str] = None


class MemoryListResponse(BaseModel):
    memories: list[GuruMemoryResponse]
    total: int
    page: int
    page_size: int


class CoreMemoryProfile(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    practice_level: Optional[str] = None
    dominant_themes: list[str] = []


class CoreMemoryResponse(BaseModel):
    profile: CoreMemoryProfile
    updated_at: str


class CoreMemoryWriteRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2048)


class ForgetMemoryRequest(BaseModel):
    memory_id: str


class EditMemoryRequest(BaseModel):
    memory_id: str
    text: str


class AddMemoryRequest(BaseModel):
    text: str


class RelevantMemoryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Semantic search query")
    limit: int = Field(default=5, ge=1, le=100, description="Max memories to return")


@router.get("/memory/list", response_model=MemoryListResponse)
async def list_memories_endpoint(
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> MemoryListResponse:
    """List episodic memories for the authenticated user, paginated."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    result = await container.memory_service.list_memories(
        user["id"], page=page, page_size=page_size
    )
    memories = []
    for m in result["memories"]:
        created_iso = m.get("created_at")
        updated_iso = m.get("updated_at")

        if not isinstance(created_iso, str):
            created_iso = created_iso.isoformat() if created_iso else ""
        if not isinstance(updated_iso, str):
            updated_iso = updated_iso.isoformat() if updated_iso else ""

        memories.append(
            GuruMemoryResponse(
                id=str(m["id"]),
                claim=m["content"],
                confidence=1.0,
                last_seen=updated_iso or created_iso,
                created_at=created_iso,
                decay_score=1.0,
                source=m.get("source", "extracted"),
                summary=m.get("summary"),
            )
        )
    return MemoryListResponse(
        memories=memories,
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get("/memory/core", response_model=CoreMemoryResponse)
async def get_core_memory_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> CoreMemoryResponse:
    """Retrieve core profile preferences aggregated with core facts."""
    if not container.user_profile:
        raise HTTPException(
            status_code=501, detail="Profile features are not available at this time."
        )

    profile = await container.user_profile.get_or_create_profile(user["id"])

    practice_level_map = {
        SpiritualLevel.BEGINNER: "beginner",
        SpiritualLevel.EXPLORER: "intermediate",
        SpiritualLevel.PRACTITIONER: "committed",
        SpiritualLevel.SEEKER: "advanced",
    }
    practice_level = practice_level_map.get(profile.spiritual_level, "beginner")
    language = profile.preferred_language.value if profile.preferred_language else "en"

    core_profile = CoreMemoryProfile(
        name=user.get("user_metadata", {}).get("full_name") or user.get("email", "Seeker"),
        language=language,
        practice_level=practice_level,
        dominant_themes=profile.topics_of_interest or [],
    )

    try:
        updated_at_dt = _dt.datetime.fromtimestamp(profile.updated_at, _dt.UTC)
        updated_at_iso = updated_at_dt.isoformat()
    except Exception:
        updated_at_iso = _dt.datetime.now(_dt.UTC).isoformat()

    return CoreMemoryResponse(
        profile=core_profile,
        updated_at=updated_at_iso,
    )


@router.put("/memory/core")
async def upsert_core_memory_endpoint(
    body: CoreMemoryWriteRequest,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Save the user's explicit guiding note through the consent-gated backend."""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Core memory content cannot be empty.")
    client = getattr(container, "supabase_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Memory storage is unavailable.")

    await require_active_memory_consent(container, user["id"])
    from services.tenant_context import TenantContext

    payload = {
        "user_id": user["id"],
        "tenant_id": TenantContext.get(),
        "content": content,
        "updated_at": _dt.datetime.now(_dt.UTC).isoformat(),
    }
    try:
        result = await asyncio.to_thread(
            lambda: (
                client.table("guru_core_memory")
                .upsert(payload, on_conflict="user_id,tenant_id")
                .select("id, content, updated_at")
                .single()
                .execute()
            )
        )
        row = getattr(result, "data", None)
        if not isinstance(row, dict) or not row.get("id"):
            raise RuntimeError("core memory write returned no row")
        updated_at = row.get("updated_at")
        if not isinstance(updated_at, str):
            updated_at = updated_at.isoformat() if updated_at else payload["updated_at"]
        await _invalidate_personalized_answer_cache(container, user["id"])
        return {"id": str(row["id"]), "content": row.get("content", content), "updated_at": updated_at}
    except Exception as exc:
        logger.warning("Core memory write failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Failed to save core memory.") from None


@router.post("/memory/add", response_model=GuruMemoryResponse)
async def add_memory_endpoint(
    body: AddMemoryRequest,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> GuruMemoryResponse:
    """Manually add an explicit memory."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    content = body.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty")

    await require_active_memory_consent(container, user["id"])
    m = await container.memory_service.add_explicit(user["id"], content, is_core=False)
    if not m:
        raise HTTPException(status_code=500, detail="Failed to save memory")
    await _invalidate_personalized_answer_cache(container, user["id"])

    created_iso = m.get("created_at")
    updated_iso = m.get("updated_at")
    if not isinstance(created_iso, str):
        created_iso = created_iso.isoformat() if created_iso else ""
    if not isinstance(updated_iso, str):
        updated_iso = updated_iso.isoformat() if updated_iso else ""

    return GuruMemoryResponse(
        id=str(m["id"]),
        claim=m["content"],
        confidence=1.0,
        last_seen=updated_iso or created_iso,
        created_at=created_iso,
        decay_score=1.0,
        source=m.get("source", "explicit"),
    )


@router.post("/memory/forget")
async def forget_memory_endpoint(
    body: ForgetMemoryRequest,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Forget/delete a specific memory by its ID."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    success = await container.memory_service.forget(user["id"], body.memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")
    await _invalidate_personalized_answer_cache(container, user["id"])

    return {"status": "ok", "message": "Memory forgotten"}


@router.post("/memory/edit")
async def edit_memory_endpoint(
    body: EditMemoryRequest,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Edit/correct a specific memory's text by its ID."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    content = body.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty")

    await require_active_memory_consent(container, user["id"])
    m = await container.memory_service.edit(user["id"], body.memory_id, content)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")
    await _invalidate_personalized_answer_cache(container, user["id"])

    return {"status": "ok", "message": "Memory updated"}


@router.delete("/memory/reflections")
async def delete_all_reflections_endpoint(
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Delete all of the user's episodic memories (reflections). Core facts are durable."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    count = await container.memory_service.forget_all_reflections(user["id"])
    await _invalidate_personalized_answer_cache(container, user["id"])
    return {"status": "ok", "deleted": count}


@router.delete("/account/purge-memory")
async def purge_account_memory_endpoint(
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Erase every memory plane before account deletion may proceed.

    Reuse the comprehensive deletion path so this endpoint cannot silently
    diverge from the user-facing erasure contract. The caller must treat any
    partial result as a hard failure and keep the Auth account intact.
    """
    result = await delete_all_memory_endpoint(_tenant=None, user=user, container=container)
    if result.get("status") != "completed":
        raise HTTPException(
            status_code=503,
            detail={
                "status": "partial_failure",
                "receipt_id": result.get("receipt_id"),
                "failures": result.get("failures", []),
            },
        )
    return {**result, "status": "ok"}


@router.post("/memory/regenerate-summary")
async def regenerate_summary_endpoint(
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Regenerate the `summary` column on episodic memories where it is null.

    Fills the column from the existing session_summary of the source conversation
    where correspondence can be inferred; falls back to a truncated claim. Cheap;
    used to surface the human-readable roll-up (Task 9 shows the summary on the
    Profile Memory tab).
    """
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    await require_active_memory_consent(container, user["id"])
    count = await container.memory_service.regenerate_summary(user["id"])
    await _invalidate_personalized_answer_cache(container, user["id"])
    return {"status": "ok", "updated": count}


@router.get("/memory/summaries")
async def list_summaries_endpoint(
    limit: int = 10,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent session summaries for the authenticated user."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    rows = await container.memory_service.recent_summaries(user["id"], limit=limit)
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append(
            {
                "id": str(r.get("id", "")),
                "session_id": str(r.get("session_id", "")),
                "summary": r.get("summary", ""),
                "created_at": created,
            }
        )
    return out


@router.get("/memory/persona")
async def get_persona_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Return the user's L3 generated persona Markdown."""
    from services.layered_memory.persona_store import get_persona

    if not getattr(container, "supabase_client", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    content, updated_at = await get_persona(container.supabase_client, user["id"])
    return {"content": content or "", "updated_at": updated_at or ""}


@router.post("/memory/persona/regenerate")
@limiter.limit(settings.memory_generation_rate_limit)
async def regenerate_persona_endpoint(
    request: Request,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Regenerate the user's L3 persona from recent L1 atoms."""
    from services.layered_memory.l1_extractor import get_recent_atoms
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona

    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    await require_active_memory_consent(container, user["id"])
    atoms = await get_recent_atoms(container.memory_service, user["id"], limit=50)
    existing, _ = await get_persona(container.supabase_client, user["id"])
    persona = await generate_persona(atoms, existing)
    ok = await save_persona(container.supabase_client, user["id"], persona)
    if ok:
        await _invalidate_personalized_answer_cache(container, user["id"])
    return {"status": "ok" if ok else "error", "content": persona}


@router.post("/memory/reflect")
@limiter.limit(settings.memory_generation_rate_limit)
async def reflect_endpoint(
    request: Request,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """On-demand full reflection: L1 → L3 persona + skills + reset turn counter."""
    from services.layered_memory.l1_extractor import get_recent_atoms
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona
    from services.layered_memory.skill_generator import generate_skills, get_skills, save_skills
    from services.tenant_context import TenantContext

    if not getattr(container, "memory_service", None) or not getattr(
        container, "supabase_client", None
    ):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    tenant_id = TenantContext.get()
    await require_active_memory_consent(container, user["id"])
    atoms = await get_recent_atoms(container.memory_service, user["id"], limit=50)
    if not atoms:
        return {"status": "ok", "persona": "", "skills": [], "note": "no atoms yet"}

    atoms_text = "\n".join(a.content for a in atoms)
    existing_persona, _ = await get_persona(container.supabase_client, user["id"])
    persona = await generate_persona(atoms, existing_persona)
    if persona:
        await save_persona(container.supabase_client, user["id"], persona)

    existing_skills = await get_skills(container.supabase_client, user["id"], tenant_id)
    new_skills = await generate_skills(atoms_text, existing_skills)
    if new_skills:
        await save_skills(container.supabase_client, user["id"], tenant_id, new_skills)

    _reset_turn_counter(user["id"])
    await _invalidate_personalized_answer_cache(container, user["id"])
    return {"status": "ok", "persona": persona or "", "skills": new_skills}


def _reset_turn_counter(user_id: str) -> None:
    try:
        import json
        import os

        import redis as sync_redis

        r = sync_redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
        )
        key = f"turn_counter:{user_id}"
        r.set(key, json.dumps({"count": 0, "last_ts": __import__("time").time()}), ex=7200)
    except Exception as _e:
        logger.debug("[memory api] suppressed non-critical error (%s)", type(_e).__name__)


@router.get("/memory/skills")
async def list_skills_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List auto-generated skills for the current user."""
    from services.layered_memory.skill_generator import get_skills
    from services.tenant_context import TenantContext

    if not getattr(container, "supabase_client", None):
        return []
    tenant_id = TenantContext.get()
    return await get_skills(container.supabase_client, user["id"], tenant_id)


@router.post("/memory/skills/regenerate")
@limiter.limit(settings.memory_generation_rate_limit)
async def regenerate_skills_endpoint(
    request: Request,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Regenerate skills from recent L1 atoms."""
    from services.layered_memory.skill_generator import generate_skills, get_skills, save_skills
    from services.tenant_context import TenantContext

    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    tenant_id = TenantContext.get()
    await require_active_memory_consent(container, user["id"])
    atoms = await container.memory_service.get_recent_atoms(user["id"], limit=30)
    atoms_text = "\n".join(a.get("content", "") for a in atoms) if atoms else ""
    existing = await get_skills(container.supabase_client, user["id"], tenant_id)
    skills = await generate_skills(atoms_text, existing)
    if skills:
        await save_skills(container.supabase_client, user["id"], tenant_id, skills)
        await _invalidate_personalized_answer_cache(container, user["id"])
    return {"skills": skills, "count": len(skills)}


@router.post("/memory/relevant")
async def relevant_memories_endpoint(
    body: RelevantMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """Return memories semantically relevant to a query via match_user_memories RPC."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )
    rows = await container.memory_service.search_semantic(
        user["id"], body.query, limit=body.limit, min_similarity=0.6
    )
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append(
            {
                "id": str(r.get("id", "")),
                "content": r.get("content", ""),
                "similarity": float(r.get("similarity", 0.0)),
                "created_at": created,
            }
        )
    return out


@router.get("/memory/conversations")
async def list_conversation_continuity_endpoint(
    limit: int = 5,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent conversation memories (for continuity display)."""
    if not container.user_profile:
        raise HTTPException(
            status_code=501, detail="Profile features are not available at this time."
        )
    rows = await container.user_profile.get_recent_memories(user["id"], limit=limit)
    out = []
    for m in rows:
        started = m.started_at
        if not isinstance(started, str):
            try:
                started = _dt.datetime.fromtimestamp(float(started), _dt.UTC).isoformat()
            except Exception:
                started = str(started)
        out.append(
            {
                "session_id": m.session_id,
                "started_at": started,
                "key_insights": m.key_insights or [],
                "follow_up_suggestions": m.follow_up_suggestions or [],
            }
        )
    return out


class KGNodeAnalytics(BaseModel):
    degree: int = 0
    betweenness: float = 0.0
    closeness: float = 0.0
    pagerank: float = 0.0
    hits_hub: float = 0.0
    hits_authority: float = 0.0


class KGNode(BaseModel):
    id: str
    label: str
    type: str
    teacher: str | None = None
    state_category: str | None = None
    content: str | None = None
    analytics: KGNodeAnalytics | None = None
    community: int = -1


class KGEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class PersonalKGResponse(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
    count: int


@router.get("/memory/knowledge-graph", response_model=PersonalKGResponse)
async def personal_knowledge_graph_endpoint(
    request: Request,
    view: str = "personal",
    container: ServiceContainer = Depends(get_container),
) -> PersonalKGResponse:
    """Return the user's personal knowledge graph.

    With Supabase auth: returns personal consciousness graph if view == "personal".
    Supports view="ontology" to get the public teaching ontology.
    Anonymous access is allowed when no credentials are present.
    """
    svc = getattr(container, "memory_service_v2", None) or getattr(
        container, "memory_service", None
    )
    if svc is None:
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    resolved_user = await _resolve_kg_user(request)
    user_id = resolved_user.get("id") if resolved_user else None
    tenant_id = get_tenant_id_from_user(resolved_user)
    normalized_view = (view or "personal").strip().lower()
    if normalized_view not in {"personal", "ontology"}:
        raise HTTPException(status_code=400, detail="Unsupported knowledge-graph view.")

    # Personal graph access is user data. Anonymous callers may only request the
    # public ontology view; accepting "personal" with a missing user id silently
    # fell back to public data and made the auth contract dependent on service
    # implementation details.
    if normalized_view == "personal" and not user_id:
        raise HTTPException(
            status_code=401, detail="Authentication required for the personal knowledge graph."
        )

    with TenantContext.scope(
        tenant_id,
        email=(resolved_user or {}).get("email") or "",
        user_id=user_id or "",
    ):
        result = await svc.build_personal_knowledge_graph(user_id, view=normalized_view)

    return PersonalKGResponse(
        nodes=[KGNode(**n) for n in result["nodes"]],
        edges=[KGEdge(**e) for e in result["edges"]],
        count=len(result["nodes"]),
    )


async def _resolve_kg_user(request: Request) -> dict | None:
    """Resolve the full authenticated identity for a Knowledge Graph request.

    Personal graph routes need both user_id and tenant_id. Returning the entire
    auth-bridge identity avoids deriving a tenant from a user ID or relying on
    request.state being populated by a different router dependency.
    Missing credentials are allowed only for the public ontology view; invalid
    or expired bearer tokens continue to fail closed.
    """
    from fastapi.security.http import HTTPAuthorizationCredentials

    auth_header = request.headers.get("Authorization", "")
    token: HTTPAuthorizationCredentials | None = None
    if auth_header.startswith("Bearer "):
        token = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header[7:])
    try:
        user = await auth_bridge.get_user(request, token)
    except HTTPException:
        if token is not None:
            raise
        return None
    return user if isinstance(user, dict) and user.get("id") else None


async def _resolve_kg_user_id(request: Request) -> str | None:
    """Backward-compatible identity helper; new KG routes retain tenant claims."""
    user = await _resolve_kg_user(request)
    return user.get("id") if user else None


class KGExportRequest(BaseModel):
    view: str = "personal"
    title: str = "Wisdom Map"

    @field_validator("title", mode="before")
    @classmethod
    def _validate_title(cls, value: Any) -> str:
        if value is None:
            return "Wisdom Map"
        text = str(value)
        if len(text) > _MAX_EXPORT_TITLE_LEN:
            raise ValueError(f"title must be at most {_MAX_EXPORT_TITLE_LEN} characters")
        if not re.match(r"^[\w\s\-_.()]+$", text, re.UNICODE):
            raise ValueError("title contains disallowed characters")
        return text


@router.post("/memory/knowledge-graph/export")
async def export_knowledge_graph_endpoint(
    request: Request,
    body: KGExportRequest,
    container: ServiceContainer = Depends(get_container),
):
    """Export the current knowledge graph as a standalone interactive HTML file."""
    if not settings.kg_export_enabled:
        raise HTTPException(status_code=501, detail="Knowledge graph export is not enabled.")

    svc = getattr(container, "memory_service_v2", None) or getattr(
        container, "memory_service", None
    )
    if svc is None:
        raise HTTPException(
            status_code=501, detail="Memory features are not available at this time."
        )

    resolved_user = await _resolve_kg_user(request)
    user_id = resolved_user.get("id") if resolved_user else None
    tenant_id = get_tenant_id_from_user(resolved_user)
    normalized_view = (body.view or "personal").strip().lower()
    if normalized_view not in {"personal", "ontology"}:
        raise HTTPException(status_code=400, detail="Unsupported knowledge-graph view.")
    if normalized_view == "personal" and not user_id:
        raise HTTPException(
            status_code=401, detail="Authentication required for the personal knowledge graph."
        )

    with TenantContext.scope(
        tenant_id,
        email=(resolved_user or {}).get("email") or "",
        user_id=user_id or "",
    ):
        result = await svc.build_personal_knowledge_graph(user_id, view=normalized_view)

    try:
        html_content = await asyncio.wait_for(
            asyncio.to_thread(
                kg_analytics.export_d3blocks_html, result, title=html.escape(body.title)
            ),
            timeout=30.0,
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=500, detail="Export failed: timed out")
    except Exception:
        logger.exception("Knowledge graph export failed")
        raise HTTPException(status_code=500, detail="Export failed")

    from io import StringIO

    from fastapi.responses import StreamingResponse

    filename = f"{_sanitize_filename(body.title)}_map.html"
    return StreamingResponse(
        StringIO(html_content),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class MemoryConsentRequest(BaseModel):
    granted: bool
    consent_version: str = Field(default="memory-v1", pattern=r"^memory-v1$")


@router.post("/memory/consent")
async def set_memory_consent_endpoint(
    body: MemoryConsentRequest,
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Record a revocable, versioned consent receipt for future memory writes."""
    from services.tenant_context import TenantContext, get_tenant_id_from_user

    outbox = getattr(container, "memory_outbox", None)
    if outbox is None:
        raise HTTPException(status_code=503, detail="Durable memory storage is unavailable")
    tenant_id = TenantContext.get()
    user_scoped_tenant = get_tenant_id_from_user(user)
    if user_scoped_tenant != tenant_id:
        # Tenant identifiers can originate from request/user context. The
        # mismatch is actionable without echoing either identifier to logs.
        logger.info("Memory consent tenant context differed from resolved user tenant")
    receipt = await outbox.record_consent(
        user_id=user["id"],
        tenant_id=tenant_id,
        granted=body.granted,
        consent_version=body.consent_version,
    )
    pending_deleted = 0
    pending_extractions_deleted = 0
    cache_entries_invalidated = 0
    if not body.granted:
        try:
            pending_deleted = await outbox.delete_user_rows(
                user_id=user["id"], tenant_id=tenant_id
            )
            client = getattr(container, "supabase_client", None)
            if client is None:
                raise RuntimeError("pending extraction store unavailable")
            pending_extractions_deleted = await _delete_supabase_memory_rows(
                client,
                "pending_extractions",
                user["id"],
                tenant_id=tenant_id,
            )
            from services.cache.invalidation import invalidate_user_exact_cache

            cache_entries_invalidated = await invalidate_user_exact_cache(
                container, user["id"]
            )
        except Exception as exc:
            # The exception trace is useful for operations; the user ID is not.
            logger.error("Memory consent was revoked but cleanup could not be confirmed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail=(
                    "Consent revocation was recorded, but cleanup is incomplete. "
                    "Retry revocation before relying on memory removal."
                ),
            ) from exc
    return {
        "status": "granted" if body.granted else "revoked",
        "receipt_id": receipt.get("id"),
        "consent_version": body.consent_version,
        "pending_outbox_rows_deleted": pending_deleted,
        "pending_extractions_deleted": pending_extractions_deleted,
        "personalized_cache_entries_invalidated": cache_entries_invalidated,
    }


async def _delete_supabase_memory_rows(
    client: Any,
    table: str,
    user_id: str,
    tenant_id: str | None = None,
) -> int:
    def _delete() -> Any:
        query = client.table(table).delete().eq("user_id", user_id)
        if tenant_id is not None:
            query = query.eq("tenant_id", tenant_id)
        return query.select("id").execute()

    result = await asyncio.to_thread(_delete)
    rows = getattr(result, "data", None) or []
    return len(rows)


@router.delete("/memory/all")
async def delete_all_memory_endpoint(
    _tenant: None = Depends(set_tenant_from_request),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Irreversibly erase every durable memory plane owned by this user.

    Failures are retained in the deletion receipt so the caller can retry. The
    endpoint never reports a full erasure when any known store could not be
    reached.
    """
    # The endpoint means whole-account erasure, not deletion in the currently
    # selected tenant. User IDs are globally unique; all derived stores must be
    # purged for this identity across every tenant namespace.
    user_id = user["id"]
    receipt_tenant_id = "*"
    counts: dict[str, int] = {}
    failures: list[str] = []
    outbox = getattr(container, "memory_outbox", None)

    def _unavailable(name: str) -> None:
        """Refuse to certify erasure when a known memory plane cannot be inspected."""
        counts[name] = 0
        failures.append(f"{name}: Storage adapter unavailable")

    async def _attempt(name: str, operation: Any) -> None:
        try:
            result = operation()
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, dict):
                counts[name] = int(result.get("deleted", result.get("count", 1)))
            elif isinstance(result, bool):
                counts[name] = int(result)
            else:
                counts[name] = int(result)
        except Exception:
            counts[name] = 0
            failures.append(f"{name}: Operation failed")
            logger.exception("Memory erasure failed for %s", name)

    if outbox is not None:
        await _attempt(
            "memory_outbox",
            lambda: outbox.delete_user_rows(user_id=user_id, tenant_id=None),
        )
    else:
        _unavailable("memory_outbox")

    from services.cache.invalidation import invalidate_user_exact_cache

    await _attempt(
        "exact_answer_cache",
        lambda: invalidate_user_exact_cache(container, user_id, all_tenants=True),
    )

    # The personal KG cache stores rendered private memory text separately
    # from the answer cache. Full erasure must evict it across every tenant.
    from services.memory_service_v2 import MemoryServiceV2

    await _attempt(
        "personal_knowledge_graph_cache",
        lambda: MemoryServiceV2.invalidate_personal_knowledge_graph_cache(
            user_id=user_id,
            all_tenants=True,
        ),
    )

    client = getattr(container, "supabase_client", None)
    if client is not None:
        for table in (
            "guru_core_memory",
            "guru_memories",
            "user_episodes",
            "guru_session_summaries",
            "memory_compaction_snapshots",
            "user_scene_blocks",
            "user_skills",
            # Canonical memory and everything that holds a plaintext copy of it:
            # the audit tables snapshot statements (old_state/new_state, reason,
            # metadata), so erasing only canonical_memories would leave the
            # seeker's words behind. user_profiles and conversation_memories are
            # what we know about the seeker too.
            "canonical_memories",
            "canonical_memory_events",
            "memory_audit_events",
            # These rollback snapshots contain serialized plaintext memory too.
            "canonical_memory_compaction_snapshots",
            "conversation_memories",
            "user_profiles",
            "user_personas",
            "pending_extractions",
        ):
            await _attempt(
                table,
                lambda table=table: _delete_supabase_memory_rows(client, table, user_id),
            )
    else:
        _unavailable("supabase_memory_tables")

    memory_service = getattr(container, "memory_service", None)
    if memory_service is not None:
        async def _clear_ephemeral() -> int:
            cleared = await memory_service.clear_ephemeral(user_id, all_tenants=True)
            if cleared is not True:
                raise RuntimeError("Redis and process-local ephemeral memory deletion was not confirmed")
            return 1

        await _attempt("ephemeral_memory", _clear_ephemeral)

        async def _delete_qdrant() -> int:
            from qdrant_client.http import models

            qdrant = await asyncio.to_thread(memory_service._get_qdrant_v2)
            if qdrant is None:
                raise RuntimeError("Qdrant adapter unavailable")
            collections_result = await asyncio.to_thread(qdrant.get_collections)
            collection_names = [
                str(item.name)
                for item in getattr(collections_result, "collections", [])
                if getattr(item, "name", None)
            ]
            # User facts can live in the global collection or a per-guru/
            # tenant-namespaced memory collection. Filter by the globally unique
            # user UUID in every recognized memory collection; never remove an
            # entire collection or any other user's points.
            candidate_names = sorted(
                name
                for name in collection_names
                if (name.split("__tenant_", 1)[0] == "global_memory"
                    or name.split("__tenant_", 1)[0].endswith("_memory"))
            )
            selector = models.Filter(
                must=[
                    models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                ]
            )
            deleted_total = 0
            for collection in candidate_names:
                # Exact count includes every page; wait=True confirms the
                # server applied the deletion before a full-erasure receipt.
                count_result = await asyncio.to_thread(
                    qdrant.count,
                    collection_name=collection,
                    count_filter=selector,
                    exact=True,
                )
                await asyncio.to_thread(
                    qdrant.delete,
                    collection_name=collection,
                    points_selector=selector,
                    wait=True,
                )
                deleted_total += int(count_result.count)
            return deleted_total

        await _attempt("qdrant_global_memory", _delete_qdrant)

        async def _delete_neo4j() -> int:
            driver = await asyncio.to_thread(memory_service._get_neo4j)
            if driver is None:
                raise RuntimeError("Neo4j/Memgraph adapter unavailable")

            def _delete() -> int:
                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (u:User {id: $user_id})
                        OPTIONAL MATCH (u)-[:HAS_MEMORY]->(m:GlobalMemory)
                        WITH collect(DISTINCT u) AS users, collect(DISTINCT m) AS memories
                        FOREACH (memory IN memories | DETACH DELETE memory)
                        FOREACH (user IN users | DETACH DELETE user)
                        RETURN size(memories) AS deleted
                        """,
                        user_id=user_id,
                    )
                    row = result.single()
                    return int(row["deleted"]) if row else 0

            return await asyncio.to_thread(_delete)

        await _attempt("neo4j_global_memory", _delete_neo4j)
    else:
        _unavailable("ephemeral_memory")
        _unavailable("qdrant_global_memory")
        _unavailable("neo4j_global_memory")

    integration = getattr(container, "canonical_memory_integration", None)
    canonical_index = getattr(getattr(integration, "memory_retriever", None), "_vector_index", None)
    if canonical_index is not None:
        await _attempt(
            "qdrant_canonical_memory",
            lambda: canonical_index.delete_all_user(user_id=user_id, all_tenants=True),
        )
    else:
        _unavailable("qdrant_canonical_memory")

    second_brain = getattr(container, "second_brain", None)
    if second_brain is not None:
        await _attempt("second_brain", lambda: second_brain.crypto_shred(user_id))
    else:
        _unavailable("second_brain")

    status = "completed" if not failures else "partial_failure"
    receipt: dict[str, Any] = {
        "user_id": user_id,
        "tenant_id": receipt_tenant_id,
        "store_counts": counts,
        "status": status,
    }
    if outbox is not None:
        receipt = await outbox.write_deletion_receipt(
            user_id=user_id,
            tenant_id=receipt_tenant_id,
            store_counts=counts,
            status=status,
            error="; ".join(failures) if failures else None,
        )
    return {
        "status": status,
        "receipt_id": receipt.get("id"),
        "deleted": counts,
        "failures": failures,
    }
