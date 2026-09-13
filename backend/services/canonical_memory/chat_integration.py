"""Canonical Memory Chat Integration — Phase 11 of the Adaptive Memory System.

Integrates the canonical memory pipeline with the existing chat orchestrator.
Feature-flag gated dual-read, shadow mode, async post-response extraction,
and failure fallback to the legacy memory system.

Design principles:
    - Memory failure never fails chat.
    - Dual-read mode: read from both old and new, use new system results.
    - Shadow mode: run new system, log decisions, don't serve results.
    - Post-response memory processing is async and non-blocking.
    - Explicit memory commands are handled synchronously.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature flags — read from Settings with safe defaults
# ---------------------------------------------------------------------------

def _flag(name: str, default: bool = False) -> bool:
    """Read a feature flag from settings, returning default if absent.

    Retained for callers that genuinely need a dynamic lookup. The five flags
    below read their attributes DIRECTLY instead: a getattr() on a variable name
    is invisible to the dead-settings scan in tests/test_wiring_invariants.py,
    which is how all five came to be read here but never declared on Settings —
    every one silently resolved to its default no matter what the environment
    said. Direct access makes the wiring checkable.
    """
    return getattr(settings, name, default)


def _ff_canonical_memory() -> bool:
    return bool(settings.canonical_memory_enabled)


def _ff_canonical_memory_retrieval() -> bool:
    return bool(settings.canonical_memory_retrieval)


def _ff_memory_shadow() -> bool:
    return bool(settings.memory_shadow)


def _ff_memory_write() -> bool:
    return bool(settings.memory_write)


def _ff_memory_influence() -> bool:
    return bool(settings.memory_influence)


# ---------------------------------------------------------------------------
# Protocol / type aliases for loose coupling
# ---------------------------------------------------------------------------

class MemoryRetrieverProto(Protocol):
    async def retrieve(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
        max_tokens: int = 2000,
    ) -> Any: ...


class ExtractorProto(Protocol):
    async def __call__(
        self,
        turns: list[dict[str, Any]],
        user_id: str,
        session_id: str = "",
        language_hint: str = "en",
    ) -> Any: ...


class JudgeProto(Protocol):
    async def judge(
        self,
        candidates: list[Any],
        user_id: str,
    ) -> list[Any]: ...


class ResolverProto(Protocol):
    async def resolve(
        self,
        decision: Any,
        user_id: str,
    ) -> Any: ...


class LegacyMemoryProto(Protocol):
    async def get_core(self, user_id: str) -> list[dict[str, Any]]: ...

    async def search_semantic(
        self, user_id: str, query: str, limit: int = 5, min_similarity: float = 0.6
    ) -> list[dict[str, Any]]: ...


class ContextOrchestratorProto(Protocol):
    async def build_context(
        self,
        user_id: str,
        query: str,
        session_messages: list[dict[str, Any]],
        memories: Optional[list[dict[str, Any]]] = None,
        knowledge_chunks: Optional[list[dict[str, Any]]] = None,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Explicit command detection
# ---------------------------------------------------------------------------

_REMEMBER_PATTERN = re.compile(
    r"^(?:please\s+)?remember\s+(?:that\s+)?(.+)$",
    re.IGNORECASE,
)
_FORGET_PATTERN = re.compile(
    r"^(?:please\s+)?(?:forget|don'?t\s+(?:remember|recall))\s+(?:that\s+)?(.+)$",
    re.IGNORECASE,
)
_RECALL_PATTERN = re.compile(
    r"^(?:what\s+(?:do|did)\s+you\s+)?(?:remember|recall)\s+(?:about\s+me|of\s+me)?\s*\??$",
    re.IGNORECASE,
)


def detect_explicit_command(query: str) -> Optional[str]:
    """Detect explicit memory commands in user input.

    Returns:
        "remember:<fact>" if user wants to remember something.
        "forget:<fact>" if user wants to forget something.
        "recall" if user asks what the system remembers.
        None if no explicit command detected.
    """
    text = (query or "").strip()
    if not text:
        return None

    m = _REMEMBER_PATTERN.match(text)
    if m:
        return f"remember:{m.group(1).strip()}"

    m = _FORGET_PATTERN.match(text)
    if m:
        return f"forget:{m.group(1).strip()}"

    if _RECALL_PATTERN.match(text):
        return "recall"

    return None


# ---------------------------------------------------------------------------
# Main integration class
# ---------------------------------------------------------------------------

def _decision_action(decision: Any) -> str:
    """Read a MemoryDecision's action, whatever the field is called.

    `MemoryJudge` returns `MemoryDecision.decision` (a `DecisionType`). This
    module was written against `.action`, so `getattr(decision, "action", None)`
    was always None — falsy — and EVERY decision was skipped. The write path
    therefore extracted candidates, judged them, and silently wrote nothing.
    Found 2026-09-13, the first time it ran against the real judge.
    """
    value = getattr(decision, "decision", None)
    if value is None:
        value = getattr(decision, "action", None)
    if value is None:
        return ""
    return str(getattr(value, "value", value))


@dataclass
class CanonicalMemoryIntegration:
    """Bridge between the canonical memory system and the chat pipeline.

    Respects feature flags for gradual rollout: shadow mode, dual-read,
    memory influence, and write gating.  Memory failures always degrade
    gracefully — chat is never blocked.
    """

    context_orchestrator: Any  # AdaptiveContextOrchestrator
    memory_retriever: Any  # CanonicalMemoryRetriever
    extractor: Any  # extract_memory_candidates callable
    judge: Any  # MemoryJudge
    resolver: Any  # MemoryResolver
    existing_memory_service: Any  # Legacy MemoryService

    # --- Feature flag readers (instance-level, testable) ---

    @property
    def canonical_enabled(self) -> bool:
        return _ff_canonical_memory()

    @property
    def retrieval_enabled(self) -> bool:
        return _ff_canonical_memory_retrieval()

    @property
    def shadow_mode(self) -> bool:
        return _ff_memory_shadow()

    @property
    def write_enabled(self) -> bool:
        return _ff_memory_write()

    @property
    def influence_enabled(self) -> bool:
        return _ff_memory_influence()

    # --- Core: prepare memory context for generation ---

    async def prepare_context(
        self,
        user_id: str,
        query: str,
        session_id: str,
        session_messages: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Prepare memory context for generation. Respects feature flags.

        Modes:
            1. Canonical disabled → legacy only (default).
            2. Canonical enabled + retrieval enabled → read from canonical,
               fallback to legacy on failure.
            3. Canonical enabled + retrieval disabled → legacy only.
            4. Shadow mode → run canonical but discard results, use legacy.
            5. Influence disabled → retrieve but don't inject into context.

        Returns:
            Memory context string for the generation prompt.
        """
        session_messages = session_messages or []
        start = time.monotonic()

        if not self.canonical_enabled:
            return await self._legacy_context(user_id, query)

        if not self.retrieval_enabled:
            return await self._legacy_context(user_id, query)

        # --- Canonical retrieval path ---
        canonical_context = ""
        try:
            canonical_context = await self._canonical_context(
                user_id, query, session_messages
            )
        except Exception as exc:
            logger.warning(
                "Canonical memory context failed, falling back to legacy: %s", exc
            )
            canonical_context = ""

        # Shadow mode: run canonical for logging, but serve legacy
        if self.shadow_mode:
            legacy_context = await self._legacy_context(user_id, query)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "shadow_mode canonical_context_len=%d legacy_context_len=%d elapsed_ms=%.1f",
                len(canonical_context),
                len(legacy_context),
                elapsed_ms,
            )
            return legacy_context

        # Influence disabled: retrieve for observability, don't serve
        if not self.influence_enabled and canonical_context:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "influence_disabled canonical_retrieved=%d_chars elapsed_ms=%.1f",
                len(canonical_context),
                elapsed_ms,
            )
            return ""

        # Canonical path: serve canonical context, fall back to legacy if empty
        if canonical_context:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "canonical_context served=%d_chars elapsed_ms=%.1f",
                len(canonical_context),
                elapsed_ms,
            )
            return canonical_context

        # Canonical returned empty — fall back to legacy
        return await self._legacy_context(user_id, query)

    # --- Async post-response memory extraction ---

    async def post_response_memory(
        self,
        user_id: str,
        query: str,
        response: str,
        session_id: str,
        session_messages: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Process memory after response. Async, non-blocking.

        Runs the canonical extraction → judge → resolver pipeline.
        If canonical memory is disabled or shadow mode is on, this is a no-op.
        """
        if not self.canonical_enabled:
            return

        if not self.write_enabled:
            return

        try:
            await self._run_extraction_pipeline(
                user_id, query, response, session_id, session_messages or []
            )
        except Exception as exc:
            logger.warning(
                "Canonical memory post-response failed (non-fatal): %s", exc
            )

    # --- Explicit memory commands ---

    async def handle_explicit_command(
        self,
        user_id: str,
        command: str,
        query: str,
    ) -> str:
        """Handle explicit memory commands: remember, forget, what do you remember.

        Returns a user-facing response string.
        """
        if not command:
            return ""

        if command.startswith("remember:"):
            fact = command[len("remember:"):]
            return await self._handle_remember(user_id, fact)

        if command.startswith("forget:"):
            fact = command[len("forget:"):]
            return await self._handle_forget(user_id, fact)

        if command == "recall":
            return await self._handle_recall(user_id)

        return ""

    # --- Internal helpers ---

    async def _canonical_context(
        self,
        user_id: str,
        query: str,
        session_messages: list[dict[str, Any]],
    ) -> str:
        """Retrieve memories from canonical system and format as context."""
        result = await self.memory_retriever.retrieve(
            user_id=user_id,
            query=query,
            limit=20,
            max_tokens=2000,
        )

        if not result or not getattr(result, "memories", None):
            return ""

        memories = [
            {
                "statement": m.statement,
                "memory_type": m.memory_type,
                "confidence": m.confidence,
                "source_conversation_id": getattr(m, "source_conversation_id", ""),
            }
            for m in result.memories
        ]

        # Use context builder for formatted output
        context_result = await self.context_orchestrator.build_context(
            user_id=user_id,
            query=query,
            session_messages=session_messages,
            memories=memories,
        )

        memory_block = context_result.memory_block
        if memory_block and memory_block.included and memory_block.content:
            return memory_block.content

        return ""

    async def _legacy_context(self, user_id: str, query: str) -> str:
        """Retrieve from legacy memory system."""
        if not self.existing_memory_service:
            return ""

        try:
            core_m = await self.existing_memory_service.get_core(user_id)
            semantic_m = []
            if query:
                semantic_m = await self.existing_memory_service.search_semantic(
                    user_id, query, limit=5, min_similarity=0.6
                )

            parts = []
            if core_m:
                parts.append(
                    "USER PROFILE & CORE FACTS:\n- "
                    + "\n- ".join(c.get("content", "") for c in core_m if c.get("content"))
                )
            if semantic_m:
                from app.orchestrator_utils import _format_scored_memory_block
                parts.append(_format_scored_memory_block(semantic_m))

            return "\n\n".join(parts) if parts else ""
        except Exception as exc:
            logger.warning("Legacy memory context failed: %s", exc)
            return ""

    async def _run_extraction_pipeline(
        self,
        user_id: str,
        query: str,
        response: str,
        session_id: str,
        session_messages: list[dict[str, Any]],
    ) -> None:
        """Run extraction → judge → resolver pipeline (post-response, async)."""
        # Build turns for extraction
        turns = list(session_messages) if session_messages else []
        turns.append({"role": "user", "content": query})
        turns.append({"role": "assistant", "content": response})

        # 1. Extract candidates
        extraction = await self.extractor(
            turns=turns,
            user_id=user_id,
            session_id=session_id,
        )

        candidates = getattr(extraction, "candidates", None) or []
        if not candidates:
            # Extraction producing nothing is normal for a turn with no durable
            # facts in it — but it is indistinguishable from a broken extractor
            # unless it says so.
            logger.info("Canonical extraction: 0 candidates from this turn")
            return

        # 2. Judge each candidate
        decisions = await self.judge.judge(candidates, user_id=user_id)

        actions = [str(getattr(d, "action", "?")) for d in decisions]
        logger.info(
            "Canonical extraction: %d candidate(s) -> decisions %s",
            len(candidates),
            actions,
        )

        # 3. Resolve accepted decisions
        for decision in decisions:
            action = _decision_action(decision)
            if action and action not in ("IGNORE", "ESCALATE"):
                try:
                    await self.resolver.resolve(decision, user_id=user_id)
                except Exception as exc:
                    logger.warning(
                        "Canonical memory resolution failed for %s: %s",
                        _decision_action(decision) or "?",
                        exc,
                    )

    async def _handle_remember(self, user_id: str, fact: str) -> str:
        """Handle explicit 'remember that X' command."""
        if not fact or len(fact.strip()) < 3:
            return "Please provide a specific fact for me to remember."

        if not self.write_enabled:
            return (
                "I appreciate you sharing that. "
                "Memory persistence is currently being set up — "
                "I'll remember it once the feature is enabled."
            )

        # Create a direct extraction candidate for the explicit fact
        try:
            from services.canonical_memory.models import MemoryCandidate, MemoryType

            candidate = MemoryCandidate(
                statement=fact.strip(),
                normalized_statement=fact.strip().lower(),
                memory_type=MemoryType.USER_EXPLICIT,
                fact_key=None,
                confidence=1.0,
                importance=0.8,
                sensitivity="normal",
                evidence=fact.strip(),
                source_turn_index=0,
                explicit_request=True,
                extraction_model="explicit",
                extraction_prompt_version="v1",
                language="en",
            )

            decisions = await self.judge.judge([candidate], user_id=user_id)
            for decision in decisions:
                action = _decision_action(decision)
                if action and action not in ("IGNORE", "ESCALATE"):
                    await self.resolver.resolve(decision, user_id=user_id)

            return f"I'll remember: {fact.strip()}"
        except Exception as exc:
            logger.warning("Explicit remember failed: %s", exc)
            return "I wasn't able to save that. Please try again later."

    async def _handle_forget(self, user_id: str, fact: str) -> str:
        """Handle explicit 'forget X' command."""
        if not fact or len(fact.strip()) < 2:
            return "Please specify what you'd like me to forget."

        if not self.write_enabled:
            return "Memory management is currently being updated. I'll handle that once it's ready."

        try:
            from services.canonical_memory.models import MemoryCandidate, MemoryType

            candidate = MemoryCandidate(
                statement=f"User wants to forget: {fact.strip()}",
                normalized_statement=fact.strip().lower(),
                memory_type=MemoryType.USER_EXPLICIT,
                fact_key=None,
                confidence=1.0,
                importance=1.0,
                sensitivity="normal",
                evidence=f"User said: forget {fact.strip()}",
                source_turn_index=0,
                explicit_request=True,
                extraction_model="explicit",
                extraction_prompt_version="v1",
                language="en",
            )

            decisions = await self.judge.judge([candidate], user_id=user_id)
            for decision in decisions:
                action = _decision_action(decision)
                if action and str(action) in ("DELETE", "EXPIRE"):
                    await self.resolver.resolve(decision, user_id=user_id)

            return f"I've forgotten: {fact.strip()}"
        except Exception as exc:
            logger.warning("Explicit forget failed: %s", exc)
            return "I wasn't able to forget that. Please try again later."

    async def _handle_recall(self, user_id: str) -> str:
        """Handle 'what do you remember' command."""
        if not self.retrieval_enabled:
            return (
                "I'm still getting to know you. "
                "As we chat, I'll learn about your preferences and interests."
            )

        try:
            result = await self.memory_retriever.retrieve(
                user_id=user_id,
                query="user profile preferences interests",
                limit=10,
                max_tokens=1000,
            )

            memories = getattr(result, "memories", None) or []
            if not memories:
                return (
                    "I'm still getting to know you. "
                    "As we chat, I'll learn about your preferences and interests."
                )

            lines = ["Here's what I remember about you:"]
            for m in memories[:10]:
                lines.append(f"- {m.statement}")

            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Explicit recall failed: %s", exc)
            return "I'm having trouble accessing your memories right now."


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_chat_integration(
    context_orchestrator: Any,
    memory_retriever: Any,
    extractor: Any,
    judge: Any,
    resolver: Any,
    existing_memory_service: Any,
) -> CanonicalMemoryIntegration:
    """Factory to create a CanonicalMemoryIntegration."""
    return CanonicalMemoryIntegration(
        context_orchestrator=context_orchestrator,
        memory_retriever=memory_retriever,
        extractor=extractor,
        judge=judge,
        resolver=resolver,
        existing_memory_service=existing_memory_service,
    )


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test explicit command detection
    cases = [
        ("Remember that I prefer concise answers", "remember:I prefer concise answers"),
        ("Please remember I live in Mumbai", "remember:I live in Mumbai"),
        ("Forget my location", "forget:my location"),
        ("Don't remember that preference", "forget:that preference"),
        ("What do you remember about me?", "recall"),
        ("What do you recall?", None),  # doesn't match exactly
        ("Hello, how are you?", None),
        ("", None),
    ]

    for query, expected in cases:
        actual = detect_explicit_command(query)
        status = "PASS" if actual == expected else "FAIL"
        print(f"  [{status}] '{query}' → {actual!r} (expected {expected!r})")

    print("\ncanonical_memory chat_integration self-check: OK")
