"""Tests for backend/scripts/ops/data_quality_audit.py against small,
hand-built fixtures under tests/fixtures/data_quality/ — never against the
live 745-video corpus or live Qdrant (those are exercised by running the
script directly, not by this suite).
"""

from pathlib import Path

from scripts.ops.data_quality_audit import (
    Thresholds,
    audit_corpus,
    audit_okf,
    run_audit,
)
from services.transcript_verbatim import find_verbatim

FIXTURES = Path(__file__).parent / "fixtures" / "data_quality"
CORPUS_FIXTURE = FIXTURES / "corpus"
OKF_FIXTURE = FIXTURES / "okf"


# ── find_verbatim, against the fixture corpus (task requirement: verbatim / partial / fabricated) ──


def test_find_verbatim_exact_match_is_verbatim():
    result = find_verbatim(
        "Individual transformation is at the crux of our work.",
        "clean_vid_001",
        corpus_root=CORPUS_FIXTURE,
    )
    assert result["status"] == "verbatim"
    assert result["score"] == 1.0


def test_find_verbatim_close_paraphrase_is_partial():
    result = find_verbatim(
        "Individual transformation is truly at the very crux of everyone's work.",
        "clean_vid_001",
        corpus_root=CORPUS_FIXTURE,
    )
    assert result["status"] == "partial"
    assert 0.70 <= result["score"] < 1.0


def test_find_verbatim_fabricated_quote_is_not_found():
    result = find_verbatim(
        "The secret to everlasting joy is buried deep within a golden temple somewhere.",
        "clean_vid_001",
        corpus_root=CORPUS_FIXTURE,
    )
    assert result["status"] == "not_found"


# ── audit_corpus: one fixture per defect class + the clean one ──────────


def test_audit_corpus_counts_each_defect_class():
    result = audit_corpus(CORPUS_FIXTURE)
    assert result["video_count"] == 5
    # empty_vid_002, negative_vid_003, repeat_vid_004 are hard failures.
    # soft_gaps_vid_005 and clean_vid_001 are not.
    assert result["videos_with_hard_failure"] == 3
    assert result["finding_counts"]["empty_segments"] == 1
    assert result["finding_counts"]["negative_span"] == 1
    assert result["finding_counts"]["repetition_loop"] == 1
    # negative_vid_003, repeat_vid_004, and soft_gaps_vid_005 all lack the
    # verbatim/word-timestamp/confidence layers (empty_vid_002 short-circuits
    # before these soft checks run; clean_vid_001 has all three).
    assert result["finding_counts"]["missing_verbatim_layer"] == 3
    assert result["finding_counts"]["missing_word_timestamps"] == 3
    assert result["finding_counts"]["missing_confidence"] == 3


def test_audit_corpus_clean_video_contributes_no_findings():
    result = audit_corpus(CORPUS_FIXTURE)
    clean_hits = [ex for ex in result["hard_failure_examples"] if ex["video_id"] == "clean_vid_001"]
    assert clean_hits == []


def test_audit_corpus_missing_root_reports_error_not_crash(tmp_path):
    result = audit_corpus(tmp_path / "does_not_exist")
    assert result["video_count"] == 0
    assert "error" in result


# ── audit_okf: verbatim/partial/fabricated tally, unknown attribution, duplicates ──


def test_audit_okf_tallies_verbatim_and_fabricated():
    result = audit_okf(CORPUS_FIXTURE, OKF_FIXTURE)
    assert result["entry_count"] == 5
    assert result["quotes_checked"] == 3
    assert result["verbatim"] == 1
    assert result["not_found"] == 2  # fabricated_teaching + unknown_attribution (no corpus dir)
    assert result["unknown_attribution_count"] == 1


def test_audit_okf_detects_duplicate_filename_pair():
    result = audit_okf(CORPUS_FIXTURE, OKF_FIXTURE)
    assert result["duplicate_filename_pairs"] == 1


# ── run_audit: end-to-end, thresholds, exit code ─────────────────────────


def test_run_audit_skip_qdrant_end_to_end():
    report = run_audit(
        corpus_root=CORPUS_FIXTURE,
        qdrant_url=None,
        qdrant_collection=None,
        thresholds=Thresholds(),
        skip_qdrant=True,
        qdrant_cap=None,
        okf_dir=OKF_FIXTURE,
    )
    assert report.qdrant == {"skipped": True, "reason": "--skip-qdrant"}
    assert report.coverage == {"skipped": True, "reason": "qdrant audit was skipped"}
    # 3/5 videos hard-fail (0.6) against the default 0.05 threshold -> hard check fails.
    hard_checks = {c["name"]: c for c in report.checks if c["severity"] == "hard"}
    assert hard_checks["corpus_hard_failure_rate"]["passed"] is False
    assert report.exit_code == 1


def test_run_audit_strict_thresholds_still_fail_on_known_fixture_defects():
    report = run_audit(
        corpus_root=CORPUS_FIXTURE,
        qdrant_url=None,
        qdrant_collection=None,
        thresholds=Thresholds.strict(),
        skip_qdrant=True,
        qdrant_cap=None,
        okf_dir=OKF_FIXTURE,
    )
    assert report.exit_code == 1


def test_run_audit_passes_on_a_fully_clean_fixture(tmp_path):
    clean_root = tmp_path / "corpus"
    clean_root.mkdir()
    (clean_root / "only_vid").mkdir()
    (clean_root / "only_vid" / "canonical_segments.json").write_text(
        '{"segments": [{"segment_id": "s0", "start": 0.0, "end": 1.0, "text": "Welcome to Ekam.", '
        '"verbatim_text": "Welcome to Ekam.", "confidence": -0.1, "word_timestamps": [{"word": "Welcome"}]}]}',
        encoding="utf-8",
    )
    empty_okf = tmp_path / "okf"
    empty_okf.mkdir()
    report = run_audit(
        corpus_root=clean_root,
        qdrant_url=None,
        qdrant_collection=None,
        thresholds=Thresholds(),
        skip_qdrant=True,
        qdrant_cap=None,
        okf_dir=empty_okf,
    )
    assert report.exit_code == 0
    assert all(c["passed"] for c in report.checks if c["severity"] == "hard")


def test_missing_corpus_root_fails_closed_and_logs_loudly(tmp_path, caplog):
    """In the Docker image the corpus is not copied: every quote must report
    not_found (fail-closed) AND an error must say why, instead of reading as
    'no fabrications found'."""
    missing = tmp_path / "no_such_corpus"
    with caplog.at_level("ERROR", logger="services.transcript_verbatim"):
        result = find_verbatim(
            "the teacher said these exact words about the beautiful state today",
            video_id="abc123",
            corpus_root=missing,
        )
    assert result["status"] == "not_found"
    assert any("corpus root missing" in r.getMessage() for r in caplog.records)
