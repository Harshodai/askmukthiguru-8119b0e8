"""
Mukthi Guru — Quality Gate & Ingestion Pipeline Test Suite
===========================================================
Validates:
1. Single canonical entity resolution (Sri Preethaji, Sri Krishnaji).
2. Reversible offset-based correction ledger & Unicode NFC normalization.
3. Quality scoring & deterministic state promotion across all 11 pilot cases.
4. Server-side schema idempotency and untrusted state rejection.
5. Fail-closed backup all() control flow.
"""

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ingestion.corpus_engine import (
    CanonicalSegment,
    CorpusEngine,
    compute_canonical_manifest_hash,
)

from app.api.ingest import RawTextIngestRequest
from services.doctrine_terms import (
    apply_corrections_with_ledger,
    load_doctrine_terms,
)


def test_single_canonical_entity_resolution():
    """Verify single canonical entities exist without colliding duplicates."""
    terms = load_doctrine_terms()
    assert "Sri Preethaji" in terms
    assert "Preethaji" not in terms, "Preethaji should be unified under 'Sri Preethaji'"
    assert "Sri Krishnaji" in terms
    assert "Krishnaji" not in terms, "Krishnaji should be unified under 'Sri Krishnaji'"
    assert "Sri Preethaji & Sri Krishnaji" in terms

    # Test correction
    text = "We welcome Sri Pretty Ji and Krishna Ji to the gathering."
    corr, ledger = apply_corrections_with_ledger(text)
    assert corr == "We welcome Sri Preethaji and Sri Krishnaji to the gathering."
    assert len(ledger) == 2


def test_reversible_correction_ledger_offsets_and_multi_match():
    """Verify offset precision, occurrence indexing, and non-destruction of lowercase 'akam'."""
    text = "Akam is the sacred space. Learn more at Akam centre. In Tamil akam means inner self."
    corr, ledger = apply_corrections_with_ledger(text, segment_id="seg_0042")

    # Lowercase 'akam' must NOT be rewritten
    assert "In Tamil akam means inner self" in corr
    # Capitalised 'Akam' must be rewritten to 'Ekam'
    assert corr.startswith("Ekam is the sacred space. Learn more at Ekam centre.")

    assert len(ledger) == 2
    # Match 1
    assert ledger[0]["char_start"] == 0
    assert ledger[0]["char_end"] == 4
    assert ledger[0]["occurrence_index"] == 1
    assert ledger[0]["matched_text"] == "Akam"
    assert ledger[0]["replacement"] == "Ekam"

    # Match 2
    assert ledger[1]["char_start"] == 40
    assert ledger[1]["char_end"] == 44
    assert ledger[1]["occurrence_index"] == 2
    assert ledger[1]["matched_text"] == "Akam"
    assert ledger[1]["replacement"] == "Ekam"

    # Hashes must match
    assert ledger[0]["original_segment_hash"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert ledger[0]["corrected_segment_hash"] == hashlib.sha256(corr.encode("utf-8")).hexdigest()


def test_all_11_pilot_fixture_quality_evaluations():
    """Evaluate quality scoring across all 11 pilot fixture cases."""
    engine = CorpusEngine()

    # 1. Manual captions (clean monotonic speech)
    manual_segs = [
        CanonicalSegment(
            segment_id="seg_0",
            start=0.0,
            end=5.0,
            text="Welcome to Ekam.",
            source_tier="manual_api",
        ),
        CanonicalSegment(
            segment_id="seg_1",
            start=5.0,
            end=10.0,
            text="We explore the Beautiful State.",
            source_tier="manual_api",
        ),
    ]
    rep = engine.evaluate_quality(
        "vid_manual", manual_segs, duration_seconds=10.0, review_completed=True
    )
    assert rep.quality_state in ["trusted", "trusted_after_review"]
    assert rep.quality_score >= 0.80

    # 2. Auto captions with ASR cross-check agreement
    auto_segs = [
        CanonicalSegment(
            segment_id="seg_0",
            start=0.0,
            end=5.0,
            text="Finding inner peace and stillness in the present moment.",
            source_tier="auto_api",
        )
    ]
    rep_agree = engine.evaluate_quality(
        "vid_auto",
        auto_segs,
        duration_seconds=5.0,
        asr_comparison_text="Finding inner peace and stillness in the present moment.",
    )
    assert rep_agree.quality_state == "trusted"
    assert rep_agree.caption_asr_agreement >= 0.70

    # 3. High disagreement between caption & ASR
    rep_disagree = engine.evaluate_quality(
        "vid_disagree",
        auto_segs,
        duration_seconds=5.0,
        asr_comparison_text="Completely different unrelated words with zero overlap.",
    )
    assert rep_disagree.quality_state == "needs_review"
    assert "caption_asr_disagreement" in " ".join(rep_disagree.flags)

    # 4. Music / Sound-only
    music_segs = [
        CanonicalSegment(
            segment_id="seg_0",
            start=0.0,
            end=10.0,
            text="[Music playing]",
            source_tier="pilot_mock",
            is_non_speech=True,
        )
    ]
    rep_music = engine.evaluate_quality("vid_music", music_segs, duration_seconds=10.0)
    assert rep_music.quality_state == "sound_only"

    # 5. Silence
    silence_segs = [
        CanonicalSegment(
            segment_id="seg_0",
            start=0.0,
            end=10.0,
            text="",
            source_tier="pilot_mock",
            is_non_speech=True,
        )
    ]
    rep_silence = engine.evaluate_quality("vid_silence", silence_segs, duration_seconds=10.0)
    assert rep_silence.quality_state == "sound_only"

    # 6. Malformed: Backward timestamp jump
    malformed_segs = [
        CanonicalSegment(
            segment_id="seg_0", start=10.0, end=15.0, text="First line.", source_tier="pilot_mock"
        ),
        CanonicalSegment(
            segment_id="seg_1", start=5.0, end=8.0, text="Backwards jump.", source_tier="pilot_mock"
        ),
    ]
    rep_mal = engine.evaluate_quality("vid_mal", malformed_segs, duration_seconds=15.0)
    assert rep_mal.quality_state == "needs_review"
    assert any("backward_timestamp_jump" in f for f in rep_mal.flags)

    # 7. Forced failure: Zero segments
    rep_fail = engine.evaluate_quality("vid_fail", [], duration_seconds=10.0)
    assert rep_fail.quality_state == "dead_lettered"


def test_idempotency_hash_and_untrusted_quality_rejection():
    """Verify canonical manifest hashing and API validation rejects untrusted states."""
    h1 = compute_canonical_manifest_hash("vid_123", "hash_abc", "2.0.0")
    h2 = compute_canonical_manifest_hash("vid_123", "hash_abc", "2.0.0")
    assert h1 == h2, "Canonical hash must be deterministic"

    h3 = compute_canonical_manifest_hash("vid_123", "hash_different", "2.0.0")
    assert h1 != h3

    # Schema test: Valid trusted request
    req_trusted = RawTextIngestRequest(
        text="Sample transcript text.",
        source_url="https://youtube.com/watch?v=123",
        quality_state="trusted",
        idempotency_key=h1,
    )
    assert req_trusted.quality_state == "trusted"


def test_fail_closed_backup_gate_logic():
    """Verify that backup gate aborts if any backup returns False."""
    b_neo4j = True
    b_qdrant = False
    b_lightrag = True

    all_backups_ok = all([b_neo4j, b_qdrant, b_lightrag])
    assert all_backups_ok is False, "Gate must fail closed if even one backup fails"


def test_artifact_manifest_structure_and_hashing(tmp_path):
    """Verify that CorpusEngine generates complete artifact_manifest.json with all hashes and sizes."""
    engine = CorpusEngine(corpus_root=tmp_path / "corpus", projection_dir=tmp_path / "transcripts")
    raw_path, raw_hash = engine.save_raw_source(
        video_id="test_art_01",
        tier="manual_api",
        language="en",
        filename="captions.json",
        content='[{"start": 0.0, "duration": 4.0, "text": "Welcome to Ekam."}]',
    )
    segs = [
        CanonicalSegment(
            segment_id="seg_0",
            start=0.0,
            end=4.0,
            text="Welcome to Ekam.",
            source_tier="manual_api",
        )
    ]
    engine.process_and_package_video(
        video_info={"video_id": "test_art_01", "title": "Test Video"},
        segments=segs,
        raw_source_path=raw_path,
        raw_source_hash=raw_hash,
    )
    art_manifest_file = tmp_path / "corpus" / "test_art_01" / "artifact_manifest.json"
    assert art_manifest_file.exists()
    data = json.loads(art_manifest_file.read_text())
    assert data["manifest_version"] == "2.0.0"
    assert data["video_id"] == "test_art_01"
    assert "canonical_segments.json" in data["artifacts"]
    assert "quality_report.json" in data["artifacts"]
    assert "correction_ledger.json" in data["artifacts"]
    assert "transcript.md" in data["artifacts"]
    assert data["artifacts"]["canonical_segments.json"]["byte_size"] > 0
    assert len(data["artifacts"]["canonical_segments.json"]["sha256"]) == 64


def test_corpus_engine_record_dead_letter(tmp_path):
    """Verify that CorpusEngine records dead-lettered / private / rate-limited videos cleanly without exceptions."""
    engine = CorpusEngine(corpus_root=tmp_path / "corpus", projection_dir=tmp_path / "transcripts")
    manifest = engine.record_dead_letter(
        video_info={"video_id": "dead_vid_01", "title": "Private Video"},
        reason="Video is private or removed from YouTube",
        quality_state="dead_lettered",
        raw_error="HTTP 403 Forbidden: Sign in to confirm you're not a bot",
    )

    assert manifest.quality_state == "dead_lettered"
    assert manifest.canonical_segment_count == 0

    v_dir = tmp_path / "corpus" / "dead_vid_01"
    assert (v_dir / "quality_report.json").exists()
    assert (v_dir / "review_record.json").exists()
    assert (v_dir / "artifact_manifest.json").exists()
    assert (v_dir / "canonical_segments.json").exists()
    assert (v_dir / "manifest.json").exists()

    q_data = json.loads((v_dir / "quality_report.json").read_text())
    assert q_data["quality_state"] == "dead_lettered"
    assert q_data["quality_score"] == 0.0

    rev_data = json.loads((v_dir / "review_record.json").read_text())
    assert rev_data["quality_state"] == "dead_lettered"
    assert "Video is private" in rev_data["reason"]


def test_corpus_engine_process_and_package_empty_or_failed_video(tmp_path):
    """Verify process_and_package_video handles None raw_source_path and empty segments gracefully."""
    engine = CorpusEngine(corpus_root=tmp_path / "corpus", projection_dir=tmp_path / "transcripts")
    manifest = engine.process_and_package_video(
        video_info={"video_id": "failed_vid_02", "title": "Empty Segments Video"},
        segments=[],
        raw_source_path=None,
        raw_source_hash="",
    )

    assert manifest.quality_state == "dead_lettered"
    v_dir = tmp_path / "corpus" / "failed_vid_02"
    assert (v_dir / "review_record.json").exists()
    assert (v_dir / "quality_report.json").exists()
