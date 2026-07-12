# OKF ingestion & anti-hallucination architecture

How Mukthi Guru avoids inventing doctrine, from ingestion through to the answer the seeker reads.
Written 2026-07-12 after a live-stack check post-Docker-rebuild (see "Current known gap" below).

## 1. OKF — the Karpathy LLM-wiki pattern applied to doctrine

[OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) formalizes
Andrej Karpathy's "LLM-wiki": a bundle of markdown files, one concept per file, YAML frontmatter with
only `type` required. `memory/okf/` (repo root) is our **doctrine bundle** — Sri Preethaji & Sri
Krishnaji's teachings, and nothing else. Every live entry is embedded and injected verbatim into
answers, so anything in it is quoted to a seeker *as doctrine*.

**Current state:** 25 live entries (20 `teaching`, 2 `practice`, 1 `glossary` — no `qa`/`reflection`
entries yet) + 1 unreviewed entry in `staging/`. `MASTER_REMEDIATION_PLAN.md` Part E flagged 22 entries
as "thin" for coverage; at 25 it's grown slightly but is still thin relative to the underlying corpus
(89,053 Qdrant chunks, 7,564 Neo4j nodes). This is the honest gap — OKF is a curated, reviewed layer on
top of the much larger raw retrieval index, not a replacement for it.

**Three invariants, enforced once at `OKFStore.list_entries()` (the single chokepoint for the compiler
and the admin API):**
1. **Doctrine types only** — `{teaching, practice, glossary, qa, reflection}`. Anything else (a runbook,
   an engineering note) is skipped. Engineering notes live here, in `docs/engineering-notes/`, never in
   the bundle.
2. **Provenance mandatory** — an entry with empty `source` is uncitable, so `format_final_answer` can't
   attribute it. Rejected at load time.
3. **No extraction artifacts** — `OKFQualityFilter` rejects RAPTOR debug headers, `_(Source: unknown)_`,
   and the extraction LLM's own prompt commentary leaking into the body.

**The review gate is a filter, not a folder-depth trick:** `list_entries()` uses `rglob` (needed for the
`sri-preethaji/`/`sri-krishnaji/`/`shared/` subdir layout) and excludes `staging/` and `_scripts/` via an
explicit `_excluded_parts` set. Dropping that filter — even while "fixing" the glob to look more
correct — is the failure mode `tests/test_okf_pipeline_integrity.py` exists to catch: it would let
unreviewed, LLM-generated doctrine reach `compiled.json` and get quoted to a seeker as fact.

**Pipeline:**
```
ingestion (per video, rag_okf_auto_extract_enabled=true)
  → extract_okf(auto_approve=False) → memory/okf/staging/*.md   (unreviewed)
  → admin approves (POST /api/admin/okf/review/{id}/approve)    ← editorial act, not a formality
  → memory/okf/*.md (live) → compile_okf() → memory/okf/compiled.json
  → _load_okf_entries() (per-process cache) → injected into every non-CASUAL query
```
Ingestion only ever *appends to staging* — it can't silently overwrite a live, reviewed entry. Nothing
reaches an answer until a human approves it and someone recompiles.

**Glossary maintenance:** the `glossary` type is exactly this system's mechanism for keeping doctrinal
terms consistent (e.g. "Ekam" vs. transliteration drift) — one entry per term, `compiler.py` embeds
`title + description` (not the bare title) so a seeker's natural-language question ("why do I keep
suffering?") matches against the description, not just a keyword.

## 2. How an answer avoids hallucinating

Every `/api/chat` request runs through `PipelineCoordinator` (pre/post stages) wrapping a ~20-node
LangGraph (`rag/graph_strategies.py`). The anti-hallucination guarantees are layered, not a single
check:

| Layer | Mechanism | What it catches |
|---|---|---|
| **Retrieval breadth** | RAPTOR summaries + leaf chunks + LightRAG graph + Parent-Child + MMR, plus OKF injection | Answering from too little context |
| **CRAG** | `grade_documents` — batch relevance grading; rewrites the query up to 3x if docs are weak | Retrieval that missed the point of the question |
| **Sufficiency gate** | `check_context_sufficiency` — clears cluster filters and retries if context is thin | Confidently answering from insufficient evidence |
| **Self-RAG** | `reflect_on_answer` — **LettuceDetect only** (embedding + lexical faithfulness); LLM self-consistency is disabled to save ~45s with no measured quality loss on spiritual paraphrasing | The generated answer drifting from the retrieved text |
| **Verification** | `verify_answer` — LettuceDetect at threshold 0.22 + doctrine boost; CoVe sub-question verification and alternative-answer self-consistency are **disabled** (save ~60s); fast-tier queries skip this node entirely | Unfaithful claims slipping past reflection |
| **Contradiction check** | `check_contradiction` — compares against conversation history | The model contradicting itself across turns |
| **Graduated confidence** | `format_final_answer` — confidence-based response shape + citation formatting + caveats | Overconfident phrasing on marginal evidence |
| **Guardrails** | Zero-shot input rail (blocks harmful/off-topic) + zero-shot output rail (moderates before the seeker sees it) | Off-topic or harmful content in either direction |
| **Doctrine-terms system** | Corrects known transliteration drift (e.g. rewrites "Akam" → "Ekam") | Retrieval-time term confusion |

**Deliberate cost/latency trade-offs, not gaps:** LLM self-consistency (Self-RAG) and CoVe are both wired
into the codebase but switched off — LettuceDetect alone was measured to hold faithfulness quality while
saving ~105s combined. If quality regresses in production, re-enabling them is a config flip, not new
code.

## 3. Current known gap (found during this check, 2026-07-12)

Live-stack check after a Docker rebuild: primary retrieval is fully intact —
Qdrant `spiritual_wisdom` = 89,053 vectors, Neo4j = 7,564 nodes (matches the ~7,512 documented after the
ontology expansion). **But LightRAG's own working-directory bookkeeping (`/app/data/lightrag/`) has only
a stale `kv_store_llm_response_cache.json` — no `full_relations`, `entity_chunks`, `relation_chunks`, or
`doc_status` records.** `KNOWLEDGE_GRAPH_QUERY_ENABLED` calls `lightrag.aquery()` directly
(`rag/nodes/retrieval.py:584`); with doc_status at 0, LightRAG believes it has ingested nothing and
returns empty context on every call — silently, no error, no crash.

**Impact:** this degrades retrieval *depth* (the per-query graph-traversal signal CLAUDE.md notes was
enabled specifically because the ontology expansion made it useful), not correctness — the CRAG/Self-RAG/
verification layers above still gate everything that does make it into an answer, and the base
Qdrant+Neo4j-ontology-seeded retrieval is untouched. It is not the cause of wrong answers; it's a
completeness regression.

**Fix:** LightRAG's KV state is populated only by `lightrag.ainsert()`, which runs inside the ingestion
pipeline (`ingest/pipeline.py`), not by any Neo4j/Qdrant restore. Re-populating it means re-running
ingestion for previously-ingested content so `ainsert()` rebuilds the working-dir JSON files — there is
no lighter-weight "reindex" entry point currently. This is compute-heavy (same caveat
`MASTER_REMEDIATION_PLAN.md` Part E gives OKF auto-extraction) — flagging it rather than running it
unprompted.
