from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.assistant_authorization import resolve_effective_assistant
from app.assistant_registry import AssistantScope


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name: str, rows: dict[str, list[dict]]):
        self.table_name = table_name
        self.rows = rows

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def limit(self, _limit):
        return self

    def order(self, _field):
        return self

    def execute(self):
        return _Result(self.rows.get(self.table_name, []))


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def table(self, table_name):
        return _Query(table_name, self.rows)


@pytest.mark.asyncio
async def test_public_database_assistant_resolves_only_approved_scope(monkeypatch):
    monkeypatch.setattr(
        "app.assistant_authorization.resolve_assistant_scope",
        lambda _slug: None,
    )
    container = SimpleNamespace(
        supabase_client=_Client(
            {
                "assistants": [
                    {
                        "id": "a1",
                        "slug": "relationship",
                        "name": "Relationship Guide",
                        "description": "",
                        "visibility": "public",
                        "system_prompt": "server prompt",
                        "knowledge_tags": ["relationships"],
                        "created_by": None,
                    }
                ],
                "assistant_scope_metadata": [
                    {
                        "corpus_id": "relationship-corpus",
                        "rights_status": "approved",
                        "rollout_enabled": True,
                        "knowledge_tags": ["relationships"],
                    }
                ],
            }
        )
    )

    result = await resolve_effective_assistant("relationship", None, container)

    assert result is not None
    assert result.scope.corpus_id == "relationship-corpus"
    assert result.system_prompt == "server prompt"
    assert result.knowledge_tags == ("relationships",)


@pytest.mark.asyncio
async def test_private_database_assistant_denies_anonymous_and_pending_scope(monkeypatch):
    monkeypatch.setattr(
        "app.assistant_authorization.resolve_assistant_scope",
        lambda _slug: None,
    )
    rows = {
        "assistants": [
            {
                "id": "a2",
                "slug": "sky",
                "name": "Sky",
                "description": "",
                "visibility": "link",
                "system_prompt": "private prompt",
                "knowledge_tags": [],
                "created_by": None,
            }
        ],
        "assistant_scope_metadata": [
            {
                "corpus_id": "sky-private",
                "rights_status": "pending",
                "rollout_enabled": False,
                "knowledge_tags": [],
            }
        ],
    }
    container = SimpleNamespace(supabase_client=_Client(rows))

    assert await resolve_effective_assistant("sky", None, container) is None


@pytest.mark.asyncio
async def test_builtin_scope_does_not_require_supabase(monkeypatch):
    monkeypatch.setattr(
        "app.assistant_authorization.resolve_assistant_scope",
        lambda slug: AssistantScope(corpus_id="builtin-corpus") if slug == "guru" else None,
    )

    result = await resolve_effective_assistant("guru", {"id": "anonymous"}, SimpleNamespace())

    assert result is not None
    assert result.scope.corpus_id == "builtin-corpus"
    assert result.assistant_id is None
