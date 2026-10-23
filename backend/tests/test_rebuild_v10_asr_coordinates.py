"""Focused tests for ``scripts.ops.rebuild_v10_asr_coordinates``.

Phase 3 rebuilds the first-person v10 ASR word coordinates and citation audio
windows from the immutable word-timed transcript artifacts. These tests pin:

* exact reconstruction, coordinate bounds and audio-window bounds;
* that a span is never silently accepted when its coordinates or its window
  disagree with the artifact;
* that multilingual (non-ASCII) spans are tokenized and validated rather than
  marked unverifiable;
* that the rebuilt candidate is deterministic and never mutates a source;
* the known baseline defects (the 298 audio-window failures, the 18 citations
  past the aligned audio extent, the 41 out-of-range coordinates) so a
  regression that "fixes" them by accident is visible.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
if _HERE.parents[1].name == "app" or _HERE.parents[1] == Path("/app"):
    _BACKEND = Path("/app")
else:
    _BACKEND = _HERE.parents[1]
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import rebuild_v10_asr_coordinates as rebuild  # noqa: E402

SCRIPT_PATH = _BACKEND / "scripts" / "ops" / "rebuild_v10_asr_coordinates.py"
ATTR_ROOT = Path("/Users/harshodaikolluru/mukthiguru_attribution_data")
V10_EXPORT = _REPO_ROOT / ".work/public_release/v10_points_export.json"

#: Recorded baseline from
#: ``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`` and
#: ``audits/evidence/public_release_v10_strict_audit_2026-10-21.json``.
KNOWN_AUDIO_WINDOW_FAILURES = 298
KNOWN_BEYOND_AUDIO = 18
KNOWN_OUT_OF_RANGE_COORDINATES = 41
KNOWN_TOTAL_SPANS = 2737


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _write_wav(path: Path, duration_ms: int, sample_rate: int = 16000) -> Path:
    """Write a real, complete PCM WAV so the duration check has real audio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int((duration_ms / 1000.0) * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack("<h", 0) * frames)
    return path


def _write_stub_wav(path: Path, declared_ms: int, sample_rate: int = 16000) -> Path:
    """Write a header-only WAV: a valid header that declares audio it lacks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int((declared_ms / 1000.0) * sample_rate)
    data_bytes = frames * 2
    header = b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", data_bytes)
    path.write_bytes(header)
    return path


def _timed_artifact(
    root: Path,
    video_id: str,
    words: list[str],
    *,
    start_s: float = 1.0,
    step_s: float = 0.5,
) -> Path:
    """Write ``transcripts_B/{video_id}.json`` — the immutable timing artifact."""
    entries = []
    for index, word in enumerate(words):
        begin = start_s + index * step_s
        entries.append(
            {
                "w": word,
                "start": round(begin, 3),
                "end": round(begin + step_s * 0.8, 3),
                "conf": 0.99,
                "disputed": False,
                "alt": None,
                "aligned": True,
                "spk": "K",
            }
        )
    target = root / "mass_ingest_2026-10" / "transcripts_B" / f"{video_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return target


def _span_payload(
    *,
    span_id: str = "span-1",
    video_id: str = "vid-1",
    text: str = "Today I want you to hold the intention to live free.",
    start_ms: int = 1000,
    end_ms: int = 4000,
    word_start: int = 0,
    word_end: int = 9,
    declared_hash: str | None = None,
    parent_id: str = "parent-1",
    guru_id: str = "krishnaji",
) -> dict:
    return {
        "record_type": "retrieval_child",
        "source_span_id": span_id,
        "parent_unit_id": parent_id,
        "video_id": video_id,
        "source_asset_id": video_id,
        "guru_id": guru_id,
        "verbatim_text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "word_start": word_start,
        "word_end": word_end,
        "source_text_hash": declared_hash
        if declared_hash is not None
        else rebuild.clip_text_hash(text),
        "transcript_hash": "b" * 64,
        "corpus_version": "fp-context-transcript-v1",
        "turn_id": "parent-1:t0",
        "turn_index": 0,
        "source_span_index": 0,
        "previous_span_id": None,
        "next_span_id": None,
    }


def _export(path: Path, payloads: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "first-person-v10-points-export-v1",
                "result": {
                    "points": [
                        {"id": f"point-{index}", "payload": payload}
                        for index, payload in enumerate(payloads)
                    ]
                },
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _run(
    tmp_path: Path,
    payloads: list[dict],
    *,
    policy: str = rebuild.POLICY_EXACT,
    coverage_floor: float = 0.90,
    extra: list[str] | None = None,
) -> tuple[int, list[dict], list[dict], list[dict], dict]:
    export = _export(tmp_path / "v10.json", payloads)
    out = tmp_path / "candidate.jsonl"
    parents = tmp_path / "parents.jsonl"
    quarantine = tmp_path / "quarantine.jsonl"
    variants = tmp_path / "variants.jsonl"
    summary = tmp_path / "summary.json"
    argv = [
        "--v10-points",
        str(export),
        "--attr-root",
        str(tmp_path / "attr"),
        "--out",
        str(out),
        "--parents",
        str(parents),
        "--quarantine",
        str(quarantine),
        "--variants",
        str(variants),
        "--summary",
        str(summary),
        "--reconstruction-policy",
        policy,
        "--coverage-floor",
        str(coverage_floor),
        "--generated-at-utc",
        "2026-10-21T00:00:00+00:00",
    ]
    if extra:
        argv += extra
    code = rebuild.main(argv)

    def _read(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    data = json.loads(summary.read_text(encoding="utf-8")) if summary.is_file() else {}
    return code, _read(out), _read(quarantine), _read(variants), data


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def test_normalization_is_multilingual_aware():
    """A non-Latin span must be tokenized, not silently erased."""
    assert rebuild.normalize_text("नमस्ते") == "नमस्ते"
    assert rebuild.tokenize("यह एक परीक्षण है") == ["यह", "एक", "परीक्षण", "है"]
    assert rebuild.normalize_text("Mind's peace — truly") == "minds peace truly"
    assert rebuild.normalize_text("40,000 people") == "40000 people"


def test_ascii_tokenizer_reports_the_multilingual_gap():
    assert rebuild._ascii_tokens("यह एक परीक्षण") == []
    assert rebuild._ascii_tokens("hello world") == ["hello", "world"]


def test_normalization_version_is_declared():
    assert rebuild.NORMALIZATION_VERSION == "fp-norm-unicode-v1"
    assert rebuild.COORDINATE_SPACE_VERSION == "fp-coords-v1"


# ---------------------------------------------------------------------------
# Exact reconstruction
# ---------------------------------------------------------------------------
def test_exact_reconstruction(tmp_path):
    words = ["Today", "I", "want", "you", "to", "hold", "the", "intention", "to", "live", "free."]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    text = "Today I want you to hold the intention to live free."
    code, candidate, quarantine, _variants, summary = _run(
        tmp_path, [_span_payload(text=text, word_end=len(words))]
    )
    assert code == rebuild.EXIT_RELEASE_BLOCKED
    assert len(candidate) == 1
    row = candidate[0]
    assert row["reconstruction_exact"] is True
    assert row["reconstruction_tier"] == rebuild.TIER_EXACT
    assert row["word_start"] == 0
    assert row["word_end"] == len(words)
    assert row["reconstructed_text"] == text
    assert row["source_text_hash"] == rebuild.clip_text_hash(text)
    assert row["id_rederives"] is True
    assert row["audio_end_ms"] > row["audio_start_ms"]
    assert quarantine == []


def test_reconstruction_from_the_artifact_not_from_the_payload(tmp_path):
    """The payload's word coordinates are ignored; the artifact decides."""
    words = ["alpha", "beta", "gamma", "delta", "epsilon"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(
        text="alpha beta gamma delta epsilon",
        word_start=0,
        word_end=99,  # deliberately wrong
    )
    _code, candidate, _q, _v, _s = _run(tmp_path, [payload])
    assert candidate[0]["word_end"] == len(words)
    assert candidate[0]["coordinates_changed_vs_live"] is True


def test_legacy_v10_coordinate_mismatch_is_reported(tmp_path):
    """A legacy/v10 coordinate mismatch is surfaced, not silently accepted."""
    words = ["one", "two", "three", "four"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="one two three four", word_start=7, word_end=9)
    _code, candidate, _q, _v, summary = _run(tmp_path, [payload])
    row = candidate[0]
    assert row["coordinates_changed_vs_live"] is True
    assert row["live_word_start"] == 7
    assert row["word_start"] == 0
    assert summary["after"]["coordinates_changed_vs_live"] == 1


# ---------------------------------------------------------------------------
# Coordinate bounds
# ---------------------------------------------------------------------------
def test_out_of_range_word_coordinates_are_detected(tmp_path):
    """A live span whose word range exceeds the artifact is invalid."""
    words = ["one", "two", "three"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="one two three", word_start=0, word_end=99)
    _code, candidate, _q, _v, summary = _run(tmp_path, [payload])
    assert summary["before"]["invalid_coordinates"] == 1
    assert summary["before"]["valid_coordinates"] == 0


def test_end_before_start_coordinates_are_detected(tmp_path):
    words = ["one", "two", "three"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="one two three", word_start=2, word_end=2)
    _code, _candidate, _q, _v, summary = _run(tmp_path, [payload])
    assert summary["before"]["invalid_coordinates"] == 1
    assert summary["before"]["valid_coordinates"] == 0


# ---------------------------------------------------------------------------
# Audio window bounds
# ---------------------------------------------------------------------------
def test_audio_window_beyond_the_archived_audio_is_quarantined(tmp_path):
    """A cited window past the end of the real audio must be quarantined."""
    words = ["one", "two", "three", "four"]
    _timed_artifact(tmp_path / "attr", "vid-1", words, start_s=1.0, step_s=0.5)
    # The audio is only 2 s long, but the artifact places words at 1.0-2.5 s.
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 2000)
    payload = _span_payload(text="one two three four", word_end=4)
    _code, candidate, quarantine, _v, summary = _run(tmp_path, [payload])
    assert candidate == []
    assert quarantine
    reasons = quarantine[0]["quarantine_reasons"]
    assert "audio_end_beyond_archived_audio" in reasons
    assert summary["after"]["out_of_bounds_audio_window"] == 0


def test_header_only_audio_stub_is_rejected(tmp_path):
    """A WAV that declares a duration but carries no audio must not be trusted."""
    words = ["one", "two", "three", "four"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_stub_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 60000)
    payload = _span_payload(text="one two three four", word_end=4)
    _code, candidate, quarantine, _v, _summary = _run(tmp_path, [payload])
    assert candidate == []
    assert "archived_audio_truncated" in quarantine[0]["quarantine_reasons"]


def test_no_overlap_audio_window_is_detected(tmp_path):
    """A cited window that contains no timed word has no overlap."""
    words = ["one", "two", "three", "four"]
    _timed_artifact(tmp_path / "attr", "vid-1", words, start_s=1.0, step_s=0.5)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    # The payload cites 20-25 s, where the artifact has no words at all.
    payload = _span_payload(text="one two three four", start_ms=20000, end_ms=25000, word_end=4)
    _code, _candidate, _q, _v, summary = _run(tmp_path, [payload])
    assert summary["before"]["audio_window_no_overlap"] == 1
    assert summary["before"]["audio_window_zero_coverage"] == 1


# ---------------------------------------------------------------------------
# Text / hash
# ---------------------------------------------------------------------------
def test_text_hash_mismatch_is_reported(tmp_path):
    """A declared source_text_hash that disagrees with the text is reported."""
    words = ["alpha", "beta", "gamma"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="alpha beta gamma", declared_hash="c" * 64, word_end=3)
    _code, candidate, _q, _v, _summary = _run(tmp_path, [payload])
    assert candidate[0]["live_source_text_hash"] == "c" * 64
    assert candidate[0]["text_hash_matches_live"] is False
    assert candidate[0]["source_text_hash"] == rebuild.clip_text_hash("alpha beta gamma")


def test_multilingual_span_is_validated_not_marked_unverifiable(tmp_path):
    """A Devanagari span must tokenize and rebuild like any other text."""
    words = ["यह", "एक", "परीक्षण", "है"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="यह एक परीक्षण है", word_end=4)
    _code, candidate, quarantine, _v, summary = _run(tmp_path, [payload])
    assert len(candidate) == 1
    assert candidate[0]["reconstruction_exact"] is True
    assert candidate[0]["span_multilingual"] is True
    assert quarantine == []
    assert summary["before"]["multilingual_unverifiable_by_ascii_checker"] == 1
    assert summary["after"]["multilingual_span_exact_reconstruction"] == 1


def test_normalization_version_mismatch_is_detected_as_a_variant(tmp_path):
    """A span whose text only reconstructs under another spelling is a variant."""
    words = ["Serene", "Mind", "practice", "is", "short"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="serene mind practice is short", word_end=5)
    _code, candidate, quarantine, _v, summary = _run(tmp_path, [payload])
    # Case differences are normalized away, so this one is still exact.
    assert candidate[0]["reconstruction_exact"] is True

    # The artifact's region holds one word the span does not: the span
    # reconstructs at 90% coverage but not exactly.
    words2 = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    _timed_artifact(tmp_path / "attr", "vid-1", words2)
    payload2 = _span_payload(
        span_id="span-2",
        text="one two three four five six seven eight nine other",
        word_end=10,
    )
    _code, candidate2, quarantine2, _v, summary2 = _run(tmp_path, [payload2])
    assert candidate2 == []
    assert "reconstruction_variant_not_exact" in quarantine2[0]["quarantine_reasons"]
    assert quarantine2[0]["reconstruction_tier"] == rebuild.TIER_VARIANT
    assert quarantine2[0]["reconstruction_exact"] is False


def test_transcription_variant_is_admitted_under_the_coverage_policy(tmp_path):
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(
        text="one two three four five six seven eight nine other", word_end=10
    )
    _code, candidate, quarantine, variants, summary = _run(
        tmp_path, [payload], policy=rebuild.POLICY_COVERAGE
    )
    assert len(candidate) == 1
    assert candidate[0]["transcription_variant"] is True
    assert candidate[0]["reconstruction_tier"] == rebuild.TIER_VARIANT
    assert quarantine == []


# ---------------------------------------------------------------------------
# Deterministic-id collisions
# ---------------------------------------------------------------------------
def test_two_distinct_source_spans_with_the_same_rebuilt_id_are_both_quarantined(tmp_path):
    """Two live spans that rebuild onto the same coordinates collide.

    Neither may be kept: the deterministic id would then identify two source
    spans, and a reader of the candidate manifest could not tell which span a
    citation refers to. EVERY member is quarantined.
    """
    words = ["alpha", "beta", "gamma"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload_a = _span_payload(span_id="span-a", text="alpha beta gamma", word_end=3)
    payload_b = _span_payload(span_id="span-b", text="alpha beta gamma", word_end=3)
    _code, candidate, quarantine, _v, summary = _run(tmp_path, [payload_a, payload_b])

    assert candidate == []
    assert len(quarantine) == 2
    for row in quarantine:
        assert "deterministic_id_collision" in row["quarantine_reasons"]
        assert row["valid"] is False
        assert row["admitted_to_candidate"] is False
    live_ids = {row["live_source_span_id"] for row in quarantine}
    assert live_ids == {"span-a", "span-b"}
    assert summary["totals"]["deterministic_id_collisions"] == 1
    assert summary["totals"]["deterministic_id_collision_members"] == 2
    assert summary["deterministic_id_collisions"][0]["resolution_status"] == "unresolved"
    assert (
        summary["deterministic_id_collisions"][0]["distinct_live_source_span_ids"]
        == ["span-a", "span-b"]
    )


# ---------------------------------------------------------------------------
# Determinism and read-only posture
# ---------------------------------------------------------------------------
def test_repeated_runs_are_byte_identical(tmp_path):
    words = ["alpha", "beta", "gamma", "delta"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    payload = _span_payload(text="alpha beta gamma delta", word_end=4)
    _code, candidate, _q, _v, summary = _run(tmp_path, [payload])
    first = (tmp_path / "candidate.jsonl").read_bytes()
    summary_first = (tmp_path / "summary.json").read_bytes()
    _code2, _c2, _q2, _v2, _s2 = _run(tmp_path, [payload])
    assert (tmp_path / "candidate.jsonl").read_bytes() == first
    assert (tmp_path / "summary.json").read_bytes() == summary_first


def test_source_manifests_are_not_modified(tmp_path):
    words = ["alpha", "beta"]
    _timed_artifact(tmp_path / "attr", "vid-1", words)
    _write_wav(tmp_path / "attr" / "audio_archive" / "wavs" / "vid-1.wav", 30000)
    export = _export(tmp_path / "v10.json", [_span_payload(text="alpha beta", word_end=2)])
    before = export.read_bytes()
    _code, _c, _q, _v, _s = _run(tmp_path, [_span_payload(text="alpha beta", word_end=2)])
    assert export.read_bytes() == before


def test_write_mode_is_refused(tmp_path):
    code = rebuild.main(["--v10-points", "x", "--out", "y", "--summary", "z", "--apply-to-qdrant"])
    assert code == rebuild.EXIT_INVALID_INPUT


def test_script_source_contains_no_qdrant_mutation():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "/points/upsert",
        "/points/delete",
        "qdrant_client",
        "upsert(",
        "delete_collection",
        "update_collection",
        "method=\"PUT\"",
        "method=\"DELETE\"",
    ):
        assert forbidden not in source, f"the rebuild script must not contain {forbidden!r}"


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "rebuild" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Known baselines against the real artifacts
# ---------------------------------------------------------------------------
def _real_artifacts_available() -> bool:
    return ATTR_ROOT.is_dir() and V10_EXPORT.is_file()


@pytest.mark.skipif(not _real_artifacts_available(), reason="real artifacts not on this host")
def test_known_out_of_range_coordinate_failures_are_reproduced() -> None:
    """41 live spans index past the end of their word-timed transcript."""
    from scripts.ops.audit_first_person_v10_strict import _discover_asr

    asr = _discover_asr(ATTR_ROOT)
    live = json.loads(V10_EXPORT.read_text(encoding="utf-8"))["result"]["points"]
    out_of_range = 0
    for point in live:
        payload = point["payload"]
        evidence = asr.get(payload["video_id"])
        if evidence is None:
            continue
        count = len(evidence["timed_words"])
        if not (
            0 <= payload["word_start"] < payload["word_end"] <= count
        ):
            out_of_range += 1
    assert out_of_range == KNOWN_OUT_OF_RANGE_COORDINATES


@pytest.mark.skipif(not _real_artifacts_available(), reason="real artifacts not on this host")
def test_known_audio_window_failures_are_reproduced() -> None:
    """298 live spans fail the audit's token-coverage check; 2 are unverifiable."""
    from scripts.ops.audit_first_person_v10_strict import (
        _norm_words,
        _token_coverage,
        _window_tokens_covering,
    )

    live = json.loads(V10_EXPORT.read_text(encoding="utf-8"))["result"]["points"]
    from scripts.ops.audit_first_person_v10_strict import _discover_asr

    asr = _discover_asr(ATTR_ROOT)
    mismatch = 0
    unverifiable = 0
    for point in live:
        payload = point["payload"]
        evidence = asr.get(payload["video_id"])
        if evidence is None:
            continue
        clip_tokens = _norm_words(payload["verbatim_text"])
        if not clip_tokens:
            unverifiable += 1
            continue
        cited = _window_tokens_covering(
            evidence["timed_words"], payload["start_ms"], payload["end_ms"], 50
        )
        if _token_coverage(clip_tokens, cited) < 0.90:
            mismatch += 1
    assert mismatch == KNOWN_AUDIO_WINDOW_FAILURES
    assert unverifiable == 2


@pytest.mark.skipif(not _real_artifacts_available(), reason="real artifacts not on this host")
def test_known_beyond_audio_failures_are_reproduced() -> None:
    """18 live spans cite past the ASR-aligned extent of the audio."""
    from scripts.ops.audit_first_person_v10_strict import _discover_asr

    asr = _discover_asr(ATTR_ROOT)
    live = json.loads(V10_EXPORT.read_text(encoding="utf-8"))["result"]["points"]
    beyond = 0
    for point in live:
        payload = point["payload"]
        evidence = asr.get(payload["video_id"])
        if evidence is None:
            continue
        extent = int(
            round(max(float(w.get("end", 0.0)) for w in evidence["timed_words"]) * 1000.0)
        )
        if payload["end_ms"] > extent:
            beyond += 1
    assert beyond == KNOWN_BEYOND_AUDIO
