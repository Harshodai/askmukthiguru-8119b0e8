"""Unit tests for the Architecture Drift Checker.

Phase 3 Ruthless Remediation — Task 5.
Validates that check_architecture_drift accurately enforces architectural contracts:
- Dense embedding dimension == 1024 (BAAI/bge-m3)
- Default Qdrant collection == spiritual_wisdom_contextual
- Pipeline stage order: InputGuardrailStage before CircuitBreakerStage, Cache before router
- Critical chat, memory, and profile routes exist in FastAPI app
- Exits 0 on compliance, non-zero on drift
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from scripts.ops.check_architecture_drift import (
    CRITICAL_ROUTES,
    EXPECTED_EMBEDDING_DIMENSION,
    EXPECTED_EMBEDDING_MODEL,
    EXPECTED_QDRANT_COLLECTION,
    check_architecture_drift,
    check_embedding_contract,
    check_fastapi_routes,
    check_pipeline_stage_order,
    check_qdrant_collection,
    main as drift_main,
)


def test_architecture_drift_passes_on_current_codebase():
    """Verify that current codebase has zero architectural drift."""
    report = check_architecture_drift()
    assert report.ok is True, f"Architectural drift detected: {report.violations}"
    assert len(report.violations) == 0
    assert len(report.checks) == 4
    for check in report.checks:
        assert check.passed is True, f"Check failed: {check.name} - {check.violation}"


def test_embedding_dimension_drift_detected():
    """Verify that any deviation from 1024 embedding dimension is flagged."""
    bad_settings = SimpleNamespace(
        embedding_dimension=384,
        embedding_model=EXPECTED_EMBEDDING_MODEL,
        qdrant_collection=EXPECTED_QDRANT_COLLECTION,
    )
    result = check_embedding_contract(bad_settings)
    assert result.passed is False
    assert "Dense embedding dimension drift" in (result.violation or "")
    assert "384" in (result.violation or "")


def test_embedding_model_drift_detected():
    """Verify that any deviation from BAAI/bge-m3 model is flagged."""
    bad_settings = SimpleNamespace(
        embedding_dimension=EXPECTED_EMBEDDING_DIMENSION,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        qdrant_collection=EXPECTED_QDRANT_COLLECTION,
    )
    result = check_embedding_contract(bad_settings)
    assert result.passed is False
    assert "Embedding model drift" in (result.violation or "")
    assert "sentence-transformers/all-MiniLM-L6-v2" in (result.violation or "")


def test_qdrant_collection_drift_detected():
    """Verify that any deviation from spiritual_wisdom_contextual is flagged."""
    bad_settings = SimpleNamespace(
        embedding_dimension=EXPECTED_EMBEDDING_DIMENSION,
        embedding_model=EXPECTED_EMBEDDING_MODEL,
        qdrant_collection="spiritual_wisdom_legacy",
    )
    result = check_qdrant_collection(bad_settings)
    assert result.passed is False
    assert "Expected default collection 'spiritual_wisdom_contextual'" in (result.violation or "")


def test_pipeline_order_drift_circuit_breaker_before_guardrails():
    """Verify that running CircuitBreakerStage before InputGuardrailStage is caught."""
    # Synthetic stages mimicking bad pipeline order
    class CircuitBreakerStage:
        pass

    class InputGuardrailStage:
        pass

    class CacheCheckStage:
        pass

    class GraphStage:
        pass

    bad_pipeline = [
        CacheCheckStage(),
        CircuitBreakerStage(),  # Inverted: circuit breaker before input guardrails
        InputGuardrailStage(),
        GraphStage(),
    ]
    result = check_pipeline_stage_order(bad_pipeline)
    assert result.passed is False
    assert "Safety order violation" in (result.violation or "")
    assert "InputGuardrailStage" in (result.violation or "")


def test_pipeline_order_drift_router_before_cache():
    """Verify that running a router/short-circuit before CacheCheckStage is caught."""
    class CasualShortCircuitStage:
        pass

    class CacheCheckStage:
        pass

    class InputGuardrailStage:
        pass

    class CircuitBreakerStage:
        pass

    bad_pipeline = [
        CasualShortCircuitStage(),  # Inverted: router before cache
        CacheCheckStage(),
        InputGuardrailStage(),
        CircuitBreakerStage(),
    ]
    result = check_pipeline_stage_order(bad_pipeline)
    assert result.passed is False
    assert "Cache order violation" in (result.violation or "")


def test_pipeline_missing_mandatory_stages():
    """Verify that omitting InputGuardrailStage or CircuitBreakerStage fails the check."""
    class CacheCheckStage:
        pass

    class GraphStage:
        pass

    incomplete_pipeline = [
        CacheCheckStage(),
        GraphStage(),
    ]
    result = check_pipeline_stage_order(incomplete_pipeline)
    assert result.passed is False
    assert "InputGuardrailStage is missing" in (result.violation or "")
    assert "CircuitBreakerStage is missing" in (result.violation or "")


def test_fastapi_missing_critical_route():
    """Verify that removing any required chat, memory, or profile route is flagged."""
    mock_app = MagicMock()
    # Provide only a subset of routes (omitting /api/chat and /api/profile)
    mock_route_1 = SimpleNamespace(path="/api/memory/episodes", methods={"GET"})
    mock_route_2 = SimpleNamespace(path="/api/memory/list", methods={"GET"})
    mock_app.routes = [mock_route_1, mock_route_2]

    result = check_fastapi_routes(mock_app)
    assert result.passed is False
    assert "Missing endpoints" in (result.violation or "")
    assert "POST /api/chat" in (result.violation or "")
    assert "GET /api/profile" in (result.violation or "")


def test_all_critical_routes_exist_on_live_app():
    """Explicitly verify that each defined critical route exists on live app."""
    from app.main import app

    registered_endpoints = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            for m in methods:
                registered_endpoints.add((m.upper(), path))

    for method, path in CRITICAL_ROUTES:
        assert (method, path) in registered_endpoints, f"Missing critical endpoint: {method} {path}"


def test_drift_cli_exit_code_zero_on_compliance(capsys):
    """Verify CLI returns 0 on compliance."""
    with patch("sys.argv", ["check_architecture_drift.py", "--quiet"]):
        code = drift_main()
        assert code == 0


def test_drift_cli_exit_code_nonzero_on_drift(capsys):
    """Verify CLI returns non-zero (1) on drift."""
    bad_settings = SimpleNamespace(
        embedding_dimension=512,
        embedding_model="unknown-model",
        qdrant_collection="wrong-collection",
    )
    with patch("scripts.ops.check_architecture_drift.check_architecture_drift") as mock_check:
        mock_check.return_value = SimpleNamespace(
            ok=False,
            summary=lambda: "Drift detected summary",
        )
        with patch("sys.argv", ["check_architecture_drift.py"]):
            code = drift_main()
            assert code == 1
            captured = capsys.readouterr()
            assert "Drift detected summary" in captured.err
