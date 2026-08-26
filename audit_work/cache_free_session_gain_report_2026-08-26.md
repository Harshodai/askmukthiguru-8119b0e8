# AskMukthiGuru Cache-Free Session Gain Report

**Date:** 26 August 2026  
**Scope:** Changes made during the current latency-reduction session  
**Measurement rule:** Only `cache_mode=disabled`, `cache_free_only=true`, `cache_hit=false`, completed samples are eligible for official performance claims.

## Executive answer

The strongest defensible matched gain from this session is on the **deep-comparison route**: backend mean decreased from **24,741.00 ms to 22,281.33 ms**, a reduction of **2,459.67 ms (9.94%)**. Wall mean decreased from **24,874.05 ms to 22,429.12 ms**, a reduction of **2,444.93 ms (9.83%)**. Both sides are cache-disabled n=3 exploratory means; p50/p95 are intentionally suppressed.

The matched evidence does **not** show a broad all-tier speedup yet. Fast factual is effectively unchanged, with backend mean down only **12.00 ms (0.25%)** while wall mean increased **69.09 ms (1.37%)**. Standard factual is slower by **213.67 ms backend (4.41%)** and **237.79 ms wall (4.75%)**. These n=3 differences are noise-sensitive and should not be treated as regressions or gains without a larger paired run.

The 420-case question-bank wave provides broad current-state coverage, not a before/after delta: it has a different workload and observed-tier mix than the earlier 36-case route matrix. It yielded 396 included cache-free rows from 420 unique cases, but no session-wide improvement percentage can be calculated from that workload alone.

## Matched cache-free route comparison

The baseline is `latency_cache_disabled_allroutes_r3_summary.json`; the post-change rows are the clean cache-disabled soft-deadline summaries. Delta is **post minus pre**; negative is faster.

| Route | n pre/post | Backend pre ms | Backend post ms | Backend delta ms | Backend delta % | Wall pre ms | Wall post ms | Wall delta ms | Wall delta % | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Fast factual | 3 / 3 | 4,834.67 | 4,822.67 | **−12.00** | **−0.25%** | 5,042.53 | 5,111.62 | **+69.09** | **+1.37%** | No proven change; exploratory noise |
| Standard factual | 3 / 3 | 4,849.33 | 5,063.00 | **+213.67** | **+4.41%** | 5,001.07 | 5,238.86 | **+237.79** | **+4.75%** | No proven gain; investigate with n≥20 |
| Deep comparison | 3 / 3 | 24,741.00 | 22,281.33 | **−2,459.67** | **−9.94%** | 24,874.05 | 22,429.12 | **−2,444.93** | **−9.83%** | Strongest observed matched gain; still n=3 |

The deep-comparison reduction is consistent with the optional retrieval-planner soft deadline: primary retrieval remains authoritative and the merge point no longer waits indefinitely for optional expansion. It is not a randomized causal experiment, so the report calls it a **matched observed gain**, not a universally proven causal percentage.

## Changes that improved attribution rather than latency

The shared LLM queue now records bounded wait attribution by operation and priority, but it intentionally does not change concurrency or scheduling. Therefore, it creates measurement capability and has **no claimed direct latency gain** yet. Provider timing now separates request, first response/TTFT, decode, retry, and completion signals; this is instrumentation, not a measured reduction. The optional OpenRouter latency-sort experiment was invalid because attempts timed out or disconnected, so it contributes **0 valid performance samples** and no gain claim.

The retrieval planner’s 350 ms soft wait is the only new cross-tier behavior with a clean matched heavy-route result. The question-bank benchmark shows that `tier3_complex` remains the dominant tail with a cache-free mean of **22,885.60 ms**, p50 **21,821.00 ms**, and p95 **40,836.45 ms** across 48 included rows. The observed `standard` tier remains at **18,754.57 ms mean** with p95 **33,567.00 ms** across 21 rows. These are post-change current-state figures, not deltas against the earlier 36-case matrix.

## Greeting-path note

A separate diagnostic captured the pure greeting structural optimization from approximately **3,687 ms backend** before the deterministic path to approximately **5 ms backend** after it, with wall time decreasing from approximately **3,995 ms to 391 ms**. However, those artifacts are labeled `warm_shared`, not `cache_mode=disabled`; because the current hard rule excludes warm/shared measurements from performance claims, this result is **not included in the official gain total**. A matched cache-disabled repeated greeting run is required before assigning it to this report’s headline improvement.

## What can honestly be claimed

| Claim | Status |
|---|---|
| Deep comparison is approximately 9.9% faster on matched cache-disabled n=3 means | **Yes, exploratory matched gain** |
| All tiers are faster because of this session | **No evidence** |
| Fast factual improved materially | **No; −0.25% backend and +1.37% wall are effectively unchanged at n=3** |
| Standard factual improved | **No; observed post-change mean is 4.41% slower** |
| Queue telemetry reduced latency | **Not measured; instrumentation only** |
| OpenRouter latency sorting improved latency | **No; experiment invalid with zero valid samples** |
| Greeting optimization produced a large gain | **Diagnostic only; excluded from official cache-free claims because artifacts are warm_shared** |
| 420-case question-bank workload improved versus baseline | **Not comparable; no paired before workload** |

## Recommended next measurement

Run a paired cache-disabled benchmark with **at least 20 included samples per route** for fast factual, fast meditation, standard factual, standard reflective, deep comparison, deep multihop, temporal, Hindi, Telugu, distress, and pure greeting. Keep single-client and controlled-concurrency waves separate. Join by exact fixture and route outcome; publish deltas only when both sides meet the same cache-free and completion gates. Track provider 429s separately, because the all-tier wave produced 21 HTTP 429 exclusions and those represent capacity/reliability limits rather than latency.

## Evidence files

- `latency_cache_disabled_allroutes_r3_summary.json` — pre-change cache-disabled route matrix.
- `latency_cache_disabled_fast_factual_post_soft_deadline_r1_summary.json` — post-change fast factual.
- `latency_cache_disabled_standard_factual_post_soft_deadline_r1_summary.json` — post-change standard factual.
- `latency_cache_disabled_deep_comparison_post_soft_deadline_r1_summary.json` — post-change deep comparison.
- `question_bank_latency_merged_v1.md` and `.json` — post-change 420-case current-state benchmark, not a before/after dataset.

No warm-cache values are used in the official matched-gain table. No commit, push, deploy, reset, rebase, corpus mutation, or global Redis flush was performed.
