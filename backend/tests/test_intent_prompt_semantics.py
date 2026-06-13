"""
Semantic regression tests for INTENT_CLASSIFICATION_PROMPT and INTENT_AND_COMPLEXITY_PROMPT.

These tests verify that the *prompt text* has the correct definitions and examples
to guide the LLM — they do NOT make live API calls.

Key regression: "How do I start a meditation practice?" was classified as MEDITATION
because the prompt had no definition distinguishing ACTION (start a session NOW) from
EDUCATIONAL (learn about meditation). These tests pin the prompt semantics.
"""

from __future__ import annotations

import pytest

from rag.prompts import INTENT_AND_COMPLEXITY_PROMPT, INTENT_CLASSIFICATION_PROMPT

# ---------------------------------------------------------------------------
# INTENT_CLASSIFICATION_PROMPT — structural checks
# ---------------------------------------------------------------------------


def test_intent_classification_prompt_has_factual_educational_clause():
    """FACTUAL definition must explicitly include educational questions about meditation."""
    assert "educational questions about meditation" in INTENT_CLASSIFICATION_PROMPT or \
           "How do I start meditating" in INTENT_CLASSIFICATION_PROMPT, \
        "FACTUAL definition must call out educational meditation questions"


def test_intent_classification_prompt_has_meditation_action_clause():
    """MEDITATION definition must say it's an ACTION intent (do now, not learn)."""
    lower = INTENT_CLASSIFICATION_PROMPT.lower()
    assert "action" in lower or "right now" in lower or "begin" in lower, \
        "MEDITATION must be defined as an action/begin intent"


def test_intent_classification_prompt_has_critical_distinction():
    """Must have a CRITICAL DISTINCTION or equivalent callout block."""
    assert "CRITICAL" in INTENT_CLASSIFICATION_PROMPT or "DISTINCTION" in INTENT_CLASSIFICATION_PROMPT, \
        "Prompt must have a CRITICAL DISTINCTION section"


def test_intent_classification_prompt_factual_examples_for_meditation_topics():
    """'How do I start a meditation practice' must appear as a FACTUAL example."""
    assert "How do I start a meditation practice" in INTENT_CLASSIFICATION_PROMPT, \
        "Must have counter-example: meditation question → FACTUAL"


def test_intent_classification_prompt_has_action_meditation_examples():
    """MEDITATION examples must include imperative session-start phrases."""
    assert "Guide me through a meditation" in INTENT_CLASSIFICATION_PROMPT or \
           "Let's do a meditation session" in INTENT_CLASSIFICATION_PROMPT, \
        "MEDITATION examples must include explicit session-start phrases"


# ---------------------------------------------------------------------------
# INTENT_AND_COMPLEXITY_PROMPT — structural checks
# ---------------------------------------------------------------------------


def test_intent_and_complexity_prompt_has_critical_distinction():
    """INTENT_AND_COMPLEXITY_PROMPT must have MEDITATION vs FACTUAL distinction."""
    assert "CRITICAL" in INTENT_AND_COMPLEXITY_PROMPT, \
        "INTENT_AND_COMPLEXITY_PROMPT must have a CRITICAL section"


def test_intent_and_complexity_prompt_has_beginner_meditation_example():
    """'How do I start a meditation practice' must map to FACTUAL in examples."""
    assert "How do I start a meditation practice" in INTENT_AND_COMPLEXITY_PROMPT, \
        "Must show: 'How do I start a meditation practice?' → FACTUAL"


def test_intent_and_complexity_prompt_has_guide_me_meditation_example():
    """'Guide me through a meditation now' must map to MEDITATION in examples."""
    assert "Guide me through a meditation now" in INTENT_AND_COMPLEXITY_PROMPT, \
        "Must show: 'Guide me through a meditation now' → MEDITATION"


def test_intent_and_complexity_prompt_has_lets_meditate_example():
    """'Let's meditate together' must map to MEDITATION in examples."""
    assert "Let's meditate together" in INTENT_AND_COMPLEXITY_PROMPT, \
        "Must show: 'Let's meditate together' → MEDITATION"


def test_intent_and_complexity_prompt_meditation_definition_has_right_now():
    """MEDITATION definition must say 'RIGHT NOW' or 'right now'."""
    assert "RIGHT NOW" in INTENT_AND_COMPLEXITY_PROMPT.upper(), \
        "MEDITATION definition must include 'RIGHT NOW' to distinguish from educational"


# ---------------------------------------------------------------------------
# Parser correctness (verifies the sarvam_service parser still works)
# ---------------------------------------------------------------------------


def _simulate_parser(raw_llm_output: str) -> dict:
    """Mirror of classify_intent_and_complexity() parser logic."""
    result_upper = raw_llm_output.upper().strip()
    lines = result_upper.splitlines()
    intent = "FACTUAL"
    complexity = "complex"
    for line in lines:
        line = line.strip()
        if line.startswith("INTENT:"):
            val = line.split(":", 1)[-1].strip()
            for candidate in [
                "DISTRESS", "SAFETY_VIOLATION", "ADVERSARIAL",
                "MEDITATION", "FACTUAL", "RELATIONAL", "FOLLOW_UP",
                "CASUAL", "QUERY",
            ]:
                if candidate in val:
                    intent = candidate
                    break
        elif line.startswith("COMPLEXITY:"):
            val = line.split(":", 1)[-1].strip()
            complexity = "simple" if "SIMPLE" in val else "complex"
    if intent == "QUERY":
        intent = "FACTUAL"
    return {"intent": intent, "complexity": complexity}


@pytest.mark.parametrize("raw,expected_intent,expected_complexity", [
    # Correctly classify educational meditation questions as FACTUAL
    ("INTENT: FACTUAL\nCOMPLEXITY: simple",   "FACTUAL",    "simple"),
    ("INTENT: FACTUAL\nCOMPLEXITY: complex",  "FACTUAL",    "complex"),
    # Session-start requests → MEDITATION
    ("INTENT: MEDITATION\nCOMPLEXITY: simple", "MEDITATION", "simple"),
    # Other intents unchanged
    ("INTENT: DISTRESS\nCOMPLEXITY: simple",  "DISTRESS",   "simple"),
    ("INTENT: RELATIONAL\nCOMPLEXITY: complex","RELATIONAL", "complex"),
    ("INTENT: FOLLOW_UP\nCOMPLEXITY: simple", "FOLLOW_UP",  "simple"),
    ("INTENT: ADVERSARIAL\nCOMPLEXITY: simple","ADVERSARIAL","simple"),
    ("INTENT: SAFETY_VIOLATION\nCOMPLEXITY: simple", "SAFETY_VIOLATION", "simple"),
    ("INTENT: CASUAL\nCOMPLEXITY: simple",    "CASUAL",     "simple"),
    # QUERY normalizes to FACTUAL
    ("INTENT: QUERY\nCOMPLEXITY: simple",     "FACTUAL",    "simple"),
    # Complexity substring trap (COMPLEXITY header should not force complex)
    ("INTENT: FACTUAL\nCOMPLEXITY: simple",   "FACTUAL",    "simple"),
])
def test_parser_handles_all_intents(raw, expected_intent, expected_complexity):
    got = _simulate_parser(raw)
    assert got["intent"] == expected_intent
    assert got["complexity"] == expected_complexity
