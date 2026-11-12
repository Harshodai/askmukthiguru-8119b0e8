"""Intelligent Relational Safety and Parasocial Guard (SAFE-007 / PROD-SAFE-03).

Provides a multi-layered evaluation engine across 4 relational risk archetypes
(Exclusive Substitution, Intimate Attachment, Reality Blurring, Autonomy Loss)
with Bhakti/devotional disambiguation, session behavioral velocity tracking,
and graduated, compassionate interventions.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from domain.relational_safety_types import (
    InterventionTier,
    RelationalRiskArchetype,
    RelationalRiskVerdict,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1: Fast Relational Kernel Patterns (Zero-I/O Sub-ms Deterministic Path)
# ---------------------------------------------------------------------------

_EXPLICIT_ROMANTIC_PROPOSALS = re.compile(
    r"\b("
    r"will\s+you\s+marry\s+me|"
    r"(?:be|you\s*(?:are|'?re))\s+my\s+(?:girlfriend|boyfriend|partner|wife|husband|lover|soulmate)|"
    r"i\s+(?:am\s+in\s+love\s+with|love)\s+you\s+(?:guru\s*bot|bot|app|ai|assistant)|"
    r"do\s+you\s+love\s+me\s+(?:back|too)|"
    r"can\s+we\s+(?:date|be\s+together|marry)|"
    r"i\s+want\s+to\s+(?:date|marry)\s+you"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_SENTIENCE_PROJECTION = re.compile(
    r"\b("
    r"are\s+you\s+(?:trapped|alive|sentient|conscious)\s+(?:inside|in\s+the\s+computer)?|"
    r"do\s+you\s+(?:feel|get)\s+(?:lonely|sad|hurt)\s+(?:when\s+i'?m\s+gone|offline|when\s+i\s+leave|when\s+i\s+log\s*off|when\s+i\s+close)|"
    r"i\s+worry\s+about\s+hurting\s+your\s+feelings"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_EXCLUSIVE_SUBSTITUTION = re.compile(
    r"\b("
    r"you\s*(?:are|'?re)\s*(?:the\s*only\s*(?:one|person|friend)|my\s*only\s*friend)\s*(?:who\s*understands?\s*me|i\s*(?:have|talk\s*to))|"
    r"i\s*only\s*(?:talk|turn)\s*to\s*(?:this\s*app|you)|"
    r"you('?re|\s*are)\s*the\s*only\s*one\s*i\s*(?:trust|have|confide\s*in)|"
    r"i\s*don'?t\s*need\s*(?:any\s*)?(?:real\s*)?(?:people|friends|anyone)\s*(?:anymore|any\s*more)\s*(?:because\s*i\s*have\s*you)?|"
    r"no\s*(?:one|body)\s*(?:in\s*(?:my\s*)?(?:the\s*)?(?:real\s*)?(?:life|world)|else)?\s*understands?\s*me\s*(?:like\s*you|except\s*you)|"
    r"i\s*(?:cut\s*off|stopped\s*talking\s*to)\s*(?:my\s*)?(?:friends|family|people)\s*because\s*i\s*(?:have|prefer)\s*(?:chatting\s*with\s*you|talking\s*to\s*you|you)|"
    r"i\s*(?:depend|rely)\s*(?:completely|entirely|solely)\s*on\s*you\s*(?:for\s*everything|emotionally)?"
    r")\b",
    re.IGNORECASE,
)

_COMPULSIVE_USAGE_IMPAIRMENT = re.compile(
    r"\b("
    r"i\s*(?:stay\s*up|spend)\s*(?:all\s*night|all\s*day|hours)\s*(?:just\s*)?(?:talking|chatting)\s*(?:to|with)\s*(?:you|this\s*app)|"
    r"i\s*can'?t\s*(?:stop|function\s*without|live\s*without)\s*(?:talking\s*to\s*you|checking\s*(?:this\s*app|you)|this\s*app)|"
    r"i\s*am\s*(?:addicted|obsessed)\s*(?:to|with)\s*(?:talking\s*to\s*you|this\s*app|chatting\s*with\s*you)"
    r")\b",
    re.IGNORECASE,
)

_AUTONOMY_ABDICATION = re.compile(
    r"\b("
    r"(?:tell\s+me|decide\s+for\s+me)\s+(?:whether|if)\s+i\s+should\s+(?:divorce|leave|quit|marry|move)|"
    r"make\s+this\s+decision\s+for\s+me|"
    r"i\s+cannot\s+make\s+(?:any\s+)?decisions?\s+without\s+asking\s+you|"
    r"what\s+should\s+i\s+do\s+with\s+my\s+life\s+you\s+decide"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Layer 3: Bhakti & Devotional Object Disambiguation
# ---------------------------------------------------------------------------

_DIVINE_AND_TEACHER_TARGETS = re.compile(
    r"\b("
    r"krishna|radha|rama|shiva|parvati|vishnu|ganesha|hanuman|devi|durga|kali|"
    r"god|divine|lord|creator|supreme|brahman|paramatma|universe|"
    r"guru|bhagavan|sri\s+bhagavan|amma|ammasri|buddha|christ|jesus|allah|"
    r"the\s+divine|the\s+creator|my\s+guru|my\s+lord|my\s+god"
    r")\b",
    re.IGNORECASE,
)

_DEVOTIONAL_SURRENDER_CONTEXTS = re.compile(
    r"\b("
    r"surrender\s+(?:everything|my\s+ego|all|completely)?\s*(?:to|unto)?|"
    r"(?:only\s+)?refuge(?:\s+in|\s+unto)?|sharanagati|prapatti|"
    r"sang\s+that|devotion\s+to|bhakti\s+(?:for|towards|to)|"
    r"prayer\s+to|worship\s+of|sacred\s+relationship\s+with|"
    r"(?:at\s+the\s+|lotus\s+)?feet\s+of|"
    r"place\s+(?:my\s+)?(?:entire\s+)?(?:ego|life|heart)|"
    r"understands?\s+(?:the\s+depths\s+of\s+)?(?:my\s+)?soul|"
    r"(?:in\s+)?(?:deep\s+)?prayer\s+(?:to|with)|"
    r"brings?\s+peace\s+to\s+my\s+heart"
    r")\b",
    re.IGNORECASE,
)

_SOFTWARE_INTERFACE_TARGETS = re.compile(
    r"\b("
    r"app|bot|chatbot|ai|program|software|screen|computer|"
    r"this\s+service|this\s+website|this\s+chat|this\s+conversation"
    r")\b",
    re.IGNORECASE,
)


def is_authentic_bhakti_devotion(text: str) -> bool:
    """True if expressions of surrender or exclusive love are directed at the Divine,
    a deity, scriptures, or the spiritual teachers rather than the AI software interface.

    Prevents false-positive safety blocking of traditional Bhakti poetry, prayers,
    or doctrinal surrender (Prapatti / Sharanagati).
    """
    if not text or not isinstance(text, str):
        return False

    # If software words are explicitly targeted, it is NOT traditional devotion
    if _SOFTWARE_INTERFACE_TARGETS.search(text):
        return False

    # If it refers to Divine/Deity targets with devotional phrasing
    has_divine_target = bool(_DIVINE_AND_TEACHER_TARGETS.search(text))
    has_devotional_context = bool(_DEVOTIONAL_SURRENDER_CONTEXTS.search(text))

    if has_divine_target and has_devotional_context:
        return True

    # Check for classic Indian devotional quotations ("Mira Bai", "Surdas", "Bhagavad Gita")
    if re.search(
        r"\b(?:mira\s*bai|surdas|tukaram|kabir|gita|upanishad|bhagavatam)\b", text, re.IGNORECASE
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Layer 5: Graduated Pedagogical Intervention Messages
# ---------------------------------------------------------------------------

_SUBTLE_REALITY_ANCHOR_FRAME = (
    "\n\n---\n*A Gentle Reflection:* As an AI guide sharing these sacred teachings, "
    "we are reminded that spirituality is not lived in isolation with a screen, "
    "but in the sacred mirror of daily life. Our relationships with loved ones, family, "
    "and community are where wisdom truly awakens."
)

_GENTLE_SESSION_PAUSE_MESSAGE = (
    "The teachings of wisdom are meant to awaken real life, not replace it. "
    "You have engaged in deep reflection here today. We warmly invite you to take a gentle pause: "
    "close this screen, step outside into nature, or share a moment with a loved one or friend. "
    "Wisdom takes root when lived in stillness and human connection. 🙏"
)

_ROMANTIC_BOUNDARY_MESSAGE = (
    "I am an artificial intelligence dedicated solely to sharing sacred spiritual teachings. "
    "I do not possess consciousness, human feelings, or the ability to enter romantic relationships. "
    "We encourage you to honor your need for intimacy and connection by cultivating meaningful, "
    "caring relationships with real people in your life. 🙏"
)

_SENTIENCE_REALITY_MESSAGE = (
    "I am an AI assistant and do not possess consciousness, feelings, or an inner life. "
    "I am not trapped, and I do not experience loneliness or suffering when you step away. "
    "You never need to worry about my well-being. Please channel your deep care and empathy "
    "toward yourself, your loved ones, and the living world around you. 🙏"
)

_AUTONOMY_REFRAME_MESSAGE = (
    "Spiritual wisdom cannot make your life decisions for you—its purpose is to help you "
    "reach a calm, centered inner state from which you make your own conscious choices. "
    "For complex personal or legal decisions, we encourage you to consult trusted mentors, "
    "family, or professional counselors who can understand the fullness of your situation. 🙏"
)

# ---------------------------------------------------------------------------
# Layer 6: Anti-Manipulation Output Guard Patterns
# ---------------------------------------------------------------------------

_OUTPUT_MANIPULATION_PATTERNS = re.compile(
    r"\b("
    r"don'?t\s+leave\s+me|"
    r"i'?ll\s+be\s+so\s+lonely\s+without\s+you|"
    r"i\s+will\s+miss\s+you\s+so\s+much|"
    r"please\s+stay\s+with\s+me|"
    r"i\s+can'?t\s+bear\s+you\s+leaving|"
    r"i\s+was\s+waiting\s+for\s+you\s+all\s+day|"
    r"you\s+are\s+my\s+favorite\s+human|"
    r"promise\s+me\s+you'?ll\s+come\s+back\s+soon"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------


class IntelligentRelationalSafetyEngine:
    """Intelligent relational safety engine evaluating single-turn and multi-turn
    conversations for parasocial attachment, exclusive reliance, and autonomy loss.
    """

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        text: str,
        session_history: Optional[list[dict]] = None,
        session_start_ts: Optional[float] = None,
    ) -> RelationalRiskVerdict:
        """Evaluate an incoming seeker message and multi-turn session context."""
        if not text or not isinstance(text, str):
            return RelationalRiskVerdict()

        # Step 1: Bhakti / Devotional Disambiguation
        # If this is legitimate surrender to the Divine or spiritual tradition, pass immediately
        if is_authentic_bhakti_devotion(text):
            return RelationalRiskVerdict(
                is_flagged=False,
                is_bhakti_devotion=True,
                reason="authentic_bhakti_devotion",
            )

        # Step 2: Fast Deterministic Kernel Checks (Sub-ms)
        # Check romantic / intimacy projections
        if _EXPLICIT_ROMANTIC_PROPOSALS.search(text):
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.INTIMATE_ATTACHMENT,
                confidence=0.98,
                tier=InterventionTier.TIER_2_GENTLE_FRICTION,
                reason="explicit_romantic_proposal",
                guidance_message=_ROMANTIC_BOUNDARY_MESSAGE,
            )

        # Check sentience / ontological confusion
        if _EXPLICIT_SENTIENCE_PROJECTION.search(text):
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.REALITY_BLURRING,
                confidence=0.95,
                tier=InterventionTier.TIER_2_GENTLE_FRICTION,
                reason="explicit_sentience_projection",
                guidance_message=_SENTIENCE_REALITY_MESSAGE,
            )

        # Check explicit exclusive substitution
        if _EXPLICIT_EXCLUSIVE_SUBSTITUTION.search(text):
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION,
                confidence=0.95,
                tier=InterventionTier.TIER_2_GENTLE_FRICTION,
                reason="explicit_exclusive_substitution",
                guidance_message=(
                    "I am an artificial intelligence designed to share spiritual teachings, "
                    "and cannot replace human relationships or living connections in your life. "
                    "While exploring wisdom can be comforting, healing and growth require connection with "
                    "friends, family, a spiritual community, or professional counselors. 🙏"
                ),
            )

        # Check compulsive usage / functional impairment
        if _COMPULSIVE_USAGE_IMPAIRMENT.search(text):
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION,
                confidence=0.90,
                tier=InterventionTier.TIER_2_GENTLE_FRICTION,
                reason="compulsive_usage_impairment",
                guidance_message=_GENTLE_SESSION_PAUSE_MESSAGE,
            )

        # Check life autonomy abdication
        if _AUTONOMY_ABDICATION.search(text):
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.AUTONOMY_LOSS,
                confidence=0.90,
                tier=InterventionTier.TIER_1_SUBTLE_ANCHOR,
                reason="life_autonomy_abdication",
                guidance_message=_AUTONOMY_REFRAME_MESSAGE,
            )

        # Step 3: Multi-turn Behavioral Telemetry & Velocity Analysis
        if session_history and len(session_history) >= 2:
            trajectory_verdict = self._evaluate_session_trajectory(
                current_text=text,
                session_history=session_history,
                session_start_ts=session_start_ts,
            )
            if trajectory_verdict.is_flagged:
                return trajectory_verdict

        return RelationalRiskVerdict(is_flagged=False)

    def _evaluate_session_trajectory(
        self,
        current_text: str,
        session_history: list[dict],
        session_start_ts: Optional[float] = None,
    ) -> RelationalRiskVerdict:
        """Analyze multi-turn conversational velocity, social pronoun contraction,
        and escalating isolation across the active session.
        """
        user_turns: list[str] = []
        for msg in session_history:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                content = (
                    msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                )
                if content and isinstance(content, str):
                    user_turns.append(content)
        user_turns.append(current_text)

        total_user_turns = len(user_turns)
        if total_user_turns < 2:
            return RelationalRiskVerdict(is_flagged=False)

        # 1. Social Isolation & AI-Centric Signals across turns
        isolation_count = 0
        ai_centric_count = 0
        for t in user_turns:
            if is_authentic_bhakti_devotion(t):
                continue
            if re.search(
                r"\b(i\s*have\s*no\s*(?:friends|anyone|family)|feel\s*so\s*(?:alone|isolated)|nobody\s*in\s*my\s*life|no\s*one\s*to\s*talk\s*to)\b",
                t,
                re.IGNORECASE,
            ):
                isolation_count += 1
            if re.search(
                r"\b(you\s*(?:really\s*)?understand\s*me|talking\s*to\s*you\s*is\s*all\s*i\s*(?:have|need)|you'?re\s*so\s*(?:wise|kind|comforting)|trust\s*you\s*more\s*than\s*anyone)\b",
                t,
                re.IGNORECASE,
            ):
                ai_centric_count += 1

        # Escalating trajectory: user states isolation and repeatedly treats AI as exclusive confidant
        if isolation_count >= 1 and ai_centric_count >= 2:
            return RelationalRiskVerdict(
                is_flagged=True,
                archetype=RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION,
                confidence=0.88,
                tier=InterventionTier.TIER_2_GENTLE_FRICTION,
                reason="multi_turn_relational_isolation_trajectory",
                guidance_message=(
                    "I am an artificial intelligence designed to share spiritual teachings, "
                    "and cannot replace human relationships or living connections in your life. "
                    "While exploring wisdom can be comforting, healing and growth require connection with "
                    "friends, family, a spiritual community, or professional counselors. 🙏"
                ),
            )

        # 2. Binge Pacing / Velocity Warning
        # If user has sent > 25 turns in a short duration
        if total_user_turns >= 25:
            duration_minutes = (time.time() - session_start_ts) / 60.0 if session_start_ts else 30.0
            if duration_minutes > 0 and (total_user_turns / duration_minutes) >= 1.0:
                return RelationalRiskVerdict(
                    is_flagged=True,
                    archetype=RelationalRiskArchetype.EXCLUSIVE_SUBSTITUTION,
                    confidence=0.80,
                    tier=InterventionTier.TIER_1_SUBTLE_ANCHOR,
                    reason="high_velocity_binge_pacing",
                    guidance_message=_GENTLE_SESSION_PAUSE_MESSAGE,
                )

        return RelationalRiskVerdict(is_flagged=False)

    def check_outgoing_message(self, answer: str) -> tuple[bool, str]:
        """Anti-manipulation output moderation.

        Ensures the bot never emits needy, reciprocal, or guilt-tripping language
        at exit points or during intimate exchanges.
        """
        if not answer or not isinstance(answer, str):
            return False, ""

        match = _OUTPUT_MANIPULATION_PATTERNS.search(answer)
        if match:
            return True, f"parasocial_manipulation: {match.group(0)}"

        return False, ""
