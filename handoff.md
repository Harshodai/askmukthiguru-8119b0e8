# AskMukthiGuru — Corpus Ingestion Handoff
**Date:** 2026-08-27 | **Status:** Ingestion STOPPED — bugs being fixed, ready to re-run after commit lands

---

## 1. What We're Trying to Do

Populate `spiritual_wisdom_contextual` (Qdrant, localhost:6333) with **487 teaching videos** from Krishnaji & Preethaji:

| Phase | Sources | Status |
|---|---|---|
| **MIGRATE** | 438 YouTube URLs | 🔄 Paused to fix bugs (~14 sources done) |
| **MIGRATE_THEN_VERIFY** | 49 URLs — 100% verified OK via subagent web search | 🔄 Combined with MIGRATE |
| **REFETCH** | 232 (needs fresh YT fetch, local corpus stale) | ⏳ Phase 2 — not started |

Input file: `/tmp/all_ingest_urls.txt` (487 URLs)

---

## 2. How Ingestion Works (Full Pipeline Per Video)

```
YouTube URL
    │
    ▼ fetch_transcript_hybrid()
    │   Tier 0 → transcripts/{vid}.md  (repo root, local, FASTEST — 469/487 present)
    │   Tier 1 → YouTube captions API
    │   Tier 2 → auto-generated captions
    │   Tier 3 → yt-dlp + Whisper (needs yt-dlp binary — NOT installed)
    ▼
DataQualityGate (score 0–100, threshold 65)
    │
    ▼ ContextualChunkingService
    │   LLM (gemini-3.6-flash via OpenRouter) enriches each chunk with context
    ▼
EmbeddingService (BAAI/bge-m3, 1024-dim)
    │
    ▼ QdrantService.upsert() → spiritual_wisdom_contextual   ← WORKING ✅
    │
    ├─▶ RaptorIndexer                  ← FIXED (threshold 8→3)
    │     cluster chunks → LLM summarize → embed → upsert RAPTOR nodes to Qdrant
    │
    ├─▶ LightRAGService.ainsert()      ← FIXED (was not wired to pipeline)
    │     entity+relationship extraction → lightrag_vdb_* Qdrant collections + Neo4j
    │
    ├─▶ write_extraction_to_neo4j      ← FIXED (neo4j_driver was None)
    │     ontology/entity nodes to Neo4j KG
    │
    └─▶ _okf_extract_for_video()       ← FIXED (asyncio.run crash)
          5-Node Transformation Arc extraction → OKF staging files
```

---

## 3. All Bugs Found + Root Causes + Fixes

### 🔴 BUG 1 (CRITICAL): Neo4j + LightRAG silently skipped
**Root cause:** `bulk_ingest_video.py` never passed `neo4j_driver` or `lightrag_service` to `IngestionPipeline`. Pipeline guards with `if self._lightrag:` → zero graph writes.
**Fix:** Wire `_neo4j_driver = neo4j.GraphDatabase.driver(...)` and `_lightrag_svc = LightRAGService()` then pass both to `IngestionPipeline(neo4j_driver=..., lightrag_service=...)`.

### 🔴 BUG 2 (CRITICAL): OKF `asyncio.run()` crashes every time
**Root cause:** `okf_extract_tasks.py:52` calls `asyncio.run(extract_okf(...))` but `bulk_ingest_video.py` already runs inside `asyncio.run()`. Python 3.10+ forbids nested `asyncio.run()`.
**Fix:** Run OKF in a `ThreadPoolExecutor(max_workers=1)` thread → gets its own fresh event loop.

### 🟡 BUG 3: RAPTOR never runs (threshold too high)
**Root cause:** `raptor_cluster_size=8` in config. Short discourses produce 3–6 chunks. 8 > 6 → RAPTOR always skips.
**Fix:** Set `pipeline._raptor._cluster_size = 3` after pipeline creation in `bulk_ingest_video.py`.

### 🟡 BUG 4: Staging queue DNS error (noisy)
**Root cause:** Pipeline tries to POST to `supabase-kong` (Docker-internal hostname). Host-side ingestion can't resolve it.
**Fix:** `os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")` before pipeline init.

### 🟡 BUG 5: Quality gate rejects valid transcripts
**Root cause:** `transcripts.json` was 96 days old (corrupted Devanagari), got used instead of clean local `.md` files because the transcript projection was to wrong directory initially.
**Fix:** Transcripts now at `transcripts/{vid}.md` (repo root, correct path) with fresh mtime.

### 🔵 BUG 6 (EXPECTED): yt-dlp not in PATH
**Impact:** Tier 3 transcription disabled. Only affects 18/487 sources missing local corpus. Tier 0+1 covers the rest.
**Fix:** Not blocking. Install `yt-dlp` if you want Tier 3, or just let those 18 fall through to YouTube API.

---

## 4. Infrastructure State

| Container | Status |
|---|---|
| `mukthiguru-backend` | ✅ healthy |
| `mukthiguru-qdrant` | ✅ healthy |
| `mukthiguru-neo4j` | ✅ healthy |
| `mukthiguru-redis` | ✅ healthy |
| `mukthiguru-supabase-db` | ✅ healthy |
| `mukthiguru-supabase-auth` | ✅ running (GoTrue booted, roles fixed) |
| `mukthiguru-supabase-rest` | ✅ running (PostgREST) |
| `mukthiguru-supabase-kong` | ⚠️ unhealthy health check (non-blocking) |

Supabase gateway at `http://localhost:54321` (Kong). Role passwords set manually via `psql -U supabase_admin -h localhost`.

---

## 5. CRITICAL: Touch Transcripts Before Every Run

The staleness guard (`PRE_EXTRACTED_MAX_AGE_SKIP = 30 days`) skips any `transcript.md` file older than 30 days. **Always touch before starting:**

```bash
find /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/transcripts/ -name "*.md" -exec touch {} +
echo "Touched $(ls transcripts/*.md | wc -l) files — ready to ingest"
```

---

## 6. How to Re-run After Fixes Land

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

# 1. Pull latest (fixes committed by subagent)
git pull origin main

# 2. Touch transcripts
find transcripts/ -name "*.md" -exec touch {} +

# 3. (Optional) Clear checkpoint to re-run all, or skip to resume
docker exec mukthiguru-redis redis-cli -a mukthiguru_redis_pass --no-auth-warning \
  DEL "ingestion_checkpoint:oneness"

# 4. Start ingestion
cd backend && nohup env \
  QDRANT_URL=http://localhost:6333 \
  QDRANT_COLLECTION=spiritual_wisdom_contextual \
  NEO4J_URI=bolt://localhost:7687 \
  NEO4J_PASSWORD=mukthiguru_neo4j_pass \
  REDIS_URL="redis://:mukthiguru_redis_pass@localhost:6379/0" \
  OPENROUTER_API_KEY=$(grep OPENROUTER_API_KEY .env | cut -d= -f2) \
  OPENROUTER_RPM_LIMIT=120 \
  EMBEDDING_BACKEND=onnx_int8 \
  RERANKER_BACKEND=onnx_int8 \
  LLM_PROVIDER=openrouter \
  SUPABASE_URL=http://localhost:54321 \
  .venv/bin/python3 -m scripts.ingestion.bulk_ingest_video \
    --input /tmp/all_ingest_urls.txt \
    --workers 4 \
  > /tmp/ingest_migrate.log 2>&1 &
echo $! > /tmp/ingest_migrate.pid

# 5. Caffeinate (prevent Mac sleep)
caffeinate -i -w $(cat /tmp/ingest_migrate.pid) &
echo $! > /tmp/caffeinate.pid

# 6. Monitor
tail -f /tmp/ingest_migrate.log | grep -E "✅|❌|Quality|RAPTOR|LightRAG|Neo4j|OKF|ETA"
```

### Expected healthy log output after all fixes:
```
Neo4j driver connected for ontology writes
LightRAG service ready for ingestion
RAPTOR cluster_size -> 3
[1/487] Found pre-extracted transcript in -0O6WmxU3pw.md!
Quality gate PASS: .../watch?v=... score=82/100
ContextualChunkingService: enriched 4/4 chunks
RAPTOR: building tree from 4 chunks...
RAPTOR Summaries: 2
LightRAG ainsert complete
Neo4j ontology write: OK
OKF 5-Node Arc extraction queued
✅ Success (180s) — Chunks: 4, RAPTOR Summaries: 2
```

---

## 7. Advanced Techniques Status

| Technique | Purpose | Status After Fixes |
|---|---|---|
| **Quantized BGE-M3 (ONNX INT8)** | 1024d multilingual dense embeddings with ~4x lower RAM (~550MB vs ~2.3GB) & 2x faster CPU passes | ✅ Enabled |
| **Quantized Reranker (ONNX INT8)** | Fast CPU cross-encoder reranking with ~80% lower RAM footprint | ✅ Enabled |
| **Scalar Quantization (Qdrant SQ INT8)** | In-RAM vector compression with full precision on-disk rescoring | ✅ Enabled |
| **Contextual chunking** | LLM enriches each chunk with discourse context | ✅ Working |
| **RAPTOR** | Hierarchical summary tree for multi-level retrieval | ✅ Fixed (threshold 8→3) |
| **LightRAG** | Entity/relationship graph + vector layer | ✅ Fixed (now wired) |
| **Neo4j KG** | Ontology nodes for structural reasoning | ✅ Fixed (driver now passed) |
| **OKF 5-Node Arcs** | Transformation arc extraction (spiritual pedagogy) | ✅ Fixed (asyncio crash) |
| **Quality gate (0–100)** | Rejects garbled/irrelevant transcripts | ✅ Working |
| **Redis checkpoint** | Idempotent resume across crashes/restarts | ✅ Working |
| **4 async workers** | `asyncio.Semaphore(4)` concurrency | ✅ Working |
| **OpenRouter gemini-3.6-flash** | LLM for contextual enrichment + quality scoring | ✅ Working |

---

## 8. ETA

| | Value |
|---|---|
| Sources remaining | ~484 (3 already in Qdrant) |
| Workers | 4 |
| Observed rate | ~4–5 sources/min with OpenRouter rate limit sleeps |
| **Estimated** | **~7–9 hours for full MIGRATE+MTV batch** |
| REFETCH (232) | Separate phase after MIGRATE completes |

---

## 9. REFETCH Phase (232 Sources — Later)

```bash
cat /tmp/refetch_urls.txt | wc -l  # 232 URLs

# Same command, different input:
--input /tmp/refetch_urls.txt
# These WILL hit YouTube API (no local transcripts)
# More rate limiting expected — may need --workers 2
```

---

## 10. Monitoring Commands

```bash
# Is ingestion running?
ps aux | grep bulk_ingest | grep -v grep

# Live log
tail -f /tmp/ingest_migrate.log

# Qdrant point count (main corpus)
curl -s http://localhost:6333/collections/spiritual_wisdom_contextual \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Points:', d['result']['points_count'])"

# LightRAG entity count (graph layer)
curl -s http://localhost:6333/collections/lightrag_vdb_entities_baai_bge_m3_1024d \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('LightRAG entities:', d['result']['points_count'])"

# Neo4j node count (verify graph writes)
docker exec mukthiguru-neo4j cypher-shell -u neo4j -p mukthiguru_neo4j_pass \
  "MATCH (n) RETURN count(n) as nodes"

# How many sources have passed quality gate
grep -c "Quality gate PASS" /tmp/ingest_migrate.log

# How many fully succeeded
grep -c "✅ Success" /tmp/ingest_migrate.log

# How many rejected
grep -c "❌ Rejected" /tmp/ingest_migrate.log

# How many OKF arcs queued
grep -c "OKF 5-Node Arc extraction queued" /tmp/ingest_migrate.log
```

---

## 11. Git Commits (This Session)

```
279ffbe9    fix(ingestion): wire Neo4j and LightRAG, fix OKF asyncio loop collision, tune RAPTOR cluster size
9697adf2    docs: Aug 27 corpus ingestion handoff in AGENTS.md
7cbda3af    fix: use OpenRouterService in bulk_ingest_video (cloud-only mode)
8b24bacd    feat: add local Supabase Docker stack to docker-compose (profile: supabase)
aa2e0cf7    latency audit evidence, memory_service fix
```

---

## 12. Files Changed

| File | What Changed |
|---|---|
| `backend/scripts/ingestion/bulk_ingest_video.py` | OllamaService→OpenRouter; wire Neo4j+LightRAG; RAPTOR threshold 8→3; SUPABASE_URL host override; OpenRouter RPM elevated to 120 for bulk throughput |
| `backend/tasks/okf_extract_tasks.py` | Fix asyncio.run() nested loop crash via ThreadPoolExecutor |
| `memory/okf/compiled.json` | Compiled 1024-dim BGE-M3 index covering all 52 canonical teachings |
| `memory/okf/{sri-preethaji,sri-krishnaji,shared}/*.md` | 52 canonical OKF transformation arcs organized into teacher subdirectories |
| `backend/docker-compose.yml` | Added 5 Supabase services under `profiles: [supabase]` |
| `backend/supabase/kong.yml` | Kong declarative config (NEW) |
| `AGENTS.md` | Aug 27 ingestion invariants handoff |
| `handoff.md` | Complete handoff document |
| `transcripts/*.md` (469 files) | Projected from corpus/, gitignored |

---

## 13. Known Remaining Issues (Non-blocking)

1. **Kong unhealthy health check** — Reconfigure healthcheck path from `/` to `/status` in docker-compose.yml if needed.
2. **yt-dlp missing** — Install with `brew install yt-dlp` if you want Tier 3 audio transcription for the 18 missing corpus sources.
3. ~~**OKF auto-approve=False**~~ **STALE, corrected 2026-08-27**: `auto_approve` no longer exists as a working option. A later commit (`ec3c7d0a`) made `extract_okf_from_stores.py`'s auto-approve path raise `ValueError` unconditionally -- OKF staging now requires human review via `POST /api/admin/okf/review/{id}/approve` before anything reaches `compiled.json`. Do not attempt to re-enable `auto_approve=True`; that bypass was removed deliberately as a review-gate closure, not an oversight.
4. **Neo4j CE limitation** — Community Edition can't create separate databases; falls back to default DB. Not a bug — works fine.

---

## 14. SESSION UPDATE — 2026-08-27 (evening): the real ingestion-collapse root cause, plus reconciliation with a parallel session

Two full ingestion runs collapsed catastrophically after this handoff was written (5/487 and 5/586 succeeded, the rest rejected as spurious "not valid JSON"). Root-caused end to end rather than just retried with different parameters:

### The real bug: OpenRouterService's rate limiter was per-instance, not global
`services/openrouter_service.py`'s `_rpm_lock`/`_request_count`/`_window_start` were instance attributes. Ingestion creates ~53 separate `OpenRouterService()` instances across quality-gate scoring, contextual chunking, LightRAG, and OKF extraction -- each enforced `OPENROUTER_RPM_LIMIT` independently, so real aggregate traffic to OpenRouter ran far above whatever value was configured, no matter how low. This is why `OPENROUTER_RPM_LIMIT=120` (this handoff's own documented re-run command, item 12 above) AND the "safe" code default of `20` both tripped the OpenRouter circuit breaker within minutes. **Fixed**: rate-limit state is now class-level, shared across every instance -- one real counter enforces the configured limit process-wide. Regression test: `test_openrouter_rate_limit_is_shared_across_instances`.

### Downstream symptom: quality-gate silently mistook provider degradation for bad content
`ingest/quality_gate.py`'s `LLMQualityScorer` fed the circuit breaker's canned "graceful degradation" fallback text (`"I'm here and listening..."` / `"I'm currently experiencing a temporary connectivity issue..."`) straight to its JSON parser, which just logged a warning and returned `QUALITY_UNKNOWN: LLM response was not valid JSON` -- a *permanent* quarantine verdict for what was actually a *transient* provider hiccup. This is what turned "OpenRouter is briefly overloaded" into "370+ of 428 videos permanently rejected as low quality." **Fixed**: detects the two fixed fallback strings, retries up to 3x with backoff (breakers self-recover on a timer) before quarantining. If it still fails after retries, the reason is now honestly `"provider degraded (circuit breaker open) after retries"`, not a misleading JSON-parse message.

### A second, unrelated bug found via this same investigation
`SemanticCacheAdapter._redis_key` (`services/cache/semantic_adapter.py`) was missing `@staticmethod` but called as `self._redis_key(scope, point_id)` -- every real get/put/invalidate call raised `TypeError`, so the semantic cache never actually cached anything despite the 17 existing tests passing (none of them called the method through an instance, only via `inspect.signature()`). **Fixed independently by two parallel sessions this evening** (this one, and commit `7532263b`'s "P0-1") -- strong convergent confirmation it was real. That commit also added a hard startup assertion enforcing `SEMANTIC_CACHE_SIMILARITY >= 0.92`.

### A merge-time regression, found and fixed before push
Merging in `7532263b`'s P0-6 fix (a new blanket `no_context_short_circuit` fast-path in `generation.py`, added to skip expensive verification when there's genuinely nothing retrieved) broke the pre-existing non-doctrinal "reflective peace-meaning" fallback for Hindi queries about the meaning of peace -- the new early-return intercepted before that more specific handler could run, replacing a warm bounded reflection with a cold generic "couldn't find teachings" message. **Fixed**: excluded that one recognized content-gap case from the short-circuit.

### Also fixed this session
- Memory fact-key auto-derivation (`services/memory_service.py`) collapsed distinct multi-valued facts onto the same key (`"I have anxiety"` / `"I have a daughter"` both derived `user:possession`, so the second silently retired the first). Narrowed to single-valued relations only (`lives_in`, `occupation`).
- `test_corpus_hallucination_integrity.py`'s 5 hard assertions had been replaced with `pytest.skip()` when the 745-package corpus directory doesn't exist in this worktree. Rather than re-weaken vs re-break, symlinked `scripts/ingestion/corpus` to the primary checkout's real corpus (same fix already applied to `transcripts/`) -- the test now runs for real (5 passed, not skipped).
- `services/multi_provider_llm.py`'s hardcoded `google/gemini-flash-1.5-8b` (decommissioned, 404 on every call) was independently fixed by a parallel session's commit `5780e59b` with a different model choice than mine; kept theirs on merge since it's coordinated with `config.py`'s freshly-updated primary/fallback model pair.

### NEW finding, unresolved -- needs your attention, not a code fix
After all the above fixes landed and ingestion was relaunched clean (workers=4, RPM=20, zero circuit-breaker trips from the rate-limiter bug), OpenRouter started returning **`402 Payment Required`** on a meaningful fraction of calls (31+ occurrences observed). This is a billing/credits issue on the OpenRouter account, not a bug in this codebase -- every fix above is confirmed working correctly (the quality-gate now honestly reports `"provider degraded"` instead of masking a 402 as `"not valid JSON"`), but ingestion cannot complete at full throughput until the account has credit. Check the OpenRouter dashboard.

### Current ingestion state (as of this update)
Running detached (survives Claude session death: `~/mukthiguru-ingest-ops/run_ingest.sh` launched via `nohup`, `~/mukthiguru-ingest-ops/watchdog.sh` writes `status.tsv` every 60s and a `final_report.md` on completion, `caffeinate -i -s` prevents sleep). Input list rebuilt at `~/mukthiguru-ingest-ops/all_ingest_urls.txt` (586 URLs, reconstructed from local transcript frontmatter after a machine reboot wiped `/tmp/all_ingest_urls.txt` -- `/tmp` does not survive a macOS reboot, a durability lesson for any future long-running job: never put durable state there). Qdrant `spiritual_wisdom_contextual` and Neo4j both non-empty and growing, gated by real OpenRouter capacity/credits now, not a code bug.

### Operational lessons for the next session
- **Restart after editing code the running process already imported.** Python doesn't hot-reload; a fix landed in a file mid-run does nothing until the process is relaunched. Caught this exact mistake once this session -- fixed `quality_gate.py`, forgot to relaunch, watched the old bug run for another 25 minutes before noticing.
- **A reboot kills everything `caffeinate` doesn't protect against.** `caffeinate -i` (or `-i -s`) prevents sleep, not a reboot. `/tmp` is wiped on reboot; anything that must survive one belongs under `$HOME`.
- **Before trusting a "0 rejected reason" or "0 entries" number from any monitoring script you wrote this session, re-verify the path/scope it's actually reading** -- two false alarms this session (RAPTOR summaries, OKF staging count) turned out to be the watchdog script pointing at the wrong location, not real pipeline failures.

---

## 2026-08-29 update — provider switch, quarantine-detector false positive, launch-script bugs, swap leak

### Provider switch: Sarvam → OpenRouter
Sarvam Cloud confirmed out of credit (`insufficient_quota_error`, live probe). OpenRouter confirmed real balance (`/api/v1/auth/key` → `usage=$11.8`, no hard limit). `~/mukthiguru-ingest-ops/run_ingest.sh` now exports `LLM_PROVIDER=openrouter`, `OPENROUTER_RPM_LIMIT=120`. `bulk_ingest_video.py` already defaulted to OpenRouter — only the ops script env var needed changing.

### Quarantine-detector false positive — corpus was never actually contaminated
`backend/services/text_quality_filter.py`'s artifact regex had one bare-word alternative (`\bConclusion\b` with no markdown-shape anchor) added by an unrelated earlier commit (`1fbc8153`). It matched ordinary doctrine prose containing the word "conclusion" ("...this chunk is the closing blessing and conclusion of a guided meditation..."). Fixed in commit `d0b695a3` — restricted that alternative to the bold-markdown form only (the other three anchored forms were already precise). Full corpus rescanned after the fix: **1268/1268 clean, zero purges needed** — nothing was ever actually corrupted, the detector was wrong. Any process that started before `10:41:03` on 2026-08-29 was running the stale, over-broad regex — verify `ps -o lstart` against `git log` before trusting a live process reflects this fix.

### Two silent-launch-failure bugs found tonight, both fixed
1. **`setsid` does not exist on macOS.** Every relaunch attempt via `nohup setsid bash run_ingest.sh ... &` silently exited 1 before Python ever started — no log line, no error surfaced to the caller unless you specifically checked the shell's own exit code. **Fix:** launch via `screen -dmS ingest bash -c '...'` instead. `screen` is preinstalled on macOS; `setsid`/`tmux`/`dtach` are not.
2. **`run_ingest.sh` `cd`s into `backend/` before invoking Python, breaking a relative `--input` path.** Passing `--input all_ingest_urls.txt` (relative) fails silently (`EXIT=1`, "Please provide --input" in the log) once the script has already `cd`'d. **Fix:** always pass the absolute path: `/Users/harshodaikolluru/mukthiguru-ingest-ops/all_ingest_urls.txt`.

Correct launch command going forward:
```bash
cd ~/mukthiguru-ingest-ops
screen -dmS ingest bash -c 'caffeinate -i bash run_ingest.sh /Users/harshodaikolluru/mukthiguru-ingest-ops/all_ingest_urls.txt <WORKERS> /Users/harshodaikolluru/mukthiguru-ingest-ops/ingest_full.log "--disable-okf"'
screen -ls   # confirms the "ingest" session; screen -r ingest to attach, Ctrl-A D to detach
```

### Swap climbs steadily regardless of worker count — looks like a per-video leak, not a worker-count problem
- workers=4: swap climbed 9.4GB→13.7GB (10GB→14GB total, macOS auto-grew the swapfile) over ~15 minutes, free RAM dropped to ~73MB. Killed manually before OOM.
- Relaunched at workers=2 (PID under `screen -dmS ingest`, started ~11:57): swap climbed again, 9.2GB→12.8GB (10GB→14GB total) over ~20 minutes — same trend, just slower.
- **This means workers=2 is not a fix, only a mitigation.** Something per-video isn't being released (candidate suspects, not yet investigated: ONNX embedding/reranker session objects, the OpenRouter httpx client pool, LightRAG's per-call graph state, or RAPTOR's clustering buffers — nobody has profiled this yet).
- **Safety net added:** `~/mukthiguru-ingest-ops/watchdog.sh` now has a `swap_pct()` check in its 60s loop — at ≥90% swap used it sends `SIGTERM` to the ingester, logs to `swap_kill.flag`, and exits its own loop (which also triggers the existing final-report generation). This exists specifically because a Claude session is not guaranteed to be watching — the ingestion + watchdog run as OS-level `screen`/`nohup` processes independent of any Claude session, but until this fix, nothing would have stopped a swap-driven OOM if no one was watching.
- **If you're picking this up fresh:** check `~/mukthiguru-ingest-ops/swap_kill.flag` first — if it exists, the watchdog already killed a run for you. Redis checkpointing means it's always safe to just relaunch (already-ingested videos are skipped). Before relaunching, actually profile the leak rather than continuing to relaunch-and-hope — `py-spy dump`/`memory_profiler` on the ingester mid-run would tell you which stage is holding memory.

### Current live state (as of this update, ~12:2x on 2026-08-29)
- Ingestion: workers=2, `screen -dmS ingest`, log `~/mukthiguru-ingest-ops/ingest_full.log` (cumulative across all runs today — scope any progress/tally query with `awk '/HH:MM/,0'` using this run's start time, ~11:57).
- Watchdog: `nohup bash watchdog.sh` (now with the swap kill-switch above), writes `status.tsv` / `final_report.md` on exit.
- Qdrant `spiritual_wisdom_contextual`: ~3250 points and growing.
- OKF extraction and the book re-ingest (`ingest_four_sacred_secrets.py`) are still deferred, not yet re-scheduled in the current primary-checkout setup (the old `ingest_book_after.sh` referenced the now-deleted worktree and needs checking/rewriting before use, same as `run_ingest.sh`/`watchdog.sh` needed).
- Deferred by explicit user agreement: swap the LightRAG extraction classify model (currently `meta-llama/llama-3.1-8b-instruct`, producing non-fatal `"Complete delimiter can not be found"` warnings on structured-output parsing) to something stronger — only after this ingestion run completes.

### Operational lesson added tonight
**A background launch command's own exit code is signal, not noise — check it, don't just check whether *something* with a plausible name shows up in `pgrep` a few seconds later.** Both bugs above (`setsid` missing, relative path) produced an instant `Exit code 1` from the very shell call that launched them; that was dismissed twice as an unrelated race condition before being read literally. `pgrep` matching a short-lived wrapper process is not the same as the actual workload running.

### STOPPED — 2026-08-29T07:09:22Z, swap kill-switch fired
`~/mukthiguru-ingest-ops/swap_kill.flag` exists: `SWAP_KILL at 2026-08-29T07:09:22Z (swap 90%) -- terminating ingester to prevent OOM. Redis checkpoint preserved, safe to resume at lower workers.` Confirmed clean stop — neither `bulk_ingest_video` nor `watchdog.sh` running anymore. Progress at stop: `[117/586]` this run's position marker (cumulative log, not the true remaining count — many earlier entries were checkpoint-skipped instantly on relaunch).

### ROOT CAUSE FOUND AND FIXED — 2026-08-29, ~12:50 IST
`scripts/ingestion/bulk_ingest_video.py`'s `bulk_ingest_async()` built `tasks = [ingest_one(src, idx) for ...]` for **all** sources up front and awaited them with a single `asyncio.gather(*tasks, return_exceptions=True)`. `asyncio.gather` holds every task's return value until the *entire* gather resolves — so each video's full result dict (`{"source": ..., "status": "success", "result": res}`, where `res` includes `hyper_extract_result` — the LLM-extracted entities/relationships list) stayed referenced in memory for the rest of the 586-video run. This is why memory grew steadily with progress **independent of worker count** — workers=4 just filled it faster than workers=2, neither was the actual cause.

Confirmed nothing downstream ever reads this: `bulk_ingest_async()`'s `results` list only feeds the function's own final `{"status": "complete", "stats": stats, "results": results}` return value, and `__main__`'s `asyncio.run(bulk_ingest_async(...))` discards that return value entirely — the accumulation was pure waste.

**Fix:** the success-path return in `ingest_one()` now carries only `{"source": src, "status": "success", "chunks": chunks, "summaries": summaries}` — small ints, not the full `res` payload. Verified live: relaunched at workers=2, swap held flat at ~7.8GB across 6+ minutes / multiple videos (previously climbed ~200-300MB/min at the same worker count). No further `swap_kill.flag` trigger since the fix landed.

If swap starts climbing again after this fix, the leak has a second source — don't assume this fully explains it forever, re-check `status.tsv`'s trend over a longer window before ruling it settled.

### Self-healing supervisor added — 2026-08-29, ~12:59 IST
`~/mukthiguru-ingest-ops/supervisor.sh` now owns the launch/relaunch loop, fully OS-level (`nohup`), no Claude session dependency:
- Launches the ingester under `screen -dmS ingest`, arms `watchdog.sh` if not already running, waits for the screen session to end.
- On end: checks the log (scoped to this attempt's start timestamp) for `"BULK INGESTION RUN COMPLETED"` — if found, writes `supervisor_done.flag` and stops.
- If not complete: checks for `swap_kill.flag` (swap-kill death) → waits 120s to let memory actually drain before retrying; any other death → waits 30s and retries.
- Caps at 15 attempts; if exhausted, writes `supervisor_gaveup.flag` — that's the one signal a human genuinely needs to look, everything else is self-recovering.
- Redis checkpointing (`IngestionCheckpoint`) makes every retry a clean resume — no duplicate work.

**To check status without a Claude session:** `tail ~/mukthiguru-ingest-ops/supervisor.log`, or check for `supervisor_done.flag` / `supervisor_gaveup.flag` in `~/mukthiguru-ingest-ops/`.
**To stop it deliberately:** `pkill -f supervisor.sh && screen -S ingest -X quit && pkill -f bulk_ingest_video` — killing just the screen session alone will get auto-relaunched by the supervisor, that's the point.
