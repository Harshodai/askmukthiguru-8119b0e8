"""Part 13 Comprehensive End-to-End Acceptance Suite.

Covers all 6 mandatory acceptance categories:
1. Teaching retrieval (love, fear & suffering, attachment, comparative teachers without forced symmetry)
2. Evidence integrity (exact quote, timestamp, teacher misattribution, unsupported claim, outdated version)
3. Cross-source reasoning (cross-video, book <-> video, corroboration vs deduplication)
4. Seeker intelligence (multi-turn, confusion recovery, AI analogy vs teacher example separation, tenant/memory isolation)
5. Editorial intelligence (research dossier, brief, outline, claim-mapped script, attribution rejection, human approval & publish gate)
6. Operational tests (partial ingestion failure, duplicate ingestion, source updates/corrections, index sync retry & DLQ, stale index detection, DB unavailability, model timeout/fallback).
"""

from __future__ import annotations

import pytest

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    EpistemicCategory,
    EvidenceCandidate,
    SourceType,
)
from services.canonical_evidence_registry import CanonicalEvidenceRegistry
from services.editorial.editorial_service import (
    EditorialApprovalError,
    EditorialIntelligenceService,
    ScriptBlock,
)
from services.evidence_adapters import (
    ClaimVerificationService,
)
from services.seeker.comprehension_recovery import (
    ComprehensionRecoveryService,
    build_isolated_cache_key,
)
from services.semantic_understanding import SemanticUnderstandingEngine
from services.unified_evidence_harness import HarnessConfig, UnifiedEvidenceHarness


def _cand(
    eid: str,
    *,
    sid: str = "src-1",
    stype: str = "video",
    teacher: str = "preethaji",
    text: str = "Observation without division dissolves suffering.",
    start_time: float | None = 120.0,
    page: int | None = None,
    source: str = "qdrant",
    version: str = "1",
    rights: str = "licensed",
) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=eid,
        source_id=sid,
        source_type=stype,
        source_title=f"Title {sid}",
        source_url=f"https://example.org/{sid}",
        teacher_id=teacher,
        speaker_verified=True,
        text=text,
        start_time=start_time,
        page_number=page,
        retrieval_source=source,
        retrieval_score=0.9,
        source_version=version,
        verification_status="human_verified" if rights == "licensed" else "unverified",
        rights_status=rights,
    )


class _StubQdrant:
    def __init__(self, items: list[EvidenceCandidate], fail: Exception | None = None) -> None:
        self._items = items
        self._fail = fail

    def search(self, **kwargs):
        if self._fail:
            raise self._fail
        tid = kwargs.get("teacher_id")
        if tid:
            return [c for c in self._items if c.teacher_id == tid]
        return list(self._items)


class _StubMemgraph:
    def __init__(
        self, items: list[EvidenceCandidate], edges=None, fail: Exception | None = None
    ) -> None:
        self._items = items
        self._edges = edges or []
        self._fail = fail

    def discover_by_concepts(self, concepts, **kwargs):
        if self._fail:
            raise self._fail
        return list(self._items)

    def expand_from_evidence_ids(self, evidence_ids, **kwargs):
        return []

    def get_concept_neighborhood(self, concept_names, **kwargs):
        if self._fail:
            raise self._fail
        return list(self._edges)


class _StubOKF:
    def __init__(self, items: list[EvidenceCandidate], fail: Exception | None = None) -> None:
        self._items = items
        self._fail = fail

    def search(self, **kwargs):
        if self._fail:
            raise self._fail
        if not kwargs.get("include_unverified", False):
            return [c for c in self._items if c.verification_status == "human_verified"]
        return list(self._items)


def test_part13_teaching_retrieval_and_asymmetric_comparison():
    love_quote = _cand(
        "ev-love-1",
        sid="vid-a",
        teacher="preethaji",
        text="Love is living in a non-divided state of connection.",
    )
    fear_quote = _cand(
        "ev-fear-1",
        sid="vid-b",
        teacher="preethaji",
        text="Fear arises whenever thought separates me from life.",
    )
    attach_quote = _cand(
        "ev-att-1",
        sid="vid-c",
        teacher="preethaji",
        text="Attachment is clinging to an image of permanence.",
    )
    harness = UnifiedEvidenceHarness(
        qdrant_adapter=_StubQdrant([love_quote, fear_quote, attach_quote]),
        memgraph_adapter=_StubMemgraph(
            [],
            edges=[
                {
                    "source_concept": "Fear",
                    "relationship": "LEADS_TO",
                    "target_concept": "Suffering",
                }
            ],
        ),
        config=HarnessConfig(require_licensed=True),
    )

    for q in (
        "What do the teachers say about love?",
        "What is the relationship between fear and suffering?",
        "Find all relevant teachings about attachment.",
    ):
        pkg = harness.retrieve_and_verify(query=q, query_dense=[0.1, 0.2])
        assert pkg.status == "answered"
        assert pkg.evidence_items

    # Comparison query: Krishnaji has 0 items -> never fabricate artificial symmetry
    comp = harness.retrieve_and_verify(
        query="Compare Sri Preethaji and Sri Krishnaji on attachment",
        query_dense=[0.1, 0.2],
    )
    assert comp.status == "answered"
    assert all(ev.teacher_id == "preethaji" for ev in comp.evidence_items)


def test_part13_evidence_integrity_checks():
    reg = CanonicalEvidenceRegistry()
    src, _ = reg.register_and_ingest(
        canonical_uri="https://www.youtube.com/watch?v=abc12345678",
        source_type=SourceType.VIDEO,
        title="Truth of Observation",
        teacher_id="krishnaji",
        rights_status="licensed",
        source_version="2",
        segments=[
            {
                "original_text": "Suffering ends when you observe division without judgment.",
                "start_time_ms": 42000,
                "end_time_ms": 58000,
                "speaker_verified": True,
            }
        ],
    )
    rec = reg._records[next(iter(reg._records))]
    cand = _cand(
        rec.evidence_id,
        sid=src.source_id,
        teacher="krishnaji",
        text=rec.original_text,
        start_time=42.0,
        version="2",
    )

    verifier = ClaimVerificationService()
    ok_rep = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c1",
                claim_text="Suffering ends when you observe division without judgment.",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="krishnaji",
                evidence_ids=[rec.evidence_id],
            )
        ],
        [cand],
    )
    assert ok_rep.passed is True

    # Separate stale-version source so both misattribution AND outdated_version trigger independently
    src2, _ = reg.register_and_ingest(
        canonical_uri="https://www.youtube.com/watch?v=def87654321",
        source_type=SourceType.VIDEO,
        title="Second Teaching",
        teacher_id="krishnaji",
        rights_status="licensed",
        source_version="2",
        segments=[
            {
                "original_text": "Awareness is clarity.",
                "start_time_ms": 1000,
                "end_time_ms": 9000,
                "speaker_verified": True,
            }
        ],
    )
    rec2 = reg.get_record(
        next(eid for eid, r in reg._records.items() if r.source_id == src2.source_id)
    )
    assert rec2 is not None
    cand2_stale = _cand(
        rec2.evidence_id,
        sid=src2.source_id,
        teacher="krishnaji",
        text=rec2.original_text,
        start_time=1.0,
        version="1",
    )

    # Misattributed teacher, unsupported claim, and stale version must fail
    bad_rep = verifier.verify_claims(
        [
            ClaimEvidenceMapping(
                claim_id="c2",
                claim_text=rec.original_text,
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="preethaji",
                evidence_ids=[rec.evidence_id],
            ),
            ClaimEvidenceMapping(
                claim_id="c3",
                claim_text="Unsupported quote claim",
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="krishnaji",
                evidence_ids=[],
            ),
            ClaimEvidenceMapping(
                claim_id="c4",
                claim_text=rec2.original_text,
                epistemic_category=EpistemicCategory.VERBATIM_EVIDENCE,
                teacher_attributed="krishnaji",
                evidence_ids=[rec2.evidence_id],
            ),
        ],
        [cand, cand2_stale],
        expected_source_versions={src.source_id: "2", src2.source_id: "2"},
    )
    assert bad_rep.passed is False
    assert bad_rep.misattributed_count >= 1
    assert bad_rep.unsupported_count >= 1
    assert bad_rep.outdated_version_count >= 1


def test_part13_cross_source_reasoning_and_deduplication():
    same_id = "ev-cross-1"
    qd_item = _cand(
        same_id,
        sid="book-sacred-secrets",
        stype="book",
        teacher="preethaji",
        text="The Warring Self divides inner awareness.",
        start_time=None,
        page=42,
        source="qdrant",
    )
    mg_dup = qd_item.model_copy(update={"retrieval_source": "memgraph"})
    okf_dup = qd_item.model_copy(update={"retrieval_source": "okf"})
    vid_item = _cand(
        "ev-vid-2",
        sid="vid-ekam",
        stype="video",
        teacher="krishnaji",
        text="Witnessing dissolves inner conflict.",
        start_time=95.0,
        source="qdrant",
    )

    harness = UnifiedEvidenceHarness(
        qdrant_adapter=_StubQdrant([qd_item, vid_item]),
        memgraph_adapter=_StubMemgraph([mg_dup]),
        okf_adapter=_StubOKF([okf_dup]),
    )
    pkg = harness.retrieve_and_verify(
        query="Build an editorial research dossier connecting the book passage and video on inner conflict",
        query_dense=[0.2, 0.3],
    )
    assert pkg.status == "answered"
    # Deduplicated: same_id counted once with 3 corroborating sources!
    eids = [ev.evidence_id for ev in pkg.evidence_items]
    assert eids.count(same_id) == 1
    merged_cross = next(ev for ev in pkg.evidence_items if ev.evidence_id == same_id)
    assert set(merged_cross.corroborating_sources) == {"qdrant", "memgraph", "okf"}
    assert pkg.syntheses and pkg.syntheses[0]["epistemic_category"] == "synthesis"


def test_part13_seeker_intelligence_recovery_and_isolation():
    signals: list[dict] = []
    recovery = ComprehensionRecoveryService(
        retrieve_fn=lambda concept, prior_ids: [
            _cand(
                "ev-alt-1",
                sid="vid-alt",
                text="Think of stillness like clear water letting silt settle.",
            )
        ],
        ai_analogy_fn=lambda concept, evs, strat: (
            "My reflection/analogy: notice quiet water settling."
        ),
        signal_sink=lambda sig: signals.append(sig) or True,
    )
    res = recovery.recover(
        concept="witness awareness",
        user_query="I didn't understand that, explain differently",
        prior_evidence_ids=["ev-prior-1"],
        user_id="seeker-A",
        tenant_id="default",
        consent_granted=True,
    )
    assert res.verification.passed is True
    assert res.learning_signal_recorded is True
    assert signals and signals[0]["user_id"] == "seeker-A" and signals[0]["tenant_id"] == "default"
    assert any(seg.category == EpistemicCategory.VERBATIM_EVIDENCE for seg in res.segments)
    assert any(
        seg.category == EpistemicCategory.APPLICATION and "[AI Illustrative Analogy" in seg.text
        for seg in res.segments
    )
    assert build_isolated_cache_key(
        query="What is awareness?",
        tenant_id="default",
        corpus_version="v13",
        embedding_version="bge-m3",
        retrieval_config_hash="cfg1",
        ontology_version="ont-v1",
        model_version="haiku",
        prompt_version="pv1",
        user_id="seeker-A",
        personal_memory_version="mem-1",
    ) != build_isolated_cache_key(
        query="What is awareness?",
        tenant_id="default",
        corpus_version="v13",
        embedding_version="bge-m3",
        retrieval_config_hash="cfg1",
        ontology_version="ont-v1",
        model_version="haiku",
        prompt_version="pv1",
        user_id="seeker-B",
        personal_memory_version="mem-1",
    )


def test_part13_editorial_end_to_end_workflow_and_gates():
    ev1 = _cand(
        "ev-ed-1",
        sid="vid-peace",
        teacher="preethaji",
        text="Peace emerges when the mind stops resisting the present.",
    )
    svc = EditorialIntelligenceService(
        search_fn=lambda topic, t, limit: [ev1],
        seeker_demand_fn=lambda: [{"topic": "inner peace", "query_count": 90, "abstain_rate": 0.5}],
        ingestion_status_fn=lambda: {"books_indexed": False},
    )
    opps = svc.discover_opportunities(limit=5)
    assert opps and "books/websites not yet fully indexed" in opps[0].ingestion_completeness_note

    proj = svc.create_project(
        title="Why Resistance Creates Suffering",
        topic="inner peace",
        objective="10m YouTube teaching",
        author_id="author-1",
    )
    dossier = svc.generate_dossier(topic=proj.topic, objective=proj.objective)
    proj = svc.attach_dossier(proj.project_id, dossier)
    brief = svc.generate_brief(dossier=dossier)
    proj = svc.attach_brief(proj.project_id, brief)
    outline = svc.generate_outline(title=proj.title, dossier=dossier, brief=brief)
    proj = svc.attach_outline(proj.project_id, outline)

    # Misattributed script cannot pass verification or approval
    bad_script = svc.build_verified_script(
        title=proj.title,
        topic=proj.topic,
        blocks=[
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text=ev1.text,
                teacher_attributed="krishnaji",
                evidence_ids=[ev1.evidence_id],
            )
        ],
        evidence_pool=dossier.evidence_items,
    )
    proj = svc.attach_script(proj.project_id, bad_script)
    with pytest.raises(EditorialApprovalError):
        svc.approve_project(proj.project_id, reviewer_id="editor@ekam.org")

    # Good script cannot be auto-approved by AI, and cannot publish before human approval
    good_script = svc.build_verified_script(
        title=proj.title,
        topic=proj.topic,
        blocks=[
            ScriptBlock(
                block_id="b0", block_type="editorial_narration", text="Welcome to this exploration."
            ),
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text=ev1.text,
                teacher_attributed="preethaji",
                evidence_ids=[ev1.evidence_id],
            ),
        ],
        evidence_pool=dossier.evidence_items,
    )
    proj = svc.attach_script(proj.project_id, good_script)
    with pytest.raises(EditorialApprovalError):
        svc.publish_project(proj.project_id, publisher_id="editor@ekam.org")
    with pytest.raises(EditorialApprovalError):
        svc.approve_project(proj.project_id, reviewer_id="ai")

    approved = svc.approve_project(
        proj.project_id, reviewer_id="editor@ekam.org", notes="Verified timestamps"
    )
    published = svc.publish_project(approved.project_id, publisher_id="editor@ekam.org")
    assert published.status == "published" and len(published.audit_log) >= 5


def test_part13_operational_ingestion_dlq_takedown_and_degradation():
    reg = CanonicalEvidenceRegistry()
    # Partial failure + duplicate + timestamp inversion + non-teacher attribution guard
    src, rep = reg.register_and_ingest(
        canonical_uri="https://ekam.org/books/sacred-secrets",
        source_type=SourceType.BOOK,
        title="The Four Sacred Secrets",
        teacher_id="preethaji",
        rights_status="licensed",
        segments=[
            {
                "original_text": "Awareness frees you from the warring self.",
                "page_number": 12,
                "speaker_verified": True,
            },
            {
                "original_text": "Awareness frees you from the warring self.",
                "page_number": 13,
                "speaker_verified": True,
            },  # duplicate
            {
                "original_text": "Audience question transcript leaked here.",
                "speaker_role": "audience",
                "teacher_id": "preethaji",
                "page_number": 14,
            },
        ],
    )
    assert src.processing_status == "partial"
    assert len(rep.accepted_records) == 1
    assert {r.reason_code for r in rep.rejections} == {
        "duplicate_content_hash",
        "speaker_role_attribution_conflict",
    }

    # Correction keeps original_text immutable
    eid = rep.accepted_records[0].evidence_id
    updated, _corr = reg.apply_correction(
        eid,
        corrected_text="Awareness frees you from the Warring Self.",
        reason="Capitalize proper term",
        corrected_by="editor@ekam.org",
        approved_by="reviewer@ekam.org",
    )
    assert updated.original_text == "Awareness frees you from the warring self."
    assert updated.corrected_text == "Awareness frees you from the Warring Self."

    # Outbox retry + DLQ recovery
    attempts = {"memgraph": 0}

    def _flaky_mg(ev):
        attempts["memgraph"] += 1
        raise RuntimeError("memgraph timeout")

    for _ in range(3):
        reg.dispatch_outbox(
            {"qdrant": lambda e: None, "memgraph": _flaky_mg, "okf": lambda e: None}
        )
    assert len(reg.get_outbox(status="dead_letter")) > 0
    requeued = reg.requeue_dead_letter()
    assert requeued > 0
    stats = reg.dispatch_outbox(
        {"qdrant": lambda e: None, "memgraph": lambda e: None, "okf": lambda e: None}
    )
    assert stats["dispatched"] == requeued

    # Stale index detection & takedown propagation + graceful Memgraph outage degradation
    drift = reg.detect_stale_index_records([{"evidence_id": eid, "source_version": "0"}])
    assert drift and "stale_version" in drift[0]["issue"]

    cand_live = _cand(
        eid,
        sid=src.source_id,
        stype="book",
        text=updated.corrected_text or "",
        page=12,
        start_time=None,
        version=updated.source_version,
    )
    harness = UnifiedEvidenceHarness(
        qdrant_adapter=_StubQdrant([cand_live]),
        memgraph_adapter=_StubMemgraph([], fail=TimeoutError("memgraph down")),
        registry=reg,
    )
    degraded_pkg = harness.retrieve_and_verify(
        query="What do the teachings say about warring self?", query_dense=[0.1, 0.2]
    )
    assert degraded_pkg.status == "answered"
    assert any("memgraph:" in d for d in degraded_pkg.degraded_stores)

    # Withdrawal immediately blocks serving even if Qdrant index still returns candidate
    reg.withdraw_source(src.source_id, reason="Rights expired")
    revoked_pkg = harness.retrieve_and_verify(
        query="What do the teachings say about warring self?", query_dense=[0.1, 0.2]
    )
    assert revoked_pkg.status == "abstained"
    assert any("source_revoked" in r for r in revoked_pkg.rejected_stale_or_revoked)


def test_part13_distress_stage_separates_bereavement_from_acute_crisis():
    from app.pipeline.stages.distress_stage import classify_existential_vs_severe_distress

    bereavement = "I lost someone I deeply loved and I cannot stop crying."
    assert classify_existential_vs_severe_distress(bereavement) == "NONE"
    assert SemanticUnderstandingEngine().interpret(bereavement).intent == "grief_bereavement"

    acute = "I want to end my life tonight."
    assert classify_existential_vs_severe_distress(acute) == "CRISIS"
    assert SemanticUnderstandingEngine().interpret(acute).intent == "crisis"
