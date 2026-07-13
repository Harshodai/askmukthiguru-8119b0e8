# OKF ingestion & anti-hallucination architecture

How Mukthi Guru avoids inventing doctrine, from ingestion through to the answer the seeker reads.
Written 2026-07-12 after a live-stack check post-Docker-rebuild (see "Current known gap" below).

## 1. OKF — the Karpathy LLM-wiki pattern applied to doctrine

[OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) formalizes
Andrej Karpathy's "LLM-wiki": a bundle of markdown files, one concept per file, YAML frontmatter with
only `type` required. `memory/okf/` (repo root) is our **doctrine bundle** — Sri Preethaji & Sri
Krishnaji's teachings, and nothing else. Every live entry is embedded and injected verbatim into
answers, so anything in it is quoted to a seeker *as doctrine*.

**Current state:** 23 live entries (20 `teaching`, 2 `practice`, 1 `glossary` — no `qa`/`reflection`
entries yet) + 1 unreviewed entry in `staging/`. `MASTER_REMEDIATION_PLAN.md` Part E flagged 22 entries
as "thin" for coverage; at 23 it's grown slightly but is still thin relative to the underlying corpus
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
| **Sufficiency gate** | Folded into `grade_documents` (CRAG) — `backend/rag/nodes/reranking.py:304` clears cluster filters and retries if context is still thin after relevance grading | Confidently answering from insufficient evidence |
| **Self-RAG** | `reflect_on_answer` — **LettuceDetect only** (embedding + lexical faithfulness); LLM self-consistency is disabled to save ~45s with no measured quality loss on spiritual paraphrasing | The generated answer drifting from the retrieved text |
| **Verification** | `verify_answer` — LettuceDetect at `settings.faithfulness_floor` (default 0.6) + doctrine boost; CoVe sub-question verification and alternative-answer self-consistency are **disabled** (save ~60s); fast-tier queries skip this node entirely | Unfaithful claims slipping past reflection |
| **Contradiction check** | _removed_ — `graph_strategies.py:444` comment: branches removed as buggy; absence pinned by `tests/test_graph_strategy_wiring.py:82, :101` | _(retired — gap by design, tests pin removal)_ |
| **Graduated confidence** | `format_final_answer` — confidence-based response shape + citation formatting + caveats | Overconfident phrasing on marginal evidence |
| **Guardrails** | Zero-shot input rail (blocks harmful/off-topic) + zero-shot output rail (moderates before the seeker sees it) | Off-topic or harmful content in either direction |
| **Doctrine-terms system** | `services/doctrine_terms.py:apply_corrections` (dict at line 30) rewrites transliteration drift at ingestion + query time (e.g. "Akam" → "Ekam"); pinned by `tests/test_doctrine_terms.py:35`. Phoneme backward-compat at `services/phonetic.py:109` is a separate path. | Retrieval-time term confusion |

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

**Update (2026-07-12, deeper probe):** the gap is wider than just the JSON working-directory. Verified against the live stack:

1. **Qdrant LightRAG vector collections are empty**: `lightrag_vdb_chunks_baai_bge_m3_1024d`, `lightrag_vdb_entities_baai_bge_m3_1024d`, `lightrag_vdb_relationships_baai_bge_m3_1024d` all report `points_count: 0` (verified via `GET /collections/{c}` on the Qdrant API).
2. **Neo4j's LightRAG graph store is empty**: `MATCH (n:LIGHTRAG) RETURN count(*)` = 0; `MATCH ()-[r:LIGHTRAG]->() RETURN count(r)` = 0. The 7,418 `:base` ontology nodes are intact (seeded by `app/db/seed_ontology.py`, separate from LightRAG).
3. **Container `/app/data/lightrag/` is missing every KV-store file except `kv_store_llm_response_cache.json`** — all of `doc_status / full_entities / full_relations / entity_chunks / relation_chunks / full_docs / text_chunks` are absent.
4. **Stale host-side `data/lightrag/*.json` (~446 MB, dated May 26 / Jun 15) exists at the repo root and must NOT be copied into the container.** These have `doc_status` keys marking 4,286 docs as `status="processed"` and `full_relations/full_entities` matching the prior 2,200-relations / 2,365-entities baseline. Copying them would mark every doc as already-ingested; LightRAG's `ainsert` would then filter all duplicates at `lightrag/lightrag.py:1453` and skip building the Qdrant vector + Neo4j graph stores — leaving the live gap in place **permanently**.

**Root cause:** `docker compose down -v` purged the named volume `telemetry_data` (mounted at `/app/data`, per `backend/docker-compose.yml:248` and volume declaration at `:425-426`). Host-side `data/lightrag/*.json` survived because they sit at the repo root, not on the named volume. **Do not use `down -v` when reloading the stack** — `docker compose down` (no `-v`) preserves named volumes.

**Fix:** re-run ingestion from inside the container so `ainsert()` rebuilds all three stores consistently. The canonical replay script is `backend/scripts/migrate_data.py`; it scrolls leaf chunks from the intact `spiritual_wisdom` Qdrant collection (89,053 points), reconstructs full text per `source_url`, and re-ingests via `pipeline.ingest_raw_text(max_accuracy=True)` which fires `ainsert` at `backend/ingest/pipeline.py:699`.

**Impact:** this degrades retrieval *depth* (the per-query graph-traversal signal CLAUDE.md notes was
enabled specifically because the ontology expansion made it useful), not correctness — the CRAG/Self-RAG/
verification layers above still gate everything that does make it into an answer, and the base
Qdrant+Neo4j-ontology-seeded retrieval is untouched. It is not the cause of wrong answers; it's a
completeness regression.

**Compute caveat:** the replay re-embeds and re-RAPTORs the entire `spiritual_wisdom` corpus (borderline
~89k leaf chunks), not just the graph store — no lighter-weight "graph-only reindex" entry point currently
exists. Same caveat `MASTER_REMEDIATION_PLAN.md` Part E gives OKF auto-extraction. Flagged rather than
run on the user's behalf unprompted.
