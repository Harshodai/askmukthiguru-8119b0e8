import logging
from typing import Optional

# We dynamically import the port to avoid circular dependencies if needed
from domain.ports.llm_port import ILLMService

logger = logging.getLogger(__name__)

class DepressionDetector:
    """
    Multilingual Distress Classifier (BE-3).
    Replaces heavy local Transformers model with lightweight, 
    multilingual intent classification via the LLM API.
    """
    
    def __init__(self, llm_service: Optional[ILLMService] = None):
        self._llm_service = llm_service

    def load(self):
        """No heavy model needed anymore as we use the abstracted LLM service."""
        logger.info("Depression Detection initialized (LLM-based Multilingual Engine)")

    async def detect(self, text: str) -> bool:
        """
        Check if text indicates depression/distress using LLM intent classification.
        Supports standard English and mixed/Indian languages interchangeably.
        Returns True if confident distress is detected.
        """
        if not self._llm_service:
            # Fallback to container injected service
            try:
                from app.dependencies import get_container
                self._llm_service = get_container().llm_service
            except Exception as e:
                logger.error(f"Failed to fetch llm_service from container for distress detection: {e}")
                return False
                
        if not self._llm_service:
            return False

        try:
            # Call abstract classify endpoint
            intent = await self._llm_service.classify_intent(text[:512])
            logger.debug(f"LLM Multilingual Distress Check Intent: {intent}")
            
            if "DISTRESS" in intent.upper():
                return True
                
        except Exception as e:
            logger.error(f"Multilingual depression detection failed: {e}")
            
        return False
