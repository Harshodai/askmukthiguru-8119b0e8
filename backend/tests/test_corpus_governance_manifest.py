"""Tests for Corpus Governance & OKF Manifest Gating.

Validates explicit, versioned, fail-closed source governance across compiled OKF
and retrieval paths per SPEC-corpus-governance.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.corpus_governance import (
    STATUS_CLEARED,
    STATUS_PENDING,
    STATUS_QUARANTINED,
    STATUS_REJECTED,
    CorpusGovernanceError,
    SourceAssetManifest,
    SourceAssetManifestRow,
    assert_not_implied_clearance,
)
from services.memory.okf_store import (
    OKFStore,
    match_okf_entries,
)


@pytest.fixture
def sample_valid_row() -> SourceAssetManifestRow:
    return SourceAssetManifestRow(
        source_id="vid_valid_01",
        corpus_version="v1",
        content_hash="h" * 64,
        serving_tier="general",
        status=STATUS_CLEARED,
        evidence_reference="ref-gov-2026-10-01",
        reviewer_id="reviewer_human_01",
        decision_date="2026-10-27",
    )


@pytest.fixture
def sample_manifest(sample_valid_row) -> SourceAssetManifest:
    pending_row = SourceAssetManifestRow(
        source_id="vid_pending_02",
        corpus_version="v1",
        content_hash="p" * 64,
        serving_tier="general",
        status=STATUS_PENDING,
        evidence_reference="ref-gov-2026-10-02",
        reviewer_id="reviewer_human_01",
        decision_date="2026-10-27",
    )
    quarantined_row = SourceAssetManifestRow(
        source_id="vid_quarantined_03",
        corpus_version="v1",
        content_hash="q" * 64,
        serving_tier="first_person",
        status=STATUS_QUARANTINED,
        evidence_reference="ref-gov-2026-10-03",
        reviewer_id="reviewer_human_01",
        decision_date="2026-10-27",
    )
    rejected_row = SourceAssetManifestRow(
        source_id="vid_rejected_04",
        corpus_version="v1",
        content_hash="r" * 64,
        serving_tier="general",
        status=STATUS_REJECTED,
        evidence_reference="ref-gov-2026-10-04",
        reviewer_id="reviewer_human_01",
        decision_date="2026-10-27",
    )
    return SourceAssetManifest(rows=[sample_valid_row, pending_row, quarantined_row, rejected_row])


# ---------------------------------------------------------------------------
# 1. Manifest row structure and digest
# ---------------------------------------------------------------------------
def test_manifest_row_dataclass_and_serialization(sample_valid_row):
    row_dict = sample_valid_row.to_dict()
    assert row_dict["source_id"] == "vid_valid_01"
    assert row_dict["status"] == STATUS_CLEARED
    reconstructed = SourceAssetManifestRow.from_dict(row_dict)
    assert reconstructed == sample_valid_row


def test_manifest_digest_computation_deterministic(sample_valid_row):
    manifest1 = SourceAssetManifest([sample_valid_row])
    manifest2 = SourceAssetManifest([sample_valid_row])
    assert manifest1.manifest_digest == manifest2.manifest_digest
    assert len(manifest1.manifest_digest) == 64
    assert manifest1.digest == manifest1.manifest_digest

    # Changing a single attribute changes the digest
    modified_row = SourceAssetManifestRow.from_dict(
        {**sample_valid_row.to_dict(), "decision_date": "2026-10-28"}
    )
    manifest3 = SourceAssetManifest([modified_row])
    assert manifest3.manifest_digest != manifest1.manifest_digest


# ---------------------------------------------------------------------------
# 2. Status fixtures: missing, unknown, pending fail closed
# ---------------------------------------------------------------------------
def test_status_fixtures_fail_closed(sample_manifest):
    # Cleared status succeeds
    ok, reason = sample_manifest.is_entry_eligible("vid_valid_01", "v1", content_hash="h" * 64)
    assert ok is True
    assert reason == "cleared"

    # Pending status fails closed
    ok, reason = sample_manifest.is_entry_eligible("vid_pending_02", "v1")
    assert ok is False
    assert reason == "ineligible_status_pending"

    # Quarantined status fails closed
    ok, reason = sample_manifest.is_entry_eligible("vid_quarantined_03", "v1", tier="first_person")
    assert ok is False
    assert reason == "ineligible_status_quarantined"

    # Rejected status fails closed
    ok, reason = sample_manifest.is_entry_eligible("vid_rejected_04", "v1")
    assert ok is False
    assert reason == "ineligible_status_rejected"

    # Unknown status fails closed
    unknown_row = SourceAssetManifestRow(
        source_id="vid_unknown",
        corpus_version="v1",
        content_hash="u" * 64,
        status="unknown",
        evidence_reference="ref-1",
        reviewer_id="rev-1",
        decision_date="2026-10-27",
    )
    unknown_manifest = SourceAssetManifest([unknown_row])
    ok, reason = unknown_manifest.is_entry_eligible("vid_unknown", "v1")
    assert ok is False
    assert reason == "ineligible_status_unknown"
    with pytest.raises(CorpusGovernanceError, match="invalid status"):
        unknown_manifest.validate()

    # Unmanifested source fails closed
    ok, reason = sample_manifest.is_entry_eligible("vid_non_existent", "v1")
    assert ok is False
    assert reason == "unmanifested_source"


# ---------------------------------------------------------------------------
# 3. Malformed and stale manifests fail closed
# ---------------------------------------------------------------------------
def test_malformed_manifest_fails_closed():
    # Row missing source_id
    malformed_manifest = SourceAssetManifest(
        rows=[{"source_id": "", "corpus_version": "v1", "content_hash": "a" * 64}]
    )
    ok, reason = malformed_manifest.is_entry_eligible("vid_01", "v1")
    assert ok is False
    assert reason == "malformed_manifest"
    with pytest.raises(CorpusGovernanceError, match="Malformed manifest"):
        malformed_manifest.validate()


def test_stale_manifest_fails_closed(sample_valid_row):
    # Stale by explicit flag
    stale_manifest = SourceAssetManifest([sample_valid_row], stale=True)
    assert stale_manifest.is_stale is True
    ok, reason = stale_manifest.is_entry_eligible("vid_valid_01", "v1")
    assert ok is False
    assert reason == "stale_manifest"
    with pytest.raises(CorpusGovernanceError, match="stale"):
        stale_manifest.validate()

    # Stale by digest mismatch
    mismatch_manifest = SourceAssetManifest([sample_valid_row], expected_digest="0" * 64)
    assert mismatch_manifest.is_stale is True
    ok, reason = mismatch_manifest.is_entry_eligible("vid_valid_01", "v1")
    assert ok is False
    assert reason == "stale_manifest"
    with pytest.raises(CorpusGovernanceError, match="stale|digest mismatch"):
        mismatch_manifest.validate()


def test_duplicate_keys_fail_closed(sample_valid_row):
    duplicate_row = SourceAssetManifestRow.from_dict(
        {**sample_valid_row.to_dict(), "content_hash": "different_hash"}
    )
    manifest = SourceAssetManifest([sample_valid_row, duplicate_row])
    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1")
    assert ok is False
    assert reason == "duplicate_manifest_key"
    with pytest.raises(CorpusGovernanceError, match="Duplicate manifest keys"):
        manifest.validate()


# ---------------------------------------------------------------------------
# 4. Hash mismatch fails closed
# ---------------------------------------------------------------------------
def test_hash_mismatch_fails_closed(sample_valid_row):
    manifest = SourceAssetManifest([sample_valid_row])
    # Exact match passes
    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1", content_hash="h" * 64)
    assert ok is True
    assert reason == "cleared"

    # Mismatched hash fails closed
    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1", content_hash="wrong_hash")
    assert ok is False
    assert reason == "content_hash_mismatch"


# ---------------------------------------------------------------------------
# 5. Missing reviewer, date, or evidence reference fails closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field_to_clear", ["reviewer_id", "decision_date", "evidence_reference"])
def test_missing_provenance_fails_closed(sample_valid_row, field_to_clear):
    bad_dict = sample_valid_row.to_dict()
    bad_dict[field_to_clear] = ""
    bad_row = SourceAssetManifestRow.from_dict(bad_dict)
    manifest = SourceAssetManifest([bad_row])

    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1", content_hash="h" * 64)
    assert ok is False
    assert reason == "incomplete_provenance"
    with pytest.raises(CorpusGovernanceError, match="incomplete provenance"):
        manifest.validate()


# ---------------------------------------------------------------------------
# 6. Undeclared or mismatched tier fails closed
# ---------------------------------------------------------------------------
def test_undeclared_or_mismatched_tier_fails_closed(sample_valid_row):
    manifest = SourceAssetManifest([sample_valid_row])  # serving_tier="general"

    # Requesting general tier succeeds
    ok, reason = manifest.is_entry_eligible(
        "vid_valid_01", "v1", content_hash="h" * 64, tier="general"
    )
    assert ok is True
    assert reason == "cleared"

    # A wildcard tier is not a bypass: it fails closed like any other mismatch
    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1", content_hash="h" * 64, tier="*")
    assert ok is False
    assert reason == "tier_mismatch_general"

    # P2-26: a caller that presents no content hash cannot prove what it serves
    ok, reason = manifest.is_entry_eligible("vid_valid_01", "v1")
    assert ok is False
    assert reason == "content_hash_missing"

    # Requesting mismatched tier fails closed
    ok, reason = manifest.is_entry_eligible(
        "vid_valid_01", "v1", content_hash="h" * 64, tier="first_person"
    )
    assert ok is False
    assert reason == "tier_mismatch_general"

    ok, reason = manifest.is_entry_eligible(
        "vid_valid_01", "v1", content_hash="h" * 64, tier="practice"
    )
    assert ok is False
    assert reason == "tier_mismatch_general"


# ---------------------------------------------------------------------------
# 7. Informal and boolean-only markers do not imply clearance
# ---------------------------------------------------------------------------
def test_informal_and_boolean_markers_do_not_imply_clearance():
    # Invariant helper raises on informal labels
    with pytest.raises(CorpusGovernanceError, match="cannot imply clearance"):
        assert_not_implied_clearance("stable")

    with pytest.raises(CorpusGovernanceError, match="cannot imply clearance"):
        assert_not_implied_clearance("licensed")

    with pytest.raises(CorpusGovernanceError, match="cannot imply clearance"):
        assert_not_implied_clearance("true")

    with pytest.raises(CorpusGovernanceError, match="cannot imply clearance"):
        assert_not_implied_clearance("rights_cleared")

    # A manifest row labeled "stable" or "licensed" fails closed
    row_stable = SourceAssetManifestRow(
        source_id="vid_stable",
        corpus_version="v1",
        content_hash="s" * 64,
        status="stable",
        evidence_reference="ref-1",
        reviewer_id="rev-1",
        decision_date="2026-10-27",
    )
    manifest = SourceAssetManifest([row_stable])
    ok, reason = manifest.is_entry_eligible("vid_stable", "v1")
    assert ok is False
    assert reason == "ineligible_status_stable"

    row_licensed = SourceAssetManifestRow(
        source_id="vid_licensed",
        corpus_version="v1",
        content_hash="l" * 64,
        status="licensed",
        evidence_reference="ref-1",
        reviewer_id="rev-1",
        decision_date="2026-10-27",
    )
    manifest_lic = SourceAssetManifest([row_licensed])
    ok, reason = manifest_lic.is_entry_eligible("vid_licensed", "v1")
    assert ok is False
    assert reason == "ineligible_status_licensed"


# ---------------------------------------------------------------------------
# 8. OKF matrix matching with manifest filter enabled: cleared only survive
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_compiled_bundle(tmp_path) -> Path:
    compiled_file = tmp_path / "compiled.json"
    dim = 1024
    vec_unit = [1.0 / np.sqrt(dim)] * dim

    entries = [
        {
            "title": "Cleared Teaching 1",
            "source": "https://www.youtube.com/watch?v=vid_cleared_01",
            "source_id": "vid_cleared_01",
            "corpus_version": "v1",
            "content_hash": "c" * 64,
            "teacher": "sri-krishnaji",
            "type": "teaching",
            "status": "stable",
            "embedding": vec_unit,
            "body": "Cleared teaching content.",
            "description": "Cleared description.",
        },
        {
            "title": "Pending Teaching 2",
            "source": "https://www.youtube.com/watch?v=vid_pending_02",
            "source_id": "vid_pending_02",
            "corpus_version": "v1",
            "teacher": "sri-krishnaji",
            "type": "teaching",
            "status": "stable",
            "embedding": vec_unit,
            "body": "Pending teaching content.",
            "description": "Pending description.",
        },
        {
            "title": "Unmanifested Teaching 3",
            "source": "https://www.youtube.com/watch?v=vid_unmanifested_03",
            "source_id": "vid_unmanifested_03",
            "corpus_version": "v1",
            "teacher": "sri-krishnaji",
            "type": "teaching",
            "status": "stable",
            "rights_cleared": True,
            "verified": True,
            "embedding": vec_unit,
            "body": "Unmanifested teaching content.",
            "description": "Unmanifested description.",
        },
    ]

    compiled_file.write_text(json.dumps({"version": 2, "entries": entries}), encoding="utf-8")
    return compiled_file


def test_okf_matrix_matching_with_manifest_filter_cleared_only(mock_compiled_bundle, monkeypatch):
    dim = 1024
    query_vector = [1.0 / np.sqrt(dim)] * dim

    # Manifest clearing only vid_cleared_01; vid_pending_02 is pending; vid_unmanifested_03 is absent
    manifest = SourceAssetManifest(
        rows=[
            SourceAssetManifestRow(
                source_id="vid_cleared_01",
                corpus_version="v1",
                content_hash="c" * 64,
                status=STATUS_CLEARED,
                evidence_reference="ref-1",
                reviewer_id="human_rev",
                decision_date="2026-10-27",
            ),
            SourceAssetManifestRow(
                source_id="vid_pending_02",
                corpus_version="v1",
                content_hash="p" * 64,
                status=STATUS_PENDING,
                evidence_reference="ref-2",
                reviewer_id="human_rev",
                decision_date="2026-10-27",
            ),
        ]
    )

    # 1. Flag OFF, manifest NOT passed -> all 3 entries match
    monkeypatch.setattr(settings, "okf_governance_manifest_enabled", False)
    all_results = match_okf_entries(
        query_dense_vector=query_vector,
        top_k=10,
        min_similarity=0.45,
        compiled_path=mock_compiled_bundle,
    )
    assert len(all_results) == 3

    # 2. Flag OFF, manifest passed -> only cleared entry survives
    filtered_results = match_okf_entries(
        query_dense_vector=query_vector,
        top_k=10,
        min_similarity=0.45,
        compiled_path=mock_compiled_bundle,
        manifest=manifest,
    )
    assert len(filtered_results) == 1
    assert filtered_results[0]["title"] == "Cleared Teaching 1"

    # 3. Flag ON, manifest passed -> only cleared entry survives
    monkeypatch.setattr(settings, "okf_governance_manifest_enabled", True)
    gated_results = match_okf_entries(
        query_dense_vector=query_vector,
        top_k=10,
        min_similarity=0.45,
        compiled_path=mock_compiled_bundle,
        manifest=manifest,
    )
    assert len(gated_results) == 1
    assert gated_results[0]["title"] == "Cleared Teaching 1"

    # 4. Flag ON, manifest not passed, default manifest missing -> fails closed (0 matches)
    empty_results = match_okf_entries(
        query_dense_vector=query_vector,
        top_k=10,
        min_similarity=0.45,
        compiled_path=mock_compiled_bundle,
        manifest=None,
    )
    assert len(empty_results) == 0


def test_okf_store_integration(mock_compiled_bundle, monkeypatch):
    dim = 1024
    query_vector = [1.0 / np.sqrt(dim)] * dim

    manifest = SourceAssetManifest(
        rows=[
            SourceAssetManifestRow(
                source_id="vid_cleared_01",
                corpus_version="v1",
                content_hash="c" * 64,
                status=STATUS_CLEARED,
                evidence_reference="ref-1",
                reviewer_id="human_rev",
                decision_date="2026-10-27",
            )
        ]
    )

    store = OKFStore(directory=mock_compiled_bundle.parent, manifest=manifest)
    results = store.match_okf_entries(
        query_dense_vector=query_vector,
        top_k=5,
    )
    assert len(results) == 1
    assert results[0]["title"] == "Cleared Teaching 1"


# ---------------------------------------------------------------------------
# 9. Assert validation does not mutate underlying OKF or corpus data
# ---------------------------------------------------------------------------
def test_validation_does_not_mutate_underlying_data(mock_compiled_bundle):
    dim = 1024
    query_vector = [1.0 / np.sqrt(dim)] * dim

    original_file_bytes = mock_compiled_bundle.read_bytes()
    original_sha256 = hashlib.sha256(original_file_bytes).hexdigest()

    with open(mock_compiled_bundle, encoding="utf-8") as f:
        data = json.load(f)
    entries_before = copy.deepcopy(data["entries"])

    manifest = SourceAssetManifest(
        rows=[
            SourceAssetManifestRow(
                source_id="vid_cleared_01",
                corpus_version="v1",
                content_hash="c" * 64,
                status=STATUS_CLEARED,
                evidence_reference="ref-1",
                reviewer_id="human_rev",
                decision_date="2026-10-27",
            )
        ]
    )

    # Perform matching with manifest filter
    results = match_okf_entries(
        query_dense_vector=query_vector,
        compiled_path=mock_compiled_bundle,
        manifest=manifest,
    )
    assert len(results) == 1

    # Verify file on disk is unchanged
    current_file_bytes = mock_compiled_bundle.read_bytes()
    assert hashlib.sha256(current_file_bytes).hexdigest() == original_sha256

    # Verify entries in json are unchanged
    with open(mock_compiled_bundle, encoding="utf-8") as f:
        data_after = json.load(f)
    assert data_after["entries"] == entries_before
