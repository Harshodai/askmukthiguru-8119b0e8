"""Base Repository — thin wrapper over the Supabase client with audit hooks.

Adapted from zabt.ai's BaseService (SQLModel) for our Supabase-py architecture.
Provides save/get/get_all/delete with pre/post action hooks for audit logging.

Usage:
    class GuruMemoriesRepository(BaseRepository):
        _table = "guru_memories"

    repo = GuruMemoriesRepository(supabase_client)
    record = repo.save({"user_id": uid, "claim": text})
    record = repo.get(record_id)
    records = repo.get_all(user_id, limit=50)
    ok = repo.delete(record_id)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseRepository:
    """Generic Supabase-backed repository with audit hooks.

    Subclasses set `_table` to the Supabase table name and optionally override
    the `on_before_action`/`on_after_action` hooks for audit logging.
    """

    _table: str = ""

    def __init__(self, supabase_client: Any):
        if not self._table:
            raise ValueError(f"{type(self).__name__} must set _table")
        self._client = supabase_client

    def on_before_action(self, action: str, **kwargs: Any) -> None:
        """Pre-event hook for audit logging. Override in subclasses."""
        logger.debug(f"AUDIT [BEFORE] {action} on {self._table}: {kwargs}")

    def on_after_action(self, action: str, result: Any, **kwargs: Any) -> None:
        """Post-event hook for audit logging. Override in subclasses."""
        logger.debug(f"AUDIT [AFTER] {action} on {self._table}: result={result}")

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert a record. Returns the inserted record."""
        self.on_before_action("save", record=record)
        response = self._client.table(self._table).insert(record).execute()
        self.on_after_action("save", result=response.data, record=record)
        return response.data[0] if response.data else {}

    def get(self, record_id: Any) -> Optional[dict[str, Any]]:
        """Get a single record by id."""
        self.on_before_action("get", record_id=record_id)
        response = (
            self._client.table(self._table).select("*").eq("id", record_id).execute()
        )
        result = response.data[0] if response.data else None
        self.on_after_action("get", result=result, record_id=record_id)
        return result

    def get_all(
        self,
        owner_field: str = "user_id",
        owner_id: Any = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get records by owner. Returns up to `limit` records."""
        self.on_before_action(
            "get_all",
            owner_field=owner_field,
            owner_id=owner_id,
            skip=skip,
            limit=limit,
        )
        query = self._client.table(self._table).select("*")
        if owner_id is not None:
            query = query.eq(owner_field, owner_id)
        # Supabase uses range() for pagination: range(start, end) is inclusive
        query = query.range(skip, skip + limit - 1)
        response = query.execute()
        result = response.data or []
        self.on_after_action("get_all", result=result, owner_id=owner_id)
        return result

    def delete(self, record_id: Any) -> bool:
        """Delete a record by id. Returns True if deleted."""
        self.on_before_action("delete", record_id=record_id)
        response = self._client.table(self._table).delete().eq("id", record_id).execute()
        deleted = bool(response.data)
        self.on_after_action("delete", result=deleted, record_id=record_id)
        return deleted

    def update(self, record_id: Any, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Update a record by id. Returns the updated record."""
        self.on_before_action("update", record_id=record_id, updates=updates)
        response = (
            self._client.table(self._table).update(updates).eq("id", record_id).execute()
        )
        result = response.data[0] if response.data else None
        self.on_after_action("update", result=result, record_id=record_id)
        return result


if __name__ == "__main__":
    # Self-check: verify the class is importable and has the expected interface
    import inspect

    expected = {"save", "get", "get_all", "delete", "update", "on_before_action", "on_after_action"}
    actual = {name for name, _ in inspect.getmembers(BaseRepository, predicate=inspect.isfunction)}
    assert expected.issubset(actual), f"Missing methods: {expected - actual}"
    print(f"BaseRepository OK — methods: {sorted(expected)}")