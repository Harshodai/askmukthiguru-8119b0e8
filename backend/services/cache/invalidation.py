"""Targeted response-cache invalidation for consent revocation and erasure."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def invalidate_user_exact_cache(container: Any, user_id: str) -> int:
    """Invalidate one user's exact-cache entries after memory state changes.

    Adapters with a per-user index perform a targeted eviction. Older or
    minimal adapters may expose only invalidate_all; broad eviction is an
    acceptable safety fallback because cache entries are disposable. Failures
    propagate so the caller cannot report successful revocation/erasure while
    stale personalized answers might still be served.
    """
    cache = getattr(container, "exact_cache", None)
    if cache is None:
        return 0

    invalidate_user = getattr(cache, "invalidate_user", None)
    invalidate_all = getattr(cache, "invalidate_all", None)
    if not callable(invalidate_user) and not callable(invalidate_all):
        raise RuntimeError("exact cache does not support invalidation")

    operation = invalidate_user if callable(invalidate_user) else invalidate_all
    result = await asyncio.to_thread(operation, user_id) if operation is invalidate_user else await asyncio.to_thread(operation)
    if inspect.isawaitable(result):
        result = await result
    try:
        return max(0, int(result or 0))
    except (TypeError, ValueError):
        return 0
