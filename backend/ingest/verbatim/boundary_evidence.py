"""Derived clip-boundary evidence: one honest record per candidate span.

The builder used to re-infer grammatical completeness at serve time from phrase
regexes over the verbatim text. This module derives the evidence ONCE, at ingest,
from the same tokens and word timings the span was cut from, and freezes it into
the payload. Serving then reads the record instead of guessing.

Pure by construction: stdlib only, no I/O, no models, no clocks. Every field is a
function of the arguments, so two calls with the same inputs are equal (the
determinism test pins that).

Nothing here repairs text. A fragment stays a fragment: the ``status`` is
``complete`` only when the span both terminates on real terminal punctuation and
carries no hard head/tail defect. Missing indexes or timings raise ``ValueError``
rather than being filled in -- an unknown boundary is never reported as complete.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ingest.verbatim.boundaries import (
    TERMINAL,
    _ends_sentence,
    boundary_defects,
    terminal_tokens,
)

# Bump when the derivation rules change: persisted evidence carries this so a
# reader can tell a re-derivable record from a stale one.
BOUNDARY_CONTRACT_VERSION = "boundary-evidence-v1"
COORDINATE_SPACE_WORD_TIMED = "word_timed_v1"

# A hard defect means the text cannot stand alone as a complete thought, so the
# record says ``uncertain`` (never complete, never a claim of completeness).
HARD_DEFECTS = frozenset(
    {
        "empty",
        "tail_no_terminal",
        "head_lowercase",
        "head_orphan_punctuation",
    }
)
# Dangling-word / severed-opener defects describe a fragment: the span is a piece
# of a thought, which is a weaker claim than "we could not tell".
FRAGMENT_DEFECTS = frozenset(
    {
        "tail_dangling_word",
        "head_fragment",
        "head_conjunction",
        "head_headless_predicate",
    }
)
# An unknown defect code is treated as hard: fail closed on anything new.
STATUS_COMPLETE = "complete"
STATUS_FRAGMENT = "fragment"
STATUS_UNCERTAIN = "uncertain"
STATUSES = (STATUS_COMPLETE, STATUS_FRAGMENT, STATUS_UNCERTAIN)


@dataclass(frozen=True, slots=True)
class BoundaryEvidence:
    """Frozen boundary record for the span ``[word_start, word_end)``."""

    contract_version: str
    word_start: int
    word_end: int
    start_ms: int
    end_ms: int
    terminal_evidence: str | None
    speaker_run_ok: bool
    defect_codes: tuple[str, ...]
    status: str
    source_artifact_sha256: str | None
    coordinate_space: str


def _status_for(defect_codes: tuple[str, ...]) -> str:
    if not defect_codes:
        return STATUS_COMPLETE
    if any(code in HARD_DEFECTS for code in defect_codes):
        return STATUS_UNCERTAIN
    if all(code in FRAGMENT_DEFECTS for code in defect_codes):
        return STATUS_FRAGMENT
    # Unknown code: do not call it a mere fragment.
    return STATUS_UNCERTAIN


def derive_boundary_evidence(
    words: Sequence[str],
    timings: Sequence[tuple[float, float]],
    start: int,
    end: int,
    *,
    labels: Sequence[str] | None = None,
    speaker: str | None = None,
    language: str | None = None,
    artifact_sha256: str | None = None,
    coordinate_space: str = COORDINATE_SPACE_WORD_TIMED,
) -> BoundaryEvidence:
    """Derive the boundary record for ``words[start:end]``.

    ``timings[i]`` is ``(start_s, end_s)`` for word ``i``; the recorded window is
    the first word's start to the last word's end, in integer milliseconds. The
    token list is read, never mutated.

    Raises ``ValueError`` on a bad index, a reversed/empty range, a missing
    timing, a collapsed window, or labels without a speaker to compare against.
    """
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError(f"span indexes must be ints, got {type(start)}/{type(end)}")
    if not 0 <= start < end:
        raise ValueError(f"bad span [{start}, {end}): start must be >= 0 and < end")
    if end > len(words):
        raise ValueError(f"bad span [{start}, {end}) for {len(words)} words")
    if len(timings) < end:
        raise ValueError(f"{len(timings)} timings cannot address word_end {end}")

    # Read-only copy: the caller's token list is never touched.
    tokens = list(words[start:end])
    if labels is not None:
        if len(labels) != len(words):
            raise ValueError(f"{len(words)} words vs {len(labels)} labels")
        if speaker is None:
            raise ValueError("speaker is required when labels are supplied")
        speaker_run_ok = all(labels[i] == speaker for i in range(start, end))
    else:
        speaker_run_ok = True

    defect_codes = tuple(boundary_defects(tokens))

    first_timing, last_timing = timings[start], timings[end - 1]
    if first_timing is None or last_timing is None:
        raise ValueError(f"missing timing for span [{start}, {end})")
    first_start_s, last_end_s = first_timing[0], last_timing[1]
    for name, value in (("start", first_start_s), ("end", last_end_s)):
        if value is None:
            raise ValueError(f"missing timing for span {name} at word {start}/{end - 1}")
    start_ms = int(first_start_s * 1000)
    end_ms = int(last_end_s * 1000)
    if end_ms <= start_ms:
        raise ValueError(f"span [{start}, {end}) has no audio window ({start_ms}ms -> {end_ms}ms)")

    last_token = tokens[-1] if tokens else ""
    # Vocabulary: an undeclared language accepts both character sets, exactly like
    # ``boundary_defects`` (whose tail check is ``_ends_sentence`` over TERMINAL);
    # a declared language narrows it, so English text never gains a danda terminal.
    vocabulary = TERMINAL if language is None else terminal_tokens(language)
    stripped = last_token.rstrip("\"'”’)]")
    terminal_evidence = (
        last_token
        if stripped and stripped[-1] in vocabulary and _ends_sentence(last_token)
        else None
    )

    status = _status_for(defect_codes)
    # Belt and braces: "complete" may never coexist with a missing terminal.
    if status == STATUS_COMPLETE and terminal_evidence is None:
        status = STATUS_UNCERTAIN

    return BoundaryEvidence(
        contract_version=BOUNDARY_CONTRACT_VERSION,
        word_start=start,
        word_end=end,
        start_ms=start_ms,
        end_ms=end_ms,
        terminal_evidence=terminal_evidence,
        speaker_run_ok=speaker_run_ok,
        defect_codes=defect_codes,
        status=status,
        source_artifact_sha256=artifact_sha256,
        coordinate_space=coordinate_space,
    )


def validate_persisted(
    evidence: BoundaryEvidence,
    *,
    parent_start_ms: int,
    parent_end_ms: int,
    source_text_sha256: str | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Check a persisted record against its parent window; ``(ok, codes)``.

    Codes are emitted in a fixed order, so the result is deterministic. ``[]``
    means the record is internally consistent and lies inside its parent.

    ``source_text_sha256`` asserts that the record was derived from a known
    artifact: when a caller supplies it and the record carries no artifact hash,
    the provenance is incomplete and ``evidence_hash_missing`` is reported.
    """
    codes: list[str] = []
    if not isinstance(evidence.word_end, int) or evidence.word_end <= evidence.word_start:
        codes.append("word_range_empty")
    if evidence.end_ms <= evidence.start_ms:
        codes.append("end_not_after_start")
    if evidence.start_ms < parent_start_ms:
        codes.append("start_before_parent")
    if evidence.end_ms > parent_end_ms:
        codes.append("end_after_parent")
    if evidence.status == STATUS_COMPLETE and evidence.terminal_evidence is None:
        codes.append("complete_without_terminal")
    if evidence.status == STATUS_COMPLETE and evidence.defect_codes:
        codes.append("status_defect_mismatch")
    if evidence.status not in STATUSES:
        codes.append("unknown_status")
    if evidence.status == STATUS_FRAGMENT and not evidence.defect_codes:
        codes.append("fragment_without_defect")
    if source_text_sha256 is not None and evidence.source_artifact_sha256 is None:
        codes.append("evidence_hash_missing")
    return (not codes), tuple(codes)


def _self_check() -> None:
    words = "Suffering is not a fact. You are awareness.".split()
    timings = [(float(i), float(i) + 0.5) for i in range(len(words))]
    ev = derive_boundary_evidence(words, timings, 0, 5)
    assert ev.status == STATUS_COMPLETE, ev
    assert ev.defect_codes == (), ev
    assert ev.terminal_evidence == "fact.", ev
    assert (ev.start_ms, ev.end_ms) == (0, 4500), ev
    assert ev.contract_version == BOUNDARY_CONTRACT_VERSION

    truncated = derive_boundary_evidence(words, timings, 0, 4)
    assert truncated.status == STATUS_UNCERTAIN, truncated
    assert truncated.terminal_evidence is None, truncated
    assert "tail_no_terminal" in truncated.defect_codes, truncated

    assert derive_boundary_evidence(words, timings, 0, 5) == ev, "not deterministic"

    assert validate_persisted(ev, parent_start_ms=0, parent_end_ms=4500) == (True, ())
    ok, codes = validate_persisted(ev, parent_start_ms=0, parent_end_ms=100)
    assert not ok and "end_after_parent" in codes, codes

    for bad in ((0, 0), (4, 2), (-1, 2), (0, len(words) + 1)):
        try:
            derive_boundary_evidence(words, timings, *bad)
        except ValueError:
            pass
        else:  # pragma: no cover - a silently accepted bad span is the bug
            raise AssertionError(f"bad span {bad} accepted")
    try:
        derive_boundary_evidence(words, timings[:2], 0, 5)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("missing timings accepted")
    print("boundary_evidence.py self-check OK")


if __name__ == "__main__":
    _self_check()
