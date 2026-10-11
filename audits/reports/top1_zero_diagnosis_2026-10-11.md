# Golden-25 top1 0.0 diagnosis (2026-10-11)

**Question:** why did golden-25 top1 fall from 0.12–0.16 (177-pt index, Oct 3) to 0.0 (3236-pt index, w3 run `first_person_harness_w3_2026-10-11.json`)?

## Verdict: benchmark-validity failure (gold answers not in the index), not a retrieval regression

**Validity — CONFIRMED, primary cause.** Live read-only Qdrant counts against `first_person_v7` (3236 pts, 391 distinct videos, `video_id` payload key verified via sample point + positive control `M7ItOHTrvz8` → 9 pts):

| gold video | points in v7 now |
|---|---|
| `UlOt31lBhLY` | 0 |
| `TqxxCYnAxo8` | 0 |
| `hUmlujE6SN0` | 0 |
| `HCs6I_BNtxo` | 0 |

All 4 gold videos are absent from the current index (mass-ingest rebuild dropped them — matches `L-FP-BENCHMARK-VALIDITY-1`). A span hit requires same-video overlap, so the metric ceiling is structurally 0.0: w3 video-level top1 match is **0/25** on both the fused and dense legs, rank recall@5/@10, MRR and NDCG@10 all 0.0. Nothing to retrieve → nothing to hit.

**Metric artifact — REJECTED as cause.** The span rule (`passage_hits_ranges`, overlap ≥ 0.5) is strictly harsher than video equality, but it is moot here: video-equality scoring of w3 also gives 0/25. Historical cost of the span rule was small — healthy Oct-3 run had 5 video-level matches but only 4 span hits (0.20 → 0.16, ~0.04). It cannot explain a 0.16 → 0.0 drop.

**Scale effect — UNMEASURABLE on gold until validity is restored; secondary at most.** Index grew 177 → 3236 pts (18.3×), 391 videos, so theme-adjacent competition is real. But theme-confusion predates scale: paraphrase `same_video_rate` was already 0.0 in the 144-pt and 177-pt runs, and Oct-3 rows already show theme neighbors stealing paraphrases (`TqxxCYnAxo8` winning group-1 queries against gold `UlOt31lBhLY`). Scale cannot score against absent gold either way.

**Retrieval regression — NO EVIDENCE.** w3 retrieval looks healthy: 0 errors, 25/25 served (all `weak_match` = uncalibrated serving, expected with the demoted profile), fused top scores 0.5–0.83, sparse leg active 1.0, top1 clips are theme-plausible neighbors. Also note the 0.0 is *cleaner* than Oct-3's misses: w3 answerability verdicts are `not_run` × 25 with **0 abstentions**, vs 8 abstains in run 1 (0.12) and 3 in run 2 (0.16) — prior numbers were partly gate-timeout-driven, w3 0.0 is 25 genuine served misses against absent gold. (Open question, not a verdict input: legs agree only 0.36 — sparse flips the dense winner 64% of the time — but no Oct-3 leg baseline exists to compare against.)

## Highest-leverage next measurement

Restore the 4 gold videos into v7 (re-ingest, or a shadow collection with identical pipeline settings), then rerun the identical harness command (`--rank-depth 10 --probe-legs` on the SHA-pinned set). Expect top1 ≈ 0.12–0.20. That single run separates validity from everything else; the per-query top-10 diff then-vs-now on the restored index additionally quantifies the pure 18× scale effect. Until then, the `GOLDEN25_TOP1_MEAN_MIN=0.12` gate (`.github/workflows/golden25-gate.yml`) will fail on w3-style runs — correctly, since the benchmark is currently invalid, not the retriever.

*Method: read-only Qdrant counts/scroll + checked-in reports only. No threshold/config changes, no writes, no commits. Gold dataset SHA pin untouched.*
