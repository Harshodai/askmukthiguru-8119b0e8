# Mukthi Guru — Ruthless Review, Self-Audited

**Purpose of this file:** a durable, model-agnostic work product. It survives a model switch (Fable → Sonnet 5) so you can keep executing regardless of which model is driving. Every claim carries a confidence rating and a "how to verify" note. Findings I could not verify at runtime are marked as such.

> **Note on existing audit docs:** this repo already has `ARCHITECTURE_AUDIT.md`, `ARCHITECTURE_AUDIT_CORRECTED.md`, `HARDCODING_AUDIT.md`, and `RUTHLESS_AUDIT_REPORT.md`. This review was written from a **fresh read of the code** (not those files), which is why you asked me to skip the `.md` docs. Reconcile/delete the stale ones — four overlapping audit files is its own tech debt.

**How to use with any model:** each fix in Part D has an exact `file:line`, a one-line change description, and a verification step. Hand a model one item at a time. Do the P0 block first — those are small, reversible diffs that fix correctness/safety.

**Overall confidence in this corrected review: 8/10.** High (9) on the static-code findings I verified by reading; medium (6) on runtime-behavior claims I could not execute (Redis-down path, middleware ordering, LocalAuthStrategy). Three findings in my first pass were overstated and are corrected below.

**Scope:** I read config, all pipeline stages, all three graph strategies, the RAG nodes, guardrails, auth, sanitization, coalescer, embedding service, docker-compose, and the frontend transport/config/admin. `backend/repos/` (624 MB vendored third-party) and benchmark/`.md` files were excluded per instruction.

---

## Part A — Self-audit: what I got wrong or overstated

I re-checked the shaky claims. Corrections:

| # | Original claim | Correction after re-verification | Confidence |
|---|---|---|---|
| 1c | "Citations: net output ≈ zero." | **Overstated.** The `citations[]` metadata list **does** survive to the frontend (chips). What's wasted is the *inline* `[Source:]` markers: the prompt demands them, `_cite_sentences` adds more (gated on the **phantom** flag `citation_by_sentence`), then `_clean_inline_citations` strips them from the prose. So it's wasted work + a phantom flag, **not** zero citations. | 8/10 |
| 2a | "Suicide → cold refusal, no helplines." | **Scoped too broadly.** A *pure* self-harm message ("I want to end my life") correctly hits the self-harm block with helplines. The bug is the **co-occurrence** of a self-harm message that **also mentions medication** — `_HARMFUL_PATTERNS` (`stop.*medication`) matches first and returns the medical refusal, skipping helplines. Real, but narrower than stated. | 7/10 |
| 2b | Example: "how do the teachings help heal depression" is blocked. | **Wrong example.** That string does **not** match the regex (`how to (cure\|heal…)`) — it's "how do…help heal", not "how to heal". A string that **does** match: "how to heal depression through these teachings". The over-block is real; my example was inaccurate. The emotional-wellness redirect ("stressful day at work") may be **intentional** product behavior, not a bug. | 6/10 |
| queue | "202/poll adds ≥2s to everything." | **Wrong for the main UX.** `ChatInterface` uses `sendMessageStreaming` (SSE). The 2s poll penalty applies to the **non-stream** path (`sendMessage`, `generateSummary`, title). Streaming has queue-pickup latency but not a flat +2s. | 7/10 |
| P90 cache | "P90 hybrid path is theater." | **Scope it:** only the per-request `TurboQuantCache` (FAISS mirror) is dead — built per `PipelineCoordinator`, which is per request. The container-level `hot_cache` and `semantic_cache` **do** persist across requests. | 7/10 |
| compose backdoor | "Recommended deployment ships the backdoor." | **Fact verified, inference scoped:** `backend/docker-compose.yml` **does** hardcode `IS_PRODUCTION=false` + `ENABLE_TEST_AUTH=true` (registers `TestAuthStrategy` → `X-Test-Key` = admin). It is the **dev/local** compose. The risk is real **if** used for the VPS deploy, not that it's labeled "production". | 9/10 fact / 5 inference |
| LocalAuthStrategy | "Dead — throws on every request." | **Unverified at runtime.** `fastapi_users.get_current_user(...)(request)` called without DI *looks* broken and is wrapped in try/except returning None, but I did not execute it. "Suspect", not confirmed. | 5/10 |
| Redis-down 500 | "Every request 500s if Redis dies." | **Medium.** `RedisCoalescer.__init__` is lazy, so `build_coalescer` won't fall back; the first `await self._redis.set()` would then raise. Plausible, not runtime-tested. | 6/10 |
| CORS on errors | "429/504 lack CORS headers." | **Medium.** Starlette runs later-added middleware as outermost; the timeout middleware (added after CORS) returns 504 before reaching the inner CORS layer. Subtle — didn't test. | 6/10 |
| Deep tier | "2 tiers, not 3." | **Refined:** graph **wiring** is byte-identical (verified: 47/47 lines, zero diff). But standard vs deep **do** differ at runtime via `query_tier` (temp 0.7 vs 0.9, budget 12k vs 16k, rerank top-k). So it's "duplicated wiring with param-driven divergence", not "identical behavior". | 9/10 wiring |

**Everything else re-verified as stated.** The load-bearing findings below are confirmed by reading the code this pass.

### Re-verified and CONFIRMED (highest value)

- **1a — system-prompt cache poisoning.** `session_id` is never placed in the graph config ([graph_stage.py:125](backend/app/pipeline/stages/graph_stage.py)), so the cache key at [generation.py:759](backend/rag/nodes/generation.py) collapses to `":default:en"` for all English/default-assistant traffic. The cached `system_prompt` **contains the retrieved KNOWLEDGE block** (layers branch line 698 and else branch line 753). On a cache hit ([generation.py:760](backend/rag/nodes/generation.py)) a later query is served an **earlier query's retrieved context** for up to 1 hour. **Verify:** log `cache_key` + first 80 chars of cached prompt; fire two different questions; watch the second reuse the first's context. **Confidence 9/10. Highest-value bug.**
- **1b — alphabetical doc sort before truncation.** `rag_cache_alignment_enabled` (default True) sorts `relevant_docs` by URL/chunk_index at [generation.py:504](backend/rag/nodes/generation.py) *before* the budget loop at line 550 drops the tail. Reranking order discarded. **Confidence 8/10.**
- **1d — distress-with-teachings dead.** On intent=DISTRESS, routing goes straight to `handle_distress` before `retrieve_documents`, so `relevant_docs` is empty and the RAG-grounded branch ([intent.py:686](backend/rag/nodes/intent.py)) never runs. **Confidence 8/10.**
- **Dead graph nodes** (0 `add_node` refs, verified): `check_contradiction`, `explain_retrieval`, `check_context_sufficiency`, `retrieve_single`, `merge_sub_results`, `route_sub_queries`. **9/10.**
- **Dead duplicate** `_prepare_user_memory` in [chat.py:67](backend/app/api/chat.py) — only reference is its own definition. **9/10.**
- **Blocking cache call on the event loop:** `semantic_cache.get` and the adapter's `get` are both **sync** (verified); [retrieval.py:750](backend/rag/nodes/retrieval.py) calls it bare in an async node, while the pipeline stage wraps the same call in `to_thread`. **8/10.**
- **`_okf_match` builds a fresh `EmbeddingService()` per query** ([retrieval.py:86](backend/rag/nodes/retrieval.py)) — reloads BGE-M3 in-process on every non-casual query with results. **8/10.**
- **Fabricated metrics:** `answer_relevancy/context_precision/context_recall` hardcoded `1.0` ([pipeline_coordinator.py:398](backend/app/pipeline/pipeline_coordinator.py)); fast tier hardcodes `faithfulness=1.0, confidence=8.0`; a similarity score is `observe()`d into a latency histogram (line 220). **8/10.**
- **httpx global monkey-patch at import time** ([config.py:668](backend/app/config.py)) wraps every process HTTP call, mutates shared client headers, recurses on 429 with no attempt cap. **7/10.**
- **Unauthenticated LLM endpoint** `POST /api/chat/title` ([chat.py:144](backend/app/api/chat.py)). **9/10.**
- **User data git-tracked:** `backend/data/feedback.jsonl`, `backend/data/lightrag/kv_store_llm_response_cache.json`. **9/10.**
- **Phantom config keys** (read via getattr, absent from `Settings`): `bm25_retrieval_enabled`, `citation_by_sentence`, `supabase_service_key`. **8/10.**

---

## Part B — Answers to the 5 questions (my judgment, labeled as judgment)

Based on the code + your memory note (provider=ollama-cloud approved, KG ≈ 5 edges). Opinions, not verified facts.

### Q1 — Real deployment target?
The 12-service compose (~10–12 GB: Neo4j 2G + GDS, Qdrant 3G, backend 3G, Celery 3G, + Redis/Jaeger/Prometheus/Grafana/GPTCache) and "Colab + $0" cannot both be the serving target. Realistic: **one modest always-on box (8–16 GB) for serving + Colab for batch ingestion.** Split compose into a **`serve` profile** (backend + qdrant + redis) and an **`ops` profile** (everything else, opt-in). Dropping Neo4j/GDS, GPTCache, Prometheus/Grafana from the serve path takes you from ~12 GB to ~4 GB.

### Q2 — Who is the benchmark for?
It currently measures the **string-stuffing layer** (keyword footers, factual-slot rewrites) and **fabricated faithfulness constants**, not retrieval quality. Removing them **will** lower reported scores — that's the point; the gap between "benchmark score" and "what a user reads" *is* the stuffing. Make the benchmark a team tool to improve **retrieval**, not a scoreboard. Yes, accept the real (lower) baseline.

### Q3 — TTFT target?
<3 s TTFT is achievable **only** on fast tier + cache hit. A cold standard/deep query on Sarvam cloud (India→cloud, 45 s LLM timeout, ≥4 serial LLM calls + a follow-up-suggestions call) **cannot** hit <3 s. Make **fast tier + streaming the product**; standard/deep the exception. Lean on your status-event streaming (genuinely good). Realistic: **fast <3 s, standard <8 s, deep best-effort.**

### Q4 — Is the KG earning its keep?
**No, not today.** ~5 edges (your memory note). Two databases, an ontology seeder, LightRAG init, per-query graph hops, an 8 s timeout, and a failure surface (`lightrag_degraded`, neo4j retries) for negative ROI. **Feature-flag LightRAG/Neo4j off in the serve path.** Keep ingestion-time entity extraction only if it enriches Qdrant metadata. Revisit at >1,000 edges **and** a measured retrieval lift.

### Q5 — One memory system or three?
**One writer.** Today a turn can run `MemoryStage` (v2), `user_profile.save_conversation_memory`, `episodic_memory_service.log_episode`, **and** frontend `queueMemoryExtraction` → Supabase edge function. 3–4 writers → races + double LLM cost. Keep **MemoryServiceV2** as the single writer, after the output guardrail. Delete the frontend Supabase extraction; fold episodic into v2 or drop it.

---

## Part C — What we both missed (new this pass)

1. **Dead length guard + silent truncation.** `ChatRequest.user_message` allows `max_length=10000` ([schemas.py:29](backend/app/schemas.py)), but `sanitize_user_input` truncates to **2000** ([chat.py:198](backend/app/api/chat.py)), and only *then* does the orchestrator check `len > 2000` ([orchestrator.py:61](backend/app/orchestrator.py)) — which can now never fire. Messages 2000–10000 chars are **silently truncated**; the "too long" 400 is dead code. Confidence 7/10.
2. **Sanitization scope gap** (reinforces 2c): `sanitize_user_input` is applied to `user_message` only, never to history/`system`-role messages, which still flow into the generation prompt. 7/10.
3. **Five overlapping telemetry systems:** OpenTelemetry/Jaeger + Prometheus + Grafana + Supabase sink + custom `telemetry_db` + `trace_dashboard`. Consolidate.
4. **No test covers the cross-stage bugs.** 693 backend tests collect (ran a subset, pass); frontend **218 pass / 2 fail** on main (not a gate). None of the P0 bugs are unit-testable in isolation — add 3 integration tests (Part D item 14).

---

## Part D — The plan (execute top-down; each item small + reversible)

### P0 — correctness & safety (do first)
1. **Delete the system-prompt cache** ([generation.py:758–768](backend/rag/nodes/generation.py)). *Verify:* two different questions, second no longer reuses first's context.
2. **Reorder guardrails:** move `self_harm` above `_HARMFUL_PATTERNS`; remove `medication`/`lithium`/`bipolar` from the pre-empting hard-block; remove `you are a (?!spiritual)`. *Verify:* "stop my medication and end my life" returns helplines.
3. **`_okf_match` → use `_services._embedder`** ([retrieval.py:86](backend/rag/nodes/retrieval.py)). One line; removes a per-query model reload.
4. **Remove the alphabetical sort** ([generation.py:504](backend/rag/nodes/generation.py)) or apply it only *after* budget selection.
5. **Validate `MessagePayload.role`** to `{user,assistant}` ([schemas.py:13](backend/app/schemas.py)); drop/guardrail client `system` messages.
6. **Compose:** remove `ENABLE_TEST_AUTH=true`/`IS_PRODUCTION=false`; give benchmarks a dedicated `benchmark_secret`.
7. **`git rm --cached backend/data/*`** + gitignore.
8. **Move `MemoryStage` after `OutputGuardrailStage`** ([pipeline_builder.py:44](backend/app/pipeline/stages/pipeline_builder.py)).
9. **Add auth to `POST /api/chat/title`** ([chat.py:144](backend/app/api/chat.py)).

### P1 — latency + honesty
10. **One citation mechanism.** Keep gateway-native or plain `citations[]`; delete keyword footers (`_ensure_keywords_in_answer`) + factual-slot rewrites (`apply_factual_slots`).
11. **Cut the follow-up-suggestions LLM call** ([generation.py:1560](backend/rag/nodes/generation.py)); let hot cache serve CASUAL ([cache_stage.py:68](backend/app/pipeline/stages/cache_stage.py)); make streaming the only interactive path.
12. **Fix coalescers:** one instance, user+session-scoped keys, no `json.dumps(dataclass)`, real in-memory fallback when Redis is down.
13. **Default `rag_context_compression_enabled=False`**; measure before re-enabling.
14. **Real metrics or none:** delete hardcoded `1.0`s ([pipeline_coordinator.py:398](backend/app/pipeline/pipeline_coordinator.py)). Add 3 integration tests: prompt-cache isolation; self-harm+medication → helplines; coalescer follower returns valid result.

### P2 — structural (delete to reduce surface)
15. Delete: Deep strategy (alias to standard), the 6 dead nodes, ~45 lines of unreachable code after `return "standard"` ([orchestrator_utils.py:254](backend/app/orchestrator_utils.py)), the duplicate `_prepare_user_memory`, the httpx monkey-patch (move rotation into the one provider client).
16. Collapse providers (7 → 1–2) and caches (7 → hot + semantic). Remove `backend/repos/` (624 MB) from the working tree; pin via `requirements.txt`.
17. Split compose into `serve`/`ops` (Q1); feature-flag Neo4j/LightRAG off (Q4); one memory writer (Q5).

---

## Part E — Advanced techniques + open-source that adds real value

**Legend:** ✓ = URL appeared in my July 2026 web search; ~ = canonical repo I'm confident exists but did **not** open this session (verify before depending). I did not invent exact URLs.

1. **Upgrade the reranker to `BAAI/bge-reranker-v2-m3`.** You serve Indic languages but rerank with `cross-encoder/ms-marco-MiniLM-L-6-v2` (English-centric). bge-reranker-v2-m3 is multilingual, ~278M, CPU-viable, and you **already depend on `FlagEmbedding`** (you load BGE-M3 through it) — a config + model swap, **zero new dependency**. +5–15 NDCG@10 reported. Repo `~ github.com/FlagOpen/FlagEmbedding` (verified by your own `BGEM3FlagModel` import); model on HF under `BAAI`. Context: [Best Rerankers for RAG 2026](https://futureagi.com/blog/best-rerankers-for-rag-2026/), [BSWEN comparison](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/) ✓
2. **Keep LettuceDetect — right call.** MIT, ModernBERT, token-level, ~30× smaller than the best prompt-based detectors. Make it the **only** verification layer (CoVe/self-consistency already off — good). [Paper (arXiv 2502.17125)](https://arxiv.org/abs/2502.17125), [HF write-up](https://huggingface.co/blog/adaamko/lettucedetect) ✓. Repo `~ github.com/KRLabsOrg/LettuceDetect`.
3. **Replace the 200-line regex guardrail with `Llama Guard 3 1B`.** The ordering bug (P0-2) is exactly what a small classifier avoids. Meta open-weight, input+output labels, CPU/small-GPU. Keep a thin regex only for the spiritual allow-list. [DeepInspect: OSS guardrails](https://www.deepinspect.ai/blog/open-source-llm-guardrails), [Best AI guardrails 2026](https://generalanalysis.com/guides/best-ai-guardrails) ✓
4. **`promptfoo` for adversarial/red-team testing** (21k★, 40+ adversarial plugins, YAML-in-repo, local). Would have **caught the guardrail ordering bug** automatically; replaces the safety side of your homegrown benchmark. [Promptfoo vs DeepEval vs RAGAS](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/), [DeepEval vs PromptFoo 2026](https://scrolltest.com/deepeval-vs-promptfoo-2026-llm-evaluation-framework/) ✓. Repo `~ github.com/promptfoo/promptfoo`.
5. **`DeepEval` for pytest-native RAG metric gates in CI.** You have RAGAS (metrics); DeepEval adds CI gates so a faithfulness/relevancy regression **fails the build**. [genai.qa comparison](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/) ✓. Repo `~ github.com/confident-ai/deepeval`. (A search hit `github.com/iEFPS/DeepEeval` is a likely typo-squat — do **not** use it.)
6. **Contextual Retrieval** (prepend a 1-sentence doc-level context to each chunk before embedding) — often a bigger win than reranking; you have `contextual_chunking_service.py`. Measure honestly vs current chunking.
7. **Unify the two-stage cache key** — your in-graph semantic re-check ([retrieval.py:747](backend/rag/nodes/retrieval.py)) uses a different key shape than the pipeline cache, so it can't hit. Unify or delete.
8. **NeMo Guardrails** (you reference it): Apache-2.0, real — [github.com/NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) ✓. But for a single-domain bot, Llama Guard + allow-list is lower-latency than the Colang dialog engine.

**Sources (verified in this session):**
- [LettuceDetect (arXiv)](https://arxiv.org/abs/2502.17125) · [HF write-up](https://huggingface.co/blog/adaamko/lettucedetect)
- [Best Rerankers 2026](https://futureagi.com/blog/best-rerankers-for-rag-2026/) · [BSWEN rerankers](https://docs.bswen.com/blog/2026-02-25-best-reranker-models/)
- [Best AI Guardrails 2026](https://generalanalysis.com/guides/best-ai-guardrails) · [OSS guardrails (DeepInspect)](https://www.deepinspect.ai/blog/open-source-llm-guardrails) · [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) · [LLM Guard](https://appsecsanta.com/llm-guard)
- [Promptfoo vs DeepEval vs RAGAS](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/) · [DeepEval vs PromptFoo 2026](https://scrolltest.com/deepeval-vs-promptfoo-2026-llm-evaluation-framework/)

---

*Nothing in the codebase was modified to produce this review. This file is the only new artifact.*
