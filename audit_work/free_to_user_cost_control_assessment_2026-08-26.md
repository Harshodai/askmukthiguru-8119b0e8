# AskMukthiGuru Free-to-User Cost-Control Assessment

**Scope:** Operating-cost containment for a product whose end users do not pay.  
**Evidence posture:** Repository-verified controls plus first-party provider documentation; no provider bill, Railway invoice, user-volume export, or production spend ledger was available in this pass.

## Executive finding

AskMukthiGuru already has meaningful free-user protection at admission: anonymous sessions default to **5 turns per 24 hours**, degraded Redis mode uses a conservative **3-turn** limit, and concurrent chat work is bounded. However, the main OpenRouter spend guard is **disabled by default**, while the broader monthly operating envelope is explicitly a soft alert. The product can therefore limit abuse and overload but cannot yet prove that provider spend is hard-bounded before a call is made.

This is the highest-priority free-to-user operating risk. The correct response is not to charge users for basic chat or weaken answers. It is to enforce a server-side spend envelope, preserve a free core path, and move expensive optional work behind measured utility and resource budgets.

## Verified controls and gaps

| Control | Current repository evidence | Free-to-user assessment | Priority |
|---|---|---|---|
| Anonymous quota | Redis-first atomic reservation; 5 turns/24h default; degraded limit 3; claim/release lifecycle | Real abuse and spend protection | P0 keep |
| Chat concurrency | `max_concurrent_chat=20` per replica; immediate 503 + `Retry-After` on exhaustion | Prevents thundering-herd provider spend | P0 keep |
| LLM concurrency | `llm_queue_max_concurrent=5`, queue max 50 | Limits simultaneous provider work but may increase tail latency | P1 tune from measured queue/provider data |
| Per-request provider cost ceiling | `$0.03` configured | Useful only when the shared guard is enabled and receives reliable usage | P0 enable after drill |
| Daily/monthly OpenRouter envelope | `$0.25` daily / `$6.00` monthly configured in policy | Reservation guard is disabled by default | P0 enable or explicitly document why not |
| Guard failure behavior | `openrouter_budget_fail_closed=true` | Safe when guard is enabled; unavailable Redis blocks provider calls rather than bypassing | P0 test before production |
| Token/cost accounting | Provider-reported cost preferred; model fallback estimate when absent; Supabase token ledger | Observability, not spend enforcement | P0 reconcile model/rate coverage |
| Broader operating budget | `$36/month` soft alert | Cannot prevent overage; exchange rate is fixed and not live | P1 replace with explicit owner-controlled policy |
| Expensive attachments | 10 MB/file, 50 MB total, bounded extraction/context, OCR/transcription timeouts | Good resource bounds; measure actual cost per modality | P1 meter and quota |
| Ingestion worker | Explicit profile/ops control | Avoids idle background burn when serving is idle | P1 retain |
| Admin LLM assistant | Sends KPI/cost/latency context to an LLM for 2–4 sentence answers | Internal cost with no direct end-user value | P1 deterministic-first or admin budget |
| Cache | Namespaced exact/hot/semantic controls; cache-disabled benchmark mode | Can lower repeated cost, but evidence gates must remain | P1 measure safe reuse |
| Pricing source | OpenRouter Models API exposes prompt/completion/request/image/web-search/reasoning/cache pricing and usage fields | Static fallback rates can omit billable dimensions | P0 versioned pricing reconciler |

## Unit-cost model without invented business data

Let `C_request` be actual provider-reported cost when present. When absent, compute a labeled estimate from exact model pricing and token counts:

`C_request = C_prompt + C_completion + C_request_fee + C_web_search + C_image + C_reasoning + C_cache_read + C_cache_write`.

OpenRouter’s official model documentation states that these pricing dimensions are exposed through the Models API and that usage counts vary by tokenizer; therefore, a ledger that records only prompt and completion tokens is incomplete for multimodal, web-search, reasoning, or cache-priced calls [1]. No user volume, actual bill, or request mix was supplied, so this audit does not estimate monthly dollars from the 420-case latency benchmark.

The existing OpenRouter fallback table gives Gemini 3.6 Flash rates of `$0.75/M` input and `$3.75/M` output tokens, but these are repository accounting assumptions and must be reconciled against the provider’s current model metadata before they are used for a financial decision. Provider-reported cost should remain authoritative whenever present.

## Implementation-ready recommendations

### P0 — enforce the free operating envelope before provider work

Run a disposable Redis budget drill with the guard enabled: reservation success, per-request rejection, daily rejection, monthly rejection, actual-cost refund, unknown-cost conservative retention, concurrent reservations, and Redis-unavailable fail-closed behavior. Only after this passes should the deployment owner enable the guard. Keep the core anonymous chat available until the envelope is reached; after that, return a truthful temporary capacity response or deterministic/local fallback where it is safe and grounded.

### P0 — reconcile actual model pricing and billable dimensions

Add a versioned pricing snapshot keyed by exact provider/model ID and record `pricing_snapshot_id`, actual provider cost, estimated cost, input/output tokens, cached tokens, cache-write tokens, reasoning tokens, web-search/image units, and finish reason. Never label an estimate as actual spend. Alert when a model ID is unknown or usage fields are missing rather than silently assigning zero.

### P1 — allocate budgets by workflow, not only tenant

Use separate internal envelopes for routine chat, deep comparison/multihop, translation, attachments, ingestion, admin analytics, and experiments. This allows free users to retain basic safe chat while preventing a rare expensive path from consuming the entire shared budget. Keep workflow names and cost fields internal; do not expose provider or budget policy details in public SSE.

### P1 — deterministic-first internal analytics

The admin assistant should answer routine KPI, latency, and cost questions from deterministic aggregates. Permit an LLM only for questions that cannot be answered by structured data, with an admin-only per-day budget and clear audit attribution. This saves provider spend without changing end-user answers.

### P1 — meter expensive optional modalities

Record CPU seconds and provider cost for OCR, transcription, reranking, graph retrieval, web search, translation, attachments, and ingestion. Apply bounded anonymous quotas and concurrency limits per modality. Do not remove citations or quality checks to reduce cost.

### P2 — adaptive quality/cost routing in shadow mode

Use initial retrieval features and measured provider/queue signals to predict whether HyDE, expansion, heavy reranking, or verification will add enough grounded evidence to justify cost and latency. Run counterfactual evaluation on held-out multilingual, comparative, distress, and out-of-corpus cases before controlling production behavior.

### P3 — free-user value and optional sustainability

Keep core chat, safety, basic citations, and deletion controls free. If sustainability features are considered later, evaluate optional donations, grants, institutional sponsorship, or clearly separated advanced workflows rather than making safety or basic guidance paywalled. No revenue, conversion, retention, CAC, or willingness-to-pay facts are available, so commercial conclusions remain unknown.

## References

[1]: https://openrouter.ai/docs/guides/overview/models "OpenRouter Models API and pricing fields"
