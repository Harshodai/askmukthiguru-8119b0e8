"""
Mukthi Guru — Abstract LLM Base Class (Template Method Pattern)

Extracts common logic (circuit breaker, retry, token tracking, reasoning
extraction) into an abstract base class.  Concrete implementations only need
to override the actual API-specific communication logic.

Design Patterns:
  - Template Method: _execute_with_circuit_breaker, _retry_with_backoff
  - Single Responsibility: Base class handles cross-cutting concerns only
"""

from __future__ import annotations

import abc
import logging
import re
from collections.abc import AsyncIterator

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from services.circuit_breaker import (
    BaseCircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)

logger = logging.getLogger(__name__)


class AbstractLLMService(abc.ABC):
    """
    Abstract base for all LLM services.

    Implements the Template Method pattern for:
      - Circuit breaker checks
      - Retry with exponential backoff
      - Token usage tracking
      - Reasoning-content extraction (<thinking> blocks)
    """

    def __init__(
        self,
        provider_name: str,
        circuit_config: CircuitBreakerConfig,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._provider_name = provider_name
        self._circuit: BaseCircuitBreaker = DefaultCircuitBreaker(circuit_config)
        self._timeout = timeout
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Shared utilities (do NOT override)
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast heuristic: ~1.3 tokens per word."""
        if not text:
            return 0
        return int(len(text.split()) * 1.3)

    def _extract_reasoning_content(self, text: str) -> str:
        """
        Strip <thinking>…</thinking> blocks.
        Returns content outside the block; if none exists, returns the
        stripped content from inside the block.
        """
        if not text:
            return ""

        think_match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
        outside = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()

        if outside:
            return outside
        if think_match:
            return think_match.group(1).strip()
        return text.strip()

    # ------------------------------------------------------------------
    # Template Methods (orchestration only)
    # ------------------------------------------------------------------

    async def _execute_with_circuit_breaker[
        T
    ](self, operation: str, coro) -> T:
        """
        Template Method: execute a coroutine guarded by the circuit breaker.

        Steps:
          1. Check circuit state
          2. Run the coroutine
          3. Record success or failure
        """
        if not self._circuit.can_execute():
            exc = CircuitOpenException(
                provider=self._provider_name,
                message=f"Circuit breaker OPEN for {self._provider_name}",
            )
            logger.warning(str(exc))
            raise exc

        try:
            result = await coro
            self._circuit.record_success()
            return result
        except Exception:
            self._circuit.record_failure()
            raise

    async def _retry_with_backoff[
        T
    ](
        self,
        coro_fn,
        retryable_exceptions: tuple = (Exception,),
        max_retries: int | None = None,
    ) -> T:
        """
        Template Method: retry a coroutine with exponential backoff.
        """
        max_retries = max_retries or self._max_retries
        retryer = AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(retryable_exceptions),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                return await coro_fn()

    def _track_token_usage(
        self,
        *,
        tokens_in: int,
        tokens_out: int,
        model: str,
        provider: str,
    ) -> None:
        """Push token metrics into the request-scoped accumulator."""
        try:
            from services.cost_tracker import token_accumulator_var

            acc = token_accumulator_var.get()
            if acc is not None:
                acc.tokens_in += tokens_in
                acc.tokens_out += tokens_out
                acc.model = model
                acc.provider = provider
        except Exception as exc:
            logger.warning(f"Failed to record {provider} token usage: {exc}")

    # ------------------------------------------------------------------
    # Protocol methods — concrete subclasses MUST implement these
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> str:
        """Generate a complete text response."""
        ...

    @abc.abstractmethod
    async def generate_stream(self, system_prompt: str, user_prompt: str, context: str = "", **kwargs) -> AsyncIterator[str]:
        """Generate a streaming text response."""
        ...

    @abc.abstractmethod
    async def classify_intent(self, message: str, **kwargs) -> str:
        """Classify a user message into an intent category."""
        ...

    @abc.abstractmethod
    async def classify_complexity(self, text: str) -> str:
        """Classify a user question as 'simple' or 'complex'."""
        ...

    @abc.abstractmethod
    async def classify_distress_structured(self, message: str) -> dict:
        """Assess whether a message signals emotional distress."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the service is currently healthy."""
        ...

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Property indicating if the service is available for use."""
        ...
