# Ruthless Plan to 10/10 — ECC Full-Coverage Audit Remediation

> **Source:** 16 grouped subagents across the full ECC catalog (292/292 skills triaged,
> 68/68 agents mapped, workflows + rules inventoried at `/tmp/ecc-audit`) plus all
> repo book skills (agentic-design-patterns, building-apps-ai-agents, ai-agents-in-action,
> ai-engineering-chip-huyen, build-llm-*, hands-on-llms, llms-in-production,
> prompt-engineering-llms, rag-made-simple, database-internals, designing-data-intensive-apps-2e,
> designing-distributed-systems, kleppmann-ddia-big-ideas, system-design-llm-era).
> Generated 2026-09-16. N/A domains (homelab, network-device, non-Python stacks, crypto,
> media-creation, unrelated business flows) are excluded by triage, not by oversight.
>
> **Scoring rubric (no mercy):** 5 = proven in production with measurements.
> 4 = CI blocks the merge. 3 = code exists but advisory. 2 = documented intent with
> open items. 1 = absent, or dead code wearing a live uniform.

## Current scores (ruthless)

| Area | Score | One-line verdict |
|---|---|---|
| Agent 12-layer stack | 2 | Verification Invariant is structural theater (0.0 finals ship) |
| Orchestration / multi-agent | 1 | `asyncio.gather` is a library call, not orchestration |
| Eval & testing | 2 | Ratchets real; everything else needs prod or can't fail |
| Memory / learning | 2 | OKF review queue has zero writers; lore file ungoverned |
| Backend architecture | 3 | Composition root is a suggestion; no versioning |
| Security | 3 | Wildcard allow-list + fail-open limiter + resurrected cookies.txt |
| Frontend / mobile / a11y | 2 | Great parser, god-component + no resume + unverified i18n around it |
| Data / ingestion | 2 | Lock never released; disjoint keyspaces; raw-path writes |
| Docs stewardship | 1 | False-authority SPEC, live secrets in harness, unindexed lore |
| DevOps / cost | 2 | Paused prod + advisory gates + wrong-collection backup |
| Python / FastAPI depth | 2 | Sixty stringly raises, bare swallows, unused `result.py` |

## Findings registry (all P0/HIGH — nothing below HIGH ships in Phase 0/1)

### P0 — live damage or live exposure
- **F-GATE-1** `scripts/ops/loop_validate.sh:18-35` — `run_gate`/`run_shell_gate` end
  `return 0` under `set +e`. The gate runner is mechanically incapable of failing.
- **F-COST-1** `backend/app/api/endpoints/auth.py:10-20` + `backend/app/main.py:934-941` —
  anon-session minting unthrottled; ~200 sessions/min × 5 msgs ≈ 1000 free LLM turns/min/IP.
- **F-ING-1** `backend/scripts/ingestion/bulk_ingest_video.py:233` — `acquire_lock()`
  with no `release_lock()`; 900s TTL wedges every retry.
- **F-BKP-1** `infrastructure/cron/mukthiguru-backup:22` — backs up `spiritual_wisdom`,
  live collection is `spiritual_wisdom_contextual`. Backup is a ritual, not a restore.
- **F-CFG-1** `nginx.conf:123-127` — `/ui` proxy lost its RFC1918 allow/deny. Documented
  invariant, absent in config. Regression.
- **F-AGT-1** `.claude/settings.local.json:35-195` — tracked wildcard allow-list
  (`git push *`, `env`, `pip install *`, `docker exec *`), no deny list.

### HIGH — correctness / money / data
- **F-COST-2..5** `backend/services/cost_tracker.py` — `id(object())` ZADD collisions
  (`:335`); flat per-1K rate ignoring 8× I/O asymmetry (`:153-160`, `:125`); process-local
  degrade lists diverge across replicas (`:174-190`); allow-on-Redis-failure with no
  alert (`:500-504`); silent drop when Supabase missing (`:239-242`); unbounded
  `get_usage_report` scan (`:362-366`); budget gate on 3 paths only, stream/v2/admin
  unaudited (`chat.py:542,698,820`).
- **F-RAG-1** `backend/services/embedding_service.py:1782-1789` — `cascaded_rerank`
  returns unscored `documents[:top_k]` when `len<10` with ColBERT off. Lowest-recall
  queries get zero rerank. Plus O(n²) text-equality scan (`:1816-1818`).
- **F-RAG-2** `backend/ingest/video_pipeline.py:268,278` — hardcoded `upsert` with
  `uuid4()` IDs outside `spiritual_wisdom*`: unretrievable + duplicates on re-ingest.
- **F-VERIFY-1** `backend/app/pipeline/stages/glue_stages.py:290-297` —
  `faithfulness_score=0.0` + `hallucination_flag=True` + `citations_verified=True`
  in one dict. No consumer can trust any field.
- **F-REDIS-1** `backend/app/api/chat.py:950-952`, `health.py:72`, `orchestrator.py:646` —
  per-request `aioredis.from_url()` with no `close()`; pool leak under SSE fan-out.
- **F-COAL-1** `backend/app/coalescer.py:125-142` — one Redis error → permanent
  in-memory fallback, never re-probes; multi-pod dedup silently per-pod.
- **F-CACHE-1** `backend/services/cache/semantic_adapter.py:252-270,277-278` —
  Qdrant vector + Redis payload dual-written non-atomically; `invalidate_all`
  drop+recreates under readers.
- **F-CELERY-1** `backend/celery_config.py:108-112` vs `backend/start_railway.py:330-333` —
  only 3 of 5 queues routed; broker+backend share one Redis DB (head-of-line blocking).
- **F-CKPT-1** `backend/ingest/handlers/checkpoint.py:210-255` — single-tier write,
  multi-tier read; file path ephemeral on Railway; Redis loss forks history. No shared WAL.
- **F-GRAPH-1** `rag/graph_strategies.py:385,489,653` — bare `compile()`, no checkpointer,
  no `interrupt_before/after`. Crash loses state; no HITL slot. Plus unbounded
  `recursion_limit: 60` (`graph_stage.py:386`), no spin detector.
- **F-PROMPT-1** `services/prompt_store.py:22-25` vs `rag/prompts/rag.py:175`,
  `rag/prompts/system.py:23` — version store exists in admin only; nodes read static
  files; evals never slice by `prompt_version_id` (`telemetry_db.py:310` logged, never read).
- **F-DSPY-1** `rag/dspy_engine.py:17-19,91,109,121,170-198` — compiled program absent,
  `cache=False` on all provider LMs, optimizer harness never calls save/load. Dead loop.
- **F-API-1** `backend/app/api/memory.py:88-93` — `page` ignored, `total` echoes page
  length. Plus dual error envelopes (`main.py:1101-1121`, `safe_errors` computed then
  dropped); `job_routes.py:57-68` TOCTOU + `None.get` 500 (`:67-68`); unconstrained
  Sarvam `model`/`speaker` passthrough (`speech.py:71,79,137,239`); expired Bearer
  silently downgraded to anonymous (`auth_service.py:668-679`).
- **F-ROUTE-1** Tier-routing sprawl: two classifiers + warmup alias + in-node
  `if query_tier in ("fast",...)` self-bypasses (`graph_stage.py:214-326,344-362`).
  Terminal `handle_fallback` ships 0.0-faithfulness finals (`short_circuit.py:207-310`).
- **F-PROD-1** `docker-compose.prod.yml:64-82` — graph env omitted, falls to localhost.
  Plus `redis allkeys-lru` evicts quota/session keys (`:140`); Qdrant version drift
  across manifests (`:111` vs helm `v1.17.1`); grace 180s vs 330s documented
  (`start_railway.py:54` vs `railway.json:27`); GHCR≠Railway Dockerfile
  (`build-deploy.yml:60`); no workflow concurrency cancel; heavy liveness probe.
- **F-WEB-1** No direct-SSE reconnect/resume (`streaming.ts:151,212`); `lazyWithRetry`
  reload discards in-flight state (`lazyWithRetry.ts:21-24`); iOS preload never fires
  (no `requestIdleCallback` fallback, `:52-56`); reduced-motion ignored on chat path
  (`ChatInterface.tsx:166,322,2152-2450`, bare `animate-ping/bounce` ×5 files);
  `DemoModal` video has no captions track; `chatStorage` bypasses Preferences adapter;
  QueryClient retries 4× while comment says 2× (`App.tsx:129-133`).
- **F-PY-1** Sync `get_container()` in async routes (`admin.py` ×9 sites,
  `canonical_memory.py:245+`); ~60 inline `HTTPException`; bare swallows
  (`orchestrator.py:305,657`, `pipeline_coordinator.py:231,554`, `chat.py` ×5,
  `main.py:62,356`); `response_model` nearly absent; dual provider generations
  (`services/llm/` vs legacy `services/*_service.py`); `mypy strict=false`;
  `searcher.py:79` sleep possibly on loop; unbounded `run_in_executor(None)`
  (`ingest/pipeline.py:2740`).
- **F-TEST-1** No MSW, `fireEvent`-only (0 `userEvent` files), no Vitest coverage
  thresholds, no POM dir, 7× arbitrary `waitForTimeout`, no `bug-check` workflow,
  loop never invokes RAGAS/benchmark runners.
- **F-DOC-1** No `docs/adr/`; SPEC_DEV false authority (`docs/SPEC_DEV.md:3`);
  no `docs/README.md` over 116 files; three parallel maps unowned
  (`subsystem-inventory` vs `CODEMAP` vs `ARCHITECTURE`); `.mcp.json` lacks
  context7/exa/firecrawl/codescene; `research/.../temp/` committed; venv shadowing
  in worktree; lessons lack transfer syntax (0 `Signal to recognize` hits).
- **F-SEC-1** `cookies.txt` resurrected on disk; tracked `.env.*` templates need
  placeholder proof; `main.py:744-747` allows shared `.railway.app` suffix;
  user-message excerpts in logs (`stream_orchestrator.py:296-297`,
  `orchestrator.py:102-103`); ingest `file.read()` unbounded + suffix-only gate
  (`ingest.py:369-373`); `pip-audit` stall still open.

## Phase 0 — Stop the bleeding (this week; ~10 small diffs, no excuses)

| # | Fix (finding) | Acceptance criterion |
|---|---|---|
| 1 | Propagate real exit codes in `loop_validate.sh` (F-GATE-1) | Deliberate violation on a branch exits non-zero in CI |
| 2 | Rate-limit anon-session minting (F-COST-1) | 200 sessions/min from one IP → 429s; test proves it |
| 3 | `release_lock()` in `finally` + single checkpoint authority (F-ING-1, F-CKPT-1 partial) | Kill -9 mid-ingest twice; resume never wedges, never double-counts |
| 4 | Cron → `spiritual_wisdom_contextual` + install + restore drill (F-BKP-1) | Serve one query from the cron artifact alone |
| 5 | Restore `/ui` allow/deny (F-CFG-1) | Config matches AGENTS.md invariant verbatim |
| 6 | Scope allow-list + deny list (F-AGT-1) | No `push *`, `env`, `pip install *`, `docker exec *` pre-authorized |
| 7 | Verification-dict constructor invariant (F-VERIFY-1) | `0.0` ⟂ `citations_verified=True` impossible by construction + test |
| 8 | Kill `cookies.txt`, rotate YT session, prove `.env.*` placeholder-only (F-SEC-1) | gitleaks + recorded review |
| 9 | Bound ingest reads + magic-byte gate (F-SEC-1) | Same pattern as `chat.py:83` on all upload paths |
| 10 | Prod compose graph env + Redis eviction scope (F-PROD-1 partial) | Boot prod compose; graph + quota keys verified alive |

## Phase 1 — Make gates real (next 2 weeks)

- **Fail closed everywhere it matters:** limiter → tight local fallback or closed;
  `is_user_over_budget` → closed + alert on Redis failure; cost `record()` → retry
  queue, never silent drop (F-COST-2..5).
- **Cost truth:** I/O-split rates; collision-free ZADD members; shared Redis degrade
  state; bounded `get_usage_report`; budget-gate coverage audit over stream/v2/admin.
- **Connection hygiene:** shared Redis client + `close()` discipline; coalescer re-probe
  with backoff; connector/retry/timeout helper for Supabase/Qdrant/Redis (F-REDIS-1, F-COAL-1).
- **Cache atomicity:** single-writer/versioned invalidation for semantic tier; kill
  drop-recreate-under-readers (F-CACHE-1).
- **Rerank the tail:** scored path for small sets; RRF weights eval-gated; O(n²) scan
  indexed (F-RAG-1, fusion `+0.05`/`rrf_k=60`).
- **Kill raw-path writes:** all Qdrant writes via `QdrantIndexer`, deterministic IDs (F-RAG-2).
- **Celery honesty:** route all 5 queues or amend the contract; separate broker DB (F-CELERY-1).
- **Graph durability:** checkpointer + interrupts on fallback paths; recursion budget with
  spin detection (F-GRAPH-1).
- **Prompt store live:** nodes read `get_active()`; evals slice by version; prompt
  changes gated on metric delta; DSPy cache on or branch deleted (F-PROMPT-1, F-DSPY-1).
- **Error contract:** `AppError(code,status)` + global handler + single envelope;
  `safe_errors` returned, not dropped; TOCTOU + `None.get` fixed; Bearer expiry
  returns 401 + refresh signal, never silent anonymous (F-API-1, F-PY-1).
- **Container discipline:** kill handler-level `Service()` news; finish
  `get_container_async()` migration; `response_model` on all routes; mypy strict
  ratchet (F-PY-1).
- **Dual-stack cleanup:** retire legacy providers or new abstraction — one stack
  (F-PY-1).

## Phase 2 — Prove it in prod (starts at Railway unpause)

- Replicas ≥2; `FORWARDED_ALLOW_IPS` set; single Dockerfile for GHCR+Railway;
  grace values reconciled; workflow concurrency cancel; lightweight liveness.
- NDCG + RAGAS + guru-voice baselines on prod Qdrant; holdout rotation; golden-set
  grader with pass@k; RAGAS release-gating on prompt change.
- TDD proof chain (RED/GREEN checkpoints); BUG-R naming; MSW + userEvent +
  coverage thresholds + POM + zero arbitrary sleeps; loop invokes RAGAS/benchmark.
- Tier-routing collapse: one classifier, warmup alias deleted or contracted,
  divergence guard marked as safety-critical with dedicated tests; grounded-or-escalate
  replaces 0.0 finals (F-ROUTE-1).
- SSE resume on direct path; i18n diff audit (complete or delete fallbacks);
  focus-trap + live-regions + captions; tablet pass; Preferences adapter everywhere.
- `docs/adr/` backfilled (Memgraph, RRF/DBSF, lightweight guardrails, TTL);
  SPEC_DEV claim struck; secrets/PIDs out of harness; `docs/README.md` index;
  lessons split (invariants stay, handoffs archived, supersede markers).
- Tiered SPOF table made honest (live tier only) or replicas actually built;
  healthcheck grace that can't mask boot failure; Neo4j restore proven or RPO
  restated.

## Phase 3 — Adopt ECC (parallel, low risk)

Install: `agent-architecture-audit`, `fastapi-reviewer` + `python-reviewer`,
`rag-pipeline-reviewer`, `production-audit`, `verification-loop`, `tdd-workflow`,
`eval-harness`, `security-review` + `security-scan`, `context-budget`,
`rules/python` + `rules/common`, `docs-lookup`, `comment-analyzer`,
`silent-failure-hunter`, `refactor-cleaner`, `pr-test-analyzer`, `spec-miner`.
Permanently skip: homelab-*, network-device-*, non-Python/TS stacks, crypto/trading,
healthcare-PHI, media-creation, unrelated business flows.

## Score trajectory

| Area | Now | P0 | P1 | P2+3 |
|---|---|---|---|---|
| Agent stack | 2 | 3 | 4 | 5 |
| Orchestration | 1 | 1 | 2 | 3* |
| Eval/testing | 2 | 3 | 4 | 5 |
| Memory/learning | 2 | 2 | 3 | 4 |
| Backend arch | 3 | 4 | 5 | 5 |
| Security | 3 | 4 | 5 | 5 |
| Frontend | 2 | 2 | 3 | 4 |
| Data/ingestion | 2 | 3 | 4 | 5 |
| Docs | 1 | 2 | 3 | 4 |
| DevOps | 2 | 3 | 4 | 5 |
| Python depth | 2 | 3 | 4 | 5 |

*Orchestration caps at 3 by design — a serving pipeline needs no councils.

---

## Verification pass — 2026-09-16 (main session)

The plan above is an ECC-agent artifact. This section records what was
independently checked against the working tree, what is now owned, and what the
plan missed. **A finding is only as good as the last time someone ran it.**

### P0 findings spot-checked on disk — 7/8 confirmed, 1 FALSE POSITIVE

| Finding | Verified | Evidence |
| :--- | :--- | :--- |
| F-GATE-1 | **FALSE POSITIVE** | My own check was wrong and is corrected here. `run_gate`/`run_shell_gate` do end in `return 0`, but that is deliberate: it lets the matrix run every gate instead of aborting on the first failure. The verdict is an `awk` aggregation at the BOTTOM of the file that turns any non-zero row in `$SUMMARY` into `LOOP_RESULT=FAIL` + `exit 1` — and it existed at `HEAD`, before this session (`git show HEAD:scripts/ops/loop_validate.sh`). I read lines 14-40 and never read the tail. The CI-gates agent then proved the script fails empirically: a real ruff violation produced `backend_ruff 1`, `LOOP_RESULT=FAIL`, exit 1. The file's own header notes this was "filed twice as a swallowed-exit-code bug and twice wrongly" — this is the third time. Two REAL gaps were found and fixed nearby: a missing backend `.venv` recorded `SKIP` instead of failing, and an empty `$SUMMARY` (zero gates ran) was not treated as failure. |
| F-BKP-1 | CONFIRMED | cron line 22 passes `--collection spiritual_wisdom`; the live collection is `spiritual_wisdom_contextual`. The backup restores an empty product. |
| F-CFG-1 | CONFIRMED | `nginx.conf:123-127` is five lines, `proxy_pass` + two headers, no allow/deny. |
| F-AGT-1 | CONFIRMED | 175 allow entries including `git push *`, `pip install *`, `docker exec *`. **No deny list at all.** |
| F-VERIFY-1 | CONFIRMED | `glue_stages.py:292-297` — `faithfulness_score=0.0`, `hallucination_flag=True`, `citations_verified=True` in one construction. |
| F-DSPY-1 | CONFIRMED | `cache=False` at `dspy_engine.py:91,108,121`. |
| F-SEC-1 (cookies) | CONFIRMED, **severity corrected** | `cookies.txt` is 549KB on disk, but it is gitignored (`.gitignore:141`) and `git log --all -- cookies.txt` is EMPTY — never tracked, never pushed. This is local-disk hygiene plus a session rotation, NOT a repository exposure. Phase 0 item 8 should say so; "resurrected" reads as a leak. |
| F-COST-1 | file present | `backend/app/api/endpoints/auth.py` exists; the throttle claim itself was not re-measured. |

### Investigated and NOT a defect — do not add it

`release_manifest=get_release_manifest().to_dict()` appears at 15 call sites and
looks like a violation of the ReleaseManifest Public Projection Invariant. It is
not. Those sites populate the **internal** pipeline dataclass; the projection
happens at the public boundary (`app/orchestrator.py:177`,
`app/api/chat.py:781`, both via `to_public_manifest_dict`), and
`tests/test_release_provenance.py` pins it. Recorded here so the next auditor
does not re-open it.

### What the plan missed

1. **Production runs Neo4j, not Memgraph** (checkpoint §6 blocker 2). This
   contradicts the migration that justified the memory budget behind the $25
   plan. Absent from a doc claiming full coverage.
2. **Celery worker is `● Online`**, not opt-in-paused, billing against the
   ceiling (checkpoint §6 blocker 3). Also absent.
3. **Phase 2's entry condition does not exist.** It "starts at Railway unpause";
   Railway is `● Crashed`. The largest phase hangs off an unowned external
   dependency the plan never names as a dependency.
4. **The score trajectory has no scorer.** Re-scoring by the same agents that
   produced the findings, after their own remediation, is defect class #7 from
   the session checkpoint — *a benchmark that scores its own reference*. Scoring
   must be done by something that can fail: the unified benchmark harness, or a
   reviewer who did not do the fixing.
5. **Phase 3 cannot fail.** Seventeen ECC installs with zero acceptance
   criteria, in a document whose own rubric scores advisory-only work as a 3.
6. **"~10 small diffs" is wrong on two items.** Phase 0 #3 (single checkpoint
   authority) and #7 (verification-dict constructor invariant) are refactors.
   Estimating them as diffs is how Phase 0 slips.

### Ownership as of 2026-09-16 (four agents live)

| Plan item | Owner |
| :--- | :--- |
| F-GATE-1, Vitest coverage thresholds, `mypy strict` ratchet | CI-gates agent |
| F-PROD-1 (grace 180 vs 330, compose graph env, `allkeys-lru` on quota keys, Qdrant drift, heavy liveness), part of F-REDIS-1 | prod-hardening agent |
| Phase 2 eval items, F-PROMPT-1 eval-slicing | benchmark-unification agent |
| Everything else | UNOWNED — assign before Phase 0 is called started |

**Boundary rule while these four run:** `.github/workflows/**`, `Makefile`,
lint/type/coverage config and `scripts/ops/loop_validate.sh` belong to the
CI-gates agent. `start_railway.py`, `app/api/health.py`,
`services/openrouter_service.py`, `services/onnx_reranker.py` belong to the
prod-hardening agent. Two agents editing one file is how this session already
lost work once.
