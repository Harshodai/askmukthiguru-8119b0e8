# Benchmark and Evaluation Quality Review

## Executive finding

The repository has a strong evaluation direction: benchmark honesty tests, gold/calibration utilities, safety scenarios, citation contracts, cross-tenant probes, latency evidence, and explicit handoff warnings against circular labels. The benchmark is not yet sufficient for a production claim because the strongest reported comparisons use a bake-off set that is not fully held out, vector reproducibility is unresolved, and direct-answer calibration is not active in the live service.

## Evidence

- `backend/evaluation/gold/run_calibration.py`, `calibrator.py`, `readiness_check.py`, and gold sheets implement calibration and human-label readiness checks.
- `backend/scripts/ops/first_person_live_eval.py` checks status, citation hash, timestamp, and teacher-filter behavior.
- `backend/tests/test_bench_honesty.py` protects against invalid/resumed/error-contaminated runs.
- `backend/tests/test_cross_tenant_leak_probe.py` checks tenant leakage behavior.
- `backend/tests/test_citation_contract.py`, `test_citation_marker_remap.py`, and frontend `src/test/citation-contract.test.tsx` verify citation/rendering contracts.
- `docs/agent/STATE_RECONCILIATION_2026-09-27.md` reports v2/v4/v5 comparisons, warns the bake-off is not held out, reports top-1 around 0.4–0.45, and identifies unresolved vector reproducibility.
- `docs/agent/EXPERIMENT_LEDGER_2026-09-27.md` records that gold labels must be human-only and that AI-authored bake-off questions are not a non-circular gold set.

## What is valid today

- Unit and contract tests are useful regression gates.
- Safety scenarios and crisis-specific tests are appropriate for adversarial coverage.
- Exact hash/timestamp/citation assertions are objective and should remain hard gates.
- Per-run calibration validation rejects malformed or mismatched profiles.
- The benchmark-honesty work correctly distinguishes failed/invalid runs from quality scores.

## What is not yet proven

### Leakage and test-set validity

The 116-question bake-off is explicitly not held out. Some questions are AI-authored from the corpus. It is appropriate for development comparison, not a final accuracy claim. Split by video/source/time and author questions independently of target passages.

### Reproducibility

The reconciliation notes report that v4 and v5 point sets match after a duration gate but vectors differ across builds and fresh embeddings. That means small A/B differences can be build noise. Pin model files, tokenizer, preprocessing, ONNX Runtime, CPU architecture, container digest, and build manifest.

### Calibration

The live container has no `first_person_calibration_path`, so direct-answer precision/coverage is not active. A passing calibration utility does not prove a profile has been fitted on adequate human gold data or matches the live build.

### Metric completeness

Top-1 strict retrieval does not measure top-3 recall, MRR, citation correctness, abstention correctness, speaker attribution, rights, multilingual safety, latency distributions, or tenant leakage together. `weak_match` semantics also need to be scored separately from direct-answer promotion.

### Per-guru isolation

A cross-tenant test exists, but the benchmark plan should include one independently labeled matrix for every guru pair, every cache mode, every index/build, and concurrent load. A single teacher filter test is not enough for arbitrary new gurus.

## Recommended evaluation protocol

### Dataset partitions

1. Human-authored, video-disjoint retrieval gold set.
2. Human-reviewed serving gold set with direct/related/no-answer labels.
3. Adversarial set for prompt injection, host leakage, ASR artifacts, dangling conjunctions, rights revocation, and multilingual/romanized crisis.
4. Per-guru isolation matrix with intentional cross-guru negatives.
5. Fixed production sentinel set for every deploy and daily drift monitoring.

### Scorecard

- Recall@1/3/5, MRR, nDCG by guru/language/topic.
- Direct-answer precision and one-sided confidence bound.
- Coverage: direct, weak, abstained, crisis-redirect.
- Exact substring/hash/timestamp/citation correctness: 100% target.
- Speaker verification precision and unknown/host leakage rate.
- Rights-cleared serving and revocation propagation SLA.
- Crisis recall and benign distress false-positive rate, with clinical/native-speaker review.
- p50/p95/p99 latency, timeout, retry, error, and queue-age distributions.
- Cross-guru leakage rate under deterministic and concurrent load.
- Cost/provider usage, cache-hit ratio, and model-version drift.

### Reproducibility manifest

Every score must include git commit/dirty state, corpus/source hashes, build ID, Qdrant collection/alias, point count, model/tokenizer/ONNX hashes, Python/container digest, query/gold/scorer hashes, random seeds, per-question outcomes, confidence intervals, and failure reasons.

### Promotion rules

- Candidate must beat the active baseline on predeclared metrics.
- No P0 safety, rights, citation, speaker, or isolation regression is acceptable.
- Calibration profile must match the candidate build exactly.
- Results must be reproduced twice from the same manifest.
- Candidate must pass a canary and have an atomic rollback path.

## Concrete remediation order

1. Freeze the artifact/runtime manifest and remove bake-off claims from release dashboards.
2. Complete the human-authored, human-labeled, video-disjoint gold set.
3. Re-run two clean baselines and one v5 candidate with identical artifacts.
4. Fit calibration and publish precision/coverage curves, not only a threshold.
5. Add per-guru and per-language slices, cross-guru negative tests, and concurrency leakage tests.
6. Add citation/speaker/rights/revocation/abstention metrics to the release scorecard.
7. Add deployment canary and rollback evidence to every benchmark result.

## Final assessment

The benchmark code is ahead of the production control plane and is directionally trustworthy. It can support higher scores only after the dataset is made independent, model/build reproducibility is fixed, and quality is decomposed into retrieval, serving, safety, integrity, and isolation metrics. Optimizing the single bake-off top-1 score now would risk overfitting and would not establish production readiness.

## Production gate addendum

The benchmark must not certify only passage overlap. The internal review found that `run_calibration.py` treats a >=50% overlap with a human-positive range as correct, which can still admit host speech or bad boundaries. A production gold label must require the correct teacher, self-contained boundary, exact/verifiable transcript, rights clearance, and timestamp validity.

The 299 zero-error figure is a count of selected confident answers, not 299 total questions. At the current estimated 20–40% coverage, approximately 750–1,500 real-style questions may be needed. The bake-off’s passage-derived questions are development data, not an independent calibration set.
