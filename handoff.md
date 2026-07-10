# Handoff — Ruthless Audit + OKF Hardening — Pass 3

## 1. Goal

Two threads, one session.

**Thread A — the audit.** Verify *every* claim in `~/Downloads/report (2).md` ("AskMukthiGuru — The Ruthless Audit Report") against the current codebase, fix what is confirmed broken, and explicitly rule on what is stale. The report is third-party static analysis and a large fraction of it turned out to be wrong. Nothing was taken on faith — every verdict below came from reading the code, and every fix has a runnable test.

**Thread B — the OKF knowledge layer.** Make `memory/okf/` contain the teachings of Sri Preethaji & Sri Krishnaji **and nothing else**, and bring it up to the actual published standard rather than a homegrown one.

The decisive fact about OKF: it is **[Google Cloud's Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)** (June 2026), which formalises [Andrej Karpathy's LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Not "Oneness Knowledge Framework" — that name was my error in an earlier pass, now corrected in `CLAUDE.md`. The spec: a *bundle* is a directory of markdown files, one concept per file, whose **only required frontmatter field is `type`**; `index.md` and `log.md` are reserved; `title`/`description`/`resource`/`tags`/`timestamp` are recommended; cross-references are bundle-relative markdown links.

## 2. Current state of code

`HEAD` = `f1b68b34`. **Nothing committed this session** — all work sits in the working tree for review.

**Test status: `753 passed, 2 failed, 5 skipped`.** Both failures are pre-existing, confirmed by stashing every change and re-running on clean `HEAD`:
- `tests/test_openrouter.py::test_openrouter_provider_delegation`
- `tests/test_test_auth_strategy.py::TestTestAuthStrategyRegistration::test_not_registered_by_default` (a `BENCHMARK_SECRET` is set in the local `.env`)

Neither is caused by this session's work.

### Nine real bugs fixed (four the report never found)

| # | Bug | Where |
|---|---|---|
| 1 | **Cross-user cache leak.** `cache_key` is `(language, message)` — no `user_id`, no `tenant_id` — while `context_engineer` conditions the answer on the user's `memory_context`. That personalized answer was written to the process-wide hot cache and to Redis exact/semantic caches, then replayed to the next person asking the same question. Proven with a failing test before the fix. | `app/pipeline/stages/cache_stage.py` |
| 2 | **P90 vector cache could never hit.** `PipelineCoordinator` is constructed *inside* the request handler (`app/api/chat.py:176,230`), so `CacheUpdateStage` wrote entries into an object garbage-collected microseconds later; `_check_vector_cache` always saw `size == 0`. | `services/turboquant_cache.py`, `app/pipeline/pipeline_coordinator.py` |
| 3 | **OKF index absent in every container.** The index resolves to `/app/memory/okf/compiled.json`, but it lives at repo-root `memory/okf/` and both Dockerfiles only `COPY backend/ .`. `_load_okf_entries()` cached `[]` silently. `rag_okf_injection_enabled` defaults to `True`, so the "canonical knowledge layer" contributed **zero documents in production** while working fine on the laptop. | `backend/Dockerfile`, `backend/Dockerfile.railway`, `rag/nodes/retrieval.py` |
| 4 | **OKF staging gate was a no-op.** `OKFStore.list_entries()` used `rglob`, sweeping `staging/` (unreviewed, LLM-generated doctrine) straight into `compiled.json` on the next compile. | `services/memory/okf_store.py` |
| 5 | **Prompt leakage served as doctrine.** Four live `type: teaching` entries were machine artifacts. `sacred_secrets.md` literally contained *"The user wants me to analyze a spiritual teaching and list the top 3-5 distinct topics discussed."* `universal_intelligence.md` began mid-sentence and ended `_(Source: unknown)_`. `inner_truth.md` carried `> [RAPTOR Level: 1]`. Meanwhile `generation.py` rule 6 forbids the model from exposing exactly that text. | `memory/okf/` |
| 6 | **Uncitable doctrine.** Two entries had no `source` at all, so `format_final_answer` could not attribute them. | `services/okf_quality_filter.py` |
| 7 | **OKF paths broke inside the image.** `compiler.py` used `parents[3]` and the extractor used `_BACKEND.parent`; inside the image `backend/` *is* `/app`, so both resolved to `/memory/okf` while retrieval read `/app/memory/okf`. `POST /admin/okf/compile` wrote where nothing reads. | `services/memory/compiler.py`, `scripts/extract_okf_from_stores.py` |
| 8 | **Extractor duplicate drift.** Two copies existed. The one ingestion/Celery/admin actually import (`backend/scripts/`) had **lost its Ollama fallback** — its LLM chain ended at OpenRouter with `raise`. Under `LLM_PROVIDER=ollama`, OKF extraction threw. Root copy deleted (zero importers). | `backend/scripts/extract_okf_from_stores.py` |
| 9 | **OKF embedded titles only.** `compiler.py` embedded `[e["title"]]`, so a seeker asking *"why do I keep suffering?"* was matched against the string `"Inner Truth"`. Now embeds `title + description`. | `services/memory/compiler.py` |

Also closed: `knowledge_graph_query_enabled` (report Change 12) did not exist — LightRAG sat inside the retrieval `asyncio.gather`, so every FACTUAL/QUERY waited up to 3s on a ~5-edge graph. Flag added, default off. And `memory_lru_evictions_total` added — `_LRU_MAX_SIZE` carried the comment *"bump if eviction rate >5%"* with no metric to measure it.

### OKF bundle: 9 entries → 5 clean

Live (`memory/okf/*.md`), all with `type` ∈ `DOCTRINE_TYPES`, non-empty `source`, an OKF `description`, and 1024-dim embeddings:
`beautiful_state` · `beautiful_state_glossary` · `inner_truth_of_suffering` · `serene_mind_practice` · `three_question_meditation`

- **Quarantined** → `memory/okf/staging/` (never compiled): `inner_truth`, `meditation_practice`, `sacred_secrets`, `universal_intelligence`.
- **Relocated** → `docs/engineering-notes/`: `adaptive_chunking_principles`, `config_pruning_lessons`, `ingestion_patterns`, `retrieval_patterns` — RAG engineering notes sitting in the doctrine directory, excluded only by the accident of missing frontmatter.
- **Added**: `memory/okf/index.md` — OKF v0.1 reserved file, progressive disclosure, bundle-relative cross-links.

Three invariants now enforced at **one chokepoint**, `OKFStore.list_entries()` (used by both the compiler and the admin API):
1. `type` ∈ `{teaching, practice, glossary, qa, reflection}`
2. non-empty `source` (uncitable ⇒ not doctrine)
3. no extraction artifacts (`OKFQualityFilter` — existed, was dead code, now wired)

### Token optimization

The entire `boris` skill (~28k tokens) was pasted verbatim into **all three** CLAUDE.md files. It loads on demand via `/boris`. Removed: **99,628 → 13,227 tokens**, saving ~86k tokens *per session* — a bigger lever than every MCP schema combined. All real content preserved; recoverable via git.

Codebase-memory index refreshed: 8,763 nodes / 29,791 edges (the old 140k figure included `.venv`). Note it **excludes `scripts/`**, so the extractor is not in the graph.

## 3. Files actively being edited

None are mid-edit. Every change below is complete and verified.

**Modified (unstaged):**
`CLAUDE.md` · `backend/CLAUDE.md` · `src/CLAUDE.md` (boris strip) · `backend/Dockerfile` · `backend/Dockerfile.railway` · `backend/app/config.py` · `backend/app/metrics.py` · `backend/app/pipeline/pipeline_coordinator.py` · `backend/app/pipeline/stages/cache_stage.py` · `backend/rag/nodes/retrieval.py` · `backend/scripts/extract_okf_from_stores.py` · `backend/services/memory/compiler.py` · `backend/services/memory/okf_store.py` · `backend/services/memory_service_v2.py` · `backend/services/okf_quality_filter.py` · `backend/services/turboquant_cache.py` · `backend/tests/test_quality_gate.py`

**Renamed (staged):** 4 engineering notes → `docs/engineering-notes/`; 4 contaminated entries → `memory/okf/staging/`
**Deleted (staged):** `scripts/extract_okf_from_stores.py`
**New (untracked):** `memory/okf/index.md` · `backend/tests/test_cache_personalization_leak.py` · `test_vector_cache_shared.py` · `test_okf_index_available.py` · `test_okf_pipeline_integrity.py` · `test_okf_doctrine_only.py`

**Not mine:** `src/components/profile/MemoryManager.tsx` — a concurrent session is editing this. Do not attribute it here.

## 4. Everything tried and failed

- **I was wrong twice, both from grepping a facade instead of the implementation.** (a) I reported Qdrant quantization / prefetch+RRF / payload indexes as missing — they all exist in `services/qdrant/{client,searcher,mmr}.py`; `services/qdrant_service.py` is a thin delegating facade. (b) I reported doc-level ingestion dedup as missing — it exists at `ingest/pipeline.py:1752` (`check_source_exists` → `delete_by_source`); the call at `:1733` is a *separate* intra-batch MinHash pass. **Grep the implementation module, not the re-export.** The report itself made the same class of error — most of its "missing" features exist one directory down.
- **I mis-simulated `okf_store.py`'s path resolution**, omitting its `while` loop, and briefly concluded it pointed at a nonexistent directory. Reading the file corrected it — the file was right. Simulate by *executing*, not by transcribing.
- **`_llm_generate` doesn't exist** — the extractor's LLM function is `_call_llm`. An assertion failed on the wrong name before I checked.
- **Derived `description` from the body via heuristic first.** It produced fragments for `beautiful_state_glossary` (*"compassion, vitality, and passion."*) and `inner_truth`. Heuristics on doctrine text are exactly the wrong place to be lazy — replaced with explicit, hand-written `description:` frontmatter on all five entries, which is what the OKF spec recommends anyway. The heuristic survives only as a fallback.
- **Broke `test_quality_gate.py`** by making `source` mandatory in `validate_entry` — its fixture had none. Fixed the fixture (the test's intent was still right) and added two new cases for the uncitable and leaked paths.
- **Broke `test_okf_compiler.py`** by assuming `embed_text` always exists; it monkeypatches `_load_okf_entries`. Fixed the *compiler* (`e.get("embed_text") or e["title"]`), not the test — an external producer could legitimately omit it.
- **The report's most confident claims were its most wrong.** §3.1 prompt-cache poisoning, §3.2 alphabetical sort, §3.3 blocking `semantic_cache.get()`, §4.1 six dead nodes, §8.1 missing `k8s/nginx/nginx.conf` (it exists, 849 B), §8.2 no healthcheck grace period (`--start-period=420s`), §5.3 no memory compaction (`compact_memories()` at `memory_service.py:262`), §4.3 "accumulates the full response before streaming" (`streaming_generator.py` does `async for line in response.aiter_lines(): yield content` — true token streaming is live). Most of §7's UI gaps ship already: `ChatEmptyState.tsx`, `ThemeProvider`, `useSpeechRecognition`, `MeditationProgressIndicator`, `useWisdomTips`, `exportConversation`.
- **`gh` is not installed** on this machine, so GitHub repo visibility could not be confirmed when the git-history exposure came up. (Owner has since ruled that data test-only — no action.)
- **`detect_changes` / `index_status` on the codebase-memory MCP reject both the path and the project name they advertise.** Worked around with `index_repository(mode="moderate")`.
- **Working directory drifts.** The Bash tool persists `cd` across calls; an earlier `cd backend` silently broke later repo-root greps. Use absolute paths.

## 5. Next step

In priority order:

1. **Rebuild the image.** The backend does *not* bind-mount source, so a plain restart will not pick up the OKF `COPY`, the new config flag, or the cache fixes:
   ```bash
   cd backend && docker compose up -d --build backend
   ```

2. **Re-extract the four quarantined concepts.** *Sacred Secrets*, *Universal Intelligence*, *Inner Truth* and *Meditation Practice* are real teachings — the extractions were bad, not the concepts. With Qdrant/Neo4j up:
   ```bash
   cd backend
   .venv/bin/python -m scripts.extract_okf_from_stores --topic "sacred secrets" --dry-run
   .venv/bin/python -m scripts.extract_okf_from_stores --topic "sacred secrets"   # → staging/
   ```
   The new gate rejects anything containing prompt leakage, so review what lands in `staging/`, promote it, then `python -m scripts.okf_compile`. **`_OKF_CACHE` in `rag/nodes/retrieval.py` is per-process — recompiling requires a backend restart before retrieval sees the change.**

   Worth fixing at the source: the extraction prompt in `_build_okf_prompt` is what produced the leakage. Consider having `extract_okf` call `OKFQualityFilter.validate_entry()` *before writing* to `staging/`, so bad entries never hit disk. That is the producer-side gate; today only the consumer-side gate exists.

3. **Run the benchmarks.** `benchmarks/RUN_ME.sh` against the live stack. Three things should move: retrieval quality up (OKF actually loads in the container now, and matches on `title + description` instead of bare titles), P90 latency down (LightRAG off, vector cache warms across requests), OKF precision up (5 clean entries beat 9 with 4 poisoned).

4. **Decide on distress routing — the one confirmed bug left unfixed.** Two divergent routers exist: `rag/nodes/intent.py:route_by_intent` sends DISTRESS to the grounded path and is **dead code**; the wired `rag/graph_strategies.py:route_after_intent:60` bypasses retrieval. So the 36-line grounded branch in `handle_distress` (`intent.py:686-722`, with its own bespoke prompt) is unreachable in both graphs, and keyword-detected distress always gets the canned template.

   **Safety is not affected** — crisis hotlines are prepended inside `handle_distress` at `level >= SEVERE` (`intent.py:728-736`) from its own `async_assess_distress`, independent of route.

   **Why I did not fix it.** A correct fix is three coupled edits. `FastGraphStrategy` wires `route_after_intent` (`:385`) but has **no `route_after_grading`**, so rerouting there would strand a distressed user with no hotline — Fast must keep the bypass. In Standard, `route_after_grading` checks `intent == "DISTRESS"` only *inside* `if relevant:` and in the final `else`; with no relevant docs and rewrite budget left, a distressed user falls into `return "rewrite"` — the CRAG loop, up to `rag_max_rewrites` (3) times, 30–60s before seeing a crisis number. `DeepGraphStrategy` is an alias for Standard. This is a crisis path whose latency cannot be validated without the live stack. **Needs your sign-off, not a guess.**

5. **Benchmark `rag_skip_retrieval_expansions`** (report Change 8, currently `False`). The expansion LLM call is fired as `asyncio.create_task` at `retrieval.py:799` and awaited at `:883` *after* Qdrant+BM25 — so the report's "+1–3s serial" is overstated; it is partially overlapped. Flipping to `True` saves an LLM call but costs recall. Measure, don't guess.

6. **Known trade from bug #1.** The cache-write guard reduces hit rate for logged-in users: `/api/chat` requires auth, and any user with history has a non-empty `memory_context`, so they no longer populate the shared cache. Correctness over hit rate is the right call. If hit rate matters, the follow-up is to key personalized answers by `user_id` rather than skip them.

7. **Deployment items, still open (real, but decisions rather than bugs):** `docker-compose.prod.yml` gives the backend `2.0 cpus / 3G` with `WEB_CONCURRENCY=2`; with BGE-M3 (~1.4 GB) that is tight, and there are no replicas or autoscaling.

## 6. Method note for whoever picks this up

- Grep the **implementation**, not the facade. `services/qdrant_service.py` → `services/qdrant/`. I got two verdicts wrong this way before catching myself.
- Verify by **executing**, not by reading. Two confident path analyses were wrong until I ran them in `python -c`.
- The gate that matters is the **single chokepoint**. Cache leak, OKF staging, doctrine purity — each was one guard in one shared function, not N guards in N callers.
- Anything in `memory/okf/` is quoted to a seeker as the gurus' words. Treat approval as an editorial act.
