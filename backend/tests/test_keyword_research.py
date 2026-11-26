"""Tests for Keyword Research product workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.keyword_research.engine import generate_keyword_research
from services.keyword_research.models import KeywordResearchPayload
from services.keyword_research.validator import (
    KeywordValidationError,
    inspect_xlsx_sheet_names,
    validate_keyword_research_payload,
)
from services.keyword_research.workbook import create_keyword_research_workbook


def test_keyword_research_generation_cardinalities():
    payload = generate_keyword_research(
        seed_keyword="meditation and inner peace",
        target_country="United States",
        data_source="public_data",
    )

    # Invariant 1: Exactly 300 keywords
    assert len(payload.keywords) == 300

    # Invariant 2: Exactly 5 topic clusters
    clusters = {k.topic_cluster for k in payload.keywords}
    assert len(clusters) == 5

    # Exactly 60 per cluster
    for c in clusters:
        count = sum(1 for k in payload.keywords if k.topic_cluster == c)
        assert count == 60

    # Invariant 3: Top 20 organic competitors
    assert len(payload.competitors) == 20

    # Invariant 4: Exactly 20 keyword gaps
    assert len(payload.gaps) == 20

    # Invariant 5: Exactly 5 findings & 5 recommendations
    assert len(payload.findings) == 5
    assert len(payload.recommendations) == 5

    # Scope label reflects country
    assert payload.volume_scope_label == "Monthly Volume (United States)"


def test_keyword_research_worldwide_scope():
    payload = generate_keyword_research(
        seed_keyword="mindfulness",
        target_country="worldwide",
    )
    assert payload.volume_scope_label == "Global Volume"


def test_payload_validation_catches_violations():
    payload = generate_keyword_research("stress relief")
    # Valid payload should pass
    validate_keyword_research_payload(payload)

    # 1. Alter keyword count
    payload_bad_count = KeywordResearchPayload(
        seed_keyword=payload.seed_keyword,
        target_country=payload.target_country,
        data_source=payload.data_source,
        volume_scope_label=payload.volume_scope_label,
        keywords=payload.keywords[:299],  # 299 instead of 300
        competitors=payload.competitors,
        gaps=payload.gaps,
        findings=payload.findings,
        recommendations=payload.recommendations,
    )
    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload_bad_count)
    assert "Expected exactly 300 keywords" in str(exc.value)

    # 2. Alter competitor count
    payload_bad_comp = KeywordResearchPayload(
        seed_keyword=payload.seed_keyword,
        target_country=payload.target_country,
        data_source=payload.data_source,
        volume_scope_label=payload.volume_scope_label,
        keywords=payload.keywords,
        competitors=payload.competitors[:19],  # 19 instead of 20
        gaps=payload.gaps,
        findings=payload.findings,
        recommendations=payload.recommendations,
    )
    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload_bad_comp)
    assert "Expected exactly 20 competitors" in str(exc.value)


def test_create_three_tab_workbook(tmp_path: Path):
    payload = generate_keyword_research(
        seed_keyword="spiritual awakening",
        target_country="United Kingdom",
    )
    out_xlsx = tmp_path / "keyword_research.xlsx"
    res_path = create_keyword_research_workbook(payload, out_xlsx)

    assert res_path.exists()
    assert res_path.stat().st_size > 5000  # Non-trivial workbook

    # Verify exact sheet names
    sheet_names = inspect_xlsx_sheet_names(res_path)
    assert len(sheet_names) == 3
    assert sheet_names == [
        "Topic Cluster Summary",
        "Priority Keyword Targets",
        "Competitor & Gap Analysis",
    ]


def test_keyword_research_with_external_provider_and_provenance():
    valid_req_hash = "a" * 64
    valid_resp_hash = "b" * 64

    class FakeExternalProvider:
        def fetch(self, *, seed_keyword: str, target_country: str, keywords):
            return {
                "data_source": "DataForSEO",
                "provenance": {
                    "provider": "DataForSEO",
                    "source_url": "https://api.dataforseo.com/v3/keywords_data/live",
                    "retrieved_at": "2026-11-23T05:00:00+00:00",
                    "request_sha256": valid_req_hash,
                    "response_sha256": valid_resp_hash,
                    "requested_keyword_count": 300,
                    "is_simulated": False,
                    "production_certified": True,
                },
                "keywords": [
                    {
                        "keyword": "guided meditation",
                        "monthly_volume": 25000,
                        "global_volume": 60000,
                        "kd": 48,
                        "cpc": 2.15,
                    }
                ],
            }

    payload = generate_keyword_research(
        seed_keyword="meditation",
        target_country="United States",
        provider=FakeExternalProvider(),
    )
    assert payload.data_source == "DataForSEO"
    assert payload.provenance is not None
    assert payload.provenance["provider"] == "DataForSEO"
    assert payload.provenance["production_certified"] is True
    assert payload.provenance["request_sha256"] == valid_req_hash
    assert payload.production_certified is True
    assert payload.is_simulated is False

    # Valid external payload must pass strict validation
    validate_keyword_research_payload(payload, require_external_certification=True)

    # Verify that the externally sourced keyword metric overrode the default
    guided_kw = next(k for k in payload.keywords if k.keyword == "guided meditation")
    assert guided_kw.monthly_volume == 25000
    assert guided_kw.global_volume == 60000
    assert guided_kw.kd == 48
    assert guided_kw.cpc == 2.15


def test_certified_payload_rejected_when_simulated():
    payload = generate_keyword_research("mindfulness")
    # Attempt to tamper: claim certified while simulated
    payload.production_certified = True
    payload.is_simulated = True

    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload)
    assert "cannot claim production_certified=True while is_simulated=True" in str(exc.value)


def test_certified_payload_rejected_with_malformed_hashes():
    payload = generate_keyword_research("mindfulness")
    payload.production_certified = True
    payload.is_simulated = False
    payload.provenance = {
        "provider": "Semrush",
        "source_url": "https://api.semrush.com/v1",
        "retrieved_at": "2026-11-23T05:00:00+00:00",
        "request_sha256": "short_hash_not_64_chars",
        "response_sha256": "z" * 64,  # 'z' is not valid hex
        "requested_keyword_count": 300,
        "is_simulated": False,
        "production_certified": True,
    }

    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload)
    assert "valid 64-character hex request_sha256 hash" in str(exc.value)


def test_certified_payload_rejected_with_missing_provenance():
    payload = generate_keyword_research("mindfulness")
    payload.production_certified = True
    payload.is_simulated = False
    payload.provenance = None

    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload)
    assert "missing required provenance object" in str(exc.value)


def test_certified_payload_rejected_with_invalid_metrics():
    payload = generate_keyword_research("mindfulness")
    payload.keywords[0].monthly_volume = -50
    payload.keywords[1].kd = 105

    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload)
    assert "negative monthly volume" in str(exc.value)
    assert "KD out of [0, 100] range" in str(exc.value)


def test_baseline_available_with_clear_uncertified_metadata():
    payload = generate_keyword_research("mindfulness")
    assert payload.production_certified is False
    assert payload.is_simulated is True
    assert payload.provenance["is_simulated"] is True
    assert payload.provenance["production_certified"] is False

    # Default validation passes for baseline
    validate_keyword_research_payload(payload)

    # But fails if external certification is required
    with pytest.raises(KeywordValidationError) as exc:
        validate_keyword_research_payload(payload, require_external_certification=True)
    assert "failed external certification check" in str(exc.value)


def test_require_external_provenance_raises_when_unconfigured():
    from services.keyword_research.provider import KeywordResearchDataUnavailable

    with pytest.raises(KeywordResearchDataUnavailable) as exc:
        generate_keyword_research(
            seed_keyword="meditation",
            require_external_provenance=True,
        )
    assert "External keyword research provider is not configured" in str(exc.value)
