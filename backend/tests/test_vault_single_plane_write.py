"""Single-plane vault learning: ONE write path behind `feature_memory_write`.

Owner decision ("don't build duplicate, wire all at one"): the vault miner
(`SecondBrainService.extract_and_write`, previously zero production callers)
rides MemoryStage's canonical-write task — same task, same consent receipt,
no second fetch. Read/injection stays exactly where it is (the orchestrator's
`prepare_user_memory`); this change adds only the write leg.

All LLM/I/O surface is faked (FakeLLM/FakeDB/FakeEmbed/FakeVaultIndex are
local doubles — zero real LLM calls, zero prod DB). `app/config.py` is never
mutated here: tests flip the EXISTING flag via monkeypatch only.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "BRAIN_KEK", "dGVzdC1vcGVyYXRvci1rZWstMzItYnl0ZXMteHh4eHg="
)  # test only, decodes to 32B

from app.config import Settings, settings  # noqa: E402
from app.pipeline.stages import memory_stage  # noqa: E402
from app.pipeline.stages.context import PipelineContext  # noqa: E402
from app.pipeline.stages.memory_stage import (  # noqa: E402
    MemoryStage,
    _vault_write_enabled,
    _write_vault_turn,
)
from services.second_brain.second_brain_service import SecondBrainService  # noqa: E402
from tests.test_second_brain import FakeDB, FakeEmbed, FakeVaultIndex  # noqa: E402

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())

TURN_MSG = "I sit for meditation every morning but my mind keeps wandering."
TURN_ANSWER = "That is a beautiful practice. Keep returning gently to the breath."

# Sentinel: distinguishes "no consent arg passed" (default receipt) from an
# explicit None (consent denied). Must precede the fakes that use it.
_UNSET = object()
_UNSET_SENTINEL = _UNSET


# ---------------------------------------------------------------------------
# Fakes (local doubles only — no network, no prod DB, no real LLM)
# ---------------------------------------------------------------------------


class FakeVault:
    """Minimal UnlockedVault double: context manager + per-user DEK identity."""

    def __init__(self, owner: str):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


class FakeSecondBrain:
    """Counts every write-leg and read-leg call; never touches the network."""

    def __init__(self, written: int = 1):
        self._written = written
        self.unlock_calls: list[str] = []
        self.extract_calls: list[tuple] = []
        self.read_calls: list[tuple] = []

    async def unlock(self, user_id: str, **_kw):
        self.unlock_calls.append(user_id)
        return FakeVault(user_id)

    async def extract_and_write(self, user_id, message, response, *, vault):
        self.extract_calls.append((user_id, message, response, vault))
        return self._written

    async def personal_context(self, user_id, query, *, vault, limit=5):
        self.read_calls.append((user_id, query))
        return []


class FakeOutbox:
    """Consent store double with a call counter (single-fetch proof)."""

    def __init__(self, consent: dict | None | object = _UNSET_SENTINEL):
        if consent is _UNSET_SENTINEL:
            consent = {"id": "receipt-1"}
        self._consent = consent
        self.consent_calls: list[tuple] = []
        self.enqueued: list[dict] = []

    async def active_consent(self, *, user_id, tenant_id):
        self.consent_calls.append((user_id, tenant_id))
        return self._consent

    async def enqueue(self, **kwargs):
        self.enqueued.append(kwargs)
        return {"id": "row-1"}


class TypedFakeLLM:
    """Fake LLM returning typed multi-kind candidates (one below the bar)."""

    async def generate(self, system_prompt, user_prompt, **_kw):
        return (
            '{"items":['
            '{"kind":"reflection","text":"User meditates each morning.","confidence":0.9},'
            '{"kind":"preference","text":"User prefers morning practice.","confidence":0.75},'
            '{"kind":"journal","text":"User noted a wandering mind today.","confidence":0.2}'
            "]}"
        )


def _ctx(container, user_id: str = USER_A, **overrides) -> PipelineContext:
    base = dict(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=TURN_MSG,
        preferred_lang="en",
        meditation_step=0,
        session_id="sess-1",
        user={"id": user_id},
        is_benchmark=False,
        stream_queue=None,
        trace_id="trace-vault-1",
        start_time=0.0,
        cache_key="ck",
        query_for_embedding=TURN_MSG,
        is_indic=False,
        user_id=user_id,
        stable_session_id="sess-1",
        chat_body_messages=[],
        state={},
        final_answer=TURN_ANSWER,
        intent="QUERY",
        med_step=0,
        citations=[],
        assessment=None,
    )
    base.update(overrides)
    return PipelineContext(**base)


def _container(*, second_brain=None, consent=_UNSET, canonical=None):
    return SimpleNamespace(
        second_brain=second_brain,
        memory_outbox=FakeOutbox({"id": "receipt-1"} if consent is _UNSET else consent),
        canonical_memory_integration=canonical,
        memory_service=None,
        user_profile=None,
    )


async def _drain_write_tasks():
    pending = [t for t in list(memory_stage._CANONICAL_WRITE_TASKS) if not t.done()]
    if pending:
        await asyncio.gather(*pending)


def _mute_celery_dispatch(monkeypatch):
    """Keep run() synchronous: the Celery publish becomes an instant no-op."""
    import tasks.memory_outbox_tasks as outbox_tasks

    monkeypatch.setattr(
        outbox_tasks.drain_memory_outbox, "apply_async", lambda *a, **k: {"id": "mock"}
    )


# ---------------------------------------------------------------------------
# Flag posture: default stays False (consent proof required before flip)
# ---------------------------------------------------------------------------


def test_vault_write_defaults_to_disabled():
    assert Settings().feature_memory_write is False


def test_vault_write_enabled_tracks_existing_flag(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", False)
    assert _vault_write_enabled() is False
    monkeypatch.setattr(settings, "feature_memory_write", True)
    assert _vault_write_enabled() is True


# ---------------------------------------------------------------------------
# Helper leg: flag-off / flag-on / anonymous / fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_means_zero_vault_writes(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", False)
    sb = FakeSecondBrain()
    n = await _write_vault_turn(
        container=_container(second_brain=sb),
        user_id=USER_A,
        user_msg=TURN_MSG,
        final_answer=TURN_ANSWER,
    )
    assert n == 0
    assert sb.unlock_calls == []
    assert sb.extract_calls == []


@pytest.mark.asyncio
async def test_flag_on_writes_typed_candidates_encrypted(monkeypatch):
    """End-to-end through the REAL service with a fake LLM: typed items land
    encrypted (AES per-user scoping), low-confidence noise is dropped."""
    monkeypatch.setattr(settings, "feature_memory_write", True)
    svc = SecondBrainService(FakeDB(), FakeEmbed(), TypedFakeLLM(), FakeVaultIndex())
    await svc.provision_vault(USER_A)
    container = _container(second_brain=svc)
    n = await _write_vault_turn(
        container=container, user_id=USER_A, user_msg=TURN_MSG, final_answer=TURN_ANSWER
    )
    assert n == 2  # 0.9 + 0.75 written; 0.2 dropped below the 0.6 bar
    with await svc.unlock(USER_A) as vault:
        items = await svc.list_items(USER_A, vault=vault)
    kinds = {i.kind for i in items}
    assert kinds == {"reflection", "preference"}
    assert len(items) == 2
    raw_rows = svc._db.store["user_brain_nodes"]
    assert all(r["user_id"] == USER_A for r in raw_rows)
    for row in raw_rows:
        assert "meditates" not in row["ciphertext"]
        assert "morning practice" not in row["ciphertext"]


@pytest.mark.asyncio
@pytest.mark.parametrize("anon_id", ["anonymous", "anon:token-123", "", "not-a-uuid", None])
async def test_anonymous_users_are_rejected(monkeypatch, anon_id):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    sb = FakeSecondBrain()
    n = await _write_vault_turn(
        container=_container(second_brain=sb),
        user_id=anon_id,
        user_msg=TURN_MSG,
        final_answer=TURN_ANSWER,
    )
    assert n == 0
    assert sb.unlock_calls == []
    assert sb.extract_calls == []


@pytest.mark.asyncio
async def test_empty_answer_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    sb = FakeSecondBrain()
    n = await _write_vault_turn(
        container=_container(second_brain=sb),
        user_id=USER_A,
        user_msg=TURN_MSG,
        final_answer="",
    )
    assert n == 0
    assert sb.unlock_calls == []


@pytest.mark.asyncio
async def test_no_second_brain_service_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    n = await _write_vault_turn(
        container=_container(second_brain=None),
        user_id=USER_A,
        user_msg=TURN_MSG,
        final_answer=TURN_ANSWER,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_vault_failure_is_fail_open(monkeypatch):
    """Memory failure never breaks chat: unlock/expiry errors yield 0, never raise."""
    monkeypatch.setattr(settings, "feature_memory_write", True)

    class LockedBrain(FakeSecondBrain):
        async def unlock(self, user_id: str, **_kw):
            self.unlock_calls.append(user_id)
            raise RuntimeError("KEK unavailable")

    assert (
        await _write_vault_turn(
            container=_container(second_brain=LockedBrain()),
            user_id=USER_A,
            user_msg=TURN_MSG,
            final_answer=TURN_ANSWER,
        )
        == 0
    )

    class ExplodingBrain(FakeSecondBrain):
        async def extract_and_write(self, user_id, message, response, *, vault):
            raise RuntimeError("db down")

    assert (
        await _write_vault_turn(
            container=_container(second_brain=ExplodingBrain()),
            user_id=USER_A,
            user_msg=TURN_MSG,
            final_answer=TURN_ANSWER,
        )
        == 0
    )


# ---------------------------------------------------------------------------
# Cross-user isolation: per-user unlock scope + AES AAD binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_isolation(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    sb = FakeSecondBrain()
    for uid in (USER_A, USER_B):
        n = await _write_vault_turn(
            container=_container(second_brain=sb),
            user_id=uid,
            user_msg=TURN_MSG,
            final_answer=TURN_ANSWER,
        )
        assert n == 1
    # Each turn unlocked exactly its own vault; the vault handed to the miner
    # is the one unlocked for that same user (per-user AES scoping).
    assert sb.unlock_calls == [USER_A, USER_B]
    assert [c[0] for c in sb.extract_calls] == [USER_A, USER_B]
    for (uid, _msg, _resp, vault), unlocked in zip(sb.extract_calls, sb.unlock_calls):
        assert vault.owner == uid == unlocked


@pytest.mark.asyncio
async def test_cross_user_ciphertext_does_not_decrypt(monkeypatch):
    """Crypto-level proof: B's DEK cannot open A's row (AAD binds user_id)."""
    monkeypatch.setattr(settings, "feature_memory_write", True)
    svc = SecondBrainService(FakeDB(), FakeEmbed(), TypedFakeLLM(), FakeVaultIndex())
    await svc.provision_vault(USER_A)
    await svc.provision_vault(USER_B)
    container = _container(second_brain=svc)
    assert (
        await _write_vault_turn(
            container=container, user_id=USER_A, user_msg=TURN_MSG, final_answer=TURN_ANSWER
        )
        == 2
    )
    from services.second_brain.crypto import VaultIntegrityError, decrypt_payload

    rows = svc._db.store["user_brain_nodes"]
    assert rows and all(r["user_id"] == USER_A for r in rows)
    with await svc.unlock(USER_B) as vault_b:
        assert await svc.list_items(USER_B, vault=vault_b) == []
        for row in rows:
            with pytest.raises(VaultIntegrityError):
                decrypt_payload(
                    vault_b.dek,
                    row["ciphertext"],
                    aad=f"{USER_A}:{row['kind']}:{row['id']}".encode(),
                )
    assert svc._qdrant.points.get(USER_B, {}) == {}


# ---------------------------------------------------------------------------
# Stage wiring: ONE vault write, ONE consent fetch, ZERO injection fetches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_turn_triggers_single_vault_write_no_double_fetch(monkeypatch):
    """A chat turn triggers at most ONE vault write and ONE injection fetch.

    ONE vault write: extract_and_write called exactly once for the turn.
    ONE injection fetch: the read/injection point is untouched — the stage
    performs zero memory reads (personal_context) and never invokes the
    orchestrator's prepare_user_memory or the deferred inject_memory_context
    node, so the existing single injection point cannot double-fetch.
    ONE consent fetch: the single-plane task reuses one active_consent
    receipt for both legs (no second consent round-trip from the vault leg).
    """
    monkeypatch.setattr(settings, "feature_memory_write", True)
    _mute_celery_dispatch(monkeypatch)
    sb = FakeSecondBrain()
    container = _container(second_brain=sb, canonical=None)

    import app.orchestrator_utils as orch_utils
    import rag.memory as rag_memory

    prepare_spy = MagicMock(side_effect=AssertionError("must not be called"))
    inject_spy = MagicMock(side_effect=AssertionError("must not be called"))
    monkeypatch.setattr(orch_utils, "prepare_user_memory", prepare_spy)
    monkeypatch.setattr(rag_memory, "inject_memory_context", inject_spy)

    outbox = container.memory_outbox
    legacy_consent_before = len(outbox.consent_calls)
    assert await MemoryStage().run(_ctx(container)) is None
    await _drain_write_tasks()
    # Exactly TWO consent fetches total: one inline in the legacy outbox path
    # (flag-on behavior, unchanged) and ONE inside the single-plane task,
    # shared by the canonical leg and the vault leg — the vault leg performs
    # no second consent round-trip of its own.
    assert len(outbox.consent_calls) == legacy_consent_before + 2

    assert len(sb.extract_calls) == 1
    uid, msg, resp, vault = sb.extract_calls[0]
    assert uid == USER_A
    assert msg == TURN_MSG and resp == TURN_ANSWER
    assert vault.owner == USER_A
    assert sb.unlock_calls == [USER_A]
    assert sb.read_calls == []
    prepare_spy.assert_not_called()
    inject_spy.assert_not_called()


@pytest.mark.asyncio
async def test_run_flag_off_schedules_no_vault_work(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", False)
    sb = FakeSecondBrain()
    container = _container(second_brain=sb, canonical=None)
    ctx = _ctx(container, final_answer="")  # no answer: no task at all either
    assert await MemoryStage().run(ctx) is None
    await _drain_write_tasks()
    assert sb.unlock_calls == []
    assert sb.extract_calls == []


@pytest.mark.asyncio
async def test_run_vault_leg_needs_no_canonical_plane(monkeypatch):
    """Vault learning does not depend on the canonical plane being wired."""
    monkeypatch.setattr(settings, "feature_memory_write", True)
    monkeypatch.setattr(settings, "memory_write", False)
    _mute_celery_dispatch(monkeypatch)
    sb = FakeSecondBrain()
    container = _container(second_brain=sb, canonical=MagicMock())
    assert await MemoryStage().run(_ctx(container)) is None
    await _drain_write_tasks()
    assert len(sb.extract_calls) == 1


@pytest.mark.asyncio
async def test_run_without_consent_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    sb = FakeSecondBrain()
    container = _container(second_brain=sb, consent=None)
    assert await MemoryStage().run(_ctx(container)) is None
    await _drain_write_tasks()
    assert sb.unlock_calls == []
    assert sb.extract_calls == []


@pytest.mark.asyncio
async def test_run_incognito_and_anonymous_skip_vault(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    sb = FakeSecondBrain()
    container = _container(second_brain=sb, canonical=None)
    assert await MemoryStage().run(_ctx(container, incognito=True)) is None
    assert await MemoryStage().run(_ctx(container, user_id="anonymous")) is None
    await _drain_write_tasks()
    assert sb.unlock_calls == []
    assert sb.extract_calls == []


@pytest.mark.asyncio
async def test_run_vault_failure_never_breaks_chat(monkeypatch):
    monkeypatch.setattr(settings, "feature_memory_write", True)
    _mute_celery_dispatch(monkeypatch)

    class LockedBrain(FakeSecondBrain):
        async def unlock(self, user_id: str, **_kw):
            raise RuntimeError("KEK unavailable")

    container = _container(second_brain=LockedBrain(), canonical=None)
    assert await MemoryStage().run(_ctx(container)) is None
    await _drain_write_tasks()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
