"""Regression tests for the 2026-08-01 answer-path audit.

Each test pins one defect that was silently degrading every answer:

  1. The persona constitution was capped at 512 tokens, discarding 67% of it —
     cutting mid-sentence and dropping the ban on invented quotes, the
     crisis-helpline-first rule, and the entire Voice section.
  2. OKF entries scored `0.9 + cosine*0.1`, so an entry with cosine 0.0 still
     scored 0.9 — above essentially every real Qdrant hit. Three were prepended
     to every non-casual query from a 23-entry bundle.
  3. `format_final_answer` overwrote the measured fast-tier faithfulness score
     with a hardcoded 1.0, making the hallucination target unfalsifiable on the
     ~73% of traffic that routes to the fast graph.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. Persona must reach the model whole
# ---------------------------------------------------------------------------


def test_persona_budget_fits_the_whole_constitution():
    from rag.compressor import cap_to_token_budget
    from rag.nodes.generation import _PERSONA_TOKEN_BUDGET
    from rag.prompts import GURU_SYSTEM_PROMPT

    # Mirror context_engineer: constitution + the appended style block.
    persona = GURU_SYSTEM_PROMPT + (
        "\n\n[USER CLASSIFICATION: SEEKER]\nStyle instruction: " + "word " * 60
    )
    capped = cap_to_token_budget(persona, _PERSONA_TOKEN_BUDGET)

    assert capped == persona, (
        f"persona truncated: {len(persona.split())} words capped to "
        f"{len(capped.split())}. Raise _PERSONA_TOKEN_BUDGET — do not let the "
        "constitution silently lose its tail."
    )


@pytest.mark.parametrize(
    "rule",
    [
        "You do not invent",             # anti-hallucination core (line-wrapped)
        "helpline information appears",  # crisis safety
        "qualified professional",        # clinical redirect
        "Who you are",                   # identity section
        "hype words",                    # Voice section
        "Four Sacred Secrets",           # doctrine vocabulary
    ],
)
def test_every_critical_rule_survives_the_persona_cap(rule):
    """These all sat past the old 393-word cut and never reached the model."""
    from rag.compressor import cap_to_token_budget
    from rag.nodes.generation import _PERSONA_TOKEN_BUDGET
    from rag.prompts import GURU_SYSTEM_PROMPT

    capped = cap_to_token_budget(GURU_SYSTEM_PROMPT, _PERSONA_TOKEN_BUDGET)
    assert rule in capped, f"critical rule lost to the persona cap: {rule!r}"


def test_constitution_preserves_rather_than_flattens_first_person():
    """The Sadhguru effect depends on the gurus' own 'I' surviving retrieval."""
    from rag.prompts import GURU_SYSTEM_PROMPT

    assert "translate every first-person reference" not in GURU_SYSTEM_PROMPT, (
        "the flattening rule is back — it converts the gurus' own words into a "
        "third-person summary, which is what makes answers feel generic"
    )
    assert "keep that first" in GURU_SYSTEM_PROMPT
    # The safety half must remain: preserve, never manufacture.
    assert "manufacture a first-person sentence" in GURU_SYSTEM_PROMPT


def test_generation_voice_rule_forbids_inventing_first_person():
    """All prompt branches must carry the preserve-but-never-invent rule."""
    from rag.prompts.system import GURU_VOICE_RULE

    generation_text = (_BACKEND / "rag" / "nodes" / "generation.py").read_text(encoding="utf-8")
    prompts_text = (_BACKEND / "rag" / "prompts" / "system.py").read_text(encoding="utf-8")

    assert "PRONOUN RULE" not in generation_text, "old flattening rule still present"
    # The shared GURU_VOICE_RULE constant must keep the full rule, including the
    # flattening and context-only clauses.
    assert "GURU_VOICE_RULE" in prompts_text
    assert "VOICE RULE" in prompts_text
    assert "never invent a first-person sentence" in GURU_VOICE_RULE
    assert "that flattening turns a living teaching into a summary" in GURU_VOICE_RULE
    assert "it is not their voice" in GURU_VOICE_RULE
    # Every prompt branch must reference the constant, not re-paste the text:
    # tier2 prompt + standard prompt + CCR re-generation prompt.
    assert generation_text.count("GURU_VOICE_RULE") >= 3, "voice rule missing from a prompt branch"


# ---------------------------------------------------------------------------
# 2. OKF injection must clear a relevance floor
# ---------------------------------------------------------------------------


def test_okf_similarity_floor_is_enforced():
    from rag.nodes.retrieval import _OKF_CURATION_BOOST, _OKF_MIN_SIMILARITY

    assert 0.0 < _OKF_MIN_SIMILARITY < 1.0
    # An irrelevant entry (cosine ~0) must score far below a good Qdrant hit.
    assert 0.0 * _OKF_CURATION_BOOST < 0.5
    # Curation earns a margin, not a floor. The old formula gave 0.9 to
    # everything; a boost >= 1.5x would drift back toward that failure.
    assert 1.0 <= _OKF_CURATION_BOOST < 1.5


def test_okf_scoring_has_no_additive_floor():
    """`0.9 + sim * 0.1` guaranteed every entry outranked real retrieval."""
    text = (_BACKEND / "rag" / "nodes" / "retrieval.py").read_text(encoding="utf-8")

    assert not re.search(r'"score":\s*0\.9\s*\+', text), (
        "additive OKF score floor is back — every curated entry would again "
        "outrank genuinely retrieved teachings"
    )


def test_okf_keyword_fallback_requires_real_coverage():
    from rag.nodes.retrieval import (
        _OKF_KEYWORD_SCORE_CEILING,
        _OKF_MIN_KEYWORD_COVERAGE,
    )

    # A single incidental word match must not select an entry.
    assert _OKF_MIN_KEYWORD_COVERAGE > 0.0
    # Lexical overlap must never outrank a real embedding match.
    assert _OKF_KEYWORD_SCORE_CEILING < 1.0


# ---------------------------------------------------------------------------
# 3. Fast-tier faithfulness must be measured, not asserted
# ---------------------------------------------------------------------------


def test_fast_tier_does_not_hardcode_a_passing_score():
    text = (_BACKEND / "rag" / "nodes" / "generation.py").read_text(encoding="utf-8")
    tail = text.split("def format_final_answer")[-1]

    assert '"method": "fast_tier_bypass"' not in tail, (
        "format_final_answer still stamps fast_tier_bypass — it is discarding "
        "the LettuceDetect score generate_answer computed for this purpose"
    )
    # The measured score must be read back off the state and gated on the floor.
    assert 'state.get("faithfulness_score")' in tail
    assert "faithfulness_floor" in tail


def test_stimulus_prompt_uses_source_aware_founder_voice():
    """The distress path must not undo the primary prompt's provenance rule."""
    from rag.prompts.rag import STIMULUS_RAG_PROMPT

    assert "Translate all first-person references" not in STIMULUS_RAG_PROMPT
    assert "Never refer to them in the first person" not in STIMULUS_RAG_PROMPT
    assert "SOURCE-AWARE FOUNDER VOICE" in STIMULUS_RAG_PROMPT
    assert "exact retrieved quotation" in STIMULUS_RAG_PROMPT
    assert "Never invent first-person founder speech" in STIMULUS_RAG_PROMPT
