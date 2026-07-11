"""Tests for NotebookService — round-trip against a mocked Supabase client."""

from __future__ import annotations

import asyncio

import pytest

from services.notebook_service import NotebookService


class _MockResp:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _MockTable:
    def __init__(self, store: list[dict], insert_data: list[dict]) -> None:
        self._store = store
        self._insert_data = insert_data
        self._row: dict | None = None
        self._filters: dict = {}
        self._eq_chain: list[tuple[str, str]] = []
        self._order_desc = False
        self._limit: int | None = None

    def insert(self, row: dict) -> "_MockTable":
        self._row = row
        return self

    def select(self, *_args) -> "_MockTable":
        return self

    def eq(self, col: str, val: str) -> "_MockTable":
        self._filters[col] = val
        self._eq_chain.append((col, val))
        return self

    def order(self, _col: str, desc: bool = False) -> "_MockTable":
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_MockTable":
        self._limit = n
        return self

    def delete(self) -> "_MockTable":
        return self

    def execute(self) -> _MockResp:
        if self._row is not None:
            row = dict(self._row)
            row.setdefault("id", "nb1")
            row.setdefault("created_at", "2026-06-30T00:00:00+00:00")
            self._store.append(row)
            self._insert_data.append(row)
            return _MockResp([row])

        # select / list path
        rows = [r for r in self._store if all(r.get(k) == v for k, v in self._filters.items())]
        if self._order_desc:
            rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _MockResp(rows)


class _MockClient:
    def __init__(self) -> None:
        self.store: list[dict] = []
        self.insert_data: list[dict] = []

    def table(self, _name: str) -> _MockTable:
        return _MockTable(self.store, self.insert_data)


@pytest.mark.unit
def test_create_and_list_notebook() -> None:
    client = _MockClient()
    svc = NotebookService(supabase_client=client)

    created = asyncio.run(svc.create("u1", "My Notebook"))
    assert created is not None
    assert created["id"] == "nb1"

    notebooks = asyncio.run(svc.list("u1"))
    assert len(notebooks) == 1


@pytest.mark.unit
def test_delete_notebook() -> None:
    client = _MockClient()
    svc = NotebookService(supabase_client=client)
    asyncio.run(svc.create("u1", "To Delete"))

    assert asyncio.run(svc.delete("u1", "nb1"))
    # Our mock delete is a no-op; it only checks no exception is raised


@pytest.mark.unit
def test_add_and_list_items() -> None:
    client = _MockClient()
    svc = NotebookService(supabase_client=client)

    asyncio.run(svc.create("u1", "My Notebook"))

    item = asyncio.run(svc.add_item("u1", "nb1", "What is oneness?", "It is union.", [{"q": "x"}], "ep1"))
    assert item is not None
    assert item["id"] == "nb1"

    items = asyncio.run(svc.list_items("u1", "nb1"))
    assert len(items) == 1


@pytest.mark.unit
def test_no_client_degrades_gracefully() -> None:
    svc = NotebookService(supabase_client=None)
    assert not svc.available
    assert asyncio.run(svc.create("u1", "t")) is None
    assert asyncio.run(svc.list("u1")) == []
    assert not asyncio.run(svc.delete("u1", "nb1"))
    assert asyncio.run(svc.add_item("u1", "nb1", "q", "a")) is None
    assert asyncio.run(svc.list_items("u1", "nb1")) == []
