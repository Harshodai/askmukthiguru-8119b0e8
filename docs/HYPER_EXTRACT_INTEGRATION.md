# Hyper-Extract Integration — Phase 5.3

## Source Repository

- **URL:** https://github.com/yifanfeng97/hyper-extract
- **License:** Apache 2.0
- **What it does:** Hyper-Extract is an LLM-powered knowledge extraction and evolution framework. It converts unstructured documents (PDFs, Markdown, text) into strongly-typed "Knowledge Abstracts" such as lists, Pydantic models, knowledge graphs, hypergraphs, temporal graphs, and spatio-temporal graphs. It exposes a CLI (`he`) and a Python API built around YAML templates, Pydantic schemas, and structured LLM output (`json_schema` / function calling). It bundles 10+ extraction engines (GraphRAG, LightRAG, Hyper-RAG, KG-Gen, ATOM, etc.) and 80+ domain templates.

## Techniques Applicable to Mukthi Guru

After reviewing the README, core modules, and extraction engines, the following ideas are directly useful for our spiritual transcript / PDF ingestion pipeline:

1. **Document Structure Parsing** — Hyper-Extract parses raw documents before extraction. For transcripts this maps to detecting section headers, timestamps, and topic boundaries so that downstream chunks stay semantically coherent.
2. **Atomic Fact Extraction** — The ATOM engine decomposes text into temporally grounded, self-contained factoids. For spiritual transcripts this means breaking long discourses into short, verifiable statements that are easier to retrieve and less prone to hallucination.
3. **Entity Linking / Knowledge Graph Edges** — GraphRAG and LightRAG engines extract entities and binary relationships. For our domain this identifies teachers (Sri Preethaji, Sri Krishnaji), concepts (Beautiful State, Serene Mind, Ego), and relations such as "teaches", "dissolves", "restores".
4. **Two-Stage Extraction** — Hyper-Extract often extracts nodes first, then edges using the known node list. This reduces hallucinated relationships and keeps entity names consistent.
5. **Deduplication / Merging** — Hyper-Extract uses OMem and SemHash to merge duplicate entities and edges. For our lightweight port we use deterministic lower-cased keys instead of LLM merging.

## What Was Ported vs Skipped

### Ported into `backend/ingest/hyper_extract_adapter.py`

| Hyper-Extract Idea | Lightweight Port |
|---|---|
| Document structure parsing | Paragraph + timestamp/header heuristics in `_detect_sections()` |
| Atomic fact extraction | Sentence splitting + pronoun resolution in `_extract_atomic_facts()` |
| Entity extraction | Curated spiritual entity list + conservative proper-noun heuristic |
| Relationship extraction | Entity co-occurrence + verb detection in `_extract_relationships()` |
| Two-stage extraction | Entities are collected first; edges are derived from facts containing those entities |
| Deduplication | Lower-cased key dictionary keeps canonical/longest forms |

### Skipped

| Hyper-Extract Feature | Why Skipped |
|---|---|
| LLM-based structured extraction (Pydantic schemas, JSON mode, function calling) | Requires many LLM calls; violates the $0 budget and <3s ingestion-time constraints |
| OMem / SemHash / ontomem deduplication engines | Heavy external dependencies not in `backend/requirements.txt` |
| YAML template engine and 80+ presets | Overkill for our single spiritual domain; adds maintenance surface |
| Hypergraph, temporal graph, spatial graph types | Not needed for retrieval quality; binary edges suffice |
| GraphRAG/LightRAG community detection and reporting | Requires `networkx` / `graspologic`; we already have LightRAG integration for graph indexing |
| MCP server / CLI / Obsidian export | Out of scope for the ingestion pipeline |

### Rationale

The project constraints from `SPEC_DEV.md` are non-negotiable: $0 budget, local-only processing, open-source dependencies, <1% hallucination, <3s response time. A full Hyper-Extract port would add heavy LLM orchestration at ingestion time and pull in packages that are not already installed. The adapter therefore implements the *retrieval-quality ideas* deterministically, using only the Python standard library and patterns that are safe on noisy transcripts.

## How It Improves Retrieval Quality

1. **Better context for chunking** — Detected section titles are preserved in the structured output. Future work can prepend section headers to chunks or use them as metadata filters in Qdrant.
2. **Atomic facts as retrievable units** — Long, meandering sentences are split into concise, self-contained facts. These can later be indexed as supplementary chunks or used to validate generation faithfulness.
3. **Entity normalization** — Known spiritual terms (e.g., "Sri Preethaji", "Beautiful State") are recognized even with casing variations. This reduces vocabulary mismatch between user queries and indexed text.
4. **Relationship hints** — Extracted `(source, relation, target)` tuples feed the existing LightRAG / knowledge-graph path and can surface connections that lexical search alone misses.
5. **Fail-soft enrichment** — The adapter is optional, bounded by length checks, and swallows its own errors. Ingestion continues even if enrichment fails, so it cannot block the pipeline.

## Configuration

All flags live in `backend/app/config.py` and are env-overridable via `.env`:

```python
# --- Hyper-Extract enrichment (Phase 5.3) ---
use_hyper_extract_enrichment: bool = False  # Enable lightweight structure/entity/fact extraction
hyper_extract_min_chars: int = 200          # Skip texts shorter than this
hyper_extract_max_chars: int = 50_000     # Hard cap to keep enrichment fast and safe
```

To enable:

```bash
# backend/.env
USE_HYPER_EXTRACT_ENRICHMENT=true
HYPER_EXTRACT_MIN_CHARS=200
HYPER_EXTRACT_MAX_CHARS=50000
```

When enabled, `IngestionPipeline.ingest_raw_text()` and `_ingest_video()` run the adapter after cleaning and redacting PII. The structured result is returned under the `hyper_extract` key in the ingestion response.

## Public API

```python
from ingest.hyper_extract_adapter import enrich_text, is_eligible

result = enrich_text(clean_transcript_text)
# result == {
#     "sections":       [{"title": ..., "start_index": ..., "end_index": ..., "text": ...}],
#     "atomic_facts":   ["Sri Krishnaji teaches that observation dissolves the ego", ...],
#     "entities":       ["Sri Krishnaji", "Ego", "Observation", ...],
#     "relationships":  [("Sri Krishnaji", "teaches", "Observation"), ...],
# }
```

## Tests

Unit tests are in `backend/tests/test_hyper_extract_adapter.py` and cover:

- Empty input
- Short input below `min_text_length`
- Section detection on a structured transcript
- Entity extraction on known spiritual terms
- Relationship extraction
- Config flag disabling enrichment
- Pipeline integration returning / omitting `hyper_extract` based on the flag

Run with:

```bash
rtk proxy python3 -m pytest backend/tests/test_hyper_extract_adapter.py backend/tests/test_ingestion_pipeline.py -q --tb=short
```

## Future Extensions

1. **Index atomic facts as separate chunks** — Add a mode that appends `atomic_facts` as small, dense chunks to Qdrant with a `fact` content type so the retriever can match precise statements.
2. **Metadata tagging from entities** — Promote extracted entities into chunk `tags` so assistant-aware tag filters can narrow retrieval by teacher or concept.
3. **Indic-language sentence boundaries** — Extend `_SENTENCE_RE` and `_PROPER_NOUN_RE` for Hindi, Telugu, Tamil, and other transcript languages.
4. **LLM fallback (bounded)** — When Sarvam Cloud is available and the text is high-value, optionally run a single small-prompt LLM pass to improve relationship extraction while keeping the deterministic fallback.
5. **Cross-source entity merging** — Build a small, in-memory canonical entity table across ingestion runs so "Preethaji" and "Sri Preethaji" resolve to the same node without heavy graph operations.
