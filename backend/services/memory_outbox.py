"""Durable queue and consent ledger for asynchronous memory persistence."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

MAX_PAYLOAD_BYTES = 256_000
DEFAULT_CONSENT_VERSION = "memory-v1"


class MemoryOutboxError(RuntimeError):
    """Raised when durable memory intent cannot safely be persisted."""


class MemoryOutbox:
    """Async façade over the synchronous Supabase client used by the backend."""

    def __init__(self, *, supabase_client: Any, worker_id: str | None = None) -> None:
        if supabase_client is None:
            raise ValueError("supabase_client is required for MemoryOutbox")
        self._client = supabase_client
        configured_worker_id = os.environ.get("MEMORY_OUTBOX_WORKER_ID")
        self._worker_id = worker_id or configured_worker_id or f"api-{uuid.uuid4()}"

    async def _execute(self, query: Any) -> Any:
        """Execute Supabase queries off the event loop."""
        result = await asyncio.to_thread(query.execute)
        return await result if inspect.isawaitable(result) else result

    @staticmethod
    def _rows(result: Any) -> list[dict[str, Any]]:
        rows = getattr(result, "data", result) or []
        return [rows] if isinstance(rows, dict) else list(rows)

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        required = {"user_message", "assistant_answer", "citations", "intent"}
        missing = required - set(payload)
        if missing:
            names = ", ".join(sorted(missing))
            raise MemoryOutboxError(f"missing memory outbox payload fields: {names}")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise MemoryOutboxError("memory outbox payload exceeds 256 KB limit")

    async def record_consent(
        self,
        *,
        user_id: str,
        tenant_id: str,
        granted: bool,
        consent_version: str = DEFAULT_CONSENT_VERSION,
    ) -> dict[str, Any]:
        """Append a consent event; never overwrite the prior grant/revocation.

        The latest receipt is authoritative. Replacing a single row on conflict
        loses the revocation timeline and can make later audit/export claims
        unverifiable.
        """
        now = datetime.now(UTC).isoformat()
        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "consent_version": consent_version,
            "granted": bool(granted),
            "created_at": now,
            "revoked_at": None if granted else now,
        }
        rows = self._rows(
            await self._execute(self._client.table("memory_consent_receipts").insert(payload))
        )
        if not rows:
            raise MemoryOutboxError("Supabase did not return a consent receipt")
        return rows[0]

    async def active_consent(
        self,
        *,
        user_id: str,
        tenant_id: str,
        consent_version: str = DEFAULT_CONSENT_VERSION,
    ) -> dict[str, Any] | None:
        """Return the latest receipt only when that latest event is an active grant.

        Do not filter granted=true before ordering: that would resurrect an
        older grant after a newer revocation.
        """
        query = self._client.table("memory_consent_receipts").select(
            "id,user_id,tenant_id,consent_version,granted,revoked_at,created_at,event_sequence"
        )
        query = query.eq("user_id", user_id).eq("tenant_id", tenant_id)
        query = query.eq("consent_version", consent_version)
        query = query.order("event_sequence", desc=True).limit(1)
        rows = self._rows(await self._execute(query))
        if not rows:
            return None
        latest = rows[0]
        if latest.get("granted") is not True or latest.get("revoked_at") is not None:
            return None
        return latest

    async def get_consent_history(
        self,
        user_id: str,
        *,
        tenant_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Export bounded consent history for a single user, optionally one tenant."""
        query = (
            self._client.table("memory_consent_receipts")
            .select(
                "id,user_id,tenant_id,consent_version,granted,created_at,revoked_at,event_sequence"
            )
            .eq("user_id", user_id)
        )
        if tenant_id is not None:
            query = query.eq("tenant_id", tenant_id)
        query = query.order("event_sequence", desc=True)
        query = query.limit(max(1, min(int(limit), 1000)))
        return self._rows(await self._execute(query))

    async def enqueue(
        self,
        *,
        user_id: str,
        tenant_id: str,
        session_id: str,
        payload: dict[str, Any],
        consent_receipt_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist pending intent before any non-durable extraction begins."""
        self._validate_payload(payload)
        active_receipt = await self.active_consent(user_id=user_id, tenant_id=tenant_id)
        if active_receipt is None:
            raise MemoryOutboxError("active memory consent is required before enqueue")
        active_receipt_id = str(active_receipt.get("id") or "")
        if not active_receipt_id:
            raise MemoryOutboxError("active memory consent has no receipt ID")
        if consent_receipt_id is not None and str(consent_receipt_id) != active_receipt_id:
            raise MemoryOutboxError("memory consent receipt changed before enqueue")
        row = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "payload": payload,
            "consent_receipt_id": active_receipt_id,
            "status": "pending",
        }
        rows = self._rows(await self._execute(self._client.table("memory_outbox").insert(row)))
        if not rows:
            raise MemoryOutboxError("Supabase did not return an outbox receipt")
        return rows[0]

    async def get_pending(self, *, limit: int = 50) -> list[dict[str, Any]]:
        query = self._client.rpc(
            "claim_memory_outbox",
            {"p_worker_id": self._worker_id, "p_limit": max(1, min(limit, 100))},
        )
        return self._rows(await self._execute(query))

    async def mark_processed(self, outbox_id: str) -> None:
        values = {
            "status": "done",
            "payload": {},
            "processed_at": datetime.now(UTC).isoformat(),
            "error": None,
            "locked_at": None,
            "locked_by": None,
        }
        query = self._client.table("memory_outbox").update(values)
        query = query.eq("id", outbox_id).eq("locked_by", self._worker_id)
        await self._execute(query)

    async def mark_step_done(self, outbox_id: str, steps: list[str]) -> None:
        """Persist which enrichment sub-steps have already committed.

        AMK-C-005: the drain loop's side effects are not individually
        idempotent, so a row reclaimed after a worker crash would otherwise
        re-run every write. Recording progress lets the reclaim RESUME.

        A plain overwrite is safe here rather than an array_append RPC:
        ``claim_memory_outbox`` hands the row to exactly one worker, and the
        ``locked_by`` guard below means a worker whose lock was stolen by the
        staleness reclaim silently writes nothing instead of clobbering the
        new owner's progress.
        """
        values = {"completed_steps": sorted(set(steps))}
        query = self._client.table("memory_outbox").update(values)
        query = query.eq("id", outbox_id).eq("locked_by", self._worker_id)
        await self._execute(query)

    async def mark_failed(self, outbox_id: str, error: str) -> None:
        values = {
            "status": "failed",
            # Never persist exception text that may embed user prompt/context.
            "payload": {},
            "error": "memory_outbox_processing_failed",
            "processed_at": datetime.now(UTC).isoformat(),
            "locked_at": None,
            "locked_by": None,
        }
        query = self._client.table("memory_outbox").update(values)
        query = query.eq("id", outbox_id).eq("locked_by", self._worker_id)
        await self._execute(query)

    async def delete_user_rows(self, *, user_id: str, tenant_id: str | None) -> int:
        """Delete queued intents for one tenant, or every tenant when None.

        Consent revocation passes a concrete tenant. Whole-account erasure passes
        None because an account-level delete must not leave another tenant's
        pending extraction payload available for a worker to process.
        """
        query = self._client.table("memory_outbox").delete().eq("user_id", user_id)
        if tenant_id is not None:
            query = query.eq("tenant_id", tenant_id)
        # Supabase mutations return no rows unless select() is requested.
        # Without it account-erasure receipts incorrectly reported zero
        # queued payloads as deleted.
        query = query.select("id")
        return len(self._rows(await self._execute(query)))

    async def write_deletion_receipt(
        self,
        *,
        user_id: str,
        tenant_id: str,
        store_counts: dict[str, int],
        status: str = "completed",
        error: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "store_counts": store_counts,
            "status": status,
            "error": error[:1000] if error else None,
        }
        rows = self._rows(
            await self._execute(self._client.table("memory_deletion_receipts").insert(row))
        )
        return rows[0] if rows else row


__all__ = ["DEFAULT_CONSENT_VERSION", "MemoryOutbox", "MemoryOutboxError"]
