"""User memory management routes."""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase
from services.user_profile_service import SpiritualLevel

router = APIRouter(tags=["Memory"])


class GuruMemoryResponse(BaseModel):
    id: str
    claim: str
    confidence: float
    last_seen: str
    created_at: str
    decay_score: float
    source: str


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
        raise HTTPException(status_code=501, detail="Memory service not enabled")

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
        raise HTTPException(status_code=501, detail="User profile service not enabled")

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
        raise HTTPException(status_code=501, detail="Memory service not enabled")

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
        raise HTTPException(status_code=501, detail="Memory service not enabled")

    success = await container.memory_service.forget(user["id"], body.memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")

    return {"status": "ok", "message": "Memory forgotten"}


@router.get("/memory/summaries")
async def list_summaries_endpoint(
    limit: int = 10,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """List recent session summaries for the authenticated user."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")
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


@router.post("/memory/relevant")
async def relevant_memories_endpoint(
    body: RelevantMemoryRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[dict]:
    """Return memories semantically relevant to a query via match_user_memories RPC."""
    if not getattr(container, "memory_service", None):
        raise HTTPException(status_code=501, detail="Memory service not enabled")
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
        raise HTTPException(status_code=501, detail="User profile service not enabled")
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
