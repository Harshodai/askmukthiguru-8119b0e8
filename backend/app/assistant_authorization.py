"""Server-authoritative assistant discovery and access resolution."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

from app.assistant_registry import AssistantScope, resolve_assistant_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantResolution:
    """Effective assistant identity, prompt, and retrieval authority."""

    slug: str
    assistant_id: Optional[str]
    name: str
    description: str
    avatar_url: Optional[str]
    visibility: str
    system_prompt: Optional[str]
    knowledge_tags: tuple[str, ...]
    scope: AssistantScope


@dataclass(frozen=True)
class AssistantCatalogItem:
    """Safe discovery payload; never includes prompts, invite codes, or scope internals."""

    id: str
    slug: str
    name: str
    description: str
    avatar_url: Optional[str]
    starter_questions: tuple[str, ...]
    visibility: str


def _is_authenticated(user: Optional[dict[str, Any]]) -> bool:
    if not user:
        return False
    user_id = str(user.get("id") or "")
    return bool(user_id) and user_id != "anonymous" and not user_id.startswith("anon:") and not user.get("is_anonymous")


def _user_id(user: Optional[dict[str, Any]]) -> Optional[str]:
    if not _is_authenticated(user):
        return None
    value = user.get("id") if user else None
    return str(value) if value else None


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _row(response: Any) -> Optional[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def _clean_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _scope_from_metadata(row: Optional[dict[str, Any]], *, fallback: AssistantScope) -> AssistantScope:
    if not row:
        return fallback
    return AssistantScope(
        corpus_id=str(row.get("corpus_id") or fallback.corpus_id),
        teacher_id=(str(row["teacher_id"]).strip() if row.get("teacher_id") else fallback.teacher_id),
        graph_namespace=(str(row["graph_namespace"]).strip() if row.get("graph_namespace") else fallback.graph_namespace),
        source_release_id=(str(row["source_release_id"]).strip() if row.get("source_release_id") else fallback.source_release_id),
        rights_status=str(row.get("rights_status") or fallback.rights_status).strip().lower(),
        rollout_enabled=bool(row.get("rollout_enabled", fallback.rollout_enabled)),
    )


async def _load_db_assistant(slug: str, container: Any) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    client = getattr(container, "supabase_client", None)
    if client is None:
        return None, None
    try:
        response = await asyncio.to_thread(
            client.table("assistants")
            .select("id, slug, name, description, avatar_url, system_prompt, starter_questions, knowledge_tags, visibility, created_by")
            .eq("slug", slug)
            .limit(1)
            .execute
        )
        assistant_row = _row(response)
        if not assistant_row:
            return None, None
        scope_response = await asyncio.to_thread(
            client.table("assistant_scope_metadata")
            .select("corpus_id, teacher_id, graph_namespace, source_release_id, assistant_scope_version, rights_status, rollout_enabled, knowledge_tags")
            .eq("assistant_id", assistant_row.get("id"))
            .limit(1)
            .execute
        )
        return assistant_row, _row(scope_response)
    except Exception as exc:
        logger.warning("Assistant catalog lookup failed for slug=%s: %s", slug, type(exc).__name__)
        return None, None


async def _has_access(assistant_row: dict[str, Any], user: Optional[dict[str, Any]], container: Any) -> bool:
    visibility = str(assistant_row.get("visibility") or "private").lower()
    if visibility == "public":
        return True
    uid = _user_id(user)
    if not uid:
        return False
    if str(assistant_row.get("created_by") or "") == uid:
        return True
    if user and user.get("is_superuser"):
        return True
    client = getattr(container, "supabase_client", None)
    if client is None:
        return False
    try:
        response = await asyncio.to_thread(
            client.table("assistant_access")
            .select("assistant_id")
            .eq("assistant_id", assistant_row.get("id"))
            .eq("user_id", uid)
            .limit(1)
            .execute
        )
        return bool(_row(response))
    except Exception as exc:
        logger.warning("Assistant access lookup failed for user=%s: %s", uid, type(exc).__name__)
        return False


async def resolve_effective_assistant(
    slug: Optional[str], user: Optional[dict[str, Any]], container: Any
) -> Optional[AssistantResolution]:
    """Resolve built-in or database-backed assistants and fail closed on access."""
    if not slug:
        return None
    normalized = slug.strip()
    if not normalized:
        return None

    builtin_scope = resolve_assistant_scope(normalized)
    if builtin_scope is not None:
        return AssistantResolution(
            slug=normalized,
            assistant_id=None,
            name=normalized,
            description="",
            avatar_url=None,
            visibility="public",
            system_prompt=None,
            knowledge_tags=(),
            scope=builtin_scope,
        )

    assistant_row, metadata_row = await _load_db_assistant(normalized, container)
    if not assistant_row:
        return None
    if not await _has_access(assistant_row, user, container):
        return None

    fallback_scope = AssistantScope(corpus_id="askmukthiguru", rights_status="pending", rollout_enabled=False)
    scope = _scope_from_metadata(metadata_row, fallback=fallback_scope)
    if scope.rights_status != "approved" or not scope.rollout_enabled:
        return None
    return AssistantResolution(
        slug=normalized,
        assistant_id=str(assistant_row.get("id")) if assistant_row.get("id") else None,
        name=str(assistant_row.get("name") or normalized),
        description=str(assistant_row.get("description") or ""),
        avatar_url=assistant_row.get("avatar_url"),
        visibility=str(assistant_row.get("visibility") or "private"),
        system_prompt=str(assistant_row.get("system_prompt") or "") or None,
        knowledge_tags=_clean_string_list(metadata_row.get("knowledge_tags") if metadata_row else assistant_row.get("knowledge_tags")),
        scope=scope,
    )


async def authorize_chat_assistant(chat_body: Any, user: Optional[dict[str, Any]], container: Any) -> Optional[AssistantResolution]:
    """Replace client prompt/tag fields with effective server-authorized values."""
    assistant = getattr(chat_body, "assistant", None)
    slug = getattr(assistant, "slug", None) if assistant is not None else None
    if not slug:
        return None
    resolved = await resolve_effective_assistant(slug, user, container)
    if resolved is None:
        raise HTTPException(status_code=403, detail="Assistant unavailable")
    assistant.slug = resolved.slug
    assistant.system_prompt = resolved.system_prompt
    assistant.knowledge_tags = list(resolved.knowledge_tags)
    return resolved


async def list_visible_assistants(user: Optional[dict[str, Any]], container: Any) -> list[AssistantCatalogItem]:
    client = getattr(container, "supabase_client", None)
    if client is None:
        return []
    try:
        response = await asyncio.to_thread(
            client.table("assistants")
            .select("id, slug, name, description, avatar_url, starter_questions, visibility, created_by")
            .order("name")
            .limit(100)
            .execute
        )
    except Exception as exc:
        logger.warning("Assistant catalog listing failed: %s", type(exc).__name__)
        return []

    visible: list[AssistantCatalogItem] = []
    for row in _rows(response):
        if await _has_access(row, user, container):
            visible.append(
                AssistantCatalogItem(
                    id=str(row.get("id")),
                    slug=str(row.get("slug")),
                    name=str(row.get("name") or row.get("slug")),
                    description=str(row.get("description") or ""),
                    avatar_url=row.get("avatar_url"),
                    starter_questions=_clean_string_list(row.get("starter_questions")),
                    visibility=str(row.get("visibility") or "private"),
                )
            )
    return visible


async def redeem_assistant_invite(invite_code: str, user: Optional[dict[str, Any]], container: Any) -> dict[str, Any]:
    """Redeem a link/private assistant invite without exposing lookup details."""
    uid = _user_id(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Sign in to redeem an assistant invite")
    code = invite_code.strip()
    if not code or len(code) > 256:
        raise HTTPException(status_code=400, detail="Invalid invite")
    client = getattr(container, "supabase_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Assistant access is unavailable")
    try:
        response = await asyncio.to_thread(
            client.table("assistants")
            .select("id, slug, name, visibility")
            .eq("invite_code", code)
            .limit(1)
            .execute
        )
        assistant_row = _row(response)
        if not assistant_row or str(assistant_row.get("visibility") or "public") == "public":
            raise HTTPException(status_code=400, detail="Invalid invite")
        await asyncio.to_thread(
            client.table("assistant_access")
            .upsert(
                {"user_id": uid, "assistant_id": assistant_row.get("id"), "granted_via": "invite"},
                on_conflict="user_id,assistant_id",
            )
            .execute
        )
        return {"slug": assistant_row.get("slug"), "name": assistant_row.get("name")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Assistant invite redemption failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Invalid invite") from exc
