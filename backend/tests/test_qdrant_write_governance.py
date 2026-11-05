"""T3-02 / DATA-06: Qdrant write governance and signed digest verification.

Verifies:
1. Qdrant read-only vs write keys on app.config.Settings and QdrantClientManager.
2. Read-only client contract rejects write operations.
3. Collection digest computation determinism and sensitivity.
4. Serving contract startup validation against signed collection digest.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings
from services.first_person_serving_contract import (
    FirstPersonServingContractError,
    assert_startup_safe,
    compute_collection_digest,
    load_contract,
    validate_serving_contract,
)
from services.qdrant.client import QdrantClientManager


def test_qdrant_api_keys_declared_on_settings():
    """Verify read-only and write keys exist on Settings with safe defaults."""
    assert hasattr(settings, "qdrant_read_only_api_key")
    assert hasattr(settings, "qdrant_write_api_key")
    assert settings.qdrant_read_only_api_key == ""
    assert settings.qdrant_write_api_key == ""


def test_qdrant_client_prefers_read_only_key(monkeypatch):
    """QdrantClientManager remote initialization uses read_only key when configured."""
    monkeypatch.setattr(settings, "qdrant_local_path", "")
    monkeypatch.setattr(settings, "qdrant_url", "http://qdrant:6333")
    monkeypatch.setattr(settings, "qdrant_api_key", "default-key")
    monkeypatch.setattr(settings, "qdrant_read_only_api_key", "ro-key-12345")

    with patch("services.qdrant.client.QdrantClient") as mock_client_cls:
        _ = QdrantClientManager(collection="test_col")
        assert mock_client_cls.called
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["api_key"] == "ro-key-12345"


def test_qdrant_client_falls_back_to_default_api_key(monkeypatch):
    """When read_only_api_key is empty, falls back to qdrant_api_key."""
    monkeypatch.setattr(settings, "qdrant_local_path", "")
    monkeypatch.setattr(settings, "qdrant_url", "http://qdrant:6333")
    monkeypatch.setattr(settings, "qdrant_api_key", "fallback-key-999")
    monkeypatch.setattr(settings, "qdrant_read_only_api_key", "")

    with patch("services.qdrant.client.QdrantClient") as mock_client_cls:
        _ = QdrantClientManager(collection="test_col")
        assert mock_client_cls.called
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["api_key"] == "fallback-key-999"


def test_backend_read_only_client_rejects_writes():
    """Verify that a write attempted via read-only credentials fails with 403 Forbidden."""
    mock_raw_client = MagicMock()
    mock_raw_client.upsert.side_effect = UnexpectedResponse(
        status_code=403,
        reason_phrase="Forbidden",
        content=b'{"status":{"error":"Forbidden: read-only access"}}',
        headers={},
    )

    manager = QdrantClientManager(collection="test_col", client=mock_raw_client)

    with pytest.raises(UnexpectedResponse) as exc_info:
        manager.client.upsert(
            collection_name="test_col",
            points=[],
        )
    assert exc_info.value.status_code == 403


def test_compute_collection_digest_determinism():
    """Collection digest is deterministic across point order and sensitive to payload/count."""
    p1 = {"id": "point-1", "payload": {"span_text_sha256": "hash_aaa"}}
    p2 = {"id": "point-2", "payload": {"span_text_sha256": "hash_bbb"}}
    p3 = {"id": "point-3", "payload": {"span_text_sha256": "hash_ccc"}}

    digest_forward = compute_collection_digest([p1, p2, p3])
    digest_reversed = compute_collection_digest([p3, p2, p1])

    # Order invariance (internal sorting by id:hash)
    assert digest_forward == digest_reversed
    assert len(digest_forward) == 64

    # Sensitive to content changes
    p2_modified = {"id": "point-2", "payload": {"span_text_sha256": "hash_mutated"}}
    digest_modified = compute_collection_digest([p1, p2_modified, p3])
    assert digest_modified != digest_forward

    # Sensitive to point count changes
    digest_truncated = compute_collection_digest([p1, p2])
    assert digest_truncated != digest_forward


def test_serving_contract_digest_matches(tmp_path):
    """When declared collection digest matches active digest, validation passes."""
    points = [
        {"id": "p1", "payload": {"span_text_sha256": "abc1"}},
        {"id": "p2", "payload": {"span_text_sha256": "abc2"}},
    ]
    expected_digest = compute_collection_digest(points)

    raw_contract = {
        "schema": "fp-serving-contract-v1",
        "collections": {
            "first_person_v10": {
                "schema": "fp-context-v1",
                "role": "context",
                "corpus_version": "fp-context-transcript-v1",
                "required_payload_fields": [
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
                ],
                "evidence_policy": "payload_speaker_and_rights_claims_unverified",
                "collection_digest": expected_digest,
            }
        },
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(raw_contract), encoding="utf-8")
    contract = load_contract(contract_file)

    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v10",
        context_collection="first_person_v10",
        context_harness_enabled=True,
        context_terminal_enabled=True,
        active_collection="first_person_v10",
        active_collection_digest=expected_digest,
    )
    digest_errors = [e for e in report.errors if "collection digest mismatch" in e]
    assert digest_errors == []


def test_serving_contract_digest_mismatch_fails_startup_in_production(tmp_path):
    """When signed collection digest disagrees with active digest, production startup raises."""
    signed_digest = "a" * 64
    active_digest = "b" * 64

    raw_contract = {
        "schema": "fp-serving-contract-v1",
        "collections": {
            "first_person_v10": {
                "schema": "fp-context-v1",
                "role": "context",
                "corpus_version": "fp-context-transcript-v1",
                "required_payload_fields": [
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
                ],
                "evidence_policy": "payload_speaker_and_rights_claims_unverified",
                "collection_digest": signed_digest,
            }
        },
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(raw_contract), encoding="utf-8")
    contract = load_contract(contract_file)

    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v10",
        context_collection="first_person_v10",
        context_harness_enabled=True,
        context_terminal_enabled=True,
        active_collection="first_person_v10",
        active_collection_digest=active_digest,
    )
    digest_errors = [e for e in report.errors if "collection digest mismatch" in e]
    assert len(digest_errors) == 1
    assert "signed digest" in digest_errors[0]

    # In production, this mismatch raises FirstPersonServingContractError
    with pytest.raises(FirstPersonServingContractError):
        assert_startup_safe(
            report,
            is_production=True,
            legacy_route_enabled=False,
            context_harness_enabled=True,
        )
