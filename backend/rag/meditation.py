"""
Mukthi Guru — Serene Mind Meditation Module

Design Patterns:
  - State Machine: 4-step linear progression with user confirmation between steps
  - Template Method: Each step follows the same structure (title, prompt, wait)
  - Memento Pattern: Meditation state preserved across chat messages

This is the meditation flow triggered by DISTRESS intent detection.
"""

from typing import Optional

import logging

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


# Maximum step index
MAX_STEP = len(MEDITATION_STEPS)


def get_distress_response() -> str:
    """
    Get the initial distress acknowledgment message.

    This is shown before the meditation starts — acknowledges pain,
    offers the meditation, and includes crisis helpline info.
    """
    return (
        "I hear you, and I want you to know that your feelings are valid. 🙏\n\n"
        "In moments like these, the teachings remind us that suffering "
        "is a doorway to transformation. It may not feel like it now, "
        "but pain can be a catalyst for deeper awareness.\n\n"
        "Would you like me to guide you through a **Serene Mind meditation** "
        "to help you find some inner peace right now?\n\n"
        "🆘 *If you're in immediate crisis, please reach out:*\n"
        "- *National Suicide Prevention Lifeline: 988 (US)*\n"
        "- *iCall: 9152987821 (India)*\n"
        "- *Crisis Text Line: Text HOME to 741741*"
    )


def get_meditation_step(step: int) -> Optional[dict]:
    """
    Get a specific meditation step.

    Args:
        step: Step number (1-4)

    Returns:
        Dict with 'step', 'title', 'prompt' or None if step is invalid
    """
    if 1 <= step <= MAX_STEP:
        return MEDITATION_STEPS[step - 1]
    return None


def format_meditation_response(step: int) -> str:
    """
    Format a meditation step for the chat response.

    Adds step indicator and title header to the meditation prompt.
    """
    step_data = get_meditation_step(step)
    if not step_data:
        return "The meditation is complete. Thank you for practicing with me. 🙏"

    header = f"**Step {step_data['step']}/{MAX_STEP}: {step_data['title']}**\n\n"
    return header + step_data["prompt"]


def is_meditation_complete(step: int) -> bool:
    """Check if all meditation steps have been completed."""
    return step > MAX_STEP


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
