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
        now = datetime.now(UTC).isoformat()
        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "consent_version": consent_version,
            "granted": granted,
            "created_at": now,
            "revoked_at": None if granted else now,
        }
        query = self._client.table("memory_consent_receipts").upsert(
            payload,
            on_conflict="user_id,tenant_id,consent_version",
        )
        rows = self._rows(await self._execute(query))
        return rows[0] if rows else payload

    async def active_consent(
        self,
        *,
        user_id: str,
        tenant_id: str,
        consent_version: str = DEFAULT_CONSENT_VERSION,
    ) -> dict[str, Any] | None:
        query = self._client.table("memory_consent_receipts").select(
            "id,user_id,tenant_id,consent_version,granted,revoked_at"
        )
        query = query.eq("user_id", user_id).eq("tenant_id", tenant_id)
        query = query.eq("consent_version", consent_version).eq("granted", True)
        query = query.is_("revoked_at", "null").limit(1)
        rows = self._rows(await self._execute(query))
        return rows[0] if rows else None

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


__all__ = ["DEFAULT_CONSENT_VERSION", "MemoryOutbox", "MemoryOutboxError"]
