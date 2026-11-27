# LLM tier for 1,000+ users: OpenRouter now, self-hosted vLLM later?

Research notes, read-only. Written 2026-11-28. Every price has the date it was read. Anything marked **MODELLED** is arithmetic on stated assumptions, not a measurement. Anything marked **SNIPPET** came from a search-result summary and the primary page was not opened.

## 1. Verdict

**Self-hosted vLLM is the wrong next step. Use an open-weight model through the OpenRouter gateway you already run, and only after you fix three code and config problems that would hit before GPU cost does.**

- **Railway has no GPUs.** A vLLM tier would sit on AWS or a GPU cloud, reached over the public internet.
- **Cost.** At a modelled 5,000 chats a day (1,000 daily users × 5 chats), the LLM bill is about $258/month on today's Haiku scorer and about $108/month on a managed open-weight scorer. One always-on L4 GPU in Mumbai costs $705/month; a high-availability pair costs $1,411/month, plus on-call time. The break-even point against managed open-weight is about 33,000 chats/day for one GPU and about 65,000 for a pair (table in section 6).
- **Self-hosting only wins on three grounds:**
  - a data-residency requirement (DPDP, India region);
  - a latency target that managed endpoints cannot meet;
  - traffic of tens of thousands of chats a day.
  None of these applies today.
- **The blockers come before any GPU** (section 3):
  - The budget ceilings in the checked-in defaults stop the service at a few hundred chats a day.
  - Pointing the existing client at vLLM would use up the spend guard after about 30 chats.
  - Gate-critical scorer calls can be routed to different quantizations of the same model from one call to the next.

## 2. Recommendation by phase

| Phase | When | What | Exit gate |
|---|---|---|---|
| **0. Make the current gateway survive 1k users** | Now, no model change | Set budget, RPM and concurrency for the projected volume. Refresh the stale cost table. For the scorer: `zdr: true`, pinned provider and quantization, `allow_fallbacks: false`, `require_parameters: true`. Record measured tokens and cost per chat (the R-2 decision record in the task list). | Measured tokens/chat replace the modelled numbers in section 6 |
| **1. Shadow-score open-weight candidates through OpenRouter** | After phase 0 | Dual-run candidates offline against the frozen graded question set and the negative controls. No serving change. Candidates: `google/gemma-4-26b-a4b-it`, `google/gemma-4-31b-it`, `qwen/qwen3-30b-a3b-instruct-2507`, `mistralai/mistral-small-3.2-24b-instruct`, `openai/gpt-oss-20b`. Separately, look at a replacement for the Llama-3.1-8B classify/distress model. | Registered graded run (invariant 24) meets the metrics in section 8 |
| **2. Dedicated endpoint** | Only with traffic above about 30k chats/day, a residency requirement, or a latency target | vLLM on AWS `g6`/`g6e` in ap-south-1 (or a managed dedicated deployment) behind an authenticating proxy. Failover goes to the **same weights** on OpenRouter, pinned to the same quantization. | Shadow agreement with the phase-1 model ≥ the phase-1 bar; on-call owner named |
| **3. Fine-tuned scorer (multi-LoRA)** | Only after ≥299 human gold labels exist | One LoRA adapter on the phase-2 base, served with `--enable-lora` | Invariant 3: never fit on AI-authored labels |

Sarvam open weights are not a phase-1 candidate (section 5).

## 3. Integration seams in our code (read 2026-11-27/28)

1. **The first-person path ignores `LLM_PROVIDER` and the gateway.**
   - `app/pipeline/stages/first_person_bridge.py:979-983` takes `container.openrouter`, falling back to `nim` and then `ollama`. The `ollama` branch is dead: Ollama was removed 2026-11-16.
   - The relevance scorer, the answerability gate and the first-person HyDE all go through that object.
   - So switching `LLM_PROVIDER` does not move the scorer.
   - The cross-provider failover in `LLMGateway` (`app/container.py:369-381`, `secondary=self.openrouter`, opt-in) does not cover the first-person path either.
2. **Repointing the base URL moves every OpenRouter call at once.**
   - `OpenRouterService` reads `settings.openrouter_base_url` (`services/openrouter_service.py:277`). Changing it moves generation, classification, ingestion and the scorer together. You cannot move only the scorer this way.
   - A second instance would collide with the first in two places:
     - It registers its circuit breaker under the provider name `"openrouter"` (`:298-304`).
     - It shares the class-level Redis limiter, keyed `openrouter:rpm:<model>` (`:259-319`).
   - `services/nim_service.py` already exists as a separate OpenAI-compatible provider class with its own `nim_base_url`, and `services/llm_factory.py` registers it. It is the template for a `vllm` provider.
3. **Spend accounting would fail closed against vLLM. This is the serious one.**
   - Every call reserves `OPENROUTER_MAX_REQUEST_COST_USD` up front: $0.03 by default, via `LLMBudgetGuard.reserve()`.
   - `settle()` refunds only when the reply carries a known `usage.cost`. Its docstring says "unknown usage retains reserve".
   - vLLM returns no `usage.cost`, so each call would keep its full $0.03.
   - **MODELLED:** $10/day ÷ $0.03 ≈ 333 calls ≈ 30 chats a day before `LLMBudgetExceeded` fires.
   - Railway sets `OPENROUTER_BUDGET_FAIL_CLOSED: "true"` (`.railway/railway.ts:101`). Every scorer call would then fail, and every chat would abstain as `relevance_indeterminate`.
   - A self-hosted provider needs its own fixed-cost accounting, or must settle at 0.
4. **The fallback cost table is stale.** It is used only when `usage.cost` is missing, and it prices unknown models at $0. Compared with the OpenRouter `/api/v1/models` list, read 2026-11-27:

   | Model | Table ($/M in/out) | Live list ($/M in/out) |
   |---|---|---|
   | `deepseek/deepseek-chat` | 0.14/0.28 | 0.2574/1.0287 |
   | `meta-llama/llama-3.3-70b-instruct` | 0.12/0.30 | 0.59/0.79 |
   | `meta-llama/llama-3.1-8b-instruct` | 0.02/0.04 | 0.05/0.08 (model listing) |

   - For the 8B model, the cheapest endpoint (DeepInfra) is still 0.02/0.04. Groq is 0.05/0.08.
   - `sarvamai/sarvam-m` is **no longer listed**, but the `sarvam-m` preset and its cost row are still in the code.
5. **Model-keyed scorer branches** (`services/first_person_pipeline.py:1018-1035` and `:1543-1564`):
   - `_SCORER_JSON_SCHEMA_MODELS`
   - `_SCORER_NO_TEMPERATURE_MODELS`
   - the `startswith("anthropic/")` branch, which sets `max_tokens=2048`, `operation="verify"` and `reasoning_effort="low"`
   - the DeepSeek `max_tokens=16` special case

   A new model id silently takes the comma-separated path with no schema unless it is added to these sets. vLLM's xgrammar-backed `response_format: json_schema` can enforce the keyed exact-count schema (`_exact_n_scorer_contract`), which is a reason to add the new model to the JSON set deliberately.
6. **Fields only OpenRouter understands.** The request carries `provider`, `reasoning` and `session_id` (`:678-726`).
   - vLLM has accepted unknown fields since PR #10463 (merged 2024-11-20). It ignores them and logs a server-side warning.
   - Exception: models served with `--tokenizer-mode mistral` can still return 400. That matters for Mistral-Small and Sarvam-M, which is built on Mistral-Small.
   - On vLLM, thinking is controlled by `chat_template_kwargs.enable_thinking` and `thinking_token_budget`. Our `reasoning` kwarg would do nothing and say nothing. Must be tested against the pinned vLLM version.
7. **Model allowlist.** `OpenRouterModelPolicy.assert_model_allowed` (`app/model_policy.py:192`) rejects any id not in `OPENROUTER_EXTRA_ALLOWED_MODELS`. Use vLLM's `--served-model-name` to keep the ids stable.
8. **Provider routing is not pinned for gate calls.**
   - `provider_preferences()` sets only `data_collection: deny`, plus `order`, `sort` and latency thresholds when configured.
   - The defaults are `sort=throughput` and `allow_fallbacks=true`.
   - Endpoint lists read 2026-11-27 show one model id served at very different precisions:
     - `gemma-4-26b-a4b-it`: 15 endpoints, from fp4 and int4 to bf16
     - `gpt-oss-20b`: fp4 to bf16
   - So a scorer score could come from an fp4 build on one call and a bf16 build on the next. OpenRouter supports `only`, `quantizations`, `zdr`, `require_parameters` and `max_price` (provider-selection docs).
9. **Defaults that cap traffic before any model choice matters:**

   | Setting | Default | Where | What it caps (MODELLED) |
   |---|---|---|---|
   | `OPENROUTER_RPM_LIMIT` | 20 per model | `backend/docker-compose.yml:266` | About 170 scorer chats/hour at 7 scorer calls per chat |
   | `OPENROUTER_RPM_LIMIT` | 120 per model | `config.py:749` | — |
   | `OPENROUTER_MONTHLY_BUDGET_USD` | 40 | `backend/.env.example`, compose | About 775 chats/day |
   | `OPENROUTER_MONTHLY_BUDGET_USD` | 100 | root `.env.example` | — |
   | `OPENROUTER_MONTHLY_BUDGET_USD` | `preserve()` | Railway | Live value unknown |
   | `MAX_CONCURRENT_CHAT` | 8 or 12 | compose, config | — |
   | `WEB_CONCURRENCY` | 1 | `railway.ts:217` | — |

10. **Scorer calls run in parallel.** `first_person_harness_parallel_enabled=True` runs them with `asyncio.gather` under a semaphore of 4 (`_HARNESS_JUDGE_CONCURRENCY`).
    - Latency is about two rounds of scorer latency, not seven.
    - The repo's own CA-2 note says Haiku spends 150-380 reasoning tokens to return a few digits, and that this is "most of the ~6 s latency floor".
    - A **non-reasoning** open model is the strongest latency lever, more than self-hosting.
11. **The distress call runs on the 8B fast model** (`classify_distress_structured` → `_generate_fast`). The Llama-3.1-8B model card lists Hindi as its only supported Indic language. The call only escalates, so its failure mode is a missed escalation. That makes the 8B replacement a safety item, not a cost item.
12. **Cache keys already change with the scorer model.** The policy fingerprint includes `relevance_model` (`first_person_pipeline.py:~4022`), so the exact cache re-keys when the scorer model changes.

## 4. Research answers

### Q1: Railway and GPUs

- Railway's own vLLM template FAQ (opened 2026-11-28) says: "Railway containers do not have GPU access, so the CPU build (`vllm-openai-cpu`) is the only viable option on Railway."
- The pricing/plans page (opened 2026-11-27) lists vCPU and RAM only: containers at $20/vCPU-month and $10/GB-month. It does not mention GPUs.
- A community thread quotes CEO Jake Cooper on 2026-05-20: "We will not do GPUs now, but we 100% will do GPUs at some point in the future". This is a replier's quote of an interview, not a staff post.
- **Alternatives:**
  - Keep the API on Railway and reach an AWS, Modal or RunPod endpoint over public TLS.
  - Railway's private network is internal to Railway, so the GPU endpoint must be internet-reachable. Lock it down with an auth token, a reverse proxy that allowlists `/v1/chat/completions` only, and ideally IP allowlisting.
  - Whether Railway provides static egress IPs was not verified.
  - Egress is negligible: a few KB of text per call.
  - Each call adds one internet round trip. With two parallel rounds per chat that adds roughly 2 RTTs; India↔ap-south-1 RTT is not measured here.

### Q2: vLLM facts (docs.vllm.ai, opened 2026-11-27)

- **OpenAI-compatible server.** Endpoints include `/v1/chat/completions`, a batch variant, and `/v1/responses`. Chat requires a chat template.
- **Auth.** `--api-key` covers only the `/v1`, `/v2`, `/inference` and `/cohere` prefixes; the docs say "Do not rely on `--api-key` alone".
- **Unauthenticated endpoints.** The security page lists endpoints outside those prefixes that skip the key:
  - inference: `/invocations`, `/score`, `/rerank`
  - control: `/pause`, `/abort_requests`, `/update_weights`
  - information: `/metrics`, `/health`

  It recommends a reverse proxy with an allowlist.
- **Prefix caching.** Automatic prefix caching reuses the KV cache of a shared leading prefix. It speeds up prefill only, and helps only when the prefix is identical and at the start.
  - Our seven scorer calls share an about 600-token rubric system prompt, followed by the question. That is a good fit.
  - The page does not say whether prefix caching is on by default.
  - It reduces GPU load, not an API bill.
- **Structured outputs.** On by default in the server: `response_format` with `json_schema`, plus `structured_outputs` with `choice`, `regex` and `grammar`. Backends are xgrammar and guidance, chosen with `auto`.
  - The `guided_*` fields were removed in v0.12.0.
  - Regex uses Rust syntax.
  - With a reasoning model, structured output may need `enable_in_reasoning`.
- **Quantization.** AWQ, GPTQ, Marlin, bitsandbytes, GGUF and LLM-Compressor INT8 all run on Ada (L4) and Ampere (A10G). FP8 W8A8 needs Ada or Hopper; on Ampere it runs weight-only.
- **Multi-LoRA.** `--enable-lora`, `--lora-modules`, `--max-loras`; requests select an adapter by the `model` name. Runtime loading is flagged as unsafe for production.
- **Metrics.** `vllm:time_to_first_token_seconds`, `vllm:request_queue_time_seconds`, `vllm:kv_cache_usage_perc`, `vllm:num_requests_running/waiting`, and the `prefix_cache_queries`/`hits` counters (no direct hit-rate metric).
- **Hardware fit:**
  - 7-8B in bf16 (about 16 GB) fits a 24 GB L4 or A10G. The AWS EKS guide says the same for an 8B model on G6.
  - A 26-31B model in bf16 (about 52-62 GB) does not fit 48 GB. Options:
    - FP8 (about 26-31 GB) on an L40S (`g6e`)
    - INT4 AWQ/GPTQ (about 14-17 GB) on an L4, at a quality cost that has to be measured
- **Throughput (reputable, not our hardware or prompt shape).** Red Hat's MLPerf v5.1 post (2025-10-31, vLLM 0.10.0, Llama-3.1-8B FP8):
  - L40S: 1,642 tok/s offline, 1,207 tok/s server
  - H100: 5,777 tok/s offline, 5,103 tok/s server

  No L4 number was found from a primary source. **SNIPPET:** the TrueFoundry A10 figure (about 349 tok/s at 16 users) and the NVIDIA NIM concurrency table.
  - Our workload is prefill-heavy with tiny outputs, unlike MLPerf.
  - **MODELLED:** peak-hour load at 5,000 chats/day is about 0.21 chats/s × about 8k input tokens ≈ 1.7k prefill tok/s. This is probably within one GPU, but **must be measured** with `vllm bench serve` on the real prompt mix.

### Q3: AWS (official price maps, published 2026-11-24, read 2026-11-27)

On-demand Linux, USD per hour:

| Instance | GPU | VRAM | us-east-1 | ap-south-1 (Mumbai) | Mumbai 24/7 (730 h) |
|---|---|---|---|---|---|
| g6.xlarge | L4 | 24 GB | 0.8048 | 0.9664 | $705 |
| g6.2xlarge | L4 | 24 GB | 0.9776 | 1.1739 | $857 |
| g5.xlarge | A10G | 24 GB | 1.006 | 1.208 | $882 |
| g6e.xlarge | L40S | 48 GB | 1.861 | 2.235 | $1,632 |
| g6e.2xlarge | L40S | 48 GB | 2.2421 | 2.6927 | $1,966 |

- **Spot.** The `spot.js` snapshot read 2026-11-27 showed:
  - g6.xlarge us-east-1: $0.105/h (about 87% off on-demand)
  - g5.xlarge: $0.50/h (us-east-1 and Mumbai)

  The snapshot is undated and **volatile**; spot instances can be interrupted, so they do not suit a serving gate without failover.
- **Not obtained:** Savings Plan prices, SageMaker endpoint prices, and Bedrock Llama prices (that table did not load).
- **Quotas.** The EC2 quota page lists "Running On-Demand G and VT instances" at a **default of 0 vCPU** (Spot also 0). A new account must file a quota request before launching anything.
- **Cold start.** The AWS EKS vLLM guide shows a best case on g6e.4xlarge with SOCI image streaming and the Run:ai model streamer:
  - node in about 30 s
  - 8.8 GB image in 48 s
  - 10.4 GB weights in 5 s

  That makes scale-from-zero minute-scale, not request-scale.
- **Deployment shape at this size.** A single EC2 instance or an ECS task with vLLM, behind an ALB/proxy, is enough. EKS is not justified at one or two GPUs.
- **Bedrock** (pricing page opened 2026-11-27, USD per M tokens in/out, US regions):

  | Model | In | Out |
  |---|---|---|
  | Gemma 4 26B A4B | 0.13 | 0.40 |
  | Gemma 4 31B | 0.14 | 0.40 |
  | Gemma 3 12B | 0.09 | 0.29 |
  | Ministral 8B | 0.15 | 0.15 |
  | Qwen3 Next 80B A3B | 0.15 | 1.20 |
  | DeepSeek v3.2 (Mumbai) | 0.74 | 2.22 |

  These are more expensive than the same weights through OpenRouter's cheaper endpoints.

### Q4: Managed open-weight and serverless GPU (pages opened 2026-11-27)

| Provider | Relevant price | Data retention (as read) |
|---|---|---|
| **OpenRouter** (`/api/v1/models` + endpoints) | gemma-4-26b-a4b 0.09/0.30 listing (DeepInfra fp8 0.07/0.34); gemma-4-31b 0.20/0.40; qwen3-30b-a3b-instruct-2507 0.10/0.30; mistral-small-3.2 0.075/0.20; gpt-oss-20b 0.03/0.13; Haiku 5.5 0.10/0.50 | Per-request `zdr: true` or an account ZDR setting. For ZDR traffic OpenRouter says it keeps no prompts or responses except for CSAM/legal review. CSAM screening of all traffic starts 2026-10-27. In-region routing exists for EU/US on Business/Enterprise; no India region was mentioned. |
| **DeepInfra** | Llama-3.1-8B 0.02/0.04; Qwen3-32B 0.08/0.28; Gemma-4-26B-A4B 0.07/0.34; dedicated A100 $1.49/h, H100 $2.90/h | "Zero data retention" appears only under the Enterprise section; default not confirmed |
| **Fireworks** | gpt-oss-120b 0.15/0.60; H100 on-demand $8/h | "Zero data retention by default"; SOC 2, HIPAA BAA |
| **Groq** (models page) | gpt-oss-20b 0.075/0.30, about 1,000 tok/s; Llama 8B and 70B "contact sales"; Developer plan 250K TPM / 1K RPM | Not read |
| **Together** | Qwen3.5-9B 0.17/0.25; gpt-oss-120B 0.15/0.60; dedicated H100 $5.49/h | Not read |
| **Modal** | L4 $0.000222/s (about $0.80/h); L40S about $1.95/h; $30/month free credits; region pinning 1.15-1.75× | Not read |
| **RunPod** | L4 pod $0.69/h (secure), serverless 24 GB class $0.75/h; L40S pod $1.09/h | Not read |
| **Replicate** | Not opened | — |

**DPDP flag (not legal advice).** Seeker messages are spiritual and mental-health adjacent. Any provider choice should be recorded in the vendor review with region and retention. A residency requirement is the one thing that would move self-hosting in ap-south-1 forward.

### Q5: Indic quality (cite only what was read)

- **Llama-3.1-8B card.** Supported languages are English, German, French, Italian, Portuguese, Hindi, Spanish and Thai. Meta "strongly discourage[s]" use in unsupported languages without fine-tuning. So Telugu, Tamil, Kannada, Malayalam, Marathi and Bengali are unsupported for the classify and distress calls.
- **Qwen3 blog.** "119 languages and dialects", explicitly including Hindi, Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam and others. Thinking can be switched off (`enable_thinking`).
- **Gemma 4 31B card.** "35+ languages" out of the box, pre-trained on 140+. MMMLU scores:
  - 31B: 88.4
  - 26B A4B: 86.3
  - Gemma 3 27B: 70.7

  MMMLU is not Indic-specific.
- **Sarvam-M card.** Mistral-Small-3.1-24B base, Apache-2.0, Indic scripts plus romanized Indic. It reports only relative gains (+20% average on Indian-language benchmarks, +86% on romanized GSM-8K), with no absolute scores. It is no longer on OpenRouter.
- **Sarvam-30B card.** 32B MoE with 2.4B active parameters, Apache-2.0.
  - MILU scores on the card: Sarvam-30B 76.8, Gemma 27B 69.2, Mistral-3.2-24B 67.9, gpt-oss-20b 73.7, Qwen3-30B-Thinking 82.6.
  - Native vLLM support is still an open PR; serving needs a fork or a hotpatch, and the card's vLLM example uses TP=8.
  - Card says "No Inference Provider currently hosts the model."
- **Artificial Analysis (2026-04-02).** Intelligence Index: Sarvam 30B 12, Sarvam 105B 18, Qwen3 30B A3B 22. High hallucination and few abstentions on AA-Omniscience. No independent Indic results.
- **Sarvam's own blog (2026-03-06).** 89-90% pairwise win rates judged by Gemini 3. The comparison models are not named, so these are vendor claims.
- **MILU (AI4Bharat + IBM, NAACL 2025).** 11 Indic languages. GPT-4o is best at 74%. Language-specific fine-tunes score barely above random. Low-resource languages score lower.
- **Disagreement.**
  - Sarvam's own numbers put it ahead on Indic.
  - Artificial Analysis rates its general capability below the Qwen and GLM peers.
  - MILU says language-specific fine-tunes generally lag.
- **Uncertainty.** No public benchmark measures our task: scoring the relevance of mostly-English teacher clips to Indic or romanized questions on a 0-3 rubric. It must be measured on our own graded set, broken out by language.

## 5. Why not Sarvam open weights first

They are not on OpenRouter, have no hosted provider, and have no native vLLM support. They also have the weakest independent general score of the candidates. Revisit once vLLM merges support and a provider hosts them.

## 6. Break-even model (MODELLED)

### Token assumptions per chat

Prompt sizes were measured from the code with `len()`: rubric 2,353 characters, answerability 2,787, HyDE 458, distress 912. Characters are converted at 4.2 per token for English.

| Call | Count | Input tokens (mid) | Output tokens (mid) |
|---|---|---|---|
| Relevance scorer (Haiku) | 7 | about 600 rubric + 25 question + 300 clip = 925 each | about 280 reasoning (CA-2: 150-380) + 15 visible |
| Answerability (8B) | 1 | 690 | 3 |
| HyDE (8B) | 1 | 135 | 150 |
| Classification (8B) | 1 | 300 | 10 |
| Distress (8B) | 1 | 350 | 60 |
| **Total** | 11 | 7,950 | about 2,190 |

Low and high cases:
- **Low:** clip 150 tokens, 150 reasoning tokens.
- **High:** clip 600 tokens, question ×3 for Indic tokenization, 380 reasoning tokens.

The Indic multiplier is applied to the question only, because the quotes are not translated. If clips are Tamil or Telugu talks, input could be 2-3× higher.

### Cost per chat (prices read 2026-11-27)

| Scorer option | Low | Mid | High | Per 1,000 chats (mid) |
|---|---|---|---|---|
| Haiku 5.5 ($0.10/$0.50), 8B at $0.02/$0.04 | $0.00116 | $0.00172 | $0.00240 | **$1.72** |
| Qwen3-30B-A3B-Instruct-2507 non-thinking ($0.10/$0.30), 15 output tokens | $0.00047 | $0.00072 | $0.00104 | **$0.72** |
| Gemma-4-26B-A4B at DeepInfra fp8 ($0.07/$0.34) | $0.00035 | $0.00053 | $0.00075 | **$0.53** |

Arithmetic for the mid Haiku row:
- Input: 7 × 925 = 6,475 tokens × $0.10/M = $0.000648
- Output: 7 × 295 = 2,065 tokens × $0.50/M = $0.00103
- 8B calls: 1,475 in × $0.02/M + 223 out × $0.04/M = $0.000038
- Total: **$0.00172**

The 8B share is under 3% of the total. Over 60% of the Haiku cost is reasoning output.

### Monthly cost at the assumed load

Assumed load: 1,000 daily users × 5 chats = 5,000 chats/day = 150,000 chats/month.

| Option | $/month |
|---|---|
| Haiku scorer via OpenRouter | **$258** |
| Open-weight scorer via OpenRouter (Qwen3-30B mid) | **$108** |
| 1 × g6.xlarge Mumbai 24/7 (730 h × $0.9664) | **$705** + ops time |
| 2 × g6.xlarge Mumbai (high availability) | **$1,411** + ops time |
| 1 × g6e.xlarge Mumbai (needed for a 26-31B model at FP8) | **$1,632** |

Business hours only (12 h/day): one g6.xlarge in us-east-1 costs about $290/month. That is useful for shadow evaluation only; a public chat app runs around the clock.

### Break-even (chats/day = GPU $/month ÷ (cost per chat × 30))

| GPU setup (Mumbai, on-demand) | vs Haiku ($0.00172) | vs managed open-weight ($0.00072) |
|---|---|---|
| 1 × g6.xlarge ($705) | 13,700/day | 32,700/day |
| 2 × g6.xlarge, high availability ($1,411) | 27,300/day | 65,300/day |
| 1 × g6e.xlarge ($1,632) | 31,600/day | 75,500/day |

Engineering and on-call time are excluded. Including them pushes break-even higher still. At the assumed 5,000 chats/day, self-hosting costs **2.7-13×** more than the managed options.

### Ceilings at the assumed load

- **Daily budget.** $10/day covers 5,000 Haiku chats/day (about $8.60/day) with almost no headroom.
- **Monthly budget.** $40/month caps at about 23,000 chats/month; $100 at about 58,000. Both are below 150,000.
- **Rate limit.** At 7 scorer calls per chat and peak hour = 15% of daily chats:
  - about 88 scorer calls/min on average across the peak hour
  - over the 20 RPM compose default
  - near the 120 RPM config default once bursts are counted

## 7. Operational risks of self-hosting

- **Capacity.** The G and VT quota starts at 0 and must be requested. L4 and L40S availability in ap-south-1 is not guaranteed. Spot capacity can be interrupted.
- **Cold starts and scaling.** Scale-from-zero takes about 1-2 minutes in AWS's own best case, so one GPU must stay warm and a second is needed for high availability.
- **Model updates.**
  - Changing weights, quantization, vLLM version or chat template can each move the gate's scores.
  - Each is a gate change that needs a registered graded run.
  - Pin all four in the image tag.
- **Observability.**
  - Scrape the vLLM `/metrics` from a private network.
  - Join it with our `OPENROUTER_CALL_TIMING` log and the R-2 decision record.
  - Alert on queue time, KV-cache usage and the indeterminate rate.
- **Paging.**
  - Today the provider is paged for outages.
  - Self-hosting makes the owner (Harshodai) the on-call for GPU, driver and OOM incidents.
  - Railway is currently stopped, so there is no 24/7 operator.
- **Failover.**
  - Falling over to a *different* model (for example Haiku) mid-outage changes serving behaviour (invariant 24).
  - Fail over to the **same weights** on OpenRouter, with `only`, `quantizations` and `allow_fallbacks: false` pinned.
  - If no same-weights endpoint is available, fail closed (abstain), which the scorer already does.
  - The first-person bridge does not use `LLMGateway` today, so that failover has to be built.
- **Security.**
  - Do not expose vLLM directly; a proxy allowlists `/v1/chat/completions` only.
  - Use a bearer token plus `--api-key`, TLS, and IP allowlisting if Railway egress IPs can be pinned (unverified).
  - Never set `VLLM_ALLOW_RUNTIME_LORA_UPDATING` or `VLLM_SERVER_DEV_MODE`.
  - Keep `/metrics` and `/update_weights` off the internet.

## 8. A graded-run-safe migration

Use the machinery that already exists rather than adding new tools:
- `backend/docker-compose.graded.yml` (frozen comparability harness; do not edit it)
- `backend/scripts/ops/graded_run_preflight.py`, `graded_capture.py`, `graded_registered_report.py`
- `run_negative_controls.py`
- `run_judge_replay.py` (spend-gated)
- `.work/autoresearch_fp/labels.jsonl` (labels)

Steps:

1. **Offline shadow scoring.** Replay the frozen graded candidate sets — the same retrieved contexts, so only the scorer varies — through each candidate scorer and Haiku. Make paid calls only with spend logged, as `run_judge_replay.py` already requires.
2. **Metrics, each broken out by English, Indic-script and romanized questions:**
   - serve/abstain agreement with Haiku at min score 2
   - quadratic-weighted kappa on the 0-3 scores
   - negative-control abstention: 13/13 must still hold
   - indeterminate rate (schema or count failures)
   - p50/p95 scorer latency
   - cost per answered question
3. **Agreement with Haiku is a regression check, not proof of quality.** Haiku's labels are AI-authored (invariant 3). Only 14 human labels exist, and no calibration profile exists. A candidate that agrees with Haiku has not been shown to be correct.
4. **Pin before measuring.** Fix provider, quantization, temperature and the schema contract. Run each candidate twice to measure self-consistency; a non-deterministic gate is disqualifying.
5. **Registered graded run** under the frozen compose with the new `FIRST_PERSON_RELEVANCE_MODEL`, then an owner decision.
6. **Serving shadow (optional).** Run the candidate in shadow on live traffic: log its scores, never serve them. Requires its own default-off flag with a reader, tests for both flag states, and no effect on the cache key.
7. **Rollback** is the env var `FIRST_PERSON_RELEVANCE_MODEL`. The policy fingerprint re-keys the cache automatically.

## 9. Uncertainties

- Every token count in section 6 is modelled. Phase 0 exists to replace them with measurements.
- No primary L4 throughput figure was found for vLLM.
- vLLM's handling of our unknown fields was read from a 2024 PR. It needs testing on the pinned version, especially in Mistral tokenizer mode.
- Prices not obtained: Savings Plans, SageMaker, Bedrock Llama, and the Groq 8B price.
- Retention policies not read: Together, Groq, Modal, RunPod.
- The live Railway budget values (`preserve()`) are unknown.
- No source measures cross-lingual clip-relevance scoring.

## Sources (opened unless marked)

- railway.com/deploy/vllm: template FAQ, "Railway containers do not have GPU access" (2026-11-28)
- docs.railway.com/reference/pricing/plans: plan limits and per-vCPU/GB prices, no GPU (2026-11-27)
- station.railway.com/community/gpu-support-vllm-b92b5375: CEO quote of 2026-05-20, relayed by a replier
- docs.vllm.ai `.../online_serving/openai_compatible_server/`: endpoints, `--api-key` scope, chat template, thinking kwargs
- docs.vllm.ai `.../usage/security.html`: unauthenticated endpoints, reverse-proxy advice
- docs.vllm.ai `.../features/automatic_prefix_caching.html`: what prefix caching does and its limits
- docs.vllm.ai `.../features/structured_outputs.html`: `response_format` json_schema, xgrammar/guidance backends
- docs.vllm.ai `.../features/quantization/`: method × hardware table
- docs.vllm.ai `.../features/lora.html`: multi-LoRA flags
- docs.vllm.ai `.../design/metrics.html`: Prometheus metric names
- github.com/vllm-project/vllm/pull/10463: extra fields ignored with a warning, merged 2024-11-20
- redhat.com: MLPerf Inference v5.1 post, Llama-3.1-8B FP8 throughput on L40S/H100 (2025-10-31)
- docs.aws.amazon.com EKS "Load & Serve Models" (vLLM): cold-start timings, monitoring
- docs.aws.amazon.com EC2 instance quotas: G/VT default 0
- aws.amazon.com/ec2/instance-types/g6, g5, g6e: specs (no prices on these pages)
- b0.p.awsstatic.com EC2 on-demand price maps for us-east-1 and ap-south-1 (published 2026-11-24)
- website.spot.ec2.aws.a2z.com/spot.js: spot snapshot (undated, volatile)
- aws.amazon.com/bedrock/pricing: open-weight per-token prices (Llama table did not load; read to character 100,000 of 117,717)
- openrouter.ai/api/v1/models and `/models/<id>/endpoints`: prices, quantizations, schema support (2026-11-27)
- openrouter.ai/docs/guides/privacy/provider-logging: data policy tiers
- openrouter.ai/docs/guides/features/zdr: `zdr` parameter, retention, CSAM screening
- openrouter.ai/docs/guides/routing/provider-selection: `only`, `quantizations`, `zdr`, `require_parameters` (read to character 100,000 of 132,066)
- console.groq.com/docs/models: gpt-oss prices, speeds, rate limits (groq.com/pricing had no prices)
- together.ai/pricing: serverless and dedicated prices
- deepinfra.com/pricing: per-token and dedicated prices, Enterprise ZDR line
- fireworks.ai/pricing: prices, "Zero data retention by default"
- modal.com/pricing: per-second GPU prices
- runpod.io/pricing: pod and serverless per-hour prices
- huggingface.co/meta-llama/Llama-3.1-8B-Instruct: supported languages
- huggingface.co/sarvamai/sarvam-m: base model, relative Indic gains
- huggingface.co/sarvamai/sarvam-30b: MILU table, vLLM PR status
- sarvam.ai/blogs/sarvam-30b-105b: vendor Indic win rates (2026-03-06)
- artificialanalysis.ai Sarvam article: independent Intelligence Index (2026-04-02)
- qwenlm.github.io/blog/qwen3: 119 languages, Indic list, thinking switch
- huggingface.co/google/gemma-4-31B-it: language counts, MMMLU, sizes
- arxiv.org/abs/2411.02538: MILU abstract
- **SNIPPET only:** TrueFoundry vLLM A10 benchmark, NVIDIA NIM performance table, enterprisedna Railway+Modal post
- **Repo files read:**
  - `backend/services/openrouter_service.py`
  - `backend/services/first_person_pipeline.py`
  - `backend/app/pipeline/stages/first_person_bridge.py`
  - `backend/app/container.py`
  - `backend/app/config.py`
  - `backend/app/model_policy.py`
  - `backend/services/llm_budget_guard.py`
  - `backend/services/llm_factory.py`
  - `backend/services/nim_service.py`
  - `backend/services/multi_provider_llm.py`
  - `backend/services/llm_gateway.py`
  - `backend/docker-compose.yml`
  - `.railway/railway.ts`
  - `backend/.env.example` and root `.env.example`
