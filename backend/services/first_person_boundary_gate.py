"""Serve-side reader for the persisted boundary evidence record.

The builder derives clip-boundary evidence once, at ingest, from the exact word
timings the span was cut from (``ingest.verbatim.boundary_evidence``), and stores
it in the payload. Before this module existed, nothing read those keys: serving
re-inferred completeness from phrase regexes over ``verbatim_text`` and had no
way to tell a verified span from a legacy point that carries no evidence at all.

Three outcomes, and one honest default:

``clean``
    The persisted record is internally consistent and carries no defect that
    blocks serving.
``incomplete``
    The record is consistent but the span does not terminate on real terminal
    punctuation. A trailing comma is ugly but answerable (owner decision
    2026-10-10, ``tail_no_terminal`` was deliberately removed from the hard
    block list), so the clip may still be served — as *related*, never as a
    direct answer.
``block``
    The record either names a serve-blocking defect or contradicts itself
    (claims completeness without a terminal, unknown contract version, unknown
    coordinate space). Excluded.
``legacy``
    No persisted record. The caller keeps its existing text-derived behaviour.
    Legacy is never reported as clean: an unknown boundary is not a verified one.

This module reads and checks; it never repairs, re-punctuates, or mutates clip
text. No I/O, no models, no clocks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ingest.verbatim.boundaries import TERMINAL
from ingest.verbatim.boundary_evidence import BOUNDARY_CONTRACT_VERSION

BOUNDARY_GATE_VERSION = "first_person_boundary_gate_v1"

# Defects that make a clip unservable. Moved here (2026-11-08) so one owner holds
# the serve-time boundary policy; ``services.first_person_pipeline`` re-exports
# the name for its existing call sites.
#
# REMOVED tail_no_terminal (2026-10-10): the v7 corpus had 25% non-terminal
# clips from ASR mid-sentence cuts. Hard-blocking them caused 100% abstention on
# many common queries (Beautiful State, anxiety, two states). Such a clip is now
# offered as *related* — see INCOMPLETE below — never as a direct answer.
SERVE_BLOCKING_BOUNDARY_DEFECTS = frozenset(
    {
        # Head defects: clip starts mid-clause, genuinely broken text
        "head_orphan_punctuation",
        "head_headless_predicate",
        "head_conjunction",
        "head_fragment",
        # Tail: dangling preposition/conjunction/article at the very end
        "tail_dangling_word",
        "tail_severed_relative_clause",
    }
)

CLEAN = "clean"
INCOMPLETE = "incomplete"
BLOCK = "block"
LEGACY = "legacy"

KNOWN_CONTRACT_VERSIONS = frozenset({BOUNDARY_CONTRACT_VERSION})
KNOWN_COORDINATE_SPACES = frozenset({"word_timed_v1"})

# Codes that mean "this record cannot be trusted", as opposed to "this span is a
# fragment". They are gate failures, not style findings.
CONTRADICTION_CODES = frozenset(
    {
        "unknown_contract_version",
        "unknown_coordinate_space",
        "complete_without_terminal",
        "terminal_evidence_mismatch",
        "defect_codes_not_a_list",
    }
)

# Tail defects that make a span incomplete but still answerable.
_INCOMPLETE_CODES = frozenset({"tail_no_terminal"})


def boundary_verdict(clip: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    """``(verdict, reason_codes)`` for one payload.

    The contract version is the switch: its absence means the point predates the
    record and must be handled by the caller's legacy path.
    """
    version = clip.get("boundary_contract_version")
    if not version:
        return LEGACY, ()

    reasons: list[str] = []
    if str(version) not in KNOWN_CONTRACT_VERSIONS:
        # Fail closed on anything we do not know how to read.
        return BLOCK, ("unknown_contract_version",)

    space = str(clip.get("coordinate_space") or "")
    if space not in KNOWN_COORDINATE_SPACES:
        # The v10 "mixed coordinate space" defect: the record's ms window cannot
        # be aligned with the payload's, so its evidence cannot be trusted.
        reasons.append("unknown_coordinate_space")

    raw_codes = clip.get("boundary_defect_codes")
    if raw_codes is None:
        codes: tuple[str, ...] = ()
    elif isinstance(raw_codes, (list, tuple)):
        codes = tuple(str(code) for code in raw_codes)
    else:
        reasons.append("defect_codes_not_a_list")
        codes = ()

    text = str(clip.get("verbatim_text") or "").strip()
    terminal = clip.get("terminal_evidence")

    if not codes and text:
        # A record that claims "no defects" is claiming completeness. Verify the
        # one thing that claim depends on, from the persisted text itself.
        last = text.rstrip("\"'”’)]").rstrip()
        if not last or last[-1] not in TERMINAL:
            reasons.append("complete_without_terminal")
        elif terminal:
            if str(terminal).strip() != text.split()[-1]:
                reasons.append("terminal_evidence_mismatch")

    blocking = tuple(code for code in codes if code in SERVE_BLOCKING_BOUNDARY_DEFECTS)
    reasons.extend(blocking)

    if any(code in CONTRADICTION_CODES for code in reasons):
        return BLOCK, tuple(dict.fromkeys(reasons))
    if blocking:
        return BLOCK, tuple(dict.fromkeys(reasons))
    if any(code in _INCOMPLETE_CODES for code in codes) or (
        terminal is None and text and not codes
    ):
        return INCOMPLETE, tuple(dict.fromkeys(reasons or _INCOMPLETE_CODES))
    return CLEAN, tuple(dict.fromkeys(reasons))


def blocks_serving(clip: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Convenience predicate: ``(blocked, reason_codes)``."""
    verdict, reasons = boundary_verdict(clip)
    return verdict == BLOCK, reasons


if __name__ == "__main__":
    _legacy = {"verbatim_text": "Suffering is not a fact."}
    assert boundary_verdict(_legacy) == (LEGACY, ())

    _clean = {
        "verbatim_text": "Suffering is not a fact.",
        "boundary_contract_version": BOUNDARY_CONTRACT_VERSION,
        "coordinate_space": "word_timed_v1",
        "boundary_defect_codes": [],
        "terminal_evidence": "fact.",
    }
    assert boundary_verdict(_clean) == (CLEAN, ()), boundary_verdict(_clean)

    _cut = {
        "verbatim_text": "Suffering is not a fact, oneness,",
        "boundary_contract_version": BOUNDARY_CONTRACT_VERSION,
        "coordinate_space": "word_timed_v1",
        "boundary_defect_codes": ["tail_no_terminal"],
        "terminal_evidence": None,
    }
    assert boundary_verdict(_cut)[0] == INCOMPLETE

    _headless = dict(_cut, boundary_defect_codes=["head_headless_predicate"])
    assert boundary_verdict(_headless)[0] == BLOCK

    _lies = dict(_clean, verbatim_text="Suffering is not a fact, oneness,")
    assert boundary_verdict(_lies)[0] == BLOCK
    assert "complete_without_terminal" in boundary_verdict(_lies)[1]

    _unknown = dict(_clean, boundary_contract_version="boundary-evidence-v99")
    assert boundary_verdict(_unknown)[0] == BLOCK

    _mixed = dict(_clean, coordinate_space="asr_char_v0")
    assert boundary_verdict(_mixed)[0] == BLOCK
    print("first_person_boundary_gate self-check passed")
