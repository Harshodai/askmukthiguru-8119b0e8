# Claude Code Handoff — AskMukthiGuru first-person track (2026-10-11, main green)

Paste at session start. Code wins over docs; report VERIFIED / PARTIAL / UNVERIFIED with command + count.

## Verified state (main, Qdrant first_person_v7 3236 pts, reconcile 0 mismatches)

- Backend 9795 passed + 0 errors at fd 61440 (default 1024 starves → Errno 24; CI now bumps `ulimit -n`). Only reds were 2 manifest-drift detectors, reconciled (preflight E003 isolation test; helm path → `infrastructure/`).
- Frontend 804 passed, typecheck + build clean.
- Ingestion: single-writer driver exited 0; H4 promise clips drop with reason (27 from `mmpmX3-qfc4`); shared `store_point_id_for_clip()` on write + verify paths; per-batch dedup mirrored; W2 salvage correctly SKIPPED (band n=3 < 10).
- Retrieval: hybrid RRF, layered gates, off-topic keyword wall ON (35/35, 0/20), exact-cache only. Uncalibrated default serves zero direct answers (intended).
- Golden-25 top1 0.0 is a validity artifact (4 gold videos absent from v7) — restore-then-remeasure; never retune thresholds to it.
- Speaker lane: ECAPA `verify_clip_speaker` + `speaker_verified` plumbing, 15 tests. ~300 Times Now clips flip on next rebuild. Never map teacher_id→name (binding).
- Calibration: n≥299 proven by math (UCB 0.0295 at n=100 fails 1% target); gap is the full 299 pairs; reviewer packets in `evals/`.
- Docker healthy on latest main (project `mukthiguru_clean` — orphan volumes adopted, do not rename). Railway paused; do not deploy.

## Binding lessons (read first)

`lessons.md` top: L-FP-HYBRID-SCAFFOLD-1 (LLM frames, code quotes), L-FP-PROMISE-1, L-FP-BENCHMARK-VALIDITY-1. CLAUDE.md invariants §49-73. AGENTS.md corrected Oct-11 entry (no activation claims).

## Open (humans only)

1. Assign native-speaker + clinician reviewers (`evals/*_packet.md`).
2. Commission 299-pair B1 batch (~15–20 annotator-hrs).
3. Restore 4 gold videos → rerun harness → set real thresholds.
4. Speaker rebuild + apply → reconcile 0 → re-measure.
5. V10 readiness verdict only after the above.

## How to work

- Small diffs, tests with every change, `git diff --check`, no direct Qdrant writes (dry-run → report → approval → apply).
- Never commit `.work/`, secrets, models, or audio. Attribution trailers on commits.
- `ulimit -n 61440` before full pytest; `vitest --maxWorkers=2`; `COMPOSE_PROJECT_NAME=mukthiguru_clean` for compose ops.
