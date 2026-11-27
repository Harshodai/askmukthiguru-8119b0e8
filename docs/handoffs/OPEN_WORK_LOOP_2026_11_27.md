# Open-work loop (2026-11-27): read this first after any compaction or new session

Goal (owner, at any cost): Railway healthy and cheap, many concurrent users served, nothing pending, everything documented.
Rule: a row closes only with evidence you ran. Every agent change gets an independent Opus review before it ships. Agents never push; the owner pushes, so give the exact command. Never raise a guard baseline on your own.

## The loop (repeat until every row is DONE)
1. Read the table below. 2. Check `gh pr list`, `railway deployment list --service askmukthiguru-8119b0e8`, `python3 scripts/ops/railway_live_audit.py` (run from a directory linked with `railway link`; `/tmp/rwlink` was used). 3. Resume or restart the next unfinished row (agents: `SendMessage` to the id; if the worktree is empty start a fresh agent with the brief in this table). 4. Review, test, commit, give the owner the push command. 5. Update this file and the docs/lessons. 6. If the API says rate limit (5-hour limit, resets 11am Asia/Calcutta), wait and resume; do not drop the row.

## State (2026-11-27 ~17:00 IST)
| # | Work | State | Where / next step |
|---|---|---|---|
| 1 | PR 121 (audit script, docs, 11 i18n keys, locale sync) | CI failed once on `test_supabase_types_lint` (out-of-band table `user_brain_keys_archive_20261119` re-added to `types.ts`); fixed by removing it again (documented in HANDOFF_2026_11_20_QUALITY_LOOP.md). Needs owner push, then CI green, then merge | worktree `scratchpad/wrail`, branch `chore/railway-live-audit-2026-11-27` |
| 2 | Tokenizer swap (`FastTokenizer`, setting `onnx_tokenizer_backend`) saves ~320-350 MB (860 MB tokenizer alone) | Opus review: BLOCK only for a false memory number in comments; fix requested; changes staged, uncommitted | worktree `.claude/worktrees/agent-ad58a3fdca9bf025c` (agent id `ad58a3fdca9bf025c`). Fix comments, rerun guards/tests, commit AFTER PR 121 merges (needs the i18n fix), PR, deploy |
| 3 | Opt-in shared model server (`SERVICE_TYPE=model-server`, `MODEL_SERVER_URL`) | Partly built, uncommitted (9 files) | worktree `.claude/worktrees/agent-ad4ac10a5823f334b` (agent `ad4ac10a5823f334b`): resume to finish equivalence tests, measurements, docs; then Opus review |
| 4 | First-query cold start (~23-29 s after every restart, unlogged block between HyDE and the context harness) | Not started (agent hit rate limit, no changes) | Start fresh: profile the real first-person retrieval path, add a startup retrieval-path canary; before/after timings |
| 5 | Why fork-before-load hangs; memory-sharing patterns (mmap'd initializers, offline-optimized model) | Not started (rate limit) | Start fresh agent; deliverable `docs/operations/model-memory-sharing-research-2026-11-27.md` |
| 6 | 100-concurrent-user capacity model and local load test (stub LLM, never prod) | Not started (rate limit) | Start fresh agent; deliverables `docs/operations/capacity-and-load-test-2026-11-27.md` and `scripts/ops/load_test_chat.py` |
| 7 | Scaling/efficiency/cost code audit with fixes | Not started (rate limit) | Start fresh agent; deliverable `docs/operations/scaling-and-efficiency-audit-2026-11-27.md` |
| 8 | Delete Railway `first_person_v10` (4,224 pts, Railway-only) | Owner said delete. Blocked: needs the Qdrant admin key. Celery still points at v10 (posture `v10_only`): align celery to the backend's `FIRST_PERSON_*` first (skipDeploys), then delete after a snapshot | owner runs a script, or retry after celery alignment |
| 9 | Rotate the HuggingFace token exposed in a reviewer session | Owner action (huggingface.co/settings/tokens, then `HF_TOKEN` on Railway backend and celery-worker, and local `backend/.env`) | an agent cannot rotate credentials |
| 10 | Repo private (owner) | Owner action; the nightly Supabase backup then works. CI minutes will cost money: trim CI first | docs/operations/railway-cost-and-deploy-review-2026-11-27.md |
| 11 | Remaining owner decisions | `FIRST_PERSON_REQUIRE_SPEAKER_VERIFIED` live false vs repo true; celery `CREATE_CONTAINER` failures (send deployment `a0d03c30-a3bc-4686-a8e8-a0fced23f188` to Railway support); human gates (distress review, gold labels, faculty invitations, sign-offs, helpline calls) | owner |

## Done today (evidence in the Railway review doc and lessons.md)
`WEB_CONCURRENCY` 2 to 1 (backend memory 4.8 GB to 2.7 GB); fallback flag false; backend redeployed from `main` and healthy; Railway Memgraph TU layer rebuilt (2,999 of 2,999); Railway Qdrant 13-point patch (fingerprint identical to local); empty 50 GB Memgraph service and volume deleted; OpenRouter caps $15/day and $150/month; soft limit $45; celery watch paths; local ingestion-only Memgraph nodes and `guru_tone_podcast` deleted after snapshots; PRs 114-120 merged earlier.
