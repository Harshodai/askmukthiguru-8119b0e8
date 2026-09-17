"""Consent must gate extraction of personal facts, per user, per request.

The defect this pins: the container built ONE `MemoryJudge()` for the process
lifetime, and `MemoryJudge.__init__` defaults `user_consent=True`, so the
judge's own consent gate (judge.py, "User has not granted memory consent")
could never fire. A per-user decision had been frozen into a singleton.

`memory_write` defaults True, so extraction is live; the only thing standing
between a seeker's words and a durable inferred fact is this gate. It fails
CLOSED — the absence of a receipt, and any failure to read one, both deny.
"""

import asyncio
import inspect

import pytest

from services.canonical_memory.consent_gate import ConsentGatedJudge, consent_granted
from services.canonical_memory.models import MemoryCandidate, MemoryType


def _candidate() -> MemoryCandidate:
    return MemoryCandidate(
        statement="User lives in Mumbai and practises daily.",
        memory_type=MemoryType.PROFILE,
        confidence=0.9,
        importance=0.7,
        fact_key="user:city",
        evidence="I live in Mumbai.",
    )


def _gate(lookup) -> ConsentGatedJudge:
    return ConsentGatedJudge(consent_lookup=lookup, tenant_resolver=lambda: "oneness")


async def _decisions(lookup, user_id: str = "seeker-1"):
    return await _gate(lookup).judge([_candidate()], user_id=user_id)


def _extracted(decisions) -> bool:
    """True if anything would reach the resolver.

    Mirrors chat_integration._run_extraction_pipeline, which resolves every
    decision whose action is neither IGNORE nor ESCALATE.
    """
    return any(d.decision.value not in ("IGNORE", "ESCALATE") for d in decisions)


# --- the four required cases -------------------------------------------------


@pytest.mark.asyncio
async def test_no_receipt_extracts_nothing():
    async def _no_receipt(*, user_id, tenant_id):
        return None

    assert not _extracted(await _decisions(_no_receipt))


@pytest.mark.asyncio
async def test_revoked_consent_extracts_nothing():
    """A row with granted=False must not be read back as consent.

    `MemoryOutbox.active_consent` filters `granted=True` and `revoked_at IS
    NULL` in the query, so a revoked seeker yields no row at all.
    """

    async def _revoked(*, user_id, tenant_id):
        return None

    assert not _extracted(await _decisions(_revoked))


@pytest.mark.asyncio
async def test_granted_consent_extracts():
    async def _granted(*, user_id, tenant_id):
        return {"id": "receipt-1", "granted": True, "consent_version": "memory-v1"}

    decisions = await _decisions(_granted)
    assert _extracted(decisions), [d.reason for d in decisions]


@pytest.mark.asyncio
async def test_consent_store_failure_extracts_nothing():
    async def _boom(*, user_id, tenant_id):
        raise RuntimeError("supabase unreachable")

    assert not _extracted(await _decisions(_boom))


# --- fail-closed on every other way the lookup can go wrong ------------------


@pytest.mark.asyncio
async def test_timeout_extracts_nothing(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "canonical_memory_timeout", 0.01)

    async def _hangs(*, user_id, tenant_id):
        await asyncio.sleep(5)
        return {"granted": True}

    assert not _extracted(await _decisions(_hangs))


@pytest.mark.asyncio
async def test_no_consent_store_extracts_nothing():
    assert not _extracted(await _decisions(None))


@pytest.mark.asyncio
async def test_anonymous_identity_extracts_nothing():
    async def _granted(*, user_id, tenant_id):
        return {"granted": True}

    assert not _extracted(await _decisions(_granted, user_id=""))


@pytest.mark.asyncio
async def test_unresolvable_tenant_extracts_nothing():
    """A tenant we cannot resolve is a receipt we cannot match."""
    seen: list[str] = []

    async def _granted(*, user_id, tenant_id):
        seen.append(tenant_id)
        return {"granted": True} if tenant_id else None

    def _explode() -> str:
        raise RuntimeError("no tenant context")

    gate = ConsentGatedJudge(consent_lookup=_granted, tenant_resolver=_explode)
    assert not _extracted(await gate.judge([_candidate()], user_id="seeker-1"))


@pytest.mark.asyncio
async def test_consent_is_resolved_per_call_not_once():
    """Revoking between turns must take effect on the next turn."""
    answers = [{"granted": True}, None]

    async def _changing(*, user_id, tenant_id):
        return answers.pop(0)

    gate = _gate(_changing)
    assert _extracted(await gate.judge([_candidate()], user_id="seeker-1"))
    assert not _extracted(await gate.judge([_candidate()], user_id="seeker-1"))


@pytest.mark.asyncio
async def test_consent_is_looked_up_per_user():
    seen: list[str] = []

    async def _per_user(*, user_id, tenant_id):
        seen.append(user_id)
        return {"granted": True} if user_id == "consented" else None

    gate = _gate(_per_user)
    assert _extracted(await gate.judge([_candidate()], user_id="consented"))
    assert not _extracted(await gate.judge([_candidate()], user_id="other"))
    assert seen == ["consented", "other"]


@pytest.mark.asyncio
async def test_consent_granted_helper_denies_on_every_failure():
    async def _boom(*, user_id, tenant_id):
        raise RuntimeError("down")

    async def _none(*, user_id, tenant_id):
        return None

    assert await consent_granted(None, "u", "t", 1.0) is False
    assert await consent_granted(_boom, "u", "t", 1.0) is False
    assert await consent_granted(_none, "u", "t", 1.0) is False
    assert await consent_granted(_none, "", "t", 1.0) is False


# --- wiring: the gate must be the thing the container actually installs ------


def test_container_wires_the_consent_gate_not_a_bare_judge():
    src = inspect.getsource(__import__("app.container", fromlist=["x"]))
    assert "ConsentGatedJudge(" in src
    assert "active_consent(" in src, "the gate must read the real consent table"
    assert "MemoryJudge(user_consent=" in src, (
        "the judge must be built with a resolved consent value; the bare "
        "constructor defaults user_consent=True and freezes a per-user "
        "decision into a process-wide singleton"
    )
    assert "_JudgeAdapter" not in src, "superseded by ConsentGatedJudge"


def test_privacy_check_consent_is_not_used_as_the_gate():
    """`check_consent` filters on a `scope` column no migration ever created.

    Wiring it would raise against the real database on every call, and under a
    fail-closed gate that silently disables memory for everyone. Guard against
    a well-meaning future "fix" that swaps the working reader for it.
    """
    src = inspect.getsource(__import__("services.canonical_memory.consent_gate", fromlist=["x"]))
    assert "check_consent(" not in src
