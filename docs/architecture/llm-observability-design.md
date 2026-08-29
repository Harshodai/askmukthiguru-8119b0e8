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
## Correction — Sarvam *is* already instrumented (2026-08-29)

An earlier revision of this document claimed `SarvamCloudService` was uninstrumented. That
was wrong. `services/gateways/sarvam_http.py` has had its own LLM span implementation since
before this work: `_start_llm_span()` (line ~769) plus an inline
`tracer.start_as_current_span("llm.sarvam.chat", ...)` on the main call path (line ~452).

The real problem is not absence, it is **divergence**. There are now three parallel
tracing implementations in the backend:

| Module | Emits | Convention |
|---|---|---|
| `app/tracing.py` | `rag.*` node spans (`trace_rag_node`) | project-local |
| `services/gateways/sarvam_http.py` | `llm.provider`, `llm.model_name`, `llm.token_count.*` | **project-local** |
| `app/llm_tracing.py` (new) | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.*` | **OTel GenAI standard** |

Consequence for phase 2: **Langfuse will parse the OpenRouter spans and ignore the Sarvam
ones**, because Langfuse keys off the `gen_ai.*` convention. Sarvam's cost and token data
would silently not appear in any dashboard. That is a real defect the moment Sarvam becomes
the active provider again.

Two smaller issues in the same file, found while auditing:
- `_start_llm_span()` uses `tracer.start_span()` (manual lifecycle) on the circuit-open path
  at line ~320 and never calls `.end()`. **An OTel span that is never ended is never
  exported**, so that path's span is created, annotated, and silently dropped. The main path
  is unaffected — it uses `start_as_current_span` with explicit `__exit__` calls.
- Its `FakeSpan` no-op stub implements only `__enter__`/`__exit__`, not `set_attribute`.
  This is currently harmless (the main path's `span` comes from `span_ctx.__enter__()` or is
  `None`, never a `FakeSpan`, and `_record_span_exception` guards with `hasattr`), but it is
  a substitutability trap: any future code that treats a `_start_llm_span()` result like a
  real span will `AttributeError` when OpenTelemetry is absent.

**Recommended follow-up (not done here):** migrate `sarvam_http.py` onto `app/llm_tracing.py`
and delete `_start_llm_span`/`FakeSpan`. That collapses three conventions to two, fixes the
unended span, and removes the substitutability trap in one change. It is deliberately not
bundled into this commit — Sarvam is out of credit and not the configured provider as of
2026-08-29, and its `_call_inner` is a ~300-line function with hand-rolled span lifecycle
across four exit paths; that refactor deserves its own change and its own test run.

## SOLID assessment

| Principle | Verdict |
|---|---|
| **SRP** | Partially violated *across modules*, not within them — three modules each own a slice of "trace an LLM call". The fix is consolidation (above), not splitting `llm_tracing.py` further; internally it is one cohesive concern. |
| **OCP** | Satisfied. Adding a provider is `@traced_llm_call("<provider>")` — extension by parameter, no modification of the tracing module. |
| **LSP** | The `FakeSpan` stub in `sarvam_http.py` is a latent violation (incomplete substitute for a real span). `app/llm_tracing.py` avoids it by returning `None` and making every consumer explicitly `None`-tolerant, so there is no partial impostor to misuse. |
| **ISP** | Satisfied. `set_llm_request` / `record_llm_result` / `record_llm_error` are separate small functions; a caller uses only the ones it has data for, rather than implementing one wide interface. |
| **DIP** | Deliberately not applied. A `TracingPort` protocol with adapters was considered and rejected: tracing here is fail-open cross-cutting infrastructure with exactly one implementation, so a port would add an indirection layer with no second implementer and no testing benefit (the module already no-ops without OTel installed). Revisit only if a genuine second backend appears that OTLP export cannot serve. |

[genai]: https://opentelemetry.io/docs/specs/semconv/gen-ai/
