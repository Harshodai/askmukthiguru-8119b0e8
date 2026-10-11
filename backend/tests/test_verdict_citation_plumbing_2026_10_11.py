"""Live-proven fixes 2026-10-11: verdict self-consistency + citation plumbing.

Issue 1: a doctrine answer shipped verification.details
"Local NLI claim verification passed (12 claims grounded, score: 1.00)"
next to passed:false, method:null, grounding:abstained. Root causes: the
local-NLI pass branches never set `method`, and format_final_answer flips
`passed` to False when the citation check fails while the stale "passed"
details survive.

Issue 2: doctrine citations lacked timestamps and one carried speaker
"Unknown". Root causes: the Qdrant searcher dropped payload timing fields,
the timestamp resolver did not understand start_ms/timestamp_seconds, and
the public citation contract passed the raw payload speaker through
verbatim (including the "Unknown" default).

Fakes only — no network, no real providers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import rag.nodes as nodes
from rag.nodes.citation_extractor import _resolve_timestamp, extract_citations
from rag.nodes.generation import (
    _PARTIAL_EVIDENCE_DETAILS,
    _demote_stale_pass_details,
    _honest_unverified_details,
    _sanitize_citations,
    format_final_answer,
)
from rag.states import GraphState
from services.attribution import clean_wire_speaker


def _supported_claims(n: int) -> list[dict]:
    return [{"text": f"Grounded claim {i}.", "score": 1.0, "supported": True} for i in range(n)]


# ---------------------------------------------------------------------------
# Issue 1a: the local-NLI pass verdict carries a method (never method:null)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_verification_services():
    from rag.nodes import _services

    saved = dict(vars(_services))
    mock_ollama = AsyncMock()
    mock_ollama.generate = AsyncMock(return_value="")
    nodes.init_services(
        ollama=mock_ollama,
        embedder=MagicMock(),
        qdrant=MagicMock(),
        lightrag=MagicMock(),
    )
    nodes._llm_gateway = None
    mock_ld = MagicMock()
    nodes._lettuce_detect = mock_ld
    yield mock_ld
    for name in set(vars(_services)) - set(saved):
        delattr(_services, name)
    for name, value in saved.items():
        setattr(_services, name, value)


def _verify_state(answer: str = "The beautiful state is connection and joy.") -> GraphState:
    return GraphState(
        question="What is the beautiful state?",
        chat_history=[],
        request_id="test-verdict-plumbing",
        intent="FACTUAL",
        query_tier="standard",
        documents=[],
        reranked_docs=[],
        hyde_text=None,
        relevant_docs=[
            {
                "text": "Sri Preethaji teaches that the beautiful state is a state of connection, "
                "a state of oneness, a state of peace, a state of love, a state of joy, "
                "and a state of compassion. It is not just an absence of suffering, but "
                "a positive presence of connection and profound harmony with life.",
                "source_url": "https://example.com/teachings/beautiful-state",
            }
        ],
        grading_reasons=[],
        rewrite_count=0,
        rewritten_query=None,
        sub_queries=["What is the beautiful state?"],
        is_complex=False,
        selected_clusters=[],
        hints=[],
        answer=answer,
        citations=[],
        is_faithful=None,
        needs_correction=False,
        reflection_feedback=None,
        verification=None,
        confidence_score=None,
        input_blocked=False,
        output_blocked=False,
        block_reason=None,
        meditation_step=0,
        meditation_response=None,
        final_answer=None,
        error=None,
        context_layers=None,
        citation_reasoning={},
        metrics={},
        user_id=None,
        detected_language="en",
        memory_context="",
        ab_model="primary",
    )


@pytest.mark.asyncio
async def test_local_nli_pass_verdict_carries_method(mock_verification_services) -> None:
    """The pass verdict that produced the live contradiction had no `method`
    key, so the API rendered method:null next to the stale details."""
    mock_ld = mock_verification_services
    mock_ld.score_faithfulness.return_value = {
        "is_faithful": True,
        "score": 1.0,
        "details": "All sentences successfully grounded in context.",
        "unsupported_sentences": [],
        "claims": _supported_claims(12),
    }
    result = await nodes.verify_answer(_verify_state())
    verification = result["verification"]
    assert verification["passed"] is True
    assert verification["method"] == "local_nli_claim_verification"
    assert "passed" in verification["details"]  # the pass string stays on a pass


# ---------------------------------------------------------------------------
# Issue 1b: forcing passed=False rewrites a stale "passed" details string
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_honest_unverified_details_preserves_counts_without_passed() -> None:
    details = _honest_unverified_details(
        {
            "claims": _supported_claims(12),
            "score": 1.0,
            "details": "Local NLI claim verification passed",
        }
    )
    assert details.startswith("12/12 claims grounded against retrieved excerpts; ")
    assert "unverified related evidence, not a direct teaching" in details
    assert "passed" not in details.lower()


@pytest.mark.unit
def test_demote_is_noop_on_honest_failure_details() -> None:
    verification = {
        "passed": False,
        "method": "local_nli_claim_verification",
        "details": "Faithfulness: 0.20 (floor=0.70); Unsupported claims: 'gold'",
        "claims": [],
    }
    _demote_stale_pass_details(verification)
    assert verification["details"].startswith("Faithfulness: 0.20")
    assert verification["method"] == "local_nli_claim_verification"


@pytest.mark.unit
def test_demote_backfills_missing_method() -> None:
    verification = {
        "passed": False,
        "details": "Local NLI claim verification passed (2 claims grounded, score: 1.00)",
        "claims": _supported_claims(2),
    }
    _demote_stale_pass_details(verification)
    assert verification["method"] == "local_nli_claim_verification"
    assert "passed" not in verification["details"].lower()


def _final_state(**overrides) -> GraphState:
    base = dict(
        answer=(
            "The beautiful state is a condition of connection and quiet joy. "
            "When attention rests, the sense of separation softens on its own. "
            "This is the first movement of the sacred wisdom tradition."
        ),
        citations=[{"url": "https://doc.example/teaching", "title": "Doc One"}],
        relevant_docs=[
            {
                "title": "Doc One",
                "source_url": "https://doc.example/teaching",
                "text": "The beautiful state is connection, joy and inner harmony.",
            }
        ],
        is_faithful=True,
        verification={
            "passed": True,
            "method": "local_nli_claim_verification",
            "details": "Local NLI claim verification passed (2 claims grounded, score: 1.00)",
            "claims": _supported_claims(2),
            # The live contradiction: the citation check failed downstream.
            "citations_verified": False,
        },
        citations_verified=False,
        faithfulness_score=1.0,
        confidence_score=8.0,
        intent="QUERY",
        query_tier="standard",
        retry_count=1,
    )
    base.update(overrides)
    return GraphState(**base)


@pytest.mark.asyncio
async def test_format_final_answer_never_ships_passed_details_with_passed_false() -> None:
    """End-to-end shape of the live defect: claims ground at 1.0 but the
    citation check fails, so the answer ships unverified. The verdict object
    must be self-consistent, while citationsVerified:false keeps keying the
    UI's unverified treatment (ChatMessage.tsx contract)."""
    result = await format_final_answer(_final_state())
    verification = result["verification"]
    assert verification["passed"] is False
    assert result["citations_verified"] is False
    assert verification.get("citations_verified") is False
    assert "passed" not in str(verification.get("details", "")).lower()
    assert "unverified related evidence, not a direct teaching" in verification["details"]
    assert "2/2 claims grounded" in verification["details"]
    assert verification.get("method")  # never method:null


def _rejected_state() -> GraphState:
    doc_text = (
        "The beautiful state is a condition of connection, joy and inner harmony "
        "that arises when attention rests and the sense of separation softens."
    )
    return GraphState(
        **{
            **_final_state(),
            "answer": (
                "The beautiful state brings connection and joy to daily life. "
                "Resting attention lets separation soften filler words here. "
                "Gold trading secrets revealed for profit today."
            ),
            "question": "What is the beautiful state?",
            "is_faithful": False,
            "verification": {
                "passed": False,
                "method": "local_nli_claim_verification",
                "details": "Faithfulness: 0.20 (floor=0.70); Unsupported claims: 'gold'",
                "claims": [
                    {"text": "unsupported one", "score": 0.1, "supported": False},
                    {"text": "unsupported two", "score": 0.1, "supported": False},
                    {"text": "unsupported three", "score": 0.1, "supported": False},
                ],
                "citations_verified": False,
            },
            "citations_verified": False,
            "faithfulness_score": 0.2,
            "confidence_score": 0.0,
            "relevant_docs": [
                {
                    "title": "Doc One",
                    "source_url": "https://doc.example/teaching",
                    "text": doc_text,
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_grounded_partial_envelope_details_are_honest() -> None:
    """The rejected-draft fallback spreads the old verdict; its details must
    describe the excerpts envelope, never the draft's pass string."""
    result = await format_final_answer(_rejected_state())
    verification = result["verification"]
    assert verification["passed"] is False
    assert verification["method"] == "grounded_partial_evidence"
    assert verification["details"] == _PARTIAL_EVIDENCE_DETAILS
    assert "passed" not in verification["details"].lower()


# ---------------------------------------------------------------------------
# Issue 2a: timestamp resolution (start_ms -> seconds, never fabricated)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_timestamp_reads_start_ms_as_seconds() -> None:
    assert _resolve_timestamp({"start_ms": 99_000}) == 99.0
    assert _resolve_timestamp({"metadata": {"start_ms": 1500}}) == 1.5


@pytest.mark.unit
def test_resolve_timestamp_reads_second_keys_and_zero() -> None:
    assert _resolve_timestamp({"timestamp_seconds": 42}) == 42.0
    assert _resolve_timestamp({"start_sec": 7}) == 7.0
    assert _resolve_timestamp({"start": 90}) == 90.0
    # 0 is a valid, playable start -- not absence.
    assert _resolve_timestamp({"start_ms": 0}) == 0.0
    assert _resolve_timestamp({}) is None
    assert _resolve_timestamp({"start_ms": None}) is None


@pytest.mark.unit
def test_extract_citations_propagates_start_ms() -> None:
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "verbatim_text": "the beautiful state is uh connection joy love",
                "source_url": "https://youtu.be/abc123",
                "start_ms": 99_000,
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
            }
        ],
    }
    (citation,) = extract_citations(state)["citations"]
    assert citation["timestamp_seconds"] == 99.0
    assert citation["speaker"] == "Sri Preethaji"


# ---------------------------------------------------------------------------
# Issue 2b: public contract -- verified timestamps/speakers in, omissions out
# ---------------------------------------------------------------------------


def _doc(url: str = "https://youtu.be/abc123", **overrides) -> dict:
    base = {
        "title": "A Talk",
        "source_url": url,
        "text": "The beautiful state is connection, joy, love.",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_sanitize_carries_doc_start_ms_and_verified_speaker() -> None:
    out = _sanitize_citations(
        [{"url": "https://youtu.be/abc123"}],
        docs=[_doc(start_ms=137_000, speaker="Sri Krishnaji", speaker_verified=True)],
    )
    assert out[0]["timestamp_seconds"] == 137.0
    assert out[0]["speaker"] == "Sri Krishnaji"


@pytest.mark.unit
def test_sanitize_omits_unknown_and_unverified_speakers() -> None:
    out = _sanitize_citations(
        [
            {"url": "https://youtu.be/aaa"},
            {"url": "https://youtu.be/bbb", "speaker": "Sri Krishnaji"},
        ],
        docs=[
            _doc("https://youtu.be/aaa", speaker="Unknown"),
            _doc("https://youtu.be/bbb", speaker="Sri Krishnaji"),
        ],
    )
    by_url = {c["url"]: c for c in out}
    # Payload default "Unknown" must never reach the wire as the teacher.
    assert by_url["https://youtu.be/aaa"]["speaker"] is None
    # An unverified bare teacher name ships as the downgraded label (or is
    # omitted) -- never as the teacher's name. The UI renders the label path.
    assert by_url["https://youtu.be/bbb"]["speaker"] in (None, "unverified clip")
    assert by_url["https://youtu.be/bbb"]["speaker"] != "Sri Krishnaji"


@pytest.mark.unit
def test_sanitize_missing_speaker_verified_is_false_never_null() -> None:
    # Live 2026-10-11 (S2 partial evidence): bare-URL citations with no verification
    # evidence shipped speaker_verified=None. Absent evidence must read as unverified.
    out = _sanitize_citations(["https://youtu.be/aaa", {"url": "https://youtu.be/bbb"}], docs=[])
    assert [c["speaker_verified"] for c in out] == [False, False]


@pytest.mark.unit
def test_sanitize_prefers_citation_timestamp_over_doc() -> None:
    out = _sanitize_citations(
        [{"url": "https://youtu.be/abc123", "timestamp_seconds": 42.0}],
        docs=[_doc(start_ms=137_000, speaker="Sri Krishnaji", speaker_verified=True)],
    )
    assert out[0]["timestamp_seconds"] == 42.0


@pytest.mark.unit
def test_sanitize_leaves_timestamp_none_when_absent() -> None:
    out = _sanitize_citations([{"url": "https://youtu.be/abc123"}], docs=[_doc()])
    assert out[0].get("timestamp_seconds") is None


@pytest.mark.unit
def test_clean_wire_speaker_rules() -> None:
    assert clean_wire_speaker("Sri Preethaji", True) == "Sri Preethaji"
    assert clean_wire_speaker("Unknown") is None
    assert clean_wire_speaker("Unknown Channel", True) is None
    assert clean_wire_speaker("Sri Krishnaji", False, "Some Vlog") == "shared in Some Vlog"
    assert clean_wire_speaker("Sri Krishnaji") == "unverified clip"
    assert clean_wire_speaker("pkconsciousness") is None
    assert clean_wire_speaker(None) is None


@pytest.mark.unit
def test_coerce_copies_drop_placeholders_and_read_start_ms() -> None:
    from app.chat_engine import ChatEngine
    from app.orchestrator import _coerce_citations as orchestrate_coerce

    raw = [
        {
            "url": "https://youtu.be/aaa",
            "speaker": "Unknown",
            "timestamp_seconds": None,
            "start_ms": 60_000,
        },
        {"url": "https://youtu.be/bbb", "speaker": "Sri Preethaji", "speaker_verified": True},
    ]
    for coerce in (ChatEngine._coerce_citations, orchestrate_coerce):
        by_url = {c["url"]: c for c in coerce(raw)}
        assert by_url["https://youtu.be/aaa"]["speaker"] is None
        assert by_url["https://youtu.be/aaa"]["timestamp_seconds"] == 60.0
        assert by_url["https://youtu.be/bbb"]["speaker"] == "Sri Preethaji"


# ---------------------------------------------------------------------------
# Issue 2c: searcher carries payload timing/speaker fields to the docs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_searcher_carries_timing_and_speaker_fields() -> None:
    from services.qdrant.searcher import QdrantSearcher

    payload = {
        "text": "The beautiful state is connection.",
        "source_url": "https://youtu.be/abc123",
        "title": "A Talk",
        "speaker": "Sri Preethaji",
        "speaker_verified": True,
        "channel": "Ekam",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "tenant_id": "t",
        "corpus_id": "c",
    }
    hit = MagicMock()
    hit.payload = payload
    hit.score = 0.9
    hit.id = "p1"
    hit.vector = None
    results = MagicMock()
    results.points = [hit]
    client = MagicMock()
    client.query_points.return_value = results

    docs = QdrantSearcher(client, "test_collection").search(
        query_vector=[0.1] * 1024, limit=5, teacher_id=None
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc["start_ms"] == 99_000
    assert doc["end_ms"] == 129_000
    assert doc["speaker_verified"] is True
    assert doc["channel"] == "Ekam"
    assert doc["timestamp_seconds"] is None  # absent stays absent


if __name__ == "__main__":  # ponytail: self-check
    test_honest_unverified_details_preserves_counts_without_passed()
    test_demote_is_noop_on_honest_failure_details()
    test_demote_backfills_missing_method()
    test_resolve_timestamp_reads_start_ms_as_seconds()
    test_resolve_timestamp_reads_second_keys_and_zero()
    test_sanitize_carries_doc_start_ms_and_verified_speaker()
    test_sanitize_omits_unknown_and_unverified_speakers()
    test_sanitize_prefers_citation_timestamp_over_doc()
    test_sanitize_leaves_timestamp_none_when_absent()
    test_clean_wire_speaker_rules()
    print("verdict/citation plumbing self-check passed")
