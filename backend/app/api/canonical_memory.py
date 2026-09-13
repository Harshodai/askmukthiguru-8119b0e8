"""Canonical Memory REST API — Phase 12 of the Adaptive Memory System.

Provides authenticated CRUD for the canonical_memories table plus consent
management and GDPR export. Every endpoint enforces Supabase JWT auth and
user_id ownership via RLS + server-side filter (defense-in-depth).

Endpoints:
    GET    /memory/canonical          — list user's memories (paginated, filterable)
    POST   /memory/canonical          — add explicit memory
    PUT    /memory/canonical/{id}     — edit memory text
    DELETE /memory/canonical/{id}     — forget specific memory (soft-delete)
    DELETE /memory/canonical          — forget all memories (hard-delete for user)
    GET    /memory/canonical/reasons  — why was this remembered?
    POST   /memory/consent            — manage consent
    GET    /memory/export             — GDPR export
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["CanonicalMemory"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CanonicalMemoryCreate(BaseModel):
    """Payload for POST /memory/canonical."""
    statement: str = Field(
        ..., min_length=2, max_length=1000,
        description="Natural-language fact about the user.",
    )
    memory_type: str = Field(
        default="USER_EXPLICIT",
        description="Memory type (PROFILE, PREFERENCE, USER_EXPLICIT, etc.).",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.8, ge=0.0, le=1.0)
    sensitivity: str = Field(default="normal")
    fact_key: Optional[str] = Field(default=None)


class CanonicalMemoryUpdate(BaseModel):
    """Payload for PUT /memory/canonical/{id}."""
    statement: str = Field(
        ..., min_length=2, max_length=1000,
        description="Updated natural-language fact.",
    )
    version: Optional[int] = Field(
        default=None,
        description="Expected version for optimistic concurrency. If omitted, "
                    "version check is skipped (user-initiated edit).",
    )
    # update_canonical_memory reads body.fact_key and writes it into
    # update_fields. Without the field declared here every successful PUT
    # raised AttributeError on the pydantic model and returned 500 — the
    # endpoint could not complete an update at all. Mirrors
    # CanonicalMemoryCreate.fact_key.
    fact_key: Optional[str] = Field(default=None)


class CanonicalMemoryResponse(BaseModel):
    """Single memory returned by list/detail endpoints."""
    id: str
    statement: str
    memory_type: str
    confidence: float
    importance: float
    sensitivity: str
    status: str
    fact_key: Optional[str] = None
    evidence_count: int = 1
    extraction_method: str = "user_explicit"
    source_conversation_id: Optional[str] = None
    created_at: str
    updated_at: str
    last_used_at: Optional[str] = None
    version: int = 1


class CanonicalMemoryListResponse(BaseModel):
    """Paginated list of memories."""
    memories: list[CanonicalMemoryResponse]
    total: int
    page: int
    page_size: int


class CanonicalMemoryReasonResponse(BaseModel):
    """Why was a specific memory remembered."""
    memory_id: str
    statement: str
    memory_type: str
    confidence: float
    extraction_method: str
    evidence: Optional[str] = None
    source_conversation_id: Optional[str] = None
    source_turn_index: Optional[int] = None
    created_at: str
    last_confirmed_at: Optional[str] = None
    evidence_count: int = 1


class ConsentRequest(BaseModel):
    """Payload for POST /memory/consent."""
    granted: bool
    consent_version: str = "memory-v1"


class GDPRExportResponse(BaseModel):
    """GDPR data export."""
    user_id: str
    exported_at: str
    memories: list[dict[str, Any]]
    consent_receipts: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    total_memories: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_supabase(container: ServiceContainer):
    """Get the Supabase client or raise 501."""
    client = getattr(container, "supabase_client", None)
    if client is None:
        raise HTTPException(status_code=501, detail="Database not available")
    return client


def _row_to_response(row: dict) -> CanonicalMemoryResponse:
    """Convert a Supabase row dict to the API response model."""
    def _iso(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        try:
            return val.isoformat()
        except Exception:
            return str(val)

    return CanonicalMemoryResponse(
        id=str(row.get("id", "")),
        statement=row.get("statement", ""),
        memory_type=row.get("memory_type", "USER_EXPLICIT"),
        confidence=float(row.get("confidence", 0.75)),
        importance=float(row.get("importance", 0.5)),
        sensitivity=row.get("sensitivity", "normal"),
        status=row.get("status", "active"),
        fact_key=row.get("fact_key"),
        evidence_count=int(row.get("evidence_count", 1)),
        extraction_method=row.get("extraction_method", "user_explicit"),
        source_conversation_id=row.get("source_conversation_id"),
        created_at=_iso(row.get("created_at")),
        updated_at=_iso(row.get("updated_at")),
        last_used_at=_iso(row.get("last_used_at")) if row.get("last_used_at") else None,
        version=int(row.get("version", 1)),
    )


def _validate_uuid(value: str, field_name: str = "id") -> str:
    """Validate and return a UUID string, raising 400 if invalid."""
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return value


# ---------------------------------------------------------------------------
# GET /memory/canonical — list user's memories
# ---------------------------------------------------------------------------


async def _index_memory_vector(container, memory_row: dict) -> None:
    """Embed a memory and upsert it into the canonical vector index.

    Without this the row exists in Postgres but is invisible to retrieval:
    `CanonicalMemoryRetriever` searches Qdrant for semantic candidates and falls
    back to an ILIKE over the statement, which only matches when the seeker
    happens to repeat the memory's own words. Verified 2026-09-12 — two stored
    memories, a directly relevant question, zero retrieved.

    Never raises: the memory is already saved, and a failed index must not turn
    a successful write into an error the way the missing audit table did.
    """
    try:
        integration = getattr(container, "canonical_memory_integration", None)
        if integration is None:
            return
        index = getattr(getattr(integration, "memory_retriever", None), "_vector_index", None)
        embedder = getattr(getattr(integration, "memory_retriever", None), "_embedder", None)
        statement = (memory_row.get("statement") or "").strip()
        if index is None or embedder is None or not statement:
            return
        vector = (await asyncio.to_thread(embedder.encode_batch, [statement]))["dense"][0]
        await index.upsert(
            user_id=str(memory_row["user_id"]),
            memory_id=str(memory_row["id"]),
            vector=list(vector),
            memory_type=memory_row.get("memory_type") or "",
            status=memory_row.get("status") or "active",
        )
        logger.info("Indexed canonical memory %s for retrieval", memory_row["id"])
    except Exception as exc:
        logger.warning("Canonical memory vector index failed (non-fatal): %s", exc)


async def _deindex_memory_vector(container, user_id: str, memory_id: str) -> None:
    """Drop a memory from the vector index. Never raises."""
    try:
        integration = getattr(container, "canonical_memory_integration", None)
        index = getattr(getattr(integration, "memory_retriever", None), "_vector_index", None)
        if index is None:
            return
        await index.delete(user_id=str(user_id), memory_id=str(memory_id))
    except Exception as exc:
        logger.warning("Canonical memory vector de-index failed (non-fatal): %s", exc)


@router.get("/memory/canonical", response_model=CanonicalMemoryListResponse)
async def list_canonical_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    memory_type: Optional[str] = Query(None),
    status: str = Query("active"),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> CanonicalMemoryListResponse:
    """List the authenticated user's canonical memories with pagination and filters.

    Enforces user_id ownership via RLS + server-side filter.
    """
    db = await _get_supabase(container)
    user_id = user["id"]

    try:
        query = (
            db.table("canonical_memories")
            .select("*", count="exact")
            .eq("user_id", user_id)
            .eq("status", status)
        )

        if memory_type:
            valid_types = {
                "PROFILE", "PREFERENCE", "COMMUNICATION_STYLE", "GOAL",
                "PROJECT", "INTEREST", "RELATIONSHIP", "USER_EXPLICIT",
                "TEMPORARY_CONTEXT", "REFLECTION",
            }
            if memory_type.upper() not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid memory_type: {memory_type}. "
                           f"Valid: {', '.join(sorted(valid_types))}",
                )
            query = query.eq("memory_type", memory_type.upper())

        offset = (page - 1) * page_size
        result = await asyncio.to_thread(
            lambda: query.order("updated_at", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = getattr(result, "data", None) or []
        # count may be None when Supabase returns no rows
        total = getattr(result, "count", None) or len(rows)

        return CanonicalMemoryListResponse(
            memories=[_row_to_response(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list canonical memories for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve memories")


# ---------------------------------------------------------------------------
# POST /memory/canonical — add explicit memory
# ---------------------------------------------------------------------------

@router.post("/memory/canonical", response_model=CanonicalMemoryResponse, status_code=201)
async def create_canonical_memory(
    body: CanonicalMemoryCreate,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> CanonicalMemoryResponse:
    """Add a new explicit memory for the authenticated user.

    Validates memory_type, enforces user_id ownership, and writes an
    audit event via the resolver.
    """
    db = await _get_supabase(container)
    user_id = user["id"]

    valid_types = {
        "PROFILE", "PREFERENCE", "COMMUNICATION_STYLE", "GOAL",
        "PROJECT", "INTEREST", "RELATIONSHIP", "USER_EXPLICIT",
        "TEMPORARY_CONTEXT", "REFLECTION",
    }
    mt = body.memory_type.upper()
    if mt not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid memory_type: {body.memory_type}. "
                   f"Valid: {', '.join(sorted(valid_types))}",
        )

    valid_sensitivities = {"normal", "sensitive", "highly_sensitive"}
    if body.sensitivity not in valid_sensitivities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sensitivity: {body.sensitivity}. "
                   f"Valid: {', '.join(sorted(valid_sensitivities))}",
        )

    now = datetime.now(timezone.utc).isoformat()
    statement = body.statement.strip()
    normalized = statement.lower()

    row = {
        "user_id": user_id,
        "tenant_id": "oneness",
        "memory_type": mt,
        "statement": statement,
        "normalized_statement": normalized,
        "fact_key": body.fact_key,
        "confidence": body.confidence,
        "importance": body.importance,
        "sensitivity": body.sensitivity,
        "status": "active",
        "extraction_method": "user_explicit",
        "evidence_count": 1,
        "created_at": now,
        "updated_at": now,
        "valid_from": now,
        "version": 1,
        "metadata": '{"source": "api"}',
    }

    try:
        result = await asyncio.to_thread(
            lambda: db.table("canonical_memories").insert(row).execute()
        )
        inserted = getattr(result, "data", None) or []
        if not inserted:
            raise HTTPException(status_code=500, detail="Failed to create memory")
        created_row = inserted[0]

        # Audit event
        audit_row = {
            "user_id": user_id,
            "memory_id": created_row["id"],
            "event_type": "CREATED",
            "actor": "user",
            "new_version": 1,
            "reason": f"User explicitly asked to remember: {statement[:200]}",
            "created_at": now,
        }
        await asyncio.to_thread(
            lambda: db.table("canonical_memory_events").insert(audit_row).execute()
        )
        await _index_memory_vector(container, created_row)

        return _row_to_response(created_row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create canonical memory for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to save memory")


# ---------------------------------------------------------------------------
# PUT /memory/canonical/{id} — edit memory
# ---------------------------------------------------------------------------

@router.put("/memory/canonical/{memory_id}", response_model=CanonicalMemoryResponse)
async def update_canonical_memory(
    memory_id: str,
    body: CanonicalMemoryUpdate,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> CanonicalMemoryResponse:
    """Edit an existing memory's statement.

    Enforces ownership. If version is provided, uses optimistic concurrency.
    """
    db = await _get_supabase(container)
    user_id = user["id"]
    memory_id = _validate_uuid(memory_id, "memory_id")

    statement = body.statement.strip()
    normalized = statement.lower()
    now = datetime.now(timezone.utc).isoformat()

    try:
        # Fetch existing to verify ownership and optionally check version
        existing = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .select("*")
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        )
        row = getattr(existing, "data", None)
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found or not owned by you")

        if body.version is not None and row.get("version") != body.version:
            raise HTTPException(
                status_code=409,
                detail="Memory was modified by another process. "
                       "Please refresh and try again.",
            )

        new_version = row.get("version", 1) + 1
        update_fields = {
            "statement": statement,
            "normalized_statement": normalized,
            "updated_at": now,
            "version": new_version,
        }
        if body.fact_key is not None:
            update_fields["fact_key"] = body.fact_key

        # Apply update
        result = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .update(update_fields)
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute()
            )
        )

        # Audit event
        audit_row = {
            "user_id": user_id,
            "memory_id": memory_id,
            "event_type": "UPDATED",
            "actor": "user",
            "old_version": row.get("version", 1),
            "new_version": new_version,
            "reason": f"User edited memory via API",
            "created_at": now,
        }
        await asyncio.to_thread(
            lambda: db.table("canonical_memory_events").insert(audit_row).execute()
        )

        # Re-fetch updated row. Ownership is already proven above (the initial
        # select filters on user_id and 404s otherwise), so this filter is
        # defence in depth: it keeps the invariant local, so removing the
        # ownership check upstream can never silently turn this into an IDOR.
        updated = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .select("*")
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        )
        updated_row = getattr(updated, "data", None) or row
        if isinstance(updated_row, list):
            updated_row = updated_row[0] if updated_row else row
        # Re-embed: the statement may have changed, and a stale vector would
        # keep retrieving the memory by its OLD wording.
        await _index_memory_vector(container, updated_row)
        return _row_to_response(updated_row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update canonical memory %s", memory_id)
        raise HTTPException(status_code=500, detail="Failed to update memory")


# ---------------------------------------------------------------------------
# DELETE /memory/canonical/{id} — forget specific memory
# ---------------------------------------------------------------------------

@router.delete("/memory/canonical/{memory_id}")
async def delete_canonical_memory(
    memory_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Soft-delete a specific memory by setting status='deleted'.

    Enforces ownership. Writes an audit event.
    """
    db = await _get_supabase(container)
    user_id = user["id"]
    memory_id = _validate_uuid(memory_id, "memory_id")

    now = datetime.now(timezone.utc).isoformat()

    try:
        # Verify ownership
        existing = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .select("id, version")
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
        )
        row = getattr(existing, "data", None)
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found or not owned by you")

        # Soft-delete
        new_version = row.get("version", 1) + 1
        await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .update({
                    "status": "deleted",
                    "updated_at": now,
                    "version": new_version,
                })
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute()
            )
        )

        # Audit event
        audit_row = {
            "user_id": user_id,
            "memory_id": memory_id,
            "event_type": "DELETED",
            "actor": "user",
            "old_version": row.get("version", 1),
            "new_version": new_version,
            "reason": "User explicitly asked to forget",
            "created_at": now,
        }
        await asyncio.to_thread(
            lambda: db.table("canonical_memory_events").insert(audit_row).execute()
        )
        # A forgotten memory must also leave the vector index, or it keeps being
        # retrieved into the prompt after the seeker asked for it to be gone.
        await _deindex_memory_vector(container, user_id, memory_id)

        return {"status": "ok", "message": "Memory forgotten", "memory_id": memory_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete canonical memory %s", memory_id)
        raise HTTPException(status_code=500, detail="Failed to forget memory")


# ---------------------------------------------------------------------------
# DELETE /memory/canonical — forget all memories
# ---------------------------------------------------------------------------

@router.delete("/memory/canonical")
async def delete_all_canonical_memories(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Hard-delete all canonical memories owned by the user.

    This is a GDPR-aligned operation. Propagates deletion to:
    1. canonical_memories (Postgres)
    2. canonical_memory_events (append-only, marked for user review)
    3. Qdrant canonical_memory_vectors (if vector index exists)
    """
    db = await _get_supabase(container)
    user_id = user["id"]
    now = datetime.now(timezone.utc).isoformat()

    deleted_count = 0
    failures: list[str] = []

    # 1. Delete from canonical_memories
    try:
        result = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .delete()
                .eq("user_id", user_id)
                .execute()
            )
        )
        rows = getattr(result, "data", None) or []
        deleted_count = len(rows)
    except Exception as exc:
        logger.warning("Failed to delete canonical_memories for user %s: %s", user_id, exc)
        failures.append("canonical_memories")

    # 2. Delete from Qdrant (best-effort, non-fatal)
    try:
        memory_service = getattr(container, "memory_service", None)
        if memory_service:
            qdrant = await asyncio.to_thread(memory_service._get_qdrant_v2)
            if qdrant is not None:
                from qdrant_client.http import models as qm

                collection = getattr(memory_service, "_memory_collection", "canonical_memory_vectors")
                selector = qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="user_id", match=qm.MatchValue(value=user_id)
                        ),
                    ]
                )
                await asyncio.to_thread(
                    lambda: qdrant.delete(
                        collection_name=collection,
                        points_selector=selector,
                    )
                )
    except Exception as exc:
        logger.debug("Qdrant cleanup for canonical memory skipped: %s", exc)
        failures.append("qdrant_vectors")

    # 3. Write a consolidated audit event (not per-memory — too many)
    try:
        audit_row = {
            "user_id": user_id,
            "memory_id": "00000000-0000-0000-0000-000000000000",
            "event_type": "DELETED",
            "actor": "user",
            "reason": f"User deleted all canonical memories ({deleted_count} total)",
            "created_at": now,
        }
        await asyncio.to_thread(
            lambda: db.table("canonical_memory_events").insert(audit_row).execute()
        )
    except Exception as exc:
        logger.debug("Audit event write for bulk delete skipped: %s", exc)

    status = "completed" if not failures else "partial_failure"
    return {
        "status": status,
        "deleted": deleted_count,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# GET /memory/canonical/reasons — why was this remembered?
# ---------------------------------------------------------------------------

@router.get("/memory/canonical/reasons", response_model=list[CanonicalMemoryReasonResponse])
async def get_memory_reasons(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> list[CanonicalMemoryReasonResponse]:
    """Return provenance metadata for the user's memories.

    Shows why each memory was created: extraction method, confidence,
    evidence, source conversation, and confirmation count.
    """
    db = await _get_supabase(container)
    user_id = user["id"]

    try:
        result = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .select(
                    "id, statement, memory_type, confidence, extraction_method, "
                    "source_conversation_id, source_turn_index, created_at, "
                    "last_confirmed_at, evidence_count, metadata"
                )
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        )
        rows = getattr(result, "data", None) or []

        reasons = []
        for row in rows:
            meta = row.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}

            reasons.append(CanonicalMemoryReasonResponse(
                memory_id=str(row.get("id", "")),
                statement=row.get("statement", ""),
                memory_type=row.get("memory_type", ""),
                confidence=float(row.get("confidence", 0.75)),
                extraction_method=row.get("extraction_method", "llm"),
                evidence=meta.get("evidence"),
                source_conversation_id=row.get("source_conversation_id"),
                source_turn_index=row.get("source_turn_index"),
                created_at=(
                    row.get("created_at").isoformat()
                    if hasattr(row.get("created_at", ""), "isoformat")
                    else str(row.get("created_at", ""))
                ),
                last_confirmed_at=(
                    row.get("last_confirmed_at").isoformat()
                    if row.get("last_confirmed_at") and hasattr(row.get("last_confirmed_at"), "isoformat")
                    else None
                ),
                evidence_count=int(row.get("evidence_count", 1)),
            ))

        return reasons
    except Exception as exc:
        logger.exception("Failed to retrieve memory reasons for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve memory reasons")


# ---------------------------------------------------------------------------
# POST /memory/consent — manage consent
# ---------------------------------------------------------------------------

@router.post("/memory/consent")
async def manage_canonical_consent(
    body: ConsentRequest,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Record a revocable, versioned consent receipt for canonical memory writes.

    When consent is revoked, all pending outbox rows for this user are deleted.
    """
    from services.tenant_context import TenantContext, get_tenant_id_from_user

    outbox = getattr(container, "memory_outbox", None)
    if outbox is None:
        raise HTTPException(status_code=503, detail="Memory consent service unavailable")

    # Consent must be written under the SAME tenant every consumer reads it
    # under. `MemoryOutbox.active_consent` — the gate that decides whether this
    # seeker's turns may be mined for durable facts — filters on
    # `TenantContext.get()`, while `get_tenant_id_from_user(user)` returns
    # `user["tenant_id"]`, which auth_service.py sets to the user's own UUID.
    # The two never matched, so consent could be granted (200, receipt id and
    # all) and then never found: `active_consent` returned None forever and the
    # write path correctly refused to remember anything. Measured 2026-09-13 —
    # receipt stored with tenant=<user uuid>, looked up with tenant="default".
    #
    # The request tenant is the authority; the per-user value is logged only so
    # the mismatch stays visible rather than silently diverging again.
    tenant_id = TenantContext.get()
    _user_scoped_tenant = get_tenant_id_from_user(user)
    if _user_scoped_tenant != tenant_id:
        logger.info(
            "Consent tenant resolved to %s (user dict carried %s)",
            tenant_id,
            _user_scoped_tenant,
        )

    try:
        receipt = await outbox.record_consent(
            user_id=user["id"],
            tenant_id=tenant_id,
            granted=body.granted,
            consent_version=body.consent_version,
        )
    except Exception as exc:
        logger.exception("Failed to record consent for user %s", user["id"])
        raise HTTPException(status_code=500, detail="Failed to record consent")

    pending_deleted = 0
    if not body.granted:
        try:
            pending_deleted = await outbox.delete_user_rows(
                user_id=user["id"], tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("Failed to purge outbox on consent revoke: %s", exc)

    return {
        "status": "granted" if body.granted else "revoked",
        "receipt_id": receipt.get("id"),
        "consent_version": body.consent_version,
        "pending_outbox_rows_deleted": pending_deleted,
    }


# ---------------------------------------------------------------------------
# GET /memory/export — GDPR export
# ---------------------------------------------------------------------------

@router.get("/memory/export", response_model=GDPRExportResponse)
async def export_canonical_memories(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> GDPRExportResponse:
    """GDPR data export: all memories, consent receipts, and audit events.

    Returns a complete JSON payload the user can download.
    """
    db = await _get_supabase(container)
    user_id = user["id"]
    now = datetime.now(timezone.utc).isoformat()

    try:
        # 1. All memories (any status)
        mem_result = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memories")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
        )
        memories = getattr(mem_result, "data", None) or []

        # 2. Audit events
        events_result = await asyncio.to_thread(
            lambda: (
                db.table("canonical_memory_events")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1000)
                .execute()
            )
        )
        events = getattr(events_result, "data", None) or []

        # 3. Consent receipts (from outbox if available)
        consent_receipts: list[dict] = []
        outbox = getattr(container, "memory_outbox", None)
        if outbox is not None:
            try:
                consent_receipts = await outbox.get_consent_history(user_id)
            except Exception:
                pass  # non-fatal for export

        # Sanitize: remove internal fields, convert datetimes to ISO strings
        def _sanitize_mem(m: dict) -> dict:
            return {
                "id": m.get("id"),
                "statement": m.get("statement"),
                "memory_type": m.get("memory_type"),
                "confidence": m.get("confidence"),
                "importance": m.get("importance"),
                "sensitivity": m.get("sensitivity"),
                "status": m.get("status"),
                "extraction_method": m.get("extraction_method"),
                "created_at": str(m.get("created_at", "")),
                "updated_at": str(m.get("updated_at", "")),
            }

        def _sanitize_event(e: dict) -> dict:
            return {
                "id": e.get("id"),
                "memory_id": e.get("memory_id"),
                "event_type": e.get("event_type"),
                "actor": e.get("actor"),
                "reason": e.get("reason"),
                "created_at": str(e.get("created_at", "")),
            }

        return GDPRExportResponse(
            user_id=user_id,
            exported_at=now,
            memories=[_sanitize_mem(m) for m in memories],
            consent_receipts=consent_receipts,
            audit_events=[_sanitize_event(e) for e in events],
            total_memories=len(memories),
        )
    except Exception as exc:
        logger.exception("GDPR export failed for user %s", user_id)
        raise HTTPException(status_code=500, detail="Export failed")


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("canonical_memory API module loaded OK")
    print("Endpoints:")
    print("  GET    /memory/canonical          — list")
    print("  POST   /memory/canonical          — create")
    print("  PUT    /memory/canonical/{id}     — update")
    print("  DELETE /memory/canonical/{id}     — forget one")
    print("  DELETE /memory/canonical          — forget all")
    print("  GET    /memory/canonical/reasons  — provenance")
    print("  POST   /memory/consent            — consent")
    print("  GET    /memory/export             — GDPR export")
