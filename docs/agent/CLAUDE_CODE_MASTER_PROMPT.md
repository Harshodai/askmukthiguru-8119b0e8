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

Current state (local, 2026-09-25/26):
- top-1 0.43, 0 direct answers, p95 210 ms, host leak 6.9%
- 14 human labels; calibration needs about 299
- first_person_v3 (clip boundaries fixed) awaits approval
- Railway is scaled to 0, so production has not been measured

Open work, in order:
1. Host leak < 1%: owner approves first_person_v3 and the speaker audit, then re-measure.
2. Frontend: clip first, chat answer streamed below it.
3. Rights (TEDx and Marie Forleo clips) and phone verification of the helplines (G1/G2).
4. Deploy: Railway PYTHON_MEMORY_LIMIT_MB=0, redeploy, run
   gate1_load_test.py --mode first-person, then the 50-question spot check.
5. In parallel: the owner labels about 300 questions in the review UI (port 8088),
   which unlocks calibration, the reranker fine-tune and the offline question field.
```
