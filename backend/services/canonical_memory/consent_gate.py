"""Per-request consent gate for canonical-memory extraction.

`MemoryJudge` owns a consent gate (`judge.py`, "User has not granted memory
consent" -> ESCALATE), but it reads `self.user_consent`, which is fixed when the
judge is constructed. The container builds ONE judge for the process lifetime,
so a per-user, per-request decision was frozen at wiring time and the gate could
never fire. A per-user decision has no correct default; this module makes the
lookup happen per call instead.

Why this reads `memory_consent_receipts` through `MemoryOutbox.active_consent`
and NOT through `MemoryPrivacyManager.check_consent`: `check_consent` filters on
a `scope` column, and no migration ever created one (the table is keyed
`(user_id, tenant_id, consent_version)` — supabase/migrations/
20260805000001_memory_outbox.sql). Every `check_consent` call would raise
against the real database, and under a fail-closed gate that means NO seeker is
ever remembered — a silent kill switch wearing the costume of a consent check.
`active_consent` is the reader that matches the deployed schema and the writer
used by both consent endpoints.

Fail CLOSED: no lookup, no receipt, a timeout, or any error means no extraction.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Optional, Protocol

from app.config import settings
from services.canonical_memory.judge import MemoryJudge

logger = logging.getLogger(__name__)


class ConsentLookup(Protocol):
    async def __call__(self, user_id: str, tenant_id: str) -> Any: ...


async def consent_granted(
    lookup: Optional[ConsentLookup],
    user_id: str,
    tenant_id: str,
    timeout: float,
) -> bool:
    """Return True only if a live, granted consent receipt was read back.

    Every other outcome — no lookup wired, blank user, no receipt, timeout,
    transport error — is False.
    """
    if lookup is None or not user_id:
        logger.info("Memory consent denied: no consent store or no user identity")
        return False
    try:
        receipt = await asyncio.wait_for(
            lookup(user_id=user_id, tenant_id=tenant_id), timeout=timeout
        )
    except TimeoutError:
        logger.warning("Memory consent lookup timed out; denying extraction")
        return False
    except Exception as exc:
        logger.warning("Memory consent lookup failed (%s); denying extraction", exc)
        return False
    if not receipt:
        logger.info("Memory consent denied: no active receipt for this seeker")
        return False
    return True


class ConsentGatedJudge:
    """Async adapter over `MemoryJudge` that resolves consent per call.

    Also bridges three call-shape mismatches: `chat_integration` awaits
    `judge.judge(candidates, user_id=...)`, while `MemoryJudge.judge` is
    synchronous, single-candidate, and takes no user_id.
    """

    def __init__(
        self,
        consent_lookup: Optional[ConsentLookup],
        judge_factory: Callable[[bool], MemoryJudge] | None = None,
        tenant_resolver: Callable[[], str] | None = None,
    ) -> None:
        self._consent_lookup = consent_lookup
        self._judge_factory = judge_factory or (lambda consent: MemoryJudge(user_consent=consent))
        self._tenant_resolver = tenant_resolver or _default_tenant

    async def judge(self, candidates, user_id: str | None = None):
        # Bounded by the READ budget, not the write budget: a consent receipt is
        # one indexed row, and this keeps the gate far inside the write task's
        # own canonical_memory_write_timeout rather than stacking onto it.
        allowed = await consent_granted(
            self._consent_lookup,
            user_id or "",
            self._resolve_tenant(),
            float(settings.canonical_memory_timeout),
        )
        return self._judge_factory(allowed).judge_all(list(candidates))

    def _resolve_tenant(self) -> str:
        try:
            return self._tenant_resolver()
        except Exception as exc:
            # A tenant we cannot resolve is a consent receipt we cannot match.
            logger.warning("Tenant resolution failed (%s); denying extraction", exc)
            return ""


def _default_tenant() -> str:
    from services.tenant_context import TenantContext

    return TenantContext.get()


if __name__ == "__main__":  # pragma: no cover - self-check
    from services.canonical_memory.models import MemoryCandidate, MemoryType

    cand = MemoryCandidate(
        statement="User lives in Mumbai and practises daily.",
        memory_type=MemoryType.PROFILE,
        confidence=0.9,
        importance=0.7,
        fact_key="user:city",
        evidence="I live in Mumbai.",
    )

    async def _granted(user_id: str, tenant_id: str):
        return {"id": "receipt-1", "granted": True}

    async def _no_receipt(user_id: str, tenant_id: str):
        return None

    async def _boom(user_id: str, tenant_id: str):
        raise RuntimeError("supabase down")

    def _gate(lookup):
        return ConsentGatedJudge(lookup, tenant_resolver=lambda: "t1")

    async def _verdict(lookup, user_id="u1"):
        out = await _gate(lookup).judge([cand], user_id=user_id)
        return out[0].decision.value

    async def _main() -> None:
        assert await _verdict(_granted) != "ESCALATE"
        for denied in (None, _no_receipt, _boom):
            assert await _verdict(denied) == "ESCALATE", denied
        assert await _verdict(_granted, user_id="") == "ESCALATE"
        print("consent_gate.py self-check passed")

    asyncio.run(_main())
