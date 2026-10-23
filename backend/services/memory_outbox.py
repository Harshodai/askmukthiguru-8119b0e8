"""Durable queue and consent ledger for asynchronous memory persistence."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 256_000
DEFAULT_CONSENT_VERSION = "memory-v1"
CONSENT_SOURCE_USER_EXPLICIT = "user_explicit"
CONSENT_SOURCE_AUTO_DEFAULT = "auto_default"


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
        ignore_duplicates: bool = False,
        source: str = CONSENT_SOURCE_USER_EXPLICIT,
    ) -> dict[str, Any]:
        # `source` is provenance, not policy: an auto-created default grant is
        # auditable as such and can never be mistaken for an explicit opt-in.
        now = datetime.now(UTC).isoformat()
        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "consent_version": consent_version,
            "granted": granted,
            "source": source,
            "created_at": now,
            "revoked_at": None if granted else now,
        }
        query = self._client.table("memory_consent_receipts").upsert(
            payload,
            on_conflict="user_id,tenant_id,consent_version",
            ignore_duplicates=ignore_duplicates,
        )
        rows = self._rows(await self._execute(query))
        if ignore_duplicates:
            read_query = (
                self._client.table("memory_consent_receipts")
                .select("id,user_id,tenant_id,consent_version,granted,source,revoked_at")
                .eq("user_id", user_id)
                .eq("tenant_id", tenant_id)
                .eq("consent_version", consent_version)
                .limit(1)
            )
            read_rows = self._rows(await self._execute(read_query))
            if read_rows:
                return read_rows[0]
        return rows[0] if rows else payload

    async def active_consent(
        self,
        *,
        user_id: str,
        tenant_id: str,
        consent_version: str = DEFAULT_CONSENT_VERSION,
        auto_grant_default: bool = False,
    ) -> dict[str, Any] | None:
        query = self._client.table("memory_consent_receipts").select(
            "id,user_id,tenant_id,consent_version,granted,source,revoked_at"
        )
        query = query.eq("user_id", user_id).eq("tenant_id", tenant_id)
        query = query.eq("consent_version", consent_version).limit(1)
        rows = self._rows(await self._execute(query))
        if rows:
            row = rows[0]
            if row.get("granted") and row.get("revoked_at") is None:
                return row
            # Explicitly revoked or granted=False: respect opt-out
            return None

        # When no explicit record exists yet for an authenticated user:
        if (
            auto_grant_default
            and user_id
            and user_id != "anonymous"
            and not user_id.startswith("anon:")
        ):
            try:
                receipt = await self.record_consent(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    granted=True,
                    consent_version=consent_version,
                    ignore_duplicates=True,
                    source=CONSENT_SOURCE_AUTO_DEFAULT,
                )
                if receipt and receipt.get("granted") and receipt.get("revoked_at") is None:
                    return receipt
                return None
            except Exception as exc:
                logger.warning("Auto-consent record failed: %s", exc)
                return None
        return None

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
        row = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "payload": payload,
            "consent_receipt_id": consent_receipt_id,
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
            "processed_at": datetime.now(UTC).isoformat(),
            "error": None,
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
            "error": error.replace("\x00", " ")[:1000],
            "processed_at": datetime.now(UTC).isoformat(),
        }
        query = self._client.table("memory_outbox").update(values)
        query = query.eq("id", outbox_id).eq("locked_by", self._worker_id)
        await self._execute(query)

    async def delete_user_rows(self, *, user_id: str, tenant_id: str) -> int:
        query = self._client.table("memory_outbox").delete()
        query = query.eq("user_id", user_id).eq("tenant_id", tenant_id)
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


__all__ = [
    "CONSENT_SOURCE_AUTO_DEFAULT",
    "CONSENT_SOURCE_USER_EXPLICIT",
    "DEFAULT_CONSENT_VERSION",
    "MemoryOutbox",
    "MemoryOutboxError",
]
