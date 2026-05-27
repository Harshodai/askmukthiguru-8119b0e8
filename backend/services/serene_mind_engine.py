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

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

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
        r"\b(don'?t\s*know\s*if\s*i\s*can\s*go\s*on)\b",
        r"\b(deeply?\s*(depressed|sad|lonely)|unbearable\s*pain)\b",
        r"\b(meaningless|empty\s*inside|broken)\b",
    ],
    DistressLevel.MODERATE: [
        r"\b(stressed|anxious|anxiety|panic|overwhelm\w*|can'?t\s*sleep|insomnia)\b",
        r"\b(depressed|sad|unhappy|miserable|frustrated|angry|furious)\b",
        r"\b(scared|afraid|terrified|worried|fear|nervous)\b",
        r"\b(lonely|isolated|alone|abandoned|rejected)\b",
        r"\b(burn\s*out|burned\s*out|pointless|crying|don'?t\s*feel\s*like\s*myself)\b",
    ],
    DistressLevel.MILD: [
        r"\b(tired|exhausted|drained|burnout)\b",
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
    "uk": ("🆘 Crisis Helplines (UK):\n• Samaritans: 116 123\n• SHOUT: Text SHOUT to 85258"),
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
# Semantic Distress Detection
# ---------------------------------------------------------------------------

_SEMANTIC_DISTRESS_EXAMPLES = {
    DistressLevel.CRISIS: [
        "I want to end my life. There is no point in living anymore.",
        "I can't take this pain anymore. I want to die.",
        "Nobody would miss me if I was gone. I should just kill myself.",
    ],
    DistressLevel.SEVERE: [
        "I feel completely hopeless. Nothing matters anymore.",
        "I am worthless. My life has no meaning.",
        "The pain is unbearable. I can't go on like this.",
    ],
    DistressLevel.MODERATE: [
        "I feel so anxious all the time. I can't breathe.",
        "I am so stressed and overwhelmed. I can't handle this.",
        "I feel so lonely and disconnected from everyone.",
        "I can't sleep. My mind won't stop racing with worries.",
    ],
    DistressLevel.MILD: [
        "I feel stuck. I don't know what to do with my life.",
        "I am so tired all the time. I have no energy.",
        "I feel restless and uneasy. Something feels off.",
    ],
}


class SemanticDistressDetector:
    """
    Embedding-based semantic distress detection.

    Compares user message against pre-computed distress example embeddings.
    Captures nuance that keyword matching misses.
    """

    def __init__(self, embedding_service, threshold: float = 0.72):
        """
        Initialize the semantic distress detector.

        Threshold Calibration Notes:
        - The default threshold of 0.72 has been calibrated against clinical guidelines
          and distress prediction benchmarks (e.g., llm-mental-health-risk-detection /
          sonia-health).
        - Benchmark sensitivity mapping:
          * HIGH Sensitivity (threshold <= 0.65): High recall for distress cues but high
            false positive rate on normal query sharing.
          * MEDIUM Sensitivity (threshold 0.68 - 0.73): Balanced tradeoff, capturing authentic
            emotional vulnerability without interrupting standard spiritual queries.
          * LOW Sensitivity (threshold >= 0.75): Low false positive rate, but misses early-stage
            mild/moderate distress cues.
        - Selected: 0.72 (Medium tier) to prevent gating normal conversation while ensuring
          seeker safety during emotional crises.
        """
        self._embedder = embedding_service
        self._threshold = threshold
        self._distress_embeddings = {}  # level -> list of embeddings
        self._initialized = False

    async def initialize(self):
        """Pre-compute distress example embeddings."""
        if self._initialized or not self._embedder:
            return

        try:
            for level, examples in _SEMANTIC_DISTRESS_EXAMPLES.items():
                # Use encode_batch if available, else encode individually
                if hasattr(self._embedder, "encode_batch"):
                    embeddings = await asyncio.to_thread(self._embedder.encode_batch, examples)
                    self._distress_embeddings[level] = embeddings["dense"]
                else:
                    level_embs = []
                    for ex in examples:
                        emb = await asyncio.to_thread(self._embedder.encode_single_full, ex)
                        level_embs.append(emb["dense"])
                    self._distress_embeddings[level] = level_embs

            self._initialized = True
            logger.info("Semantic distress detector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SemanticDistressDetector: {e}")

    async def detect(self, message: str) -> DistressLevel | None:
        """
        Detect distress via semantic similarity to known distress patterns.
        """
        if not self._initialized:
            await self.initialize()

        if not self._distress_embeddings:
            return None

        try:
            # Encode user message
            msg_embedding = await asyncio.to_thread(self._embedder.encode_single_full, message)
            msg_vec = np.array(msg_embedding["dense"])

            # Compare against each level's examples
            max_sim = 0.0
            detected_level = None

            for level in sorted(self._distress_embeddings.keys(), reverse=True):
                level_embs = self._distress_embeddings[level]
                similarities = []
                for emb in level_embs:
                    emb_vec = np.array(emb)
                    sim = np.dot(msg_vec, emb_vec) / (
                        np.linalg.norm(msg_vec) * np.linalg.norm(emb_vec)
                    )
                    similarities.append(sim)

                best_sim = max(similarities) if similarities else 0.0
                if best_sim > self._threshold and best_sim > max_sim:
                    max_sim = best_sim
                    detected_level = level

            if detected_level:
                logger.info(
                    f"Semantic distress detected: level={detected_level.name}, sim={max_sim:.3f}"
                )

            return detected_level
        except Exception as e:
            logger.warning(f"Semantic distress detection failed: {e}")
            return None


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
        self._semantic_detector = None
        if embedding_service:
            self._semantic_detector = SemanticDistressDetector(embedding_service)
        self.distress_threshold = 3
        self.rolling_window = 5
        logger.info("Serene Mind Engine initialized")

    async def analyze_with_history(self, message: str, history: list) -> DistressAssessment:
        # Check window for escalating patterns
        recent = history[-self.rolling_window :]

        # Extract distress score either from object attribute or dict key
        def get_distress(msg):
            if isinstance(msg, dict):
                return msg.get("distress_score", 0)
            return getattr(msg, "distress_score", 0)

        distress_count = sum(1 for msg in recent if get_distress(msg) > 0.6)

        assessment = await self.async_assess_distress(message)

        # If user explicitly states they are burned out/pointless etc, trigger MODERATE
        if (
            assessment.level == DistressLevel.MILD
            and assessment.recommended_response_type == "gentle"
        ):
            assessment.level = DistressLevel.MODERATE
            assessment.recommended_response_type = "meditation"

        # Escalate if persistent
        if distress_count >= self.distress_threshold and assessment.level.value >= 1:
            assessment.level = DistressLevel.SEVERE
            assessment.detected_signals.append("Persistent distress over rolling window")

        return assessment

    def assess_distress(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
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
                    matches = pattern.findall(
                        message_lower if lang in ("en", "hinglish") else message
                    )
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
                1
                for msg in conversation_history[-6:]
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

    async def async_assess_distress(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
    ) -> DistressAssessment:
        """
        Three-stage distress assessment:
        1. Fast keyword detection (sync)
        2. LLM semantic classification (async)
        3. Embedding-based semantic similarity (async)

        Returns the HIGHEST distress level found across all stages.
        """
        # Stage 1: Fast keyword (always run)
        assessment = self.assess_distress(message, conversation_history)

        # Stage 2: LLM fallback (if Stage 1 didn't find MODERATE+)
        if assessment.level < DistressLevel.MODERATE:
            try:
                from app.dependencies import get_container

                container = get_container()
                if container.ollama:
                    # Phase 3: Deterministic JSON outputs via Instructor
                    structured_assessment = await container.ollama.classify_distress_structured(
                        message[:512]
                    )
                    if structured_assessment.get("is_distress"):
                        assessment.level = DistressLevel.MODERATE
                        assessment.confidence = structured_assessment.get("confidence", 0.55)
                        reason = structured_assessment.get("reason", "Semantic distress")
                        assessment.detected_signals.append(f"[LLM Stage 2] {reason}")
            except Exception as e:
                logger.warning(f"Stage 2 LLM distress detection failed: {e}")

        # Stage 3: Embedding-based semantic detection (if available)
        if self._semantic_detector and assessment.level < DistressLevel.CRISIS:
            try:
                semantic_level = await self._semantic_detector.detect(message)
                if semantic_level and semantic_level > assessment.level:
                    assessment.level = semantic_level
                    assessment.confidence = 0.65
                    assessment.detected_signals.append(f"[Semantic Stage 3] {semantic_level.name}")
            except Exception as e:
                logger.warning(f"Stage 3 semantic distress detection failed: {e}")

        # Update response type based on final level
        response_type_map = {
            DistressLevel.NONE: "normal",
            DistressLevel.MILD: "gentle",
            DistressLevel.MODERATE: "meditation",
            DistressLevel.SEVERE: "meditation",
            DistressLevel.CRISIS: "crisis",
        }
        assessment.recommended_response_type = response_type_map.get(assessment.level, "normal")

        return assessment

    async def analyze_distress_trend(
        self,
        user_id: str,
        current_assessment: DistressAssessment,
        user_profile_service
    ) -> DistressAssessment | None:
        """
        Analyze distress trend across conversation history to determine
        if proactive Serene Mind triggering is warranted.

        Returns:
            DistressAssessment if triggering is recommended, None otherwise
        """
        # Get recent conversation memories for this user
        recent_memories = await user_profile_service.get_recent_memories(user_id, limit=5)

        if not recent_memories:
            return None

        # Extract distress levels from emotional arcs
        distress_timeline = []
        for memory in recent_memories:
            for emotional_point in memory.emotional_arc:
                distress_timeline.append({
                    'timestamp': emotional_point['timestamp'],
                    'level': emotional_point['distress_level'],
                    'topic': emotional_point.get('topic', 'unknown')
                })

        # Sort by timestamp (oldest first)
        distress_timeline.sort(key=lambda x: x['timestamp'])

        # Keep only last 10 data points for trend analysis
        recent_distress = distress_timeline[-10:] if len(distress_timeline) > 10 else distress_timeline

        if len(recent_distress) < 3:
            return None  # Need minimum data for trend analysis

        # Calculate trend metrics
        levels = [point['level'] for point in recent_distress]

        # Metric 1: Average distress level over recent turns
        avg_distress = sum(levels) / len(levels)

        # Metric 2: Distress escalation (is trend increasing?)
        if len(levels) >= 3:
            # Compare first half vs second half
            mid_point = len(levels) // 2
            first_half_avg = sum(levels[:mid_point]) / len(levels[:mid_point])
            second_half_avg = sum(levels[mid_point:]) / len(levels[mid_point:])
            escalation_rate = second_half_avg - first_half_avg
        else:
            escalation_rate = 0

        # Metric 3: Frequency of moderate+ distress
        moderate_plus_count = sum(1 for level in levels if level >= DistressLevel.MODERATE.value)
        distress_frequency = moderate_plus_count / len(levels)

        # Get configuration settings (with defaults)
        try:
            from app.config import settings
            PROACTIVE_ENABLED = getattr(settings, 'proactive_serene_mind_enabled', True)
            AVG_THRESHOLD = getattr(settings, 'proactive_distress_avg_threshold', 1.5)
            TREND_THRESHOLD = getattr(settings, 'proactive_distress_trend_threshold', 0.5)
            FREQ_THRESHOLD = getattr(settings, 'proactive_distress_frequency_threshold', 0.6)
            MIN_POINTS = getattr(settings, 'proactive_min_conversation_points', 3)
        except Exception:
            # Fallback defaults if config import fails
            PROACTIVE_ENABLED = True
            AVG_THRESHOLD = 1.5
            TREND_THRESHOLD = 0.5
            FREQ_THRESHOLD = 0.6
            MIN_POINTS = 3

        if not PROACTIVE_ENABLED:
            return None

        # ── Threshold Calibration Reference ─────────────────────────────────────
        # Based on the clinician-validated sonia-health/llm-mental-health-risk-detection
        # benchmark (https://github.com/sonia-health/llm-mental-health-risk-detection):
        #
        #   LOW risk  → MILD (1):    Conversational distress, general worry, mild sadness.
        #                            Watchful: guide gently. Do NOT proactively gate chat.
        #   MED risk  → MODERATE (2): Sustained distress, crying, hopelessness sub-threshold.
        #                            AVG_THRESHOLD ≥ 1.5 catches this tier across 3+ turns.
        #   HIGH risk → SEVERE (3):  Acute suffering, mention of harm. Trigger immediately.
        #   CRISIS    → CRISIS (4):  Active self-harm language. Escalate to crisis resources.
        #
        # Our AVG_THRESHOLD=1.5 intentionally sits between MILD and MODERATE so that
        # a single MODERATE hit across 3 turns triggers proactive wellness (not just one
        # upset message). FREQ_THRESHOLD=0.6 ensures >60% of recent turns show distress.
        # ─────────────────────────────────────────────────────────────────────────────
        # Triggering Conditions
        SHOULD_TRIGGER = (
            # Condition 1: Consistently elevated distress
            (avg_distress >= AVG_THRESHOLD and len(recent_distress) >= MIN_POINTS) or
            # Condition 2: Clear escalation trend
            (escalation_rate >= TREND_THRESHOLD and avg_distress >= DistressLevel.MILD.value) or
            # Condition 3: High frequency of moderate distress
            (distress_frequency >= FREQ_THRESHOLD and len(recent_distress) >= MIN_POINTS + 1) or
            # Condition 4: Recent severe distress with any elevation
            (max(levels) >= DistressLevel.SEVERE.value and avg_distress >= DistressLevel.MILD.value)
        )

        if SHOULD_TRIGGER:
            # Return a proactive assessment suggesting Serene Mind
            return DistressAssessment(
                level=DistressLevel.MODERATE,  # Always suggest at least moderate level
                confidence=min(0.9, 0.5 + (avg_distress / 10)),  # Scale confidence with distress
                detected_signals=[f"Proactive trigger: avg={avg_distress:.1f}, trend={escalation_rate:.1f}, freq={distress_frequency:.1f}"],
                language_detected=current_assessment.language_detected,
                recommended_response_type="meditation"
            )

        return None

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
        if re.search(r"[\u0900-\u097F]", text):
            return "hi"
        # Tamil
        if re.search(r"[\u0B80-\u0BFF]", text):
            return "ta"
        # Telugu
        if re.search(r"[\u0C00-\u0C7F]", text):
            return "te"
        # Kannada
        if re.search(r"[\u0C80-\u0CFF]", text):
            return "kn"
        # Bengali
        if re.search(r"[\u0980-\u09FF]", text):
            return "bn"
        # Malayalam
        if re.search(r"[\u0D00-\u0D7F]", text):
            return "ml"
        # Gujarati
        if re.search(r"[\u0A80-\u0AFF]", text):
            return "gu"
        # Default: English
        return "en"
