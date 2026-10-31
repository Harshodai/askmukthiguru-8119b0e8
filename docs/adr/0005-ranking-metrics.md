# ADR 0005: Ranking Metrics — MRR/MAP/NDCG & Per-Class Breakdown Release Gate

- **Status:** Proposed (the numeric thresholds below are NOT adopted; see "Hard Release Gate")
- **Date:** 2026-10-28
- **Deciders:** Data Engineering, Search Quality, ML Evaluation
- **Consulted:** Master Plan DE-5.3, DE-5.4, Phase 5 Eval

---

## Context
Previously, retrieval changes (e.g. tuning hybrid weights, modifying top_k, changing rerank depth, or updating embeddings) were evaluated either informally or through aggregate averages that masked acute regressions in critical query types. For example, an overall average MRR could improve slightly while retrieval for crisis or philosophical comparison queries collapsed.

## Decision
1. **Standardized IR Ranking Metrics:**
   - Retrieval quality is evaluated using three standard metrics:
     - **MRR (Mean Reciprocal Rank):** Speed and precision of the first relevant chunk.
     - **MAP (Mean Average Precision):** Precision across all relevant retrieved chunks.
     - **NDCG@10 (Normalized Discounted Cumulative Gain):** Graded relevance ranking quality.
2. **Mandatory Per-Class Breakdown:**
   - Evaluations must report scores segmented across the query classes implemented in `backend/evaluation/run_golden_eval.py::classify_question`:
     - `faq`
     - `comparative`
     - `multi_hop`
     - `distress_adjacent`
     - `indic_language`
     - `standard`
3. **Release Gate (thresholds pending owner decision):**
   - Adopting numeric release thresholds is an owner decision (SPEC-quality-observability: *ask first*) and requires an owner-reviewed held-out baseline. Until then these are **proposals, not gates**: overall MRR >= 0.75, NDCG@10 >= 0.80, no class regression greater than 5% versus the baseline collection. Values belong in config with provenance once adopted.
   - Not negotiable regardless of numbers: distress and safety-critical retrieval precision must not degrade.

## Consequences
- **Positive:** Quantitative, reproducible promotion criteria; prevents regressions in sensitive query classes; eliminates subjective "looks good" approvals.
- **Negative:** Requires running the evaluation matrix before any index alias swap or reranker tuning.
