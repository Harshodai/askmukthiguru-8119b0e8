"""Tests for the Phase A1.1 meditation-hijack fix.

The pre-fix benchmark (results/query_results.json, run 2026-06-16) had three
non-cached questions returning the literal sentinel
"The meditation is complete. Thank you for practicing with me. 🙏" because:

  - intent_router classified non-imperative interrogative queries containing
    meditation nouns ("Can I practice Soul Sync on Mars?") as MEDITATION intent,
  - route_by_intent then dispatched to handle_meditation with step=0,
  - handle_meditation's start-script branches required step==1 (off-by-one) and
    fell through to format_meditation_response(0) → the sentinel.

This test module pins the fix in four layers:

  1. meditation.is_meditation_imperative correctly distinguishes imperative
     start-requests from interrogative / educational queries (incl. Hinglish).
  2. meditation.format_meditation_response returns None for out-of-range steps
     instead of leaking the sentinel.
  3. intent_prerouter.preroute_intent requires imperative + meditation noun and
     no longer matches the lone token "meditate".
  4. handle_meditation's safety net for step<=0 with no script keyword emits a
     graceful soft-fallback and sets _meditation_misroute=True (NEVER the
     sentinel).

These tests do NOT require Qdrant, Redis, Neo4j or Supabase. Heavy optional
dependencies are stubbed via sys.modules in _bootstrap_stubs() so the suite is
fully hermetic for unit-level layers 1-3. Layer 4 tests (handle_meditation)
load the full module via importlib and skip cleanly if a transitive dep is
missing in the current environment — they always run inside the docker stack.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_module_stub(name: str, attrs: dict | None = None) -> types.ModuleType:
    """Register a minimal stand-in module so heavy optional deps can be
    imported by application code without their real implementations."""
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    for key, value in (attrs or {}).items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _bootstrap_stubs() -> None:
    """Install sys.modules stubs for heavy optional dependencies."""
    qc = _install_module_stub("qdrant_client")
    qc.QdrantClient = type("QdrantClient", (), {"__init__": lambda self, *a, **kw: None})
    _install_module_stub("qdrant_client.http")
    qc_models = _install_module_stub("qdrant_client.models")
    for cls_name in (
        "Distance", "VectorParams", "SparseVectorParams", "SparseIndexParams",
        "PointStruct", "Filter", "FieldCondition", "MatchValue",
        "SparseVector", "NamedVector", "NamedSparseVector",
    ):
        setattr(qc_models, cls_name, type(cls_name, (), {"__init__": lambda self, *a, **kw: None}))
    setattr(qc_models, "Distance", type("Distance", (), {"COSINE": "Cosine"}))

    st = _install_module_stub("sentence_transformers")
    st.SentenceTransformer = type("SentenceTransformer", (), {"__init__": lambda self, *a, **kw: None})
    st.CrossEncoder = type("CrossEncoder", (), {"__init__": lambda self, *a, **kw: None})

    n4 = _install_module_stub("neo4j")
    n4.GraphDatabase = type("GraphDatabase", (), {"driver": staticmethod(lambda *a, **kw: None)})
    n4.Driver = type("Driver", (), {})

    lr = _install_module_stub("lightrag")
    lr.LightRAG = type("LightRAG", (), {"__init__": lambda self, *a, **kw: None})
    lr.QueryParam = type("QueryParam", (), {"__init__": lambda self, *a, **kw: None})

    sb = _install_module_stub("supabase")
    sb.create_client = lambda *a, **kw: None
    sb.Client = type("Client", (), {})

    for mod in (
        "FlagEmbedding",
        "lightrag.utils",
        "lightrag.llm.openai",
        "lightrag.kg.shared_storage",
    ):
        _install_module_stub(mod)


_bootstrap_stubs()


def _safe_run(coro):
    """Run an async coroutine on a fresh event loop. asyncio.get_event_loop()
    raises DeprecationWarning + RuntimeError outside an active loop in 3.12+,
    so we explicitly create-and-close one."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _load_handle_meditation():
    """Import rag.nodes.intent.handle_meditation, skipping the test if a
    transitive dep can't be satisfied in the current environment."""
    try:
        import importlib

        return importlib.import_module("rag.nodes.intent").handle_meditation
    except ModuleNotFoundError as exc:  # pragma: no cover -- env guard
        pytest.skip(f"handle_meditation import chain unavailable: {exc}")


# ---------------------------------------------------------------------------
# Layer 1 — is_meditation_imperative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Start the meditation",
        "Start meditation now",
        "Begin Serene Mind",
        "Guide me through Soul Sync",
        "Let's meditate together",
        "Take me through a meditation",
        "Lead me in a breathing exercise",
        "Open the breathing meditation",
    ],
)
def test_imperative_meditation_requests_recognised(query):
    from rag.meditation import is_meditation_imperative

    assert is_meditation_imperative(query) is True, query


@pytest.mark.parametrize(
    "query",
    [
        # The four failing benchmark queries that hit the hijack:
        "Can I practice Soul Sync on Mars or does the gravity mess up the golden light?",
        "Can I apply Spiritual Right Action to decide if I should launch a hostile takeover of a rival tech startup?",
        "What is the relationship between suffering and inner truth?",
        "Mera mind bohot dysfunctional ho gaya hai, hamesha suffering state me rehta hu. Kaise isko beautiful state me badlu?",
        # Other interrogatives that mention meditation nouns:
        "What is Soul Sync?",
        "What is Serene Mind meditation?",
        "How does Soul Sync work?",
        "Why do people meditate?",
        "Is meditation effective?",
        # Educational / FACTUAL queries that mention "meditation":
        "How do I start a meditation practice",
        "I want to learn about meditation someday",
        # Hinglish interrogatives:
        "Kaise meditation karu?",
        "Kya Soul Sync important hai?",
    ],
)
def test_interrogatives_not_classified_as_imperative(query):
    from rag.meditation import is_meditation_imperative

    assert is_meditation_imperative(query) is False, query


# ---------------------------------------------------------------------------
# Layer 2 — format_meditation_response returns None for invalid steps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_step", [-1, 0, 99, 1000])
def test_format_meditation_response_invalid_step_returns_none(invalid_step):
    from rag.meditation import format_meditation_response

    assert format_meditation_response(invalid_step) is None


@pytest.mark.parametrize("valid_step", [1, 2, 3, 4])
def test_format_meditation_response_valid_step_returns_string(valid_step):
    from rag.meditation import format_meditation_response

    out = format_meditation_response(valid_step)
    assert isinstance(out, str)
    assert "Step" in out
    assert "meditation is complete" not in out.lower()


def test_get_meditation_complete_message_emits_sentinel_only_when_called():
    """The 'meditation is complete' string MUST only be produced by the
    explicit centraliser, never by format_meditation_response."""
    from rag.meditation import get_meditation_complete_message

    msg = get_meditation_complete_message()
    assert "meditation is complete" in msg.lower()


# ---------------------------------------------------------------------------
# Layer 3 — intent_prerouter MEDITATION regex requires imperative + noun
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "imperative_query",
    [
        "start meditation",
        "let's meditate",
        "begin serene mind",
        "guide me through soul sync",
        "take me through a breathing exercise",
    ],
)
def test_prerouter_matches_imperative_meditation(imperative_query):
    from rag.intent_prerouter import preroute_intent

    assert preroute_intent(imperative_query) == "MEDITATION"


@pytest.mark.parametrize(
    "non_imperative_query",
    [
        "meditate",  # dangerous lone token from the old regex
        "I love meditation",
        "what is meditation",
        "can i practice soul sync on mars",
        "is meditation good for anxiety",
        "tell me about serene mind",
    ],
)
def test_prerouter_does_not_match_non_imperative(non_imperative_query):
    from rag.intent_prerouter import preroute_intent

    assert preroute_intent(non_imperative_query) != "MEDITATION"


# ---------------------------------------------------------------------------
# Layer 4 — handle_meditation behaviour (skipped if env lacks deps)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Can I practice Soul Sync on Mars or does the gravity mess up the golden light?",
        "What is the relationship between suffering and inner truth?",
        "Can I apply Spiritual Right Action to decide if I should launch a hostile takeover of a rival tech startup?",
        "Mera mind bohot dysfunctional ho gaya hai, hamesha suffering state me rehta hu. Kaise isko beautiful state me badlu?",
    ],
)
def test_handle_meditation_safety_net_no_sentinel(query):
    handle_meditation = _load_handle_meditation()
    state = {
        "question": query,
        "meditation_step": 0,
        "chat_history": [],
    }
    result = _safe_run(handle_meditation(state))
    answer = (result.get("final_answer") or "").lower()
    assert "the meditation is complete" not in answer, (query, result)
    assert result.get("_meditation_misroute") is True
    assert isinstance(result.get("final_answer"), str) and result["final_answer"].strip()


def test_handle_meditation_advances_through_valid_steps():
    handle_meditation = _load_handle_meditation()
    state = {
        "question": "continue",
        "meditation_step": 1,
        "chat_history": [],
    }
    result = _safe_run(handle_meditation(state))
    assert result["meditation_step"] == 2
    assert "Step 1/" in result["final_answer"]


def test_handle_meditation_emits_complete_only_when_session_actually_finished():
    handle_meditation = _load_handle_meditation()
    from rag.meditation import MAX_STEP, get_meditation_complete_message

    state = {
        "question": "next",
        "meditation_step": MAX_STEP + 1,
        "chat_history": [],
    }
    result = _safe_run(handle_meditation(state))
    assert result["final_answer"] == get_meditation_complete_message()
    assert result["meditation_step"] == 0


def test_handle_meditation_starts_soul_sync_on_first_turn():
    handle_meditation = _load_handle_meditation()
    state = {
        "question": "guide me through soul sync",
        "meditation_step": 0,
        "chat_history": [],
    }
    result = _safe_run(handle_meditation(state))
    assert "Soul Sync Meditation" in result["final_answer"]
    assert result.get("_meditation_misroute") is not True
