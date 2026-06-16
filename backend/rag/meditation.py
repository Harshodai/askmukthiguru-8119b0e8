"""
Mukthi Guru — Serene Mind Meditation Module

Design Patterns:
  - State Machine: 4-step linear progression with user confirmation between steps
  - Template Method: Each step follows the same structure (title, prompt, wait)
  - Memento Pattern: Meditation state preserved across chat messages
  - Null Object Pattern: format_meditation_response returns a context-aware fallback
    rather than a misleading "complete" sentinel for out-of-range steps.

This is the meditation flow triggered by DISTRESS intent detection.
"""

import logging
from typing import Optional

from app.config import settings
from rag.prompts import MEDITATION_STEPS

logger = logging.getLogger(__name__)

MEDITATION_SCRIPTS = {
    "serene_mind": {
        "title": "Serene Mind Meditation",
        "steps": [
            "Settle into a comfortable seat and let your body know it is safe.",
            "Bring attention to conscious breathing: breathe in gently and breathe out slowly.",
            "Notice racing thoughts, overthinking, stress, anger, frustration, grief, or anxiety without fighting them.",
            "Let the breath guide you toward a serene state of calm and inner connection.",
            "When you are ready, gently open your eyes and carry this calm into your next action.",
        ],
    },
    "soul_sync": {
        "title": "Soul Sync Meditation",
        "steps": [
            "Breathe deeply with breath awareness.",
            "Practice bee humming and feel the vibration settle the nervous system.",
            "Rest in the pause between breaths.",
            "Chant A-hummm, also written as Aham, with gentle attention.",
            "Visualize golden light expanding through you into oneness.",
            "Set a heartfelt intention from this expanded state.",
            "Practice as a nine minute, 12 minute, 15 minute, or 20 minute daily morning ritual.",
        ],
    },
}


def get_meditation_script(script_name: str) -> dict:
    return MEDITATION_SCRIPTS.get(script_name, {"title": "Meditation", "steps": []})


# Sentinel string previously returned when the step was out of range. Kept as a constant
# so callers (and tests) can detect it; production code MUST NOT emit this string.
_LEGACY_COMPLETE_SENTINEL = "The meditation is complete. Thank you for practicing with me. \U0001f64f"


def _get_max_step() -> int:
    """Resolve the meditation step count from settings, falling back to the script length.

    Reading from settings keeps the value env-overridable per the no-hardcoding doctrine.
    """
    configured = getattr(settings, "meditation_max_step", None)
    if isinstance(configured, int) and configured > 0:
        return configured
    return len(MEDITATION_STEPS)


# Backwards-compatible module-level constant. Callers should prefer _get_max_step() so the
# value tracks settings overrides, but legacy imports still resolve to a sane number.
MAX_STEP = _get_max_step()


def get_distress_response() -> str:
    """
    Get the initial distress acknowledgment message.

    Helpline contacts are sourced from `services.crisis_helplines` (which in
    turn reads from `backend/config/router_routes.yaml`). No helpline number
    or text appears in this function body — editing helplines is a YAML edit
    only. See `services/crisis_helplines.py` for the single source of truth.
    """
    # Imported lazily so the meditation module remains importable in unit
    # tests that stub out the services package.
    from services.crisis_helplines import format_helplines_block

    helpline_block = format_helplines_block(style="compact_two_line")
    return (
        "I hear you, and I want you to know that your feelings are valid. \U0001f64f\n\n"
        "In moments like these, the teachings remind us that suffering "
        "is a doorway to transformation. It may not feel like it now, "
        "but pain can be a catalyst for deeper awareness.\n\n"
        "Would you like me to guide you through a **Serene Mind meditation** "
        "to help you find some inner peace right now?\n\n"
        f"{helpline_block}"
    )


def get_meditation_step(step: int) -> Optional[dict]:
    """
    Get a specific meditation step.

    Args:
        step: Step number (1..MAX_STEP).

    Returns:
        Dict with 'step', 'title', 'prompt' or None if step is invalid.
    """
    max_step = _get_max_step()
    if 1 <= step <= max_step:
        return MEDITATION_STEPS[step - 1]
    return None


def format_meditation_response(step: int) -> Optional[str]:
    """Format a meditation step for the chat response.

    Returns:
        A formatted step prompt (str) when `step` is in 1..MAX_STEP.
        `None` when `step` is out of range. Callers MUST detect None and
        either (a) signal a re-route to FACTUAL intent or (b) emit a
        context-aware close — they must NOT emit the legacy
        "The meditation is complete..." sentinel for fresh / invalid steps.

    Why `None` (Null Object) instead of the legacy sentinel:
      The pre-fix code returned the literal string for any out-of-range step,
      which leaked into adversarial, interrogative, and multilingual queries
      that were mis-classified as MEDITATION intent. The sentinel is now an
      explicit signal of misuse rather than a misleading user-facing answer.
    """
    step_data = get_meditation_step(step)
    if not step_data:
        logger.debug(
            "format_meditation_response called with out-of-range step=%s "
            "(valid range: 1..%s). Returning None for caller to handle.",
            step,
            _get_max_step(),
        )
        return None

    return f"**Step {step_data['step']}/{_get_max_step()}: {step_data['title']}**\n\n" + step_data["prompt"]


def get_meditation_complete_message() -> str:
    """Return the user-facing close when an active meditation has ACTUALLY finished.

    This is the ONLY function that should emit the "meditation is complete" wording,
    and it must only be called when `step > MAX_STEP` for a session that began at step 1.
    Centralizing the string makes it easy to audit and lets us evolve the copy without
    hunting through call sites.
    """
    return _LEGACY_COMPLETE_SENTINEL


def is_meditation_complete(step: int) -> bool:
    """Check if all meditation steps have been completed."""
    return step > _get_max_step()


def should_start_meditation(message: str) -> bool:
    """
    Check if the user's message indicates they want to start meditation.

    Used after the distress acknowledgment to detect acceptance.
    Checks for negation first to avoid false positives like "no, please don't".
    """
    negative_signals = [
        "no",
        "don't",
        "dont",
        "not now",
        "nah",
        "nope",
        "stop",
        "cancel",
        "never",
        "skip",
        "later",
    ]
    positive_signals = [
        "yes",
        "sure",
        "ok",
        "okay",
        "please",
        "let's",
        "lets",
        "guide me",
        "meditat",
        "help me",
        "start",
        "i'd like",
        "begin",
        "ready",
    ]
    message_lower = message.lower().strip()

    # Check negation first — "no, please don't" should NOT trigger meditation
    if any(neg in message_lower for neg in negative_signals):
        return False

    return any(signal in message_lower for signal in positive_signals)


# ---------------------------------------------------------------------------
# Imperative detection (Phase A1.1 fix — Soul-Sync-on-Mars hijack)
# ---------------------------------------------------------------------------
# A query should only trigger MEDITATION intent (or continue past handle_meditation's
# step==1 guards) when it is BOTH (a) explicitly imperative ("start", "guide me",
# "let's", "begin", "do", "open") AND (b) names a meditation noun. Interrogatives
# like "Can I practice Soul Sync on Mars?" must be treated as FACTUAL.

_MEDITATION_NOUNS = (
    "meditation",
    "meditate",
    "serene mind",
    "soul sync",
    "breathwork",
    "breathing exercise",
    "guided practice",
)

# Verbs that signal the user wants to start practicing RIGHT NOW.
# These must be unambiguous imperatives — "I want to learn about meditation" should
# NOT match, only "start meditation" / "guide me through meditation" should. We
# intentionally exclude soft preferences like "I want to" / "I'd like to" because
# they pair as easily with educational verbs ("learn", "understand") as with
# imperative ones ("start", "begin"). When the user actually wants to begin, they
# will say so with one of the verbs below.
_IMPERATIVE_VERBS = (
    "start",
    "begin",
    "open",
    "guide me",
    "let's",
    "lets",
    "do ",            # trailing space so "doing", "does" don't match
    "take me through",
    "walk me through",
    "lead me",
    "ready to begin",
    "ready to start",
)

# Cheap structural detectors for interrogatives. Order-sensitive: we check question
# mark first, then English question stems, then Hinglish/Romanized Hindi stems
# ("kya", "kaise", "kab", "kahan", "kyu", "kyon").
_INTERROGATIVE_STEMS_EN = (
    "can i", "could i", "should i", "may i",
    "what is", "what are", "what does", "what's",
    "how do", "how does", "how can", "how to",
    "why is", "why does", "why do", "why are",
    "when is", "when does", "where is", "where does",
    "is there", "are there", "does ", "do you ",
    "which ", "who is", "who are",
)
_INTERROGATIVE_STEMS_HINGLISH = (
    "kya ", "kaise ", "kab ", "kahan ", "kyu", "kyon", "kese",
)


def is_meditation_imperative(message: str) -> bool:
    """Return True only if `message` is an imperative request to begin meditation now.

    Examples:
        "Start the meditation"                        -> True
        "Guide me through Serene Mind"                -> True
        "Let's meditate"                              -> True
        "Can I practice Soul Sync on Mars?"           -> False (interrogative)
        "What is Soul Sync?"                          -> False (interrogative)
        "I want to learn about meditation"            -> False (learn != start)
        "Mera mind dysfunctional hai, kaise badlu?"   -> False (Hinglish interrogative)
    """
    if not message:
        return False
    text = message.lower().strip()

    # Quick reject: anything ending with '?' is an interrogative even if it contains
    # imperative-looking words.
    if text.endswith("?"):
        # Allow one narrow exception: "start serene mind?" pattern (rare but valid)
        if not any(text.startswith(v.strip()) for v in _IMPERATIVE_VERBS if v.strip()):
            return False

    # Interrogative stems anywhere in the FIRST 40 chars rule out imperatives.
    head = text[:40]
    for stem in _INTERROGATIVE_STEMS_EN + _INTERROGATIVE_STEMS_HINGLISH:
        if stem in head:
            return False

    # Must mention a meditation noun.
    if not any(noun in text for noun in _MEDITATION_NOUNS):
        return False

    # Must have an imperative verb signal.
    return any(verb in text for verb in _IMPERATIVE_VERBS)
