"""
Tests for Corpus Source Catalog & Freshness SLI — DE-3.1, DE-3.2

Tests:
- upsert_source records and updates source catalog entries.
- list_stale_sources and calculate_freshness_sli accurately flag sources older
  than the threshold and update Prometheus gauges CORPUS_SOURCE_AGE_DAYS and
  CORPUS_STALE_SOURCES_TOTAL.
- In-memory fallback and mock Supabase client behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from services.source_catalog import (
    CORPUS_SOURCE_AGE_DAYS,
    CORPUS_STALE_SOURCES_TOTAL,
    SourceCatalog,
    SourceCatalogService,
    calculate_freshness_sli,
)


@pytest.fixture
def memory_catalog() -> SourceCatalogService:
    """Fixture providing a fresh in-memory SourceCatalogService."""
    catalog = SourceCatalogService()
    # Force in-memory fallback for isolated testing
    catalog._use_fallback = True
    catalog._supabase = None
    catalog._memory_store = {}
    return catalog


def test_upsert_and_get_source(memory_catalog: SourceCatalogService) -> None:
    """Test upsert_source records new source and get_source retrieves it."""
    source_id = "yt_video_101"
    url = "https://www.youtube.com/watch?v=video101"
    corpus_id = "askmukthiguru"
    checksum = "sha256_mock_checksum_abc"

    created = memory_catalog.upsert_source(
        source_identity=source_id,
        source_url=url,
        corpus_id=corpus_id,
        checksum=checksum,
        status="active",
    )

    assert created["source_identity"] == source_id
    assert created["source_url"] == url
    assert created["corpus_id"] == corpus_id
    assert created["last_checksum"] == checksum
    assert created["status"] == "active"
    assert "last_ingested_at" in created
    assert "created_at" in created
    assert "updated_at" in created

    # Fetch source
    fetched = memory_catalog.get_source(source_id)
    assert fetched is not None
    assert fetched["source_identity"] == source_id
    assert fetched["source_url"] == url

    # Update source with new checksum and release ID
    new_checksum = "sha256_mock_checksum_updated"
    release_id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    updated = memory_catalog.upsert_source(
        source_identity=source_id,
        source_url=url,
        corpus_id=corpus_id,
        checksum=new_checksum,
        active_release_id=release_id,
        status="active",
    )

    assert updated["last_checksum"] == new_checksum
    assert updated["active_release_id"] == release_id
    assert updated["created_at"] == created["created_at"]

    # Re-fetch and check
    refetched = memory_catalog.get_source(source_id)
    assert refetched is not None
    assert refetched["last_checksum"] == new_checksum
    assert refetched["active_release_id"] == release_id


def test_list_stale_sources(memory_catalog: SourceCatalogService) -> None:
    """Test list_stale_sources correctly filters sources older than max_age_days."""
    now = datetime.now(UTC)
    corpus_id = "test_corpus"

    # Source 1: fresh (5 days ago)
    memory_catalog.upsert_source(
        source_identity="src_fresh",
        source_url="https://example.com/fresh",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=5),
    )

    # Source 2: stale (35 days ago)
    memory_catalog.upsert_source(
        source_identity="src_stale_35",
        source_url="https://example.com/stale35",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=35),
    )

    # Source 3: very stale (60 days ago)
    memory_catalog.upsert_source(
        source_identity="src_stale_60",
        source_url="https://example.com/stale60",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=60),
    )

    # Threshold = 30 days
    stale_sources = memory_catalog.list_stale_sources(corpus_id=corpus_id, max_age_days=30)
    assert len(stale_sources) == 2
    # Ordered oldest first
    assert stale_sources[0]["source_identity"] == "src_stale_60"
    assert stale_sources[0]["age_days"] >= 59.9
    assert stale_sources[1]["source_identity"] == "src_stale_35"
    assert stale_sources[1]["age_days"] >= 34.9

    # Threshold = 40 days -> only src_stale_60
    stale_40 = memory_catalog.list_stale_sources(corpus_id=corpus_id, max_age_days=40)
    assert len(stale_40) == 1
    assert stale_40[0]["source_identity"] == "src_stale_60"


def test_calculate_freshness_sli_and_prometheus_gauges(
    memory_catalog: SourceCatalogService,
) -> None:
    """Test calculate_freshness_sli computes SLI and updates Prometheus gauges."""
    now = datetime.now(UTC)
    corpus_id = "freshness_sli_test_corpus"

    # Seed 3 sources: 1 fresh, 2 stale
    memory_catalog.upsert_source(
        source_identity="item_fresh",
        source_url="https://example.com/1",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=2),
    )
    memory_catalog.upsert_source(
        source_identity="item_stale_45",
        source_url="https://example.com/2",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=45),
    )
    memory_catalog.upsert_source(
        source_identity="item_stale_90",
        source_url="https://example.com/3",
        corpus_id=corpus_id,
        last_ingested_at=now - timedelta(days=90),
    )

    result = memory_catalog.calculate_freshness_sli(
        corpus_id=corpus_id,
        stale_threshold_days=30,
    )

    assert result["stale_count"] == 2
    assert result["total_sources"] == 3
    assert result["max_age_days"] >= 89.9
    assert len(result["stale_sources"]) == 2

    # Check Prometheus gauges
    age_metric_val = CORPUS_SOURCE_AGE_DAYS.labels(corpus_id=corpus_id)._value.get()
    stale_metric_val = CORPUS_STALE_SOURCES_TOTAL.labels(corpus_id=corpus_id)._value.get()

    assert age_metric_val >= 89.9
    assert stale_metric_val == 2

    # Also test the module-level helper function
    helper_res = calculate_freshness_sli(
        corpus_id=corpus_id,
        stale_threshold_days=30,
        catalog=memory_catalog,
    )
    assert helper_res["stale_count"] == 2


def test_get_source_stats_empty_corpus(memory_catalog: SourceCatalogService) -> None:
    """Test stats on an empty corpus return clean zeroes."""
    stats = memory_catalog.get_source_stats("nonexistent_corpus")
    assert stats["count"] == 0
    assert stats["active_count"] == 0
    assert stats["stale_count"] == 0
    assert stats["oldest_age_days"] == 0.0
    assert stats["newest_age_days"] == 0.0


def test_mock_supabase_client_integration() -> None:
    """Test SourceCatalogService with a mocked Supabase client."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    sample_row = {
        "source_identity": "supa_source_1",
        "source_url": "https://example.com/supa1",
        "corpus_id": "supa_corpus",
        "last_ingested_at": "2026-10-01T00:00:00+00:00",
        "last_checksum": "sha256_mock",
        "active_release_id": None,
        "status": "active",
        "created_at": "2026-10-01T00:00:00+00:00",
        "updated_at": "2026-10-01T00:00:00+00:00",
    }

    # Mock upsert response
    mock_upsert_resp = MagicMock()
    mock_upsert_resp.data = [sample_row]
    mock_table.upsert.return_value.execute.return_value = mock_upsert_resp

    # Mock select response
    mock_select_resp = MagicMock()
    mock_select_resp.data = [sample_row]
    mock_table.select.return_value.eq.return_value.execute.return_value = mock_select_resp
    mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        mock_select_resp
    )

    catalog = SourceCatalog(supabase_client=mock_client)
    res = catalog.upsert_source(
        source_identity="supa_source_1",
        source_url="https://example.com/supa1",
        corpus_id="supa_corpus",
        checksum="sha256_mock",
    )
    assert res["source_identity"] == "supa_source_1"
    mock_table.upsert.assert_called_once()

    fetched = catalog.get_source("supa_source_1")
    assert fetched is not None
    assert fetched["source_identity"] == "supa_source_1"
