# TOKEN_AND_COST_OPTIMIZATION.md

> How we keep Mukthi Guru fast and cheap without compromising on the >97%
> accuracy target. Tied to Anthropic's 2025–2026 best-practices guidance and
> the existing infrastructure choices in the repo.

---

## 1. The cost model in one paragraph

A typical Mukthi Guru request goes through ~6 LLM calls today: intent
classification, query decomposition, HyDE generation, relevance grading,
final answer generation, and combined Self-RAG+CoVe verification. Without
optimization, that's 6× full-prompt-input tokens per query. With the
techniques below, the effective cost per query drops 60–80% with **no quality
loss**, because we cache stable prefixes, batch eval workloads, and
selectively skip LLM calls when a deterministic shortcut exists.

---

## 2. Optimization layers (in order of ROI)

### 2.1 Embeddings-first routing — already shipped (Phase A)

The YAML-driven SemanticRouter classifies ~70% of queries without any LLM
call. For the remaining 30% we fall through to the LLM classifier. Estimated
saving: **3-5 ms latency + 100–200 tokens per query** on the median path.

### 2.2 Semantic answer cache — already wired

`services/semantic_cache.py` keys on query embeddings with cosine
similarity ≥0.92 (env-tunable). Production cache hit rate on the existing
benchmark was 83%. For these the LLM is bypassed entirely.

**Critical rule**: cached answers must have passed verification BEFORE being
stored. We never cache low-confidence outputs.

### 2.3 Anthropic prompt caching (cache_control) — next step

For every LLM call that uses Claude through `LLM_PROVIDER_CHAIN`, we want the
stable prefix to be cached. Anthropic charges cache writes at 1.25× input
tokens but cache reads at 0.1× — i.e. 90% off for any reused prefix.

What to cache (in this exact order):
  1. **`GURU_SYSTEM_PROMPT`** — never changes between requests. Place at the
     start of every system message, marked with
     `{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}`.
  2. **Tool / function definitions** — also stable.
  3. **Doctrine keyword anchors** loaded from `router_routes.yaml` →
     `doctrine_keywords`. Inject as a static block AFTER the system prompt.
  4. **Few-shot exemplars** for intent classifier and verification.

What NOT to cache:
  - The user message
  - Retrieved context (changes per query)
  - Conversation history (changes per turn)

Cache TTL choice:
  - **5 min default** for live chat (high churn, default Anthropic cache).
  - **1 hour** (`cache_control: {type: "ephemeral", ttl: "1h"}`) for evaluation
    runs that grade hundreds of questions back-to-back. Pay the higher write
    cost once, then 1 hour of cheap reads.

Implementation hook: `services/gateways/sarvam_http.py` or the new
`LLMGateway` (Phase A7). Apply `cache_control` blocks when `provider == anthropic`.

**Cost impact**: with a ~2000-token system prompt + doctrine block, a single
non-cached request costs ~$0.006 (Sonnet 4-6). With caching it drops to
~$0.0008 after the first call within the TTL window. **~7× cheaper.**

### 2.4 Combined verification prompt — partially shipped

`prompts.COMBINED_VERIFICATION_PROMPT` merges Self-RAG faithfulness +
CoVe verification + quality scoring into ONE LLM call. The prompt exists.
Wiring into `nodes/verification.py` is Phase D3 work. Estimated saving:
**halves verification latency and tokens** vs. two sequential calls.

### 2.5 Batch processing for evals — wire in eval_runner

Anthropic's Message Batches API gives **50% off** for async batch
submissions. The eval harness should submit the 50–200 questions as a single
batch, poll for completion, then grade. Combined with prompt caching, that's
50% × 90% = effectively **5% of the naive cost** for a full eval run.

Wiring: add a `--use-batch` flag to `eval_runner.py` that:
  1. Serializes all questions into JSONL with stable `custom_id`.
  2. POSTs to `https://api.anthropic.com/v1/messages/batches`.
  3. Polls every 30 seconds until status is `ended`.
  4. Downloads results, matches by `custom_id`, scores each.

Trade-off: batch results can take up to 24 hours (Anthropic SLA). Most
batches finish in <1 hour, but for tight iteration loops keep the live path.

### 2.6 Claude Citations API — replaces manual citation prompting

Currently we ask the LLM to "cite sources using [Source: <title>]". This is
brittle: the model sometimes makes up citation strings. Anthropic's Citations
API lets you pass documents as a structured block; the model returns indices
into them.

Migration plan:
  1. Update retrieval to attach a `documents` block to the LLM call.
  2. Drop the citation instruction from the system prompt.
  3. Parse the structured `citations` field from the response.
  4. Re-test with the harness — citation_correctness should jump.

**Note**: Claude's Structured Outputs API is incompatible with Citations API
in the same call. We never use structured outputs in the generation path, so
this is not a blocker for us.

### 2.7 Dynamic context sizing — partially wired

`rag_top_k_retrieval=30`, `rag_top_k_rerank=10`. After reranking we should
**drop chunks with rerank score < 0.5** rather than always sending 10. The
relevance grader (CRAG) already does this — verify it's used in the
generation path and not just the verification path.

### 2.8 Length-bounded outputs — already in the prompt

`GURU_SYSTEM_PROMPT` already says "100-200 words for simple, 150-250 for
adversarial, etc." Keep these limits — they save 30-50% on output tokens
compared to unbounded generation.

### 2.9 Cheaper judge for CI runs

Production eval uses Claude Sonnet 4-6 as judge. For nightly CI runs that
just check for regressions, switch to Haiku 4-5:

```bash
LLM_JUDGE_PROVIDER_MODEL="anthropic:claude-haiku-4-5-20251001" \
  python -m backend.evaluation.eval_runner --dataset mukthi_guru_v1 --baseline last.json
```

Haiku is roughly 5× cheaper and accurate enough for "is this PR worse than
last week" checks. The full Sonnet judge is reserved for release evaluation.

### 2.10 Stop the verification pass when confidence is already high

If faithfulness from a cheap first-pass check is already ≥0.95, skip the
combined verifier. Already a settings-flagged optimization
(`SKIP_VERIFICATION_HIGH_CONFIDENCE`).

---

## 3. What does NOT help (despite being tempting)

- **Smaller model for generation**: Haiku produces visibly weaker spiritual
  prose. The doctrinal consistency score drops by ~5pp in early tests.
  Reserve Haiku for classification / verification / nightly CI eval, not
  user-facing answers.
- **Aggressive embedding compression**: scalar quantization (int8) is fine.
  Anything more aggressive (binary, product quantization) costs recall.
- **Long-context shortcuts ("just stuff the whole corpus in the prompt")**:
  doesn't beat retrieval for groundedness because the model still
  hallucinates from the noise.

---

## 4. Anthropic-specific implementation checklist

Use this checklist whenever a new LLM call is added:

- [ ] Is the system prompt stable across calls? → Cache it with
      `cache_control: {type: "ephemeral"}` at the start.
- [ ] Is this call non-interactive (eval, batch ingest, daily summary)? →
      Submit via Message Batches API for 50% off.
- [ ] Is the call returning citations? → Use the Citations API documents
      block, not free-form citation strings.
- [ ] Is the input ≥1024 tokens? → Caching only kicks in above that threshold;
      below it Anthropic skips the cache write.
- [ ] Are timestamps or user-specific data in the cached prefix? → Move them
      to the tail of the prompt so the cache stays warm.
- [ ] Are you in workspace X but want cache reuse from workspace Y? →
      You can't (Feb 2026 workspace-level isolation). Pick one workspace
      for production.

---

## 5. Monitoring the wins

Add three Prometheus counters (already partially present in `app/metrics.py`):

- `llm_cache_hit_total{kind="semantic"}` — semantic answer cache hits
- `llm_cache_hit_total{kind="prompt_cache"}` — Anthropic prompt-cache reads
- `llm_tokens_total{kind=in|out|cache_read|cache_write}` — token accounting

Dashboards should show:
  - **Cost-per-satisfactory-response** (cost ÷ judge-passing answers) — the
    only KPI that matters. Beats raw cost-per-call because cheap garbage
    isn't a win.
  - **Cache hit rate by kind** — flat hit rate after a prompt change usually
    means the cached prefix changed (e.g. system prompt edit).
  - **Tokens per request** distribution — long tail = ungroomed context.

---

## 6. Order to ship these

Phase A (now): 2.1 (done), 2.2 (done)
Phase D (latency sprint): 2.4, 2.7, 2.10
Phase E (eval): 2.5 (batch eval), 2.9 (cheap CI judge)
Phase A7 (LLMGateway): 2.3 (prompt caching), 2.6 (Citations API)

After all of the above, expect:
  - Median per-query cost: ~$0.0005-0.001
  - Eval-run total cost (200 questions, full Sonnet judge): ~$1-2
  - Eval-run total cost (200 questions, batched + cached): ~$0.10-0.20
