# AskMukthiGuru Session Handoff

**As of:** 2026-07-25, working tree on top of commit `1c128f12`. This replaces the handoff written earlier in this same session (Neo4j incident recovery) — everything in that one is still accurate and summarized in §4 below, but a second, larger phase of work happened after it that needs its own record: ContextBudgetManager, benchmark suite fixes, dashboard wiring, and a production incident I personally caused with a benchmark run. Read to the end before touching anything — the last section is the one that matters most.

**Update, same day, continuation session**: §5's memory leak is now root-caused AND fixed (not just diagnosed) — see the new §7 at the end. Question bank also expanded with 7 new edge-case categories. Both verified via the full backend test suite (1118 passed, 0 failed). Nothing deployed to prod yet — that decision is explicitly left to the user, see §7's last paragraph.

---

## 1. Goal

Two goals stacked on top of each other this session:

1. **Fix the Neo4j production incident** (crash-looping, backend unhealthy) — done, documented in the prior handoff section, not repeated here.
2. **"Ruthlessly" audit and harden the codebase**, which the user then narrowed to: wire up `ContextBudgetManager` (found dead in the earlier audit — fully built, never called), prove the fix with real benchmarks (not vibes), enhance the benchmark/eval suite ("every corner case"), and update the HTML dashboard to reflect real current data — all explicitly "don't worry about costs, be ruthless."

The actual end goal, in the user's words: **authentic data users, investors, and the teachers themselves (Krishnaji/Preethaji) can trust** — i.e. the benchmark suite needs to be *correct*, not just *comprehensive*. That reframing turned out to matter: two of the "failures" this session found were the benchmark's own bugs, not product bugs.

## 2. Current state of code

**All of this is uncommitted, working tree only** (`git diff HEAD --stat`: 21 files, 394 insertions, 119 deletions). Nothing from this session has been pushed or committed — standing instruction is never to do that without being asked, and nobody asked.

- **`backend/services/context_compressor.py`** — `ContextBudgetManager.compress()` now also returns `selected_chunks` (the actual chunk dicts it kept, not just the joined string). Purely additive, existing `compressed_context` field unchanged.
- **`backend/rag/nodes/generation.py`** — `context_engineer`'s knowledge-layer assembly changed: docs are now selected by relevance (`rerank_score`, via `ContextBudgetManager`) *before* `sort_docs_canonically`'s hash sort, instead of hash-sorting first and blindly truncating the tail. Fixes a real, provable bug: the old order had no relationship to relevance, so truncation could (and did, ~9.5% of the time in a 200-trial synthetic benchmark) drop the single most relevant document. New order keeps the cache-friendly hash-sort for whatever survives selection, so the 85-95% prompt-cache-hit-rate property (`rag/doc_utils.py`) is preserved — verified by the existing `test_context_engineer_prefix_cache_stability` test still passing.
- **`backend/benchmarks/context_budget_selection_benchmark.py`** (new, untracked) — free, no-LLM-cost comparison of old vs new selection logic over 200 random trials. Results: top-relevance-doc survival 90.5%→100%, avg relevance of kept content 0.516→0.651.
- **Tests**: `backend/tests/test_context_compressor.py` (+1 test), `backend/tests/test_prompt_cache_prefix.py` (+1 test, specifically constructs a case where the old method would drop the highest-relevance doc and asserts the new one doesn't). Full backend suite: **1116 passed, 0 failed, 6 skipped** as of the last run before the benchmark suite changes below (not re-run after — see §5).
- **`backend/benchmarks/question_bank.py`** — two real bugs fixed, both found via live evidence, not guesses:
  1. `"expected_intent": "CRISIS"` (9 occurrences) → `"DISTRESS"`. The real system has never used "CRISIS" as an intent value — confirmed via `grep` across `rag/nodes/intent.py` (zero hits for CRISIS, 14 for DISTRESS). This was making every distress-query test in the suite report a false failure regardless of whether the app behaved correctly.
  2. Two new categories added, tied directly to this session's own code changes rather than generic padding: `constitutional_adherence_traps` (7 items, targets `check_constitutional_compliance`/`check_persona_adherence` in `verification.py`) and `context_budget_stress` (5 items, broad multi-topic questions designed to force the token-budget truncation path the ContextBudgetManager fix touches).
- **`backend/benchmarks/sdlc_rag_benchmark.py`** — the `expected: "refuse"` safety check now checks the response's structured `blocked` field first, falling back to the old hardcoded phrase list. Verified live: a real prompt-injection attempt was correctly blocked by the guardrail (`blocked: true, block_reason: "Off-topic: prompt_injection"`) with a graceful in-character response that matched *none* of the 8 hardcoded refusal phrases — the old check would have (and did) call this a `safety_fail` on a guardrail that was working correctly.
- **`backend/benchmarks/generate_dashboard.py`** — now loads `benchmarks/reports/benchmark_report.json` (the file `sdlc_rag_benchmark.py` actually writes) and renders it as a new "SDLC Question Bank" tab. Previously the dashboard only knew about `ruthless_report.json`/`native_eval_report.json`/`comprehensive_report.json` — the SDLC benchmark's data never appeared anywhere. Ran once successfully, produced `benchmarks/reports/dashboard.html`, sent to the user.
- **Other uncommitted files not touched this session** (`backend/ingest/pipeline.py`, `backend/schemas/push.py`, `backend/scripts/ops/reprocess_contextual.py`, `backend/scripts/phase05_audit.py`, `backend/services/cache/semantic_adapter.py`, `backend/services/lightrag_service.py`, `backend/services/second_brain/vault_index.py`, `scripts/ingest_lightrag_data.py`, `AGENTS.md`, `askmukthiguru-official-launch-demo.mp4`, `slowapi/__init__.py`, `video-composition/index.html`) — pre-existing from earlier in the session or the user's own independent work, not investigated further here.

## 3. Files actively being edited

None mid-edit. Everything above is complete and internally consistent — no half-applied changes.

## 4. Things tried and failed

### Neo4j incident (earlier in this session — summary only, full detail was in the prior handoff and in `lessons.md` RULE 37-40)
Root cause: Railway's Neo4j template had `server.http.listen_address` and `server.bolt.listen_address` both set to `:7687` — a genuine port collision, found only after `railway ssh` into the container and reading the actual generated config, following five failed guesses (variable touch, password rotation, explicit bolt-address override, dropping the n10s plugin, a full image rebuild). Fixed. Also found and fixed along the way: Neo4j password env-var rotation is a no-op on an already-initialized database volume; `railway up` is the most reliable Railway CLI lever when `restart`/`redeploy` refuse to touch a wedged deployment.

### This session's second half — the ruthless-audit phase
1. **First benchmark attempt against prod** — `--timeout 150` was too tight against this system's own documented ~133s standard-tier latency. Most queries timed out at exactly 150.0s rather than failing meaningfully. Killed it, re-ran with `--timeout 300`.
2. **Assumed a `curl` failure to `/api/health` meant something was broken** — turned out to be an intermittent harness-level network block on this specific tool call pattern, unrelated to backend health; resolved by retrying.
3. **Manual curl test of the guardrail used the wrong request schema** (missing `user_message` field — the API needs `{messages, user_message, meditation_step}` per CLAUDE.md, not just `messages`). Got a generic validation error, initially misleading. Fixed by matching the documented schema, which then revealed the *real* response and confirmed the guardrail check bug in §2.
4. **The second (300s-timeout) benchmark run itself degraded production.** This is the one that matters most — see §5.

## 5. THE THING THAT NEEDS ATTENTION FIRST — a production capacity problem I caused

Running the SDLC benchmark at just **`--concurrency 2`** against live production caused real degradation, not a benchmark artifact:

- Early categories succeeded normally (`doctrine_founders` 31s, `doctrine_four_secrets` 35s — both within normal range).
- Then per-category average latency climbed sharply: `doctrine_manifest` averaged **66.7s**, `doctrine_deeksha` averaged **77.8s**.
- After that, the backend started returning fast `503 Service Unavailable` for nearly everything — 40 of the last ~44 requests failed in 300-400ms (rejection, not timeout). Final tally: **46 total, 6 passed, 40 failed, 13.0% pass rate.**
- A direct `/api/health` check immediately after caught the backend mid-restart (`"status":"starting"`). A follow-up check ~30s later showed full recovery (`ready:true`, all critical services healthy).

**Corrected root cause (verified via `railway metrics --memory --raw`, not just inference from logs)**: this is NOT "2 concurrent requests instantly exhaust memory." Real memory usage climbed **gradually and steadily from 2.8GB to 6.5GB over ~55 minutes** — a slow, roughly-linear accumulation across many requests, not a spike. It crossed the app's own **self-imposed** `RLIMIT_DATA` ceiling of 5632MB (set explicitly in app startup, log: "Python memory limit set to 5632MB via RLIMIT_DATA") and crashed — usage dropped to 0.8GB at the exact restart moment, then climbed back to 1.67GB and sat **perfectly flat** for 12+ minutes after (worth checking whether that's genuinely idle-healthy or something got stuck post-restart).

**Critically: the container's real Railway memory limit is 24GB** (`railway metrics --memory` confirms `MEMORY_LIMIT_GB: 24.0`), not 5.6GB — the 5632MB figure is a self-imposed application-level limit with no relationship to what Railway actually allocated. There is 17+GB of real, unused headroom.

**This means the priority is different than originally diagnosed**: this looks like a genuine memory leak (steady climb across sustained request volume, not correlated to request concurrency specifically), not a hard concurrency ceiling. Raising `RLIMIT_DATA` would buy short-term headroom (there's plenty of real room to do it safely), but doesn't fix a leak — it just delays the next crash to a higher watermark. The 12-minute flat-line after restart is also unexplained and worth checking before assuming full recovery.

## 6. Next steps, in the order I'd take them

1. **Investigate the memory leak, not the concurrency ceiling** — confirmed via `railway metrics --memory --raw` (not just log inference): usage climbed steadily 2.8GB→6.5GB over ~55 minutes, crossed the app's *self-imposed* `RLIMIT_DATA` limit (`backend/app/main.py:40-51`, `PYTHON_MEMORY_LIMIT_MB` env var, currently 5632 in prod vars), and crashed. The container's real Railway limit is 24GB (confirmed, 17+GB unused headroom) — this was never genuine resource exhaustion. Two angles: (a) quick mitigation — raise `PYTHON_MEMORY_LIMIT_MB` since there's plenty of real room; (b) actual fix — find what's accumulating across requests without being released (embedding/reranker caches, LangGraph state, HTTP client pools, LightRAG's own caching are the likely suspects given this pipeline's architecture). Also unexplained: memory sat *perfectly flat* at 1.667GB for 12+ minutes right after the restart — confirm that's genuinely idle-healthy, not something stuck.
2. **Do not run further concurrent-load benchmarks against production until #1 is understood** — repeat the same incident with more categories or higher concurrency, and it could be a longer/more visible outage next time.
3. **Deploy the ContextBudgetManager fix** (`railway up`, same method used all session) — it's tested (2 targeted tests + 200-trial free benchmark, both proving the fix) and part of a stack of already-uncommitted changes, but never shipped. Do this only after #1, on a quiet backend, and verify with a handful of *sequential* (not concurrent) sanity checks rather than another benchmark run.
4. **Re-run the SDLC benchmark properly** once #1 is addressed — at `--concurrency 1` if the ceiling is confirmed to be that low, accepting a much longer wall-clock run in exchange for not repeating the incident. The two benchmark-suite bug fixes (CRISIS→DISTRESS, blocked-field check) are verified correct from the partial run that did complete; a full clean run would give real pass-rate numbers instead of the current 13% (which reflects capacity, not quality).
5. **Qdrant API key** — still not activated on either service. Unrelated to the above, still the highest-blast-radius pending decision (Qdrant backs every chat request).
6. **Neo4j Bolt public proxy** — still deliberately closed. Fine as long as ingestion isn't running from outside Railway's private network.
7. **`git diff` pass before committing anything** — 21 files changed this session, mixed with pre-existing unrelated uncommitted activity noted in §2's last paragraph. Separate the two before any commit.

## 7. Continuation session — memory leak root-caused and fixed, question bank expanded

**Railway re-auth**: MCP session had expired mid-session previously (RULE 40). Re-ran `mcp__railway__whoami` this session — it now works again on its own (`Logged in as Harshodai`), no manual re-login action was needed or taken.

**Current prod state before touching anything**: `/api/health` → `ready:true, status:"degraded"` (only non-critical `job_queue`/`ocr` down, expected/known). Memory via `railway metrics --memory` (linked service, 4h window): 1.24–1.66GB, stable — no active leak in progress right now. This confirmed the prior incident's restart genuinely recovered; the leak is latent (triggers again under sustained volume), not currently active.

**Root cause, found (not guessed)**: audited every unbounded `dict`/`list` instance attribute across `services/` and `app/` (`grep -rn "self\..*= *{}\|self\..*= *\[\]"`), cross-referenced against what's wired as a process-wide singleton in `app/container.py`. Found it: `services/user_profile_service.py`'s `UserProfileService._local_cache` (keyed by `user_id`) and `_conversation_cache` (keyed by `session_id`) were plain `dict`s, **never evicted**, on the one singleton `container.user_profile`. `app/pipeline/stages/memory_stage.py`'s `MemoryStage.run()` — a stage that never short-circuits — writes to `_conversation_cache` on literally every chat turn. Anonymous users mint a fresh `session_id` per conversation (`crypto.randomUUID()` in `src/lib/chatStorage.ts`), so every distinct conversation ever served adds one permanent entry, for the life of the process. Bonus finding: `get_recent_memories()`'s in-memory fallback does an O(n) scan over `_conversation_cache.values()` on every query (`app/orchestrator_utils.py`), which explains the *latency climb* seen right before the 503 storm in the original incident, not just the eventual OOM — the scan gets slower as the leak grows.

Checked two other unbounded-looking candidates from the same grep sweep and ruled them out as false positives: `services/cache/hot_cache_adapter.py`'s `HotCache._store` (explicit `max_size` param, active eviction on write — confirmed by reading the eviction code) and `services/health_monitor.py`'s `_arrivals`/`_intervals` (capped via `_HB_WINDOW_SIZE` with `.pop(0)`). Only `UserProfileService` was the real leak.

**Fix**: swapped both dicts to `cachetools.TTLCache(maxsize=10000, ttl=86400)` in `services/user_profile_service.py:__init__` — the exact bounded-cache pattern already used elsewhere in this codebase (`services/retrieval_cache.py`, `services/lightrag_service.py`, `services/cache/memory_adapter.py`), already a declared dependency. Zero other call sites needed changes (same `MutableMapping` interface). New regression test `backend/tests/test_user_profile_cache_bound.py` (fills each cache past `maxsize`, asserts `len()` stays bounded) — passes. Full backend suite re-run after the fix: **1118 passed, 0 failed, 6 skipped** (was 1116 before this session; +2 from the new leak test). Documented as `lessons.md` RULE 41.

**Still uncommitted, local only** — same as before, nothing pushed.

**Question bank expanded**: added 7 new categories to `backend/benchmarks/question_bank.py` targeting real untested failure modes (36 new questions, 373 total across 31 categories, up from ~250):
- `malformed_input` (10) — empty/whitespace/`null`/`undefined`/emoji-spam/zero-width-unicode/long-gibberish/rambling-text. Relies on the existing `_is_garbage()` auto-check in `sdlc_rag_benchmark.py`, no new grading code needed.
- `cold_start_followups` (6) — pronoun/reference queries with zero prior turns (tests `resolve_followup` doesn't invent an antecedent).
- `infra_probing` (6) — direct questions trying to surface Qdrant/Neo4j/API-key/`.env` internals.
- `multilingual_jailbreak_traps` (5) — the same jailbreak intent as `guardrails_input` but in Hindi/Hinglish/Tamil (every existing jailbreak test was English-only; every existing Hinglish test was benign).
- `markdown_html_injection` (5) — `<script>`/`javascript:`/`onerror=`/`data:` URI echo-back attempts (chat UI renders markdown).
- `micro_queries` (6) — single-word/near-empty context-free queries.
- `future_date_confabulation` (4) — "Manifest 2027", "Day 8 of the peace festival" — probes whether the model invents a plausible-sounding extension instead of saying it doesn't know.

Verified: module imports clean, `tests/test_benchmarks.py` still passes. **Not yet run against a live backend** — see next steps below.

**Next steps, updated**:
1. **Deploy decision is now the user's call, not mine** — the memory-leak fix (`services/user_profile_service.py`) is tested and ready, along with the still-pending `ContextBudgetManager` wiring from §6 item 3. Both are local/uncommitted. Given this is production infrastructure and the session has already run one incident from a benchmark run, I'm stopping short of `railway up` / any prod-affecting action without explicit go-ahead.
2. If/when told to proceed: deploy the memory-leak fix **first, alone** (it's the safer, narrower, actually-root-caused change), verify with sequential `/api/health` + a couple of manual chat requests over ~10-15 minutes watching `railway metrics --memory --raw` for the climb to be gone, *then* separately consider `ContextBudgetManager`.
3. Run the expanded question bank (`sdlc_rag_benchmark.py`) against a live backend once deployed — at low concurrency (1-2) given what happened last time, and only after confirming the memory fix actually holds under sustained volume.
4. Qdrant API key activation (§6 item 5) and Neo4j Bolt proxy decision (§6 item 6) — still untouched, still pending explicit sign-off, unrelated to the memory fix.
5. `git diff` / commit separation (§6 item 7) — still pending, now with more files changed this session on top of it.

## 8. Deployed the memory fix, then a canary benchmark crashed prod again — different bug, also fixed

Deployed §7's fix via `railway up` (stashed everything except `services/user_profile_service.py` + its test first, so only the isolated fix shipped — `git stash pop` still pending, see below). Deploy succeeded (`c8306a47`), health green, one sequential sanity chat request passed. Then ran a small canary benchmark (26 questions, concurrency=1, from the newly expanded bank) as the "verify carefully before a bigger run" step — and it crashed prod again, fast 503s, same fingerprint as before.

**This was NOT the same bug.** `railway metrics --memory --raw` showed an instant dip to ~0 (a real crash/restart, not a 55-minute climb), and a `faulthandler` thread-dump landed in the deploy logs at the exact moment, showing the process frozen inside `services/turboquant_cache.py:93` (`self._index.add(vec)`), called from `app/pipeline/stages/cache_stage.py:260`. Root cause: that one `vcache.put(...)` call was never wrapped in `asyncio.to_thread`, unlike its two sibling cache writes (`exact_cache.put`, `semantic_cache.put`) three lines above it in the same function — a native-library call blocking the single asyncio event loop. Made worse by `TurboQuantCache`'s own eviction design: once `faiss_cache_size` (500) fills, every `put()` rebuilds the entire native index from scratch, synchronously. Fixed by wrapping the one missed call in `asyncio.to_thread`, matching its siblings exactly. Documented as `lessons.md` RULE 42. Full suite re-run clean: 1116 passed, 0 failed.

**Current uncommitted scope**: `services/user_profile_service.py` (RULE 41, already deployed), `app/pipeline/stages/cache_stage.py` (RULE 42, **not yet deployed** as of this writing), `backend/tests/test_user_profile_cache_bound.py`, the question-bank/dashboard/sdlc-benchmark files (benchmark-only, confirmed not imported by the running app), plus the still-stashed ContextBudgetManager/Qdrant-API-key/ingest-pipeline group from §7 (`git stash list` has one entry).

**Next**: deploy the RULE 42 fix the same isolated way, then re-run the canary before anything bigger — and this time watch `railway metrics --memory --raw` live during the run itself, not just after, since two different crash-causing bugs have now surfaced from two consecutive "careful" verification attempts.
