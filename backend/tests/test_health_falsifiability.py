"""Falsifiability probes for /api/health signals (H-FALSE-2/3/4/5).

Each test asserts the signal actually flips red for the failure it claims
to detect — a health signal that cannot go red for its own failure mode is
the defect class these tests guard against.

H-FALSE-2: fast/standard/deep_graph must report not-ok for a compiled-but-
  broken graph (empty topology / missing serving spine), not just for None.
H-FALSE-3: lightrag must report not-ok when its own circuit breaker is OPEN,
  not only when the latched init flag says degraded.
H-FALSE-4: pinned behavior — warming_up reports ok=True (fast graph serves
  by design) WITH status=warming_up preserved, and critical=False so it
  never gates readiness. The distinction lives in `status`, not `ok`.
H-FALSE-5: the embedding probe must exercise the async path live chat uses
  (encode_single_full_async on _EMBED_EXECUTOR), not the sync one.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.dependencies as _app_deps
from app.api import health as health_module
from app.main import app

client = TestClient(app)


async def _async_true(*args, **kwargs):
    return True


def _base_container(monkeypatch):
    """Healthy-by-default mock container, mirroring tests/test_health.py."""
    monkeypatch.setattr(_app_deps, "startup_complete", True)
    monkeypatch.setattr(health_module, "_check_redis", lambda c: _async_true())
    monkeypatch.setattr(health_module, "_check_neo4j", lambda c: _async_true())
    monkeypatch.setattr(
        health_module,
        "inspect_runtime_artifacts",
        lambda: {"readiness_ok": True, "missing_required": [], "present": 2, "total": 3},
    )
    from app.config import settings as _settings

    mock_container = MagicMock()
    mock_container.qdrant.health_check.return_value = True
    mock_container.ollama.health_check = _async_true
    mock_container.ollama.is_circuit_open = lambda: False
    mock_container.ocr.health_check.return_value = True
    mock_container.embedding.encode_single_full.return_value = {
        "dense": [0.0] * _settings.embedding_dimension
    }
    mock_container.guardrails.is_available = True
    mock_container.guardrails.provider_name = "mock"
    mock_container.exact_cache = MagicMock()
    mock_container.exact_cache.is_available = True
    mock_container.semantic_cache = MagicMock()
    mock_container.semantic_cache.is_available = True
    mock_container.fast_graph = MagicMock()
    mock_container.standard_graph = MagicMock()
    mock_container.deep_graph = MagicMock()
    mock_container.lightrag_degraded = False
    mock_container.graph_warmup_status = "ready"
    mock_container.job_queue = MagicMock()
    mock_container.job_queue.queue_size = 0
    return mock_container


def _get_health(mock_container):
    async def mock_get_container():
        return mock_container

    app.dependency_overrides[_app_deps.get_container] = mock_get_container
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        return response.json()
    finally:
        app.dependency_overrides.pop(_app_deps.get_container, None)


def _spine_nodes():
    return {
        "retrieve_documents": object(),
        "generate_answer": object(),
        "format_final_answer": object(),
        "other": object(),
    }


# --- H-FALSE-2 ---------------------------------------------------------------


def test_hfalse2_empty_topology_reports_not_ok(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.fast_graph = SimpleNamespace(nodes={})
    data = _get_health(mock_container)
    assert data["services"]["fast_graph"]["ok"] is False
    assert data["services"]["fast_graph"]["detail"] == "empty_topology"


def test_hfalse2_missing_spine_node_reports_not_ok(monkeypatch):
    mock_container = _base_container(monkeypatch)
    nodes = _spine_nodes()
    del nodes["generate_answer"]
    mock_container.standard_graph = SimpleNamespace(nodes=nodes)
    data = _get_health(mock_container)
    assert data["services"]["standard_graph"]["ok"] is False
    assert "generate_answer" in data["services"]["standard_graph"]["detail"]


def test_hfalse2_intact_spine_reports_ok(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.fast_graph = SimpleNamespace(nodes=_spine_nodes())
    mock_container.standard_graph = SimpleNamespace(nodes=_spine_nodes())
    mock_container.deep_graph = SimpleNamespace(nodes=_spine_nodes())
    data = _get_health(mock_container)
    assert data["services"]["fast_graph"]["ok"] is True
    assert data["services"]["fast_graph"]["detail"] == "spine_present"
    assert data["status"] == "healthy"


def test_hfalse2_none_graph_still_not_ok(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.deep_graph = None
    data = _get_health(mock_container)
    assert data["services"]["deep_graph"]["ok"] is False


# --- H-FALSE-3 ---------------------------------------------------------------


def test_hfalse3_open_breaker_flips_lightrag_red(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.lightrag_degraded = False  # init flag says healthy ...
    mock_container.lightrag._circuit.is_open = lambda: True  # ... but breaker is OPEN
    data = _get_health(mock_container)
    assert data["services"]["lightrag"]["ok"] is False
    assert data["services"]["lightrag"]["detail"] == "circuit_open"


def test_hfalse3_closed_breaker_keeps_lightrag_green(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.lightrag_degraded = False
    mock_container.lightrag._circuit.is_open = lambda: False
    data = _get_health(mock_container)
    assert data["services"]["lightrag"]["ok"] is True
    # Non-critical: never gates readiness either way.
    assert data["services"]["lightrag"]["critical"] is False


def test_hfalse3_degraded_flag_still_reports_not_ok(monkeypatch):
    mock_container = _base_container(monkeypatch)
    mock_container.lightrag_degraded = True
    data = _get_health(mock_container)
    assert data["services"]["lightrag"]["ok"] is False


# --- H-FALSE-4 (pinned behavior) ----------------------------------------------


def test_hfalse4_warming_up_serves_ok_with_status_preserved(monkeypatch):
    """ok=True during warmup is truthful, not a gap: the fast graph is fully
    built before status flips to warming_up (container.py:789-803) and serves
    by design while optional variants compile. The phase distinction lives in
    `status`; critical=False so it never gates readiness."""
    mock_container = _base_container(monkeypatch)
    mock_container.graph_warmup_status = "warming_up"
    data = _get_health(mock_container)
    assert data["services"]["graph_warmup"]["ok"] is True
    assert data["services"]["graph_warmup"]["status"] == "warming_up"
    assert data["services"]["graph_warmup"]["critical"] is False


# --- H-FALSE-5 -----------------------------------------------------------------


def test_hfalse5_probe_prefers_async_path(monkeypatch):
    """Sync path returns a wrong-dim vector while the async path (live chat's
    path) returns the right one: the probe must report ok. If it used the
    sync path, this would flip red."""
    from app.config import settings as _settings

    mock_container = _base_container(monkeypatch)

    async def async_full(text):
        return {"dense": [0.0] * _settings.embedding_dimension}

    mock_container.embedding.encode_single_full_async = async_full
    mock_container.embedding.encode_single_full.return_value = {"dense": [0.0] * 8}
    data = _get_health(mock_container)
    assert data["services"]["embedding"]["ok"] is True


def test_hfalse5_async_failure_reports_not_ok(monkeypatch):
    from app.config import settings as _settings

    mock_container = _base_container(monkeypatch)

    async def async_full_broken(text):
        return {"dense": [0.0] * 8}

    mock_container.embedding.encode_single_full_async = async_full_broken
    mock_container.embedding.encode_single_full.return_value = {
        "dense": [0.0] * _settings.embedding_dimension
    }
    data = _get_health(mock_container)
    assert data["services"]["embedding"]["ok"] is False
