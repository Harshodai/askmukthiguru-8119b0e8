"""Regression tests for server-authoritative assistant corpus scope resolution."""
from __future__ import annotations

import json

from app import assistant_registry
from app.config import settings


def _set_registry(monkeypatch, *, slugs: str, registry: dict) -> None:
    monkeypatch.setattr(settings, "allowed_assistant_slugs", slugs)
    monkeypatch.setattr(settings, "assistant_corpus_registry", json.dumps(registry))
    assistant_registry._allowed_slugs.cache_clear()
    assistant_registry._scope_registry.cache_clear()


def test_resolve_assistant_scope_uses_server_registry(monkeypatch):
    _set_registry(
        monkeypatch,
        slugs="guru,preethaji",
        registry={
            "guru": {"corpus_id": "public-core"},
            "preethaji": {"corpus_id": "preethaji-approved", "teacher_id": "preethaji"},
        },
    )

    scope = assistant_registry.resolve_assistant_scope("preethaji")

    assert scope is not None
    assert scope.corpus_id == "preethaji-approved"
    assert scope.teacher_id == "preethaji"


def test_unknown_or_unmapped_slug_fails_closed(monkeypatch):
    _set_registry(monkeypatch, slugs="guru,preethaji", registry={"guru": {}})

    assert assistant_registry.resolve_assistant_scope("attacker") is None
    assert assistant_registry.resolve_assistant_scope("preethaji") is None


def test_missing_persona_uses_default_public_corpus(monkeypatch):
    _set_registry(monkeypatch, slugs="guru", registry={"guru": {}})
    monkeypatch.setattr(settings, "default_corpus_id", "askmukthiguru")

    scope = assistant_registry.resolve_assistant_scope(None)

    assert scope is not None
    assert scope.corpus_id == "askmukthiguru"
    assert scope.teacher_id is None
