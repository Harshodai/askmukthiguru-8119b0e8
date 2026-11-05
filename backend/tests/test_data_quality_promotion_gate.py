"""Tests for DATA-14, DATA-15, DATA-16 / T3-05:
1. Scorecard promotion gate (0 BLOCKER fails, strict clean >= 60%).
2. Serving contract approved corpus version == served corpus version.
3. First-person continuous quality audit checks in data_quality_audit.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.ops.data_quality_audit import audit_qdrant
from scripts.ops.fp_data_quality_scorecard import evaluate_promotion_gate
from services.first_person_serving_contract import (
    CollectionContract,
    validate_serving_contract,
)


def test_scorecard_promotion_gate_clean_passes():
    """Clean report with strict_clean >= 60% and no gating failures is promotable."""
    mock_report = {
        "summary": {
            "verdict": "PASS",
            "gating_failures": [],
            "checks": 26,
            "passed": 26,
        },
        "checks": [
            {
                "id": "strict_clean_rate",
                "severity": "HIGH",
                "measured": 0.65,
                "target": 0.60,
                "status": "PASS",
            },
            {
                "id": "text_hash_mismatch",
                "severity": "BLOCKER",
                "measured": 0,
                "target": 0,
                "status": "PASS",
            },
        ],
    }
    promotable, reasons = evaluate_promotion_gate(mock_report, target_strict_clean=0.60)
    assert promotable is True
    assert reasons == []


def test_scorecard_promotion_gate_refuses_low_strict_clean():
    """Scorecard with strict_clean_rate < 60% is refused for promotion (DATA-14)."""
    mock_report = {
        "summary": {
            "verdict": "FAIL",
            "gating_failures": ["strict_clean_rate"],
            "checks": 26,
            "passed": 25,
        },
        "checks": [
            {
                "id": "strict_clean_rate",
                "severity": "HIGH",
                "measured": 0.42,
                "target": 0.60,
                "status": "FAIL",
            },
        ],
    }
    promotable, reasons = evaluate_promotion_gate(mock_report, target_strict_clean=0.60)
    assert promotable is False
    assert any("strict_clean_rate 42.00% is below promotion target 60.00%" in r for r in reasons)


def test_scorecard_promotion_gate_refuses_blocker_failure():
    """Scorecard with any BLOCKER failure is refused for promotion."""
    mock_report = {
        "summary": {
            "verdict": "FAIL",
            "gating_failures": ["text_hash_mismatch"],
            "checks": 26,
            "passed": 25,
        },
        "checks": [
            {
                "id": "text_hash_mismatch",
                "severity": "BLOCKER",
                "measured": 3,
                "target": 0,
                "status": "FAIL",
            },
            {
                "id": "strict_clean_rate",
                "severity": "HIGH",
                "measured": 0.70,
                "target": 0.60,
                "status": "PASS",
            },
        ],
    }
    promotable, reasons = evaluate_promotion_gate(mock_report, target_strict_clean=0.60)
    assert promotable is False
    assert any("BLOCKER check text_hash_mismatch failed" in r for r in reasons)


def test_serving_contract_refuses_approved_corpus_version_mismatch():
    """Approved corpus version != served corpus version fails serving contract validation (DATA-16)."""
    contract = {
        "fp_test_v10": CollectionContract(
            name="fp_test_v10",
            schema="fp-context-v1",
            role="context",
            corpus_version="fp-context-transcript-v1",
            approved_corpus_version="fp-context-transcript-v2",  # Mismatch
            required_payload_fields=("record_type", "source_span_id", "corpus_version"),
            evidence_policy="verified",
        )
    }

    report = validate_serving_contract(
        contract=contract,
        legacy_collection="fp_test_v10",
        context_collection="fp_test_v10",
        context_harness_enabled=True,
        context_terminal_enabled=True,
        active_collection="fp_test_v10",
    )
    assert report.ok is False
    assert any(
        "does not match approved_corpus_version 'fp-context-transcript-v2'" in e
        for e in report.errors
    )


def test_serving_contract_accepts_matching_approved_corpus_version():
    """Approved corpus version == served corpus version passes serving contract validation."""
    contract = {
        "fp_test_v10": CollectionContract(
            name="fp_test_v10",
            schema="fp-context-v1",
            role="context",
            corpus_version="fp-context-transcript-v1",
            approved_corpus_version="fp-context-transcript-v1",  # Matching
            required_payload_fields=(
                "record_type",
                "source_span_id",
                "parent_unit_id",
                "guru_id",
                "verbatim_text",
                "source_text_hash",
                "transcript_hash",
                "speaker_verified",
                "rights_cleared",
                "corpus_version",
            ),
            evidence_policy="verified",
        )
    }

    report = validate_serving_contract(
        contract=contract,
        legacy_collection="fp_test_v10",
        context_collection="fp_test_v10",
        context_harness_enabled=True,
        context_terminal_enabled=True,
        active_collection="fp_test_v10",
    )
    assert report.ok is True
    assert report.errors == ()


def test_data_quality_audit_detects_fp_defects():
    """Qdrant audit detects verified_without_method and corpus_version mismatch (DATA-15)."""
    fake_payloads = [
        {
            "point_id": "p1",
            "source_span_id": "span-1",
            "video_id": "vid-1",
            "speaker_verified": True,
            "voice_verification_method": None,  # Defect: verified without method
            "corpus_version": "fp-v1",
            "source_text_hash": "hash1",
        },
        {
            "point_id": "p2",
            "source_span_id": "span-2",
            "video_id": "vid-1",
            "speaker_verified": True,
            "voice_verification_method": "ecapa@rev1",
            "corpus_version": "fp-v1",
            "source_text_hash": "hash2",
        },
    ]

    with (
        patch(
            "scripts.ops.data_quality_audit._validate_qdrant_base_url",
            return_value="http://127.0.0.1:6333",
        ),
        patch("scripts.ops.data_quality_audit._scroll", return_value=iter(fake_payloads)),
    ):
        res = audit_qdrant(
            "http://127.0.0.1:6333",
            "first_person_test",
            cap=None,
            expected_corpus_version="fp-v2",  # Mismatched expected version
        )

        assert res["verified_without_method_count"] == 1
        assert res["corpus_version_matches"] is False
        assert res["computed_digest"] != ""
