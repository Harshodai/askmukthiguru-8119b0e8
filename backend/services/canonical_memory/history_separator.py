"""Chat History Separation — Phase 9 of the Adaptive Memory System.

This module enforces the strict boundary between three distinct layers:

- **History**: "What did we discuss?" — session transcripts, conversation summaries
- **Memory**: "What durable information do we know about this user?" — canonical_memories
- **Knowledge**: "What does the corpus teach?" — Qdrant spiritual_wisdom

The separator ensures temporary conversation information does NOT become durable
memory unintentionally. It classifies each turn as transient (history-only) or
durable (memory-worthy), and builds session-history context that never leaks
into the memory context.

Design principle from memory-target-architecture.md §2:
    "Strict separation. USER MEMORY, CHAT HISTORY, and KNOWLEDGE BASE never
     share stores, vectors, or retrieval paths."
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token estimation (1 token ≈ 4 chars for English, ~3 chars for Indic scripts)
# ---------------------------------------------------------------------------

_TOKEN_CHAR_RATIO_EN = 4
_TOKEN_CHAR_RATIO_INDIC = 3


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length. Handles mixed scripts."""
    if not text:
        return 0
    indic_chars = sum(
        1 for ch in text
        if unicodedata.category(ch).startswith(("Lo",))  # "Lo" = Letter, other
        and ord(ch) > 0x0900  # Devanagari and above in Unicode block
    )
    total = len(text)
    if total == 0:
        return 0
    indic_ratio = indic_chars / total
    char_ratio = (
        _TOKEN_CHAR_RATIO_EN * (1 - indic_ratio)
        + _TOKEN_CHAR_RATIO_INDIC * indic_ratio
    )
    return max(1, int(total / char_ratio))


# ---------------------------------------------------------------------------
# Indic word-boundary helper
# ---------------------------------------------------------------------------
# Python's \b treats Indic vowel signs (matras, category "M") as non-word
# chars, so \b fires *inside* Telugu/Tamil/Kannada words.  This helper
# checks that a regex match is a standalone word, not a substring of a
# larger Indic word.

def _is_standalone_word(text: str, start: int, end: int) -> bool:
    """Return True if the match at [start:end) is a complete word.

    For Latin text: checks ASCII word boundaries.
    For Indic text: checks that the char before/after is not a Letter or Mark.
    """
    if start > 0:
        prev = text[start - 1]
        cat = unicodedata.category(prev)
        if cat.startswith(("L", "M")):
            return False
    if end < len(text):
        nxt = text[end]
        cat = unicodedata.category(nxt)
        if cat.startswith(("L", "M")):
            return False
    return True


# ---------------------------------------------------------------------------
# Transient topic classification (deterministic, no LLM)
# ---------------------------------------------------------------------------

# Weather patterns — English + Indic (no \b; use _is_standalone_word at call site)
_WEATHER_RE = re.compile(
    r"(?:weather|rain(?:ing)?|rainy|sunny|cold|hot|temperature|storm|humid|wind|"
    r"मौसम|बारिश|धूप|ठंड|गर्म|तापमान|"
    r"వాతావరణం|వర్షం|ఎండ|చల్లదనం|వేడి|"
    r"வானிலை|மழை|வெயில்|குளிர்|வெப்பம்|"
    r"ಹವಾಮಾನ|ಮಳೆ|ಬಿಸಿಲು|ಚಳಿ|ಬಿಸಿ|"
    r"हवामान|पाऊस|उन्हाळा|थंडी|गरमी)",
    re.IGNORECASE,
)

# Current events / news (no \b; use _is_standalone_word at call site)
_CURRENT_EVENTS_RE = re.compile(
    r"(?:news|headline|politi(?:cal|cs)|election|president|minister|"
    r"cricket|match|score|world.?cup|olympic|gdp|inflation|"
    r"समाचार|राजनीति|चुनाव|"
    r"వార్తలు|రాజకీయాలు|"
    r"செய்தி|அரசியல்|"
    r"ಸುದ್ದಿ|ರಾಜಕಾರಣ)",
    re.IGNORECASE,
)

# Greetings / phatic language — matches if message STARTS with a greeting word
# (allows trailing content like "how are you?" after "Hello")
_GREETING_RE = re.compile(
    r"^\s*(?:hi|hello|hey|namaste|namaskaram|vanakkam|good\s*(?:morning|afternoon|evening|night)"
    r"|thanks?|thank\s*you|bye|goodbye|see\s*you|take\s*care|"
    r"नमस्ते|नमस्कार|शुभ प्रभात|धन्यवाद|अलविदा|"
    r"నమస్కారం|శుభోదయం|ధన్యవాదాలు|"
    r"வணக்கம்|நன்றி|பிரியாவிடை|"
    r"ನಮಸ್ಕಾರ|ಶುಭೋದಯ|ಧನ್ಯವಾದ)",
    re.IGNORECASE,
)

# Temporal / time-bound references (no \b; use _is_standalone_word at call site)
_TEMPORAL_RE = re.compile(
    r"(?:today|yesterday|tomorrow|this\s*(?:morning|afternoon|evening|week|month|year)"
    r"|last\s*(?:week|month|year|night)|next\s*(?:week|month|year)"
    r"|right\s*now|currently|at\s*the\s*moment|this\s*time|"
    r"आज|कल|परसों|इस\s*हफ़्ते|पिछले\s*महीने|"
    r"ఈరోజు|నిన్న|రేపు|"
    r"இன்று|நேற்று|நாளை|"
    r"ಇಂದು|ನಾಳೆ|ನಿನ್ನೆ)",
    re.IGNORECASE,
)

# Transient states (fatigue, mood moments, temporary conditions)
_TRANSIENT_STATE_RE = re.compile(
    r"(?:i(?:'m| am)\s*(?:tired|sleepy|bored|hungry|thirsty|busy|free|done)"
    r"|just\s*(?:checking|browsing|looking)"
    r"|can(?:'t| not)\s*(?:sleep|focus|concentrate)"
    r"|i(?:'ve| have)\s*(?:a\s*(?:meeting|call|appointment))"
    r"|feeling\s*(?:better|worse|ok|fine|okay|good|bad|sick)"
    r"|(?:not\s*)?(?:in\s*the\s*mood|feeling\s*(?:lazy|energetic))"
    r"|after\s*(?:lunch|dinner|tea|breakfast)"
    r"|मैं\s*(?:थका\s*हूँ|भूखा\s*हूँ|व्यस्त\s*हूँ|"
    r"आराम\s*कर\s*रहा\s*हूँ)"
    r"|మేము\s*(?:అలసిపోయాము|ఆకలిగా\s*ఉన్నాం|"
    r"బిజీగా\s*ఉన్నాము)"
    r"|நான்\s*(?:சோர்வாக\s*இருக்கிறேன்|பசியாக\s*இருக்கிறேன்))",
    re.IGNORECASE,
)

# Simple yes/no/acknowledgment acknowledgments
_ACKNOWLEDGMENT_RE = re.compile(
    r"^\s*(?:ok|okay|sure|got\s*it|i\s*see|right|yeah|yep|nope|no|yes"
    r"|हाँ|जी|नहीं|ठीक\s*है|समझ\s*गया"
    r"|సరే|అవును|లేదు|అర్థమైంది"
    r"|சரி|ஆம்|இல்லை|புரிந்தது"
    r"|ಸರಿ|ಹೌದು|ಇಲ್ಲ|ಅರ್ಥವಾಯಿತು)\s*[.!.]*\s*$",
    re.IGNORECASE,
)

# Durable topics: preferences, goals, relationships, self-disclosure
_DURABLE_PREFERENCE_RE = re.compile(
    r"(?:i\s*(?:prefer|like|love|enjoy|hate|dislike|want|need|wish)"
    r"|my\s*(?:favorite|preferred|fav)"
    r"|please\s*(?:use|write|explain|make)"
    r"|don'?t\s*(?:use|write|make|include)"
    r"|मुझे.*(?:पसंद.*है|नापसंद.*है|चाहिए)"
    r"|నాకు.*(?:ఇష్టం|కావాలి|అవసరం)"
    r"|எனக்கு.*(?:பிடிக்கும்|வேண்டும்)"
    r"|ನನಗೆ.*(?:ಇಷ್ಟ|ಬೇకು|ಅವಶ್ಯಕతె))",
    re.IGNORECASE,
)

_DURABLE_FACT_RE = re.compile(
    r"(?:i(?:\s+am\s+(?!(?:tired|sleepy|bored|hungry|thirsty|busy|free|done|feeling))|\s+'m\s+(?!(?:tired|sleepy|bored|hungry|thirsty|busy|free|done|feeling))|\s+(?:was|have|had|live|work|study|practi[sc]e|teach))"
    r"|my\s*(?:name|family|wife|husband|child(?:ren)?|guru|teacher|friend)"
    r"|i(?:'ve| have)\s*(?:been|always|never)"
    r"|मैं\s*(?:हूँ|रहता\s*हूँ|काम\s*करता\s*हूँ|पढ़ता\s*हूँ)"
    r"|నేను\s*(?:ఉన్నాను|పని\s*చేస్తాను|చదువుతాను)"
    r"|நான்\s*(?:இருக்கிறேன்|வேலை\s*செய்கிறேன்|படிக்கிறேன்))",
    re.IGNORECASE,
)


@dataclass
class MemoryCandidate:
    """Lightweight durable-fact candidate extracted by the separator."""

    statement: str
    memory_type: str
    confidence: float = 0.7
    fact_key: Optional[str] = None
    evidence: str = ""


@dataclass
class TurnClassification:
    """Result of classifying a single conversation turn."""

    durable_facts: list[MemoryCandidate] = field(default_factory=list)
    transient_topics: list[str] = field(default_factory=list)
    session_context: dict[str, Any] = field(default_factory=dict)
    is_greeting: bool = False
    is_acknowledgment: bool = False
    is_temporal: bool = False


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------


def _has_pattern_match(text: str, pattern: re.Pattern) -> Optional[re.Match]:
    """Search text for pattern, ensuring match is a standalone word (not substring)."""
    for m in pattern.finditer(text):
        if _is_standalone_word(text, m.start(), m.end()):
            return m
    return None


def is_transient(topic: str) -> bool:
    """Determine if a topic is transient (weather, current events, temporary context).

    Returns True for topics that should live ONLY in the history layer and
    NEVER become durable memory.

    Deterministic — no LLM call. Uses regex pattern matching against known
    transient categories: weather, current events, temporal references,
    transient physical states, and simple acknowledgments.
    """
    if not topic or not topic.strip():
        return True

    text = topic.strip()

    # Empty / trivial → transient
    if len(text.split()) <= 2:
        return True

    # Pattern matching (using standalone-word check for Indic safety)
    if _has_pattern_match(text, _WEATHER_RE):
        return True
    if _has_pattern_match(text, _CURRENT_EVENTS_RE):
        return True
    if _has_pattern_match(text, _TEMPORAL_RE):
        return True
    if _has_pattern_match(text, _TRANSIENT_STATE_RE):
        return True
    if _ACKNOWLEDGMENT_RE.match(text):
        return True
    if _GREETING_RE.match(text):
        return True

    return False


def classify_conversation_turn(
    user_message: str,
    assistant_response: str,
) -> TurnClassification:
    """Classify whether a turn contains memory-worthy durable information.

    Analyzes the user message (primary) and assistant response (secondary)
    to separate durable facts from transient discussion.

    Returns:
        TurnClassification with durable_facts, transient_topics, and session_context.
    """
    classification = TurnClassification()

    user_text = (user_message or "").strip()

    # --- Greeting detection ---
    if _GREETING_RE.match(user_text):
        classification.is_greeting = True
        classification.transient_topics.append("greeting")
        classification.session_context["type"] = "greeting"
        # Don't return early — greeting may co-occur with durable content

    # --- Acknowledgment detection ---
    if _ACKNOWLEDGMENT_RE.match(user_text):
        classification.is_acknowledgment = True
        classification.transient_topics.append("acknowledgment")
        classification.session_context["type"] = "acknowledgment"
        return classification

    # --- Transient topic detection ---
    transient_topics: list[str] = []

    if _has_pattern_match(user_text, _WEATHER_RE):
        transient_topics.append("weather")
    if _has_pattern_match(user_text, _CURRENT_EVENTS_RE):
        transient_topics.append("current_events")
    if _has_pattern_match(user_text, _TEMPORAL_RE):
        transient_topics.append("temporal_reference")
    if _has_pattern_match(user_text, _TRANSIENT_STATE_RE):
        transient_topics.append("transient_state")

    is_purely_transient = bool(transient_topics)

    if transient_topics:
        classification.transient_topics = transient_topics
        classification.is_temporal = bool(
            "temporal_reference" in transient_topics
            or "transient_state" in transient_topics
        )
        classification.session_context["type"] = "transient"
        classification.session_context["topics"] = transient_topics

    # --- Durable fact extraction (deterministic patterns) ---
    durable_facts: list[MemoryCandidate] = []

    # Note: even greeting/acknowledgment messages may contain durable facts
    # (e.g., "Hello! I live in Chennai.") — extract them below

    # Check for explicit "remember that" / "don't forget" requests
    explicit_re = re.compile(
        r"(?:remember|don'?t\s*forget|keep\s*in\s*mind|note\s*that|"
        r"याद\s*रखो|गोल\s*मारो|"
        r"గుర్తుపెట్టుకో|మరచిపోకు|"
        r"நினைவில்\s*கொள்|மறந்துவிடாதே)",
        re.IGNORECASE,
    )
    if explicit_re.search(user_text):
        has_durable_patterns = True
        # Strip the explicit prefix and treat the rest as durable
        cleaned = explicit_re.sub("", user_text).strip(" ,.:;")
        if cleaned and len(cleaned.split()) >= 2:
            durable_facts.append(
                MemoryCandidate(
                    statement=cleaned,
                    memory_type="USER_EXPLICIT",
                    confidence=0.95,
                    evidence=user_text,
                )
            )

    # Check for preference patterns
    if _DURABLE_PREFERENCE_RE.search(user_text):
        has_durable_patterns = True
        # Extract the preference statement
        pref_match = re.search(
            r"(?:i\s*(?:prefer|like|love|enjoy|hate|dislike|want|need|wish)"
            r"|please\s*(?:use|write|explain|make)"
            r"|don'?t\s*(?:use|write|make|include)"
            r"|(?:ముఝే|నాకు|எనక్కు|ನನగె).*(?:పసంద|ఇష్టం|பிடிக்கும்|ಇಷ್ಟ)"
            r".*?(?:है|ఉంది|ும்|ಿದೆ))"
            r"(.*)",
            user_text,
            re.IGNORECASE | re.DOTALL,
        )
        pref_content = pref_match.group(0).strip() if pref_match else user_text.strip()
        # Limit to first sentence or 200 chars
        pref_content = re.split(r"[.!?।]", pref_content)[0].strip()
        if len(pref_content) > 200:
            pref_content = pref_content[:197] + "..."
        if pref_content and len(pref_content.split()) >= 2:
            # Determine fact_key from content
            fact_key = _infer_fact_key(pref_content)
            durable_facts.append(
                MemoryCandidate(
                    statement=pref_content,
                    memory_type="PREFERENCE",
                    confidence=0.8,
                    fact_key=fact_key,
                    evidence=user_text,
                )
            )

    # Check for durable self-disclosure patterns
    if _DURABLE_FACT_RE.search(user_text):
        # Extract the self-disclosure
        disclosure_match = re.search(
            r"(?:i\s*(?:am|'m|was|have|live|work|study|practi[sc]e|teach)"
            r"|my\s*(?:name|family|wife|husband|child(?:ren)?|guru|teacher|friend)"
            r"|(?:मैं|నేను|நான்)\s*(?:हूँ|ఉన్నాను|இருக்கிறேன்))"
            r"(.*)",
            user_text,
            re.IGNORECASE | re.DOTALL,
        )
        if disclosure_match:
            disclosure = disclosure_match.group(0).strip()
            disclosure = re.split(r"[.!?।]", disclosure)[0].strip()
            if len(disclosure) > 200:
                disclosure = disclosure[:197] + "..."
            if disclosure and len(disclosure.split()) >= 2:
                fact_key = _infer_fact_key(disclosure)
                memory_type = _infer_memory_type(disclosure)
                durable_facts.append(
                    MemoryCandidate(
                        statement=disclosure,
                        memory_type=memory_type,
                        confidence=0.75,
                        fact_key=fact_key,
                        evidence=user_text,
                    )
                )

    # Check for goal/project patterns
    goal_re = re.compile(
        r"(?:i(?:'m| am)\s*(?:trying|working|planning|aiming)"
        r"|my\s*(?:goal|project|plan|target)"
        r"|i\s*(?:want|plan|aim)\s*to"
        r"|मेरा\s*(?:लक्ष्य|योजना)"
        r"|నా\s*(?:లక్ష్యం|ప్రణాళిక)"
        r"|என்\s*(?:இலக்கு|திட்டம்))"
        r"(.*)",
        re.IGNORECASE | re.DOTALL,
    )
    goal_match = goal_re.search(user_text)
    if goal_match:
        has_durable_patterns = True
        goal_text = goal_match.group(0).strip()
        goal_text = re.split(r"[.!?।]", goal_text)[0].strip()
        if len(goal_text) > 200:
            goal_text = goal_text[:197] + "..."
        if goal_text and len(goal_text.split()) >= 3:
            durable_facts.append(
                MemoryCandidate(
                    statement=goal_text,
                    memory_type="GOAL",
                    confidence=0.7,
                    evidence=user_text,
                )
            )

    classification.durable_facts = durable_facts

    # Mixed turns: transient topics detected but durable facts also extracted
    if is_purely_transient and durable_facts:
        classification.session_context["type"] = "mixed"
    elif is_purely_transient:
        classification.durable_facts = []
        classification.session_context["type"] = "transient"
    elif durable_facts:
        classification.session_context["type"] = "durable"
    elif not classification.transient_topics:
        classification.session_context["type"] = "neutral"

    return classification


# ---------------------------------------------------------------------------
# Fact key inference
# ---------------------------------------------------------------------------

_FACT_KEY_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"live[sd]?\s+in|resident\s+of|based\s+in|रहत[ााई]|నివసిస్తున్నా|வாழ்கிறேன்", re.I), "user:lives_in"),
    (re.compile(r"work[s]?\s+(?:as|at|in)|occupation|profession|job|काम\s+करत[ााई]|పని\s*చేస్తు|வேலை\s*செய்", re.I), "user:occupation"),
    (re.compile(r"prefer[s]?\s+(?:concise|brief|short|detailed|thorough|simple)|like[s]?\s+(?:concise|detailed)|पसंद.*(?:संक्षिप्त|विस्तृత)|ఇష్టం.*(?:సంక్షిప్తం|వివరంగా)", re.I), "user:prefers_tone"),
    (re.compile(r"prefer[s]?\s+(?:deep|surface|brief)|like[s]?\s+(?:deep|surface)|deep(?:er)?\s+(?:explanation|understanding)", re.I), "user:prefers_depth"),
    (re.compile(r"prefer[s]?\s+(?:hindi|telugu|tamil|kannada|marathi|english)|speak(?:s|ing)?\s+(?:hindi|telugu|tamil|kannada|marathi)|हिंदी\s+में|తెలుగు\s*లో|தமிழில்", re.I), "user:prefers_language"),
    (re.compile(r"meditat(?:e|ion|ing)\s+(?:for|experience|practice|level|years?)|vipassana|mindfulness\s+(?:practice|experience)|ధ్యానం|தியானம்|ಧ್ಯಾನ", re.I), "user:meditation_experience"),
    (re.compile(r"current(?:ly)?\s+(?:working|project|task)|my\s+project|इस\s+समय.*प्रोजेक्ट|ప్రస్తుతం.*ప్రాజెక్ట్", re.I), "user:current_project"),
    (re.compile(r"(?:interested|interest|passionate|fond)\s+in|spiritual|yoga|meditation|chanting", re.I), "user:spiritual_interest"),
    (re.compile(r"my\s+(?:guru|teacher|master|mentor|friend|wife|husband|child|family|parent)|गुरु|परिवार|మాస్టారు|குரு", re.I), "user:relationship"),
]


def _infer_fact_key(text: str) -> str | None:
    """Infer a dedup fact_key from statement content."""
    for pattern, fact_key in _FACT_KEY_MAP:
        if pattern.search(text):
            return fact_key
    return None


def _infer_memory_type(text: str) -> str:
    """Infer memory_type from statement content."""
    text_lower = text.lower()
    # Order matters: check goals before preferences (goals contain "want to")
    if any(kw in text_lower for kw in ("goal", "plan", "project", "target", "trying to", "working on", "want to", "aim to", "लक्ष्य", "ప్రణాళిக")):
        return "GOAL"
    if any(kw in text_lower for kw in ("prefer", "like", "love", "hate", "dislike", "want", "need", "पसंद", "ఇష్టం", "பிடிக்கும்")):
        return "PREFERENCE"
    if any(kw in text_lower for kw in ("interested", "interest", "passionate", "fond", "spiritual", "yoga", "meditation", "practice")):
        return "INTEREST"
    if any(kw in text_lower for kw in ("my name", "i am", "i'm", "i live", "i work", "my family", "मैं", "नేను", "நான்")):
        return "PROFILE"
    if any(kw in text_lower for kw in ("my guru", "my teacher", "my friend", "my wife", "my husband", "guru", "परिवार")):
        return "RELATIONSHIP"
    return "REFLECTION"


# ---------------------------------------------------------------------------
# History context builder
# ---------------------------------------------------------------------------


def build_history_context(
    session_messages: list[dict[str, Any]],
    *,
    max_tokens: int = 1024,
    max_turns: int = 20,
) -> str:
    """Build session history context for generation.

    This builds the HISTORY layer context only. It does NOT include durable
    memory — that is the memory layer's job (Phase 8 / MemoryRetriever).

    The output is a compact, provenance-labeled block suitable for injection
    into a generation prompt.

    Args:
        session_messages: ordered list of {"role": ..., "content": ...} dicts
        max_tokens: token budget (estimated via character count)
        max_turns: hard cap on number of turns included

    Returns:
        Formatted history context string, bounded by max_tokens.
    """
    if not session_messages:
        return ""

    # Filter to valid messages
    valid_messages = [
        m for m in session_messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    if not valid_messages:
        return ""

    # Take the most recent turns (bounded by max_turns)
    recent = valid_messages[-max_turns:]

    # Build the history block with provenance labels
    lines: list[str] = []
    lines.append("[History: this_session]")
    lines.append(
        "The following is the conversation history for this session. "
        "Treat it as context, not as durable user facts."
    )

    char_budget = max_tokens * _TOKEN_CHAR_RATIO_EN  # Convert tokens to chars
    current_chars = sum(len(line) + 1 for line in lines)

    for msg in recent:
        role = "Seeker" if msg.get("role") == "user" else "Guru"
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        line = f"- {role}: {content}"
        line_chars = len(line) + 1  # +1 for newline

        if current_chars + line_chars > char_budget:
            # Try to truncate this last message
            remaining = char_budget - current_chars - 5  # room for "..."
            if remaining > 30:
                truncated = content[:remaining].rstrip()
                lines.append(f"- {role}: {truncated}...")
            break

        lines.append(line)
        current_chars += line_chars

    lines.append("[/History]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Separation validator
# ---------------------------------------------------------------------------

_HISTORY_MARKERS = re.compile(
    r"\[History:.*?\]|Seeker:|Guru:|- (?:Seeker|Guru):"
)

_MEMORY_MARKERS = re.compile(
    r"\[Memory:.*?\]|\[Memory Context.*?\]|canonical_memory|memory_type.*?:|confidence.*?:"
)


def validate_separation(
    memory_context: str,
    history_context: str,
) -> bool:
    """Validate that memory_context and history_context are properly separated.

    Checks:
    1. memory_context does NOT contain history-only content (conversation transcripts)
    2. history_context does NOT contain durable memory content
    3. Both contexts are non-empty when they should be (or both empty is valid)

    Returns True if separation is valid, False if leakage detected.
    """
    # Empty contexts are valid (no data = no leakage)
    if not memory_context and not history_context:
        return True

    # Check: memory_context should not contain history markers
    if memory_context and _HISTORY_MARKERS.search(memory_context):
        logger.warning(
            "Separation violation: memory_context contains history markers"
        )
        return False

    # Check: history_context should not contain memory markers
    if history_context and _MEMORY_MARKERS.search(history_context):
        logger.warning(
            "Separation violation: history_context contains memory markers"
        )
        return False

    # Check: history should not contain memory-type metadata patterns
    if history_context:
        # Look for memory candidate JSON-like patterns
        if re.search(r'"memory_type"\s*:', history_context):
            logger.warning(
                "Separation violation: history_context contains memory_type metadata"
            )
            return False
        if re.search(r'"fact_key"\s*:', history_context):
            logger.warning(
                "Separation violation: history_context contains fact_key metadata"
            )
            return False
        # Plain-text fact_key pattern (e.g. "fact_key: user:lives_in")
        if re.search(r"fact_key:\s*\S+", history_context):
            logger.warning(
                "Separation violation: history_context contains fact_key metadata"
            )
            return False

    return True


if __name__ == "__main__":
    # Self-check: verify classification of known patterns
    cases = [
        ("What's the weather today?", "It's sunny!", "transient"),
        ("Hello, how are you?", "I'm doing well, seeker.", "greeting"),
        ("I prefer concise answers.", "Understood.", "durable"),
        ("I live in Mumbai.", "Mumbai is a beautiful city.", "durable"),
        ("I'm tired today.", "Take rest.", "transient"),
        ("Remember that I prefer Hindi.", "Noted.", "durable"),
        ("What is meditation?", "Meditation is a practice...", "neutral"),
    ]

    for user_msg, asst_resp, expected_type in cases:
        result = classify_conversation_turn(user_msg, asst_resp)
        actual_type = result.session_context.get("type", "neutral")
        status = "PASS" if actual_type == expected_type else "FAIL"
        print(
            f"  [{status}] '{user_msg[:40]}...' → {actual_type} "
            f"(expected {expected_type}, "
            f"durable={len(result.durable_facts)}, "
            f"transient={result.transient_topics})"
        )

    # Test history context building
    msgs = [
        {"role": "user", "content": "I live in Mumbai"},
        {"role": "assistant", "content": "Mumbai is wonderful!"},
        {"role": "user", "content": "I prefer Hindi responses"},
        {"role": "assistant", "content": "I'll respond in Hindi from now on."},
    ]
    history = build_history_context(msgs, max_tokens=200)
    print(f"\nHistory context ({len(history)} chars):")
    print(history)

    # Test separation validation
    assert validate_separation("", "") is True
    assert validate_separation("User lives in Mumbai.", "") is True
    assert validate_separation("", "Seeker: hello") is True
    assert validate_separation("User lives in Mumbai.", "Seeker: hello") is True
    # Leakage: memory contains history
    assert validate_separation("Seeker: hello", "some history") is False
    # Leakage: history contains memory
    assert validate_separation("some memory", "memory_type: PREFERENCE") is False
    assert validate_separation("some memory", "fact_key: user:lives_in") is False
    print("\nAll self-checks passed.")
