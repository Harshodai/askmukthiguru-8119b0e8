"""Regression tests for the shared LLM-artifact gate.

Pins the two defects found in the 2026-08-01 corpus audit, which put the
extraction LLM's own chain-of-thought into 24.3% of the 89,061-chunk
`spiritual_wisdom` collection where it was retrievable as doctrine:

  1. `_extract_topics` salvaged unparseable LLM output through a *blocklist*,
     which fails open — anything not on the list became a persisted "topic".
  2. `_embed_and_upsert` indexed `extra_metadatas[i]` by POST-filter position
     while the list was built for the PRE-filter chunks, so a single dropped
     chunk shifted every later chunk's metadata onto the wrong chunk.

The poison strings below are verbatim from live Qdrant points. The doctrine
strings are verbatim from the `guru_tone_podcast` collection — if the filter
ever rejects one of those, it is deleting real teachings.
"""

from __future__ import annotations

import pytest

from services.text_quality_filter import (
    clean_topic_label,
    find_artifact,
    is_clean,
    select_clean,
)

# Verbatim from live `spiritual_wisdom` points (2026-08-01 audit).
CORPUS_POISON = [
    '2.  **Analyze the Input Sentence:** " "The State of Contemporary Anxiety." I like "',
    "1.  **Deconstruct the User's Request:**",
    "The rules are for a task that is *not* the one I've been asked to perform.",
    "Sadhana is a term in the teaching. a common transcription error where a space is omitted.",
    "[RAPTOR Level: 1 | Topic: Simple, Foundational Presence]",
    '*   "Ego and Control" - This gets to the *why* behind the flawed view.',
    '2.  **Interpret the Input "hs and":**',
    "The user wants me to analyze a spiritual teaching and list the top 3-5 distinct topics",
]

# Verbatim guru speech from `guru_tone_podcast`. Must never be rejected.
REAL_DOCTRINE = [
    "In a beautiful state, you are powerful enough to help yourself and help others around you.",
    "You are outright intelligent, and your actions are decisive and powerful.",
    "Let us observe Nomi a little longer. Anger and confusion have mounted over his ideas of duty.",
    "In my observation, when a stressful state mounts over your ideas, however lofty they are.",
    "We are given this life to live in connection, not in division.",
    "Every day lived in a beautiful state is life truly lived.",
]


@pytest.mark.parametrize("text", CORPUS_POISON)
def test_detects_every_artifact_found_in_live_corpus(text):
    assert not is_clean(text), f"artifact slipped through: {text!r}"
    assert find_artifact(text), "find_artifact must report the matched span"


@pytest.mark.parametrize("text", REAL_DOCTRINE)
def test_never_rejects_real_doctrine(text):
    assert is_clean(text), (
        f"FALSE POSITIVE — filter would delete real teaching: {text!r}. "
        "A false positive here removes doctrine from the corpus."
    )


def test_select_clean_returns_indices_not_a_filtered_list():
    """The alignment fix depends on getting indices back, not a shrunk list."""
    chunks = [REAL_DOCTRINE[0], CORPUS_POISON[0], REAL_DOCTRINE[1], CORPUS_POISON[1]]
    keep, rejected = select_clean(chunks)
    assert keep == [0, 2]
    assert [r[0] for r in rejected] == [1, 3]
    for _idx, artifact, preview in rejected:
        assert artifact, "every rejection must carry the matched artifact for audit"
        assert preview, "every rejection must carry a preview for audit"


def test_parallel_arrays_stay_aligned_after_filtering():
    """Regression for the metadata-shift bug in `_embed_and_upsert`.

    Reproduces the exact pattern the pipeline uses: filter by index, then
    re-slice every parallel array with the same indices.
    """
    chunks = [REAL_DOCTRINE[0], CORPUS_POISON[0], REAL_DOCTRINE[1]]
    metadatas = [{"chunk": "A"}, {"chunk": "POISON"}, {"chunk": "C"}]
    speakers = ["teacher", "narration", "teacher"]

    keep, _ = select_clean(chunks)
    kept_chunks = [chunks[i] for i in keep]
    kept_metadatas = [metadatas[i] for i in keep]
    kept_speakers = [speakers[i] for i in keep]

    assert kept_chunks == [REAL_DOCTRINE[0], REAL_DOCTRINE[1]]
    # The old code produced [{"chunk": "A"}, {"chunk": "POISON"}] here —
    # chunk C silently carrying the dropped poison chunk's metadata.
    assert kept_metadatas == [{"chunk": "A"}, {"chunk": "C"}]
    assert kept_speakers == ["teacher", "teacher"]


def test_all_chunks_rejected_yields_empty_keep():
    keep, rejected = select_clean(CORPUS_POISON)
    assert keep == []
    assert len(rejected) == len(CORPUS_POISON)


def test_select_clean_handles_empty_input():
    assert select_clean([]) == ([], [])


class TestCleanTopicLabel:
    """Positive validation: a topic is a short noun phrase, or it is not a topic."""

    @pytest.mark.parametrize(
        "label", ["Nature of Suffering", "Beautiful State", "Soul Sync Practice"]
    )
    def test_accepts_real_topic_labels(self, label):
        assert clean_topic_label(label) == label

    @pytest.mark.parametrize(
        "label",
        [
            "a common transcription error where a space is omitted.",  # from live corpus
            "The user wants me to analyze this",
            "x" * 80,                    # too long
            "Wait\nlet me reconsider",   # multi-line
            "First point. Second point. Third point.",  # sentence-shaped
            "Topics are:",               # trailing colon
            "",
            "   ",
        ],
    )
    def test_rejects_non_topics(self, label):
        assert clean_topic_label(label) is None

    def test_strips_surrounding_quotes(self):
        assert clean_topic_label('"Inner Truth"') == "Inner Truth"
        assert clean_topic_label("'Inner Truth'") == "Inner Truth"


def test_okf_filter_shares_the_same_pattern_table():
    """Two lists is how the corpus went unguarded. Keep them fused."""
    from services.okf_quality_filter import _LEAKAGE_PATTERNS
    from services.text_quality_filter import _ARTIFACT_PATTERNS

    missing = set(_ARTIFACT_PATTERNS) - set(_LEAKAGE_PATTERNS)
    assert not missing, (
        f"OKF filter no longer inherits shared artifact patterns: {missing}. "
        "Every persistence path must enforce the same table."
    )


def test_live_okf_bundle_survives_the_filter():
    """The stricter filter must not retroactively reject reviewed doctrine."""
    from services.memory.okf_store import OKFStore

    entries = OKFStore().list_entries()
    assert len(entries) >= 23, (
        f"only {len(entries)} OKF entries loaded — the artifact filter is "
        "rejecting human-reviewed doctrine"
    )
