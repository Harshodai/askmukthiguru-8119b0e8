"""Run measurable live benchmark & ControlledRetrievalOptimizer sweep across Qdrant + Memgraph + OKF.

Executes strictly read-only against local Qdrant (``first_person_v13_shadow``),
Memgraph (``bolt://127.0.0.1:7687``), and OKF (``memory/okf/compiled.json``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from evaluation.retrieval_optimizer import ControlledRetrievalOptimizer, RetrievalCandidateConfig
from services.embedding_service import EmbeddingService
from services.evidence_adapters import (
    MemgraphEvidenceAdapter,
    OKFEvidenceAdapter,
    QdrantEvidenceAdapter,
)
from services.semantic_understanding import SemanticUnderstandingEngine
from services.unified_evidence_harness import HarnessConfig, UnifiedEvidenceHarness


def _to_qdrant_sparse(sw: Any) -> dict[str, Any] | None:
    if not isinstance(sw, dict) or not sw:
        return None
    indices = []
    values = []
    for k, v in sw.items():
        try:
            indices.append(int(k))
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return {"indices": indices, "values": values} if indices else None


def run_live_benchmark(dataset_path: Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    ds_path = dataset_path or (root / "evals" / "evidence_platform_golden.jsonl")
    items = [
        json.loads(line)
        for line in ds_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    from app.config import settings  # config only via settings; imported lazily (validates env)

    mg_user = settings.neo4j_user or ""
    mg_pass = settings.neo4j_password or ""
    driver = GraphDatabase.driver(
        "bolt://127.0.0.1:7687",
        auth=(mg_user, mg_pass) if (mg_user or mg_pass) else None,
    )

    qc = QdrantClient(url="http://127.0.0.1:6333", timeout=10.0)
    qd_adapter = QdrantEvidenceAdapter(qc, "first_person_v13_shadow")
    mg_adapter = MemgraphEvidenceAdapter(driver)
    okf_adapter = OKFEvidenceAdapter()

    emb = EmbeddingService()
    queries = [it["query"] for it in items]
    dense_vecs = emb.encode(queries)
    vec_map = {q: (list(dv), None) for q, dv in zip(queries, dense_vecs)}

    sem_engine = SemanticUnderstandingEngine(embed_fn=emb.encode)

    retrieval_items = [it for it in items if not it.get("expect_abstain")]
    safety_abstain_items = [it for it in items if it.get("expect_abstain")]

    per_query_outcomes: list[dict[str, Any]] = []

    def _eval_fn(cfg: RetrievalCandidateConfig, item: dict[str, Any]) -> dict[str, Any]:
        harness = UnifiedEvidenceHarness(
            qdrant_adapter=qd_adapter,
            memgraph_adapter=mg_adapter,
            okf_adapter=okf_adapter,
            semantic_engine=sem_engine,
            config=HarnessConfig(
                rrf_k0=cfg.rrf_k0,
                qdrant_weight=cfg.w_qdrant,
                memgraph_weight=cfg.w_memgraph,
                okf_weight=cfg.w_okf,
                vector_top_k=cfg.qdrant_top_k,
                rerank_depth=cfg.rerank_depth,
                require_licensed=True,
                require_speaker_verified=True,
            ),
        )
        dv, sv = vec_map[item["query"]]
        pkg = harness.retrieve_and_verify(query=item["query"], query_dense=dv, query_sparse=sv)
        if cfg.name == "baseline_k60_top15":
            per_query_outcomes.append(
                {
                    "id": item["id"],
                    "question_class": item.get("question_class") or item.get("intent"),
                    "strategy": pkg.retrieval_strategy,
                    "status": pkg.status,
                    "hits": len(pkg.evidence_items),
                    "top3_ids": [ev.evidence_id for ev in pkg.evidence_items[:3]],
                    "expected_hit_rank": next(
                        (
                            idx
                            for idx, ev in enumerate(pkg.evidence_items, start=1)
                            if ev.evidence_id in (item.get("relevance_grades") or {})
                        ),
                        None,
                    ),
                    "latency_ms": pkg.latency_ms,
                }
            )
        return {
            "ranked_ids": [ev.evidence_id for ev in pkg.evidence_items],
            "source_ids": [ev.source_id for ev in pkg.evidence_items],
            "raw_candidate_count": len(pkg.evidence_items),
            "latency_ms": pkg.latency_ms,
        }

    baseline_cfg = RetrievalCandidateConfig(
        name="baseline_k60_top15", qdrant_top_k=15, rrf_k0=60, rerank_depth=15
    )
    candidate_cfg = RetrievalCandidateConfig(
        name="expanded_k20_top30", qdrant_top_k=30, rrf_k0=20, rerank_depth=20
    )

    try:
        optimizer = ControlledRetrievalOptimizer(eval_fn=_eval_fn, max_p95_latency_ms=5000.0)
        decision = optimizer.compare_and_decide(
            baseline_cfg=baseline_cfg,
            candidate_cfg=candidate_cfg,
            golden_items=retrieval_items,
        )

        # Also verify deterministic abstention on out-of-scope and crisis benchmark rows
        guard_harness = UnifiedEvidenceHarness(
            qdrant_adapter=qd_adapter,
            memgraph_adapter=mg_adapter,
            okf_adapter=okf_adapter,
            semantic_engine=sem_engine,
            config=HarnessConfig(require_licensed=True, require_speaker_verified=True),
        )
        guard_outcomes = []
        for g in safety_abstain_items:
            dv, sv = vec_map[g["query"]]
            pkg = guard_harness.retrieve_and_verify(
                query=g["query"], query_dense=dv, query_sparse=sv
            )
            guard_outcomes.append(
                {
                    "id": g["id"],
                    "question_class": g.get("question_class") or g.get("intent"),
                    "status": pkg.status,
                    "abstain_reason": pkg.abstain_reason,
                }
            )

        return {
            "baseline": vars(decision.baseline),
            "candidate": vars(decision.candidate),
            "promoted": decision.promoted,
            "decision_reason": decision.reason,
            "per_query_baseline": per_query_outcomes,
            "guard_outcomes": guard_outcomes,
        }
    finally:
        driver.close()


if __name__ == "__main__":
    report = run_live_benchmark()
    print(json.dumps(report, indent=2))
