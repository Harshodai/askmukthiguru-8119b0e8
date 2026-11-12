"""Derived boundary evidence: derived once at ingest, never inferred at serve.

Every field must be a function of the arguments (deterministic), every unknown
must raise instead of being filled in, and a truncated span must never be
reported ``complete``. These tests pin those three properties.
"""

from __future__ import annotations

import pytest

from ingest.verbatim.boundary_evidence import (
    BOUNDARY_CONTRACT_VERSION,
    COORDINATE_SPACE_WORD_TIMED,
    derive_boundary_evidence,
    validate_persisted,
)

WORDS = (
    "Suffering is not a fact. You are awareness itself. When you see this clearly "
    "the mind becomes still."
).split()


def _timings(n: int, step: float = 0.5) -> list[tuple[float, float]]:
    """Word i spans [i*step, (i+1)*step) seconds."""
    return [(i * step, (i + 1) * step) for i in range(n)]


def _base_evidence():
    return derive_boundary_evidence(WORDS, _timings(len(WORDS)), 0, 5)


def test_offsets_equal_first_and_last_word_timings():
    timings = _timings(len(WORDS), step=0.4)
    ev = derive_boundary_evidence(WORDS, timings, 5, 10)
    assert ev.word_start == 5 and ev.word_end == 10
    assert ev.start_ms == int(timings[5][0] * 1000)
    assert ev.end_ms == int(timings[9][1] * 1000)
    assert ev.end_ms > ev.start_ms


def test_contract_and_coordinate_space_are_pinned():
    ev = _base_evidence()
    assert ev.contract_version == BOUNDARY_CONTRACT_VERSION
    assert ev.coordinate_space == COORDINATE_SPACE_WORD_TIMED
    assert ev.status == "complete"
    assert ev.defect_codes == ()
    assert ev.terminal_evidence == "fact."


def test_trimming_moves_the_window_with_the_span():
    timings = _timings(len(WORDS))
    full = derive_boundary_evidence(WORDS, timings, 0, 10)
    # Trimming the unterminated tail keeps the span honest: the window follows
    # the surviving words and the terminal evidence comes from word 9.
    trimmed = derive_boundary_evidence(WORDS, timings, 0, 5)
    assert trimmed.word_end == 5
    assert trimmed.end_ms == int(timings[4][1] * 1000)
    assert trimmed.end_ms < full.end_ms
    assert trimmed.terminal_evidence == "fact."
    assert trimmed.status == "complete"
    # Trimming the head onto a lowercase word is a severed head, not a repair.
    head_trimmed = derive_boundary_evidence(WORDS, timings, 1, 5)
    assert "head_lowercase" in head_trimmed.defect_codes
    assert head_trimmed.status == "uncertain"


def test_artifact_hash_is_carried_and_optional():
    ev = derive_boundary_evidence(WORDS, _timings(len(WORDS)), 0, 5, artifact_sha256="a" * 64)
    assert ev.source_artifact_sha256 == "a" * 64
    assert _base_evidence().source_artifact_sha256 is None


def test_speaker_run_violation_is_recorded():
    labels = ["krishnaji"] * 5 + ["preethaji"] * (len(WORDS) - 5)
    inside = derive_boundary_evidence(
        WORDS, _timings(len(WORDS)), 0, 5, labels=labels, speaker="krishnaji"
    )
    assert inside.speaker_run_ok is True
    crossed = derive_boundary_evidence(
        WORDS, _timings(len(WORDS)), 0, 6, labels=labels, speaker="krishnaji"
    )
    assert crossed.speaker_run_ok is False
    # No labels supplied: nothing to contradict, so the run is not flagged.
    assert _base_evidence().speaker_run_ok is True


def test_labels_without_speaker_is_a_value_error():
    with pytest.raises(ValueError):
        derive_boundary_evidence(
            WORDS, _timings(len(WORDS)), 0, 5, labels=["krishnaji"] * len(WORDS)
        )


def test_parent_bounds_violation_is_reported():
    ev = _base_evidence()
    ok, codes = validate_persisted(ev, parent_start_ms=ev.start_ms, parent_end_ms=ev.end_ms)
    assert (ok, codes) == (True, ())
    ok, codes = validate_persisted(ev, parent_start_ms=ev.start_ms + 1, parent_end_ms=ev.end_ms)
    assert not ok and "start_before_parent" in codes
    ok, codes = validate_persisted(ev, parent_start_ms=ev.start_ms, parent_end_ms=ev.end_ms - 1)
    assert not ok and "end_after_parent" in codes
    ok, codes = validate_persisted(
        ev, parent_start_ms=ev.start_ms, parent_end_ms=ev.end_ms, source_text_sha256="b" * 64
    )
    assert not ok and "evidence_hash_missing" in codes


def test_deterministic_across_calls():
    first = derive_boundary_evidence(WORDS, _timings(len(WORDS)), 0, 5)
    second = derive_boundary_evidence(WORDS, _timings(len(WORDS)), 0, 5)
    assert first == second
    assert hash(first) == hash(second)
    ev = _base_evidence()
    assert validate_persisted(ev, parent_start_ms=0, parent_end_ms=10_000) == validate_persisted(
        ev, parent_start_ms=0, parent_end_ms=10_000
    )


@pytest.mark.parametrize(
    "start,end",
    [(0, 0), (5, 2), (-1, 3), (0, len(WORDS) + 1), (len(WORDS), len(WORDS))],
)
def test_bad_index_or_reversed_range_raises(start, end):
    with pytest.raises(ValueError):
        derive_boundary_evidence(WORDS, _timings(len(WORDS)), start, end)


def test_missing_timing_raises():
    short = _timings(3)
    with pytest.raises(ValueError):
        derive_boundary_evidence(WORDS, short, 0, 5)
    holed = _timings(5)
    holed[4] = None  # type: ignore[assignment]
    with pytest.raises(ValueError):
        derive_boundary_evidence(WORDS, holed, 0, 5)


def test_collapsed_window_raises():
    timings: list[tuple[float, float]] = [(1.0, 1.0)] * 5
    with pytest.raises(ValueError):
        derive_boundary_evidence(WORDS, timings, 0, 5)


def test_truncated_span_is_never_complete():
    for start, end in [(0, 1), (0, 4), (5, 8), (9, 12)]:
        ev = derive_boundary_evidence(WORDS, _timings(len(WORDS)), start, end)
        assert ev.status != "complete", (start, end, ev)
        assert ev.status == "uncertain", (start, end, ev)
        assert "tail_no_terminal" in ev.defect_codes


def test_words_are_never_mutated():
    words = list(WORDS)
    snapshot = list(words)
    derive_boundary_evidence(
        words, _timings(len(words)), 0, 5, labels=["k"] * len(words), speaker="k"
    )
    assert words == snapshot


def test_empty_result_is_never_complete():
    # start == end cannot even be derived: an empty span has no boundary claim.
    with pytest.raises(ValueError):
        derive_boundary_evidence(WORDS, _timings(len(WORDS)), 4, 4)
