"""
Mukthi Guru — Serene Mind Emotional Intelligence Engine

Multi-language distress detection with graduated response levels.
Designed for Indian spiritual context with support for 10+ Indian languages.

Design Patterns:
  - Strategy Pattern: Multiple detection strategies (keyword, embedding, LLM)
  - Chain of Responsibility: Escalating detection severity levels
  - Observer Pattern: Conversation history analysis for escalation

Distress Levels:
  - NONE → Normal interaction
  - MILD → Light stress, gentle acknowledgment
  - MODERATE → Significant distress, meditation offer
  - SEVERE → Deep suffering, guided meditation + helpline
  - CRISIS → Immediate danger, helpline information first
"""

import logging
import re
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class DistressLevel(IntEnum):
    """Graduated distress severity levels."""
    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    CRISIS = 4


@dataclass
class DistressAssessment:
    """Result of a Serene Mind distress evaluation."""
    level: DistressLevel
    confidence: float  # 0.0 - 1.0
    detected_signals: list[str] = field(default_factory=list)
    language_detected: str = "en"
    recommended_response_type: str = "normal"  # normal, gentle, meditation, crisis


# ---------------------------------------------------------------------------
# Multi-language distress patterns
# ---------------------------------------------------------------------------

# English distress patterns
_EN_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(suicid|kill\s*my\s*self|end\s*(my|it)\s*all|want\s*to\s*die|self[\s-]*harm)\b",
        r"\b(hurt\s*myself|cut\s*myself|overdose|no\s*reason\s*to\s*live)\b",
    ],
    DistressLevel.SEVERE: [
        r"\b(hopeless|worthless|can'?t\s*go\s*on|give\s*up|no\s*point)\b",
        r"\b(deeply?\s*(depressed|sad|lonely)|unbearable\s*pain)\b",
        r"\b(meaningless|empty\s*inside|broken)\b",
    ],
    DistressLevel.MODERATE: [
        r"\b(stressed|anxious|anxiety|panic|overwhelm|can'?t\s*sleep|insomnia)\b",
        r"\b(depressed|sad|unhappy|miserable|frustrated|angry|furious)\b",
        r"\b(scared|afraid|terrified|worried|fear|nervous)\b",
        r"\b(lonely|isolated|alone|abandoned|rejected)\b",
    ],
    DistressLevel.MILD: [
        r"\b(tired|exhausted|drained|burnout|burn\s*out)\b",
        r"\b(confused|lost|uncertain|stuck|struggling)\b",
        r"\b(uneasy|uncomfortable|restless|unsettled)\b",
    ],
}

# Hindi distress patterns (Devanagari)
_HI_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(मरना\s*चाहता|मरना\s*चाहती|आत्महत्या|ज़िंदगी\s*खत्म|जीने\s*का\s*मन\s*नहीं)",
        r"(खुद\s*को\s*मारना|सब\s*खत्म\s*करना)",
    ],
    DistressLevel.SEVERE: [
        r"(बहुत\s*(दुखी|उदास|अकेला|अकेली)|जीवन\s*व्यर्थ|कोई\s*उम्मीद\s*नहीं)",
        r"(सहन\s*नहीं\s*हो\s*रहा|टूट\s*गया|टूट\s*गई|निराशा)",
    ],
    DistressLevel.MODERATE: [
        r"(तनाव|चिंता|घबराहट|परेशान|नींद\s*नहीं|अवसाद)",
        r"(दुखी|उदास|रोना|गुस्सा|डर|अकेलापन)",
        r"(तकलीफ|कष्ट|पीड़ा|दर्द)",
    ],
    DistressLevel.MILD: [
        r"(थका|थकान|उलझन|भ्रम|अशांत|बेचैन)",
    ],
}

# Tamil distress patterns
_TA_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(தற்கொலை|உயிரை\s*மாய்க்க|சாக\s*விரும்புகிறேன்)",
    ],
    DistressLevel.SEVERE: [
        r"(மிகவும்\s*வேதனை|நம்பிக்கையில்லை|தாங்க\s*முடியல|வாழ\s*விருப்பமில்லை)",
    ],
    DistressLevel.MODERATE: [
        r"(கஷ்டப்படுகிறேன்|பயம்|கவலை|தூக்கமின்மை|சோகம்|தனிமை)",
    ],
}

# Telugu distress patterns
_TE_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(ఆత్మహత్య|చచ్చిపోవాలని|బతకడం\s*ఇష్టం\s*లేదు)",
    ],
    DistressLevel.SEVERE: [
        r"(చాలా\s*బాధగా|ఎందుకు\s*బతకాలి|నిరాశ|తట్టుకోలేను)",
    ],
    DistressLevel.MODERATE: [
        r"(ఒత్తిడి|ఆందోళన|భయం|ఒంటరిగా|దుఃఖం|నిద్ర\s*రాదు)",
    ],
}

# Kannada distress patterns
_KN_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(ಆತ್ಮಹತ್ಯೆ|ಸಾಯಬೇಕು|ಬದುಕಲು\s*ಇಷ್ಟ\s*ಇಲ್ಲ)",
    ],
    DistressLevel.MODERATE: [
        r"(ಒತ್ತಡ|ಭಯ|ಆತಂಕ|ದುಃಖ|ಒಂಟಿ|ನಿದ್ದೆ\s*ಬರಲ್ಲ)",
    ],
}

# Bengali distress patterns
_BN_PATTERNS = {
    DistressLevel.CRISIS: [
        r"(আত্মহত্যা|মরে\s*যেতে\s*চাই|বেঁচে\s*থাকতে\s*চাই\s*না)",
    ],
    DistressLevel.MODERATE: [
        r"(চাপ|ভয়|উদ্বেগ|দুঃখ|একা|ঘুম\s*আসে\s*না)",
    ],
}

# Hinglish / Romanized Hindi
_HINGLISH_PATTERNS = {
    DistressLevel.CRISIS: [
        r"\b(marna\s*chahta|suicide|zindagi\s*khatam|jeene\s*ka\s*mann\s*nahi)\b",
    ],
    DistressLevel.SEVERE: [
        r"\b(bahut\s*(dukhi|udaas|akela)|koi\s*ummeed\s*nahi|sab\s*khatam)\b",
    ],
    DistressLevel.MODERATE: [
        r"\b(tension|tanav|pareshan|neend\s*nahi|ghabra|akela)\b",
        r"\b(dukhi|udaas|rona|gussa|darr)\b",
    ],
}

# Compile all patterns into a single lookup
_ALL_PATTERNS: dict[str, dict[DistressLevel, list[re.Pattern]]] = {}
for _name, _patterns in [
    ("en", _EN_PATTERNS),
    ("hi", _HI_PATTERNS),
    ("ta", _TA_PATTERNS),
    ("te", _TE_PATTERNS),
    ("kn", _KN_PATTERNS),
    ("bn", _BN_PATTERNS),
    ("hinglish", _HINGLISH_PATTERNS),
]:
    _ALL_PATTERNS[_name] = {
        level: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
        for level, patterns in _patterns.items()
    }


# ---------------------------------------------------------------------------
# Crisis resources by region
# ---------------------------------------------------------------------------

CRISIS_RESOURCES = {
    "global": "🆘 If you're in crisis: Please reach out for help.",
    "india": (
        "🆘 Crisis Helplines (India):\n"
        "• iCall: 9152987821\n"
        "• Vandrevala Foundation: 1860-2662-345\n"
        "• AASRA: 9820466726\n"
        "• Snehi: 044-24640050"
    ),
    "us": (
        "🆘 Crisis Helplines (US):\n"
        "• 988 Suicide & Crisis Lifeline: 988\n"
        "• Crisis Text Line: Text HOME to 741741"
    ),
    "uk": (
        "🆘 Crisis Helplines (UK):\n"
        "• Samaritans: 116 123\n"
        "• SHOUT: Text SHOUT to 85258"
    ),
}


# ---------------------------------------------------------------------------
# Graduated response templates
# ---------------------------------------------------------------------------

DISTRESS_RESPONSES = {
    DistressLevel.MILD: (
        "I sense you may be going through a challenging time. "
        "Remember, as Sri Preethaji teaches, every moment of discomfort "
        "is an invitation to deepen your awareness. "
        "Would you like to explore any specific teaching that might help? 🌱"
    ),
    DistressLevel.MODERATE: (
        "I hear you, and I want you to know that your feelings are completely valid. "
        "In moments like these, the teachings remind us that suffering is a doorway "
        "to transformation — not something to fight against, but to move through with awareness.\n\n"
        "Would you like me to guide you through a Serene Mind meditation? "
        "It can help you find some inner peace right now. 🙏"
    ),
    DistressLevel.SEVERE: (
        "I feel the depth of your pain, and I want you to know — you are not alone. "
        "Your feelings matter, and there is light even in the darkest moments.\n\n"
        "Sri Krishnaji says: 'When you stop running from your suffering and turn towards it "
        "with awareness, transformation begins.'\n\n"
        "I'd like to guide you through a calming Serene Mind meditation. "
        "Would you like to begin? 🌸\n\n"
        "If you need to speak with someone right away, please reach out:\n"
    ),
    DistressLevel.CRISIS: (
        "🙏 I care deeply about your wellbeing. Please know that you are valued, "
        "and there are people who want to help you right now.\n\n"
        "**Please reach out to a crisis helpline immediately:**\n"
    ),
}


# ---------------------------------------------------------------------------
# Serene Mind Engine
# ---------------------------------------------------------------------------

class SereneMindEngine:
    """
    Emotional intelligence engine for Mukthi Guru.

    Performs multi-language distress detection using:
    1. Keyword/pattern matching (fast, reliable baseline)
    2. Conversation history analysis (escalation detection)

    Future: Embedding-based semantic similarity for nuanced detection.
    """

    def __init__(self, embedding_service=None):
        """
        Initialize the Serene Mind Engine.

        Args:
            embedding_service: Optional embedding service for semantic distress detection.
                              If provided, enables semantic similarity-based detection.
        """
        self._embedder = embedding_service
        logger.info("Serene Mind Engine initialized")

    def assess_distress(
        self,
        message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> DistressAssessment:
        """
        Assess the distress level of a user message.

        Uses multi-language keyword patterns with conversation history context.

        Args:
            message: The user's message text
            conversation_history: Optional list of prior messages for escalation detection

        Returns:
            DistressAssessment with level, confidence, and recommended response type
        """
        message_lower = message.lower()
        signals = []
        max_level = DistressLevel.NONE
        max_confidence = 0.0

        # Scan across all language patterns
        for lang, levels in _ALL_PATTERNS.items():
            for level in sorted(levels.keys(), reverse=True):  # Check most severe first
                for pattern in levels[level]:
                    matches = pattern.findall(message_lower if lang in ("en", "hinglish") else message)
                    if matches:
                        signal_text = f"[{lang}] {matches[0]}"
                        signals.append(signal_text)
                        if level > max_level:
                            max_level = level
                            # Higher severity = higher confidence
                            max_confidence = min(0.5 + (level.value * 0.15), 1.0)

        # Escalation detection from conversation history
        if conversation_history and len(conversation_history) >= 2:
            recent_distress_count = sum(
                1 for msg in conversation_history[-6:]
                if msg.get("role") == "user" and self._quick_distress_check(msg.get("content", ""))
            )
            if recent_distress_count >= 2:
                # User has expressed distress multiple times — escalate
                if max_level < DistressLevel.MODERATE:
                    max_level = DistressLevel.MODERATE
                    max_confidence = max(max_confidence, 0.7)
                    signals.append("[escalation] Multiple distress signals in conversation")
                elif max_level == DistressLevel.MODERATE:
                    max_level = DistressLevel.SEVERE
                    max_confidence = max(max_confidence, 0.8)
                    signals.append("[escalation] Persistent distress pattern detected")

        # Map level to response type
        response_type_map = {
            DistressLevel.NONE: "normal",
            DistressLevel.MILD: "gentle",
            DistressLevel.MODERATE: "meditation",
            DistressLevel.SEVERE: "meditation",
            DistressLevel.CRISIS: "crisis",
        }

        # Detect language for response localization
        detected_lang = self._detect_language(message)

        assessment = DistressAssessment(
            level=max_level,
            confidence=max_confidence,
            detected_signals=signals,
            language_detected=detected_lang,
            recommended_response_type=response_type_map.get(max_level, "normal"),
        )

        if max_level > DistressLevel.NONE:
            logger.info(
                f"Serene Mind: Detected distress level={max_level.name}, "
                f"confidence={max_confidence:.2f}, signals={signals}, "
                f"lang={detected_lang}"
            )

        return assessment

    def get_response(self, assessment: DistressAssessment) -> str:
        """
        Get the appropriate response for a given distress assessment.

        Returns a compassionate, graduated response with crisis resources if needed.
        """
        if assessment.level == DistressLevel.NONE:
            return ""  # No distress response needed

        base_response = DISTRESS_RESPONSES.get(
            assessment.level,
            DISTRESS_RESPONSES[DistressLevel.MODERATE],
        )

        # For SEVERE and CRISIS, append crisis resources
        if assessment.level >= DistressLevel.SEVERE:
            base_response += "\n" + CRISIS_RESOURCES["india"]
            base_response += "\n" + CRISIS_RESOURCES["us"]

        return base_response

    def _quick_distress_check(self, text: str) -> bool:
        """Quick check if a message contains any distress signals (for history analysis)."""
        text_lower = text.lower()
        for lang, levels in _ALL_PATTERNS.items():
            for level, patterns in levels.items():
                if level >= DistressLevel.MODERATE:
                    for pattern in patterns:
                        if pattern.search(text_lower if lang in ("en", "hinglish") else text):
                            return True
        return False

    def _detect_language(self, text: str) -> str:
        """Simple heuristic language detection based on script."""
        # Check for Devanagari (Hindi, Marathi)
        if re.search(r'[\u0900-\u097F]', text):
            return "hi"
        # Tamil
        if re.search(r'[\u0B80-\u0BFF]', text):
            return "ta"
        # Telugu
        if re.search(r'[\u0C00-\u0C7F]', text):
            return "te"
        # Kannada
        if re.search(r'[\u0C80-\u0CFF]', text):
            return "kn"
        # Bengali
        if re.search(r'[\u0980-\u09FF]', text):
            return "bn"
        # Malayalam
        if re.search(r'[\u0D00-\u0D7F]', text):
            return "ml"
        # Gujarati
        if re.search(r'[\u0A80-\u0AFF]', text):
            return "gu"
        # Default: English
        return "en"
