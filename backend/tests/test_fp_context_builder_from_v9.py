"""Unit coverage for the v9 -> fp-context builder (phase C).

The builder is the only place that derives something the source payload does not
carry (word offsets), so the derivation rules are pinned here: where a clip is
located, where it is refused, and what the completeness classifier does. No
Qdrant and no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from domain.first_person_context import (
    CompletenessStatus,
    ParentUnit,
    SourceSpan,
    clip_text_hash,
)
from scripts.ops.build_fp_context_from_v9 import (
    DEFAULT_CORPUS_VERSION,
    _best_window,
    _completeness_status,
    build,
    transcript_words,
)

VIDEO = "vidTEST00001"
TRANSCRIPT = (
    "Namaste. Suffering is a call to awaken. When you observe the mind, "
    "the division between the observer and the observed dissolves. "
    "That is the whole teaching."
)


def _point(text: str, **overrides):
    payload = {
        "guru_id": "krishnaji",
        "teacher_id": "krishnaji",
        "video_id": VIDEO,
        "verbatim_text": text,
        "parent_id": f"{VIDEO}_v2_p1",
        "start_ms": 20000,
        "end_ms": 59520,
        "transcript_hash": hashlib.sha256(TRANSCRIPT.encode()).hexdigest(),
        "rights_cleared": True,
        "quality_status": "verified_verbatim",
        "speaker_verified": True,
        "speaker": "Sri Krishnaji",
        "provenance_kind": "speech_turn_clip",
        "source_url": f"https://www.youtube.com/watch?v={VIDEO}",
    }
    payload.update(overrides)
    return {"id": "point-1", "payload": payload, "vector": None}


def _transcripts_dir(tmp_path: Path) -> Path:
    body = f"# Test\n\n**Video ID:** `{VIDEO}`\n\n## Transcript\n\n{TRANSCRIPT}\n\n## Notes\n\nignored tail\n"
    (tmp_path / f"{VIDEO}.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_transcript_words_reads_body_and_stops_at_next_heading(tmp_path):
    words = transcript_words(_transcripts_dir(tmp_path) / f"{VIDEO}.md")
    assert words is not None
    assert "ignored" not in words
    assert words[:2] == ["Namaste.", "Suffering"]


def test_best_window_locates_a_clip_and_reports_similarity():
    transcript = transcript_words_text(TRANSCRIPT)
    clip = "when you observe the mind the division between the observer and the observed dissolves"
    start, ratio = _best_window(clip.split(), transcript)
    assert start == 7
    assert ratio >= 0.99


def test_best_window_refuses_text_that_is_not_there():
    transcript = transcript_words_text(TRANSCRIPT)
    start, ratio = _best_window(
        "completely different sentence about money and markets".split(), transcript
    )
    assert start == -1
    assert ratio == 0.0


def test_best_window_requires_a_probe_for_short_clips():
    transcript = transcript_words_text(TRANSCRIPT)
    # Clips reach the matcher already normalized (case/punctuation stripped).
    assert _best_window(["namaste"], transcript) == (0, 1.0)
    assert _best_window(["absent"], transcript) == (-1, 0.0)


def test_completeness_classifier_marks_leading_conjunctions_as_fragments():
    assert _completeness_status("and then the mind becomes still.") is CompletenessStatus.FRAGMENT
    assert _completeness_status("Suffering is a call to awaken.") is CompletenessStatus.COMPLETE


def test_build_produces_parent_and_child_payloads(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    manifest, report, _ = build(
        [_point(text)],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    parents = [row for row in manifest if row["record_type"] == "parent_unit"]
    assert len(children) == 1 and len(parents) == 1
    span = SourceSpan(**{k: v for k, v in children[0].items() if k != "record_type"})
    parent = ParentUnit(**{k: v for k, v in parents[0].items() if k != "record_type"})
    assert parent.ordered_source_span_ids == (span.source_span_id,)
    assert span.parent_unit_id == parent.parent_unit_id
    assert clip_text_hash(span.verbatim_text) == span.source_text_hash
    # The fixture point carries only the legacy clip label (speaker_verified=True) and
    # no span-level verdict, so the span must NOT claim verification.
    assert span.speaker_verified is False
    assert span.voice_verification_method is None
    assert report["quality_counters"]["speaker_label_only"] == 1
    assert report["derived_span_ids"] == 1
    assert report["quarantined"] == {}


def test_build_quarantines_unverified_speaker_and_unlocatable_text(tmp_path):
    trusted = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    manifest, report, _ = build(
        [
            _point(trusted, speaker_verified=None),
            _point("A sentence that no transcript contains at all.", speaker_verified=True),
        ],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    assert manifest == []
    assert report["quarantined"] == {"speaker_unverified": 1, "clip_text_not_locatable": 1}


def test_build_deduplicates_repeated_source_spans(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    later = "That is the whole teaching."
    manifest, report, _ = build(
        [
            _point(text),
            # Same word window, shifted timestamps: an exact duplicate, not a container.
            _point(text, start_ms=21000, end_ms=60520),
            _point(later, start_ms=30000, end_ms=60520),
        ],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    assert report["quarantined"] == {"duplicate_span": 1}
    assert [row["turn_index"] for row in children] == [0, 1]
    assert [row["source_span_index"] for row in children] == [0, 1]


def test_build_drops_a_parent_container_and_keeps_its_children(tmp_path):
    """D6: a parent clip indexed beside its own children duplicates the words."""
    child_a = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    child_b = "That is the whole teaching."
    container = f"{child_a} {child_b}"
    manifest, report, _ = build(
        [
            _point(container, start_ms=20000, end_ms=59520),
            _point(child_a, start_ms=20000, end_ms=40000),
            _point(child_b, start_ms=40000, end_ms=59520),
        ],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    assert report["quality_counters"]["container_dropped"] == 1
    assert [row["verbatim_text"] for row in children] == [child_a, child_b]
    assert not any(row["verbatim_text"] == container for row in children)


def test_build_keeps_an_overlapping_span_that_is_not_a_container(tmp_path):
    """Time containment alone is not parent/child; the text must contain the child."""
    child = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    other = "Namaste. Suffering is a call to awaken."
    manifest, report, _ = build(
        [
            _point(child, start_ms=20000, end_ms=59520),
            _point(other, start_ms=21000, end_ms=30000),
        ],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    assert report["quality_counters"].get("container_dropped", 0) == 0
    assert len([row for row in manifest if row["record_type"] == "retrieval_child"]) == 2


def test_build_output_is_deterministic(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    first, _, _ = build([_point(text)], transcripts_dir=_transcripts_dir(tmp_path))
    second, _, _ = build([_point(text)], transcripts_dir=_transcripts_dir(tmp_path))
    assert first == second


def test_build_refuses_a_point_without_a_valid_transcript_hash(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    manifest, report, _ = build(
        [_point(text, transcript_hash="not-a-hash")],
        transcripts_dir=_transcripts_dir(tmp_path),
    )
    assert manifest == []
    assert report["quarantined"] == {"transcript_hash_invalid": 1}


def transcript_words_text(text: str) -> list[str]:
    """Normalized words of an in-memory transcript, mirroring the builder."""
    import re

    return re.sub(r"[^a-z0-9 ]", "", text.lower()).split()


def test_speaker_verdict_upgrades_an_unverified_clip_and_records_the_method(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    verdicts = {
        "items": {"point-1": {"verified": True, "method": "ecapa_voxceleb_centroid_v1"}},
    }
    manifest, report, _ = build(
        [_point(text, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=verdicts,
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    assert len(children) == 1
    assert children[0]["speaker_verified"] is True
    assert children[0]["voice_verification_method"] == "ecapa_voxceleb_centroid_v1"
    assert report["speaker_verified_by_voice"] == 1


def test_speaker_verdict_that_did_not_verify_keeps_the_clip_out(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    verdicts = {"items": {"point-1": {"verified": False}}}
    manifest, report, _ = build(
        [_point(text, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=verdicts,
    )
    assert manifest == []
    assert report["quarantined"] == {"speaker_unverified": 1}


_TEXT = "When you observe the mind, the division between the observer and the observed dissolves."


def test_legacy_label_with_a_verdict_records_the_method_not_none(tmp_path):
    # Regression: the method used to be set only for spans WITHOUT the legacy label,
    # so a labelled+verified span was written with speaker_verified=True and no method.
    verdicts = {"items": {"point-1": {"verified": True, "method": "ecapa_voxceleb_centroid_v1"}}}
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=True)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=verdicts,
    )
    (child,) = [r for r in manifest if r["record_type"] == "retrieval_child"]
    assert child["speaker_verified"] is True
    assert child["voice_verification_method"] == "ecapa_voxceleb_centroid_v1"
    assert report["speaker_verified_by_voice"] == 1
    assert "speaker_label_only" not in report["quality_counters"]


def test_label_only_span_is_kept_but_never_claims_verification(tmp_path):
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=True)], transcripts_dir=_transcripts_dir(tmp_path)
    )
    (child,) = [r for r in manifest if r["record_type"] == "retrieval_child"]
    assert child["speaker_verified"] is False and child["voice_verification_method"] is None
    assert report["speaker_verified_by_voice"] == 0
    # No span in the manifest may be verified without a recorded method.
    assert all(
        r.get("voice_verification_method")
        for r in manifest
        if r.get("record_type") == "retrieval_child" and r.get("speaker_verified")
    )


def test_explicit_verdict_refusal_beats_an_inherited_label(tmp_path):
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=True)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts={"items": {"point-1": {"verified": False}}},
    )
    assert manifest == []
    assert report["quarantined"] == {"speaker_verdict_refused": 1}


def test_report_counts_clean_would_change_and_over_long_spans(tmp_path):
    # Report-only counters: nothing is edited and nothing is blocked.
    long_point = _point(_TEXT, start_ms=0, end_ms=61_000)
    manifest, report, _ = build([long_point], transcripts_dir=_transcripts_dir(tmp_path))
    assert report["quality_counters"]["span_over_max_seconds"] == 1
    assert len([r for r in manifest if r["record_type"] == "retrieval_child"]) == 1


def test_asr_words_take_precedence_over_the_transcript_file(tmp_path):
    text = (
        "When you observe the mind, the division between the observer and the observed dissolves."
    )
    asr_dir = tmp_path / "asr"
    (asr_dir / "large-v3").mkdir(parents=True)
    words = text.replace(",", "").split()
    (asr_dir / "large-v3" / f"{VIDEO}.json").write_text(
        json.dumps({"words": [{"word": w} for w in words]})
    )
    transcript_dir = tmp_path / "no_transcripts"  # force the ASR path
    manifest, report, _ = build(
        [_point(text)],
        transcripts_dir=transcript_dir,
        asr_dir=asr_dir,
        asr_model="large-v3",
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    assert len(children) == 1
    assert children[0]["asr_engine"] == "faster_whisper"
    assert children[0]["asr_model_version"] == "large-v3"
    assert report["alignment_source"] == {"asr": 1}


def test_text_edit_ledger_is_hash_only_and_names_the_stage(tmp_path):
    # A stored clip that the cleaner would still change must leave a ledger row:
    # the span, the stage, and both hashes, but never the teacher text itself.
    text = "So, So " + _TEXT
    point = _point(text)
    _manifest, report, _ = build([point], transcripts_dir=_transcripts_dir(tmp_path))
    ledger = report["text_edit_ledger"]
    stages = {row["stage"] for row in ledger}
    assert "asr_cleaner_pending" in stages
    for row in ledger:
        assert set(row) == {"source_point_id", "stage", "before_sha256", "after_sha256"}
        assert row["before_sha256"] != row["after_sha256"]
    assert _TEXT not in json.dumps(ledger)


def test_text_edit_ledger_is_empty_for_clean_text(tmp_path):
    _manifest, report, _ = build([_point(_TEXT)], transcripts_dir=_transcripts_dir(tmp_path))
    assert report["text_edit_ledger"] == []


# ---------------------------------------------------------------- P3: provenance


_V2_ROW = {
    "verified": True,
    "method": "ecapa_voxceleb_span_slice_v2",
    "cosine": 0.71,
    "margin": 0.4,
    "cosine_floor": 0.2828,
    "margin_threshold": 0.05,
    "speaker_model_revision": "rev-1",
    "calibration_revision": "cal-1",
}


def _children(manifest):
    return [r for r in manifest if r["record_type"] == "retrieval_child"]


def test_v2_verdict_row_with_full_evidence_is_written_with_full_provenance(tmp_path):
    from services.first_person_context_store import assert_speaker_provenance

    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts={"items": {"point-1": _V2_ROW}},
        built_at="2026-10-31T00:00:00+00:00",
    )
    (child,) = _children(manifest)
    assert child["speaker_verified"] is True
    assert child["voice_verification_method"] == "ecapa_voxceleb_span_slice_v2"
    assert child["voice_model_revision"] == "rev-1"
    assert child["voice_calibration_id"] == "cal-1"
    assert child["voice_score"] == 0.71
    assert child["voice_threshold_applied"] == {"cosine_floor": 0.2828, "margin_threshold": 0.05}
    assert child["voice_verified_at"] == "2026-10-31T00:00:00+00:00"
    assert child["speaker_verification_status"] == "verified"
    assert "speaker_provenance_incomplete" not in report["quality_counters"]
    assert_speaker_provenance(manifest, where="test")


def test_v2_verdict_row_missing_calibration_is_never_written_verified(tmp_path):
    from services.first_person_context_store import assert_speaker_provenance

    row = {k: v for k, v in _V2_ROW.items() if k != "calibration_revision"}
    # Unlabelled clip: nothing else vouches for the speaker, so it is quarantined.
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts={"items": {"point-1": row}},
    )
    assert manifest == []
    assert report["quarantined"] == {"speaker_unverified": 1}

    # Labelled clip: stored, but demoted to pending_voice_check and counted.
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=True)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts={"items": {"point-1": row}},
    )
    (child,) = _children(manifest)
    assert child["speaker_verified"] is False
    assert child["voice_verification_method"] is None
    assert child["speaker_verification_status"] == "pending_voice_check"
    assert report["quality_counters"]["speaker_provenance_incomplete"] == 1
    assert_speaker_provenance(manifest, where="test")


def test_row_level_evidence_may_come_from_the_verdict_document(tmp_path):
    row = {k: v for k, v in _V2_ROW.items() if k not in ("cosine_floor", "margin_threshold")}
    doc = {"items": {"point-1": row}, "cosine_floor": 0.2828, "threshold": 0.05}
    manifest, _, _ = build(
        [_point(_TEXT, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=doc,
    )
    (child,) = _children(manifest)
    assert child["speaker_verified"] is True
    assert child["voice_threshold_applied"] == {"cosine_floor": 0.2828, "margin_threshold": 0.05}


def test_label_only_span_is_pending_voice_check(tmp_path):
    manifest, _, _ = build(
        [_point(_TEXT, speaker_verified=True)], transcripts_dir=_transcripts_dir(tmp_path)
    )
    (child,) = _children(manifest)
    assert child["speaker_verification_status"] == "pending_voice_check"


def test_legacy_centroid_rows_are_counted_and_keep_their_exemption(tmp_path):
    verdicts = {"items": {"point-1": {"verified": True, "cosine": 0.5, "margin": 0.2}}}
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=verdicts,
    )
    (child,) = _children(manifest)
    assert child["voice_verification_method"] == "ecapa_voxceleb_centroid_v1"
    assert child["voice_score"] == 0.5
    assert report["quality_counters"]["speaker_legacy_centroid"] == 1


def test_unknown_verdict_method_is_not_promoted(tmp_path):
    verdicts = {"items": {"point-1": {"verified": True, "method": "vibes_v9"}}}
    manifest, report, _ = build(
        [_point(_TEXT, speaker_verified=None)],
        transcripts_dir=_transcripts_dir(tmp_path),
        speaker_verdicts=verdicts,
    )
    assert manifest == []
    assert report["quarantined"] == {"speaker_unverified": 1}
