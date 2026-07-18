# Deep-Module-Refactor Blueprint — AskMukthiGuru backend

**Skill applied:** `deep-module-refactor` (John Ousterhout, *A Philosophy of
Software Design* — a **deep module** has a small interface hiding a large
implementation; you test at the boundary, not inside).

**Method:** I explored the codebase as an AI navigates it and noted where
understanding one concept forces bouncing between many shallow files. The
friction points below are the signal. For each I give the cluster, why it's
coupled, the deepened interface, and the boundary test that replaces the
scattered ones. Two of the four are **already implemented** in this pack.

---

## Candidate 1 — LLM access (IMPLEMENTED → `llm_gateway.py`)

- **Cluster:** `services/sarvam_service.py` (1209 lines),
  `services/ollama_service.py` (1022 lines), plus provider calls scattered
  through `rag/nodes/*` and `services/*`.
- **Why coupled / shallow:** two parallel provider modules with near-identical
  responsibilities and no shared protocol. Every caller re-implements retry,
  timeout, and (inconsistently) caching. To answer "how does the app call an
  LLM?" you must read 2200+ lines across two files. This is the textbook
  *shallow module* — interface nearly as complex as implementation.
- **Deepened interface (chosen):** one `LLMGateway.complete(prompt, task=…)`
  — a 6-method surface hiding providers, circuit breakers, tiered fallback,
  model routing, and coalesce caching. Callers never touch a provider.
- **Why this design (of 3 considered):** I weighed (a) minimal 2-method
  gateway, (b) a fully configurable policy engine, (c) the pragmatic
  protocol+gateway hybrid. Chose (c): `LLMProvider` protocol keeps adapters
  trivial, the gateway hides the resilience logic. (a) was too rigid for
  task-based routing; (b) was over-engineering for two providers.
- **Boundary test:** `test` in the module — fallback, circuit-breaker, and
  single-flight coalescing all verified with fakes (no network). This replaces
  per-provider unit tests that tested the *inside* of each service.
- **Status:** ✅ implemented + tested (`backend/services/llm_gateway.py`).

## Candidate 2 — Retrieval (IMPLEMENTED → `graphrag_fusion.py`)

- **Cluster:** `rag/nodes/retrieval.py` (1166 lines), `rag/nodes/generation.py`
  (1468 lines), Qdrant calls, Neo4j calls, the OKF matcher.
- **Why coupled / shallow:** vector retrieval, graph retrieval, reranking,
  and budget-truncation are interleaved inside giant node functions. The
  "how does context get assembled?" concept is smeared across two files and
  three storage backends. Graph retrieval is effectively an afterthought —
  the doctrine KG isn't a first-class channel.
- **Deepened interface:** `GraphRAGFusion.retrieve(question) -> FusedContext`
  — one call that runs both channels concurrently, fuses via RRF, budgets
  tokens, and returns provenance-tagged items ready for the prompt.
- **Boundary test:** module self-test verifies multi-hop, dedup
  corroboration, and token budgeting with injected fakes.
- **Status:** ✅ implemented + tested
  (`backend/services/graphrag_fusion.py`).

## Candidate 3 — Memory / personal knowledge (PARTIALLY → see vault)

- **Cluster:** `services/memory_service.py` (37 KB) **and**
  `services/memory_service_v2.py` (50 KB), `app/api/memory.py`, plus the new
  `seed_personal_kg.py`.
- **Why coupled / shallow:** two overlapping memory services (a half-finished
  migration). "What does the app remember about a user?" requires reading
  both services and three storage tiers. No encryption anywhere.
- **Deepened interface:** consolidate to ONE memory service behind a small
  protocol (`remember / recall / forget / export`), and make the **Second
  Brain vault** the encrypted per-user store beneath it.
- **Boundary test:** the vault's 6-test suite (isolation, Mode-B lock,
  shredding) is the boundary test; the old per-tier tests get deleted.
- **Status:** 🟡 the encrypted vault is implemented + tested
  (`backend/services/second_brain/`); the **v1/v2 consolidation is your next PR** —
  pick v2's tier model, put the vault under it, delete v1.

## Candidate 4 — Ingestion (PROPOSED)

- **Cluster:** `ingest/pipeline.py` (**2837 lines**) — the god-module.
- **Why coupled / shallow:** every content source (YouTube, Whisper, web,
  files) is handled inside one file. Adding a source means editing a
  2800-line function maze. You already solved this *pattern* for
  transcription (`TranscriptionProvider` protocol) — apply it here.
- **Deepened interface:** a `ContentSource` protocol —
  `load(source) -> Iterator[RawDoc]` per source type, with the orchestrator
  just fanning out. The ContentSource registry enforces an **approval
  boundary**: only approved Sri Preethaji/Sri Krishnaji YouTube material
  and approved images are allowlisted; provenance must be validated before
  loading. General web, files, Whisper, or arbitrary source types are
  excluded unless they satisfy that allowlist.
- **Boundary test:** each source tested with a fixture; the orchestrator
  tested with fake sources. The 2837-line file shrinks to a ~200-line router.
- **Status:** 📐 proposed; reference source implemented
  (`backend/ingestion/web_ingest_pipeline.py`).

---

## The one-line summary

The codebase's deepest friction is **duplication and god-modules**: two LLM
services, two memory services, one 2837-line ingester. The fix in every case
is the same Ousterhout move — *deepen the module*: a small protocol at the
boundary, the complexity hidden behind it, tests at the boundary. Two of the
four are done and tested in this pack.

## Suggested PR order (each small & reversible)

1. `llm_gateway.py` — put providers behind the gateway (biggest blast-radius
   reducer; do first).
2. Second-Brain vault — additive, no existing behavior changes.
3. `graphrag_fusion.py` — wire into `retrieval.py` as the context assembler.
4. Memory v1/v2 consolidation — deletion PR after v2+vault is live.
5. `ContentSource` ingestion split — mechanical, do last.
