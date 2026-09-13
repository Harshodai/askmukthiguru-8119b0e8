# Task 9 (D1/D2) — Golden relabel + human questions + tuning toward 0.80

Date: 2026-09-13. Golden: `backend/evaluation/datasets/golden_retrieval_v1.json` v1 → **v2 (frozen 2026-09-13)**.
Harness: `backend/benchmarks/recall_harness.py` (now skips `excluded`, reports `ndcg_at_10`,
per-item `first_relevant_rank`; detail and summary use the same normalized comparison).
Scorer: `backend/benchmarks/retrieval_metrics.py` (`normalize_source_key`, `SOURCE_KEY_ALIASES`).
Freeze guard: `backend/tests/test_golden_retrieval_v2.py` (12 tests incl. scorer regressions pass).

## 1. Baseline (recorded, not re-guessed)

- 60-question synthetic track (exact chunk-id membership,
  `scripts/eval/retrieval_golden_baseline.py`, prefetch 3.0 / top-k 24 from `3ffbdf8c`):
  **Recall@1 0.517 / nDCG@10 0.693** (`backend/tests/test_retrieval_tuning_baseline.py`,
  `backend/app/config.py:325`). Unchanged by this task; that track was already at its measured optimum.
- 68-item source-level track (exact `source_url` membership, `recall_harness.py`),
  measured live 2026-09-13 on `spiritual_wisdom_contextual` (12,904 pts, green):
  **R@1 0.1765 / R@5 0.4559 / R@10 0.4853 / nDCG@10 0.285 / MRR 0.2966** (`/tmp/recall_baseline_v1.json`).
- L-DOCKER-19 root cause verified live before any edit: **70 points** under
  `https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319`,
  **0 points** under `The_Four_Sacred_Secrets.pdf`. Baseline top-10s show the canonical
  URL at rank 3 (-000), rank 2 (-021), rank 5 (-026) — retrieval correct, labels wrong
  (exact-match scores 0.0). -042/-060 top-10s contain zero book chunks (Deeksha videos
  instead) — term-match false positives, not retrieval failures.

## 2. Label changes (before → after, one reviewed change)

| id | before | after | class |
|----|--------|-------|-------|
| doctrine_four_secrets-000 | sources `[The_Four_Sacred_Secrets.pdf]`, chunks 384 | sources `[amazon…/dp/1846046319]`, chunks **70** (previous values preserved per item) | key mismatch + unresolvable count (doc has 70 chunks live) |
| doctrine_founders-021 | `[The_Four_Sacred_Secrets.pdf]` | `[amazon…/dp/1846046319]` | key mismatch (retrieved rank 2) |
| doctrine_founders-026 | `[The_Four_Sacred_Secrets.pdf]` | `[amazon…/dp/1846046319]` | key mismatch (retrieved rank 5) |
| doctrine_manifest-042 | scored, gold = book chunks | **`excluded: true`** (reason kept on item) | content-stale: `[deeksha, august]` matched intro narrative that does not answer |
| doctrine_deeksha-060 | scored, gold = book chunks | **`excluded: true`** (reason kept on item) | content-stale: `[deeksha, oneness blessing, transfer, energy]` matched intro narrative |

Plus **20 human-authored seeker paraphrases** (`-h01…-h20`, e.g. "i forgot the second step
of soul sync — can you remind me?"), qrels inherited verbatim from non-stale multi-source
parents with `derived_from` provenance (BEIR query-variant practice: same need, new surface
form). Counts: 88 items total, 86 scored, 2 excluded.

## 3. Tuning attempt (canonical-URL key normalization) — honest result

`normalize_source_key` bridges bare-filename gold keys to the canonical URL at scoring time
(alias map + host-lowercase/fragment-strip; query strings kept — the video id lives there).
Prefetch 3.0 / top-k 24 left untouched (already the measured optimum, pinned by test).

After (v2, n=86 scored, same collection, same retrieval path): **R@1 0.2326 / R@5 0.6047 /
R@10 0.6628 / R@25 0.7674 / R@50 0.7907 / nDCG@10 0.4534 / MRR 0.3934**
(`/tmp/recall_after_v2b.json`; detail and summary agree exactly).

Win attribution (same retrieval, so this is label-hygiene recovery, not a model win):
relabeled trio now hit at ranks 2/3/5; normalization additionally credits book retrievals for
11 further pdf-keyed labels (e.g. -001 rank 1, -012 rank 2); 2 content-stale misses leave the
denominator; 20 derived paraphrases hit 12/20 @10 (0.60 — paraphrase robustness tracks the
parents, no inflation beyond them).

## 4. Verdict: 0.80 NOT reached — no inflation

R@10 0.6628 (n=86). Per-class @10: ekam 12/12, four_secrets 16/23, founders 7/16,
soul_sync 10/17, manifest 4/8, deeksha 3/10. The residual is genuine retrieval/corpus gap
(L-DOCKER-19: -086 near-miss rank 14 is RRF-tunable; -087 soul-sync video absent top-100 is a
hard corpus gap), not label artifact — further gains must come from corpus/RRF work with live
measurement, never from more label edits. 8 remaining bare-PDF-only labels (-006, -008, -016,
-019, -032, -033, -035, -055) were deliberately left untouched (no per-query evidence yet) and
are flagged as follow-up, not silently fixed.
