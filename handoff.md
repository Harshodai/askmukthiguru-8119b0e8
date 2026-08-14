# ⚠️ REMAINING ITEMS — DO NOT REMOVE UNTIL PROD TESTED ⚠️

> **This section must remain at the top of handoff.md until ALL items are verified in production.**
> Do not delete, edit, or remove these items until prod testing confirms each is done.
> Last updated: 2026-08-11 (wave 10 audit sprint `4f1423e3` on main).

## Pre-Prod Verification Required

### Backend (local suite: 1583 passed, 2 infra-bound failures — Qdrant/Redis connection refused, pre-existing at HEAD)

1. **`test_qdrant_search_quality` ×3** (`test_qdrant_search_quality_dense`, `test_qdrant_search_quality_hybrid`, `test_qdrant_search_quality_hybrid_reranked`)
   - **Status**: ✅ NDCG=0.0 bug FIXED 2026-08-10 — `_extract_source_filename()` multi-key fallback (`source_url` → `source` → `url`, nested payload too) + DCG formula corrected to `log2(rank+2)`. Now `@pytest.mark.integration` (skipped by default via `-m 'not integration'`) with a Qdrant-unreachable skip guard.
   - **Action**: Baseline NDCG against production Qdrant per AGENTS.md item 8 (load prod env first — a host run without it hits docker/localhost, not prod).

2. **`test_retrieve_documents_contract`** (`test_retrieve_documents_contract::test_retrieve_documents_contract`)
   - **Status**: ✅ PASSING (1 passed, verified 2026-08-11 at HEAD `4f1423e3`). Mock setup now covers the full call chain: OKF injection disabled, semantic cache disabled, score-delta cutoff disabled; Qdrant/LightRAG/Ollama mocks injected; LightRAG correctly excluded from hot path.

### Production Environment Tasks (from plan STATUS, wave 8)

3. **P1-OPS-6 T4/T5 — cold-start <60s verification + prod load test (2 replicas)**
   - **Status**: Gated on prod. `railway.json` set to 1 replica (2 replicas caused second replica to fail init timeout). T4/T5 need cold-start verification with 2 replicas + prod load test.
   - **Action**: Deploy to Railway staging, scale to 2 replicas, verify cold-start <60s, run load test (`benchmarks/locustfile.py`), confirm no init timeout.
   - **Mark done when**: 2-replica cold-start <60s verified on Railway staging/prod.

4. **P1-OPS-1 T5 — synthetic alert on staging**
   - **Status**: Synthetic alerting configured but not verified on staging.
   - **Action**: Deploy synthetic alert to Railway staging, trigger alert, verify on-call notification fires.
   - **Mark done when**: Synthetic alert fires on-call notification on staging.

### Deployment Readiness (from AGENTS.md checklist, Jul 31)

5. **Language coverage audit** — `t()` usage vs translation keys. 8 of 14 languages fall back to English (bn, gu, ml, ur, or, pa, as, sa). Hardcoded English strings still exist. 6 real locales (en, hi, te, kn, ta, mr) need missing keys added.
6. **Full responsive stress-test** at every breakpoint (especially 768–1024 tablet).
7. **Google login E2E test** using dedicated OAuth test identities or isolated provider test app with CI-injected secrets (verify single redirect in staging).
8. **Forgot password E2E test** with real Supabase email (verify email sent + link works).
9. **Audio E2E on production** (CDN-accessible Lovable asset, not `:8080`).
10. **Live-LLM guru-voice benchmark** → flip `langhanam_voice_enabled` at ≥4.0/5.0.
11. **Set nightly-RLS repo secrets** and confirm ephemeral-user cleanup before first prod run.

### Security / Ops

12. **Rotate the OpenRouter key** exposed 2026-08-02 (https://openrouter.ai/keys). Still open from prior handoff.
13. **Neo4j + LightRAG rebuild** — 41.4% contaminated; rebuild only after green is stable (decision in plan §6.3.2). `spiritual_wisdom_contextual` still rebuilding.
14. **34 unread config fields** (`csrf_secret`, `auth_rate_limit_*` need a wire-or-remove decision). Open from prior handoff.
   - **Status**: ✅ RESOLVED 2026-08-11 (wave 10) — C5 deleted 8 dead settings; `test_no_undeclared_dead_settings` (S1) scans the whole backend with a justified allowlist: 9 C5-owned leftovers + 22 `KNOWN_EXTRA_DEAD` entries documented with reasons (scan 2/2 pass). Remaining decision: wire-or-remove the 22 `KNOWN_EXTRA_DEAD` fields — the scan allows them but they have no runtime read.

---

# EXECUTION RUNBOOK — Remaining Audit Fixes (2026-08-15)

> Scope-locked: each cluster lists exact files. Touch ONLY those files — no drive-by refactors,
> renames, or "improvements" elsewhere. If you notice something else while in a file, file a new
> task instead of fixing it inline. Every cluster has an acceptance criterion; don't mark done
> without meeting it. Clusters group by file-collision safety — entries in the SAME cluster must
> go through ONE agent/pass (they share a file); different clusters are parallel-safe.

**Already done and verified this session** — do not re-touch: tasks #1-#17, #18-#20, #21-#24, #26-#28
(cost_tracker part 1), #27, #34-#36, #38-#39, #42, #52, #70, #75 (in progress as of this writing —
check task tracker before re-running).

## Cluster B — cost_tracker.py blocking I/O follow-up (task #28)
**Scope:** `backend/app/api/chat.py` — ONLY the single call site invoking `get_cost_tracker().record(...)`.
**Description:** `record()` blocks the event loop with synchronous Supabase I/O; already fixed on
the cost_tracker.py side (throttle + alert write). Only the call-site wrap remains.
**Fix:** `await asyncio.to_thread(get_cost_tracker().record, tenant_id=..., ...)` — keep all
existing kwargs. Do NOT make `record()` itself `async def` (requires the call site to await it
too; doing one without the other silently no-ops cost tracking).
**Acceptance:** `grep -n "asyncio.to_thread" backend/app/api/chat.py` shows the wrapped call;
`chat.py` imports clean; nothing else in the file changed.

## Cluster C — Checkpoint Redis-fallback gap (task #25)
**Scope:** `backend/ingest/handlers/checkpoint.py` only.
**Description:** `is_processed()` returns `False` on empty-but-successful Redis `.exists()`
without checking `self.processed_chunks` (the local-file fallback set) — a checkpoint that fell
back to local JSON during a Redis blip becomes permanently invisible.
**Fix:** After a Redis `False`, also check `self.processed_chunks`, return `True` if present.
**Acceptance:** any existing checkpoint test still passes; module imports clean.

## Cluster D — MemoryStage sync Celery dispatch (task #29)
**Scope:** `backend/app/pipeline/stages/memory_stage.py` only.
**Fix:** wrap `drain_memory_outbox.apply_async()` in `await asyncio.to_thread(...)`.
**Acceptance:** grep confirms the wrap; module imports clean.

## Cluster E — Coalescer shield + lock leak (tasks #30, #32)
**Scope:** `backend/app/coalescer.py` only.
**Fix:** (1) wrap the coalesced `coro_func()` call in `get_or_run` with `asyncio.shield()` so a
follower/leader disconnect can't cancel work others depend on. (2) purge `_locks[key]` in a
finally/except around `coro_func()`, not only on success.
**Acceptance:** existing coalescer tests pass; module imports clean.

## Cluster F — Untranslated short-circuits + GDPR logger wiring (tasks #31, #71)
**Scope:** `backend/app/pipeline/stages/doctrine_cache_stage.py`, `guardrail_stage.py`,
`backend/app/pipeline/pipeline_coordinator.py`.
**Fix:** (1) add the same translate-before-return branch already used elsewhere to
`DoctrineCacheStage` and `_circuit_open_result`. (2) call
`ctx.container.compliance_logger.log_interaction(...)`/`log_error(...)` from a real point in the
request path (likely result-assembly / error handling) — read `services/compliance_logger.py`'s
signature, don't edit that file.
**Acceptance:** modules import clean; pipeline stage tests still pass; grep confirms
`log_interaction` has a real caller outside its own file/tests.

## Cluster G — Dead-code deletions batch 1 (tasks #33, #43, #44, #45, #47, #50, #61)
**Scope:** 7 independent files, fully parallel:
- `backend/services/streaming_generator.py` — DELETE (#33)
- `backend/rag/graph_strategies.py` — remove `lightweight_verify` only (#43, ~108-161) + its
  dedicated test file if solely for it
- `backend/rag/nodes/intent.py` — remove `route_by_intent` only (#44, ~1009-1029) + its export
  in `rag/nodes/__init__.py`
- `backend/rag/cot_verifier.py` — DELETE (#45)
- `backend/services/model_failover.py` — DELETE (#47)
- `backend/services/ontology_schema_validator.py` — DELETE (#50)
- `backend/ingest/sources/base.py` — DELETE (#61)
**Acceptance per file:** grep confirms zero remaining references outside tests; `pytest --collect-only` still collects clean.

## Cluster H — NeMo output guardrail no-op (task #46)
**Scope:** `backend/guardrails/nemo_handler.py` only.
**Description:** `_handle_output` classifies a NeMo-generated continuation, not the actual output
text.
**Fix:** use NeMo's real output-classification API on `text` directly; if none exists, at minimum
make the synthetic-dialogue check actually evaluate `text`, not a fake completion.
**Acceptance:** `test_guardrails.py`/`test_guardrails_chain.py` pass; manual trace confirms `text`
(not a generated continuation) drives block/allow.

## Cluster I — citation_extractor wrong field (task #40)
**Scope:** `backend/rag/nodes/citation_extractor.py` only.
**Fix:** `state.get("selected_docs") or state.get("relevant_docs", [])` instead of
`state.get("documents", [])`, matching `generation.py`'s own fallback (~677-678, read only).
**Acceptance:** grep confirms the change; citation tests pass if present.

## Cluster J — faithfulness_floor enforcement (task #41) — NEEDS SIGN-OFF, DO NOT AUTO-FIX
**Scope:** `backend/rag/nodes/verification.py`, IF approved.
**Warning:** changes core answer-acceptance behavior, could reject more answers than today. Do
NOT apply without running the RAGAS/benchmark eval suite for a before/after reject-rate delta and
explicit sign-off. If told to "just fix it": add `faithfulness_score >= settings.faithfulness_floor`
as an explicit `is_valid` condition, but flag prominently that eval verification is still needed —
"code matches docs" is not "safe to ship."
**Acceptance:** blocked until eval run authorized.

## Cluster K — Guardrail allowlist ordering (task #49)
**Scope:** `backend/guardrails/lightweight_handler.py` only.
**Fix:** move the spiritual-domain allowlist check to AFTER the optional LLM-classifier check (or
scope the allowlist to skip only regex/keyword checks). Read ~350-370 fully first — crisis-safety
checks must stay before the allowlist, don't disturb that ordering.
**Acceptance:** `test_guardrails.py` passes; manual check that an allowlisted term + LLM-catchable
content now reaches the LLM check.

## Cluster L — Config/doc-only fixes (tasks #51, #53)
**Scope:** `backend/app/config.py` (comment only), root `CLAUDE.md`.
**Fix:** (1) fix the misleading "toggle" comment on `semantic_router_enabled`/`_top_k` — state
they're unwired, don't implement wiring. (2) update `CLAUDE.md`'s Service Matrix rrf_ranker.py
row to `services/rankers.py::_reciprocal_rank_fusion`.
**Acceptance:** doc/comment-only diffs, no behavior change.

## Cluster M — YouTube Tier-4 audio fallback (tasks #54, #55)
**Scope:** `backend/ingest/sources/youtube_service.py`, plus ONE call site in
`backend/ingest/pipeline.py` where `fetch_transcript_hybrid()`'s `method="failed"` is handled —
nothing else in pipeline.py (re-read current file state first, this session already touched it).
**Fix:** (1) add the missing `await` on `transcribe_and_preprocess_audio()` in
`_try_audio_transcribe_fallback`. (2) wire the Tier-4 fallback into pipeline.py's failure path.
**Acceptance:** the await fix is a 1-line diff; the wiring addition is small, not a rewrite;
modules import clean.

## Cluster N — Quality gate fails open (task #56)
**Scope:** `backend/ingest/quality_gate.py` only.
**Fix:** on `LLMQualityScorer.score` exception, route to Tier-3 staging (fail closed) instead of
auto-passing at score=65, matching `gate_summary_faithfulness`'s existing fail-closed pattern in
the same file.
**Acceptance:** simulate an LLM exception, confirm the item is NOT auto-passed.

## Cluster O — BoundaryChunker fallback + bounds (tasks #57, #58)
**Scope:** `backend/ingest/boundary_chunker.py` only.
**Fix:** (1) add a character-length fallback split when `_split_sentences` produces one
oversized "sentence" (no punctuation). (2) `_merge_small_chunks` should use `self.min_size`/
`self.max_size`, not hardcoded classmethod defaults.
**Acceptance:** feed an unpunctuated long string, confirm multiple reasonable chunks not one
giant one; existing chunking tests pass.

## Cluster P — DataAuditor dead code (task #59)
**Scope:** `backend/ingest/auditor.py` (DELETE). Check first whether Cluster A's earlier
pipeline.py fix already removed the `DataAuditor` import — if not, remove that one line too.
**Acceptance:** grep confirms zero remaining references; pipeline.py imports clean.

## Cluster Q — adaptive_chunking_service.py dead code (task #60)
**Scope:** `backend/services/adaptive_chunking_service.py` (DELETE) + its dedicated test file if
solely for it + `CLAUDE.md`'s Service Matrix row (point at `ingest/adaptive_chunking.py::AdaptiveChunker`).
**Acceptance:** grep confirms zero references; CLAUDE.md updated.

## Cluster R — audio_transcriber coverage guard (task #62)
**Scope:** `backend/ingest/audio_transcriber.py` only.
**Fix:** add a coverage-ratio check in `_transcribe_chunks` before returning, mirroring
`contextual_reingest.py`'s `_assert_coverage` pattern (read only, don't edit that file).
**Acceptance:** simulate 2-of-6 segment failure, confirm it now raises/flags instead of silently
truncating.

## Cluster S — Hardcoded path cleanup (task #63)
**Scope:** `backend/ingest/social_media_loader.py` only. Remove the hardcoded dev-machine
cookies.txt path (line ~62), let it fall through to `cookiesfrombrowser`.
**Acceptance:** grep for the literal path returns nothing.

## Cluster T — Cypher f-string safety (task #64) — verify only
**Scope:** read-only check of `triple_extractor.py` + `relation_type_to_neo4j_label`. Confirm the
label is always enum-derived regardless of LLM input. Note the finding; no fix expected unless
the constraint is broken.

## Cluster U — PII scrubber dead code (task #65)
**Scope:** `backend/app/telemetry_sink.py`, `backend/app/telemetry_db.py` (read `PIIScrubber` +
its scrubbing `log_query_trace`, don't rewrite them).
**Fix:** route `SupabaseTelemetrySink.log_query_trace`'s `query_text`/`response_text` through
`PIIScrubber`, or delegate to telemetry_db.py's scrubbing function — pick the less invasive
integration after reading both.
**Acceptance:** send a fake email/phone through the live path, confirm the persisted text is redacted.

## Cluster V — db_rectify.py dry-run (task #66)
**Scope:** `backend/scripts/db_rectify.py` only. Add argparse `--dry-run`/require `--apply`,
matching the convention in `backend/scripts/ops/` siblings (read one first).
**Acceptance:** no-flag run deletes nothing and prints intent; `--apply` required for real deletes.

## Cluster W — hallucination_anomaly.py silent failure (task #67)
**Scope:** `backend/scripts/ops/hallucination_anomaly.py` only.
**Fix:** distinguish a Supabase query exception from a genuine empty result; alert/exit non-zero
on the former instead of reporting "no anomaly."
**Acceptance:** simulate a connection failure, confirm it's no longer indistinguishable from "no anomaly."

## Cluster X — Dead telemetry event-bus (task #68)
**Scope:** `backend/app/telemetry/` directory (delete), plus the
`self.telemetry.stage_complete(...)` call site in `pipeline_coordinator.py`'s `_stage()` —
nothing else in that file.
**Fix:** delete the dead event-bus module and its call site. Do NOT wire a real sink in this
pass — that's a separate feature decision.
**Acceptance:** grep confirms zero remaining references; pipeline still runs (existing tests pass).

## Cluster Y — SLO alerting infra (task #69)
**Scope:** `infrastructure/prometheus/prometheus.yml`, `backend/docker-compose.yml` (prometheus
service block only, plus add an alertmanager service block).
**Fix:** add `rule_files:` pointing at `alerting-rules.yml`; mount it into the container; add an
`alertmanager` service using the existing `alertmanager.yml`, matching the compose file's own
conventions.
**Acceptance:** `docker compose config` parses clean; `rule_files` present.

## Cluster Z — Misc LOW single-file fixes (tasks #72, #73, #74, #83, #84)
**Scope:** 5 independent files, parallel-safe:
- `rag/telemetry_observer.py` (#72) — fix docstring (doesn't do Prometheus/StatsD, just logs)
- `scripts/check_docker_health.py` (#73) — remove hardcoded `"password"` Neo4j fallback, fail
  loudly instead
- `scripts/monitoring_dashboard.py` (#74) — fix `parse_prometheus` to read real Histogram
  `_bucket` lines, not substring-match a nonexistent quantile line
- `services/reranker_service.py` (#83) — raise/log an explicit signal when both rerankers fail,
  instead of silent `[]`
- `services/multi_provider_llm.py` (#84) — stop silently defaulting to NIM first; drop it from
  default priority or log clearly when used, matching the documented NIM-removal security decision
**Acceptance per file:** module imports clean, no cross-file changes.

## Cluster LL — Circuit breaker cluster (tasks #75-#81) — largest, do separately
**Scope:** `app/api/health.py`, `services/circuit_breaker.py`, `services/qdrant_service.py`,
`services/embedding_service.py`, `services/web_search_service.py`, `services/sarvam_service.py`,
`services/gateways/sarvam_http.py`, `services/openrouter_service.py`, `services/lightrag_service.py`,
`app/container.py` if wiring requires it. Full 7-fix spec already in tasks #75-#81's descriptions.
**Key lesson from a failed first attempt:** use an agent type with Edit/Write tools
(`general-purpose` works; a review-only type like `ecc:python-reviewer` is Read+Bash only and
will refuse).
**Acceptance:** a breaker's state visibly changes after simulated failures on a real service
(not a phantom registry object); existing circuit-breaker tests still pass.

---

# AUDIT — 2026-08-14/15 (8-lane parallel read-only audit, backend + AI end-to-end)

> Read-only. No code changed in this pass — every finding below is tracked as a task (#18-#84 in the session's task list) for staged fixing later. Full detail (file:line, exact failure scenario, fix direction) lives in each task's description, not duplicated here.

## Correction to earlier wave-11 entry
The "webhook fail-open" framing in the wave-11 section below is **wrong**. Verified directly: `scripts/whatsapp_webhook.py`'s `validate_twilio_signature`/`validate_meta_signature` both `return False` (403 reject) when their secret is unset — **fail-closed**, not fail-open. The original session-1 finding this was based on was a false positive. Task #11's warning-log addition was harmless but the rationale was wrong.

## 7 CRITICAL findings (launch blockers)

1. **Unprotected delete-before-write in `_embed_and_index`** (`ingest/pipeline.py:2319-2375`) — `delete_by_source()` runs before embed/upsert, called OUTSIDE every caller's rollback try/except. A failure after delete permanently loses the source's indexed content with no rollback and no checkpoint.
2. **Crisis-preemption response never translated for Indic users** (`distress_stage.py:97-173`) — the pipeline's own sourced Hindi/Tamil/Telugu/etc. crisis-keyword detection correctly fires, but the safety/helpline response it returns is hardcoded English, delivered before `TranslationStage` ever runs.
3. **`cost_tracker.record()` blocks the event loop** (`services/cost_tracker.py:150-165`) — synchronous Supabase I/O runs unwrapped on every chat response's completion path; this session's new hourly budget check doubles the stall. Matches a bug class already documented as causing a production Railway restart under load (`cache_stage.py:407-415`).
4. **Incognito doesn't stop full-content telemetry on 2 of 3 chat routes** — `orchestrator.py`/`chat_engine.py` (`/api/chat`, `/api/chat/v2`) log full message+answer to Supabase regardless of the incognito flag; only the SSE path (`stream_orchestrator.py`) has the guard. **This is a regression from this session's own `d1dc533a` "enforce end-to-end incognito isolation" commit** — fixed everywhere except these two spots, and that commit's own docs falsely claim it's fixed.
5. **`cross_teacher_reasoning` bypasses the teacher-domain rights gate entirely** (`rag/nodes/cross_teacher_reasoning.py:129-183`) — **directly undermines this session's own TeacherDomain work** (task #17). Unlicensed-teacher content (Sadhguru, Amma Bhagavan, ISKCON) can be injected into `relevant_docs` at score 0.95 and delivered to a seeker as licensed Ekam doctrine, since this node never consults `resolve_teacher_domain`/`licensed_domain`.
6. **Two post-retrieval injection points bypass prompt-injection screening** — `cross_teacher_reasoning.py` and `enrich_context`'s LightRAG synthesis both append to `relevant_docs` in nodes that run after `retrieve_documents`'s "single finalization point" screen (`_screen_prompt_injection`), so LLM-extracted graph text never passes through it.
7. **Admin circuit-breaker dashboard/reset endpoint operates on phantom breakers** (`app/api/health.py:266-330`) — `ServiceContainer.circuit_breaker_registry` holds brand-new breaker objects never wired to the real `self._circuit` instances inside each service. Status always reads healthy; reset always reports success while doing nothing. During a real outage the admin observability surface lies.

## Notable HIGH-severity clusters (full list in tasks #19-#84)

- **This session's 3 new circuit breakers (tasks #4/#5/#6) don't actually protect what they look like they protect**: embedding breaker guards a near-unused method while the real hot path (`encode_batch`) is unguarded; web-search breaker can never trip because the provider classes swallow their own exceptions first; Qdrant breaker only covers `search()`, not the RAPTOR/neighbor-lookup calls also on the hot path. Sarvam separately has two disconnected breakers (streaming vs non-streaming) — pre-existing, not from this session.
- **Teacher-domain rights gate (task #17) is write-only** — nothing downstream reads `licensed_domain`/`domain_rights_status`; only covers `BEING` nodes, not `TEXT`/`TRADITION`/`PRACTICE`; alias resolution can silently downgrade the licensed Ekam teacher's own stamp during entity consolidation.
- **Ingestion data-loading layer**: documented YouTube Tier-4 audio fallback is dead code AND has a missing-`await` bug; quality-gate LLM scorer fails OPEN exactly at its pass/fail threshold (opposite of the fail-closed pattern used elsewhere in the same file); `BoundaryChunker` (the default chunker) has no character-length fallback for unpunctuated OCR/ASR text.
- **Telemetry/privacy**: a working PII scrubber exists in `telemetry_db.py` but is never called by the live telemetry path — even non-incognito users get zero redaction. `db_rectify.py` runs unconditional destructive Neo4j deletes with no dry-run, the one outlier among all ops scripts. `hallucination_anomaly.py` reports "no anomaly" indistinguishably from "Supabase connection broken." GDPR `ComplianceLogger` is wired for reads but never fed writes — audit trail always empty. SLO alerting rules exist on disk but are never loaded by Prometheus, no alertmanager service exists.
- **~15 LOW/MEDIUM dead-code findings**: `model_failover.py`, `ontology_schema_validator.py`, `adaptive_chunking_service.py`, `ingest/sources/base.py`, `ingest/auditor.py`'s `DataAuditor`, `app/telemetry/` event-bus (invoked on every request, no-ops every time), `route_by_intent`, `cot_verifier.py`, `lightweight_verify` — see tasks for each.

---

# CURRENT STATE — 2026-08-14 (wave 11: ruthless-plan lane D/F/G + teacher-domain registry)

> Working tree only — **nothing committed**. 22 files changed, all sitting for review.

## What landed this session (all locally verified unless noted)

**Cleanup / dead code**
- Deleted 5 dead files: `app/test_sarvam.py`, `app/test_retrieval.py`, `app/debug_retrieval.py`, `app/debug_helper.py`, `services/llm/failover_provider.py` (all grep-confirmed zero live callers; failover_provider was already documented-dead per NIM-removal note in CLAUDE.md).
- Removed 2 genuinely-dead config flags (`use_contextual_chunking`, `context_budget_enabled`). **8 other flags flagged by an investigator agent were FALSE POSITIVES** — had real `getattr`/dict-access readers; grep-verify caught them before deletion. Do not re-flag: `guardrails_provider`, `enable_colbert`, `llm_speaker_role_fallback_enabled`, `data_audit_strict_mode`, `use_request_queue`, `use_markitdown_parser`, `ab_testing_enabled`, `llm_provider`.

**Config extraction (behavior-preserving, values unchanged, verified via live import)**
- `rag/nodes/retrieval.py`: 6 OKF/adaptive constants → `settings.okf_*` / `settings.retrieval_*`.
- `rag/nodes/generation.py`: 5 constants → `settings.generation_*`.

**Resilience**
- Circuit breakers added to `qdrant_service.py`, `embedding_service.py`, `web_search_service.py` (same `CircuitBreakerConfig.from_provider()` pattern as LLM services). **Caveat**: web-search provider classes (`DuckDuckGoProvider`/`SearXNGProvider`) swallow their own exceptions and return `[]`, so most real failures never reach the breaker — cosmetic until that's changed.
- 5 chaos tests appended to `tests/test_edge_cases.py` (Qdrant timeout, embedding fail, web-search fail, rate-limit, cascading). **NOT RUN GREEN**: the whole file needs live Qdrant/Redis/Neo4j — 11 of 13 pre-existing tests fail identically in a bare sandbox (`400` because `container.py` startup calls `qdrant.init_collection()` synchronously and hard-fails with no Qdrant). Pre-existing infra coupling, not introduced here. **Worth a separate fix: app startup shouldn't 400 the whole TestClient just because Qdrant is unreachable.**

**Cost / security**
- `cost_tracker.py`: soft ₹3,000/month (~$36 fixed conversion) budget alert, log-level only, throttled to once/hour/process. No hard enforcement.
- `scripts/whatsapp_webhook.py`: fail-open signature branches now `logger.warning()` when bypassed (behavior unchanged — still fails open outside prod when secret unset; gated by `WHATSAPP_WEBHOOK_ENABLED=False` + freeze test).

**Capability-manifest gating** (removes hardcoded native checks)
- Added `google_sso` + `push_notifications` flags to `/api/capabilities`; `config.py` `google_sso_enabled`/`push_notifications_enabled` (both default True). `useChatCapabilities` hook + `Index.tsx` + `PushPermissionPrompt.tsx` now read them. Cookie-consent banner left hardcoded (legal, not a feature).

**Memory / privacy (frontend + backend)**
- Consent gate (`AlertDialog`) before first memory save → existing `PUT /memory/consent`, once-per-device localStorage flag.
- `POST /memory/edit` correction endpoint + `MemoryService.edit()` (ownership-checked like `forget()`, re-embeds). Frontend `memoryApi.edit()` + `MemoryManager` edit UI — **these were already built by prior/parallel work, verified wired, not re-done.**
- One-tap reset: ProfilePage "Clear Local Data" now also clears response-prefs + `DELETE /memory/all` cascade; dialog copy updated to disclose truthfully.

**Teacher-domain registry (Phase 3 — NEW, first real domain-isolation)**
- `domain/spiritual_ontology.py` `ONTOLOGY_VERSION` 1.0.0 → 1.1.0. Added `TeacherDomain` dataclass + `TEACHER_DOMAINS` registry + `resolve_teacher_domain()`. Encodes the actual CLAUDE.md rights boundary: **only `ekam` (Sri Preethaji & Sri Krishnaji) is `licensed`/`rollout_enabled=True`**; Sadhguru / Amma Bhagavan / ISKCON are `unlicensed_reference_only`, `rollout_enabled=False` (recognizable for cross-teacher mentions, never a retrievable corpus, never first-person voice).
- `ingest/ontology_writer.py` now stamps `licensed_domain` + `domain_rights_status` on BEING/Teacher nodes at Neo4j write time (unregistered BEING → `unverified`, quarantined not silently-licensed). Self-check + `test_ontology_provenance.py` (2/2) pass.
- **NOT YET DONE**: retrieval side does not yet READ these stamps to filter unlicensed-domain content out of doctrine quotes. The write-side gate exists; the read-side enforcement is the next step.

## Confirmed NOT-STARTED (deferred, need decisions — see "Audit scope" below)
- **Expo companion**: real skeleton (`mobile/expo/`, 9 files, Expo 54) — only `getCapabilities` + `sendChat` (non-streaming). No auth, no SSE streaming, no language sheet, no practices/library. Needs `expo-secure-store` (new dep) for auth + a live backend to verify SSE.
- **SLO enforcement/alerting**: `metrics.py` has `SLO_CHAT_LATENCY` etc. as descriptive constants; nothing enforces/alerts. External blocker — Datadog/PagerDuty MCP servers listed but unauthenticated this session.
- **Response-style preferences** (`ResponsePreferencesMenu`, `responsePreferences.ts`): already fully built + wired by prior work (separate from memory consent).

---

# CURRENT STATE — 2026-08-10 (wave 9: test-isolation fixes + tsc errors)

## Wave 9 — squash commit `2b2d3470` on main (2026-08-10)

All 97 commits from `ruthless-audit-remediation` branch squashed into one commit on main.
This session's work (11 files, the last 1 of those 97 commits):

### Backend (15→4 failed, 1516 passed)
- **Fix 1 (Bucket C)**: Removed `sys.modules` stub pollution from `test_meditation_routing.py` — `_bootstrap_stubs()` permanently replaced `qdrant_client` with non-package stub, breaking `test_qdrant_embedded_mode` ×4.
- **Fix 2 (Bucket A)**: Added `QDRANT_URL=127.0.0.1:6333` override in `conftest.py` — docker hostname didn't resolve on host.
- **Fix 3 (Bucket B)**: Fixed `mock_coalescer` target in `test_edge_cases.py` + `test_chat_endpoint.py` — patched `app.main.coalescer` but orchestrator uses `app.orchestrator._coalescer`; fixed edge ×3, circuit ×2, chat ×1.
- **Fix D**: Narrowed `sys.modules` eviction in `test_anonymous_session_purge.py` + `test_cleanup_inactive.py` — blanket eviction corrupted hallucination test's module reference; fixed hallucination ×6.
- Added collection+point-count skip guard to `test_qdrant_search_quality.py`.

### Frontend (10 tsc errors → 0)
- `lazyWithRetry.ts`: `ComponentType<unknown>` → `ComponentType<any>` (prop types propagate to lazy components).
- `sentry.ts`: `maskInputs` → `maskAllInputs` (ReplayConfiguration has no `maskInputs`).
- `sentry-init.test.ts`: `stubEnv('PROD', 'true')` → `stubEnv('PROD', true)` (boolean type).

### Docs
- `lessons.md`: L-TEST-1 through L-TEST-4 prepended (mock targets, sys.modules eviction, import-time stubs, env DNS overrides).
- Plan STATUS updated. SDD ledger wave-9 rows appended.

### Remaining (see ⚠️ section above — DO NOT REMOVE until prod tested)
4 integration test failures (items 1-2) + 2 prod tasks (items 3-4) + 7 deployment readiness items (5-11) + 3 security/ops items (12-14).

---


## Round 3 — the corrector was replaced, not patched

`ingest/corrector.py`'s LLM proofreading and `services/doctrine_terms.py`'s typed
variant lists are both superseded by **`services/doctrine_lexicon.py`**, built by
**`scripts/ops/build_doctrine_lexicon.py`**. Nothing is hand-typed: vocabulary is
derived from the books, ekam.org, theonenessmovement.org, corpus consensus and a
200k English list. See `lessons.md` L-CORRUPT-15..18 for the five measured
failures that shaped it.

**Measured ship gate** — 12,000 random live chunks: 0.117% changed, 12 distinct
rules, **all 12 correct**. `Ujash`/`Ujasi`/`Ojasi` -> `Ojas` (never enumerated);
`peace`/`piece`/`soar`/`steel`/`bodhi`/`citta` untouched.

Architecture is an asymmetry — **193,686 words protect, 5,849 attract**:
1. in authority vocabulary -> never touched (this is the whole safety property);
2. common in corpus / many sources -> never touched;
3. possessive or hyphenated -> never touched (style, not error);
4. capitalised -> only maps to another proper noun;
5. prefix completion beats similarity for truncations (`coura` is `courage`, not `core`);
6. phonetic path aims only at doctrine-only terms, never ordinary English.

Deps added, all permissive: `jellyfish` (MIT), `rapidfuzz` (MIT), `wordfreq`
(Apache-2.0), declared in `requirements.txt`.

**Book pilot finished**: `The_Four_Sacred_Secrets.pdf`, 25/25 sections, 451
chunks, exit 0, 36 min. Green = 453 points. Section-aware ingest works.

### Next, in order
1. Route `doctrine_terms.apply_corrections` to the lexicon — six call sites
   (`corrector.py`, `contextual_reingest.py` x3, `whisper_local_service.py` x2,
   `rag/nodes/generation.py`) change in one edit.
2. Re-run `corpus_forensics feasibility` with the lexicon applied.
3. Reingest all sources; then rebuild OKF, LightRAG, Neo4j, ontology from the
   corrected text.
4. Still open: rotate the OpenRouter key exposed 2026-08-02; 34 unread config
   fields (`csrf_secret`, `auth_rate_limit_*` need a wire-or-remove decision).

# CURRENT STATE — 2026-08-02 (older)

## Round 2 — green was clean but architecturally incomplete (fixed)

The first pilot produced 430 chunks at 0.2% contamination and was still not a
usable collection. `backend/scripts/ops/corpus_forensics.py` (new; `forensic`
and `feasibility` subcommands) found four defects, all now fixed with tests:

1. **Mixed pooling** (`cls=118, mean=312` live). The late-chunking fallback kept
   the CLS vector when a chunk's span could not be located, putting two vector
   spaces ~0.757 cosine apart in one collection — wrong ranking on every query.
   Now mean-pools standalone, and a mixed batch raises. `lessons.md` L-CORRUPT-9.
2. **No parent-child.** Green had none of `parent_id`/`parent_text`/`is_child`,
   which `services/qdrant/searcher.py` and `rag/nodes/retrieval.py` consume, so
   every small-to-big swap was a no-op. Rebuilt in `_build_parents`: 2,000-6,000
   char parents from whole consecutive chunks, deterministic ids, no runt tail.
   Blue's own parents are 88.8% present but **median 320 chars** — do not copy
   them. L-CORRUPT-12.
3. **Broadcast provenance.** `title`/`page_range` came from `payloads[0]`, which
   for `The_Four_Sacred_Secrets.pdf` mis-cites all 1,171 chunks to "Front
   Matter, pages 2-4". `_origin_index_map` now attributes each chunk by
   fractional-position overlap — verified on the real PDF: **23 distinct page
   ranges and titles, monotonically increasing**. L-CORRUPT-11.
4. **Dead metadata pruned.** `phonetic_tokens` (100% of green) fed a searcher
   prefetch deleted for latency; `original_chunk_count` had no reader. Both
   removed, along with the per-query phonetic computation in `searcher.py`.
   `source_version` was **kept** — `retrieval.py` dedups on it. L-CORRUPT-10.

## Bulk re-ingest feasibility — measured answer: NO

`python -m scripts.ops.corpus_forensics feasibility --collection spiritual_wisdom`
over all **720 sources** (not 367 — that figure came from a 10k-point prefix):

| verdict | sources | confidence |
|---|---|---|
| MIGRATE (≤2% contaminated) | 439 | 0.90 |
| MIGRATE_THEN_VERIFY (2-10%) | 49 | 0.45 |
| **REFETCH_FROM_ORIGIN (>10%)** | **232** | 0.95 |

Only **3,105 / 89,061 chunks (3.5%)** are safely migratable — the 439 clean
sources are small, the bulk of the corpus sits in the contaminated 232. Report:
`backend/benchmarks/reports/reingest_feasibility.json`.

**Still open:** rotate the OpenRouter key exposed in a 2026-08-02 transcript
(https://openrouter.ai/keys). Neo4j + LightRAG (41.4% contaminated) still need
delete-and-reingest once green is stable. recall@k remains unmeasurable — only
1 of 68 golden queries references a loaded source.

## The strategy changed: migration cannot clean contaminated sources

Measured, not assumed (`lessons.md` L-CORRUPT-7): re-ingesting `5hNCT4duOgc`
with every gate active wrote **1 chunk of 82**. The gate was right — that source
is **46.4% contaminated in blue**, and re-chunking *concentrates* contamination
(46.4% of coarse chunks dirty → **98.8%** of finer re-chunked output, because one
CoT fragment condemns its whole chunk). **Audit each source first; above a few
percent contamination the only valid path is re-fetching from YouTube.**

## 11 defects fixed 2026-08-02, all with regression tests (1,200 pass / 0 fail)

`corrector.py` — (1) length guard was `min(50, len//2)` = **always 50**, so a
50-char stub replaced a 4,000-char chunk and silently destroyed **65% of a
transcript** (22,487→7,876 chars) while every gate passed it; now a 0.90–1.15
ratio bound. (2) edit-distance ceiling (15% tokens). (3) overlap duplication at
every 4k seam removed.

`contextual_reingest.py` — (4) RAPTOR summaries excluded from transcript
reconstruction (they share `chunk_index` space and were spliced into verbatim
doctrine). (5) metadata `or`-fallback; `content_type` no longer inherited
(every point had `topic=""`, `content_type="summary"`). (6) **coverage
invariant** `_assert_coverage()` raises below 85% after correction, chunking and
contextualization. (8) dangling `parent_chunk_id` removed. (9) `_STATE_FILE` now
resolves in repo *and* image (was writing `/scripts/…` → Permission denied
WARNING → no checkpoint ever persisted). (10) corrected my own misleading
"likely a reasoning model" error message.

`config.py` — (7) `reingest_late_chunking` default `False`→`True`; the committed
default contradicted every stored point's `pooling="mean"`, risking a silent
mix of mean/CLS pooling (~0.757 cosine apart).

`embedding_service.py` — (11) `_ONNX_ENCODER_REVISION` was `None` and
`Dockerfile.railway` baked a **404ing** SHA; re-resolved to
`2b34e84df040034d4b9eabb62383a87c18955822` and verified. Any Railway rebuild
would have failed before this.

## Live state

- **blue `spiritual_wisdom`: 89,061 points — untouched, verified.**
- green `spiritual_wisdom_contextual`: deleted and rebuilding; 1 point from
  `5hNCT4duOgc` (correctly gated) at last check.
- `mukthiguru-pilot` container was processing source 2
  (`The_Four_Sacred_Secrets.pdf`, **1,196/1,196 clean** — the valid migration
  test). It started *before* fixes 6/9/10, so it lacks them and will not persist
  a checkpoint.
- `scripts/ingestion/ingestion_state.json` reset to `[]` (two sources were
  falsely marked processed with zero points in green).

## Next steps

1. Check the pilot result for source 2 — a sensible chunk count proves the
   migration path works for *clean* sources.
2. Per-source contamination audit to split 367 sources into migrate (clean) vs
   refetch-from-origin (dirty).
3. **recall@k is still unmeasured and not measurable** on a near-empty green:
   only 1 of 68 golden queries references any loaded source, so the ceiling is
   1/68 by construction. Do not quote a recall number until coverage is broad.
4. Rotate the OpenRouter key (exposed in an earlier session transcript).
5. LightRAG stores remain **41.4% contaminated**; rebuild only after green is
   stable (decision in plan §6.3.2).

---

# Session Handoff & Architecture Summary

## 1. Goal We Are Working Toward
The primary goal is to build an **ultra-clean, highly accurate, hallucination-free spiritual RAG & Knowledge Graph platform** (*AskMukthiGuru*) powered by:
- **Semantic Topic-Shift Chunking (`SemanticChunker`)**: Splitting documents at embedding cosine distance spikes rather than arbitrary character limits.
- **Automated LLM Transcript Proofreading (`TranscriptCorrector`)**: Contextual zero-shot proofreading of raw ASR audio captions *before* chunking or contextualization to eliminate homophone errors (*"eye consciousness"* $\rightarrow$ **"I-Consciousness"**, *"soul sink"* $\rightarrow$ **"Soul Sync"**).
- **Late Chunking & Contextual Enrichment**: Prepending Anthropic-style situating headers (`[Context: ...]`) and encoding full 8k document attention via BGE-M3 1024d vectors.
- **Deduplication & Quality Gate Enforcement**: Eliminating duplicate point IDs, machine output scaffolding, and ASR decoder loops.

---

## 2. Current State of Code
- **Quality Filter & Deduplication**: Fully operational (`select_clean`, `collapse_repeats` in `backend/services/text_quality_filter.py`). 40/40 tests passing.
- **Semantic Topic-Shift Chunker**: Implemented in `backend/ingest/semantic_chunker.py` and integrated into `ContextualReingestEngine._rechunk()`. Tests passing (2/2).
- **LLM Transcript Proofreader**: Integrated into `ContextualReingestEngine._reconstruct_full_text()` via `_correct_full_text()`. Passes `**kwargs` and supports both OpenRouter and local Ollama.
- **Qdrant Collection (`spiritual_wisdom_contextual`)**:
  - Truncated and re-ingested video `https://www.youtube.com/watch?v=mmpmX3-qfc4` end-to-end.
  - Successfully produced **6 clean, semantic topic chunks** (down from 14 fixed window splits), fully proofread with **"I-Consciousness"** and Anthropic context headers.
- **Test Suite**: All 49 unit tests across quality filters, semantic chunker, and contextual re-ingest are passing (`pytest`).

---

## 3. Files Actively Edited & Created
- `backend/ingest/semantic_chunker.py` **[NEW]**: Implements `SemanticChunker` with sentence embedding distance spikes and percentile thresholding.
- `backend/tests/test_semantic_chunker.py` **[NEW]**: Unit tests for `SemanticChunker`.
- `backend/ingest/contextual_reingest.py` **[MODIFY]**: Integrated `_correct_full_text()` (LLM proofreading) and updated `_rechunk()` to use `SemanticChunker`. Added `**kwargs` support to `_OpenRouterContextualizer.generate()` and `_LocalOllamaContextualizer.generate()`.
- `backend/services/doctrine_terms.py` **[MODIFY]**: Added `"I-Consciousness": ["Eye Consciousness", "Eye consciousness", "eye consciousness"]` to canonical term dictionary.
- `backend/services/text_quality_filter.py` **[MODIFY]**: Expanded `_ARTIFACT_PATTERNS` to catch meta-prompt analysis scaffolding.
- `lessons.md` **[MODIFY]**: Appended Aug 2, 2026 architectural learnings.

---

## 4. Everything Tried and Failed (With Root Cause Analysis)

### Attempt 1: Manual Term Glossary Addition (`doctrine_terms.py`)
- **What was tried**: Added `"I-Consciousness"` to `DEFAULT_DOCTRINE_TERMS` and ran in-place Qdrant payload updates.
- **Result**: Fixed the specific term `"Eye Consciousness"` in Qdrant, BUT failed to address the root problem.
- **Why it failed / limitation**: Playing "whack-a-mole". Static term lists miss un-cataloged ASR homophone errors (*"soul sink"*, *"winded child"*, *"uncrafted state"*) in future video transcripts.

### Attempt 2: Re-ingestion without LLM Proofreading Stage
- **What was tried**: Ran `ContextualReingestEngine` directly from `spiritual_wisdom` to `spiritual_wisdom_contextual`.
- **Result**: `ContextualChunkingService` (the LLM contextualizer) inherited raw `"Eye Consciousness"` from the source payload and repeated the error inside its generated `[Context: ...]` headers!
- **Why it failed**: Re-ingest reconstructed full text directly from un-proofread source payloads without passing text through an LLM proofreader *before* chunking and contextualization.

### Attempt 3: Wrapper Interface Signature Mismatch (`TypeError`)
- **What was tried**: Called `TranscriptCorrector` using `_OpenRouterContextualizer` inside `_correct_full_text()`.
- **Result**: Task failed with `TypeError: _OpenRouterContextualizer.generate() got an unexpected keyword argument 'temperature'`.
- **Why it failed**: `TranscriptCorrector` passed `temperature=0.0, operation="correction", is_structured=True`, but `_OpenRouterContextualizer.generate()` only accepted positional parameters (`system_prompt`, `user_prompt`).
- **Fix Applied**: Added `temperature: float = 0.3, **kwargs: Any` to `generate()` methods in `_OpenRouterContextualizer` and `_LocalOllamaContextualizer`.

---

## 5. What We Learnt & Results from Each Try

### Result 1: Fixed-Window vs. Semantic Topic-Shift Boundaries
- **Fixed Window (`BoundaryChunker`)**: Produced **14 chunks** for video `mmpmX3-qfc4`, cutting the opening King's fable mid-narrative across multiple chunks.
- **Semantic Topic-Shift (`SemanticChunker`)**: Sentence-level embedding distance spikes grouped the same video into **6 coherent semantic topic clusters**, keeping the full King's fable intact in Chunk 0.

### Result 2: Empirical Zero-Shot LLM Proofreader Performance
Ran `TranscriptCorrector` with **ZERO glossary terms injected** (`CLEAN_SYSTEM_PROMPT`) against raw ASR audio captions:
- **Input 1**: *"eye consciousness... preoccupation with oneself"*
  - **Output**: *"I-consciousness... preoccupation with oneself"* (Corrected zero-shot from context).
- **Input 2**: *"we did soul sink today and it brought deep peace"*
  - **Output**: *"We did Soul Sync today and it brought deep peace."* (Corrected zero-shot).
- **Input 3**: *"in an uncrafted state you experience profound clarity"*
  - **Output**: *"In an unclouded state, you experience profound clarity."* (Inferred "unclouded state" from clarity context).

---

## 6. Next Steps
1. **Full Corpus Contextual Re-Ingestion**: Run `ContextualReingestEngine` across all 391 source videos in `spiritual_wisdom` to populate `spiritual_wisdom_contextual` with clean, semantic topic chunks.
2. **Hierarchical Parent-Child Storage Expansion**: Update `services/qdrant/indexer.py` to store 256-token child vectors for search matching alongside 1024-token parent blocks for LLM generation.
3. **Qdrant Collection Swap**: Point `settings.qdrant_collection` to `spiritual_wisdom_contextual` in production after full ingest completion.

---

## 7. Full Evidences & Complete Verbatim Chunk Texts

### Evidence A: Unit Test Suite Output (`pytest`)
```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-8.4.2 -- backend/.venv/bin/python3
rootdir: /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend

tests/test_text_quality_filter.py .................................. [ 82%]
tests/test_semantic_chunker.py ..                                    [ 86%]
tests/test_contextual_reingest.py .......                            [100%]

======================== 49 passed, 1 skipped in 5.05s =========================
```

### Evidence B: Complete Verbatim Payload Texts for All 6 Re-Ingested Semantic Chunks (`spiritual_wisdom_contextual`)

#### **Chunk 0** (ID: `9ad187af-0a15-597e-a9fa-41a9c224c06e`)
```text
[Context: The speaker begins by highlighting a common paradox: people pursue things like money, relationships, and children to achieve happiness and security, but these pursuits often create the opposite experience. This introduction sets the stage for exploring a crisis in consciousness and the potential for a different way of being.]
Thank you, thank you. Philosophically, it might seem very funny. Think of it. Why do you make money? You make it so it will give you leisure, it'll give you freedom from anxiety, security, and ease. But the very act and idea of money gives you the opposite experience. So much of your anxiety, so much of your stress is in the act of making money and also not losing it. Why do you get into a relationship? So that relationships will give you comfort, will give you comfort, security, freedom from loneliness. But relationships are anything but this. So much of your experience of relationships is insecurity, suspicion, not wanting to be made use of, definitely loneliness, even while you are together. Why do you have children? So that you will be able to share the gift of love to another being, so that you can experience playfulness with a child, so you can feel whole. But parenting experience is anything but this. You are annoyed that they are demanding so much of your love and so much of your time. You feel inadequate. You are very upset that they are not grateful that you gave them life. What are you doing? Where are you running? Why does life feel so topsy-turvy? He is not happy. He thought his happiness lay in having children. He has them, yet he is not happy. Finally, he thinks his happiness lies in a happy beggar's shirt, but this time the beggar did not have a shirt. Are you not this King, seeking love? You set out to find a perfect partner. All your life, you're only engaged in elimination routes.
```

#### **Chunk 1** (ID: `b40b19e9-25ed-5669-84fc-35e7e885160f`)
```text
[Context: The speaker is illustrating how the pursuit of happiness through external means like relationships, wealth, and experiences often leads to dissatisfaction and anxiety. This section describes the resulting internal state of constant negation and disconnection, ultimately leading into a discussion of the contrasting state of Oneness Consciousness.]
All your life, you're only engaged in elimination routes. Not this person, not this person. Seeking Tranquility, you set out to the most beautiful places on Earth. You went out to see it. You keep wandering, dissatisfied, saying not this place, not this place. If you heard the inner dialogue that goes on within you, it is a constant negation of life. This person can't give me what I want. This career or this acquisition is not giving me what I want. We live with a noisy, dissatisfied, disconnected Consciousness that has no Delight. Remember, so many of your problems are not problems of circumstance. We can say that they are a crisis in consciousness. I want you to pause, stop running internally, stop running, and take this moment to be in the present. Sri Krishnaji and I have created Ekam as a center for enlightenment. It is created to birth a new generation ion with oneself. Let us now talk of the other end of the spectrum, which is Oneness Consciousness. Experiences of love, joy, peace, gratitude, compassion, endurance, courage. What is the nature of these states? It is interconnection and Oneness. Each of these states of Oneness Consciousness, these states include yourself and the other, yourself and nature, yourself and the Earth. In Oneness Consciousness, your emotions, your thinking, your decisions, your actions are all inclusive. They take into consideration your well-being as well as the well-being of the other. In Earth. In Oneness Consciousness, your emotions, your thinking, your decisions, your actions are all inclusive.
```

#### **Chunk 2** (ID: `f9872126-b3da-53f5-a586-eca0d59986ab`)
```text
[Context: The speaker is transitioning to discussing Oneness Consciousness, contrasting it with earlier observations about the paradoxical nature of seeking happiness through external means. This section elaborates on the characteristics and benefits of Oneness Consciousness, including its impact on personal growth, connection to the Divine, and ability to manifest positive outcomes.]
In Oneness Consciousness, your emotions, your thinking, your decisions, your actions are all inclusive. They take into consideration your well-being as well as the well-being of the other. In Oneness Consciousness, our sense of self increases, expands progressively until there is no circumference. You become limitless. You are infinite. As you move into states of Oneness Consciousness, everything grows in life. Connection with the Divine grows, Grace grows, wealth grows, love grows, your ability to impact the society and transform growth. You grow into an awareness that you're participating in something much greater than yourself, and, in fact, that you are the whole. fter a few months, and they were in a state of joyful surprise at the turn of events in their life. They said: "With only two sales people promoting their produce, the company shot back to growth miraculously." They were not even advertising heavily; they were just going about everything with dedication, along with the practice, living in a state of Oneness. This is a classical example of synchronicities: we are connected and in a Oneness state of consciousness. You should know that it is a field of magical action. From the state of Oneness Consciousness, you would experience immense power. As a leader, you would experience immense power to change a dysfunctional system. As an entrepreneur, you will have the power to create abundance and achieve success. As a student, you will have the power to manifest excellence.
```

#### **Chunk 3** (ID: `4daf80d8-738b-55d3-8514-8c89924d6524`)
```text
[Context: The speaker is describing the expansive power and benefits of living in a state of Oneness Consciousness, detailing how it can positively impact various aspects of life, from personal achievement to global transformation. Following a discussion of the power of Oneness, the speaker shifts focus to exploring the importance of maintaining a positive, beautiful state of being to unlock further potential.]
As a student, you will have the power to manifest excellence. As an athlete, you will enter a zone where you would transcend your body limitations. You can manifest every one of your dreams. When you live from Oneness Consciousness, you manifest a beautiful world, not only for yourself, but also for your loved ones, and that is the journey that happens at Mukthi. If you're a leader or an aspiring leader, flow with me today. Today, let us explore what needs to happen within you for A stressful state or a beautiful state? Remember, only when you live in a beautiful state, the universe becomes your friend and supports you in conquering your challenges and fulfilling your heartfelt intentions. You enter a magical zone in life. We have seen it again and again that only when you live in a beautiful state, your problems melt ice in the heat of the sun, and life becomes filled with magical coincidences. When you begin to break through your limitations, you enter a when you live in a beautiful state, your problems melt ice in the heat of the sun, and life becomes filled with magical coincidences. When you begin to break through your limitations, you enter a different realm. You become part of the magical flow of life where synchronicities unfold, which means the randomly moving universe will arrange itself in patterns to fulfill your heartfelt purpose: ideas, contacts, people you never expected will begin to flow into your life. But why stress at all? Let us explore. The world is accelerating at an incredible pace.
```

#### **Chunk 4** (ID: `00018844-72ad-5a02-8631-502f9d219f5d`)
```text
[Context: The speaker is discussing how living in a state of Oneness Consciousness can lead to positive transformation and abundance, contrasting it with a dissatisfied and disconnected state. This section explores the potential impact of Oneness on addressing global challenges like technological disruption and interpersonal relationships, emphasizing the importance of expanding one's sense of self.]
The world is accelerating at an incredible pace. As artificial intelligence takes over sphere after sphere of our existence, millions are left worrying about their future. Students are confused as career after career begins to look bleak and hopeless. Driverless cars, automated checkouts, Robo office assistants, chefless kitchens, What will happen if you address the problems in your intimate relationships by returning to Oneness? The miracle of affection will be born. Your heart will emerge out of its defensive shell and become open. You will bridge any distance that there may be between you and the other and create enduring and true love. Do what would happen if we addressed the problems of our Earth with a deep awareness of the interconnection of all the life forms? We will see the immense power of Mother Nature to return life to balance, where all life forms can coexist peacefully. If only leaders can have a fundamental shift in their consciousness towards Oneness, that Oneness will transform their loved ones, their families, their organizations, communities, and the world. Your life and contribution will become positive signatures on human consciousness that will continue to influence generations to come. Every one of you has a circumference that you call "mine": some friends, some family members, some colleagues, some race or religion or group. And every time your circumference shrinks, your magical connection with the universe tricks. Life becomes chaotic. So keep expanding the circumference consciously.
```

#### **Chunk 5** (ID: `54f4d552-c7a1-5fc5-847e-950e769b7f44`)
```text
[Context: The speaker is discussing Oneness Consciousness and its transformative power, emphasizing that expanding one's sense of self and inclusivity is key to experiencing its benefits. This chunk provides practical advice on how to consciously expand one's "circumference" and connect with others.]
So keep expanding the circumference consciously. Include individuals and groups you had excluded with your judgment earlier. At a physical level, pause more often. Look into people's eyes, smile with your lips, smile with your
```

---

# WIDE RESEARCH HARDENING RUNBOOK — 24 SCOPE-LOCKED CLUSTERS

**Baseline:** connected working tree at `6b5d8c4`; this runbook is authoritative for the approved hardening pass. Existing pre-prod warnings above remain in force. No cluster is complete until its acceptance criteria and evidence path are recorded here.

## Execution rules

Each cluster is restricted to its exact file allow-list. Do not make opportunistic edits outside the active cluster. Every change must have a failing or gap-demonstrating test where practical, a passing verification after the fix, and a rollback note. Status values are `NOT STARTED`, `IN PROGRESS`, `BLOCKED`, `VERIFIED`, or `DEFERRED`.

| # | Cluster and exact scope | Fix objective and acceptance criteria |
|---:|---|---|
| 1 | **Secrets:** `memory/test_credentials.md`; `supabase/snippets/Untitled query 625.sql`; `.gitignore`; CI secret-scan files | Remove credential artifacts, scan history, rotate any non-local values with approval. Acceptance: clean secret scan and no tracked credential-bearing fixtures. |
| 2 | **Dependencies/build:** `backend/requirements.txt`; `backend/requirements.lock`; `backend/pyproject.toml`; `package-lock.json`; Docker build manifests | Make lock authority explicit and builds reproducible. Acceptance: clean Python 3.12 install, `npm ci`, lock diff clean, SBOM/image scan passes. |
| 3 | **Configuration:** `backend/app/config.py`; `backend/.env.example`; `backend/app/constants.py`; config tests | Validate required production variables and remove silent unsafe defaults. Acceptance: invalid production config fails before serving traffic; test config remains usable. |
| 4 | **Auth/admin/CORS:** `backend/app/main.py`; `backend/routers/admin.py`; auth/dependency modules; relevant Supabase migrations/security tests | Enforce exact origins, admin/MFA boundaries, and disable test backdoors in production. Acceptance: cross-user and unauthorized-admin tests pass. |
| 5 | **Abuse/SSRF/uploads:** ingestion routes; URL/fetch helpers; middleware; upload validation tests | Bound redirects, DNS/IP targets, body size, file type, quotas, and ingestion concurrency. Acceptance: SSRF, oversized, malformed, and rate-limit tests pass. |
| 6 | **Pipeline contracts:** `backend/app/pipeline/pipeline_coordinator.py`; `backend/app/pipeline/stages/context.py`; `backend/app/pipeline/stages/__init__.py`; `backend/app/pipeline/stages/pipeline_builder.py`; pipeline tests | Make stage inputs/outputs explicit and deterministic. Acceptance: stage graph contract tests pass with no hidden required state. |
| 7 | **Fast route:** `backend/app/chat_engine.py`; `backend/app/orchestrator_utils.py`; route policy/config; fast-route tests | Make simple queries deterministic and cheap. Acceptance: no planner/HyDE/deep graph/expensive verifier on fast route; latency budget test passes. |
| 8 | **Standard retrieval:** `backend/rag/nodes/retrieval.py`; `backend/rag/nodes/generation.py`; `backend/rag/nodes/verification.py`; standard-route tests | Bound retrieval/rewrite/rerank work and preserve evidence. Acceptance: standard route returns grounded answer or abstains. |
| 9 | **Deep graph/comparison:** graph strategy modules; `backend/rag/nodes/graph_stage.py`; cross-teacher modules; deep-route tests | Isolate multi-hop work from interactive traffic and label teacher differences. Acceptance: deep route cannot starve fast/standard queues. |
| 10 | **LLM gateway/fallback:** `backend/services/llm*`; `backend/services/multi_provider_llm.py`; provider adapters; provider tests | Centralize timeouts, fallback, retry classification, and provider policy. Acceptance: 429/5xx/timeout/non-retryable behavior is deterministic. |
| 11 | **Rate limiting/coalescing:** `backend/app/coalescer.py`; Redis/cache/rate-limiter modules; concurrency tests | Use distributed single-flight and avoid sleeping while holding locks. Acceptance: concurrent identical requests coalesce without deadlock or stampede. |
| 12 | **Streaming/cancellation:** `backend/app/stream_orchestrator.py`; actual streaming route owner; SSE tests | Stream real model tokens, safe terminal events, and cancel upstream work on disconnect. Acceptance: TTFT and disconnect tests pass. |
| 13 | **TTFT/observability:** `backend/app/metrics.py`; timeline/tracing modules; `backend/app/chat_engine.py`; load tests | Record queue, retrieval, generation, first-token, and end-to-end timings. Acceptance: p50/p95/p99 evidence saved by route/cache state. |
| 14 | **Qdrant/fusion:** `backend/services/qdrant_service.py`; Qdrant config/adapters; collection/index tests | Use one typed hybrid retrieval contract and named-vector/index checks. Acceptance: fusion and collection dimension tests pass. |
| 15 | **Reranking/scores:** reranker service modules; `backend/rag/nodes/retrieval.py`; score tests | Bound candidates and normalize dense/sparse/graph/reranker scores. Acceptance: held-out fusion/rerank metrics improve without latency regression. |
| 16 | **Confidence/calibration:** `backend/services/confidence_scorer.py`; confidence schemas/routes; calibration assets/tests | Separate retrieval, grounding, authority, contradiction, safety, and answer confidence. Acceptance: held-out calibration report with ECE/Brier/coverage exists. |
| 17 | **Verification/citations:** `backend/rag/nodes/verification.py`; `backend/rag/nodes/generation.py`; citation services/schemas/tests | Require release/span provenance and safe abstention. Acceptance: no-context and contradictory-context tests cannot return high-confidence factual claims. |
| 18 | **YouTube/source acquisition:** `backend/ingest/youtube_loader.py`; acquisition helpers; transcript tests; Celery entrypoints | Bound provider cascade, retries, freshness, playlist concurrency, and partial failures. Acceptance: resumable playlist and DLQ tests pass. |
| 19 | **Document/media adapters:** `backend/ingest/image_loader.py`; OCR/transcription/parser modules; adapter tests; worker routing | Add source adapter contracts for PDF/book/HTML/audio/image without blocking chat workers. Acceptance: raw artifact and page/segment provenance survives parsing. |
| 20 | **Chunking/quality:** `backend/ingest/pipeline.py`; `backend/ingest/quality_gate.py`; adaptive/contextual modules/tests | Make UNKNOWN quality outcomes quarantine; guarantee deterministic chunk IDs and coverage. Acceptance: scorer outage never publishes candidate content. |
| 21 | **Index/release publication:** embedding service; persistence helpers; Celery ingestion tasks; release/checkpoint migrations; replay tests | Add immutable source releases, candidate namespaces, idempotent upserts, and atomic published pointer. Acceptance: failed reingest preserves last good release. |
| 22 | **Graph/ontology/provenance:** graph/LightRAG services; Neo4j projection modules; ontology schemas/migrations; graph replay tests | Make graph a replayable derived projection with teacher/tradition/source-release provenance. Acceptance: outbox replay rebuilds graph and prevents silent equivalence. |
| 23 | **Evaluation/telemetry:** `backend/benchmarks/ruthless_benchmark.py`; `backend/benchmarks/golden_eval.py`; question bank; telemetry/OTel; CI evaluation workflow | Replace fallback-perfect scoring with gold evidence-span/source-held-out evaluation. Acceptance: retrieval, groundedness, citation, safety, abstention, and confidence reports are versioned. |
| 24 | **Deployment/ops:** `backend/Dockerfile`; `backend/Dockerfile.railway`; `backend/docker-compose.yml`; `backend/start_railway.py`; Celery/Kubernetes/Railway manifests | Separate API and workers, remove dev mounts/default secrets, pin model cache, harden readiness, backups, restore, and memory limits. Acceptance: exact image builds, load/memory/rollback/restore evidence exists. |

## Final CRITICAL cluster — task #75: circuit breaker (execute last)

**Exact scope:** `backend/services/circuit_breaker.py`; `backend/app/constants.py`; `backend/app/container.py`; `backend/app/metrics.py`; the actual health/operator route owner (currently likely `backend/app/main.py`); the exact circuit-breaker test module; and only the minimum required integration/load-test file.

**Required fix:** verify and correct monotonic timing, closed/open/half-open transitions, concurrent half-open admission, provider-specific thresholds, retryable versus non-retryable failures, timeout classification, recovery timeout, reset semantics, metric accuracy, multi-worker behavior, and safe provider fallback. The operator reset must be authenticated, audited, rate-limited, and unavailable to ordinary users.

**Acceptance:** fake-clock unit tests; concurrent half-open tests; recovery/flapping tests; provider failover tests; metrics assertions; authenticated operator-control tests; and an integration test proving an open upstream circuit does not starve healthy routes. Task #75 cannot be marked complete until clusters 1–24 and the full regression matrix are green.

## Completion evidence

For each cluster, append status, commit or working-tree diff reference, test command, result, and residual risk below this section. Do not remove the existing pre-production warnings until the corresponding production verification is actually complete.

## Execution evidence — initial connected-computer pass

**Recorded:** 2026-08-14, working tree at `6b5d8c4` with pre-existing user changes preserved.

| Cluster | Status | Evidence | Residual risk |
|---:|---|---|---|
| 1 | PARTIAL | Removed tracked `memory/test_credentials.md` and `supabase/snippets/Untitled query 625.sql` from the worktree; quarantined review copies under `.tmp_release_evidence/quarantine/security`; local Gitleaks scan: no leaks found, 0 commits scanned. | OpenRouter key rotation and any historical-secret rewrite still require operator action and production confirmation. |
| 2 | IN PROGRESS | Repository uses `backend/requirements.lock` and `package-lock.json`; Python 3.12 backend venv is available. | Clean-install and image/SBOM evidence not yet run. |
| 3 | VERIFIED-LOCAL | Targeted config/security/auth collection ran with backend Python 3.12: 131 passed, 8 skipped, 1 warning, 1,651 deselected. | Production environment validation still requires Railway/staging variables. |
| 4 | VERIFIED-LOCAL | Same targeted suite covered auth/security/CORS-related paths; no local failures. | Staging OAuth/MFA and cross-tenant production probes remain required. |
| 5 | VERIFIED-LOCAL | Same targeted suite covered SSRF, edge-case, and rate-limit selections; no local failures. | External redirect/DNS rebinding and production WAF/quotas remain unverified. |

The first test command was intentionally rejected by the connected computer’s system Python 3.9.6 because the code uses Python 3.10+ union annotations. Re-running with the repository’s Python 3.12 virtual environment passed the targeted slice. This is an environment-contract finding, not a code failure.

### Cluster 20 evidence — quality gate fail-closed patch

**Status:** VERIFIED-LOCAL (partial cluster scope). `backend/ingest/quality_gate.py` now returns explicit `QUALITY_UNKNOWN:` reasons and score 0 for LLM timeout, provider failure, malformed JSON, and JSON parse errors. `DataQualityGate` refuses to pass an UNKNOWN result, so scorer outage cannot publish candidate doctrine. Added regression tests in `backend/tests/test_quality_gate.py`.

**Verification:** `backend/.venv/bin/pytest backend/tests/test_quality_gate.py -q --tb=short` → **10 passed**. Remaining cluster-20 work is release-level quarantine/publication atomicity, which is tracked under clusters 21–22.

### Clusters 6–17 evidence — request-path regression slice

**Status:** VERIFIED-LOCAL for the existing contract surface; performance acceptance remains open. The connected computer’s Python 3.12 environment ran the selected pipeline, streaming/SSE, retrieval, reranking, metrics, latency-adjacent, and coalescing tests: **175 passed, 3 skipped, 1 warning, 1,615 deselected**.

This proves the current stage/stream/retrieval contracts remain regression-green after the pre-existing wave-11 changes. It does **not** prove production TTFT, p95 queue delay, cancellation under real client disconnects, or ten-customer load; those require the phase-6 operational test profile.

### Clusters 18–22 evidence — ingestion and knowledge foundation

**Status:** VERIFIED-LOCAL for the exercised contract slices; production publication and replay drills remain open.

The connected computer ran the ingestion/YouTube/transcript/contextual/chunk/quality selection: **123 passed, 1 warning**; graph/ontology/Neo4j/LightRAG/cross-teacher/provenance selection: **135 passed, 1 warning**; and Qdrant/embedding/vector/source-version/checkpoint selection: **56 passed, 1 warning**. A follow-up ingestion-task/quality-gate/playlist/checkpoint selection after the new patches passed **85 tests, 1 warning**.

Two hardening changes are now present. First, `backend/ingest/quality_gate.py` treats scorer timeout, transport failure, and malformed JSON as `QUALITY_UNKNOWN` and refuses publication. Second, `backend/tasks/ingest_tasks.py` retries only transient `TimeoutError`, `ConnectionError`, `OSError`, and `httpx.HTTPError` instead of retrying every deterministic exception. This reduces duplicate partial writes and makes quality/schema failures visible to the job/DLQ path.

Remaining release-level proof is still required: candidate namespace publication, crash/retry idempotency, last-good-release preservation, graph outbox replay, and source-held-out retrieval evaluation.

### Clusters 23–24 evidence — evaluation and deployment slice

**Status:** VERIFIED-LOCAL for tests/build manifests; NOT VERIFIED for cloud load, memory, backup, and restore.

The evaluation/confidence/citation/hallucination selection passed **106 tests, 1 warning**. The full frontend suite passed **369 tests, 6 skipped** across 75 files after fixing a deployment-safety defect in `src/lib/backendUrl.ts`: the legacy `askmukthiguru.lovable.app` hostname had been allowed to resolve to production despite the tests and fail-closed policy requiring an empty backend URL. `npm run build` completed successfully, prerendering 17 routes. `docker compose -f backend/docker-compose.yml config --quiet` also passed.

The first full frontend run exposed two real failures; both now pass in the targeted `src/test/backendUrl.test.ts` run (**9/9**) and full suite. Remaining cluster-24 blockers are clean-install reproducibility, image/SBOM scanning, ten-customer load and RSS evidence, Railway two-replica cold-start, synthetic alert verification, and backup/restore drills.

## FINAL CRITICAL — task #75 circuit breaker evidence

**Status:** VERIFIED-LOCAL for the scoped implementation and regression contract.

`backend/services/circuit_breaker.py` now uses `time.monotonic()`, an `RLock`, atomic half-open probe reservation, explicit in-flight probe accounting, a metric-aware `reset()` method, and transition-safe state/stat reads. The previous race could admit more half-open probes than configured and wall-clock jumps could distort recovery. `backend/app/api/health.py` now exposes the operator reset as an authenticated `POST`, rate-limits repeated resets per operator, uses the breaker’s reset method rather than mutating private fields, and writes structured audit data.

Added `backend/tests/test_circuit_breaker.py` with fake-clock recovery, concurrent half-open admission, failed-probe reopening, reset clearing, authenticated admin control, and rate-limit tests: **4 passed**. Follow-up circuit/health/auth/streaming regressions passed **165 tests, 1 skipped, 1 warning**.

**Residual operational risk:** the operator-reset cooldown is process-local. A distributed Redis-backed reset lock should be added before multi-replica public deployment if operators need a strict global cooldown across workers. The endpoint is nevertheless authenticated, admin-only, POST-only, audited, and locally rate-limited in this pass.

## Final verification — connected computer

**Backend:** `backend/.venv/bin/pytest backend/tests -q -m 'not integration' --tb=short` → **1,760 passed, 24 skipped, 13 deselected, 1 warning** in 143.08 seconds. The first full run found one pre-existing cost-budget retry contract regression; the bounded failure-cooldown fix in `backend/services/cost_tracker.py` restored the contract and the rerun was clean.

**Frontend:** `npm test -- --run` → **369 passed, 6 skipped** across 75 files. `npm run build` → successful, with 17 prerendered routes. `docker compose -f backend/docker-compose.yml config --quiet` → successful. Targeted Python compilation for all task-75, quality-gate, ingestion-task, cost-tracker, and test files → successful. `git diff --check` → clean.

## Final go/no-go

| Readiness target | Decision | Reason |
|---|---|---|
| Internal review | GO | Documentation, scoped patches, targeted tests, full non-integration backend suite, frontend suite, build, and compose validation are green. |
| Controlled alpha | CONDITIONAL GO | Suitable only with operator monitoring, one-replica limits, strict quotas, and the unresolved production checklist kept visible. |
| Ten-customer public waitlist | CONDITIONAL / staging first | Requires Railway staging load, cold-start, memory, alert, OAuth, audio, and backup/restore evidence before inviting real users. |
| Unrestricted public production | NO-GO | OpenRouter key rotation/history review, contaminated graph rebuild, cloud load/SLO evidence, global multi-replica reset cooldown, and restore drill are not proven locally. |

No commit, push, deployment, credential rotation, production migration, or external secret mutation was performed. The working tree contains pre-existing user edits plus the scoped hardening changes and documentation from this pass; review and commit as one deliberate change set after inspecting the diff.

# TODO BACKLOG — COMPLETE THE THREE DELIVERABLES

**Purpose:** This backlog is the actionable completion list for all unresolved work identified in this conversation, in addition to the 24-cluster runbook above. A TODO is not complete when code exists; it is complete only when its acceptance evidence is linked here and the relevant production/staging gate passes.

| ID | Priority | Workstream and exact scope | Owner | Acceptance criteria / evidence |
|---|---|---|---|---|
| TODO-001 | P0 | Rotate the OpenRouter key exposed in the 2026-08-02 history/transcript; audit Git history and CI logs. Scope: provider secrets, GitHub secret store, Railway variables, `.env*`, transcripts. | Security/Ops | Key revoked and replaced; history scan clean or documented; no secret in reachable refs; evidence: secret-scan report and provider rotation receipt. |
| TODO-002 | P0 | Rebuild contaminated Neo4j/LightRAG stores. Scope: graph projection, `spiritual_wisdom` releases, LightRAG state, Neo4j indexes. | Ingestion/Graph | Per-source contamination audit complete; contaminated sources refetched or quarantined; graph rebuilt from clean release; evidence: contamination report, point counts, graph audit. |
| TODO-003 | P0 | Enforce teacher-domain rights on retrieval, not only writes. Scope: `backend/domain/spiritual_ontology.py`, ontology writer, retrieval/citation nodes, graph projection tests. | Retrieval/Compliance | Sadhguru/Amma Bhagavan/ISKCON remain reference-only and cannot be retrieved as licensed doctrine or first-person voice; cross-teacher comparison is explicitly labeled; tests cover mixed corpora. |
| TODO-004 | P0 | Finish candidate-release publication atomicity and replay safety. Scope: source-release migrations, ingestion checkpoints, Qdrant aliases/namespaces, graph outbox, Celery tasks. | Ingestion/Platform | Crash at every stage preserves last good release; retry is idempotent; one published-release pointer is atomic; replay produces identical IDs and no duplicate edges. |
| TODO-005 | P0 | Remove the Python-runtime ambiguity in deployment and CI. Scope: Dockerfiles, Railway startup, CI workflows, `backend/requirements.lock`, runtime documentation. | Platform | Clean Python 3.12 install is the only supported backend path; Python 3.9 fails with a clear message; Docker and CI use the pinned lock; clean-install evidence saved. |
| TODO-006 | P0 | Verify tenant and admin isolation against real staging Supabase/RLS. Scope: auth dependencies, admin routes, Supabase migrations, RLS E2E scripts. | Security | Cross-user reads/writes, admin-only routes, memory, notebooks, ingestion, and telemetry isolation pass with disposable users; users are deleted; evidence is a staging RLS report. |
| TODO-007 | P1 | Run Railway staging two-replica cold-start and load test. Scope: `railway.json`, `Dockerfile.railway`, `start_railway.py`, Locust profile, API/worker topology. | Platform/Perf | Two replicas start within 60 seconds, readiness is truthful, no init timeout, p50/p95/p99 TTFT and queue delay are recorded for ten-customer concurrency. |
| TODO-008 | P1 | Complete memory/RSS and SLO evidence. Scope: API, Celery, embedding, graph workers; Prometheus/OpenTelemetry metrics; alert rules. | Platform/Perf | RSS high-water, CPU, queue depth, provider latency, TTFT, error rate, and circuit state are measured under load; alert thresholds fire in staging. |
| TODO-009 | P1 | Verify synthetic alerts and on-call notification. Scope: `.github/workflows`, Railway monitoring, notification integration. | Ops | Deliberate staging failure produces one actionable alert and recovery notification; evidence includes timestamps and redacted notification output. |
| TODO-010 | P1 | Complete backup and restore drill. Scope: Supabase telemetry/source releases, Qdrant snapshots, Neo4j dump, Redis policy, object storage. | Ops | Restore into an isolated environment from documented backups; published release and citations remain consistent; measured RPO/RTO recorded. |
| TODO-011 | P1 | Build a real confidence calibration set. Scope: `confidence_scorer.py`, golden questions, evidence spans, verifier output, evaluation scripts. | Quality/Research | Human labels include answerability, supporting spans, contradiction, authority, and abstention; held-out ECE/Brier/reliability/coverage report exists; API exposes calibrated confidence without false precision. |
| TODO-012 | P1 | Expand evaluation coverage and remove the current coverage ceiling. Scope: `question_bank.py`, `golden_eval.py`, source-release fixtures. | Quality/Research | Golden questions reference loaded source releases across languages, teachers, practices, safety, contradiction, and no-context cases; source-held-out recall@k, groundedness, citation precision, and abstention are reported. |
| TODO-013 | P1 | Audit all 720 sources and finish clean/refetch split. Scope: `corpus_forensics.py`, YouTube loader, PDF/book/audio adapters, ingestion state. | Ingestion | Every source receives contamination verdict and origin status; ≤2% sources migrate, dirty sources refetch or quarantine, and no zero-point source is marked processed. |
| TODO-014 | P1 | Complete full clean corpus re-ingestion and derived-store rebuild. Scope: `contextual_reingest.py`, doctrine lexicon, semantic chunker, Qdrant, Neo4j, LightRAG, OKF compiler. | Ingestion/Graph | Raw source, corrected text, chunk, parent, citation, release, graph, and OKF counts reconcile; no mixed pooling; provenance is monotonic; post-ingest quality report is green. |
| TODO-015 | P1 | Close the 34-config-field cleanup. Scope: `backend/app/config.py`, all `KNOWN_EXTRA_DEAD` fields, docs, tests. | Backend | Every field is wired, removed, or explicitly classified with a test and owner; no undocumented production setting remains. |
| TODO-016 | P1 | Complete multilingual coverage audit and translations. Scope: i18n dictionaries, `t()` calls, language bundles, frontend tests. | Frontend/Content | bn, gu, ml, ur, or, pa, as, and sa fallback gaps are resolved or explicitly product-deferred; parity test and responsive language UI evidence pass. |
| TODO-017 | P1 | Complete OAuth, forgot-password, and audio production E2E. Scope: auth routes, Supabase OAuth, email redirect config, CDN audio, Playwright tests. | Frontend/Auth | Dedicated staging identities complete one redirect, reset email/link, session expiry, and CDN audio playback; secrets are CI-injected and redacted. |
| TODO-018 | P1 | Finish global distributed operator-reset cooldown. Scope: `backend/app/api/health.py`, Redis limiter/lock, circuit-breaker tests. | Platform/Security | Concurrent resets across two worker processes have one global rate-limit decision; Redis outage fails safely for this operator action; audit record is complete. |
| TODO-019 | P1 | Run provider failure and slow-p99 chaos tests. Scope: LLM gateway, Qdrant, embedding, web-search, circuit breaker, load tests. | Reliability | 429 is not treated as an outage unless policy says so; timeouts are classified; open circuits do not starve healthy routes; no flapping under normal p99 latency. |
| TODO-020 | P1 | Verify streaming TTFT and cancellation with real providers. Scope: stream orchestrator, provider gateways, frontend transport abort, SSE tests. | Perf/Frontend | First-token timestamp is real, not simulated; client disconnect cancels upstream work; no final-answer double emission; p95 TTFT target is met by route. |
| TODO-021 | P2 | Decide bounded adoption of Docling/Unstructured, Graphiti/Neo4j GraphRAG, Ragas/Phoenix, and vLLM/SGLang. Scope: research notes, dependency manifests, integration spikes. | Architecture | Each candidate has license, maintenance, memory, latency, migration, and rollback analysis; only benchmark-positive components are adopted behind flags. |
| TODO-022 | P2 | Add source-release-aware ontology expansion for future traditions. Scope: ontology schema, graph projection, rights registry, admin review UI. | Knowledge/Compliance | New teachers can be staged as reference-only, reviewed, licensed, and rolled back without cross-domain leakage; every claim retains source/release/span provenance. |
| TODO-023 | P2 | Add user-facing progressive-disclosure features. Scope: chat response schema, frontend chat cards, analytics. | Product/Frontend | Answers provide optional “why this answer,” source spans, confidence explanation, suggested follow-ups, practice next steps, and “tips” without bloating the default response. |
| TODO-024 | P2 | Build retention and waitlist features with measurable experiments. Scope: onboarding, waitlist, daily practice, saved answers, feedback, product analytics. | Product | Consent-respecting onboarding, one-click feedback, referral/waitlist loop, streak/practice reminders, and experiment guardrails are shipped with activation/retention metrics. |
| TODO-025 | P2 | Complete Expo companion scope decision. Scope: `mobile/expo`, auth storage, SSE, capabilities, practices/library. | Mobile | Either explicitly defer mobile with rationale or deliver secure auth, streaming, language selection, practice/library screens, and mobile E2E against staging. |
| TODO-026 | P2 | Clean release packaging and review. Scope: all changed files, `.tmp_release_evidence`, generated `dist`, untracked docs/tests. | Release Manager | Review diff, remove/quarantine only intended artifacts, run clean-install checks, create one deliberate commit, and push only after approval. |

## TODO execution order

Complete P0 items before inviting any external user. Complete TODO-007 through TODO-020 before moving from controlled alpha to ten-customer availability. P2 items may proceed in parallel only when they cannot alter evidence, retrieval rights, or the production request path. Every completed item must append its command, result, timestamp, and evidence path under the relevant cluster section.

## TODO PROGRAM PHASE 2 — P0 EXECUTION

**Status:** LOCAL P0 IMPLEMENTATION VERIFIED; external credential rotation, staging RLS, and production release publication remain gated on operator/cloud access.

The rights-read gate is explicit: CorpusScope supports required_rights_status; live retrieval scopes require licensed when settings.require_licensed_domain_reads is enabled; Qdrant filters on domain_rights_status; and returned documents preserve licensed_domain and domain_rights_status provenance. The rights/corpus/retrieval slice passed 14 tests.

Source-release safety now has database-level uniqueness in supabase/migrations/20260814080000_harden_source_release_atomicity.sql. Duplicate corpus/source/checksum registrations and multiple active releases are rejected; the migration intentionally fails on pre-existing duplicates rather than deleting history.

Task #75 operator reset now uses a Redis-backed distributed claim in production and fails closed when Redis is unavailable; local/test mode keeps a process-local fallback. Dedicated circuit-breaker tests pass 4/4.

A clean Python 3.12 environment installed backend/requirements.lock successfully and passed the rights/release smoke tests. Local auth/RLS/admin/tenant/service-role regressions passed 213 tests. Reachable-history audit found OpenRouter markers in 106 reachable commits and marker references in 24 tracked files; no provider rotation or history rewrite was attempted. TODO-001 remains BLOCKED pending operator key revocation/rotation and history decision.

**Remaining P0 gates:** disposable-user RLS isolation against staging Supabase; duplicate audit before applying the unique-index migration; clean candidate corpus rebuild before enabling the licensed-read gate against production data; and provider key rotation/revocation plus history decision.

## TODO PROGRAM PHASE 3 — CORPUS, GRAPH, ONTOLOGY, PROVENANCE

**Status:** MANIFEST AND LOCAL VALIDATION COMPLETE; candidate corpus/graph publication remains blocked pending rights-approved origins and staging stores.

Generated `.tmp_release_evidence/todo_program/phase3/reingest_manifest.json` from the measured forensic report: 720 sources classified as 439 MIGRATE, 49 MIGRATE_THEN_VERIFY, and 232 REFETCH_FROM_ORIGIN. The manifest is planning-only and sets publish_allowed=false for every source. Added backend/scripts/ops/build_reingest_manifest.py and its contract test.

Corpus-forensics, contextual re-ingestion, ontology, provenance, checkpoint, and source-release selections passed 52 tests. No live Qdrant/Neo4j/LightRAG delete, re-fetch, rebuild, or active-release swap was performed.

**Next controlled action:** obtain rights-approved origin/access, audit duplicate release rows, fetch/refetch into a candidate namespace, stamp domain rights and provenance, run held-out evaluation, rebuild graph/OKF/LightRAG, and activate only through the source-release registry.

## TODO PROGRAM PHASE 6 — FRONTEND, AUTH, LANGUAGE, AUDIO, MOBILE
**Status:** LOCAL FRONTEND AND MOBILE VERIFICATION COMPLETE; authenticated OAuth/password-reset/audio and real-device acceptance remain STAGING-GATED.

The frontend regression suite passed **369 tests across 75 files**, with 6 intentionally skipped tests. The Vite production build passed and prerendered **17 routes**. The build still reports expected large chunks for ChatPage and the shared vendor bundles; this is a performance follow-up, not a build failure. JSDOM emitted known navigation-not-implemented diagnostics during tests but the suite remained green.

The canonical public-domain helper no longer hardcodes the retired Lovable hostname. It now uses `VITE_PUBLIC_APP_URL`, falls back to the current HTTPS browser origin for previews, and uses `https://askmukthiguru.com` as the intended custom-domain fallback. `.env.example`, active deployment documentation, mobile release documentation, and store-listing URLs were aligned with the Vercel + Railway plan. Runtime backend routing continues to require an explicit `VITE_BACKEND_URL` on previews/native builds and only resolves the production Railway backend for exact allowlisted hosts.

The language surface was audited: the selector advertises English, Hinglish, and 21 Indic answer languages; 14 UI locale bundles are loaded lazily with English fallback; existing i18n parity, selector, translation, accessibility, and voice tests remain green. Mobile Expo TypeScript verification passed with `npx tsc --noEmit`; the companion app has a valid Expo 54 package contract but does not yet have a real-device release proof.

**Staging/device blockers:** verify Vercel environment variables and preview/prod redirect allowlists; complete one Google/OAuth redirect, one forgot-password email/link/reset, session expiry, and disallowed-domain test against disposable Supabase identities; verify CDN/Sarvam audio playback and browser fallback behavior; build and exercise Android/iOS binaries on physical devices; configure and test push credentials, deep links, privacy/support URLs, and store metadata. No OAuth login, password reset, audio upload/CDN mutation, push notification, or app-store submission was performed.

**Acceptance decision:** local frontend and type checks are green. Ten-customer onboarding remains **CONDITIONAL / staging first** until authenticated web E2E, audio playback, and physical-device checks are recorded.

**Evidence:** `.tmp_release_evidence/todo_program/phase6/`; `src/lib/domain.ts`; `docs/DEVELOPER_GUIDE.md`; `docs/MOBILE_RELEASE_RUNBOOK.md`; `backend/tests/test_production_env_preflight.py`.

## TODO PROGRAM PHASE 7 — OPEN-SOURCE ARCHITECTURE AND PRODUCT ADOPTION
**Status:** RESEARCH AND LOCAL FEATURE FLAG IMPLEMENTATION COMPLETE; benchmark spikes remain deferred until rights-approved corpus and funded staging/GPU capacity exist.

Added `docs/architecture/OPEN_SOURCE_ADOPTION_MATRIX.md` with current repository evidence, licenses, maturity, fit, guardrails, and a staged adoption order for Graphiti, Docling, Unstructured, Microsoft GraphRAG, Neo4j GraphRAG, Ragas, Phoenix, vLLM, and SGLang. The decision is deliberately non-disruptive: preserve the existing Qdrant + Neo4j + LangGraph source-release and rights contracts, then benchmark adapters in disposable namespaces. Graphiti is reserved for temporal context/user episodes, not doctrinal truth. Microsoft GraphRAG is treated as a research reference because its own repository states it is largely in maintenance mode. vLLM is the default future GPU-serving benchmark candidate, with SGLang as the measured alternative.

The user-facing adoption surfaces already present in the repository—confidence/support labeling, collapsed provenance/source links, suggested follow-ups, guidance-plan cards, memory provenance, and rotating teaching tips—now have explicit default-on Vite rollout flags in `src/lib/featureFlags.ts`: `VITE_ENABLE_WISDOM_TIPS`, `VITE_ENABLE_SUGGESTED_FOLLOWUPS`, and `VITE_ENABLE_RESPONSE_PROVENANCE`. The flags can be set false for a staged rollback without changing the backend contract. Added `src/test/featureFlags.test.ts`; both default-on and explicit false rollback cases passed.

**Research sources:** Graphiti [1], Docling [2], Unstructured [3], Microsoft GraphRAG [4], Neo4j GraphRAG [5], Ragas [6], Phoenix [7], vLLM [8], and SGLang [9] are linked in `docs/architecture/OPEN_SOURCE_ADOPTION_MATRIX.md`. The repository evidence was read from the official project pages, not search snippets alone.

**Acceptance decision:** no unmeasured third-party runtime dependency was added to the production path. Product features are reversible and covered locally. Architecture adoption remains **DEFERRED / benchmark-gated** until rights-approved golden data, isolated stores, and cloud/GPU capacity are available.

**Evidence:** `docs/architecture/OPEN_SOURCE_ADOPTION_MATRIX.md`; `src/lib/featureFlags.ts`; `src/test/featureFlags.test.ts`; `src/components/chat/ChatMessage.tsx`; `src/components/chat/ThinkingPills.tsx`.

## FINAL TODO RECONCILIATION — 2026-08-14

| ID | Status | Evidence / remaining gate |
|---|---|---|
| TODO-001 | BLOCKED | Reachable-history scan found OpenRouter markers in 106 commits / 24 tracked files; operator must revoke/rotate, decide history rewrite, and replace repository if required. |
| TODO-002 | BLOCKED | 720-source forensic audit and planning manifest exist; clean rights-approved Neo4j/LightRAG rebuild was not run. |
| TODO-003 | DONE | Rights status is enforced on retrieval/corpus scopes and provenance; mixed-corpus regression slice passed. Production corpus publication still depends on clean sources. |
| TODO-004 | BLOCKED | Idempotency and single-active-release migration added; duplicate-row audit and staging migration/application remain required. |
| TODO-005 | DONE | Python 3.12 lock install, compile checks, Railway explicit proxy gate, and runtime documentation verified. |
| TODO-006 | BLOCKED | Local auth/RLS/admin/tenant regressions passed; disposable-user isolation against staging Supabase was not possible without cloud access. |
| TODO-007 | BLOCKED | Railway topology and load profile reviewed; two-replica cold-start/TTFT/queue evidence requires staging. |
| TODO-008 | BLOCKED | Metrics and alert rules exist; RSS/CPU/queue/p99 SLO measurements under Railway load remain unproven. |
| TODO-009 | BLOCKED | Alert rules exist; synthetic notification and recovery delivery require configured staging integrations. |
| TODO-010 | BLOCKED | Qdrant/Neo4j/LightRAG backup helpers reviewed; isolated restore and RPO/RTO drill were not run. |
| TODO-011 | BLOCKED | Fail-safe uncalibrated calibrator and tests added; held-out human-labeled calibration artifact is still required. |
| TODO-012 | BLOCKED | Evaluation and retrieval-quality tests pass; source-held-out multilingual/teacher coverage report is still required. |
| TODO-013 | DONE | 720-source forensic report and deterministic migrate/refetch/quarantine manifest generated; no publication was authorized. |
| TODO-014 | BLOCKED | Full clean corpus, graph, LightRAG, and OKF rebuild awaits rights-approved origins and isolated stores. |
| TODO-015 | DONE | Config cleanup and production settings validation are covered by current code/tests and the deployment preflight. |
| TODO-016 | DONE | 14 UI locale bundles, English fallback, parity tests, and 22-language answer selector audited; unsupported UI chrome is explicitly English-fallback. |
| TODO-017 | BLOCKED | Auth/reset/audio flows are implemented and locally tested; disposable Supabase identities, CDN audio, and Playwright staging E2E remain. |
| TODO-018 | DONE | Redis-backed distributed operator reset claim, fail-closed Redis behavior, and circuit tests pass. |
| TODO-019 | BLOCKED | Local chaos/circuit tests pass; real provider/Qdrant slow-p99 and failure load evidence requires staging. |
| TODO-020 | BLOCKED | Real first-chunk TTFT metric and cancellation propagation are implemented/tested locally; real-provider p95 target remains unmeasured. |
| TODO-021 | DEFERRED | Open-source matrix and guarded rollout decisions are complete; benchmark-positive integration spikes await golden data/cloud/GPU capacity. |
| TODO-022 | DEFERRED | Rights-aware multi-teacher ontology/provenance foundations exist; admin review and live staged traditions await approved sources. |
| TODO-023 | DONE | Confidence/support, provenance, follow-ups, guidance, memory context, and wisdom tips are present; rollout flags and tests added. |
| TODO-024 | DEFERRED | Retention/waitlist experiment loop was not expanded in this hardening pass; product analytics and consent design remain next work. |
| TODO-025 | DEFERRED | Expo package typecheck passes and release runbook exists; secure native auth/SSE/practice screens and physical-device E2E remain future scope. |
| TODO-026 | DEFERRED | Working tree intentionally remains uncommitted for owner review; no commit, push, deployment, or destructive cleanup performed. |

### Final verification result

The final local matrix is green: backend non-integration **1,771 passed, 24 skipped, 13 deselected**; frontend **371 passed, 6 skipped** across 77 files; Vite build successful with **17 prerendered routes**; Expo TypeScript check passed; backend compilation passed; and `git diff --check` passed. Evidence is in `.tmp_release_evidence/todo_program/phase5/`, `.tmp_release_evidence/todo_program/phase6/`, and `.tmp_release_evidence/todo_program/phase8/final_verification.txt`.

### Release decision

**Internal review: GO. Controlled alpha: CONDITIONAL GO. Ten-customer waitlist: CONDITIONAL / staging first. Unrestricted public production: NO-GO.** The blocking items are external rather than hidden: credential rotation/history handling, staging RLS, rights-approved corpus rebuild, Railway load/memory/SLO/alert evidence, backup restore drill, real-provider TTFT, and authenticated OAuth/audio/device E2E. The owner must complete those gates before inviting paying or waitlisted customers beyond controlled testing.
