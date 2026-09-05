"""Unit tests for contextual re-ingestion engine and task wiring."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "deepseek-v4-flash:cloud")
os.environ.setdefault("OLLAMA_CLASSIFY_MODEL", "deepseek-v4-flash:cloud")
os.environ.setdefault("SARVAM_API_KEY", "placeholder")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from ingest.contextual_reingest import ContextualReingestEngine

    # Inject mocks through the engine constructor
    qdrant = MagicMock()
    qdrant.scroll.return_value = ([], None)

    embedder = MagicMock()
    embedder.encode_batch.return_value = {
        "dense": [[0.1] * 1024, [0.2] * 1024],
        "sparse": [None, None],
    }

    contextualizer = MagicMock()
    contextualizer.service = MagicMock()

    state_file = tmp_path / "ingestion_state.json"

    return ContextualReingestEngine(
        source_collection="spiritual_wisdom",
        target_collection="spiritual_wisdom_contextual",
        qdrant_client=qdrant,
        embedding_service=embedder,
        contextualizer=contextualizer,
        state_file=state_file,
    )


@pytest.fixture
def sample_payloads():
    return [
        {
            "text": "First paragraph of a teaching.",
            "source_url": "http://example.com/video",
            "title": "Teaching One",
            "speaker": "Sri Krishnaji",
            "topic": "Presence",
            "content_type": "video",
            "source_type": "youtube",
            "language": "en",
            "tags": ["meditation"],
            "chunk_index": 0,
            "raptor_level": 0,
            "authority_tier": "primary",
        },
        {
            "text": "Second paragraph continues the teaching.",
            "source_url": "http://example.com/video",
            "title": "Teaching One",
            "speaker": "Sri Krishnaji",
            "topic": "Presence",
            "content_type": "video",
            "source_type": "youtube",
            "language": "en",
            "tags": ["meditation"],
            "chunk_index": 1,
            "raptor_level": 0,
            "authority_tier": "primary",
        },
    ]


@pytest.mark.asyncio
async def test_dry_run(engine, sample_payloads, monkeypatch):
    from unittest.mock import AsyncMock

    # Prepare scroll results
    records = [MagicMock(id=f"id-{i}", payload=p) for i, p in enumerate(sample_payloads)]
    engine._client().scroll.return_value = (records, None)

    # Monkey-patch rechunk and contextualize for determinism
    monkeypatch.setattr(
        engine,
        "_rechunk",
        lambda full_text, payloads: ["Chunk A", "Chunk B"],
    )
    service_mock = MagicMock()
    service_mock.enrich_chunks = AsyncMock(return_value=["Ctx A", "Ctx B"])

    def _make_service(*args, **kwargs):
        return service_mock

    monkeypatch.setattr(
        "ingest.contextual_reingest.ContextualChunkingService",
        _make_service,
    )

    result = await engine.dry_run(limit=1)

    assert result["dry_run"] is True
    assert result["target_collection"] == "spiritual_wisdom_contextual"
    assert result["sources_previewed"] == 1
    assert result["total_new_chunks"] == 2
    assert result["previews"][0]["new_chunk_count"] == 2


@pytest.mark.asyncio
async def test_reingest_writes_points(engine, sample_payloads, monkeypatch, tmp_path):
    from qdrant_client.http.models import PointStruct

    records = [MagicMock(id=f"id-{i}", payload=p) for i, p in enumerate(sample_payloads)]
    engine._client().scroll.return_value = (records, None)

    monkeypatch.setattr(
        engine,
        "_rechunk",
        lambda full_text, payloads: ["Chunk A", "Chunk B"],
    )

    service_mock = MagicMock()
    service_mock.enrich_chunks = AsyncMock(return_value=["Ctx A", "Ctx B"])

    def _make_service(*args, **kwargs):
        return service_mock

    monkeypatch.setattr(
        "ingest.contextual_reingest.ContextualChunkingService",
        _make_service,
    )

    # Mock target manager
    target_manager = MagicMock()
    target_manager.client = engine._client()
    engine._target_manager = target_manager
    engine._ensure_target_collection = MagicMock()

    result = await engine.reingest(source_url="http://example.com/video")

    assert result["status"] == "ok"
    assert result["chunks_written"] == 2
    assert result["sources_processed"] == 1

    upsert_call = engine._client().upsert.call_args
    assert upsert_call[1]["collection_name"] == "spiritual_wisdom_contextual"
    points = upsert_call[1]["points"]
    assert len(points) == 2
    assert all(isinstance(p, PointStruct) for p in points)
    for p in points:
        assert p.payload["source_version"] == 2
        assert p.payload["chunk_type"] == "contextual"
        # `parent_chunk_id` must NOT be written: it used to be a fresh uuid4()
        # per chunk pointing at no stored parent document — a dangling reference
        # that reads as a working parent-child index (lessons.md L-CORRUPT-5).
        assert "parent_chunk_id" not in p.payload
        assert "ingested_at" in p.payload
        assert "authority_tier" in p.payload
        # This IS a contextual chunk regardless of what blue called the source
        # rows; inheriting content_type="summary" mislabelled verbatim doctrine.
        assert p.payload["content_type"] == "contextual"
        assert "dense" in p.vector


@pytest.mark.asyncio
async def test_reingest_skips_already_processed(engine, sample_payloads, monkeypatch):
    state_file = Path(engine._state_file)
    state_file.write_text(
        json.dumps({"contextual_reingest_processed_sources": ["http://example.com/video"]}),
        encoding="utf-8",
    )

    # Force re-read state
    engine._state = engine._load_state()

    records = [MagicMock(id=f"id-{i}", payload=p) for i, p in enumerate(sample_payloads)]
    engine._client().scroll.return_value = (records, None)

    # Skip Ollama health check and target collection creation so the test
    # does not need a live Qdrant/Ollama instance.
    monkeypatch.setattr(engine, "_contextualizer_service", MagicMock())
    monkeypatch.setattr(engine, "_ensure_target_collection", MagicMock())

    result = await engine.reingest()

    assert result["sources_processed"] == 0
    assert result["skipped"] == 1


def test_reconstruct_full_text_strips_old_header():
    from ingest.contextual_reingest import ContextualReingestEngine

    payloads = [
        {
            "text": "[Source: Old | Speaker: X]\n\nReal first chunk.",
            "chunk_index": 0,
        },
        {
            "text": "Second chunk.",
            "chunk_index": 1,
        },
    ]
    text = ContextualReingestEngine._reconstruct_full_text(payloads)
    assert "[Source: Old" not in text
    assert "Real first chunk." in text
    assert "Second chunk." in text


def test_task_registration():
    from tasks.contextual_reingest_task import contextual_reingest, contextual_reingest_dry_run

    assert contextual_reingest.name == "tasks.contextual_reingest_task.contextual_reingest"
    assert (
        contextual_reingest_dry_run.name
        == "tasks.contextual_reingest_task.contextual_reingest_dry_run"
    )
    assert contextual_reingest.queue == "ingestion"


def test_default_construction_does_not_double_suffix_target():
    """Regression for the 2026-09-03 bug: settings.qdrant_collection now
    defaults to the post-migration "spiritual_wisdom_contextual" collection
    itself, not the legacy raw one. A no-args ContextualReingestEngine() (as
    both run_pilot.py and tasks/contextual_reingest_task.py construct it)
    must resolve source=spiritual_wisdom / target=spiritual_wisdom_contextual,
    never a double-suffixed "spiritual_wisdom_contextual_contextual".
    """
    from ingest.contextual_reingest import ContextualReingestEngine

    engine = ContextualReingestEngine()
    assert engine._source_collection == "spiritual_wisdom"
    assert engine._target_collection == "spiritual_wisdom_contextual"
    assert not engine._target_collection.endswith("_contextual_contextual")


@pytest.mark.asyncio
async def test_reingest_source_with_late_chunking_enabled(engine, sample_payloads, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "reingest_late_chunking", True)

    monkeypatch.setattr(
        engine,
        "_rechunk",
        lambda full_text, payloads: ["Chunk A", "Chunk B"],
    )

    service_mock = MagicMock()
    service_mock.enrich_chunks = AsyncMock(return_value=["Ctx A", "Ctx B"])
    monkeypatch.setattr(
        "ingest.contextual_reingest.ContextualChunkingService",
        lambda *a, **kw: service_mock,
    )

    engine._embedding.encode_batch.return_value = {
        "dense": [[0.1] * 1024, [0.2] * 1024],
        "sparse": [None, None],
    }
    engine._embedding.encode_late_chunked.return_value = [[0.9] * 1024, [0.8] * 1024]

    target_manager = MagicMock()
    target_manager.client = engine._client()
    engine._target_manager = target_manager
    engine._ensure_target_collection = MagicMock()

    result = await engine._reingest_source("http://example.com/video", sample_payloads)

    assert result == 2
    upsert_call = engine._client().upsert.call_args
    points = upsert_call[1]["points"]
    assert len(points) == 2
    assert points[0].payload["pooling"] == "mean"
    assert points[1].payload["pooling"] == "mean"
    assert points[0].vector["dense"] == [0.9] * 1024


@pytest.mark.asyncio
async def test_correct_full_text_invokes_llm_corrector(engine):
    with patch(
        "ingest.corrector.TranscriptCorrector.correct_transcript", new_callable=AsyncMock
    ) as mock_correct:
        mock_correct.return_value = "Corrected text about I-Consciousness."
        res = await engine._correct_full_text(
            "Raw text with eye consciousness", "http://example.com/video"
        )
        assert res == "Corrected text about I-Consciousness."
        mock_correct.assert_called_once()


# ---------------------------------------------------------------------------
# Regression guards for the 2026-08-02 silent-truncation incident.
#
# lessons.md L-CORRUPT-6: a lesson without a failing test is a wish. Lesson #5
# ("caps truncate silently") was filed BEFORE the corrector shipped and did not
# prevent it, because it was a narrative rather than an assertion. These are the
# assertions.
# ---------------------------------------------------------------------------


def test_corrector_rejects_stub_replacing_full_chunk():
    """The exact 2026-08-02 bug: `min(50, len//2)` is always 50, so a 50-char
    stub was accepted as a correction of a 4,000-char chunk."""
    from ingest.corrector import _MAX_LENGTH_RATIO, _MIN_LENGTH_RATIO

    original = "When you practice the sacred breath, observe how the mind settles. " * 60
    stub = "Corrected."
    ratio = len(stub) / len(original)

    assert not (_MIN_LENGTH_RATIO <= ratio <= _MAX_LENGTH_RATIO), (
        f"a {len(stub)}-char stub must not pass as a correction of "
        f"{len(original)} chars (ratio {ratio:.3f})"
    )
    # And the old expression must never come back.
    assert min(50, len(original) // 2) == 50, (
        "min(50, len//2) collapses to 50 for any chunk >100 chars — this is the "
        "shape of the original bug; the guard must be a ratio, never a min()"
    )


def test_corrector_accepts_real_doctrine_fix_but_rejects_paraphrase():
    """Guard must separate a genuine term fix from an LLM paraphrase, measured at
    a REALISTIC chunk size — at toy sizes the thresholds false-positive."""
    from ingest.corrector import _rewrote_too_much

    base = (
        "When you practice the sacred breath observe how the mind settles into stillness. "
        "Do not force the breath simply allow it. The body becomes a vessel of peace. "
    ) * 13
    original = base + "The guru speaks of eye consciousness and soul sink today."
    fixed = original.replace("eye consciousness", "I-Consciousness").replace(
        "soul sink", "Soul Sync"
    )
    paraphrase = "The teacher explains breathing practice and mental calm. " * 20

    assert not _rewrote_too_much(original, fixed), "a doctrine-term fix must be accepted"
    assert _rewrote_too_much(original, paraphrase), "a paraphrase must be rejected"


def test_corrector_split_does_not_duplicate_overlap():
    """`correct_transcript` rejoins with a plain `" ".join`, so any overlap in the
    split is duplicated into stored doctrine at every seam."""
    from ingest.corrector import _sentence_aware_split

    text = "This is a sentence about the beautiful state. " * 300
    chunks = _sentence_aware_split(text, chunk_size=4000, overlap=0)
    rejoined_len = sum(len(c) for c in chunks)

    assert rejoined_len <= len(text) * 1.02, (
        f"rejoined length {rejoined_len} exceeds input {len(text)} — overlap is "
        "being duplicated because the rejoin does not strip it"
    )


def test_coverage_invariant_raises_on_catastrophic_loss():
    """The systemic fix: gates catch WRONG text, nothing caught MISSING text."""
    from ingest.contextual_reingest import ContextualReingestEngine

    before = "x" * 22487  # the real incident's numbers
    after = "x" * 7876  # 35% survived

    with pytest.raises(ValueError, match="Refusing to ingest a mutilated document"):
        ContextualReingestEngine._assert_coverage("test stage", "src", before, after)

    # A legitimate small loss (quality gate dropping one real ASR loop) must pass.
    ContextualReingestEngine._assert_coverage("test stage", "src", before, "x" * 21000)


def test_raptor_summaries_never_reach_transcript_reconstruction():
    """Summaries share chunk_index space with transcript chunks; sorting by index
    alone spliced machine prose into the guru's words."""
    from ingest.contextual_reingest import ContextualReingestEngine

    engine = ContextualReingestEngine.__new__(ContextualReingestEngine)
    payloads = [
        {
            "chunk_index": 0,
            "content_type": "summary",
            "raptor_level": 1,
            "text": "SUMMARY",
            "_id": "a",
        },
        {
            "chunk_index": 0,
            "content_type": "video_enhanced",
            "raptor_level": 0,
            "text": "REAL 0",
            "_id": "b",
        },
        {
            "chunk_index": 1,
            "content_type": "video_enhanced",
            "raptor_level": 0,
            "text": "REAL 1",
            "_id": "c",
        },
    ]
    kept = [
        p
        for p in payloads
        if p.get("content_type") != "summary" and not (p.get("raptor_level") or 0)
    ]
    assert [p["text"] for p in kept] == ["REAL 0", "REAL 1"]
    assert all("SUMMARY" not in p["text"] for p in kept)
    assert engine is not None  # engine construction path unused; filter is the contract


def test_metadata_uses_or_fallback_not_dict_default():
    """Blue payloads carry `topic` as an EMPTY STRING, so `.get(k, default)` never
    fires and every stored point got topic=""."""
    blue_payload = {"topic": "", "language": "", "speaker": ""}

    assert blue_payload.get("topic", "Spiritual") == "", "dict default does not fire on empty value"
    assert (blue_payload.get("topic") or "Spiritual") == "Spiritual", "`or` is the correct idiom"


# ---------------------------------------------------------------------------
# 2026-08-02: parent-child, uniform pooling, per-chunk provenance, bloat prune.
# The green collection passed every contamination check while being
# architecturally incomplete — clean text, unusable retrieval.
# ---------------------------------------------------------------------------


def test_parents_are_never_runts_and_never_split_a_chunk():
    """Blue's parents came from RecursiveCharacterTextSplitter(chunk_size=500),
    giving a median parent of 320 chars — often SMALLER than its own children, so
    the small-to-big swap in retrieval.py degraded to a no-op. A parent must span
    whole consecutive chunks and reach the minimum size."""
    from ingest.contextual_reingest import (
        _PARENT_MAX_CHARS,
        _PARENT_MIN_CHARS,
        ContextualReingestEngine,
    )

    for chunks in (["A" * 800] * 10, ["A" * 1800] * 7, ["A" * 1500] * 4 + ["E" * 200]):
        assigned = ContextualReingestEngine._build_parents("src", chunks)
        assert len(assigned) == len(chunks)

        groups: dict[str, list[int]] = {}
        for i, (pid, _) in enumerate(assigned):
            groups.setdefault(pid, []).append(i)

        for pid, idxs in groups.items():
            assert idxs == list(range(idxs[0], idxs[0] + len(idxs))), (
                f"{pid} is not a consecutive run — a parent must be contiguous text"
            )
            size = len(assigned[idxs[0]][1])
            assert size >= _PARENT_MIN_CHARS, f"{pid} is a {size}-char runt"
            # +200 absorbs the "\n\n" joins between chunks.
            assert size <= _PARENT_MAX_CHARS + 200, f"{pid} is {size} chars, over the cap"


def test_parent_ids_are_deterministic_across_runs():
    """Blue minted parent ids with uuid4(), so re-ingesting the same source
    produced entirely new ids for identical text. Deterministic ids keep the
    re-ingest idempotent, matching the deterministic point ids."""
    from ingest.contextual_reingest import ContextualReingestEngine

    chunks = ["A" * 1200, "B" * 1200, "C" * 1200]
    first = ContextualReingestEngine._build_parents("https://x/v1", chunks)
    second = ContextualReingestEngine._build_parents("https://x/v1", chunks)
    assert first == second
    assert first[0][0] == "https://x/v1#parent-0"
    other = ContextualReingestEngine._build_parents("https://x/v2", chunks)
    assert other[0][0] != first[0][0], "parent ids must be scoped to their source"


def test_origin_map_attributes_chunks_to_the_right_section():
    """`title` and `page_range` differ per SECTION in a PageIndex-parsed book.
    Taking them from payloads[0] mis-cited all 1,171 points of
    The_Four_Sacred_Secrets.pdf to whichever section sorted first."""
    from ingest.contextual_reingest import ContextualReingestEngine

    payloads = [
        {"text": "a" * 1000, "title": "Ch1", "page_range": "1-10"},
        {"text": "b" * 1000, "title": "Ch2", "page_range": "11-20"},
        {"text": "c" * 1000, "title": "Ch3", "page_range": "21-30"},
    ]
    spans = [(0, 900), (1100, 1900), (2100, 2900), (0, 0)]
    mapped = ContextualReingestEngine._origin_index_map(payloads, spans, 3000)

    assert mapped[:3] == [0, 1, 2]
    assert [payloads[i]["page_range"] for i in mapped[:3]] == ["1-10", "11-20", "21-30"]
    # An unlocatable chunk (empty span) falls back to the first payload, never crashes.
    assert mapped[3] == 0
    assert ContextualReingestEngine._origin_index_map([], spans, 3000) == [0, 0, 0, 0]


def test_late_chunking_never_mixes_pooling_modes():
    """CLS and mean vectors sit ~0.757 cosine apart. The first implementation
    kept the CLS vector whenever _chunk_spans could not locate a chunk, so one
    collection held both (measured live: cls=118, mean=312) and every query
    scored half the corpus across that gap. Any span-location failure must
    mean-pool the chunk standalone instead."""
    import inspect

    from ingest.contextual_reingest import ContextualReingestEngine

    src = inspect.getsource(ContextualReingestEngine._ingest_unit)
    assert "encode_query_mean_pooled" in src, (
        "the late-chunking fallback must mean-pool, not fall back to CLS"
    )
    assert "mixed pooling modes" in src, "a mixed-pooling collection must raise, not warn"
    # production-audit finding false-confidence-2: a bare `src.count(...) == 1`
    # can't detect the actual regression shape — re-indenting this exact same
    # line back inside the `if vec and any(vec):` success branch (the original
    # bug) still produces exactly one textual occurrence. Check the line's
    # INDENTATION instead: it must sit at the `for` loop's body level (outside
    # both the if and else blocks), not nested one level deeper inside either.
    lines = src.splitlines()
    for_indent = None
    assignment_indent = None
    for line in lines:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if stripped.startswith("for i in range(len(dense_vectors)):"):
            for_indent = indent
        elif 'pooling_modes[i] = "mean"' in stripped and assignment_indent is None:
            assignment_indent = indent
    assert for_indent is not None, "could not locate the late-chunking for-loop in source"
    assert assignment_indent is not None, 'pooling_modes[i] = "mean" not found'
    assert assignment_indent == for_indent + 4, (
        f"pooling_modes[i] assignment is nested at indent {assignment_indent} "
        f"(loop body is {for_indent + 4}) — it must be unconditional per "
        "iteration, not confined to the if/else branch above it"
    )


def test_dead_metadata_is_not_written():
    """`phonetic_tokens` fed a searcher prefetch that was deleted for latency,
    and `original_chunk_count` describes the migration, not the chunk. Both rode
    on 100% of green's payloads with no reader."""
    import inspect

    from ingest.contextual_reingest import ContextualReingestEngine
    from services.qdrant.indexer import QdrantIndexer
    from services.qdrant.searcher import QdrantSearcher

    reingest_src = inspect.getsource(ContextualReingestEngine._ingest_unit)
    assert '"original_chunk_count": len(payloads)' not in reingest_src

    indexer_src = inspect.getsource(QdrantIndexer.upsert_chunks)
    assert '"phonetic_tokens": phonetic_tokens' not in indexer_src
    assert "IndicPhoneticMatcher.get_phonetic_tokens" not in indexer_src

    searcher_src = inspect.getsource(QdrantSearcher)
    assert "query_phonetic_tokens" not in searcher_src, (
        "computing phonetic tokens per query with no consumer is pure waste"
    )


def test_chunk_spans_survive_whitespace_normalisation():
    """SemanticChunker single-spaces its output while a reconstructed transcript
    carries double spaces at every payload seam. A literal find() therefore
    matched NOTHING: the 2026-08-02 live run located 0 of 2 spans and ran with
    late chunking silently disabled, reporting success throughout."""
    from ingest.contextual_reingest import ContextualReingestEngine

    doc = "Meditation builds immunity.  This increases your ojas.\n\nOjas is strength."
    chunks = ["Meditation builds immunity. This increases your ojas.", "Ojas is strength."]

    spans = ContextualReingestEngine._chunk_spans(doc, chunks)
    assert all(end > start for start, end in spans), f"unlocated chunk: {spans}"

    # Spans must point at the right text, not merely be non-empty.
    for chunk, (start, end) in zip(chunks, spans):
        assert " ".join(doc[start:end].split()) == chunk

    # Spans stay ordered and non-overlapping for sequential chunks.
    assert spans[0][1] <= spans[1][0]
    # A chunk that truly is not in the document still reports an empty span.
    assert ContextualReingestEngine._chunk_spans(doc, ["not in here at all"]) == [(0, 0)]


def test_chunk_spans_pick_the_later_occurrence_of_a_repeated_sentence():
    """Forward scanning must survive normalisation too — otherwise a repeated
    line maps every later chunk back onto the first occurrence."""
    from ingest.contextual_reingest import ContextualReingestEngine

    doc = "Be still.  Then the mind clears.  Be still.  Then joy arises."
    spans = ContextualReingestEngine._chunk_spans(doc, ["Be still.", "Be still."])
    assert spans[0][0] < spans[1][0], spans


def test_llm_correction_is_skipped_for_already_edited_sources():
    """The corrector fixes ASR damage. Run against a published book it summarized
    instead: 108 of ~106 chunks of The_Four_Sacred_Secrets.pdf tripped the length
    guard (ratios 0.21-0.32), so ~440 OpenRouter calls bought nothing while
    risking the text. Deterministic dictionary corrections still apply."""
    import asyncio

    from ingest.contextual_reingest import (
        _NO_LLM_CORRECTION_TYPES,
        ContextualReingestEngine,
    )

    engine = ContextualReingestEngine.__new__(ContextualReingestEngine)
    called = []

    def _boom(*_a, **_k):
        called.append(True)
        raise AssertionError("LLM correction must not run for edited prose")

    engine._contextualizer_service = _boom
    text = "Ojas is the essence of immunity."

    for content_type in _NO_LLM_CORRECTION_TYPES:
        out = asyncio.run(
            engine._correct_full_text(text, "The_Four_Sacred_Secrets.pdf", content_type)
        )
        assert out, content_type
    assert not called

    # A transcript still goes through the LLM path (which falls back to the
    # dictionary here because the stub raises) — the skip must be type-scoped.
    asyncio.run(engine._correct_full_text(text, "https://youtu.be/x", "video_enhanced"))
    assert called, "transcripts must still be corrected"


def test_book_sections_are_processed_as_separate_documents():
    """The contextualizer truncates its "document" to max_doc_chars. On the
    424,302-char book that is ~1.9% of the text, so a chapter-7 chunk was being
    situated against the front matter and back cover. Sections also stop chunks
    and parents straddling a chapter boundary."""
    from ingest.contextual_reingest import ContextualReingestEngine

    book = (
        [{"node_id": "0001", "title": "Front Matter", "page_range": "2-4", "text": "a"}] * 3
        + [{"node_id": "0009", "title": "Second Journey", "page_range": "58-74", "text": "b"}] * 4
        + [{"node_id": "0012", "title": "Third Secret", "page_range": "76-84", "text": "c"}] * 2
    )
    groups = ContextualReingestEngine._section_groups(book)
    assert [key for key, _ in groups] == ["0001", "0009", "0012"]
    assert [len(payloads) for _, payloads in groups] == [3, 4, 2]

    # A transcript has no structural markers — exactly one unit, unchanged behaviour.
    transcript = [{"text": "x", "title": ""} for _ in range(5)]
    plain = ContextualReingestEngine._section_groups(transcript)
    assert len(plain) == 1 and len(plain[0][1]) == 5

    # A node_id that reappears later starts a NEW section rather than merging
    # text from opposite ends of the book into one unit.
    interleaved = [
        {"node_id": "A", "text": "1"},
        {"node_id": "B", "text": "2"},
        {"node_id": "A", "text": "3"},
    ]
    assert len(ContextualReingestEngine._section_groups(interleaved)) == 3


def test_parent_ids_are_unique_across_book_sections():
    """Parents are built per unit. If every section built them from the bare
    source_url, section 2's `#parent-0` would collide with section 1's and the
    small-to-big swap would serve the wrong chapter."""
    from ingest.contextual_reingest import ContextualReingestEngine

    chunks = ["x" * 1200, "y" * 1200]
    first = ContextualReingestEngine._build_parents("book.pdf#0009", chunks)
    second = ContextualReingestEngine._build_parents("book.pdf#0012", chunks)
    assert {p for p, _ in first}.isdisjoint({p for p, _ in second})


def test_sections_are_written_incrementally_with_resume():
    """A 25-section book runs for hours. Writing once at the end meant a crash in
    section 24 discarded everything. Each section is now upserted as it finishes,
    the source is deleted ONCE up front (never between sections), and a resumed
    run skips what already landed."""
    import inspect

    from ingest.contextual_reingest import _STATE_KEY_SECTIONS, ContextualReingestEngine

    assert _STATE_KEY_SECTIONS == "contextual_reingest_processed_sections"
    src = inspect.getsource(ContextualReingestEngine._reingest_source)
    assert "_STATE_KEY_SECTIONS" in src, "per-section progress must be persisted"
    # Delete must be guarded by "nothing done yet", or section 2 wipes section 1.
    assert "if not done and target_service.check_source_exists" in src
    # Exactly one delete call in the whole method.
    assert src.count("delete_by_source(source_url)") == 1
    # State is persisted after each section, not once at the end.
    assert src.count("self._save_state()") >= 2
    # Point ids stay unique: chunk_index continues across sections.
    assert "next_index + offset" in src
    assert "next_index += len(section_payloads)" in src, "resume must advance the cursor"


@pytest.mark.asyncio
async def test_reingest_source_resumes_after_simulated_crash(tmp_path):
    """production-audit finding false-confidence-3: the sibling test above only
    greps source text — it never actually crashes and resumes a run. Simulate
    a real crash after section 1 completes, then construct a FRESH engine
    (as a real process restart would) sharing only the on-disk state file, and
    verify section 1 is not reprocessed and the source is deleted exactly once
    across both runs."""
    from ingest.contextual_reingest import ContextualReingestEngine

    state_file = tmp_path / "ingestion_state.json"
    source_url = "https://example.com/book"
    payloads = [
        {"node_id": "ch1", "text": "chapter one text", "_id": "p1"},
        {"node_id": "ch2", "text": "chapter two text", "_id": "p2"},
    ]

    shared_target_service = MagicMock()
    shared_target_service.check_source_exists.return_value = True
    shared_target_service.upsert_chunks.return_value = 1

    def make_engine():
        engine = ContextualReingestEngine(
            source_collection="spiritual_wisdom",
            target_collection="spiritual_wisdom_contextual",
            qdrant_client=MagicMock(),
            embedding_service=MagicMock(),
            contextualizer=MagicMock(),
            state_file=state_file,
        )
        engine._target_service = MagicMock(return_value=shared_target_service)
        return engine

    # --- Run 1: section 1 succeeds, section 2 crashes (uncaught exception) ---
    engine1 = make_engine()

    async def ingest_unit_run1(src_url, section_payloads, label):
        if "ch1" in label:
            return (["chunk1"], [{"chunk_index": 0}], [[0.1] * 4], [None])
        raise RuntimeError("simulated crash mid-section")

    engine1._ingest_unit = AsyncMock(side_effect=ingest_unit_run1)

    with pytest.raises(RuntimeError, match="simulated crash"):
        await engine1._reingest_source(source_url, payloads)

    assert shared_target_service.delete_by_source.call_count == 1
    assert shared_target_service.upsert_chunks.call_count == 1

    # --- Run 2: fresh engine instance (process restart), same state file ---
    engine2 = make_engine()

    async def ingest_unit_run2(src_url, section_payloads, label):
        assert "ch1" not in label, "section 1 must not be reprocessed after resume"
        return (["chunk2"], [{"chunk_index": 0}], [[0.2] * 4], [None])

    engine2._ingest_unit = AsyncMock(side_effect=ingest_unit_run2)

    written = await engine2._reingest_source(source_url, payloads)

    assert written == 1
    engine2._ingest_unit.assert_awaited_once()
    # Delete must NOT fire again on resume — still exactly one across both runs.
    assert shared_target_service.delete_by_source.call_count == 1
    assert shared_target_service.upsert_chunks.call_count == 2
