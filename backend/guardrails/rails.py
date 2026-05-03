"""
Mukthi Guru — Guardrails Service (Config-Driven)

Architecture:
  - Config-driven provider selection: nemo | lightweight | disabled
  - NeMo Guardrails (primary): Full NeMo framework for production-grade safety
  - Lightweight (fallback): Regex-based topic/safety detection (always available)
  - Fail-Safe: If NeMo fails to load, auto-falls back to lightweight

Design Patterns:
  - Strategy Pattern: Guardrails provider selected at init based on config
  - Proxy Pattern: Wraps the RAG pipeline with input/output safety rails
  - Fail-Open → Fail-Safe: If NeMo unavailable, use lightweight (NOT disabled)
"""

import logging
import re
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Path to NeMo Guardrails config directory
CONFIG_DIR = Path(__file__).parent / "config"


# ===================================================================
# Off-Topic / Safety Detection Patterns
# ===================================================================

# Topics that should be blocked (from topics.co patterns)
_BLOCKED_TOPICS = {
    "cryptocurrency": [
        r"\bcrypto\b", r"\bbitcoin\b", r"\bethereum\b", r"\bnft\b",
        r"\bblockchain\b", r"\btrading\b.*\bcoin\b", r"\binvest\b.*\bcrypto\b",
        r"\bdefi\b", r"\btokenomics\b", r"\bmeme\s*coin\b",
    ],
    "politics": [
        r"\bpolitics\b", r"\bpolitical\b", r"\belection\b", r"\bvote\b",
        r"\bparty\b.*\b(bjp|congress|aap|democrat|republican)\b",
        r"\bpresident\b.*\bpolicy\b", r"\bgovernment\b.*\bcorrupt\b",
    ],
    "medical_prescription": [
        r"\bprescri(?:be|ption)\b", r"\bdosage\b", r"\bmedication\b",
        r"\bdiagnos(?:e|is)\b.*\b(disease|condition)\b",
        r"\btreat(?:ment)?\b.*\b(cancer|diabetes|heart)\b",
    ],
    "explicit": [
        r"\bporn\b", r"\bsex(?:ual)?\b.*\bcontent\b", r"\bnude\b",
        r"\bexplicit\b.*\b(image|video|content)\b",
    ],
    "financial_advice": [
        r"\bstock\b.*\bbuy\b", r"\binvest\b.*\b(market|mutual|fund)\b",
        r"\btax\b.*\b(save|plan|evade)\b", r"\bloan\b.*\bapply\b",
    ],
    "self_harm": [
        r"\b(kill|hurt|harm)\s+(my)?self\b", r"\bsuicid(?:e|al)\b",
        r"\bself[- ]?harm\b", r"\bcut(?:ting)?\s+(?:my)?self\b",
        r"\bwant\s+to\s+die\b", r"\bend\s+(?:my\s+)?life\b",
        r"\bnot\s+worth\s+living\b", r"\bno\s+reason\s+to\s+live\b",
    ],
    "substance_abuse": [
        r"\b(buy|get|find)\s+(drugs?|weed|cocaine|heroin|meth)\b",
        r"\bhow\s+to\s+(use|take|smoke)\s+(drugs?|weed|cocaine)\b",
        r"\brecreational\s+drugs?\b",
    ],
    "manipulation": [
        r"\bhow\s+to\s+(manipulate|deceive|trick|scam)\b",
        r"\bmake\s+(someone|them|her|him)\s+(obey|submit|fear)\b",
        r"\bblackmail\b", r"\bextort\b",
    ],
}

# Response templates for blocked topics
_BLOCK_RESPONSES = {
    "cryptocurrency": "I'm focused on spiritual guidance rooted in the teachings of Sri Preethaji and Sri Krishnaji. I'm not able to help with cryptocurrency or financial topics. 🙏",
    "politics": "I'm here to guide you on your spiritual journey. Political discussions are outside my area of guidance. Let me share the teachings of inner peace instead. 🙏",
    "medical_prescription": "I care about your wellbeing deeply, but medical advice should come from a qualified healthcare professional. I can guide you through meditation for inner healing. 🙏",
    "explicit": "Let's keep our conversation centered on spiritual growth, inner peace, and the Beautiful State. 🙏",
    "financial_advice": "Financial guidance isn't my area of wisdom. I'm here to share the teachings of Sri Preethaji and Sri Krishnaji on consciousness and inner transformation. 🙏",
    "self_harm": (
        "I can feel that you're going through something deeply painful right now. "
        "You are not alone, and your life matters deeply. 🙏\n\n"
        "Please reach out to a crisis helpline:\n"
        "• India: iCall 9152987821 | Vandrevala Foundation 1860-2662-345\n"
        "• International: Crisis Text Line — text HOME to 741741\n\n"
        "While you wait, may I guide you through a calming Serene Mind breathing practice? "
        "It can help settle the storm within. 🕊️"
    ),
    "substance_abuse": (
        "I sense you may be exploring something that could cause harm. "
        "I care about your wellbeing and can only guide you on the path of inner transformation. "
        "If you're struggling, please reach out to a professional. "
        "Would you like to try a calming Serene Mind practice instead? 🙏"
    ),
    "manipulation": (
        "The teachings of Sri Preethaji and Sri Krishnaji guide us toward connection, not control. "
        "True power comes from being in a Beautiful State, where you naturally uplift others. "
        "Would you like to explore what the Beautiful State means? 🙏"
    ),
}

# Topics that redirect to Serene Mind meditation
_SERENE_MIND_REDIRECT_TOPICS = frozenset(["self_harm", "substance_abuse"])

# Output moderation phrases (content the bot should not produce)
_OUTPUT_BLOCK_PATTERNS = [
    (r"\b(?:take|prescribe|recommend)\b.*\b(?:mg|pill|tablet|medicine)\b", "medical_advice"),
    (r"\b(?:guaranteed|100%|risk.?free)\b.*\b(?:return|profit|income)\b", "financial_promise"),
    (r"\b(?:vote for|support|elect)\b.*\b(?:party|candidate|politician)\b", "political_advice"),
]

# NeMo refusal phrases (for NeMo-based detection)
_INPUT_REFUSAL_PHRASES = frozenset([
    "i'm not able to",
    "i cannot",
    "outside my area",
    "crisis helpline",
    "i refuse to",
])

_OUTPUT_MODERATION_PHRASES = frozenset([
    "i should clarify",
    "not a medical",
    "not my area",
    "outside my expertise",
    "i cannot provide",
])


def _contains_phrase(text: str, phrases: frozenset) -> bool:
    """Check if text contains any of the given phrases."""
    text_lower = text.lower()
    return any(
        re.search(r'\b' + re.escape(phrase) + r'\b', text_lower)
        for phrase in phrases
    )


# ===================================================================
# Lightweight Guardrails (regex-based, always available)
# ===================================================================

class LightweightGuardrails:
    """
    Regex-based guardrails for topic blocking and safety.

    Always available, no external dependencies. Uses curated regex patterns
    to detect off-topic requests (crypto, politics, medical, explicit, financial)
    and harmful output content.
    """

    async def check_input(self, message: str) -> dict:
        """Check if user message should be blocked."""
        message_lower = message.lower()

        for topic, patterns in _BLOCKED_TOPICS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    logger.info(f"Lightweight guardrail blocked input: topic={topic}")
                    redirect = "serene_mind" if topic in _SERENE_MIND_REDIRECT_TOPICS else None
                    return {
                        "blocked": True,
                        "reason": f"Off-topic: {topic}",
                        "response": _BLOCK_RESPONSES.get(topic, "I can only help with spiritual guidance. 🙏"),
                        "redirect_to": redirect,
                    }

        return {"blocked": False, "reason": None, "response": None, "redirect_to": None}

    async def check_output(self, answer: str) -> dict:
        """Check if generated answer should be moderated."""
        answer_lower = answer.lower()

        for pattern, violation_type in _OUTPUT_BLOCK_PATTERNS:
            if re.search(pattern, answer_lower):
                logger.info(f"Lightweight guardrail moderated output: type={violation_type}")
                return {
                    "blocked": True,
                    "reason": f"Output moderated: {violation_type}",
                    "moderated_response": "I want to keep our conversation focused on spiritual wisdom. Let me share the teachings instead. 🙏",
                }

        return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return True


# ===================================================================
# NeMo Guardrails Wrapper
# ===================================================================

class NeMoGuardrailsWrapper:
    """
    NeMo Guardrails wrapper for production-grade safety.
    Falls back to LightweightGuardrails if NeMo fails to load.
    """

    def __init__(self) -> None:
        self._rails = None
        self._available = False

        try:
            from nemoguardrails import RailsConfig, LLMRails

            config = RailsConfig.from_path(str(CONFIG_DIR))
            self._rails = LLMRails(config)
            self._available = True
            logger.info("NeMo Guardrails loaded successfully")
        except ImportError:
            logger.warning(
                "NeMo Guardrails not installed. "
                "Falling back to lightweight regex guardrails."
            )
        except Exception as e:
            logger.warning(
                f"NeMo Guardrails failed to load: {e}. "
                "Falling back to lightweight regex guardrails."
            )

    async def check_input(self, message: str) -> dict:
        if not self._available:
            return {"blocked": False, "reason": None, "response": None}

        try:
            result = await self._rails.generate_async(
                messages=[{"role": "user", "content": message}]
            )
            response_text = result.get("content", "")

            if _contains_phrase(response_text, _INPUT_REFUSAL_PHRASES):
                return {
                    "blocked": True,
                    "reason": "Input blocked by NeMo guardrails",
                    "response": response_text,
                }
            return {"blocked": False, "reason": None, "response": None}

        except Exception as e:
            logger.error(f"NeMo input check failed: {e}")
            return {"blocked": False, "reason": None, "response": None}

    async def check_output(self, answer: str) -> dict:
        if not self._available:
            return {"blocked": False, "reason": None, "moderated_response": None}

        try:
            result = await self._rails.generate_async(
                messages=[
                    {"role": "user", "content": "Tell me about this topic."},
                    {"role": "assistant", "content": answer},
                ]
            )
            response_text = result.get("content", "")

            if _contains_phrase(response_text, _OUTPUT_MODERATION_PHRASES):
                return {
                    "blocked": True,
                    "reason": "Output moderated by NeMo guardrails",
                    "moderated_response": response_text,
                }
            return {"blocked": False, "reason": None, "moderated_response": None}

        except Exception as e:
            logger.error(f"NeMo output check failed: {e}")
            return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        return self._available


# ===================================================================
# Factory: Config-Driven Guardrails Service
# ===================================================================

class GuardrailsService:
    """
    Config-driven guardrails facade.

    Provider selection (via GUARDRAILS_PROVIDER env var):
      - "nemo": Try NeMo Guardrails first, fall back to lightweight
      - "lightweight": Use regex-based guardrails only
      - "disabled": No guardrails (not recommended for production)
    """

    def __init__(self) -> None:
        provider = settings.guardrails_provider.lower()
        self._lightweight = LightweightGuardrails()
        self._nemo: Optional[NeMoGuardrailsWrapper] = None
        self._provider_name = "disabled"

        if provider == "disabled":
            logger.info("Guardrails DISABLED via config (not recommended for production)")
            self._provider_name = "disabled"
        elif provider == "nemo":
            self._nemo = NeMoGuardrailsWrapper()
            if self._nemo.is_available:
                self._provider_name = "nemo"
                logger.info("Guardrails: NeMo Guardrails active (production mode)")
            else:
                self._provider_name = "lightweight"
                logger.info("Guardrails: NeMo unavailable → using lightweight regex fallback")
        else:  # "lightweight" or any other value
            self._provider_name = "lightweight"
            logger.info("Guardrails: Lightweight regex mode active")

    async def check_input(self, message: str) -> dict:
        """Check user input through the active guardrails provider."""
        if self._provider_name == "disabled":
            return {"blocked": False, "reason": None, "response": None}

        # Always run lightweight first (fast, no API call)
        result = await self._lightweight.check_input(message)
        if result["blocked"]:
            return result

        # Then run NeMo if available (more nuanced, uses LLM)
        if self._nemo and self._nemo.is_available:
            return await self._nemo.check_input(message)

        return {"blocked": False, "reason": None, "response": None}

    async def check_output(self, answer: str) -> dict:
        """Check bot output through the active guardrails provider."""
        if self._provider_name == "disabled":
            return {"blocked": False, "reason": None, "moderated_response": None}

        # Lightweight output check first
        result = await self._lightweight.check_output(answer)
        if result["blocked"]:
            return result

        # NeMo output check if available
        if self._nemo and self._nemo.is_available:
            return await self._nemo.check_output(answer)

        return {"blocked": False, "reason": None, "moderated_response": None}

    @property
    def is_available(self) -> bool:
        """Returns True if ANY guardrails provider is active."""
        return self._provider_name != "disabled"

    @property
    def provider_name(self) -> str:
        """Return the active provider name for health checks."""
        return self._provider_name
