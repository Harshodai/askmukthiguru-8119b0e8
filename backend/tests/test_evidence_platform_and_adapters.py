"""Tests for multi-format rights, Qdrant/Memgraph/OKF adapters, RRF fusion, and claim verification."""

from __future__ import annotations

from types import SimpleNamespace

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    EpistemicCategory,
    EvidenceCandidate,
    content_sha256,
)
from services.evidence_adapters.claim_verifier import ClaimVerificationService
from services.evidence_adapters.fusion import EvidenceFusionEngine, RRFConfig
from services.evidence_adapters.memgraph_adapter import MemgraphEvidenceAdapter
from services.evidence_adapters.okf_adapter import OKFEvidenceAdapter
from services.evidence_adapters.qdrant_adapter import QdrantEvidenceAdapter
from services.first_person_rights import source_is_authoritatively_licensed


def test_editorial_demand_returns_no_opportunities_without_telemetry(monkeypatch):
    from app.api import editorial

    monkeypatch.setattr(editorial, "_EDITORIAL_SINGLETON", None)
    service = editorial.get_editorial_service(SimpleNamespace(telemetry_sink=None))

    assert service.discover_opportunities() == []


def test_multiformat_rights_allows_books_and_websites_when_registered(monkeypatch):
    import services.qdrant.indexer as qidx

    registered = {
        "https://ekam.org/books/sufkor": "licensed",
        "https://www.amazon.in/Four-Sacred-Secrets": "licensed",
        "https://www.youtube.com/watch?v=abc123def45": "licensed",
    }
    monkeypatch.setattr(
        qidx,
        "resolve_source_rights_status",
        lambda source_url, video_id=None: registered.get(source_url, "unverified"),
    )

    assert source_is_authoritatively_licensed(
        source_url="https://ekam.org/books/sufkor",
        video_id=None,
        domain_rights_status="licensed",
        source_type="book",
    )
    assert source_is_authoritatively_licensed(
        source_url="https://www.amazon.in/Four-Sacred-Secrets",
        video_id="",
        domain_rights_status="licensed",
        source_type="book",
    )
    # Unregistered book fails closed
    assert not source_is_authoritatively_licensed(
        source_url="https://unknown.example/book.pdf",
        video_id=None,
        domain_rights_status="licensed",
        source_type="book",
    )
    # Video without video_id still fails closed
    assert not source_is_authoritatively_licensed(
        source_url="https://www.youtube.com/watch?v=abc123def45",
        video_id="",
        domain_rights_status="licensed",
        source_type="video",
    )


def test_qdrant_adapter_normalizes_book_and_video_hits(monkeypatch):
    import services.first_person_rights as fpr

    monkeypatch.setattr(fpr, "source_is_authoritatively_licensed", lambda **_: True)
    # Also patch inside adapter module
    import services.evidence_adapters.qdrant_adapter as qa

    monkeypatch.setattr(qa, "source_is_authoritatively_licensed", lambda **_: True)

    fake_hits = [
        SimpleNamespace(
            id="pt-book-1",
            score=0.88,
            payload={
                "source_span_id": "ev-book-1",
                "source_type": "book",
                "title": "The Four Sacred Secrets",
                "chapter": "Chapter 3: The Warring Self",
                "page_number": 74,
                "source_url": "https://www.amazon.in/Four-Sacred-Secrets",
                "guru_id": "preethaji_krishnaji",
                "speaker_verified": True,
                "domain_rights_status": "licensed",
                "verbatim_text": "Suffering arises from obsessive self-centric thinking.",
            },
        ),
        SimpleNamespace(
            id="pt-vid-1",
            score=0.82,
            payload={
                "source_span_id": "ev-vid-1",
                "video_id": "abc123def45",
                "source_url": "https://www.youtube.com/watch?v=abc123def45",
                "guru_id": "krishnaji",
                "speaker_verified": True,
                "domain_rights_status": "licensed",
                "start_ms": 12000,
                "end_ms": 28000,
                "verbatim_text": "When division ends, inner stillness awakens.",
            },
        ),
    ]

    class _FakeQdrant:
        def query_points(self, **kwargs):
            return SimpleNamespace(points=fake_hits)

    adapter = QdrantEvidenceAdapter(_FakeQdrant(), "first_person_v14")
    results = adapter.search(query_dense=[0.1, 0.2, 0.3], limit=5)
    assert len(results) == 2
    assert results[0].source_type == "book"
    assert results[0].page_number == 74
    assert results[0].chapter == "Chapter 3: The Warring Self"
    assert results[1].start_time == 12.0
    assert results[1].teacher_id == "krishnaji"


def test_memgraph_adapter_enforces_rights_at_store_boundary():
    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def run(self, cypher, **params):
            assert "rights_status = 'licensed'" in cypher
            return [
                {
                    "evidence_id": "ev-licensed",
                    "video_id": "vid12345678",
                    "guru_id": "preethaji",
                    "verbatim_text": "Peace is your true nature.",
                    "start_ms": 5000,
                    "end_ms": 15000,
                    "rights_status": "licensed",
                    "matched_concepts": ["Beautiful State"],
                },
                {
                    "evidence_id": "ev-unverified-leak",
                    "video_id": "vid99999999",
                    "guru_id": "preethaji",
                    "verbatim_text": "Should never pass.",
                    "rights_status": "unverified",
                },
            ]

    class _FakeDriver:
        def session(self):
            return _FakeSession()

    adapter = MemgraphEvidenceAdapter(_FakeDriver(), tenant_id="oneness")
    cands = adapter.discover_by_concepts(["Beautiful State"], limit=5)
    assert [c.evidence_id for c in cands] == ["ev-licensed"]


def test_okf_adapter_quarantines_unverified_and_filters_generic_tags():
    entries = [
        {
            "title": "Unverified Draft",
            "body": "Unverified summary.",
            "verified": None,
            "tags": ["oneness", "teaching"],
            "embedding": [1.0, 0.0],
        },
        {
            "title": "Verified Concept",
            "body": "Verified wisdom note.",
            "verified": True,
            "resource": "https://www.youtube.com/watch?v=abc123def45",
            "source_span_id": "ev-okf-1",
            "tags": ["oneness", "teaching", "beautiful state"],
            "embedding": [0.95, 0.05],
        },
    ]
    adapter = OKFEvidenceAdapter(compiled_entries=entries)
    results = adapter.search(query_dense=[1.0, 0.0], min_similarity=0.4)
    assert len(results) == 1
    assert results[0].evidence_id == "ev-okf-1"
    assert results[0].concepts == ["beautiful state"]


def test_rrf_fusion_deduplicates_identical_evidence_across_three_stores():
    shared_id = "ev-canonical-42"
    q_cand = EvidenceCandidate(
        evidence_id=shared_id,
        source_id="src-1",
        teacher_id="preethaji",
        speaker_verified=True,
        text="Live in a beautiful state.",
        start_time=10.0,
        end_time=20.0,
        retrieval_source="qdrant",
        retrieval_score=0.91,
        rights_status="licensed",
    )
    m_cand = EvidenceCandidate(
        evidence_id=shared_id,
        source_id="src-1",
        teacher_id="preethaji",
        speaker_verified=False,
        text="Live in a beautiful state.",
        retrieval_source="memgraph",
        retrieval_score=1.0,
        graph_paths=["seed-[TU_CONTINUES]->ev-canonical-42"],
        rights_status="licensed",
    )
    o_cand = EvidenceCandidate(
        evidence_id=shared_id,
        source_id="src-1",
        teacher_id="preethaji",
        text="Live in a beautiful state.",
        retrieval_source="okf",
        retrieval_score=0.85,
        concepts=["beautiful state"],
        rights_status="licensed",
    )

    fused = EvidenceFusionEngine(RRFConfig(k0=60)).fuse(
        {"qdrant": [q_cand], "memgraph": [m_cand], "okf": [o_cand]},
        limit=10,
    )
    assert len(fused) == 1
    assert fused[0].evidence_id == shared_id
    assert fused[0].corroborating_sources == ["qdrant", "memgraph", "okf"]
    assert fused[0].speaker_verified is True
    assert fused[0].start_time == 10.0
    assert "beautiful state" in fused[0].concepts


def test_claim_verifier_catches_misattribution_fabrication_and_stale_versions():
    ev_k = EvidenceCandidate(
        evidence_id="ev-k1",
        source_id="src-k1",
        teacher_id="krishnaji",
        speaker_verified=True,
        text="Fear is born when the mind projects a future threat.",
        retrieval_source="qdrant",
        source_version="2",
        content_hash=content_sha256("Fear is born when the mind projects a future threat."),
    )
    verifier = ClaimVerificationService()

    # 1. Valid verbatim claim
    ok_rep = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c1",
                claim_text="Fear is born when the mind projects a future threat.",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="Sri Krishnaji",
                evidence_ids=["ev-k1"],
            )
        ],
        [ev_k],
        expected_source_versions={"src-k1": "2"},
    )
    assert ok_rep.passed is True

    # 2. Wrong teacher attribution (Preethaji instead of Krishnaji)
    bad_teacher = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c2",
                claim_text="Fear is born when the mind projects a future threat.",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="Sri Preethaji",
                evidence_ids=["ev-k1"],
            )
        ],
        [ev_k],
    )
    assert bad_teacher.passed is False
    assert bad_teacher.misattributed_count == 1

    # 3. Fabricated quote not in canonical source
    bad_quote = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c3",
                claim_text="I promise your suffering will vanish overnight.",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="krishnaji",
                evidence_ids=["ev-k1"],
            )
        ],
        [ev_k],
    )
    assert bad_quote.passed is False
    assert bad_quote.quote_mismatch_count == 1

    # 4. Outdated source version
    stale_rep = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c4",
                claim_text="Fear is born when the mind projects a future threat.",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="krishnaji",
                evidence_ids=["ev-k1"],
            )
        ],
        [ev_k],
        expected_source_versions={"src-k1": "3"},
    )
    assert stale_rep.passed is False
    assert stale_rep.outdated_version_count == 1
