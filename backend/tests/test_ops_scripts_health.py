"""Health of the operational scripts A-36 listed as already broken (2026-11-15).

These run in the repo venv with no live services: the assertions are import and
argument-surface checks, never a Qdrant/Neo4j/provider call.
"""

from __future__ import annotations

import sys

import pytest


def test_resolve_entities_imports_the_client_that_exists():
    """It imported ``SarvamService``, which was renamed to ``SarvamCloudService``."""
    from scripts.ops import resolve_entities as mod
    from services.sarvam_service import SarvamCloudService

    assert mod.SarvamCloudService is SarvamCloudService
    assert not hasattr(mod, "SarvamService")
    assert not hasattr(mod, "SarvamHTTPGateway")


def test_resolve_entities_builds_the_client_without_a_gateway(monkeypatch):
    """``SarvamCloudService()`` takes no gateway; the script used to pass one."""
    from scripts.ops import resolve_entities as mod

    class _FakeService:
        def __init__(self) -> None:
            self.built = True

    monkeypatch.setattr(mod, "SarvamCloudService", _FakeService)
    monkeypatch.setattr(mod, "_llm_service", None)
    mod._init_llm()
    assert isinstance(mod._llm_service, _FakeService)


def test_eval_script_requires_an_explicit_collection_pair(monkeypatch):
    """``first_person_v9`` was purged; a default pair would point at a missing collection."""
    from scripts.ops import eval_v8_vs_v9 as mod

    monkeypatch.setattr(sys, "argv", ["eval_v8_vs_v9.py"])
    with pytest.raises(SystemExit) as excinfo:
        mod.main()
    assert excinfo.value.code == 2
