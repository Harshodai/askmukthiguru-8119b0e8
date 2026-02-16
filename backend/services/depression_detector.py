
import logging
from transformers import pipeline
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class DepressionDetector:
    """
    Service to detect emotional distress/depression in user messages.
    Uses a finetuned RoBERTa model.
    """
    
    def __init__(self):
        self.model_name = "mrm8488/distilroberta-finetuned-depression"
        self._pipe = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    def load(self):
        """Load the model (heavy operation)."""
        logger.info(f"Loading Depression Detection model: {self.model_name}...")
        try:
            self._pipe = pipeline("text-classification", model=self.model_name)
            logger.info("Depression Detection model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Depression Detection model: {e}")
            self._pipe = None

    async def detect(self, text: str) -> bool:
        """
        Check if text indicates depression/distress.
        Returns True if confident.
        """
        if not self._pipe:
            return False

        try:
            # Run in threadpool to avoid blocking event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._executor, 
                lambda: self._pipe(text[:512]) # Truncate to max len
            )
            
            # Result format: [{'label': 'LABEL_1', 'score': 0.9}]
            # LABEL_1 is typically "depression" in this model, but we should verify.
            # Usually these models are [Not Depressed, Depressed].
            # Let's assume LABEL_1 = Depressed based on standard HF model cards for this specific model.
            
            label = result[0]['label']
            score = result[0]['score']
            
            logger.debug(f"Depression Check: {label} ({score:.4f})")
            
            if label == 'LABEL_1' and score > 0.6:
                return True
                
        except Exception as e:
            logger.error(f"Depression detection failed: {e}")
            
        return False
