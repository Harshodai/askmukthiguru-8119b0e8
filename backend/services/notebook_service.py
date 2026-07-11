"""Notebook service — persistent study notebooks for saving QA turns.

CRUD for study_notebooks (metadata) and study_notebook_items (saved turns).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings  # noqa: F401

logger = logging.getLogger(__name__)

_TABLE = "study_notebooks"
_ITEMS = "study_notebook_items"


class NotebookService:
    def __init__(self, supabase_client: Optional[Any] = None) -> None:
        self._client = supabase_client

    @property
    def available(self) -> bool:
        return self._client is not None

    async def create(self, user_id: str, title: str) -> dict | None:
        if not self.available:
            return None
        try:
            resp = self._client.table(_TABLE).insert({
                "user_id": user_id,
                "title": title,
            }).execute()
            data = getattr(resp, "data", None) or []
            return data[0] if data else None
        except Exception as e:
            logger.warning("notebook.create failed: %s", e)
            return None

    async def list(self, user_id: str) -> list[dict]:
        if not self.available:
            return []
        try:
            resp = self._client.table(_TABLE).select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            return list(getattr(resp, "data", None) or [])
        except Exception as e:
            logger.warning("notebook.list failed: %s", e)
            return []

    async def delete(self, user_id: str, notebook_id: str) -> bool:
        if not self.available:
            return False
        try:
            # RLS ensures user only deletes own notebook; cascade deletes items
            self._client.table(_TABLE).delete().eq("id", notebook_id).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.warning("notebook.delete failed: %s", e)
            return False

    async def add_item(
        self,
        user_id: str,
        notebook_id: str,
        query: str,
        answer: str,
        citations: Optional[list[dict]] = None,
        source_episode_id: Optional[str] = None,
    ) -> dict | None:
        if not self.available:
            return None
        try:
            verify = self._client.table(_TABLE).select("id").eq("id", notebook_id).eq("user_id", user_id).execute()
            if not getattr(verify, "data", None):
                logger.warning("notebook.add_item: notebook %s not owned by %s", notebook_id, user_id)
                return None
            resp = self._client.table(_ITEMS).insert({
                "notebook_id": notebook_id,
                "query": query,
                "answer": answer,
                "citations": citations or [],
                "source_episode_id": source_episode_id,
            }).execute()
            data = getattr(resp, "data", None) or []
            return data[0] if data else None
        except Exception as e:
            logger.warning("notebook.add_item failed: %s", e)
            return None

    async def list_items(self, user_id: str, notebook_id: str, limit: int = 50) -> list[dict]:
        if not self.available:
            return []
        try:
            verify = self._client.table(_TABLE).select("id").eq("id", notebook_id).eq("user_id", user_id).execute()
            if not getattr(verify, "data", None):
                logger.warning("notebook.list_items: notebook %s not owned by %s", notebook_id, user_id)
                return []
            resp = self._client.table(_ITEMS).select("*").eq("notebook_id", notebook_id).order("created_at", desc=True).limit(limit).execute()
            return list(getattr(resp, "data", None) or [])
        except Exception as e:
            logger.warning("notebook.list_items failed: %s", e)
            return []


if __name__ == "__main__":  # ponytail: self-check
    import asyncio

    class _MockResp:
        def __init__(self, data): self.data = data

    class _MockTable:
        def __init__(self, *_): pass
        def insert(self, _): return self
        def select(self, *_): return self
        def eq(self, *_): return self
        def order(self, *_): return self
        def limit(self, *_): return self
        def delete(self): return self
        def execute(self): return _MockResp([{"id": "nb1"}])

    class _MockClient:
        def table(self, _): return _MockTable()

    async def _demo():
        svc = NotebookService(_MockClient())
        assert (await svc.create("u1", "My Notebook"))["id"] == "nb1"
        assert len(await svc.list("u1")) == 1
        assert (await svc.add_item("u1", "nb1", "q", "a"))["id"] == "nb1"
        assert await svc.delete("u1", "nb1")
        print("notebook_service OK")

    asyncio.run(_demo())
