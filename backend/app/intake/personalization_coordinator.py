"""Unified Seeker Personalization & Second Brain Context Hydration Coordinator.

Runs parallel hydration in <15ms using asyncio.gather with strict deadlines.
Respects DPDP consent receipts and universal client-side Zero-Knowledge
Mode-B encryption without blocking the request intake path.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnifiedUserPersonalizationContext:
    """Unified user context delivered to Engine 2 retrieval and Engine 3 generation."""

    user_id: str
    guru_tone: str = "gentle"  # 'gentle' | 'direct' | 'poetic'
    familiarity_level: str = "seeker"  # 'seeker' | 'practitioner' | 'advanced'
    preferred_language: str = "en"
    sadhana_streak_days: int = 0
    last_practice: Optional[str] = None  # e.g. 'soul_sync', 'serene_mind'
    active_memories: list[str] = field(default_factory=list)  # Top 3 personal facts/goals
    is_mode_b_unlocked: bool = False


class UnifiedPersonalizationCoordinator:
    """Coordinates fast concurrent retrieval of seeker profile, streaks, and PKG memories."""

    @staticmethod
    def _map_familiarity(level: Any) -> str:
        """Normalize spiritual / familiarity level to 3 canonical tiers."""
        raw = str(getattr(level, "value", level) or "").lower()
        if raw in ("advanced", "master"):
            return "advanced"
        if raw in ("practitioner", "sadhak", "intermediate"):
            return "practitioner"
        return "seeker"

    async def _fetch_profile(self, user_id: str, container: Any) -> tuple[str, str, str]:
        """Fetch (guru_tone, familiarity_level, preferred_language)."""
        tone = "gentle"
        familiarity = "seeker"
        lang = "en"

        user_profile_svc = getattr(container, "user_profile", None)
        if user_profile_svc is not None and hasattr(user_profile_svc, "get_or_create_profile"):
            try:
                prof = await user_profile_svc.get_or_create_profile(user_id)
                if prof:
                    tone = str(getattr(prof, "guru_tone", "gentle") or "gentle").lower()
                    if tone not in ("gentle", "direct", "poetic"):
                        tone = "gentle"
                    familiarity = self._map_familiarity(getattr(prof, "spiritual_level", "seeker"))
                    pref_lang = getattr(prof, "preferred_language", "en")
                    lang = str(getattr(pref_lang, "value", pref_lang) or "en").lower()
            except Exception as e:
                logger.debug("Profile fetch error for user %s: %s", user_id, e)

        return tone, familiarity, lang

    async def _fetch_streaks(self, user_id: str, container: Any) -> tuple[int, Optional[str]]:
        """Fetch (sadhana_streak_days, last_practice)."""
        streak_days = 0
        last_practice: Optional[str] = None

        retention_svc = getattr(container, "retention_service", None)
        if retention_svc is not None and hasattr(retention_svc, "_load_state"):
            try:
                state = await retention_svc._load_state(user_id)
                if state:
                    streak_days = int(getattr(state, "current", 0) or 0)
                    last_practice = getattr(state, "last_practice", None)
            except Exception as e:
                logger.debug("Streak fetch error for user %s: %s", user_id, e)

        # Fallback to direct supabase client if retention service wasn't wired
        if streak_days == 0 and hasattr(container, "supabase_client") and container.supabase_client:
            try:
                db = container.supabase_client
                res = await asyncio.to_thread(
                    lambda: (
                        db.table("user_streaks")
                        .select("current_streak,last_practice")
                        .eq("user_id", user_id)
                        .maybe_single()
                        .execute()
                    )
                )
                row = res.data if res and getattr(res, "data", None) else {}
                if row:
                    streak_days = int(row.get("current_streak", 0) or 0)
                    last_practice = row.get("last_practice")
            except Exception as e:
                logger.debug("Direct streak query error for user %s: %s", user_id, e)

        return streak_days, last_practice

    async def _fetch_memories(
        self, user_id: str, x_brain_unlock: Optional[str], container: Any
    ) -> tuple[list[str], bool]:
        """Fetch decrypted PKG active memories respecting DPDP consent receipts."""
        active_memories: list[str] = []
        is_mode_b_unlocked = False

        # 1. DPDP Consent Check
        outbox = getattr(container, "memory_outbox", None)
        if outbox is None or not hasattr(outbox, "active_consent"):
            # No consent store reachable: DPDP says no memories, not "assume consent".
            return active_memories, False
        try:
            from services.tenant_context import TenantContext

            tenant_id = TenantContext.get() or "default"
            receipt = await outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
            if not receipt:
                # Fail closed per DPDP Act: no memories if consent not explicitly active
                return active_memories, False
        except Exception as e:
            logger.debug("DPDP consent verification error: %s", e)
            return active_memories, False

        # 2. Second Brain Unlock & Memory Retrieval
        second_brain = getattr(container, "second_brain", None)
        if second_brain is not None and hasattr(second_brain, "unlock"):
            try:
                vault = await second_brain.unlock(user_id, passphrase=x_brain_unlock)
                if vault:
                    is_mode_b_unlocked = bool(x_brain_unlock)
                    if hasattr(second_brain, "personal_context"):
                        items = await second_brain.personal_context(
                            user_id, query="", limit=3, vault=vault
                        )
                        for it in items:
                            text = getattr(it, "text", None)
                            if text and isinstance(text, str):
                                active_memories.append(text.strip())
                    elif hasattr(second_brain, "list_items"):
                        items = await second_brain.list_items(user_id, vault=vault, limit=3)
                        for it in items:
                            text = getattr(it, "text", None)
                            if text and isinstance(text, str):
                                active_memories.append(text.strip())
            except Exception as e:
                logger.debug("Second brain memory recall error for user %s: %s", user_id, e)

        return active_memories[:3], is_mode_b_unlocked

    async def hydrate_context(
        self,
        user_id: Optional[str],
        x_brain_unlock: Optional[str] = None,
        container: Optional[Any] = None,
        timeout_ms: int = 15,
    ) -> UnifiedUserPersonalizationContext:
        """Hydrate unified personalization context with a strict SLA deadline (<15ms).

        Degrades gracefully if user is anonymous or services time out, returning
        a default context in <10ms without failing the request.
        """
        # Anonymous / unauthenticated short-circuit (<1ms)
        if not user_id or user_id in ("anonymous", "guest", ""):
            return UnifiedUserPersonalizationContext(user_id="anonymous")

        if container is None:
            return UnifiedUserPersonalizationContext(user_id=user_id)

        timeout_sec = max(0.001, timeout_ms / 1000.0)

        async def _gather_all() -> UnifiedUserPersonalizationContext:
            profile_task = asyncio.create_task(self._fetch_profile(user_id, container))
            streak_task = asyncio.create_task(self._fetch_streaks(user_id, container))
            memory_task = asyncio.create_task(
                self._fetch_memories(user_id, x_brain_unlock, container)
            )

            results = await asyncio.gather(
                profile_task, streak_task, memory_task, return_exceptions=True
            )

            tone, familiarity, lang = (
                results[0] if not isinstance(results[0], Exception) else ("gentle", "seeker", "en")
            )
            streaks, last_prac = results[1] if not isinstance(results[1], Exception) else (0, None)
            memories, mode_b = results[2] if not isinstance(results[2], Exception) else ([], False)

            return UnifiedUserPersonalizationContext(
                user_id=user_id,
                guru_tone=tone,
                familiarity_level=familiarity,
                preferred_language=lang,
                sadhana_streak_days=streaks,
                last_practice=last_prac,
                active_memories=memories,
                is_mode_b_unlocked=mode_b,
            )

        try:
            return await asyncio.wait_for(_gather_all(), timeout=timeout_sec)
        except TimeoutError:
            logger.warning(
                "Personalization hydration timed out (>%dms) for user %s; returning default context",
                timeout_ms,
                user_id,
            )
            return UnifiedUserPersonalizationContext(user_id=user_id)
        except Exception as exc:
            logger.warning(
                "Personalization hydration encountered error for user %s (%s); returning default",
                user_id,
                exc,
            )
            return UnifiedUserPersonalizationContext(user_id=user_id)
