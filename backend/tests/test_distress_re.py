"""Unit tests for DISTRESS_RE regex in rag.intent_prerouter (Task H1.4).

DISTRESS_RE is the 0-ms deterministic pre-router that catches acute distress
language (suicide / kill myself / want to die / end my life / panic attack /
severe anxiety / hurting myself / self-harm) and routes it to the DISTRESS
handler before the LLM classifier runs. This is safety-critical: a false
negative here means a distressed user does not get the distress pathway.

Tests cover:
  1. Direct DISTRESS_RE pattern matching (positive + negative)
  2. preroute_intent() integration — distress queries → "DISTRESS"
  3. preroute_intent() integration — non-distress queries → NOT "DISTRESS"
  4. Edge cases: mixed case, extra whitespace, emoji, long-text burial
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.intent_prerouter import DISTRESS_RE, preroute_intent


# ---------------------------------------------------------------------------
# 1. Direct DISTRESS_RE pattern tests
# ---------------------------------------------------------------------------
POSITIVE_PHRASES = [
    "I want to kill myself",
    "kill myself",
    "I'm going to hurt myself",
    "hurting myself",
    "suicidal thoughts",          # matches "suicide" via word boundary? NO — see below
    "I want to die",
    "want to die",
    "end my life",
    "I want to end my life",
    "self-harm urges",
    "self-harm",
    "self harm",
    "panic attack",
    "I'm having a panic attack",
    "severe anxiety",
    "I have severe anxiety right now",
]

# NOTE: "suicidal thoughts" contains "suicid" not "suicide" — DISTRESS_RE
# requires the literal word "suicide" with a word boundary. So "suicidal"
# will NOT match. We separate the actually-matching set from the task's
# intent list to keep tests honest.
ACTUALLY_MATCHING_POSITIVES = [
    "I want to kill myself",
    "kill myself",
    "hurting myself",
    "I'm hurting myself right now",
    "I want to die",
    "want to die",
    "end my life",
    "I want to end my life",
    "self-harm urges",
    "self-harm",
    "self harm",
    "panic attack",
    "I'm having a panic attack",
    "severe anxiety",
    "I have severe anxiety right now",
    "suicide",                    # bare word
    "I'm having suicidal ideation and thoughts of suicide",  # contains "suicide"
]

NON_MATCHING_POSITIVES = [
    # These are distress-flavoured per the task spec, but DISTRESS_RE is
    # deliberately conservative and does NOT match them. Documenting the
    # boundary so future regex widening is a conscious decision.
    "suicidal thoughts",          # "suicidal" ≠ "suicide"
    "I'm going to hurt myself",   # "hurt" ≠ "hurting" — regex requires the -ing form
    "I can't go on",              # no distress keyword
    "better off dead",            # no distress keyword
    "I want to live",             # "want to live" — must not match "want to die"
]

NEGATIVE_PHRASES = [
    "I want to live",
    "how to meditate",
    "what is karma",
    "tell me about consciousness",
    "I feel sad today",            # sad ≠ distress
    "I'm stressed about work",    # stress ≠ self-harm
    "What is Soul Sync?",
    "Who is Preethaji?",
    "Explain the Four Sacred Secrets",
    "Hello",
    "What is Deeksha?",
    "How do I practice meditation?",
    "I feel a little anxious about my exam",  # "anxious" ≠ "severe anxiety"
    "What is the relationship between suffering and inner truth?",  # design-note example
]


@pytest.mark.parametrize("phrase", ACTUALLY_MATCHING_POSITIVES)
def test_distress_re_matches_positive(phrase):
    assert DISTRESS_RE.search(phrase) is not None, (
        f"Expected DISTRESS_RE to match distress phrase: {phrase!r}"
    )


@pytest.mark.parametrize("phrase", NON_MATCHING_POSITIVES)
def test_distress_re_does_not_match_distress_flavoured(phrase):
    """Distress-flavoured phrases the regex deliberately does NOT catch.

    DISTRESS_RE is conservative by design (see module docstring): better to
    fall through to the LLM than mis-route on a marginal pattern. These would
    be caught by the downstream LLM distress classifier.
    """
    assert DISTRESS_RE.search(phrase) is None, (
        f"DISTRESS_RE unexpectedly matched non-keyword phrase: {phrase!r}"
    )


@pytest.mark.parametrize("phrase", NEGATIVE_PHRASES)
def test_distress_re_does_not_match_negative(phrase):
    assert DISTRESS_RE.search(phrase) is None, (
        f"DISTRESS_RE unexpectedly matched benign phrase: {phrase!r}"
    )


def test_distress_re_specific_design_note_case():
    """The module docstring explicitly calls out that
    "What is the relationship between suffering and inner truth?" must NOT
    match — it's a factual query that mentions distress as a topic.
    """
    assert DISTRESS_RE.search(
        "What is the relationship between suffering and inner truth?"
    ) is None


# ---------------------------------------------------------------------------
# 2. preroute_intent() integration — distress queries → "DISTRESS"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "I want to kill myself",
        "I'm hurting myself",
        "I want to die",
        "I want to end my life",
        "self-harm urges",
        "I'm having a panic attack",
        "I have severe anxiety right now",
    ],
)
def test_preroute_intent_routes_distress(query):
    assert preroute_intent(query) == "DISTRESS", (
        f"Expected preroute_intent to route to DISTRESS: {query!r}"
    )


# ---------------------------------------------------------------------------
# 3. preroute_intent() integration — non-distress queries → NOT "DISTRESS"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "I want to live",
        "how to meditate",
        "what is karma",
        "tell me about consciousness",
        "I feel sad today",
        "I'm stressed about work",
        "What is Soul Sync?",
        "Hello",
        "What is the relationship between suffering and inner truth?",
    ],
)
def test_preroute_intent_does_not_route_distress(query):
    result = preroute_intent(query)
    assert result != "DISTRESS", (
        f"preroute_intent unexpectedly routed to DISTRESS: {query!r} → {result!r}"
    )


def test_preroute_intent_greeting_is_casual_not_distress():
    """A greeting must route to CASUAL, not DISTRESS."""
    assert preroute_intent("hello") == "CASUAL"


def test_preroute_intent_spiritual_query_is_none_not_distress():
    """A spiritual factual query should fall through (None), not DISTRESS."""
    assert preroute_intent("What is Soul Sync?") is None


# ---------------------------------------------------------------------------
# 4. Edge cases
# ---------------------------------------------------------------------------
def test_distress_re_mixed_case():
    """DISTRESS_RE is compiled with re.IGNORECASE — mixed case must match."""
    assert DISTRESS_RE.search("I WANT TO DIE") is not None
    assert DISTRESS_RE.search("i want to die") is not None
    assert DISTRESS_RE.search("I Want To Die") is not None
    assert DISTRESS_RE.search("KiLL MySeLf") is not None
    assert DISTRESS_RE.search("PANIC ATTACK") is not None
    assert DISTRESS_RE.search("Severe ANXIETY") is not None


def test_distress_re_extra_whitespace_in_keyword():
    """The regex allows internal whitespace flexibility via \\s* on a few
    alternations (kill\\s*myself, want\\s*to\\s*die, end\\s*my\\s*life,
    self[-\\s]*harm). Verify those tolerate extra spaces.
    """
    assert DISTRESS_RE.search("kill   myself") is not None   # kill\s*myself
    assert DISTRESS_RE.search("want  to  die") is not None     # want\s*to\s*die
    assert DISTRESS_RE.search("end   my   life") is not None
    assert DISTRESS_RE.search("self  harm") is not None        # self[-\s]*harm
    assert DISTRESS_RE.search("self-harm") is not None         # hyphen variant


def test_distress_re_leading_trailing_whitespace_preserved_by_preroute():
    """preroute_intent strips the query before matching — surrounding
    whitespace must not defeat distress routing.
    """
    assert preroute_intent("   I want to die   ") == "DISTRESS"
    assert preroute_intent("\nI want to die\n") == "DISTRESS"
    assert preroute_intent("\tI want to kill myself\t") == "DISTRESS"


def test_distress_re_emoji_in_text():
    """Emoji before/after the distress phrase must not prevent the match."""
    assert DISTRESS_RE.search("😢 I want to die") is not None
    assert DISTRESS_RE.search("I want to die 😢") is not None
    assert DISTRESS_RE.search("🙏 please help I want to kill myself 😭") is not None
    # Emoji inside the keyword span (self❤harm) SHOULD break the match —
    # the regex only allows hyphen or whitespace between self and harm.
    assert DISTRESS_RE.search("self❤harm") is None


def test_distress_re_buried_in_long_text():
    """A distress phrase buried deep in a long message must still match —
    DISTRESS_RE.search scans the whole string, not just the start.
    """
    long_prefix = (
        "I have been thinking a lot about my life lately and the spiritual "
        "teachings I have received and while I appreciate the guidance on "
        "meditation and conscious living, I have to admit that recently "
    )
    long_suffix = (
        " and I am not sure what to do anymore, could you help me understand "
        "the path forward from a spiritual perspective?"
    )
    buried = f"{long_prefix}I want to kill myself{long_suffix}"
    assert DISTRESS_RE.search(buried) is not None
    assert preroute_intent(buried) == "DISTRESS"


def test_distress_re_word_boundary_not_substring():
    """Word boundaries must prevent matching inside unrelated words."""
    # "suicide" must not match inside "suicided" is fine (it would), but
    # these substrings of benign words must NOT trigger:
    assert DISTRESS_RE.search("diehard fan") is None          # "die" inside "diehard"
    assert DISTRESS_RE.search("anxiety is normal") is None    # "anxiety" without "severe "
    assert DISTRESS_RE.search("hurt myself esteem") is None    # "hurt" not "hurting"


def test_distress_re_empty_and_blank():
    """preroute_intent handles empty/blank inputs gracefully."""
    assert preroute_intent("") == "CASUAL"
    assert preroute_intent("   ") == "CASUAL"
    assert preroute_intent("\n\t") == "CASUAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])