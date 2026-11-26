"""Unified Controlled Evidence Harness across Qdrant, Memgraph, OKF, and Canonical Registry.

Implements the Part 5.3 deterministic orchestration flow:
  Question -> Semantic Interpreter -> Retrieval Planner -> Parallel Store Adapters
  -> Normalizer -> RRF Fusion & Deduplication -> Reranker -> Coverage Check &
  Bounded Graph Expansion -> Canonical Verification -> Epistemic Packaging
  -> Claim Validation -> Final Evidence Package or Bounded Abstention.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.evidence_contract import (
    ClaimEvidenceMapping,
    ClaimVerificationReport,
    EpistemicCategory,
    EvidenceCandidate,
)
from services.canonical_evidence_registry import CanonicalEvidenceRegistry
from services.evidence_adapters import (
    ClaimVerificationService,
    EvidenceFusionEngine,
    MemgraphEvidenceAdapter,
    OKFEvidenceAdapter,
    QdrantEvidenceAdapter,
    RRFConfig,
)
from services.semantic_understanding import (
    RetrievalPlan,
    SemanticUnderstandingEngine,
    plan_retrieval,
)

logger = logging.getLogger(__name__)


class EpistemicResponsePackage(BaseModel):
    """Structured output preserving strict separation between Evidence, Interpretation, Synthesis & Application."""

    model_config = ConfigDict(extra="forbid")

    query: str
    status: LiteralStatus = "answered"
    abstain_reason: str | None = None
    retrieval_strategy: str
    evidence_items: list[EvidenceCandidate] = Field(default_factory=list)
    interpretations: list[dict[str, Any]] = Field(default_factory=list)
    syntheses: list[dict[str, Any]] = Field(default_factory=list)
    applications: list[dict[str, Any]] = Field(default_factory=list)
    concept_relationships: list[dict[str, Any]] = Field(default_factory=list)
    claim_verification: ClaimVerificationReport | None = None
    degraded_stores: list[str] = Field(default_factory=list)
    rejected_stale_or_revoked: list[str] = Field(default_factory=list)
    replay_provenance: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    trace: list[str] = Field(default_factory=list)


# Using str literal type alias for clean Pydantic validation without extra imports
LiteralStatus = str


@dataclass(frozen=True)
class HarnessConfig:
    rrf_k0: int = 60
    qdrant_weight: float = 1.0
    memgraph_weight: float = 0.75
    okf_weight: float = 0.50
    vector_top_k: int = 20
    graph_limit: int = 10
    okf_limit: int = 5
    rerank_depth: int = 15
    min_coverage_candidates: int = 2
    require_licensed: bool = True
    require_speaker_verified: bool = False
    corpus_version: str = "fp-context-resegment-v2"
    ontology_version: str = "v1"
    model_version: str = "retrieval_only"
    prompt_version: str = "v1"


class UnifiedEvidenceHarness:
    """Deterministic multi-store retrieval, fusion, verification, and epistemic packaging harness."""

    def __init__(
        self,
        *,
        qdrant_adapter: QdrantEvidenceAdapter | None = None,
        memgraph_adapter: MemgraphEvidenceAdapter | None = None,
        okf_adapter: OKFEvidenceAdapter | None = None,
        registry: CanonicalEvidenceRegistry | None = None,
        semantic_engine: SemanticUnderstandingEngine | None = None,
        claim_verifier: ClaimVerificationService | None = None,
        rerank_fn: Callable[[str, list[EvidenceCandidate]], list[EvidenceCandidate]] | None = None,
        config: HarnessConfig | None = None,
    ) -> None:
        self._qdrant = qdrant_adapter
        self._memgraph = memgraph_adapter
        self._okf = okf_adapter
        self._registry = registry
        self._semantic = semantic_engine or SemanticUnderstandingEngine()
        self._verifier = claim_verifier or ClaimVerificationService()
        self._rerank_fn = rerank_fn
        self._config = config or HarnessConfig()
        self._fusion = EvidenceFusionEngine(
            RRFConfig(
                k0=self._config.rrf_k0,
                weights={
                    "qdrant": self._config.qdrant_weight,
                    "memgraph": self._config.memgraph_weight,
                    "okf": self._config.okf_weight,
                },
            )
        )

    def retrieve_and_verify(
        self,
        *,
        query: str,
        query_dense: list[float],
        query_sparse: dict[str, Any] | None = None,
        teacher_scope: str | None = None,
        source_types: list[str] | None = None,
        proposed_claims: list[ClaimEvidenceMapping] | None = None,
    ) -> EpistemicResponsePackage:
        t0 = time.perf_counter()
        trace: list[str] = []
        degraded: list[str] = []

        understanding = self._semantic.interpret(query)
        trace.append(f"interpret:{understanding.intent}")

        if understanding.intent == "crisis":
            return EpistemicResponsePackage(
                query=query,
                status="crisis_preempted",
                abstain_reason="acute_crisis",
                retrieval_strategy="crisis_bypass",
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                trace=trace,
            )

        plan: RetrievalPlan = plan_retrieval(understanding)
        eff_teacher = teacher_scope or understanding.teacher_scope or plan.teacher_scope
        use_memgraph = "memgraph" in plan.adapters and plan.graph_depth > 0
        use_okf = "okf" in plan.adapters
        effective_top_k = max(self._config.vector_top_k, plan.top_k) if plan.top_k > 0 else 0
        effective_rerank = (
            max(self._config.rerank_depth, plan.rerank_depth) if plan.rerank_depth > 0 else 0
        )
        trace.append(f"plan:{plan.strategy}")

        if effective_top_k <= 0:
            return EpistemicResponsePackage(
                query=query,
                status="abstained",
                abstain_reason="out_of_scope",
                retrieval_strategy=plan.strategy,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                trace=trace,
            )

        ranked_lists: dict[str, list[EvidenceCandidate]] = {}
        concept_edges: list[dict[str, Any]] = []
        concepts_seed = (
            understanding.target_concepts or [w for w in query.split() if len(w) > 3][:5] or [query]
        )

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_qd = pool.submit(
                self._safe_qdrant,
                query_dense=query_dense,
                query_sparse=query_sparse,
                teacher_id=None if eff_teacher == "both" else eff_teacher,
                source_types=source_types,
                top_k=effective_top_k,
            )
            f_mg = (
                pool.submit(
                    self._safe_memgraph_concepts,
                    concepts=concepts_seed,
                    teacher_id=None if eff_teacher == "both" else eff_teacher,
                )
                if use_memgraph and self._memgraph is not None
                else None
            )
            f_okf = (
                pool.submit(
                    self._safe_okf,
                    query_dense=query_dense,
                    teacher_id=None if eff_teacher == "both" else eff_teacher,
                )
                if use_okf and self._okf is not None
                else None
            )

            qd_res, qd_err = f_qd.result()
            if qd_err:
                degraded.append(f"qdrant:{qd_err}")
            ranked_lists["qdrant"] = qd_res

            if f_mg is not None:
                mg_res, mg_err = f_mg.result()
                if mg_err:
                    degraded.append(f"memgraph:{mg_err}")
                ranked_lists["memgraph"] = mg_res

            if f_okf is not None:
                okf_res, okf_err = f_okf.result()
                if okf_err:
                    degraded.append(f"okf:{okf_err}")
                ranked_lists["okf"] = okf_res

        trace.append("retrieve:" + ",".join(f"{k}={len(v)}" for k, v in ranked_lists.items()))

        # Fuse and deduplicate strictly on canonical evidence_id
        fused = self._fusion.fuse(ranked_lists, limit=max(effective_top_k, effective_rerank))
        trace.append(f"fuse:{len(fused)}")

        # Coverage check -> bounded adjacency graph expansion when thin and Memgraph enabled
        if (
            self._memgraph is not None
            and use_memgraph
            and fused
            and len(fused) < self._config.min_coverage_candidates
        ):
            try:
                seed_ids = [c.evidence_id for c in fused[:4]]
                adj = self._memgraph.expand_from_evidence_ids(
                    seed_ids, limit=self._config.graph_limit
                )
                if adj:
                    fused = self._fusion.fuse(
                        {"fused": fused, "memgraph": adj}, limit=effective_top_k
                    )
                    trace.append(f"expand_adj:{len(adj)}")
            except Exception as exc:
                degraded.append(f"memgraph_adj:{type(exc).__name__}")

        if self._memgraph is not None and use_memgraph:
            try:
                concept_edges = self._memgraph.get_concept_neighborhood(concepts_seed, limit=10)
            except Exception as exc:
                degraded.append(f"memgraph_nbr:{type(exc).__name__}")

        # Rerank bounded top slice
        if self._rerank_fn is not None and fused and effective_rerank > 0:
            head = fused[:effective_rerank]
            tail = fused[effective_rerank:]
            try:
                fused = self._rerank_fn(query, head) + tail
                trace.append(f"rerank:{len(head)}")
            except Exception as exc:
                degraded.append(f"rerank:{type(exc).__name__}")

        # Canonical Evidence Registry verification & stale/revocation exclusion
        verified_items: list[EvidenceCandidate] = []
        rejected: list[str] = []
        for cand in fused:
            if self._registry is not None:
                ok, reason = self._registry.is_candidate_active(cand)
                if not ok:
                    rejected.append(f"{cand.evidence_id}:{reason}")
                    continue
            if self._config.require_licensed and cand.rights_status != "licensed":
                rejected.append(f"{cand.evidence_id}:rights_{cand.rights_status}")
                continue
            verified_items.append(cand)

        trace.append(f"verify:kept={len(verified_items)},rejected={len(rejected)}")

        if not verified_items:
            return EpistemicResponsePackage(
                query=query,
                status="abstained",
                abstain_reason="no_verified_evidence" if not degraded else "stores_unavailable",
                retrieval_strategy=plan.strategy,
                degraded_stores=degraded,
                rejected_stale_or_revoked=rejected,
                replay_provenance=self._build_replay_metadata([], plan.strategy),
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                trace=trace,
            )

        # Optional claim validation against retrieved verified evidence pool
        claim_report: ClaimVerificationReport | None = None
        if proposed_claims:
            claim_report = self._verifier.verify_claims(proposed_claims, verified_items)
            trace.append(f"claim_check:{claim_report.passed}")
            if not claim_report.passed:
                return EpistemicResponsePackage(
                    query=query,
                    status="claim_rejected",
                    abstain_reason=claim_report.summary,
                    retrieval_strategy=plan.strategy,
                    evidence_items=verified_items,
                    claim_verification=claim_report,
                    concept_relationships=concept_edges,
                    degraded_stores=degraded,
                    rejected_stale_or_revoked=rejected,
                    replay_provenance=self._build_replay_metadata(verified_items, plan.strategy),
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                    trace=trace,
                )

        # Strictly separate cross-source synthesis metadata from verbatim teacher evidence
        syntheses: list[dict[str, Any]] = []
        distinct_sources = {ev.source_id for ev in verified_items}
        if len(distinct_sources) >= 2:
            syntheses.append(
                {
                    "epistemic_category": EpistemicCategory.SYNTHESIS.value,
                    "label": "CROSS_SOURCE_SYNTHESIS",
                    "supporting_evidence_ids": [ev.evidence_id for ev in verified_items[:5]],
                    "distinct_source_count": len(distinct_sources),
                }
            )

        return EpistemicResponsePackage(
            query=query,
            status="answered",
            retrieval_strategy=plan.strategy,
            evidence_items=verified_items,
            syntheses=syntheses,
            concept_relationships=concept_edges,
            claim_verification=claim_report,
            degraded_stores=degraded,
            rejected_stale_or_revoked=rejected,
            replay_provenance=self._build_replay_metadata(verified_items, plan.strategy),
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            trace=trace,
        )

    def _safe_qdrant(
        self,
        *,
        query_dense: list[float],
        query_sparse: dict[str, Any] | None,
        teacher_id: str | None,
        source_types: list[str] | None,
        top_k: int,
    ) -> tuple[list[EvidenceCandidate], str | None]:
        if self._qdrant is None:
            return [], None
        try:
            return (
                self._qdrant.search(
                    query_dense=query_dense,
                    query_sparse=query_sparse,
                    teacher_id=teacher_id,
                    source_types=source_types,
                    limit=top_k,
                    require_licensed=self._config.require_licensed,
                    require_speaker_verified=self._config.require_speaker_verified,
                ),
                None,
            )
        except Exception as exc:
            logger.warning("[UnifiedEvidenceHarness] Qdrant adapter error: %s", exc)
            return [], type(exc).__name__

    def _safe_memgraph_concepts(
        self,
        *,
        concepts: list[str],
        teacher_id: str | None,
    ) -> tuple[list[EvidenceCandidate], str | None]:
        if self._memgraph is None:
            return [], None
        try:
            return (
                self._memgraph.discover_by_concepts(
                    concepts, limit=self._config.graph_limit, teacher_id=teacher_id
                ),
                None,
            )
        except Exception as exc:
            logger.warning("[UnifiedEvidenceHarness] Memgraph adapter error: %s", exc)
            return [], type(exc).__name__

    def _safe_okf(
        self,
        *,
        query_dense: list[float],
        teacher_id: str | None,
    ) -> tuple[list[EvidenceCandidate], str | None]:
        if self._okf is None:
            return [], None
        try:
            return (
                self._okf.search(
                    query_dense=query_dense,
                    teacher_id=teacher_id,
                    limit=self._config.okf_limit,
                    include_unverified=False,
                ),
                None,
            )
        except Exception as exc:
            logger.warning("[UnifiedEvidenceHarness] OKF adapter error: %s", exc)
            return [], type(exc).__name__

    def _build_replay_metadata(
        self,
        items: list[EvidenceCandidate],
        strategy: str,
    ) -> dict[str, Any]:
        return {
            "evidence_ids": [ev.evidence_id for ev in items],
            "source_versions": {ev.evidence_id: ev.source_version for ev in items},
            "corpus_version": self._config.corpus_version,
            "ontology_version": self._config.ontology_version,
            "retrieval_config": {
                "strategy": strategy,
                "rrf_k0": self._config.rrf_k0,
                "vector_top_k": self._config.vector_top_k,
                "rerank_depth": self._config.rerank_depth,
            },
            "model_version": self._config.model_version,
            "prompt_version": self._config.prompt_version,
        }
