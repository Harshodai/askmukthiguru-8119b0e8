# W2 + W3 + Quality Probe — 2026-10-11 (branch `fp-prod-hardening-2026-10-11`)

Read-only evals. No ingestion writes, no commits, no pipeline/store/config changes.
Driver was NOT relaunched.

## W2 salvage — decision: SKIP (band n=3 < 10)

- `~/mukthiguru_attribution_data/mass_ingest_2026-10/state.json`: 516 videos; **3** in
  ASR-agreement band [0.79, 0.80]: `4LIZkNHlNaM` (0.7996), `vcvE5YpOjL4` (0.7907),
  `zPsun8EkA2s` (0.7992) — all `status=stages_done`. 56 below 0.79, 1 unknown (`__last_apply__`).
- Latest index report `index_report/report_20261010T183028Z.json`: 59 quarantined, all
  `asr_agreement_low`; same 3 videos in band (0.800 / 0.791 / 0.799).
- 3 < 10 → per instructions W2 stops here. No `--max-disputed-rate` fit, no
  hallucination_spans / repeated_ngram wiring, no targeted re-index, no reconcile run.

## W3 harness re-measure (index settled, driver NOT mid-run)

Provenance: Qdrant `first_person_v7` = **3236 points, status green**.
Driver NOT running (`ps` empty); `driver_resume.log` last write 00:00:29 IST ended in
`RuntimeError: [apply] 1 produced point(s) missing after upsert` — a crash, reported
as-is, driver not relaunched per instructions.
Command (pin respected, no `--no-pin-check`; sha `1cd21138…` verified in output):
`python -m evaluation.first_person_harness run --collection first_person_v7
--questions evaluation/datasets/first_person_golden_paraphrase_25.json --rank-depth 10
--probe-legs --out …` → `audits/reports/first_person_harness_w3_2026-10-11.json`

| metric | measured (n=25) |
|---|---|
| top1 hit mean [ci_low, ci_high] | 0.0 [0.0, 0.0] |
| paraphrase same_video / same_clip (5 groups) | 0.0 / 0.0 |
| recall@5 / recall@10 / MRR / NDCG@10 | 0.0 / 0.0 / 0.0 / 0.0 |
| status | 25× weak_match; answerability `not_run` ×25 |
| legs fused_dense_top1_agree / sparse active | 0.36 / 1.0 |
| latency p50 / p95 | 2551.8 / 2568.1 ms |
| n_errors / JSON-recorded timeouts | 0 / 0 (gate timeout_s=4.0s, p95 well under) |

Why zero: serving calibration profile is **demoted** (`claims=none, no risk bound`) so
`is_direct` is always False → every answer is `weak_match` ("Related, not a direct
answer"); container has `uncalib_direct=False`. Stderr also shows repeated OpenRouter
`generate` failures (`Event loop is closed`, model deepseek/deepseek-chat) — the LLM
answerability leg cannot run in this container window; harness records `not_run`, not timeouts.
Serve-time integrity gate quarantines heavily (tail_dangling_word, head_fragment,
head_headless_predicate, severed preposition opener — incl. repeat offenders e.g.
`46074e57…` / `1nhXsnx5--Y`).

Gate thresholds: **NOT updated**. Recommended values for owner approval: with all-zero
measured top1/same_video/same_clip on n=25 under a demoted profile, no data-driven
threshold can be set — recommend re-measuring after a valid calibration profile exists,
then fitting per maitained procedure.
Conformal note (unresolved, flagged only): `evaluation/gold/calibrator.py:121-133`
requires **n ≥ 299 selected (0 errors)** for the 1%/95% Clopper-Pearson bound, while
gate docs elsewhere cite n ≥ 100 — discrepancy noted, not resolved unilaterally.

## Quality probe

`scripts/quality_probe.py` run **as-is** (forces answerability OFF via env, lines 12/14;
NOT rewritten — broader than a trivial flag given the hardcoded 5-query list).
→ `audits/reports/quality_probe_v3_2026-10-11.txt` (exit 0):
5/5 queries `weak_match`, `is_direct=False`, 1 citation each (Q1 8286ms cold-start, Q2–Q5 <100ms).

Golden-25 + 3 OOC controls run separately at container defaults (**answerability ON**,
no script edits; inline probe only) → `audits/reports/quality_probe_ooc_golden25_2026-10-11.{txt,json}`:
- Golden-25: 25× weak_match, 0 direct, 25 citations.
- OOC (capital of France / Cricket World Cup 2023 / chocolate cake): 2× weak_match
  (explicitly labelled "Related, not a direct answer"), 1× abstained, 0 direct.
- **OOC served (status=success or is_direct): 0** ✓ (must be 0)
- **Quote-fidelity violations: 0** ✓ (must be 0) — 27/27 citations: quote present in
  answer, sha256(transcript_hash) matches, Qdrant payload `verbatim_text` identical by
  point_id. (First pass flagged 27× `retrieve_error` from a probe-side bug —
  `FirstPersonStore` exposes `.collection`, not `.collection_name`; re-verified clean.)

## Report paths

- `audits/reports/first_person_harness_w3_2026-10-11.json`
- `audits/reports/quality_probe_v3_2026-10-11.txt`
- `audits/reports/quality_probe_ooc_golden25_2026-10-11.txt`
- `audits/reports/quality_probe_ooc_golden25_2026-10-11.json`
- This summary: `audits/reports/evals_w2w3_probe_2026-10-11.md`
