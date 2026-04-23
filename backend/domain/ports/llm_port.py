from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List

class ILLMService(ABC):
    """
    Abstract Port for LLM Services to decouple the business logic from 
    specific providers like Ollama or Sarvam Cloud.
    """
    @abstractmethod
    def invoke(self, messages: List[Dict[str, str]], **kwargs) -> Any:
        pass
        
    @abstractmethod
    async def ainvoke(self, messages: List[Dict[str, str]], **kwargs) -> Any:
        pass
        
    @abstractmethod
    async def classify_intent(self, text: str) -> str:
        """Classify user intent (e.g., DISTRESS, QUERY, CASUAL) supporting multilingual text."""
        pass
        
    @abstractmethod
    async def get_fast_model(self) -> Any:
        """Return the model configuration optimized for speed/classification."""
        pass
        
    @abstractmethod
    async def get_main_model(self) -> Any:
        """Return the heavy model optimized for Generation/RAG."""
        pass
