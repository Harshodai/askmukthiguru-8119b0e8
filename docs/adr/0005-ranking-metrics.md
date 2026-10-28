# ADR 0005: Ranking Metrics — MRR/MAP/NDCG & Per-Class Breakdown Release Gate

- **Status:** Accepted
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
   - Evaluations must report scores segmented across the 5 canonical query classes:
     - `fast` / `casual`
     - `standard` / `doctrine`
     - `comparative`
     - `distress` / `crisis`
     - `hindi` / multilingual
3. **Hard Release Gate:**
   - Any reindex or retrieval pipeline alteration must prove:
     - Overall MRR >= 0.75 and NDCG@10 >= 0.80.
     - Zero class regression greater than 5% compared to the baseline collection.
     - Distress and safety critical retrieval precision must not degrade under any condition.

## Consequences
- **Positive:** Quantitative, reproducible promotion criteria; prevents regressions in sensitive query classes; eliminates subjective "looks good" approvals.
- **Negative:** Requires running the evaluation matrix before any index alias swap or reranker tuning.
