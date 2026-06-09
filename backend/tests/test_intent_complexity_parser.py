"""Regression tests for OllamaService.classify_intent_and_complexity parsing.

Bug history:
- Initial implementation used `"COMPLEX" in result_upper` to detect complex
  queries. The literal token "COMPLEXITY" in the LLM's response header
  contains the substring "COMPLEX", so every response was classified as
  complex. This forced every query through the standard/deep graph and
  defeated the entire tiered-routing optimization.

These tests pin the corrected parsing logic. Do not regress.
"""

from __future__ import annotations

import pytest


def _parse(result: str) -> dict:
    """Inline copy of the parser block from OllamaService.classify_intent_and_complexity.

    Kept in sync manually — if the production parser changes, update here too.
    """
    result_upper = result.upper().strip()

    intent = "CASUAL"
    for label in (
        "DISTRESS", "SAFETY_VIOLATION", "ADVERSARIAL",
        "FACTUAL", "RELATIONAL", "FOLLOW_UP",
        "MEDITATION", "CASUAL",
    ):
        if label in result_upper:
            intent = label
            break

    complexity = "simple"
    found = False
    for line in result_upper.splitlines():
        if line.startswith("COMPLEXITY"):
            value = line.split(":", 1)[-1] if ":" in line else line.replace("COMPLEXITY", "", 1)
            complexity = "complex" if "COMPLEX" in value else "simple"
            found = True
            break
    if not found:
        stripped = result_upper.replace("COMPLEXITY", "")
        complexity = "complex" if "COMPLEX" in stripped else "simple"

    return {"intent": intent, "complexity": complexity}


@pytest.mark.parametrize(
    "raw,exp_intent,exp_complexity",
    [
        # Well-formed expected outputs
        ("INTENT: FACTUAL\nCOMPLEXITY: simple",              "FACTUAL",          "simple"),
        ("INTENT: RELATIONAL\nCOMPLEXITY: complex",          "RELATIONAL",       "complex"),
        ("INTENT: DISTRESS\nCOMPLEXITY: simple",             "DISTRESS",         "simple"),
        ("INTENT: MEDITATION\nCOMPLEXITY: simple",           "MEDITATION",       "simple"),
        ("INTENT: SAFETY_VIOLATION\nCOMPLEXITY: complex",    "SAFETY_VIOLATION", "complex"),
        ("INTENT: ADVERSARIAL\nCOMPLEXITY: simple",          "ADVERSARIAL",      "simple"),
        ("INTENT: FOLLOW_UP\nCOMPLEXITY: simple",            "FOLLOW_UP",        "simple"),
        # Case insensitivity
        ("intent: distress\ncomplexity: simple",             "DISTRESS",         "simple"),
        # Lazy LLM — minimal output
        ("FACTUAL simple",                                   "FACTUAL",          "simple"),
        ("CASUAL",                                           "CASUAL",           "simple"),
        # Junk fallback
        ("",                                                 "CASUAL",           "simple"),
        ("nope",                                             "CASUAL",           "simple"),
        # Substring trap regression — the "COMPLEXITY" header must NOT
        # force complexity=complex when its value is "simple".
        ("INTENT: FACTUAL\nCOMPLEXITY: simple",              "FACTUAL",          "simple"),
        # Free-form mention of "complex" without a header line — should detect complex.
        ("This is a complex question. FACTUAL.",             "FACTUAL",          "complex"),
        # Leading whitespace and trailing punctuation
        ("  COMPLEXITY: simple\nINTENT: FACTUAL",            "FACTUAL",          "simple"),
        ("INTENT: FACTUAL.\nCOMPLEXITY: simple.",            "FACTUAL",          "simple"),
    ],
)
def test_intent_and_complexity_parsing(raw: str, exp_intent: str, exp_complexity: str) -> None:
    got = _parse(raw)
    assert got["intent"] == exp_intent, f"intent: got {got['intent']}, expected {exp_intent} for {raw!r}"
    assert got["complexity"] == exp_complexity, (
        f"complexity: got {got['complexity']}, expected {exp_complexity} for {raw!r}"
    )


def test_complexity_substring_trap_does_not_recur() -> None:
    """Specific regression: 'COMPLEXITY:' header containing the substring 'COMPLEX'
    must not flip complexity to 'complex' when its value says 'simple'."""
    got = _parse("INTENT: FACTUAL\nCOMPLEXITY: simple")
    assert got["complexity"] == "simple"
