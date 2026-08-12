"""User memory management routes."""

from __future__ import annotations

import asyncio
import datetime as _dt
import html
import logging
import re
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.config import settings
from app.dependencies import ServiceContainer, get_container
from services import kg_analytics
from services.auth_service import auth_bridge, get_current_user_from_supabase
from services.user_profile_service import SpiritualLevel

router = APIRouter(tags=["Memory"])

logger = logging.getLogger(__name__)


_SANITIZE_TITLE_RE = re.compile(r"[^A-Za-z0-9 _-]")
_MAX_EXPORT_TITLE_LEN = 120


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
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    rows = await svc.retrieve_recent(user["id"], limit=page_size)
    episodes = [_episode_from_row(r) for r in rows]
    return EpisodeListResponse(episodes=episodes, total=len(episodes), page=page, page_size=page_size)


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
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
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


class ForgetMemoryRequest(BaseModel):
    memory_id: str


class AddMemoryRequest(BaseModel):
    text: str


class RelevantMemoryRequest(BaseModel):
    query: str
    limit: int = 5


@router.get("/memory/list", response_model=MemoryListResponse)
async def list_memories_endpoint(
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> MemoryListResponse:
    """List episodic memories for the authenticated user, paginated."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")

    result = await container.memory_service.list_memories(user["id"], page=page, page_size=page_size)
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
        raise HTTPException(status_code=501, detail="Profile features are not available at this time.")

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
        updated_at_dt = _dt.datetime.fromtimestamp(profile.updated_at, _dt.timezone.utc)
        updated_at_iso = updated_at_dt.isoformat()
    except Exception:
        updated_at_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()

    return CoreMemoryResponse(
        profile=core_profile,
        updated_at=updated_at_iso,
    )


@router.post("/memory/add", response_model=GuruMemoryResponse)
async def add_memory_endpoint(
    body: AddMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> GuruMemoryResponse:
    """Manually add an explicit memory."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")

    content = body.text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory text cannot be empty")

    m = await container.memory_service.add_explicit(user["id"], content, is_core=False)
    if not m:
        raise HTTPException(status_code=500, detail="Failed to save memory")

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
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Forget/delete a specific memory by its ID."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")

    success = await container.memory_service.forget(user["id"], body.memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")

    return {"status": "ok", "message": "Memory forgotten"}


@router.delete("/memory/reflections")
async def delete_all_reflections_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Delete all of the user's episodic memories (reflections). Core facts are durable."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    count = await container.memory_service.forget_all_reflections(user["id"])
    return {"status": "ok", "deleted": count}


@router.post("/memory/regenerate-summary")
async def regenerate_summary_endpoint(
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
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    count = await container.memory_service.regenerate_summary(user["id"])
    return {"status": "ok", "updated": count}


@router.get("/memory/summaries")
async def list_summaries_endpoint(
    limit: int = 10,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent session summaries for the authenticated user."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    rows = await container.memory_service.recent_summaries(user["id"], limit=limit)
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append({
            "id": str(r.get("id", "")),
            "session_id": str(r.get("session_id", "")),
            "summary": r.get("summary", ""),
            "created_at": created,
        })
    return out


@router.get("/memory/persona")
async def get_persona_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Return the user's L3 generated persona Markdown."""
    from services.layered_memory.persona_store import get_persona

    if not getattr(container, "supabase_client", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    content, updated_at = await get_persona(container.supabase_client, user["id"])
    return {"content": content or "", "updated_at": updated_at or ""}


@router.post("/memory/persona/regenerate")
async def regenerate_persona_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Regenerate the user's L3 persona from recent L1 atoms."""
    from services.layered_memory.l1_extractor import get_recent_atoms
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona

    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    atoms = await get_recent_atoms(container.memory_service, user["id"], limit=50)
    existing, _ = await get_persona(container.supabase_client, user["id"])
    persona = await generate_persona(atoms, existing)
    ok = await save_persona(container.supabase_client, user["id"], persona)
    return {"status": "ok" if ok else "error", "content": persona}


@router.post("/memory/reflect")
async def reflect_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """On-demand full reflection: L1 → L3 persona + skills + reset turn counter."""
    from services.layered_memory.l1_extractor import get_recent_atoms
    from services.layered_memory.l3_persona_generator import generate_persona
    from services.layered_memory.persona_store import get_persona, save_persona
    from services.layered_memory.skill_generator import generate_skills, get_skills, save_skills
    from services.tenant_context import TenantContext

    if not getattr(container, "memory_service", None) or not getattr(container, "supabase_client", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    tenant_id = TenantContext.get()
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
    return {"status": "ok", "persona": persona or "", "skills": new_skills}


def _reset_turn_counter(user_id: str) -> None:
    try:
        import json, os
        import redis as sync_redis
        r = sync_redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        key = f"turn_counter:{user_id}"
        r.set(key, json.dumps({"count": 0, "last_ts": __import__("time").time()}), ex=7200)
    except Exception as _e:
        logger.debug("[memory api] suppressed non-critical error: %s", _e)


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
async def regenerate_skills_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Regenerate skills from recent L1 atoms."""
    from services.layered_memory.skill_generator import generate_skills, get_skills, save_skills
    from services.tenant_context import TenantContext

    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    tenant_id = TenantContext.get()
    atoms = await container.memory_service.get_recent_atoms(user["id"], limit=30)
    atoms_text = "\n".join(a.get("content", "") for a in atoms) if atoms else ""
    existing = await get_skills(container.supabase_client, user["id"], tenant_id)
    skills = await generate_skills(atoms_text, existing)
    if skills:
        await save_skills(container.supabase_client, user["id"], tenant_id, skills)
    return {"skills": skills, "count": len(skills)}


@router.post("/memory/relevant")
async def relevant_memories_endpoint(
    body: RelevantMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """Return memories semantically relevant to a query via match_user_memories RPC."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")
    rows = await container.memory_service.search_semantic(
        user["id"], body.query, limit=body.limit, min_similarity=0.6
    )
    out = []
    for r in rows:
        created = r.get("created_at")
        if not isinstance(created, str):
            created = created.isoformat() if created else ""
        out.append({
            "id": str(r.get("id", "")),
            "content": r.get("content", ""),
            "similarity": float(r.get("similarity", 0.0)),
            "created_at": created,
        })
    return out


@router.get("/memory/conversations")
async def list_conversation_continuity_endpoint(
    limit: int = 5,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent conversation memories (for continuity display)."""
    if not container.user_profile:
        raise HTTPException(status_code=501, detail="Profile features are not available at this time.")
    rows = await container.user_profile.get_recent_memories(user["id"], limit=limit)
    out = []
    for m in rows:
        started = m.started_at
        if not isinstance(started, str):
            try:
                started = _dt.datetime.fromtimestamp(float(started), _dt.timezone.utc).isoformat()
            except Exception:
                started = str(started)
        out.append({
            "session_id": m.session_id,
            "started_at": started,
            "key_insights": m.key_insights or [],
            "follow_up_suggestions": m.follow_up_suggestions or [],
        })
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
    svc = getattr(container, "memory_service_v2", None) or getattr(container, "memory_service", None)
    if svc is None:
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")

    user_id = await _resolve_kg_user_id(request)

    result = await svc.build_personal_knowledge_graph(user_id, view=view)

    return PersonalKGResponse(
        nodes=[KGNode(**n) for n in result["nodes"]],
        edges=[KGEdge(**e) for e in result["edges"]],
        count=len(result["nodes"]),
    )


async def _resolve_kg_user_id(request: Request) -> str | None:
    """Resolve the KG caller's user id, allowing anonymous access.

    Uses the shared auth bridge. Valid credentials return their user id.
    Missing credentials fall back to None (anonymous / public ontology view).
    Invalid or expired credentials propagate the 401 from the auth bridge.
    """
    from fastapi.security.http import HTTPAuthorizationCredentials

    auth_header = request.headers.get("Authorization", "")
    token: HTTPAuthorizationCredentials | None = None
    if auth_header.startswith("Bearer "):
        token = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth_header[7:])
    try:
        user = await auth_bridge.get_user(request, token)
    except HTTPException:
        # Only propagate auth errors when the client actually sent credentials.
        if token is not None:
            raise
        return None
    if user:
        return user.get("id")
    return None


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

    svc = getattr(container, "memory_service_v2", None) or getattr(container, "memory_service", None)
    if svc is None:
        raise HTTPException(status_code=501, detail="Memory features are not available at this time.")

    user_id = await _resolve_kg_user_id(request)

    result = await svc.build_personal_knowledge_graph(user_id, view=body.view)

    try:
        html_content = await asyncio.wait_for(
            asyncio.to_thread(kg_analytics.export_d3blocks_html, result, title=html.escape(body.title)),
            timeout=30.0,
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="Export failed: timed out")
    except Exception:
        logger.exception("Knowledge graph export failed")
        raise HTTPException(status_code=500, detail="Export failed")

    from fastapi.responses import StreamingResponse
    from io import StringIO

    filename = f"{_sanitize_filename(body.title)}_map.html"
    return StreamingResponse(
        StringIO(html_content),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

class MemoryConsentRequest(BaseModel):
    granted: bool
    consent_version: str = "memory-v1"


@router.put("/memory/consent")
async def set_memory_consent_endpoint(
    body: MemoryConsentRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Record a revocable, versioned consent receipt for future memory writes."""
    from services.tenant_context import get_tenant_id_from_user

    outbox = getattr(container, "memory_outbox", None)
    if outbox is None:
        raise HTTPException(status_code=503, detail="Durable memory storage is unavailable")
    tenant_id = get_tenant_id_from_user(user)
    receipt = await outbox.record_consent(
        user_id=user["id"],
        tenant_id=tenant_id,
        granted=body.granted,
        consent_version=body.consent_version,
    )
    pending_deleted = 0
    if not body.granted:
        pending_deleted = await outbox.delete_user_rows(
            user_id=user["id"], tenant_id=tenant_id
        )
    return {
        "status": "granted" if body.granted else "revoked",
        "receipt_id": receipt.get("id"),
        "consent_version": body.consent_version,
        "pending_outbox_rows_deleted": pending_deleted,
    }


async def _delete_supabase_memory_rows(
    client: Any, table: str, user_id: str
) -> int:
    def _delete() -> Any:
        return client.table(table).delete().eq("user_id", user_id).execute()

    result = await asyncio.to_thread(_delete)
    rows = getattr(result, "data", None) or []
    return len(rows)


@router.delete("/memory/all")
async def delete_all_memory_endpoint(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Irreversibly erase every durable memory plane owned by this user.

    Failures are retained in the deletion receipt so the caller can retry. The
    endpoint never reports a full erasure when any known store could not be
    reached.
    """
    from services.tenant_context import TenantContext, get_tenant_id_from_user

    user_id = user["id"]
    tenant_id = get_tenant_id_from_user(user)
    TenantContext.set(tenant_id, user_id=user_id)
    counts: dict[str, int] = {}
    failures: list[str] = []
    outbox = getattr(container, "memory_outbox", None)

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
        except Exception as exc:
            counts[name] = 0
            failures.append(f"{name}: {str(exc)[:240]}")
            logger.exception("Memory erasure failed for %s", name)

    if outbox is not None:
        await _attempt(
            "memory_outbox",
            lambda: outbox.delete_user_rows(user_id=user_id, tenant_id=tenant_id),
        )

    client = getattr(container, "supabase_client", None)
    if client is not None:
        for table in (
            "guru_core_memory",
            "guru_memories",
            "user_episodes",
            "guru_session_summaries",
            "user_scene_blocks",
            "user_skills",
        ):
            await _attempt(
                table,
                lambda table=table: _delete_supabase_memory_rows(client, table, user_id),
            )

    memory_service = getattr(container, "memory_service", None)
    if memory_service is not None:
        await _attempt("ephemeral_memory", lambda: memory_service.clear_ephemeral(user_id))

        async def _delete_qdrant() -> int:
            from qdrant_client.http import models

            qdrant = await asyncio.to_thread(memory_service._get_qdrant_v2)
            if qdrant is None:
                return 0
            collection = memory_service._get_memory_collection()
            selector = models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=user_id)
                    ),
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=tenant_id)
                    ),
                ]
            )
            points, _ = await asyncio.to_thread(
                qdrant.scroll,
                collection_name=collection,
                scroll_filter=selector,
                limit=10000,
                with_payload=False,
                with_vectors=False,
            )
            if points:
                await asyncio.to_thread(
                    qdrant.delete,
                    collection_name=collection,
                    points_selector=selector,
                )
            return len(points)

        await _attempt("qdrant_global_memory", _delete_qdrant)

        async def _delete_neo4j() -> int:
            driver = await asyncio.to_thread(memory_service._get_neo4j)
            if driver is None:
                return 0

            def _delete() -> int:
                with driver.session() as session:
                    result = session.run(
                        """
                        MATCH (u:User {tenant_id: $tenant_id, id: $user_id})
                        OPTIONAL MATCH (u)-[:HAS_MEMORY]->(m:GlobalMemory)
                        WITH u, collect(m) AS memories
                        FOREACH (memory IN memories | DETACH DELETE memory)
                        DETACH DELETE u
                        RETURN size(memories) AS deleted
                        """,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    row = result.single()
                    return int(row["deleted"]) if row else 0

            return await asyncio.to_thread(_delete)

        await _attempt("neo4j_global_memory", _delete_neo4j)

    second_brain = getattr(container, "second_brain", None)
    if second_brain is not None:
        await _attempt("second_brain", lambda: second_brain.crypto_shred(user_id))

    status = "completed" if not failures else "partial_failure"
    receipt: dict[str, Any] = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "store_counts": counts,
        "status": status,
    }
    if outbox is not None:
        receipt = await outbox.write_deletion_receipt(
            user_id=user_id,
            tenant_id=tenant_id,
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
