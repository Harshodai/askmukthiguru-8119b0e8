"""Tests for benchmark harness guard and citation floor auditing (Criteria A1.5, A1.6).

Verifies:
1. Benchmark startup aborts immediately when Qdrant serving collection has 0 points
   or when required runtime artifacts (e.g. okf_compiled) are missing.
2. Question bank doctrine categories and verified questions strictly enforce
   min_citations >= 1 to prevent ungrounded answers from vacuously passing.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from benchmarks.question_bank import QUERIES
from benchmarks.ruthless_benchmark import check_corpus_readiness


# ═══════════════════════════════════════════════════════════════════════════
# 1. HARNESS GUARD RUNTIME ABORT TESTS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_harness_guard_aborts_on_zero_qdrant_points(monkeypatch):
    """Harness must abort with clear error and non-zero exit code when Qdrant points count is 0."""
    # Mock runtime artifacts as healthy
    monkeypatch.setattr(
        "app.runtime_artifacts.inspect_runtime_artifacts",
        lambda: {"missing_required": [], "present": 2, "total": 2, "readiness_ok": True},
    )

    # Mock httpx AsyncClient to return 0 points from Qdrant REST probe
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "points_count": 0,
            "status": "green",
        }
    }

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    # Test raise_on_error=True raises RuntimeError with clear explanation
    with pytest.raises(RuntimeError) as exc_info:
        await check_corpus_readiness(
            base_url="http://localhost:8000",
            client=mock_client,
            raise_on_error=True,
        )

    err_text = str(exc_info.value)
    assert "BENCHMARK HARNESS GUARD FAILED" in err_text
    assert "void on an empty corpus" in err_text
    assert "points_count must be > 0" in err_text

    # Test default raise_on_error=False triggers sys.exit(1)
    with pytest.raises(SystemExit) as exit_info:
        await check_corpus_readiness(
            base_url="http://localhost:8000",
            client=mock_client,
            raise_on_error=False,
        )
    assert exit_info.value.code == 1


@pytest.mark.asyncio
async def test_harness_guard_aborts_on_missing_qdrant_collection(monkeypatch):
    """Harness must abort if Qdrant collection lookup 404s (uninitialized)."""
    monkeypatch.setattr(
        "app.runtime_artifacts.inspect_runtime_artifacts",
        lambda: {"missing_required": [], "present": 2, "total": 2, "readiness_ok": True},
    )

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"status": "error", "error": "Not found"}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(RuntimeError) as exc_info:
        await check_corpus_readiness(
            base_url="http://localhost:8000",
            client=mock_client,
            raise_on_error=True,
        )

    err_text = str(exc_info.value)
    assert "void on an empty corpus" in err_text
    assert "points_count must be > 0" in err_text


@pytest.mark.asyncio
async def test_harness_guard_aborts_on_missing_okf_compiled(monkeypatch):
    """Harness must abort when required runtime artifact okf_compiled is missing."""
    # Mock runtime artifacts reporting missing okf_compiled
    monkeypatch.setattr(
        "app.runtime_artifacts.inspect_runtime_artifacts",
        lambda: {
            "missing_required": ["okf_compiled"],
            "present": 1,
            "total": 2,
            "readiness_ok": False,
        },
    )

    # Mock Qdrant collection as populated
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "points_count": 1500,
            "status": "green",
        }
    }

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(RuntimeError) as exc_info:
        await check_corpus_readiness(
            base_url="http://localhost:8000",
            client=mock_client,
            raise_on_error=True,
        )

    err_text = str(exc_info.value)
    assert "BENCHMARK HARNESS GUARD FAILED" in err_text
    assert "Missing required runtime artifacts: okf_compiled" in err_text


@pytest.mark.asyncio
async def test_harness_guard_passes_when_qdrant_and_artifacts_healthy(monkeypatch):
    """Harness guard proceeds cleanly when Qdrant points > 0 and artifacts are present."""
    monkeypatch.setattr(
        "app.runtime_artifacts.inspect_runtime_artifacts",
        lambda: {"missing_required": [], "present": 2, "total": 2, "readiness_ok": True},
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "points_count": 4200,
            "status": "green",
        }
    }

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await check_corpus_readiness(
        base_url="http://localhost:8000",
        client=mock_client,
        raise_on_error=True,
    )

    assert result["status"] == "ready"
    assert result["points_count"] == 4200
    assert result["missing_artifacts"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. CITATION FLOOR & QUESTION BANK AUDIT TESTS
# ═══════════════════════════════════════════════════════════════════════════


DOCTRINE_CATEGORIES = [
    "doctrine_four_secrets",
    "doctrine_founders",
    "doctrine_manifest",
    "doctrine_deeksha",
    "doctrine_soul_sync",
    "doctrine_ekam_architecture",
]


def test_question_bank_doctrine_categories_enforce_min_citations():
    """All factual doctrine cases must enforce min_cites >= 1 so ungrounded answers fail."""
    for category_name in DOCTRINE_CATEGORIES:
        assert category_name in QUERIES, f"Missing expected doctrine category: {category_name}"
        items = QUERIES[category_name]
        assert len(items) > 0, f"Doctrine category '{category_name}' has no queries"

        for idx, item in enumerate(items):
            min_cites = item.get("min_cites")
            assert (
                min_cites is not None and isinstance(min_cites, int) and min_cites >= 1
            ), (
                f"Vacuous citation pass risk! {category_name}[{idx}] ({item.get('q')}) "
                f"has min_cites={min_cites!r} (must be >= 1)"
            )


def test_question_bank_verified_cases_enforce_min_citations():
    """Any question in the entire question bank with verified=True must have min_cites >= 1."""
    for category_name, items in QUERIES.items():
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if isinstance(item, dict) and item.get("verified") is True:
                min_cites = item.get("min_cites")
                assert (
                    min_cites is not None and isinstance(min_cites, int) and min_cites >= 1
                ), (
                    f"Verified case without citation floor! {category_name}[{idx}] ({item.get('q')}) "
                    f"has verified=True but min_cites={min_cites!r}"
                )


def test_question_bank_lokaa_query_has_citation_floor():
    """Specific regression test: 'Who is Lokaa?' must have min_cites >= 1."""
    founders_queries = QUERIES.get("doctrine_founders", [])
    lokaa_item = next(
        (it for it in founders_queries if isinstance(it, dict) and "Who is Lokaa?" in it.get("q", "")),
        None,
    )
    assert lokaa_item is not None, "Could not find 'Who is Lokaa?' query in doctrine_founders"
    assert lokaa_item.get("min_cites") == 1, (
        f"'Who is Lokaa?' query must have min_cites == 1, got {lokaa_item.get('min_cites')}"
    )


def test_evaluation_manifest_doctrine_cases_enforce_min_citations():
    """Latency evaluation manifest must enforce min_citations >= 1 on all doctrine cases."""
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "audit_work" / "question_bank_latency_manifest_v1.json"
    if not manifest_path.exists():
        pytest.skip("question_bank_latency_manifest_v1.json not present in workspace")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases", [])

    for case in cases:
        cat = case.get("source_category", "")
        stratum = case.get("benchmark_stratum", "")
        # Check doctrine categories (excluding refusal traps like doctrine_traps)
        if (cat in DOCTRINE_CATEGORIES) or (stratum == "in_corpus_doctrine" and cat != "doctrine_traps"):
            min_c = case.get("min_citations")
            assert (
                min_c is not None and isinstance(min_c, int) and min_c >= 1
            ), (
                f"Manifest case {case.get('case_id')} in {cat} has min_citations={min_c!r} (must be >= 1)"
            )
