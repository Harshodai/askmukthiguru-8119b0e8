"""
Mukthi Guru — Serene Mind Meditation Module

Design Patterns:
  - State Machine: 4-step linear progression with user confirmation between steps
  - Template Method: Each step follows the same structure (title, prompt, wait)
  - Memento Pattern: Meditation state preserved across chat messages

This is the meditation flow triggered by DISTRESS intent detection.
"""

import logging
from typing import Optional

from rag.prompts import MEDITATION_STEPS, DISTRESS_PROMPT

logger = logging.getLogger(__name__)

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
    """
    positive_signals = [
        "yes", "sure", "ok", "okay", "please", "let's", "lets",
        "guide me", "meditat", "help me", "start", "i'd like",
        "begin", "ready",
    ]
    message_lower = message.lower().strip()
    return any(signal in message_lower for signal in positive_signals)
