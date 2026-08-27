# Chunk Size Evaluation Report (Wave 2)
**Run Date:** 2026-08-27 15:20:12
## Metrics Legend
- **SC (Size Compliance)**: Keeps chunks within optimal length bounds (200-1600 characters).
- **ICC (Intrachunk Cohesion)**: Mean similarity of each sentence to its chunk's centroid (topic focus).
- **DCC (Discourse Continuity Coherence)**: Measures bigram overlap between consecutive chunks (context flow).
- **BI (Block Integrity)**: Ratio of chunks ending at sentence boundaries.
- **RC (Redundancy-Coherence)**: Penalizes duplicate chunks (similarity < 0.95).
- **Combined**: Production-weighted score (0.20 SC + 0.30 ICC + 0.20 DCC + 0.15 BI + 0.15 RC).

## Evaluation Results
| Size (chars) | Strategy | Chunks | SC | ICC | DCC | BI | RC | Combined |
|---|---|---|---|---|---|---|---|---|
| 300 | Recursive | 13 | 0.846 | 0.689 | 0.014 | 1.000 | 1.000 | 0.679 |
| 300 | Semantic | 15 | 0.467 | 0.753 | 0.020 | 1.000 | 1.000 | 0.623 |
| 500 | Recursive | 8 | 0.875 | 0.541 | 0.037 | 1.000 | 1.000 | 0.645 |
| 500 | Semantic | 15 | 0.467 | 0.753 | 0.020 | 1.000 | 1.000 | 0.623 |
| 800 | Recursive | 5 | 1.000 | 0.449 | 0.059 | 1.000 | 1.000 | 0.647 |
| 800 | Semantic | 15 | 0.467 | 0.753 | 0.020 | 1.000 | 1.000 | 0.623 |
| 1200 | Recursive | 4 | 1.000 | 0.378 | 0.017 | 1.000 | 1.000 | 0.617 |
| 1200 | Semantic | 15 | 0.467 | 0.753 | 0.020 | 1.000 | 1.000 | 0.623 |
| 1500 | Recursive | 3 | 1.000 | 0.342 | 0.021 | 1.000 | 1.000 | 0.607 |
| 1500 | Semantic | 15 | 0.467 | 0.753 | 0.020 | 1.000 | 1.000 | 0.623 |
