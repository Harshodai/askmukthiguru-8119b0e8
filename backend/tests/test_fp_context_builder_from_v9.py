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
    assert span.speaker_verified is True
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
            _point(text, start_ms=21000),
            _point(later, start_ms=30000),
        ],
        transcripts_dir=_transcripts_dir(tmp_path),
        corpus_version=DEFAULT_CORPUS_VERSION,
        min_alignment=0.90,
    )
    children = [row for row in manifest if row["record_type"] == "retrieval_child"]
    assert report["quarantined"] == {"duplicate_span": 1}
    assert [row["turn_index"] for row in children] == [0, 1]
    assert [row["source_span_index"] for row in children] == [0, 1]


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
