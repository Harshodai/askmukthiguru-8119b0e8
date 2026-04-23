from abc import ABC, abstractmethod
from typing import Optional

class ICacheRepository(ABC):
    \"\"\"Abstract port for response caching (BE-6).\"\"\"
    
    @abstractmethod
    def get(self, query: str) -> Optional[dict]:
        \"\"\"Retrieve cached response payload by query key.\"\"\"
        pass
        
    @abstractmethod
    def put(self, query: str, response: str, intent: str, citations: list[str], meditation_step: int = 0) -> None:
        \"\"\"Store a newly generated response payload in the cache.\"\"\"
        pass
        
    @abstractmethod
    def invalidate_all(self) -> None:
        \"\"\"Invalidate the entire cache when new data is ingested.\"\"\"
        pass
