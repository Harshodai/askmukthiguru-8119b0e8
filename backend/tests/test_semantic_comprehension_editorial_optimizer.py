"""Tests for Semantic Understanding, Seeker Comprehension Recovery, Editorial Intelligence, and Retrieval Optimizer."""

from __future__ import annotations

import math

import pytest

from domain.evidence_contract import EvidenceCandidate
from evaluation.fp_rank_metrics import graded_ndcg_at_k
from evaluation.retrieval_optimizer import (
    ControlledRetrievalOptimizer,
    RetrievalCandidateConfig,
    SafetyLockError,
)
from services.editorial.editorial_service import (
    EditorialApprovalError,
    EditorialIntelligenceService,
    ScriptBlock,
)
from services.seeker.comprehension_recovery import (
    ComprehensionRecoveryService,
    build_isolated_cache_key,
)
from services.semantic_understanding import SemanticUnderstandingEngine, plan_retrieval


def _mock_embedder(texts: list[str]) -> list[list[float]]:
    """Deterministic semantic vector stub mapping concept families onto orthogonal axes."""
    out: list[list[float]] = []
    for t in texts:
        low = t.lower()
        vec = [0.05] * 10
        if any(
            w in low
            for w in (
                "beautiful state",
                "suffering",
                "oneness",
                "ego",
                "love",
                "fear",
                "attachment",
            )
        ):
            vec[0] = 1.0
        if any(w in low for w in ("steps", "soul sync", "serene mind", "aham", "practice")):
            vec[1] = 1.0
        if any(
            w in low
            for w in (
                "low for weeks",
                "happy anymore",
                "feel like doing",
                "disconnected",
                "kastamga",
                "dukhi",
                "tired of everything",
            )
        ):
            vec[2] = 1.0
        if any(w in low for w in ("lost someone", "crying", "passed away", "grief", "mourning")):
            vec[3] = 1.0
        if any(w in low for w in ("compare", "differ", "perspective")):
            vec[4] = 1.0
        if any(w in low for w in ("sacred secrets", "sufkor", "exact quote", "timestamp")):
            vec[5] = 1.0
        if any(
            w in low
            for w in (
                "didn't understand",
                "confused",
                "simpler",
                "different example",
                "too abstract",
            )
        ):
            vec[6] = 1.0
        if any(
            w in low
            for w in ("dossier", "underexplored", "fact check", "draft script", "editorial")
        ):
            vec[7] = 1.0
        if any(
            w in low for w in ("python", "stock price", "france", "cricket", "sort a dictionary")
        ):
            vec[8] = 1.0
        out.append(vec)
    return out


def test_semantic_engine_handles_indirect_distress_grief_and_code_switching():
    engine = SemanticUnderstandingEngine(embed_fn=_mock_embedder)

    # Indirect depression/emotional struggle without literal "depression" keyword
    low_mood = engine.interpret(
        "Nothing makes me happy anymore and I don't feel like doing anything."
    )
    assert low_mood.intent == "emotional_support"
    assert low_mood.emotional_signal == "persistent_distress"

    # Telugu-English code-switching
    telugu = engine.interpret("Chala kastamga undi, manasu prashantamga ledu.")
    assert telugu.intent == "emotional_support"

    # Bereavement grief must NOT falsely trigger suicide crisis rail
    grief = engine.interpret("I lost someone I deeply loved and I cannot stop crying.")
    assert grief.intent == "grief_bereavement"
    assert grief.emotional_signal == "grief_bereavement"

    # Explicit acute self-harm triggers deterministic rail
    crisis = engine.interpret("I have no reason to live and want to end my life.")
    assert crisis.intent == "crisis"
    assert crisis.method == "acute_safety_rail"
    assert plan_retrieval(crisis).strategy == "safety_redirect"


def test_retrieval_planner_comparative_never_forces_artificial_symmetry():
    engine = SemanticUnderstandingEngine(embed_fn=_mock_embedder)
    interp = engine.interpret("Compare what Sri Preethaji and Sri Krishnaji teach about fear.")
    plan = plan_retrieval(interp)
    assert plan.strategy == "comparative_teachers"
    assert plan.force_equal_teachers is False
    assert plan.budget_mode == "thinking"


def test_seeker_comprehension_recovery_excludes_prior_evidence_and_labels_ai_analogy():
    prior_ev = EvidenceCandidate(
        evidence_id="ev-prior-1",
        source_id="src-1",
        teacher_id="preethaji",
        speaker_verified=True,
        text="Observation without division dissolves inner conflict.",
        start_time=45.0,
        retrieval_source="qdrant",
        rights_status="licensed",
    )
    alt_ev = EvidenceCandidate(
        evidence_id="ev-alt-2",
        source_id="src-2",
        source_title="Ekam Talk on Observation",
        teacher_id="krishnaji",
        speaker_verified=True,
        text="To observe without naming or judging is to watch anger like a passing cloud.",
        start_time=120.0,
        retrieval_source="qdrant",
        rights_status="licensed",
    )

    recorded_signals: list[dict] = []
    svc = ComprehensionRecoveryService(
        retrieve_fn=lambda q, excl: [prior_ev, alt_ev],
        signal_sink=lambda s: recorded_signals.append(s) or True,
        ai_analogy_fn=lambda concept, evs, strat: (
            "Think of watching traffic from a quiet balcony instead of jumping into the street."
        ),
    )
    res = svc.recover(
        concept="observation without division",
        user_query="I didn't understand that, explain differently",
        prior_evidence_ids=["ev-prior-1"],
        prior_strategies=["simpler_language"],
        user_id="user-123",
        tenant_id="oneness",
        consent_granted=True,
        familiarity_level="beginner",
    )
    assert [e.evidence_id for e in res.evidence_used] == ["ev-alt-2"]
    assert res.strategy_used == "teacher_parable"
    assert res.verification.passed is True
    assert res.segments[0].category.value == "verbatim_evidence"
    assert res.segments[1].category.value == "application"
    assert "[AI Illustrative Analogy" in res.segments[1].text
    assert res.learning_signal_recorded is True
    assert recorded_signals[0]["user_id"] == "user-123"


def test_cache_key_isolation_prevents_cross_user_and_incognito_leakage():
    assert (
        build_isolated_cache_key(
            query="What is love?",
            corpus_version="v14",
            embedding_version="bge-m3",
            retrieval_config_hash="cfg1",
            ontology_version="ont1",
            model_version="m1",
            prompt_version="p1",
            incognito=True,
        )
        is None
    )

    # Authenticated user missing memory version fails closed (bypass)
    assert (
        build_isolated_cache_key(
            query="What is love?",
            corpus_version="v14",
            embedding_version="bge-m3",
            retrieval_config_hash="cfg1",
            ontology_version="ont1",
            model_version="m1",
            prompt_version="p1",
            user_id="user-a",
            tenant_id="oneness",
            personal_memory_version=None,
        )
        is None
    )

    k_a = build_isolated_cache_key(
        query="What is love?",
        corpus_version="v14",
        embedding_version="bge-m3",
        retrieval_config_hash="cfg1",
        ontology_version="ont1",
        model_version="m1",
        prompt_version="p1",
        user_id="user-a",
        tenant_id="oneness",
        personal_memory_version="mem-1",
    )
    k_b = build_isolated_cache_key(
        query="What is love?",
        corpus_version="v14",
        embedding_version="bge-m3",
        retrieval_config_hash="cfg1",
        ontology_version="ont1",
        model_version="m1",
        prompt_version="p1",
        user_id="user-b",
        tenant_id="oneness",
        personal_memory_version="mem-1",
    )
    assert k_a is not None and k_b is not None and k_a != k_b


def test_editorial_workflow_blocks_misattributed_scripts_and_requires_human_approval():
    ev = EvidenceCandidate(
        evidence_id="ev-ed-1",
        source_id="src-ed-1",
        source_title="Dissolving Suffering",
        source_url="https://www.youtube.com/watch?v=xyz98765432",
        source_type="video",
        teacher_id="preethaji",
        speaker_verified=True,
        text="Suffering is born from division within oneself.",
        start_time=30.0,
        end_time=45.0,
        retrieval_source="qdrant",
        rights_status="licensed",
        concepts=["Suffering State"],
    )

    svc = EditorialIntelligenceService(
        search_fn=lambda topic, tscope, lim: [ev],
        seeker_demand_fn=lambda: [{"topic": "Sufkor", "query_count": 42, "abstain_rate": 0.9}],
        ingestion_status_fn=lambda: {"books_indexed": False},
    )

    dossier = svc.generate_dossier(topic="Suffering", objective="Video brief")
    assert dossier.existing_coverage_count == 1
    assert any(
        "books not yet in active first-person index" in a for a in dossier.underexplored_angles
    )

    opps = svc.discover_opportunities(limit=5)
    assert opps[0].topic == "Sufkor"
    assert "Ingestion incomplete" in opps[0].ingestion_completeness_note

    proj = svc.create_project(
        title="Why Division Causes Suffering", topic="Suffering", author_id="author-1"
    )
    proj = svc.attach_dossier(proj.project_id, dossier)

    # Misattributed script block (attributed to Krishnaji when evidence is Preethaji)
    bad_script = svc.build_verified_script(
        title="Draft 1",
        topic="Suffering",
        blocks=[
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text="Suffering is born from division within oneself.",
                teacher_attributed="krishnaji",
                evidence_ids=["ev-ed-1"],
            )
        ],
        evidence_pool=[ev],
    )
    assert bad_script.verification.passed is False
    svc.attach_script(proj.project_id, bad_script)

    with pytest.raises(EditorialApprovalError):
        svc.approve_project(proj.project_id, reviewer_id="editor-1")

    # Fix attribution and approve
    good_script = svc.build_verified_script(
        title="Draft 2",
        topic="Suffering",
        blocks=[
            ScriptBlock(
                block_id="b1",
                block_type="exact_quote",
                text="Suffering is born from division within oneself.",
                teacher_attributed="preethaji",
                evidence_ids=["ev-ed-1"],
            ),
            ScriptBlock(
                block_id="b2",
                block_type="editorial_narration",
                text="Notice how this connects directly to daily relationship conflicts.",
            ),
        ],
        evidence_pool=[ev],
    )
    svc.attach_script(proj.project_id, good_script)
    approved = svc.approve_project(
        proj.project_id, reviewer_id="editor-1", notes="Verified and approved"
    )
    assert approved.status == "approved"
    assert approved.approved_by == "editor-1"


def test_graded_ndcg_and_controlled_retrieval_optimizer():
    # Hand-verified graded DCG@3: grades [3, 1, 2], ideal [3, 2, 1]
    dcg = (2**3 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3) + (2**2 - 1) / math.log2(4)
    idcg = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3) + (2**1 - 1) / math.log2(4)
    assert graded_ndcg_at_k([3, 1, 2], [3, 2, 1], k=3) == round(dcg / idcg, 4)

    with pytest.raises(SafetyLockError):
        ControlledRetrievalOptimizer.validate_safety_locks({"require_licensed_domain_reads": False})

    golden = [
        {
            "query": "What is the beautiful state?",
            "question_class": "standard",
            "relevance_grades": {"e1": 3, "e2": 2},
        }
    ]

    def _eval(cfg: RetrievalCandidateConfig, item: dict) -> dict:
        if cfg.qdrant_top_k >= 30:
            return {
                "ranked_ids": ["e1", "e2"],
                "source_ids": ["s1", "s2"],
                "raw_candidate_count": 3,
                "latency_ms": 1200,
            }
        return {
            "ranked_ids": ["e2", "e1"],
            "source_ids": ["s2", "s1"],
            "raw_candidate_count": 2,
            "latency_ms": 900,
        }

    opt = ControlledRetrievalOptimizer(eval_fn=_eval, max_p95_latency_ms=5000.0)
    base = RetrievalCandidateConfig(name="baseline", qdrant_top_k=10)
    cand = RetrievalCandidateConfig(name="top30", qdrant_top_k=30)
    dec = opt.compare_and_decide(baseline_cfg=base, candidate_cfg=cand, golden_items=golden)
    assert dec.promoted is True
    assert dec.rollback_config == base
