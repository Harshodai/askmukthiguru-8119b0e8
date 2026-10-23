"""A32 — Personalisation consent invariants (2026-10-19).

Recorded requirement: "opt-in, view and delete what is used, no cross-user
caching". Three invariants are exercised here:

  (a) opt-out yields a generic order   — with consent off, personalisation must
      not reorder or bias results.
  (b) delete removes signals           — after the delete/forget path the
      signals are genuinely gone and a later request cannot be influenced.
  (c) no cross-user caching            — a result computed with one seeker's
      personalisation is never served to another.

Each test states in its docstring exactly what change would break it. Where an
invariant does NOT hold today, the test is a strict ``xfail`` documenting the
gap (it must fail until the gap is closed, and it XPASSes — a hard CI failure —
the moment someone removes the marker by fixing the code without resetting the
expectation). Nothing here asserts a fabricated capability.

Findings (file:line as of 2026-10-19):

* Consent is a WRITE gate only. ``PUT /api/memory/consent``
  (``app/api/memory.py:788``) -> ``MemoryOutbox.record_consent``
  (``services/memory_outbox.py:52``); the reader ``active_consent``
  (``services/memory_outbox.py:76``) is consulted by ``MemoryStage`` before a
  canonical/legacy write (``app/pipeline/stages/memory_stage.py:180,241``) and
  by the canonical judge (``services/canonical_memory/consent_gate.py:40``).
* Consent is NOT consulted on the READ/application path:
  ``prepare_user_memory`` (``app/orchestrator_utils.py:861``) never calls
  ``active_consent``; it gates only on incognito + persistable-user-id
  (``app/orchestrator_utils.py:917-924``, caller ``:553-569``).
* The applied signals are the user profile's ``topics_of_interest`` /
  ``favorite_teachings``, fed into the graph at
  ``app/pipeline/stages/graph_stage.py:221-231``, used to expand the retrieval
  query (``rag/nodes/retrieval.py:1524-1533``) and to REORDER reranked docs
  (``rag/nodes/reranking.py:194-197`` -> ``services/reranker_service.py:438``).
* ``PUT /api/memory/consent`` with ``granted=False`` deletes only PENDING
  ``memory_outbox`` rows (``app/api/memory.py:808-809`` ->
  ``services/memory_outbox.py:161``); stored profile/memories survive.
* The sharpest invariant (c) HOLDS: shared caches skip personalisation-eligible
  queries (``app/pipeline/stages/cache_stage.py:32-58`` read guard, ``:553``
  write guard); the exact cache is user-scoped (``:385,478,649``); the graph
  coalescer key carries the user id (``app/pipeline/stages/graph_stage.py:72-101``)
  and the T-B14 personalize scope carries a per-seeker digest
  (``app/pipeline/pipeline_coordinator.py:89-112``).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.chat_engine import ChatEngine
from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase
from app.orchestrator_utils import prepare_user_memory
from app.pipeline.pipeline_coordinator import _personalize_scope_for
from app.pipeline.stages.cache_stage import (
    CacheCheckStage,
    CacheUpdateStage,
    _is_personalization_eligible,
)
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.graph_stage import _coalesce_key
from services.cache.hot_cache_adapter import hot_cache

USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"
CLIP_BODY = SimpleNamespace(
    personalize_teaching=SimpleNamespace(video_id="valid123456", timestamp_seconds=10.0)
)


# ---------------------------------------------------------------------------
# (a) opt-out yields a generic order
# ---------------------------------------------------------------------------


class _Mem:
    """Minimal stand-in for a stored memory row consumed by build_memory_context."""

    def __init__(self, insights: list[str]) -> None:
        self.session_id = "s-1"
        self.key_insights = insights
        self.follow_up_suggestions: list[str] = []
        self.emotional_arc: list[dict] = []


class _Profile:
    total_conversations = 0
    topics_of_interest = ["fear", "surrender"]
    favorite_teachings = ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]


class _UserProfile:
    async def get_or_create_profile(self, user_id: str) -> _Profile:
        return _Profile()

    async def update_profile(self, profile: _Profile) -> None:
        return None

    async def get_recent_memories(self, user_id: str, limit: int = 3) -> list[_Mem]:
        return [_Mem(["fear of failure"])]


class _RevokedOutbox:
    """Consent ledger whose active receipt is absent (seeker opted out)."""

    def __init__(self) -> None:
        self.reads = 0

    async def active_consent(self, *, user_id: str, tenant_id: str):
        self.reads += 1
        return None


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "A32 invariant (a) NOT IMPLEMENTED. Consent gates memory WRITES only "
        "(app/pipeline/stages/memory_stage.py:180,241). prepare_user_memory "
        "(app/orchestrator_utils.py:861-924) never consults "
        "MemoryOutbox.active_consent, so a seeker who revokes consent still "
        "receives profile/memory personalisation — the generic order promised "
        "by opt-out is never produced. Fixing this (consulting the consent "
        "ledger before serving memory_context / profile signals) will XPASS and "
        "must then be declared by removing this marker."
    ),
)
def test_opt_out_yields_a_generic_order(monkeypatch):
    """With consent revoked, no durable signal may reach the prompt.

    Breaks for a real reason if: ``prepare_user_memory`` keeps returning a
    non-empty ``memory_context`` (profile/recent-memory block) even though the
    consent ledger reports no active receipt. That is the current behaviour.
    """
    monkeypatch.setattr(
        "services.layered_memory.persona_store.get_persona",
        AsyncMock(return_value=(None, None)),
    )
    outbox = _RevokedOutbox()
    container = SimpleNamespace(
        second_brain=None,
        user_profile=_UserProfile(),
        canonical_memory_integration=None,
        memory_service=None,
        memory_service_v2=None,
        memory_outbox=outbox,
        supabase_client=None,
    )

    memory_context, _distress, _profile, _evidence = asyncio.run(
        prepare_user_memory(container, USER_A, [], user_msg_en="help me with fear")
    )

    # Opt-out: the seeker's learned signals must not colour this turn.
    assert memory_context == "", (
        f"consent revoked but personalised context was still served: {memory_context!r}"
    )


# ---------------------------------------------------------------------------
# (b) delete removes signals
# ---------------------------------------------------------------------------


class _FakeExactCache:
    """Stands in for the Redis exact cache that holds user-scoped answers."""

    def __init__(self) -> None:
        self.store = {"tenant:rel:en:what is meditation": {"response": "personalised answer"}}

    def get(self, query: str, user_id: str | None = None):
        return self.store.get(query)

    def put(self, **kwargs) -> None:  # pragma: no cover - not exercised here
        self.store[kwargs["query"]] = {"response": kwargs.get("response")}


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "A32 invariant (b) partial gap. DELETE /api/memory/all "
        "(app/api/memory.py:827-989) hard-deletes every memory store but does "
        "not invalidate the seeker's user-scoped exact-cache entry. A "
        "personalised answer cached before the delete is still read back "
        "afterwards because the exact-cache read (app/pipeline/stages/"
        "cache_stage.py:385) is unconditional and user-scoped — so a later "
        "request is still influenced by deleted signals until the 3600s TTL. "
        "Declare the fix by removing this marker."
    ),
)
def test_delete_all_invalidates_the_callers_cached_answers():
    """After erasing memories, cached answers derived from them must be gone.

    Breaks for a real reason if: the delete endpoint leaves the caller's cached
    personalised answer in place (it does today — the endpoint never touches
    ``exact_cache``).
    """
    fake_cache = _FakeExactCache()
    container = SimpleNamespace(exact_cache=fake_cache)
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": USER_A}
    app.dependency_overrides[get_container] = lambda: container
    try:
        resp = TestClient(app).delete("/api/memory/all")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    assert fake_cache.store == {}, (
        "deleted signals still influence later requests via the user-scoped "
        f"answer cache: {fake_cache.store!r}"
    )


def test_delete_all_hard_deletes_the_ordering_signals():
    """The full erase must remove the profile/memory rows that drive ordering.

    Guard (HOLDS). Breaks for a real reason if: the endpoint's table list
    (app/api/memory.py:871-888) drops ``user_profiles`` (topics_of_interest /
    favorite_teachings — the signals that reorder retrieval), or
    ``conversation_memories`` / ``canonical_memories`` / ``guru_memories``,
    leaving what we know about the seeker behind a "delete everything" promise.
    """

    class _Supabase:
        def __init__(self) -> None:
            self.tables: list[str] = []

        def table(self, name: str):
            outer = self

            class _Q:
                def delete(self):
                    return self

                def eq(self, column, value):
                    outer.tables.append(name)
                    assert column == "user_id"
                    return self

                def execute(self):
                    return SimpleNamespace(data=[{"id": 1}])

            return _Q()

    supabase = _Supabase()
    container = SimpleNamespace(supabase_client=supabase)
    app.dependency_overrides[get_current_user_from_supabase] = lambda: {"id": USER_A}
    app.dependency_overrides[get_container] = lambda: container
    try:
        resp = TestClient(app).delete("/api/memory/all")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    erased = set(supabase.tables)
    expected = {"user_profiles", "conversation_memories", "canonical_memories", "guru_memories"}
    assert expected <= erased, f"not erased: {expected - erased}"


# ---------------------------------------------------------------------------
# (c) no cross-user caching
# ---------------------------------------------------------------------------


def test_graph_coalescer_key_is_seeker_scoped():
    """Two seekers asking the same text must never coalesce onto one graph run.

    Guard (HOLDS). Breaks for a real reason if: ``_coalesce_key`` drops
    ``user_id`` (app/pipeline/stages/graph_stage.py:72-101) — a personalised
    result from one seeker could then be handed to another.
    """
    args = ("en", "what is meditation", "hh", "", 0, "", "")
    key_a = _coalesce_key(USER_A, "sess", *args)
    key_b = _coalesce_key(USER_B, "sess", *args)
    assert key_a != key_b
    assert USER_A in key_a and USER_A not in key_b


def test_chat_engine_coalesce_key_is_seeker_scoped():
    """The batch coalescer key must carry the seeker id too.

    Guard (HOLDS). Breaks for a real reason if: ``_build_coalesce_key``
    (app/chat_engine.py:241-252) drops ``user_id``.
    """
    engine = ChatEngine(container=MagicMock())
    key_a = engine._build_coalesce_key("what is meditation", USER_A, "sess", None, "en")
    key_b = engine._build_coalesce_key("what is meditation", USER_B, "sess", None, "en")
    assert key_a != key_b
    assert USER_A in key_a and USER_B in key_b


def test_personalize_scope_is_per_seeker_and_bounded():
    """The same clip personalised by two seekers must not share a cache scope.

    Guard (HOLDS). Breaks for a real reason if: ``_personalize_scope_for``
    (app/pipeline/pipeline_coordinator.py:89-112) drops the seeker digest or
    leaks the raw user id.
    """
    scope_a = _personalize_scope_for(CLIP_BODY, {"id": USER_A})
    scope_b = _personalize_scope_for(CLIP_BODY, {"id": USER_B})
    assert scope_a and scope_b
    assert scope_a != scope_b
    assert USER_A not in scope_a and USER_B not in scope_b


def test_personalisation_eligible_reads_skip_the_shared_hot_cache():
    """An eligible seeker must never be served a shared (generic) hot entry.

    Guard (HOLDS). Breaks for a real reason if: the read guard in
    CacheCheckStage (app/pipeline/stages/cache_stage.py:251) is moved below the
    hot-cache read — a personalised query would then replay an answer cached
    for a different seeker.
    """
    cache_key = "a32:test:personalisation:hot"
    container = SimpleNamespace(
        exact_cache=SimpleNamespace(get=lambda query, user_id=None: None),
        semantic_cache=None,
    )
    hot_cache.invalidate(cache_key)
    hot_cache.put(cache_key, "GENERIC ANSWER FOR SOMEBODY ELSE", [], ttl=60.0, intent="QUERY")
    try:
        eligible = PipelineContext(
            container=container,
            coordinator=None,
            request=SimpleNamespace(),
            user_msg="what is meditation",
            query_for_embedding="what is meditation",
            preferred_lang="en",
            cache_key=cache_key,
            personalization_eligible=True,
            user_id=USER_A,
        )
        eligible_result = asyncio.run(CacheCheckStage().run(eligible))
        # Eligible must fall through to a miss; it must not receive the shared entry.
        assert eligible_result is None, "personalisation-eligible query read a shared cache entry"

        # Control: the same setup, not eligible, DOES hit — proving the guard is what blocks it.
        plain = PipelineContext(
            container=container,
            coordinator=None,
            request=SimpleNamespace(),
            user_msg="what is meditation",
            query_for_embedding="what is meditation",
            preferred_lang="en",
            cache_key=cache_key,
            personalization_eligible=False,
            user_id="anonymous",
        )
        plain_result = asyncio.run(CacheCheckStage().run(plain))
        assert plain_result is not None and plain_result.cache_hit is True
        assert plain_result.final_answer == "GENERIC ANSWER FOR SOMEBODY ELSE"
    finally:
        hot_cache.invalidate(cache_key)


def test_personalised_answer_is_not_written_to_the_shared_hot_cache():
    """A personalised answer must be written user-scoped, never to the shared tier.

    Guard (HOLDS). Breaks for a real reason if: the write guard in
    CacheUpdateStage (app/pipeline/stages/cache_stage.py:638) is removed, letting
    one seeker's personalised answer enter the process-wide hot cache.
    """
    cache_key = "a32:test:personalisation:write"
    hot_cache.invalidate(cache_key)

    class _RecordingExactCache:
        def __init__(self) -> None:
            self.puts: list[dict] = []

        # Sync on purpose: CacheUpdateStage invokes it via asyncio.to_thread.
        def put(self, **kwargs) -> None:
            self.puts.append(kwargs)

    exact = _RecordingExactCache()
    ctx = PipelineContext(
        container=SimpleNamespace(exact_cache=exact, semantic_cache=None),
        coordinator=None,
        request=SimpleNamespace(),
        user_msg="what is meditation",
        query_for_embedding="what is meditation",
        preferred_lang="en",
        cache_key=cache_key,
        user_id=USER_A,
        personalization_eligible=True,
        state={"memory_context": "seekers's own context"},
        final_answer="A personalised reflection.",
        intent="QUERY",
        citations=[{"id": "c1"}],
        graph_result={},
    )
    try:
        asyncio.run(CacheUpdateStage().run(ctx))
        # User-scoped write happened...
        assert exact.puts and exact.puts[0].get("user_id") == USER_A
        # ...and the shared hot cache stayed empty for this key.
        assert hot_cache.get(cache_key) is None
    finally:
        hot_cache.invalidate(cache_key)


def test_personalization_predicate_reads_state_fallback():
    """The write guard must still see personalisation via state when the probe missed.

    Guard (HOLDS). Breaks for a real reason if: ``_is_personalization_eligible``
    (app/pipeline/stages/cache_stage.py:32-58) stops consulting
    ``ctx.state["memory_context"]`` — a probe miss would let a personalised
    response be cached under a shared key.
    """
    ctx = PipelineContext(
        container=None,
        coordinator=None,
        request=SimpleNamespace(),
        state={"memory_context": "seekers's own context"},
        personalization_eligible=False,
    )
    assert _is_personalization_eligible(ctx) is True
