"""Targeted response-cache invalidation for consent revocation and erasure."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


async def invalidate_user_exact_cache(
    container: Any, user_id: str, *, all_tenants: bool = False
) -> int:
    """Invalidate exact answers after consent changes or account erasure.

    Tenant-scoped revocation clears that tenant's cache. Account-wide erasure
    must explicitly request all tenants; silently falling back to a tenant-only
    adapter would let stale answers survive and falsely certify erasure.
    """
    cache = getattr(container, "exact_cache", None)
    if cache is None:
        return 0

    invalidate_user = getattr(cache, "invalidate_user", None)
    invalidate_all = getattr(cache, "invalidate_all", None)
    if not callable(invalidate_user) and not callable(invalidate_all):
        raise RuntimeError("exact cache does not support invalidation")

    if all_tenants:
        # "invalidate_all" semantics vary by adapter; require an explicit
        # all_tenants contract when available rather than assume it is global.
        try:
            parameters = inspect.signature(invalidate_user).parameters if callable(invalidate_user) else {}
        except (TypeError, ValueError):
            parameters = {}
        if callable(invalidate_user) and "all_tenants" in parameters:
            result = await asyncio.to_thread(invalidate_user, user_id, all_tenants=True)
        elif callable(invalidate_all):
            result = await asyncio.to_thread(invalidate_all)
        else:
            raise RuntimeError("exact cache cannot prove cross-tenant invalidation")
    elif callable(invalidate_user):
        result = await asyncio.to_thread(invalidate_user, user_id)
    else:
        result = await asyncio.to_thread(invalidate_all)

    if inspect.isawaitable(result):
        result = await result
    try:
        return max(0, int(result or 0))
    except (TypeError, ValueError):
        return 0
