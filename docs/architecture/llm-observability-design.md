# LLM Observability Design — GenAI spans + optional Langfuse

**Status:** design + phase 1 implemented · **Date:** 2026-08-29 · **Owner:** Architecture

## Problem

LLM call observability is fragmented across three places, none of which capture what a
debugging session actually needs:

| Where | What it has | What it's missing |
|---|---|---|
| `logger.info("OPENROUTER_CALL_TIMING ...")` (`services/openrouter_service.py`) | model, operation, attempts, tokens, cost, finish_reason | **no prompt, no completion**; unstructured text, not queryable |
| Redis trace dashboard (`app/trace_dashboard.py`, 24h TTL) | pipeline *stage* timings and decisions | stage-level only — never sees an individual LLM call |
| Jaeger / OTel (`app/observability.py`) | FastAPI request spans, LangChain spans | **our LLM calls bypass it entirely** — see below |

### The specific gap

`app/observability.py` installs `LangChainInstrumentor()`, which emits proper GenAI spans
with prompts and completions — but `OpenRouterService` and `SarvamCloudService` make **raw
`httpx` calls**, not LangChain calls. So the instrumentation that would capture prompt and
completion text is installed and running against a code path we don't use. Every real LLM
call in the RAG pipeline (~8 per ingested video, several per chat query across ~20 LangGraph
nodes) is invisible to it.

Two 2026-08-29 incidents cost hours that this would have made obvious:
- An over-broad regex in `text_quality_filter.py` silently quarantined valid doctrine. Root
  cause required manually grepping the ingestion log and reconstructing which text was
  rejected. A queryable trace of "input text → verdict" would have surfaced it immediately.
- A self-imposed `$10/day` `OpenRouterBudgetGuard` cap rejected ~1,628 calls with an error
  string that read like a provider fault. Cost-per-trace rollup would have shown the spend
  curve flatlining against a ceiling, not a provider outage.

## Constraint that shapes the design

**Langfuse's OTLP endpoint accepts HTTP only — gRPC is not supported.**
`app/observability.py:52` currently uses `opentelemetry.exporter.otlp.proto.grpc`
against `http://jaeger:4317`. So Langfuse cannot simply reuse the existing exporter; it
needs a second, HTTP-protocol exporter alongside it.

**Host memory is already the binding constraint.** Self-hosted Langfuse v3 is not one
container — it's `web` + `worker` + Postgres + ClickHouse + Redis + MinIO. On a 16GB
machine already running Qdrant, Neo4j, Redis, and Jaeger (and observed swapping at 90%+
during ingestion, 2026-08-29), adding that stack is not currently viable.

## Design

Split into two independent phases so the valuable part ships without the heavy part.

### Phase 1 — GenAI-semantic-convention spans (no new infrastructure) ✅ implemented

Emit OpenTelemetry spans following the [GenAI semantic conventions][genai] directly from
the LLM service layer, where model/tokens/cost/finish_reason are already computed. These
flow to the **existing** Jaeger via the **existing** exporter — zero new services, and
Jaeger's UI immediately becomes useful for LLM debugging.

`app/llm_tracing.py` provides one context manager:

```python
with llm_span(operation="generate", model=model, provider="openrouter",
              prompt=messages) as span:
    ...
    record_llm_result(span, completion=content, tokens_in=..., tokens_out=...,
                      cost_usd=..., finish_reason=...)
```

It is **fail-open by construction**: if OpenTelemetry isn't installed, isn't initialized,
or the span operations raise, the context manager yields `None` and the LLM call proceeds
untouched. Observability must never take down inference.

**Prompt/completion capture is opt-in** (`LLM_TRACE_CONTENT=true`, default `false`) and
truncated to `LLM_TRACE_CONTENT_MAX_CHARS` (default 2000). Seeker questions are personal
and the corpus is doctrine — content capture is a deliberate decision, not a default. See
`docs/runbooks/PRIVACY.md` before enabling it in any environment with real user traffic.

### Phase 2 — Langfuse as an additional OTLP/HTTP destination (deferred)

When host capacity allows (or when Langfuse runs off-box), add a second
`BatchSpanProcessor` with an HTTP exporter pointed at Langfuse's `/api/public/otel`
endpoint. Because Phase 1 emits standard GenAI conventions, **Langfuse parses those spans
natively — no re-instrumentation.** That's the point of doing Phase 1 in the standard
rather than inventing a custom span shape.

Gated behind `LANGFUSE_ENABLED` (default `false`) so the code path exists and is reviewed,
but nothing runs until deliberately switched on:

```
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...     # env only, never committed
LANGFUSE_SECRET_KEY=sk-lf-...     # env only, never committed
```

Auth is HTTP Basic (`base64(public_key:secret_key)`) in the OTLP headers.

**Deliberately not chosen:** the `langfuse` Python SDK. It installs and configures its own
TracerProvider, which would conflict with the one `init_observability()` already owns. The
OTLP-exporter route keeps a single provider and a single span pipeline, with Langfuse as
one more destination.

## What this does not solve

- Cost attribution per *seeker* or per *conversation* still needs a session/user id
  propagated onto spans; Phase 1 emits per-call cost only.
- Prompt versioning / playground / dataset-eval features are Langfuse-application features,
  unavailable until Phase 2 actually runs.
- `SarvamCloudService` is not yet instrumented (OpenRouter is the configured provider as of
  2026-08-29); it needs the same two-line treatment when it returns to use.

[genai]: https://opentelemetry.io/docs/specs/semconv/gen-ai/
