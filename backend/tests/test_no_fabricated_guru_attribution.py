"""F9 guard: no response constant may attribute a teaching to a living Guru.

Six (in fact eight) teaching claims attributed to Sri Preethaji and Sri
Krishnaji BY NAME were hardcoded in Python string constants. A full substring
scan of all 12,904 chunks in the live corpus found ZERO of them anywhere
(controls hit, so the scan was sound). One was live on the demo's most likely
first turn via `_WARM_GREETINGS`, and three more were live via
`MEDITATION_STEPS`, which `rag.meditation.format_meditation_response` emits
verbatim.

These constants bypass every safeguard the product has -- retrieval, the
faithfulness gate, the citation extractor, the output guardrail -- because they
never enter any of them. A fabricated direct quotation is something Sri
Krishnaji recognises as not his on sight.

This test is the permanent fix. Attributed doctrine belongs in `memory/okf/`,
where provenance is mandatory (OKF invariant 2: an entry with an empty `source`
is uncitable and is rejected) -- never in a Python literal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# backend/tests/ -> backend/
_BACKEND = Path(__file__).resolve().parents[1]

# Modules holding strings that reach a seeker verbatim, or exemplar answers a
# prompt steers the model to reproduce.
_SCANNED_DIRS = ("rag/prompts", "app/pipeline/stages", "services")
_SCANNED_FILES = ("rag/meditation.py",)

# "Sri Preethaji teaches ...", "Sri Krishnaji says: ...", "Sri Preethaji calls ..."
_ATTRIBUTION = re.compile(
    r"Sri\s+(?:Preethaji|Krishnaji)[^.]{0,40}?\b(?:says|teaches|calls|shares)\b"
)

# An attributed payload that trails off in an ellipsis asserts nothing -- it is a
# format template telling the model HOW to attribute, and the teaching content
# itself comes from retrieved context (e.g. GURU_VOICE_RULE, the third-person
# style rule, FOLLOW_UP_ENHANCEMENT). A payload that COMPLETES asserts a
# teaching, and that is the defect. This is the only distinction the test draws.
#
# ponytail: a fixed 40-char lookahead window, not a payload parser. A future
# fabrication that happens to contain an ellipsis within 40 chars of the
# attribution verb would slip through. Tighten to real payload-boundary parsing
# only if that ever actually happens.
_PLACEHOLDER_WINDOW = 40


def _scanned_paths() -> list[Path]:
    paths: list[Path] = []
    for rel in _SCANNED_DIRS:
        paths.extend(sorted((_BACKEND / rel).glob("*.py")))
    paths.extend(_BACKEND / rel for rel in _SCANNED_FILES)
    return [p for p in paths if p.is_file()]


def _violations(text: str) -> list[tuple[int, str]]:
    """Return (line_number, matched_text) for each real attributed claim."""
    found = []
    for m in _ATTRIBUTION.finditer(text):
        window = text[m.end() : m.end() + _PLACEHOLDER_WINDOW]
        if "…" in window or "..." in window:
            continue  # format template, asserts nothing
        line_no = text.count("\n", 0, m.start()) + 1
        snippet = text[m.start() : m.start() + 110].split("\n")[0]
        found.append((line_no, snippet))
    return found


def test_scan_actually_covers_the_known_modules():
    """Guard the guard: a typo'd path would make every assertion below vacuous."""
    names = {p.relative_to(_BACKEND).as_posix() for p in _scanned_paths()}
    assert "rag/prompts/system.py" in names
    assert "app/pipeline/stages/glue_stages.py" in names
    assert "rag/meditation.py" in names
    assert len(names) > 5, names


def test_no_response_constant_attributes_a_teaching_to_a_living_guru():
    offences: list[str] = []
    for path in _scanned_paths():
        rel = path.relative_to(_BACKEND).as_posix()
        for line_no, snippet in _violations(path.read_text(encoding="utf-8")):
            offences.append(f"{rel}:{line_no}: {snippet}")

    assert not offences, (
        "Fabricated Guru attribution in a response constant (F9).\n\n"
        + "\n".join(offences)
        + "\n\nThese strings bypass retrieval, the faithfulness gate, the "
        "citation extractor and the output guardrail entirely. Strip the "
        "attributive clause and the quotation marks and keep the pastoral "
        "language -- it is the product's own voice and needs no source. If the "
        "claim IS a real teaching, it belongs in memory/okf/ with a real "
        "`source`, never in a Python literal. Do not invent a source to keep "
        "a string."
    )


@pytest.mark.parametrize(
    "text",
    [
        "Welcome! As Sri Preethaji teaches, every encounter is an opportunity.",
        "Sri Krishnaji says: 'When you stop running from your suffering.'",
        "As Sri Krishnaji teaches: 'Awareness is the greatest agent of change.'",
        "This is what Sri Preethaji calls 'The Beautiful State'",
        "As Sri Krishnaji says: 'You are not your suffering.'",
        "and Sri Preethaji teaches that this suffering is a doorway.",
        "Sri Preethaji shares that stillness begins with awareness.",
    ],
)
def test_detector_catches_the_shapes_that_shipped(text):
    """Mutation check: the detector must fail on the real removed strings.

    Without this, deleting the regex body would leave the suite green -- a
    defect class this repo has produced three times.
    """
    assert _violations(text), f"detector missed a known fabrication: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        'refer to them in the third person ("Sri Krishnaji teaches…")',
        "\"Sri Preethaji says: 'I want you to...'\"",
        '- "Sri Preethaji goes deeper into this when she teaches..."',
    ],
)
def test_detector_allows_ellipsis_format_templates(text):
    """Templates tell the model HOW to attribute; they assert no teaching."""
    assert not _violations(text), f"false positive on a format template: {text!r}"
