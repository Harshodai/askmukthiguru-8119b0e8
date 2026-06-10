"""Multi-Provider LLM Service with Circuit Breakers and Rate Limiting.

Provider stack (priority order):
1. Sarvam Cloud - Primary (best Indic language support, 60 RPM free tier)
2. OpenRouter - Fallback (200+ models, OpenAI-compatible)
3. Ollama Local - Emergency (self-hosted, zero latency, privacy)

Auto-failover with circuit breaker pattern (3 failures = open, 60s recovery).
Token bucket rate limiting per provider.
"""

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import aiohttp


class ProviderState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    state: ProviderState = ProviderState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = ProviderState.OPEN

    def record_success(self):
        self.failure_count = 0
        self.state = ProviderState.CLOSED

    def can_try(self) -> bool:
        if self.state == ProviderState.CLOSED:
            return True
        if self.state == ProviderState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = ProviderState.HALF_OPEN
                return True
            return False
        return True


class TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now


@dataclass
class ProviderConfig:
    name: str
    api_key_env: str
    base_url: str
    models: list[str]
    default_model: str
    rpm: int
    timeout: float = 30.0
    max_retries: int = 2


class MultiProviderLLMService:
    """LLM service with multi-provider failover."""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._init_session = False

        self.providers = {
            "sarvam": ProviderConfig(
                name="Sarvam Cloud",
                api_key_env="SARVAM_API_KEY",
                base_url="https://api.sarvam.ai/v1",
                models=["arya-1.2-8b", "arya-1.2-24b"],
                default_model="arya-1.2-8b",
                rpm=60,
                timeout=30.0,
            ),
            "openrouter": ProviderConfig(
                name="OpenRouter",
                api_key_env="OPENROUTER_API_KEY",
                base_url="https://openrouter.ai/api/v1",
                models=["google/gemini-flash-1.5-8b", "mistralai/mixtral-8x7b-instruct", "gpt-4o-mini"],
                default_model="google/gemini-flash-1.5-8b",
                rpm=200,
                timeout=30.0,
            ),
            "ollama": ProviderConfig(
                name="Ollama Local",
                api_key_env="OLLAMA_API_KEY",
                base_url="http://host.docker.internal:11434/v1",
                models=["gemma2:2b", "llama3.2:3b"],
                default_model="gemma2:2b",
                rpm=999,
                timeout=60.0,
            ),
        }

        self.circuit_breakers = {
            name: CircuitBreaker(name=name) for name in self.providers
        }

        self.rate_limiters = {
            name: TokenBucket(rate=cfg.rpm / 60.0, capacity=max(1, cfg.rpm // 10))
            for name, cfg in self.providers.items()
        }

        self._provider_priority = ["sarvam", "openrouter", "ollama"]

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._init_session:
            self.session = aiohttp.ClientSession()
            self._init_session = True
        return self.session

    def _get_api_key(self, provider: str) -> Optional[str]:
        env_var = self.providers[provider].api_key_env
        return os.environ.get(env_var) or os.environ.get(env_var.lower())

    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate completion with auto-failover across providers."""
        session = await self._get_session()

        if provider:
            return await self._try_provider(
                session, provider, model, prompt, max_tokens, temperature
            )

        last_error = None
        for p in self._provider_priority:
            if not self.circuit_breakers[p].can_try():
                continue
            if not self.rate_limiters[p].consume():
                continue
            try:
                return await self._try_provider(
                    session, p, model, prompt, max_tokens, temperature
                )
            except Exception as e:
                self.circuit_breakers[p].record_failure()
                last_error = e

        raise RuntimeError(f"All providers failed: {last_error}")

    async def _try_provider(
        self,
        session: aiohttp.ClientSession,
        provider: str,
        model: Optional[str],
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        cfg = self.providers[provider]
        api_key = self._get_api_key(provider)
        use_model = model or cfg.default_model

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://askmukthiguru.com"
            headers["X-Title"] = "Mukthi Guru"

        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with session.post(
            f"{cfg.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=cfg.timeout),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"{cfg.name} error {resp.status}: {text}")
            data = await resp.json()
            self.circuit_breakers[provider].record_success()

            return {
                "provider": provider,
                "model": use_model,
                "content": data["choices"][0]["message"]["content"],
                "finish_reason": data["choices"][0].get("finish_reason", "stop"),
                "usage": data.get("usage", {}),
            }

    async def close(self):
        if self.session:
            await self.session.close()

    def get_provider_status(self) -> dict[str, dict]:
        return {
            name: {
                "state": self.circuit_breakers[name].state.value,
                "failures": self.circuit_breakers[name].failure_count,
                "tokens": self.rate_limiters[name].tokens,
                "model": self.providers[name].default_model,
            }
            for name in self._provider_priority
        }


_singleton: Optional[MultiProviderLLMService] = None


def get_llm_service() -> MultiProviderLLMService:
    global _singleton
    if _singleton is None:
        _singleton = MultiProviderLLMService()
    return _singleton