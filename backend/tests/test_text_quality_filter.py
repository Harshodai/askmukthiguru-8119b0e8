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
            "x" * 80,  # too long
            "Wait\nlet me reconsider",  # multi-line
            "First point. Second point. Third point.",  # sentence-shaped
            "Topics are:",  # trailing colon
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
    """The stricter filter must not retroactively reject reviewed doctrine.

    The bundle was cleared on 2026-08-01 for a clean rebuild from the green
    corpus, so it is legitimately empty right now and there is nothing to
    protect. Skip rather than assert a count — but keep the guard armed, so it
    returns automatically once entries are re-extracted and reviewed.
    """
    from services.memory.okf_store import OKFStore

    entries = OKFStore().list_entries()
    if not entries:
        pytest.skip(
            "OKF bundle is empty (cleared 2026-08-01 for rebuild from the green "
            "corpus) — no reviewed doctrine to protect yet"
        )
    assert len(entries) >= 23, (
        f"only {len(entries)} OKF entries loaded — the artifact filter is "
        "rejecting human-reviewed doctrine"
    )


# ---------------------------------------------------------------------------
# Batch-level repeat guard.
#
# The per-chunk filter above cannot see a generator loop: the 2026-08-01 corpus
# measurement found 227 identical copies under one source_url with consecutive
# chunk_index values, each copy individually innocent. `make_point_id` hashes
# chunk_index, so all 227 earned distinct point ids and persisted.
# ---------------------------------------------------------------------------

_LOOPED_CHUNK = "source topic power of observation the streets are the way we are"


def test_collapse_repeats_keeps_first_occurrence_only():
    from services.text_quality_filter import collapse_repeats

    texts = [_LOOPED_CHUNK] * 227
    keep, repeats = collapse_repeats(texts, ["vid_a"] * 227)

    assert keep == [0], "only the first copy survives"
    assert len(repeats) == 1
    preview, count, source = repeats[0]
    assert count == 226 and source == "vid_a"
    assert preview.startswith("source topic power")


def test_collapse_repeats_returns_indices_not_a_filtered_list():
    """Same contract as select_clean — callers filter parallel arrays by index."""
    from services.text_quality_filter import collapse_repeats

    texts = ["alpha teaching", "beta teaching", "alpha teaching", "gamma teaching"]
    keep, _ = collapse_repeats(texts, ["v"] * 4)

    assert keep == [0, 1, 3], "indices must address the ORIGINAL list"


def test_same_text_in_different_sources_is_legitimate_repetition():
    """The gurus repeat teachings across talks. That is doctrine, not a loop."""
    from services.text_quality_filter import collapse_repeats

    teaching = "The beautiful state is your natural state."
    keep, repeats = collapse_repeats([teaching] * 3, ["vid_a", "vid_b", "vid_c"])

    assert keep == [0, 1, 2], "cross-source repetition must survive"
    assert repeats == []


def test_repeat_alarm_separates_a_loop_from_ordinary_duplication():
    from services.text_quality_filter import collapse_repeats, is_repeat_alarm

    _, ordinary = collapse_repeats(["a chunk", "a chunk"], ["v", "v"])
    assert ordinary and not is_repeat_alarm(ordinary), "one dup is not an alarm"

    _, loop = collapse_repeats([_LOOPED_CHUNK] * 12, ["v"] * 12)
    assert is_repeat_alarm(loop), "a run of copies means the writer stopped advancing"


def test_collapse_repeats_ignores_whitespace_and_case_drift():
    from services.text_quality_filter import collapse_repeats

    keep, repeats = collapse_repeats(
        ["The Beautiful State.", "  the   beautiful state.  "], ["v", "v"]
    )
    assert keep == [0] and repeats[0][1] == 1


def test_storage_boundary_collapses_a_generator_loop():
    """End-to-end at the chokepoint: 227 looped copies must write ONE point,
    with vectors and metadata still aligned to the surviving chunk."""
    from unittest.mock import MagicMock

    from services.qdrant.indexer import QdrantIndexer

    n = 227
    texts = [_LOOPED_CHUNK] * n + ["A real teaching about the beautiful state."]
    vectors = [[float(i)] * 4 for i in range(n + 1)]
    metadatas = [{"source_url": "vid_a", "chunk_index": i, "raptor_level": 0} for i in range(n + 1)]

    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._collection = "test_collection"
    indexer._client = MagicMock()
    indexer._utils = MagicMock()
    indexer._utils.make_point_id.side_effect = lambda s, c, r: f"{s}:{c}:{r}"

    written = indexer.upsert_chunks(texts, vectors, metadatas)

    assert written == 2, f"expected 1 collapsed loop + 1 real teaching, got {written}"
    points = indexer._client.upsert.call_args.kwargs["points"]
    payload_texts = [p.payload["text"] for p in points]
    assert payload_texts == [_LOOPED_CHUNK, "A real teaching about the beautiful state."]
    assert [p.payload["chunk_index"] for p in points] == [0, n]


def test_collapse_repeats_rejects_shorter_sources_sequence():
    from services.text_quality_filter import collapse_repeats

    texts = ["teaching A", "teaching B"]
    sources = ["source_1"]  # shorter than texts
    with pytest.raises(ValueError, match="Length mismatch"):
        collapse_repeats(texts, sources)


def test_storage_boundary_missing_sources_equal_text_collapsed():
    """Two records with missing sources and equal text share one sentinel and are collapsed."""
    from unittest.mock import MagicMock

    from services.qdrant.indexer import QdrantIndexer

    texts = ["Equal text without source", "Equal text without source"]
    vectors = [[0.1] * 4, [0.2] * 4]
    metadatas = [{}, {}]  # missing source_url

    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._collection = "test_collection"
    indexer._client = MagicMock()
    indexer._utils = MagicMock()
    indexer._utils.make_point_id.side_effect = lambda s, c, r: f"{s}:{c}:{r}"

    written = indexer.upsert_chunks(texts, vectors, metadatas)
    assert written == 1, "identical records with missing source share sentinel and are collapsed"
    points = indexer._client.upsert.call_args.kwargs["points"]
    assert len(points) == 1


def test_stale_qdrant_points_reconciled_on_reingest():
    """Integration test: duplicate chunk IDs are deleted from Qdrant before upserting retained records."""
    from unittest.mock import MagicMock

    from services.qdrant.indexer import QdrantIndexer

    teaching = "Duplicated teaching chunk"
    texts = [teaching, teaching]
    vectors = [[0.1] * 4, [0.2] * 4]
    metadatas = [
        {"source_url": "vid_stale", "chunk_index": 0, "raptor_level": 0},
        {"source_url": "vid_stale", "chunk_index": 1, "raptor_level": 0},
    ]

    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._collection = "test_collection"
    indexer._client = MagicMock()
    indexer._utils = MagicMock()
    indexer._utils.make_point_id.side_effect = lambda s, c, r: f"{s}:{c}:{r}"

    written = indexer.upsert_chunks(texts, vectors, metadatas)
    assert written == 1
    # Verify client.delete was called with the stale point id for chunk_index 1
    indexer._client.delete.assert_called_once_with(
        collection_name="test_collection",
        points_selector=["vid_stale:1:0"],
    )
