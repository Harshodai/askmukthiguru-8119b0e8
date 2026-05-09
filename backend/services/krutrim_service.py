"""Krutrim AI integration as alternative/fallback LLM provider."""

import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class KrutrimService:
    """
    Krutrim Pro integration — supports 22 Indian languages.
    Used as:
    - Primary for certain languages Krutrim handles better
    - Fallback if Sarvam is unavailable
    - A/B testing alternative
    """
    
    def __init__(self):
        self._api_key = settings.krutrim_api_key or ""
        self._base_url = "https://api.krutrim.com/v1"
        self._model = "krutrim-pro-v1"
    
    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        if not self._api_key:
            raise ValueError("Krutrim API key not configured")
            
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                raise Exception(f"Krutrim API error: {resp.status_code} — {resp.text[:200]}")
