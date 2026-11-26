"""Consent gate and persistence for seeker comprehension signals and seen-clip signals.

Both are personal learning signals. Nothing is read or written unless the request is an
authenticated, non-incognito, non-benchmark one with an active memory consent receipt.
Any lookup failure means "no consent" (fail closed).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from services.first_person_seen_store import clear_seen_clips
from services.seeker.comprehension_recovery import ComprehensionRecoveryService
from services.tenant_context import TenantContext
from services.user_profile_service import _is_persistable_user_id

logger = logging.getLogger(__name__)

SIGNALS_TABLE = "seeker_comprehension_signals"
_CONSENT_ERRORS = (RuntimeError, OSError, ConnectionError, TimeoutError, ValueError, KeyError)
_CONFUSION_CUES = (
    "didn't understand",
    "did not understand",
    "don't get",
    "explain differently",
    "confused",
    "simpler",
)


async def active_consent_receipt_id(ctx: Any, container: Any) -> str | None:
    """Receipt id when this turn may touch personal learning signals, else None."""
    if getattr(ctx, "incognito", False) or getattr(ctx, "is_benchmark", False):
        return None
    user_id = getattr(ctx, "user_id", None)
    if not user_id or not _is_persistable_user_id(user_id):
        return None
    outbox = getattr(container, "memory_outbox", None)
    tenant_id = TenantContext.get()
    if outbox is None or not tenant_id:
        return None
    try:
        receipt = await outbox.active_consent(user_id=str(user_id), tenant_id=tenant_id)
    except _CONSENT_ERRORS as exc:
        logger.warning(
            "Seeker consent lookup failed (%s); treating as no consent", type(exc).__name__
        )
        return None
    return str(receipt["id"]) if receipt and receipt.get("id") else None


def is_confusion_turn(user_msg: str) -> bool:
    low = (user_msg or "").lower()
    return any(c in low for c in _CONFUSION_CUES)


def _insert_signal(client: Any, receipt_id: str, payload: dict[str, Any]) -> bool:
    # Only structured fields: no question text. Scoped by user, tenant and consent receipt.
    row = {**payload, "consent_receipt_id": receipt_id}
    client.table(SIGNALS_TABLE).insert(row).execute()
    return True


async def record_comprehension_signal(
    ctx: Any, container: Any, citations: list[dict[str, Any]]
) -> bool:
    """Flag-gated, consent-gated, observational: never alters the served answer."""
    if not getattr(settings, "seeker_comprehension_recovery_enabled", False):
        return False
    if not is_confusion_turn(getattr(ctx, "user_msg", "")):
        return False
    client = getattr(container, "supabase_client", None)
    receipt_id = await active_consent_receipt_id(ctx, container)
    if client is None or receipt_id is None:
        return False
    from domain.evidence_contract import EvidenceCandidate

    # Candidates are the clips this turn already served (already fully gated, verbatim).
    served = [
        EvidenceCandidate(
            evidence_id=str(c.get("id") or c.get("clip_id") or c.get("chunk_id")),
            source_id=str(c.get("videoId") or c.get("video_id") or ""),
            text=str(c.get("text") or c.get("verbatim_text") or ""),
            retrieval_source="first_person_served",
        )
        for c in citations
        if (c.get("id") or c.get("clip_id") or c.get("chunk_id"))
    ]
    concept = str((citations[0].get("concept") if citations else "") or "unspecified")
    service = ComprehensionRecoveryService(
        retrieve_fn=lambda _concept, _exclude: served,
        signal_sink=lambda payload: _insert_signal(client, receipt_id, payload),
    )
    result = await asyncio.to_thread(
        service.recover,
        concept=concept,
        user_query="",
        prior_evidence_ids=[],
        user_id=str(ctx.user_id),
        tenant_id=TenantContext.get() or "",
        consent_granted=True,
    )
    return result.learning_signal_recorded


async def erase_seeker_signals(container: Any, user_id: str, tenant_id: str) -> None:
    """Revocation/erasure: drop comprehension signals and seen-clip signals for the user."""
    client = getattr(container, "supabase_client", None)
    if client is None:
        raise RuntimeError("comprehension signal store unavailable")

    def _delete() -> None:
        client.table(SIGNALS_TABLE).delete().eq("user_id", user_id).eq(
            "tenant_id", tenant_id
        ).execute()

    await asyncio.to_thread(_delete)
    # Seen-clip keys use the bridge's tenant label ("default" when unset).
    redis_client = getattr(container, "redis_client", None)
    for tid in {tenant_id, "default"}:
        await asyncio.to_thread(clear_seen_clips, user_id, tid, redis_client)
