"""T1-05: fail closed on the teaching route.

When first person cannot serve a teaching-lane turn (kill switch off, node
fault), the answer is the static abstain, never LLM-written teaching prose.
The generating path is allowed only when ``FIRST_PERSON_LLM_FALLBACK_ENABLED``
is deliberately true.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Static abstain used where no PipelineContext exists (generate_answer guard).
# Same wording as the bridge's English abstain; no model generates it.
STATIC_ABSTAIN_TEXT = (
    "I don't have a verified verbatim teaching that directly "
    "answers this, and I'd rather say so than improvise one. "
    "Try rephrasing, or ask about a specific teaching or practice."
)


def teaching_generation_allowed() -> bool:
    """True only when generated teaching prose may serve a teaching-lane turn."""
    return getattr(settings, "first_person_llm_fallback_enabled", False) is True


def fail_closed_active() -> bool:
    return not teaching_generation_allowed()


def record_fail_closed(reason: str) -> None:
    """Increment the fail-closed counter; metrics must never break a request."""
    try:
        from app.metrics import FP_FAIL_CLOSED_TOTAL

        FP_FAIL_CLOSED_TOTAL.labels(reason=reason).inc()
    except Exception:  # noqa: BLE001
        logger.debug("fp fail-closed metric unavailable", exc_info=True)
