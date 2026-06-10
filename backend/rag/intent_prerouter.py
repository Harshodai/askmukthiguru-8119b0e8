import logging
import re

from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Compile regexes for quick matching
# Obvious greetings/casual intents
GREETINGS_RE = re.compile(
    r"^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening)|yo|sup|namaste|pranam)(\s+.*)?$",
    re.IGNORECASE
)

# Obvious distress intents (matches acute distress keywords)
DISTRESS_RE = re.compile(
    r"\b(suicide|kill\s*myself|want\s*to\s*die|end\s*my\s*life|panic\s*attack|severe\s*anxiety|depressed|hopeless|hurting\s*myself)\b",
    re.IGNORECASE
)

# Obvious meditation requests
MEDITATION_RE = re.compile(
    r"\b(start\s*meditation|let\'s\s*meditate|meditate|guided\s*practice|start\s*practice|breathing\s*exercise|soul\s*stage|meditation\s*practice)\b",
    re.IGNORECASE
)

def preroute_intent(query: str) -> Optional[str]:
    """
    Statically classify simple and obvious intents using regex.
    Bypasses LLM classification for performance (0ms latency).
    Returns:
        The matching intent string ("CASUAL", "DISTRESS", "MEDITATION") or None.
    """
    if not getattr(settings, "feature_regex_prerouter", True):
        return None

    cleaned = query.strip().lower()
    if not cleaned:
        return "CASUAL"

    if DISTRESS_RE.search(cleaned):
        logger.info(f"Regex Pre-Router: matched DISTRESS intent for query: {query[:50]}...")
        return "DISTRESS"

    if MEDITATION_RE.search(cleaned):
        logger.info(f"Regex Pre-Router: matched MEDITATION intent for query: {query[:50]}...")
        return "MEDITATION"

    if GREETINGS_RE.match(cleaned):
        logger.info(f"Regex Pre-Router: matched CASUAL intent for query: {query[:50]}...")
        return "CASUAL"

    return None
