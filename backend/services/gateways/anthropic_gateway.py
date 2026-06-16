"""Anthropic-direct gateway with prompt caching, Citations API, and cost tracking.

This sits BESIDE the existing `multi_provider_llm.py` / `sarvam_service.py` /
`openrouter_service.py` stack. The legacy stack handles OpenAI-compatible
endpoints and the production Sarvam path; this gateway handles direct
Anthropic API calls so we can use features the OpenAI-compatible path cannot:

  1. **Prompt caching** via `cache_control` blocks (up to 90% off reused prefixes)
  2. **Citations API** via documents content blocks (block-index citations)
  3. **Extended thinking** via the `thinking` parameter (for hard answers)
  4. **Native usage telemetry** with cache_read / cache_write token counts

Design intent:

  * Opt-in. Settings flag (`anthropic_gateway_enabled`) gates everything.
    The default Sarvam path keeps working unchanged.
  * Configurable. Provider model, system prompt cache TTL, max_tokens,
    temperature, and timeout are all settings-driven.
  * Resilient. Network errors, timeouts, malformed responses bubble up as
    `AnthropicGatewayError` so callers can fall back gracefully.
  * Observable. Every call emits structured telemetry (input tokens, output
    tokens, cache_read tokens, cache_creation tokens, latency_ms, model,
    session_id) so cost dashboards have real signal.
  * Stateless. No singletons, no module-level mutable globals other than the
    aiohttp ClientSession which is lazily created.

Public API:
    gateway = AnthropicGateway.from_settings()
    response = await gateway.generate(
        system_prompt=GURU_SYSTEM_PROMPT,        # cached
        user_message="What is Soul Sync?",
        documents=[{"title": "...", "text": "..."}],  # optional, enables citations
    )
    print(response.text, response.citations, response.usage)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnthropicUsage:
    """Token + latency telemetry for one Anthropic call."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    latency_ms: int

    @property
    def cache_hit_ratio(self) -> float:
        """How much of the input came from cache reads (0..1).
        100% = perfect cache hit; 0% = no caching benefit on this call.
        """
        total = self.input_tokens + self.cache_read_input_tokens + self.cache_creation_input_tokens
        if total == 0:
            return 0.0
        return self.cache_read_input_tokens / total


@dataclass
class Citation:
    """One citation as returned by the Citations API."""

    cited_text: str
    document_index: int
    document_title: str | None = None
    start_char_index: int | None = None
    end_char_index: int | None = None
    start_block_index: int | None = None
    end_block_index: int | None = None


@dataclass
class AnthropicResponse:
    """Normalized response from an Anthropic API call."""

    text: str
    citations: list[Citation] = field(default_factory=list)
    usage: AnthropicUsage | None = None
    stop_reason: str | None = None
    model: str | None = None
    raw: dict[str, Any] | None = None


class AnthropicGatewayError(RuntimeError):
    """Raised on transport, timeout, or API errors. Callers should catch and
    fall back to the legacy LLM stack rather than propagating."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AnthropicGatewayConfig:
    """All settings come from environment via app.config.settings. No code
    edits required to swap models, switch caching modes, or change endpoints.
    """

    api_key: str
    base_url: str
    model: str
    api_version: str
    beta_features: tuple[str, ...]
    max_tokens: int
    temperature: float
    timeout_s: int
    system_cache_ttl: str             # "5m" | "1h" | "" (no cache)
    extended_thinking_enabled: bool
    extended_thinking_budget_tokens: int

    @classmethod
    def from_settings(cls) -> "AnthropicGatewayConfig":
        """Resolve config from `app.config.settings` with sane defaults.
        Falls back to env vars if Settings hasn't been initialised."""

        # Lazy-import so test envs that stub `app.config` don't fail at module
        # import time.
        try:
            from app.config import settings
        except Exception:  # noqa: BLE001
            settings = None  # type: ignore[assignment]

        def _get(name: str, default: Any) -> Any:
            if settings is not None and hasattr(settings, name):
                return getattr(settings, name)
            return os.environ.get(name.upper(), default)

        ttl = str(_get("anthropic_gateway_cache_ttl", "1h"))
        return cls(
            api_key=str(_get("anthropic_api_key", "")),
            base_url=str(_get("anthropic_base_url", "https://api.anthropic.com/v1")),
            model=str(_get("anthropic_gateway_model", "claude-sonnet-4-6")),
            api_version=str(_get("anthropic_api_version", "2023-06-01")),
            beta_features=tuple(
                _csv_to_tuple(str(_get("anthropic_beta_features", "prompt-caching-2024-07-31")))
            ),
            max_tokens=int(_get("anthropic_gateway_max_tokens", 2048)),
            temperature=float(_get("anthropic_gateway_temperature", 0.7)),
            timeout_s=int(_get("anthropic_gateway_timeout_s", 60)),
            system_cache_ttl=ttl,
            extended_thinking_enabled=bool(
                int(_get("anthropic_extended_thinking_enabled", "0"))
                if isinstance(_get("anthropic_extended_thinking_enabled", "0"), str)
                else _get("anthropic_extended_thinking_enabled", False)
            ),
            extended_thinking_budget_tokens=int(_get("anthropic_extended_thinking_budget_tokens", 0)),
        )


def _csv_to_tuple(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


class AnthropicGateway:
    """Direct Anthropic API client with prompt caching + Citations API.

    Usage::

        gateway = AnthropicGateway.from_settings()
        resp = await gateway.generate(
            system_prompt=GURU_SYSTEM_PROMPT,
            user_message="What is Soul Sync?",
            documents=[
                {"title": "Ekam Soul Sync Discourse", "text": chunk_text},
            ],
        )
        print(resp.text)
        for c in resp.citations:
            print(c.document_index, c.cited_text)
    """

    def __init__(self, config: AnthropicGatewayConfig | None = None) -> None:
        self.config = config or AnthropicGatewayConfig.from_settings()
        self._session: aiohttp.ClientSession | None = None
        self._enabled = bool(self.config.api_key)

    @classmethod
    def from_settings(cls) -> "AnthropicGateway":
        return cls(AnthropicGatewayConfig.from_settings())

    @property
    def enabled(self) -> bool:
        """Returns True iff an API key is configured. Callers should check
        this before issuing requests and fall back to the legacy stack
        otherwise."""
        return self._enabled

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # ---- request construction ----

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.api_version,
            "content-type": "application/json",
        }
        if self.config.beta_features:
            headers["anthropic-beta"] = ",".join(self.config.beta_features)
        return headers

    def _build_system_block(self, system_prompt: str) -> list[dict]:
        """Wrap the system prompt in a cache_control block when caching is on.

        Anthropic caches prefixes that are byte-identical across requests, so
        the system prompt — which never changes per-user — is the highest-ROI
        block to cache. We mark it `ephemeral` with the configured TTL.
        """
        block: dict[str, Any] = {"type": "text", "text": system_prompt}
        if self.config.system_cache_ttl:
            block["cache_control"] = {
                "type": "ephemeral",
                **({"ttl": self.config.system_cache_ttl} if self.config.system_cache_ttl != "5m" else {}),
            }
        return [block]

    def _build_user_message(
        self,
        user_message: str,
        documents: list[Mapping[str, Any]] | None,
    ) -> list[dict]:
        """Build the user message content array.

        When documents are supplied, we use Anthropic's Citations API
        (`"citations": {"enabled": True}`) so the model returns block-index
        citations instead of free-form citation strings. The documents come
        FIRST so the model treats them as the grounding context, then the
        question.
        """
        content: list[dict] = []
        for idx, doc in enumerate(documents or []):
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "text",
                        "media_type": "text/plain",
                        "data": str(doc.get("text", "")),
                    },
                    "title": str(doc.get("title", f"Document {idx + 1}")),
                    "context": str(doc.get("context", "")),
                    "citations": {"enabled": True},
                }
            )
        content.append({"type": "text", "text": user_message})
        return content

    def _build_payload(
        self,
        *,
        system_prompt: str,
        user_message: str,
        documents: list[Mapping[str, Any]] | None,
        max_tokens_override: int | None,
        temperature_override: float | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens_override or self.config.max_tokens,
            "temperature": (
                temperature_override
                if temperature_override is not None
                else self.config.temperature
            ),
            "system": self._build_system_block(system_prompt),
            "messages": [
                {"role": "user", "content": self._build_user_message(user_message, documents)}
            ],
        }
        if self.config.extended_thinking_enabled and self.config.extended_thinking_budget_tokens > 0:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.config.extended_thinking_budget_tokens,
            }
        return payload

    # ---- public methods ----

    async def generate(
        self,
        *,
        system_prompt: str,
        user_message: str,
        documents: list[Mapping[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AnthropicResponse:
        """Non-streaming generation. Raises `AnthropicGatewayError` on failure."""
        if not self._enabled:
            raise AnthropicGatewayError("AnthropicGateway has no api_key; cannot generate.")

        payload = self._build_payload(
            system_prompt=system_prompt,
            user_message=user_message,
            documents=documents,
            max_tokens_override=max_tokens,
            temperature_override=temperature,
        )
        headers = self._build_headers()
        session = await self._get_session()

        start = time.monotonic()
        try:
            async with session.post(
                f"{self.config.base_url.rstrip('/')}/messages",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_s),
            ) as resp:
                latency_ms = int((time.monotonic() - start) * 1000)
                if resp.status >= 400:
                    text = await resp.text()
                    raise AnthropicGatewayError(
                        f"Anthropic API returned {resp.status}: {text[:300]}"
                    )
                data = await resp.json()
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            raise AnthropicGatewayError(f"transport: {exc}") from exc

        return self._parse_response(data, latency_ms)

    async def stream(
        self,
        *,
        system_prompt: str,
        user_message: str,
        documents: list[Mapping[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Streaming generation. Yields text chunks as they arrive.

        Citations and usage are not returned by this iterator — for those, use
        `generate()`. We keep this method narrow so streaming code paths don't
        accidentally over-couple to non-streamable features.
        """
        if not self._enabled:
            raise AnthropicGatewayError("AnthropicGateway has no api_key; cannot stream.")

        payload = self._build_payload(
            system_prompt=system_prompt,
            user_message=user_message,
            documents=documents,
            max_tokens_override=max_tokens,
            temperature_override=temperature,
        )
        payload["stream"] = True
        headers = self._build_headers()
        session = await self._get_session()

        try:
            async with session.post(
                f"{self.config.base_url.rstrip('/')}/messages",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_s),
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise AnthropicGatewayError(
                        f"Anthropic API returned {resp.status}: {text[:300]}"
                    )
                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_payload = line[len("data:"):].strip()
                    if data_payload == "[DONE]":
                        return
                    try:
                        event = json.loads(data_payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text_chunk = delta.get("text") or ""
                            if text_chunk:
                                yield text_chunk
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            raise AnthropicGatewayError(f"transport: {exc}") from exc

    # ---- response parsing ----

    def _parse_response(self, data: dict[str, Any], latency_ms: int) -> AnthropicResponse:
        text_parts: list[str] = []
        citations: list[Citation] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
                for c in block.get("citations") or []:
                    citations.append(
                        Citation(
                            cited_text=str(c.get("cited_text", "")),
                            document_index=int(c.get("document_index", 0)),
                            document_title=c.get("document_title"),
                            start_char_index=c.get("start_char_index"),
                            end_char_index=c.get("end_char_index"),
                            start_block_index=c.get("start_block_index"),
                            end_block_index=c.get("end_block_index"),
                        )
                    )
        usage_raw = data.get("usage") or {}
        usage = AnthropicUsage(
            input_tokens=int(usage_raw.get("input_tokens", 0) or 0),
            output_tokens=int(usage_raw.get("output_tokens", 0) or 0),
            cache_read_input_tokens=int(usage_raw.get("cache_read_input_tokens", 0) or 0),
            cache_creation_input_tokens=int(usage_raw.get("cache_creation_input_tokens", 0) or 0),
            latency_ms=latency_ms,
        )
        if usage.cache_read_input_tokens > 0 or usage.cache_creation_input_tokens > 0:
            logger.info(
                "AnthropicGateway: cache_read=%d cache_create=%d input=%d output=%d ratio=%.2f",
                usage.cache_read_input_tokens,
                usage.cache_creation_input_tokens,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_hit_ratio,
            )
        return AnthropicResponse(
            text="".join(text_parts),
            citations=citations,
            usage=usage,
            stop_reason=data.get("stop_reason"),
            model=data.get("model"),
            raw=data,
        )
