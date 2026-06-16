import logging
import re

from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex pre-router for cheap, deterministic intent classification (0 ms latency)
# ---------------------------------------------------------------------------
# Design contract:
#   - These regexes MUST be conservative. A false positive here bypasses the LLM
#     classifier and the meditation-hijack guard. Better to fall through to the
#     LLM than to mis-route on a marginal pattern.
#   - All patterns use word boundaries (\b) and require a contextual cue (imperative
#     verb + meditation noun for MEDITATION).

# Obvious greetings/casual intents — single-word or compact greetings.
GREETINGS_RE = re.compile(
    r"^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening)|yo|sup|namaste|pranam)(\s+.*)?$",
    re.IGNORECASE,
)

# Acute distress keywords. Kept tight to avoid swallowing FACTUAL queries that mention
# distress as a topic (e.g. "What is the relationship between suffering and inner truth?").
DISTRESS_RE = re.compile(
    r"\b("
    r"suicide|kill\s*myself|want\s*to\s*die|end\s*my\s*life|"
    r"panic\s*attack|severe\s*anxiety|"
    r"hurting\s*myself|self[-\s]*harm"
    r")\b",
    re.IGNORECASE,
)

# MEDITATION pre-router (Phase A1.3 fix).
# Requires BOTH (a) an imperative verb AND (b) a meditation noun in the same match.
# This prevents queries like "What is Soul Sync?" or "Can I practice Soul Sync on Mars?"
# from being classified as MEDITATION at the regex layer.
#
# Examples that MATCH (intentional):
#   "start meditation"
#   "let's meditate"
#   "begin Serene Mind"
#   "guide me through Soul Sync"
#   "open the breathing exercise"
#   "do a meditation session now"
#
# Examples that DO NOT MATCH (intentional):
#   "what is meditation"            (no imperative)
#   "can I practice Soul Sync"      (interrogative)
#   "is meditation helpful"         (no imperative)
#   "I want to meditate someday"    (no temporal urgency; LLM will decide)
_MEDITATION_IMPERATIVE = (
    r"("
    r"start|begin|open|let'?s|lets|guide\s+me|take\s+me\s+through|"
    r"walk\s+me\s+through|lead\s+me|do\s+a?"
    r")"
)
_MEDITATION_NOUN = (
    r"("
    r"meditation|meditat(?:e|ing)|"
    r"serene\s*mind|soul\s*sync|"
    r"breathwork|breathing\s+(?:exercise|practice|meditation)|"
    r"guided\s+practice"
    r")"
)
MEDITATION_RE = re.compile(
    rf"\b{_MEDITATION_IMPERATIVE}\b.{{0,40}}\b{_MEDITATION_NOUN}\b",
    re.IGNORECASE,
)


def preroute_intent(query: str) -> Optional[str]:
    """Statically classify obvious intents using compiled regexes.

    Bypasses the LLM classifier for performance (0 ms latency) when the user's message
    is unambiguous. Returns None for any ambiguous case so the LLM (and the
    meditation-hijack guard inside the LLM path) can take over.

    Returns:
        "DISTRESS" | "MEDITATION" | "CASUAL" | None
    """
    if not getattr(settings, "feature_regex_prerouter", True):
        return None

    cleaned = query.strip().lower()
    if not cleaned:
        return "CASUAL"

    if DISTRESS_RE.search(cleaned):
        logger.info("Regex Pre-Router: matched DISTRESS intent for query: %s...", query[:50])
        return "DISTRESS"

    if MEDITATION_RE.search(cleaned):
        logger.info("Regex Pre-Router: matched MEDITATION intent for query: %s...", query[:50])
        return "MEDITATION"

    if GREETINGS_RE.match(cleaned):
        logger.info("Regex Pre-Router: matched CASUAL intent for query: %s...", query[:50])
        return "CASUAL"

    return None
