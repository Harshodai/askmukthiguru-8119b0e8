"""Regression tests for prompt-time grounded guru voice behavior."""

import pytest

from services.guru_voice_langhanam import (
    LANGHANAM_ELIGIBLE_INTENTS,
    LANGHANAM_VOICE_BLOCK,
    REFERENCE_VOICE,
    contains_sanskrit_terms,
    count_fillers,
    detect_combined_teachings,
    has_direct_address,
    is_voice_eligible,
    mean_sentence_length,
    render_langhanam_system_prompt,
    split_sentences,
    strip_fillers,
)

# --- Reference voice -------------------------------------------------------


def test_reference_voice_has_five_to_seven_paragraphs():
    paragraphs = [p.strip() for p in REFERENCE_VOICE.split("\n\n") if p.strip()]
    assert 5 <= len(paragraphs) <= 7


def test_reference_voice_keeps_sanskrit_terms():
    assert "langhanam" in REFERENCE_VOICE.lower()
    assert "vaak shakti" in REFERENCE_VOICE.lower()


def test_reference_voice_has_no_transcription_errors():
    assert "shittim" not in REFERENCE_VOICE.lower()
    assert "love venoms" not in REFERENCE_VOICE.lower()


def test_reference_voice_has_no_fillers():
    assert count_fillers(REFERENCE_VOICE) == 0


# --- No-filler detection ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Like, you know, basically this is how it works.",
        "Totally, I think you should try this.",
        "kind of like a practice, you know what i mean?",
    ],
)
def test_count_fillers_detects_american_fillers(text):
    assert count_fillers(text) >= 1


def test_count_fillers_clean_text():
    assert count_fillers("Listen. Practice langhanam. Observe your breath.") == 0


def test_strip_fillers_removes_them():
    cleaned = strip_fillers("Basically, you know, practice langhanam like this.")
    assert count_fillers(cleaned) == 0
    assert "practice langhanam" in cleaned


def test_strip_fillers_does_not_remove_legit_words():
    # "kind of" after a determiner is legit Indian-English ("any kind of fasting"),
    # and "thinkers" must never be hit by the "i think" pattern.
    cleaned = strip_fillers("Deep thinkers practice any kind of fasting.")
    assert "thinkers" in cleaned
    assert "any kind of fasting" in cleaned
    assert count_fillers(cleaned) == 0


# --- Direct address --------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I want you to practice langhanam.",
        "Listen to the end before you come to any conclusion.",
        "Try this: sit still and observe your breath.",
        "Notice how your thoughts settle.",
    ],
)
def test_direct_address_detected(text):
    assert has_direct_address(text)


def test_direct_address_absent_in_passive_text():
    assert not has_direct_address("Langhanam is a principle used by ancients.")


# --- Single-teaching guard -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "In another teaching, the gurus also explain Deeksha.",
        "Similarly, the book teaches about the Beautiful State.",
        "Other teachings say the same about intention.",
    ],
)
def test_combined_teachings_detected(text):
    assert detect_combined_teachings(text)


def test_single_teaching_text_passes_guard():
    assert (
        detect_combined_teachings("The first langhanam is fasting from food. Practice it daily.")
        == []
    )


# --- Sanskrit terms --------------------------------------------------------


def test_sanskrit_terms_detected():
    assert contains_sanskrit_terms("vaak Shakti grows when you speak truth.")
    assert contains_sanskrit_terms("Prana moves with slow breath.")


def test_no_sanskrit_terms():
    assert not contains_sanskrit_terms("Just eat well and rest.")


# --- Sentence helpers ------------------------------------------------------


def test_split_sentences_and_mean_length():
    text = "First sentence. Second, longer sentence here!"
    sentences = split_sentences(text)
    assert len(sentences) == 2
    assert mean_sentence_length(text) == pytest.approx(
        (len(sentences[0].split()) + len(sentences[1].split())) / 2
    )


def test_mean_sentence_length_empty():
    assert mean_sentence_length("") == 0.0


# --- Variant A: system-prompt rendering ------------------------------------


def test_render_langhanam_system_prompt_appends_voice_block():
    base = "You are Mukthi Guru."
    rendered = render_langhanam_system_prompt(base)
    assert rendered.startswith(base)
    # Asserted against the block's actual content. The previous probes
    # ("use this voice", "Do not combine or genericize teachings") matched no
    # version of the block and had been failing since the flag was flipped on.
    assert "THE GURU'S VOICE" in rendered
    assert "SPEAK TO THE SEEKER" in rendered


def test_voice_block_is_evidence_based_not_sanskrit_ornamentation():
    """The block must not re-acquire the mandates measurement disproved.

    Across 2,700 sentences of real guru speech the old block's requirements
    appeared: Sanskrit quota 2x, "our ancients"/"the rishis" 0x, its mandated
    opener 5x. Re-adding any of them pushes output away from their register and
    forces claims absent from the retrieved context.
    """
    block = LANGHANAM_VOICE_BLOCK.lower()
    assert "at least two of" not in block, "Sanskrit term quota must not return"
    assert "maximum 20 words" not in block, "flat sentence cap must not return"
    assert "this is not optional" not in block, "invented-tradition mandate must not return"
    # Positive: the markers that ARE their measured voice.
    for marker in ("second person", "first person", "beautiful state", "rhetorical question"):
        assert marker in block, f"voice block lost its evidence-based marker: {marker!r}"


def test_render_langhanam_system_prompt_empty_base():
    assert render_langhanam_system_prompt("") == LANGHANAM_VOICE_BLOCK


def test_langhanam_voice_flag_default():
    """The source-aware prompt voice ships enabled by default."""
    from app.config import Settings

    settings = Settings(llm_provider="ollama")
    assert settings.langhanam_voice_enabled is True


def test_guru_voice_mode_defaults_to_prompt():
    from app.config import Settings

    settings = Settings(llm_provider="ollama")
    assert settings.guru_voice_mode == "prompt"


def test_guru_voice_gate_score_default():
    from app.config import Settings

    settings = Settings(llm_provider="ollama")
    assert settings.guru_voice_gate_score == pytest.approx(4.0)


# --- N2 regression: append-only contract, never a replacement -------------
#
# docs/agent/NON_NEGOTIABLES.md N2: "The AI never speaks as, or claims the
# authority, blessing, initiation or voice of the gurus." This is enforced by
# two independent, always-on layers, neither of which is the benchmark-score
# `guru_voice_gate_score` mentioned in config.py's comment (that gate scores
# voice-authenticity/brand-fidelity — direct address, Sanskrit terms,
# Indian-English phrasing, fillers, rhythm — and has no impersonation check in
# its rubric; it is not a safety gate and is not wired into any runtime check
# or CI job). The real N2 enforcement is structural:
#   1. GURU_SYSTEM_PROMPT (rag/prompts/system.py) unconditionally states
#      "never as the founders themselves" / "never in impersonation".
#   2. Both `_maybe_apply_langhanam_voice` code paths (the live
#      `voice_register.apply_register` path and the `render_langhanam_system_prompt`
#      fallback) APPEND to the existing system prompt; neither ever replaces it,
#      so the base clause survives regardless of `langhanam_voice_enabled`.
# This test locks that structural behavior so a future refactor that swaps
# append for replace (or drops the base clause) fails loudly here rather than
# silently reopening an N2 gap.


def _normalize_ws(text: str) -> str:
    """Collapse newlines/whitespace so a phrase that wraps across a line in
    the source string can still be matched as one substring."""
    return " ".join(text.split())


def test_langhanam_voice_never_strips_base_anti_impersonation_clause():
    from rag.nodes.generation import _maybe_apply_langhanam_voice
    from rag.prompts.system import GURU_SYSTEM_PROMPT

    base_normalized = _normalize_ws(GURU_SYSTEM_PROMPT)
    assert "never as the founders themselves" in base_normalized
    assert "never in impersonation" in base_normalized

    state = {
        "intent": "TEACHING",
        "question": "What is the Beautiful State?",
        "relevant_docs": [],
    }
    combined_prompt, _ = _maybe_apply_langhanam_voice(state, GURU_SYSTEM_PROMPT, "")
    combined_normalized = _normalize_ws(combined_prompt).lower()

    # Append-only contract: the base anti-impersonation clause must survive
    # verbatim even though the voice register/block was appended on top.
    assert "never as the founders themselves" in combined_normalized
    assert "never in impersonation" in combined_normalized
    # And the appended layer must itself forbid fabricated first-person guru
    # speech (both the live register.py block and the legacy static block
    # carry this rule).
    assert "never invent a first-person sentence" in combined_normalized


def test_voice_eligibility():
    assert is_voice_eligible("DISTRESS")
    assert is_voice_eligible("QUERY")
    assert is_voice_eligible("RELATIONAL")
    assert is_voice_eligible("COMPARATIVE")
    assert is_voice_eligible("teaching")
    assert is_voice_eligible("DOCTRINE")
    # FACTUAL is now eligible (2026-08-01). It was excluded as "pure lookup",
    # but on_device_intent seeds FACTUAL with what/who/why/how/explain/teach me
    # — the shape of nearly every seeker question — so excluding it meant the
    # voice fired on 1 of 8 realistic queries and output stayed generic.
    assert is_voice_eligible("FACTUAL")
    assert not is_voice_eligible("CASUAL")
    assert not is_voice_eligible("CASUAL")
    assert not is_voice_eligible("")
    assert "FACTUAL" in LANGHANAM_ELIGIBLE_INTENTS
    assert "CASUAL" not in LANGHANAM_ELIGIBLE_INTENTS
