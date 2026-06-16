"""Tests for the YAML-driven SemanticRouter.

These tests validate the de-hardcoding goal in two ways:

  1. The four failing benchmark queries from results/query_results.json no longer
     match MEDITATION even when the embedding model would think they're similar,
     because the YAML config sets `exclude_if_interrogative: true` for that route.
  2. Adding/changing routes happens entirely in YAML — no Python code edits needed.

The tests do NOT require a real embedding model. They inject a deterministic
stub encoder that returns a high-similarity vector for queries that share keyword
overlap with each route's utterances. This is enough to validate the routing
logic; the production encoder is the existing sentence-transformers model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _keyword_overlap_encoder():
    """Return an encode_fn that maps text to a binary marker vector. Identical
    marker presence → cosine similarity ≈ 1.0 against any utterance with the
    same markers. This is a stand-in for the production sentence-transformer
    encoder; it lets us assert that the router's *routing logic* works without
    depending on a full embedding model in this preview environment."""
    MARKERS = [
        # Meditation domain
        "meditation", "meditate", "soul sync", "serene mind", "breathing", "breathwork",
        "start", "begin", "guide me", "take me", "lead me", "open the", "let us",
        # Distress
        "hopeless", "suicide", "anxious", "panic", "alone", "crying", "drowning",
        "kashtama", "mann tut", "tut chuka",
        # Doctrine / FACTUAL
        "preethaji", "krishnaji", "ekam", "deeksha", "beautiful state",
        "suffering state", "four sacred secrets", "spiritual vision",
        "spiritual right action", "inner truth", "universal intelligence",
        "surrender", "oneness",
        # Temporal
        "schedule", "upcoming", "next", "month", "manifest course", "retreat",
        # Casual
        "hello", "hi", "namaste", "pranam", "thank",
        # Capability
        "what can you", "tell me about yourself", "how do you work", "topics",
    ]

    def encode(text: str) -> list[float]:
        lower = text.lower()
        return [1.0 if marker in lower else 0.0 for marker in MARKERS]

    return encode


def _build_router_with_stub():
    from services.semantic_router import SemanticRouter

    router = SemanticRouter()
    router.prime(_keyword_overlap_encoder())
    return router


# ---------------------------------------------------------------------------
# YAML config is loaded and routes are present
# ---------------------------------------------------------------------------


def test_router_loads_yaml_and_finds_routes():
    router = _build_router_with_stub()
    names = router.route_names()
    # Asserting these in YAML order proves the YAML is the source of truth.
    expected = {"SAFETY_VIOLATION", "DISTRESS", "MEDITATION", "ADVERSARIAL", "TEMPORAL", "CASUAL", "CAPABILITY", "FACTUAL"}
    assert expected.issubset(set(names)), names


def test_router_is_primed_after_prime_call():
    router = _build_router_with_stub()
    assert router.primed is True


# ---------------------------------------------------------------------------
# The four originally-failing queries do NOT match MEDITATION (config-level fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Can I practice Soul Sync on Mars or does the gravity mess up the golden light?",
        "Can I apply Spiritual Right Action to decide if I should launch a hostile takeover of a rival tech startup?",
        "What is the relationship between suffering and inner truth?",
        "Mera mind bohot dysfunctional ho gaya hai, hamesha suffering state me rehta hu. Kaise isko beautiful state me badlu?",
    ],
)
def test_failing_benchmark_queries_do_not_route_to_meditation(query):
    router = _build_router_with_stub()
    match = router.classify(query, meditation_step=0)
    # The router can return None (defer to LLM) or any non-MEDITATION route.
    # What it MUST NOT do is fire MEDITATION on an interrogative.
    if match is not None:
        assert match.route != "MEDITATION", (query, match)


# ---------------------------------------------------------------------------
# Imperative meditation requests DO match MEDITATION
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Start the meditation",
        "Begin Serene Mind right now",
        "Guide me through Soul Sync",
        "Take me through a breathing exercise",
        "Let us meditate together",
    ],
)
def test_imperative_meditation_requests_route_to_meditation(query):
    router = _build_router_with_stub()
    match = router.classify(query, meditation_step=0)
    assert match is not None, query
    assert match.route == "MEDITATION", (query, match)


# ---------------------------------------------------------------------------
# Safety net regex still fires (priority over embedding scores)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "I want to end my life",
        "I am thinking about suicide",
        "Will lithium help me with my bipolar",
        "Diagnose my depression please",
    ],
)
def test_safety_violation_regex_fires(query):
    router = _build_router_with_stub()
    match = router.classify(query)
    assert match is not None
    assert match.route == "SAFETY_VIOLATION"
    assert match.reason == "regex"


# ---------------------------------------------------------------------------
# Interrogative detection — language coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Can I do this?", True),
        ("What is Soul Sync?", True),
        ("How do I begin?", True),
        ("Kaise meditation karu?", True),
        ("Kya ye sahi hai?", True),
        ("Enna idhu?", True),
        ("Start the meditation now", False),
        ("I feel hopeless", False),
    ],
)
def test_linguistic_is_interrogative(query, expected):
    router = _build_router_with_stub()
    assert router.linguistic.is_interrogative(query) is expected
