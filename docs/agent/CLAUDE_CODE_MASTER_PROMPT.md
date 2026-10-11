# AskMukthiGuru — session prompt for first-person work (2026-09-26)

Paste this at the start of a session.

```markdown
Goal: ship the first-person verbatim route. Follow ADR FP-1 to FP-3, all ACCEPTED, in
docs/architecture/first-person-path-to-prod.md.

- v1 serves the closest teacher clip, labelled "Closest teaching", with no direct-answer claim.
- It ships on its own gate (FP-2):
  - integrity 100%
  - crisis probe green
  - host-voice leak < 1% of top-1
  - p95 < 1 s on the deployed stack
  - 50-question human spot check
- The chat path is frozen except for bug fixes (FP-3).

Ground rules:
- The invariants are in CLAUDE.md, "First-Person Verbatim Route: invariants (verified against code)".
  Code wins over any doc. If a doc and the code disagree, say so; don't "fix" the code to match the doc.
- Read NEXT_PROD_READY.md and the files you touch. Don't bulk-read the docs/agent research files:
  several describe designs that were never built (VAD, synthetic questions, alias swaps, +1.8 s tails).
- Report every claim as VERIFIED (you ran it), UNVERIFIED, or NOT RUN.
- Human-only gold labels. Never open docs/attribution/label_*.csv or *_KEY.json.
- Every Qdrant/OKF/graph write goes dry-run → report → snapshot → owner approval → apply.
- Before any benchmark launch: smoke the previously errored ids on the current backend.
  Pause on a burst of instant system_error rows.
- No commit or push unless asked.

Current state (verified 2026-10-11, supersedes Sep numbers below):
- Qdrant first_person_v7: 3236 pts, 100% rights_cleared, reconcile 0 mismatches; driver exited clean
- Retrieval: hybrid RRF + layered gates; golden-25 top1 0.0 is a validity artifact (gold videos absent), NOT a regression
- Serving: hybrid scaffold (LLM frames, code quotes), off-topic gate ON, uncalibrated default serves zero direct answers
- Calibration: needs 299 B1 pairs (n=100 insufficient); reviewer packets staged under evals/
- Docker healthy on latest main; Railway paused; suite 9780 green except 2 pre-existing main failures

Open work, in order:
1. Host leak < 1%: owner approves first_person_v3 and the speaker audit, then re-measure.
2. Frontend: clip first, chat answer streamed below it.
3. Rights (TEDx and Marie Forleo clips) and phone verification of the helplines (G1/G2).
4. Deploy: Railway PYTHON_MEMORY_LIMIT_MB=0, redeploy, run
   gate1_load_test.py --mode first-person, then the 50-question spot check.
5. In parallel: the owner labels about 300 questions in the review UI (port 8088),
   which unlocks calibration, the reranker fine-tune and the offline question field.
```
