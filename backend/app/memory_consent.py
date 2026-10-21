"""Server-authoritative consent checks for user-scoped durable memory writes.

All durable memory writers should call this helper before persisting new or
derived personal information. Missing consent infrastructure and lookup errors
fail closed; user-directed deletion remains available without consent.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def require_active_memory_consent(container: Any, user_id: str) -> dict[str, Any]:
    """Require a current consent receipt for the resolved request tenant."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user required.")

    outbox = getattr(container, "memory_outbox", None)
    if outbox is None:
        raise HTTPException(
            status_code=503,
            detail="Memory consent cannot be verified right now.",
        )

    from services.tenant_context import TenantContext

    tenant_id = TenantContext.get()
    if not tenant_id:
        raise HTTPException(
            status_code=503,
            detail="Memory consent cannot be verified without a tenant context.",
        )

    try:
        receipt = await outbox.active_consent(user_id=user_id, tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("Memory consent verification failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Memory consent cannot be verified right now.",
        ) from exc

    if not receipt:
        raise HTTPException(
            status_code=403,
            detail="Explicit active memory consent is required for this operation.",
        )
    return receipt
