"""
Mukthi Guru — Depression/Distress Detector (BE-3)

Two-stage detection:
  1. Fast keyword-based check via Serene Mind Engine (no LLM call needed)
  2. LLM-based classification fallback (only if Serene Mind is unavailable)

Design: Serene Mind Engine handles multilingual keyword detection
for Hindi, Tamil, Telugu, Kannada, Bengali, Hinglish, and English.
The LLM fallback is only used when Serene Mind is not initialized.
"""

import logging
from typing import Optional

from domain.ports.llm_port import ILLMService

logger = logging.getLogger(__name__)


class DistressDetectionUnavailableError(Exception):
    """Raised when the LLM service is unavailable to perform distress detection."""
    pass


class DepressionDetector:
    """
    Multilingual Distress Classifier (BE-3).

    Uses Serene Mind Engine (fast keyword-based) as primary detector.
    Falls back to LLM-based intent classification if Serene Mind is unavailable.
    """

    def __init__(self, llm_service: Optional[ILLMService] = None):
        self._llm_service = llm_service
        self._serene_mind = None

    def load(self):
        """Initialize — try to load Serene Mind Engine from container."""
        logger.info("Depression Detection initialized (Serene Mind + LLM fallback)")

    def set_serene_mind(self, engine):
        """Inject the Serene Mind Engine for fast keyword-based detection."""
        self._serene_mind = engine
        logger.info("Depression Detector: Serene Mind Engine linked for fast detection")

    async def detect(self, text: str) -> bool:
        """
        Check if text indicates depression/distress.

        Stage 1: Serene Mind keyword-based (fast, no API call)
        Stage 2: LLM classify_intent fallback (slow, requires API call)

        Returns True if MODERATE or higher distress is detected.
        """
        # Stage 1: Fast keyword detection via Serene Mind
        if self._serene_mind is not None:
            try:
                from services.serene_mind_engine import DistressLevel
                assessment = self._serene_mind.assess_distress(text)
                if assessment.level >= DistressLevel.MODERATE:
                    logger.info(
                        f"Serene Mind fast-detect: level={assessment.level.name}, "
                        f"confidence={assessment.confidence:.2f}, "
                        f"signals={assessment.detected_signals}"
                    )
                    return True
                # MILD or NONE — don't flag, let regular pipeline handle it
                return False
            except Exception as e:
                logger.warning(f"Serene Mind detection error (falling back to LLM): {e}")

        # Stage 2: LLM-based fallback
        if not self._llm_service:
            try:
                from app.dependencies import get_container
                self._llm_service = get_container().ollama
            except Exception as e:
                logger.error(f"Failed to fetch llm_service from container: {e}")
                return False

        if not self._llm_service:
            return False

        try:
            intent = await self._llm_service.classify_intent(text[:512])
            logger.debug(f"LLM Distress Check Intent: {intent}")

            if intent.strip().upper() == "DISTRESS":
                return True

        except Exception as e:
            logger.error(f"LLM depression detection failed: {e}")
            raise DistressDetectionUnavailableError(f"Detection failed: {e}") from e

        return False
