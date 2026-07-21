"""Mukthi Guru — Centralized query-pattern constants.

Single source for the regex / keyword lists used by intent routing and graph
selection. Previously `rag/nodes/intent.py` and `app/orchestrator_utils.py`
each declared their own `_SIMPLE_QUERY_PATTERNS` with *different* contents but
the same name, masked by a "MUST be kept in lock-step" comment that was never
enforced. Centralizing here makes the intent of each list explicit and removes
the name collision.

Naming convention:
- ``DOCTRINE_*``    — patterns consumed by ``rag/nodes/intent.py`` during
  intent routing (doctrine-bound spiritual terms).
- ``HEURISTIC_*``   — patterns consumed by ``app/orchestrator_utils.py``
  during graph selection (broad, generic phrasing).
"""

from __future__ import annotations

import re

# === rag/nodes/intent.py ==================================================

# Capability / meta questions ("what can you do", "who are you", ...).
# Substring match on the lowercased question.
DOCTRINE_CAPABILITY_PATTERNS: list[str] = [
    "what can you", "what do you know", "what topics", "what kind of things",
    "what can you answer", "what teachings do you have", "what is in your repository",
    "what do you store", "what information do you have", "how can you help",
    "what questions can you", "what are you able to", "tell me about yourself",
    "what do you do", "who are you", "what do you offer", "how do you work",
]

# Doctrine-bound simple queries. Use ``re.search`` so multi-word phrases such
# as "Explain the first sacred secret" still match.
DOCTRINE_SIMPLE_PATTERNS: list[str] = [
    r"^who is (sri )?preethaji",
    r"^who is (sri )?krishnaji",
    r"^what is (the )?beautiful state",
    r"^what is (the )?ekam",
    r"^what is deeksha",
    r"^what is soul sync",
    r"^what are (the )?four sacred secrets",
    r"^what is oneness",
    r"^what is moksha",
    r"^define ",
    r"^explain ",
]

# Temporal / real-time query markers. Substring match on the lowercased
# question; triggers web search and tier3_complex routing.
DOCTRINE_TEMPORAL_PATTERNS: list[str] = [
    "this month", "next festival", "upcoming", "when is", "schedule",
    "calendar", "latest", "current events", "this year", "next year",
    "next month", "last month", "this week", "next week", "today",
    "recent", "announcement", "program", "scope of manifest",
    "manifest scope", "ekam events", "oneness events",
]


# === app/orchestrator_utils.py ===========================================

# Heuristic simple-query detection (broad, generic phrasing). Consumed via
# ``re.search`` on the lowercased query.
HEURISTIC_SIMPLE_PATTERNS: list[str] = [
    r"^who\bs+",
    r"^what\bs+(is|are)\b",
    r"^when\b",
    r"^where\b",
    r"^how\s+(to|do|does|many|much)\b",
    r"^can\s+you\b",
    r"^explain\b",
    r"^what\s+did\b",
    r"^tell\s+me\s+about\b",
    r"^describe\b",
    r"^define\b",
    r"^meaning\s+of\b",
]

# Comparative / analytical / multi-hop query markers.
HEURISTIC_DEEP_PATTERNS: list[str] = [
    r"\bcompare\b", r"\bcontrast\b", r"\bdifference between\b",
    r"\bsimilarities between\b", r"\bversus\b", r"\bvs\b",
    r"\brelationship between\b", r"\bhow are .* connected\b",
    r"\bpros and cons\b", r"\badvantages? and disadvantages?\b",
    r"\bevolution of\b", r"\bover time\b", r"\bacross different\b",
    r"\btrick question\b", r"\btrap\b", r"\bfooled\b",
    r"\btest the bot\b", r"\btry to confuse\b",
]

# Doctrine keyword fast-path triggers (common spiritual terms + founder
# names). Substring match on the lowercased query.
DOCTRINE_FAST_PATH_KEYWORDS: list[str] = [
    # Core teachings
    "four sacred secrets", "four secrets", "sacred secret",
    "deeksha", "oneness blessing",
    "soul sync", "soul-sync",
    "ekam", "varadaiahpalem",
    "manifest 2026", "manifest 2025", "12 powers",
    "beautiful state", "beautiful state teachings",
    "preethaji", "krishnaji", "founder",
    "loka seva", "ekam world",
    # Expanded for broader fast-path coverage
    "meditation", "serene mind", "breath", "breathing",
    "consciousness", "oneness", "surrender", "bliss",
    "suffering", "soul", "spiritual", "divine", "enlightenment",
    "karma", "dharma", "moksha", "atma", "guru",
    "peace", "love", "gratitude", "compassion", "wisdom",
]

# Multi-part guard: queries containing conjunctions/comparatives should not
# be fast-pathed even when doctrine keywords are present (avoids routing
# "What is deeksha and how do I practice it?" to the fast graph).
HEURISTIC_MULTI_PART_INDICATORS: list[str] = [
    r"\band\b", r"\balso\b", r"\bplus\b", r"\bbesides\b",
    r"\bin addition\b", r"\bfurthermore\b", r"\bmoreover\b",
]

# Broader regex-based simple-query detection. Consumed via ``re.search`` on
# the lowercased query.
HEURISTIC_BROAD_SIMPLE_PATTERNS: list[str] = [
    r"^(what|who|where|when|how|why|is|are|can|do|does|did)\s",
    r"^(tell me|explain|describe|define)\s+(about|the|what|how)",
    r"^(what is|what are|who is|who are|where is|where are)\s+",
]

# Deep-cue markers that promote a query to tier4_deep.
TIER4_DEEP_CUES: list[str] = [
    r"\bdeep\b",
    r"\bgo deeper\b",
    r"\bexplore in depth\b",
    r"\bthorough\b",
    r"\bcomprehensive\b",
    r"\bdoctrinal synthesis\b",
    r"\bsynthesis of\b",
    r"\bhow does .* connect to .* and .*(?:connect|relate|lead)",
    r"\bcompare .* and .* in the (?:teachings|doctrine|tradition)",
    r"\brelationship between .* and .* and .*",
    r"\binterconnected\b",
    r"\bmulti[- ]?hop\b",
    r"\banalytical\b",
]


def detect_tier4_deep_cues(question: str) -> bool:
    """Heuristic cues that should route a query to tier4_deep.

    Matches multi-hop doctrinal synthesis, cross-teacher comparison, and
    explicit requests for deep analysis. Used by the intent router before
    the cheaper fast/standard paths fire.
    """
    lower_q = question.lower()
    return any(re.search(p, lower_q) for p in TIER4_DEEP_CUES)
