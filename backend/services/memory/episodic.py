"""Episodic memory — verbatim query/answer turn log in Supabase.

Reuses the existing supabase client created in ServiceContainer._build_profiles
(same client handed to MemoryServiceV2). No new client, no auth middleware.
RLS on user_episodes guarantees a user can only read/write their own rows, so
the service trusts the caller-supplied user_id for scoping but never exposes
another user's rows.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TABLE = "user_episodes"


class EpisodicMemoryService:
    """Log and retrieve raw conversation episodes (query + answer + citations)."""

    def __init__(self, supabase_client: Optional[Any] = None) -> None:
        # ponytail: client is optional — service degrades to no-op when Supabase
        # is unconfigured (local/dev), mirroring MemoryServiceV2's pattern.
        self._client = supabase_client

    @property
    def available(self) -> bool:
        return self._client is not None

    async def log_episode(
        self,
        user_id: str,
        query: str,
        answer: str,
        citations: Optional[list[Any]] = None,
        intent: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Insert one episode row. Returns the inserted row, or None on failure."""
        if not self.available or not user_id or user_id == "anonymous":
            return None
        if not query or not answer:
            return None
        import json

        row = {
            "user_id": user_id,
            "query": query,
            "answer": answer,
            "citations": json.dumps(citations or []),
            "intent": intent,
        }
        try:
            # supabase-py client is sync; run the blocking call inline.
            # Episodes are fire-and-forget from the pipeline — latency is acceptable.
            resp = self._client.table(_TABLE).insert(row).execute()
            data = getattr(resp, "data", None) or []
            return data[0] if data else None
        except Exception as e:  # non-fatal: memory must never break the pipeline
            logger.warning(f"episodic.log_episode failed for user {user_id}: {e}")
            return None

    async def retrieve_recent(
        self, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the user's most recent episodes, newest first."""
        if not self.available or not user_id or user_id == "anonymous":
            return []
        limit = max(1, min(limit, 100))
        try:
            resp = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(getattr(resp, "data", None) or [])
        except Exception as e:
            logger.warning(f"episodic.retrieve_recent failed for user {user_id}: {e}")
            return []

    async def search(
        self, user_id: str, q: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring search over the user's episodes (query + answer)."""
        if not self.available or not user_id or user_id == "anonymous" or not q or not q.strip():
            return []
        limit = max(1, min(limit, 100))
        term = f"%{q.strip()}%"
        try:
            # ponytail: ilike over query|answer — no FTS index needed; upgrade to
            # websearch_to_tsvector if substring search becomes a hot path.
            resp = (
                self._client.table(_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .or_(f"query.ilike.{term},answer.ilike.{term}")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(getattr(resp, "data", None) or [])
        except Exception as e:
            logger.warning(f"episodic.search failed for user {user_id}: {e}")
            return []


if __name__ == "__main__":  # ponytail: one runnable self-check
    import asyncio

    class _MockResp:
        def __init__(self, data): self.data = data

    class _MockTable:
        def __init__(self, *_): self._rows = []
        def insert(self, row): self._row = row; return self
        def select(self, *_): return self
        def eq(self, *_): return self
        def or_(self, *_): return self
        def order(self, *_): return self
        def limit(self, *_): return self
        def execute(self): return _MockResp([{"id": "x", **getattr(self, "_row", {"query":"q","answer":"a","user_id":"u"})}])

    class _MockClient:
        def table(self, _): return _MockTable()

    async def _demo():
        svc = EpisodicMemoryService(_MockClient())
        assert (await svc.log_episode("u", "q", "a")) is not None
        assert isinstance(await svc.retrieve_recent("u"), list)
        assert isinstance(await svc.search("u", "q"), list)
        # anonymous + no-client degrade to no-op
        assert await svc.log_episode("anonymous", "q", "a") is None
        assert await EpisodicMemoryService().retrieve_recent("u") == []
        print("episodic OK")

    asyncio.run(_demo())