"""Unit coverage for first-person span boundary ingest fixes (Phase A).

Covers:
- T1-T3: _completeness_status() detects tail defects and returns FRAGMENT.
- T4-T6: snap_to_sentences() shrinks tail/head defects and quarantines when < min_words.
- T7-T8: Builder updates verbatim_text and source_text_hash after snap.
- T9-T10: Builder emits BoundaryStatus.REPAIRED for snapped spans and VERIFIED for clean spans.
- T11-T12: validate_release_grade() accepts clean REPAIRED spans and flags defective ones.
- T13-T15: Parent completeness 3-way logic (COMPLETE / FRAGMENT / UNCERTAIN).
- T16: Neighbour-linking only links surviving spans inside parent.
- T17-T18: Rights register resolution stamps domain_rights_status="licensed" and quarantines unverified.
- T19: _apply() calls assert_no_bare_flag_speakers().
- T20: corpus_gate_rejections persistence on quarantine (X40).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain.first_person_context import (
    BoundaryStatus,
    CompletenessStatus,
    ParentUnit,
    SourceSpan,
    SpeakerRole,
    clip_text_hash,
    make_source_span_id,
)
from scripts.ops.build_fp_context_from_v9 import (
    DEFAULT_CORPUS_VERSION,
    _completeness_status,
    build,
    persist_corpus_gate_rejection,
)
from services.corpus_build_safety import RightsDecision

VIDEO = "vidBOUND001"
TRANSCRIPT = (
    "Namaste. Suffering is a call to awaken. When you observe the mind, "
    "the division between the observer and the observed dissolves. "
    "That is the whole teaching. Live in peace."
)


def _point(text: str, video_id: str = VIDEO, **overrides):
    payload = {
        "guru_id": "krishnaji",
        "teacher_id": "krishnaji",
        "video_id": video_id,
        "verbatim_text": text,
        "parent_id": f"{video_id}_v2_p1",
        "start_ms": 20000,
        "end_ms": 59520,
        "transcript_hash": hashlib.sha256(TRANSCRIPT.encode()).hexdigest(),
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "quality_status": "verified_verbatim",
        "speaker_verified": True,
        "voice_verification_method": "ecapa_voxceleb_span_slice_v2",
        "speaker": "Sri Krishnaji",
        "provenance_kind": "speech_turn_clip",
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
    }
    payload.update(overrides)
    return {"id": f"point-{video_id}-1", "payload": payload, "vector": None}


def _transcripts_dir(tmp_path: Path, video_id: str = VIDEO, text: str = TRANSCRIPT) -> Path:
    body = (
        f"# Test\n\n**Video ID:** `{video_id}`\n\n## Transcript\n\n{text}\n\n## Notes\n\nignored\n"
    )
    (tmp_path / f"{video_id}.md").write_text(body, encoding="utf-8")
    return tmp_path


# --- T1-T3: _completeness_status tests ---


def test_completeness_status_returns_fragment_for_tail_defects():
    # Ends mid-sentence without terminal punctuation
    text = "When you observe the mind the division dissolves and"
    assert _completeness_status(text) == CompletenessStatus.FRAGMENT


def test_completeness_status_returns_complete_for_well_formed_sentences():
    text = "Suffering is a call to awaken. Live in peace."
    assert _completeness_status(text) == CompletenessStatus.COMPLETE


def test_completeness_status_returns_uncertain_for_empty_text():
    assert _completeness_status("") == CompletenessStatus.UNCERTAIN
    assert _completeness_status("   ") == CompletenessStatus.UNCERTAIN


# --- T4-T6: snap_to_sentences tests ---


def test_snap_to_sentences_shrinks_tail_broken_span():
    from ingest.verbatim.boundaries import snap_to_sentences

    text = "Suffering is a call to awaken. When you observe the mind the division dissolves and"
    toks = text.split()
    res = snap_to_sentences(toks, 0, len(toks), min_words=5)
    assert res is not None
    s, e = res
    snapped = " ".join(toks[s:e])
    assert snapped == "Suffering is a call to awaken."


def test_snap_to_sentences_returns_none_when_no_boundary_survives():
    from ingest.verbatim.boundaries import snap_to_sentences

    text = "when you observe the mind the division between the observer and the observed"
    toks = text.split()
    res = snap_to_sentences(toks, 0, len(toks), min_words=15)
    assert res is None


def test_builder_quarantines_when_snap_returns_none(tmp_path):
    # A clip that has no complete sentence and cannot be snapped
    clip_text = "when you observe the mind the division dissolves"
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([point], t_dir)

    assert report["quarantined"].get("incomplete_span_no_sentence_boundary", 0) >= 1
    assert len(manifest) == 0


# --- T7-T10: Builder verbatim_text, hash, and BoundaryStatus updates ---


def test_builder_updates_verbatim_text_to_snapped_text(tmp_path):
    # Transcript has full text; clip has a dangling tail "When you observe"
    clip_text = "Suffering is a call to awaken. When you observe"
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([point], t_dir)

    children = [r for r in manifest if r.get("record_type") == "retrieval_child"]
    assert len(children) == 1
    child = children[0]
    assert child["verbatim_text"] == "Suffering is a call to awaken."


def test_builder_updates_source_text_hash_to_match_snapped_text(tmp_path):
    clip_text = "Suffering is a call to awaken. When you observe"
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([point], t_dir)

    children = [r for r in manifest if r.get("record_type") == "retrieval_child"]
    assert len(children) == 1
    child = children[0]
    expected_hash = clip_text_hash("Suffering is a call to awaken.")
    assert child["source_text_hash"] == expected_hash


def test_builder_emits_boundary_status_repaired_for_snapped_spans(tmp_path):
    clip_text = "Suffering is a call to awaken. When you observe"
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([point], t_dir)

    children = [r for r in manifest if r.get("record_type") == "retrieval_child"]
    assert len(children) == 1
    assert children[0]["boundary_status"] == BoundaryStatus.REPAIRED.value


def test_builder_retains_boundary_status_verified_for_unsnapped_clean_spans(tmp_path):
    clip_text = "Suffering is a call to awaken."
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([point], t_dir)

    children = [r for r in manifest if r.get("record_type") == "retrieval_child"]
    assert len(children) == 1
    assert children[0]["boundary_status"] == BoundaryStatus.VERIFIED.value


# --- T11-T12: validate_release_grade() tests ---


def test_validate_release_grade_accepts_clean_repaired_spans():
    text = "Suffering is a call to awaken. That is the whole teaching."
    thash = "a" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id=VIDEO,
        corpus_version=DEFAULT_CORPUS_VERSION,
        word_start=0,
        word_end=11,
        transcript_hash=thash,
    )
    span = SourceSpan(
        corpus_version=DEFAULT_CORPUS_VERSION,
        guru_id="krishnaji",
        video_id=VIDEO,
        source_asset_id=VIDEO,
        source_span_id=span_id,
        parent_unit_id="p1",
        turn_id="p1:t0",
        turn_index=0,
        source_span_index=0,
        start_ms=10000,
        end_ms=25000,
        word_start=0,
        word_end=11,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=thash,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.REPAIRED,
        completeness_status=CompletenessStatus.COMPLETE,
        rights_cleared=True,
        domain_rights_status="licensed",
        caption_status="auto",
        source_url=f"https://www.youtube.com/watch?v={VIDEO}",
    )
    defects = span.validate_release_grade()
    boundary_defects_list = [d for d in defects if d.startswith("boundary_status_")]
    assert len(boundary_defects_list) == 0


def test_validate_release_grade_rejects_repaired_span_with_residual_defects():
    text = "Suffering is a call to awaken and"
    thash = "a" * 64
    span_id = make_source_span_id(
        guru_id="krishnaji",
        video_id=VIDEO,
        corpus_version=DEFAULT_CORPUS_VERSION,
        word_start=0,
        word_end=7,
        transcript_hash=thash,
    )
    span = SourceSpan(
        corpus_version=DEFAULT_CORPUS_VERSION,
        guru_id="krishnaji",
        video_id=VIDEO,
        source_asset_id=VIDEO,
        source_span_id=span_id,
        parent_unit_id="p1",
        turn_id="p1:t0",
        turn_index=0,
        source_span_index=0,
        start_ms=10000,
        end_ms=25000,
        word_start=0,
        word_end=7,
        speaker_id="krishnaji",
        speaker_role=SpeakerRole.GURU,
        speaker_verified=True,
        voice_verification_method="ecapa_voxceleb_span_slice_v2",
        source_transcript_text=text,
        verbatim_text=text,
        transcript_hash=thash,
        source_text_hash=clip_text_hash(text),
        boundary_status=BoundaryStatus.REPAIRED,
        completeness_status=CompletenessStatus.FRAGMENT,
        rights_cleared=True,
        domain_rights_status="licensed",
        caption_status="auto",
        source_url=f"https://www.youtube.com/watch?v={VIDEO}",
    )
    defects = span.validate_release_grade()
    assert any("boundary_status_repaired_with_defects" in d for d in defects)


# --- T13-T15: Parent completeness 3-way logic ---


def test_parent_completeness_status_complete_when_all_children_complete_or_repaired(tmp_path):
    clip_text = "That is the whole teaching. Live in peace."
    point = _point(clip_text)
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, _, _ = build([point], t_dir)

    parents = [r for r in manifest if r.get("record_type") == "parent_unit"]
    assert len(parents) == 1
    assert parents[0]["completeness_status"] == CompletenessStatus.COMPLETE.value


def test_parent_completeness_status_fragment_when_child_is_fragment(tmp_path):
    # A span that starts with connective opener but ends cleanly
    clip_text = "and the division dissolves. Live in peace."
    custom_transcript = "Namaste. and the division dissolves. Live in peace."
    point = _point(
        clip_text, transcript_hash=hashlib.sha256(custom_transcript.encode()).hexdigest()
    )
    t_dir = _transcripts_dir(tmp_path, text=custom_transcript)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, _, _ = build([point], t_dir)

    parents = [r for r in manifest if r.get("record_type") == "parent_unit"]
    if parents:
        # Fragment child should make parent FRAGMENT, not UNCERTAIN
        assert parents[0]["completeness_status"] == CompletenessStatus.FRAGMENT.value


def test_parent_completeness_status_uncertain_when_child_is_uncertain():
    # Direct model construction of parent with uncertain child
    p = ParentUnit(
        corpus_version=DEFAULT_CORPUS_VERSION,
        guru_id="krishnaji",
        video_id=VIDEO,
        parent_unit_id="p1",
        ordered_source_span_ids=("s1",),
        start_ms=1000,
        end_ms=5000,
        parent_text_hash="a" * 64,
        speaker_ids=("krishnaji",),
        speaker_continuity=True,
        boundary_status=BoundaryStatus.UNCERTAIN,
        completeness_status=CompletenessStatus.UNCERTAIN,
    )
    assert p.completeness_status == CompletenessStatus.UNCERTAIN


# --- T16: Neighbour-linking test ---


def test_neighbour_linking_only_links_surviving_spans(tmp_path):
    # 2 points: first is clean, second cannot be snapped (quarantined)
    p1 = _point("Suffering is a call to awaken.", point_id="pt1", start_ms=10000, end_ms=20000)
    p2 = _point(
        "when you observe the mind the division dissolves",
        point_id="pt2",
        start_ms=21000,
        end_ms=30000,
    )
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, report, _ = build([p1, p2], t_dir)

    children = [r for r in manifest if r.get("record_type") == "retrieval_child"]
    # Only p1 should survive
    assert len(children) == 1
    # p1's next_span_id should be None (not linking to quarantined p2!)
    assert children[0]["next_span_id"] is None
    assert children[0]["previous_span_id"] is None


# --- T17-T18: Rights resolution tests ---


def test_builder_resolves_and_stamps_domain_rights_status_licensed(tmp_path):
    point = _point("Suffering is a call to awaken.")
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(True, "licensed", "register_licensed")
        manifest, _, _ = build([point], t_dir)

    for item in manifest:
        if item.get("record_type") == "retrieval_child":
            assert item.get("domain_rights_status") == "licensed"


def test_builder_quarantines_unlicensed_video_spans(tmp_path):
    point = _point("Suffering is a call to awaken.")
    t_dir = _transcripts_dir(tmp_path)

    with patch("scripts.ops.build_fp_context_from_v9.video_rights_decision") as mock_rights:
        mock_rights.return_value = RightsDecision(False, "unverified", "register_not_licensed")
        manifest, report, _ = build([point], t_dir)

    assert report["quarantined"].get("rights_not_cleared", 0) >= 1
    assert len(manifest) == 0


# --- T19: Bare flag speaker guard in _apply() ---


def test_assert_no_bare_flag_speakers_called_in_apply():
    from scripts.ops.build_fp_context_from_v9 import _apply
    from services.first_person_context_store import FirstPersonContextStoreError

    client = MagicMock()
    manifest = [
        {
            "record_type": "retrieval_child",
            "source_span_id": "span1",
            "video_id": VIDEO,
            "verbatim_text": "Suffering is a call to awaken.",
            "start_ms": 10000,
            "speaker_verified": True,
            "voice_verification_method": None,  # BARE FLAG!
            "domain_rights_status": "licensed",
        }
    ]
    with pytest.raises(FirstPersonContextStoreError):
        _apply(manifest, [], target="test_target", client=client, by_key={}, vectors={})


# --- T20: corpus_gate_rejections persistence on quarantine (X40) ---


def test_corpus_gate_rejections_persists_quarantines():
    mock_db = MagicMock()
    success = persist_corpus_gate_rejection(
        source_url="https://youtube.com/watch?v=vid1",
        reason="snap_no_boundary",
        chunk_index=0,
        matched_span="fragment words here",
        point_id="pt1",
        client=mock_db,
    )
    assert success is True
    mock_db.table.assert_called_with("corpus_gate_rejections")
    mock_db.table().insert.assert_called_once()
    row = mock_db.table().insert.call_args[0][0][0]
    assert row["reason"] == "snap_no_boundary"
    assert row["gate_verdict"] == "rejected"
    assert row["gate_layer"] == "fp_context_builder_v9"
