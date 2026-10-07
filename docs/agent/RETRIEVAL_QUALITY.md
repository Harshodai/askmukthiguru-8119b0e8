# Retrieval, knowledge graph and answer-quality standard

Read this before touching ingestion, retrieval, the knowledge graph, or any eval that scores an answer. Read `NON_NEGOTIABLES.md` first; nothing here overrides it (N3 faithfulness and N7 content rights bind everything below).

**Why this file exists.** The architecture choice (Qdrant vector store + a LightRAG-style knowledge graph instead of plain vector RAG) is evidence-backed: graph-augmented RAG beats flat vector RAG on comprehensiveness and diversity in published win-rate evaluations, commonly in the 60 to 85% range. That puts this project ahead of most RAG builds. But architecture is not the same as configuration, and configuration is not the same as measured quality. Most production RAG systems (an estimated 72%) ship without any measured answer-quality metric at all. Do not let this project be one of them by default.

## 1. Audit before you build

Do not assume the pipeline is configured the way the docs describe it. Confirm, with evidence (`path:line`, a config dump, or a query against the running system):

- **Extraction model.** Which model performs entity/relationship extraction during LightRAG ingestion. Practitioner guidance suggests a floor on the order of a 32-billion-parameter class model for reliable extraction; a smaller or cheaper model will silently produce a sparser, noisier graph with no error thrown. Report the model, its parameter class, and whether it meets this bar.
- **Qdrant mode.** Whether collections use hybrid search (dense + sparse vectors, fused with something like Reciprocal Rank Fusion) or dense-only. Sparse/exact matching matters for this corpus because seekers may query using the gurus' own terms (Sanskrit or Telugu words, named practices) where semantic similarity alone under-retrieves.
- **Reranking.** Whether a reranking step runs on retrieved candidates before the final context is assembled, and with what model.
- **Graph schema.** Whether entity/relationship extraction uses a fixed type system (an ontology) or fully open extraction. Open extraction with no schema commonly produces duplicate, disconnected entities for what is really one concept (e.g. "witnessing" and "being aware" as two nodes instead of one).
- **Ingestion completeness.** What share of the intended corpus (all books, all discourses) is actually indexed right now, with a date. Do not trust an old README count.

## 2. Ontology (build if missing) — use OG-RAG as the reference design

Don't build an ad hoc "add some entity types" ontology. Use **OG-RAG (Ontology-Grounded RAG)**, a published Microsoft Research method (EMNLP 2025): it anchors retrieval in a domain ontology by grouping facts into hyperedges of a hypergraph and retrieving a minimal covering set of hyperedges per query, rather than loose chunks. The paper reports (on its own benchmarks, not independently reproduced here) 55% higher recall of accurate facts, 40% better response correctness, 30% faster attribution, and 27% better fact-based reasoning versus baseline RAG. This directly targets faithfulness (N3) and citation speed, which is exactly what this product needs most.

Starting structural type system for this corpus:

- **Entity types:** Teacher, Teaching, Practice/Meditation, State, Obstacle/DistressPattern, Source.
- **Relationship types:** `teaches`, `addresses`, `leadsTo`, `contrastsWith`, `partOf`.
- Seed LightRAG's extraction prompt with this schema so the same underlying concept collapses to one node instead of scattering across near-duplicate entities.
- This is a moderate lift, not a rebuild. It directly improves "ask within a theme" scoping, the mind-map feature, and citation precision.
- Do not invent teachings-specific classifications (which states are "advanced," which practices are "correct") — that is a content judgment for the founder and faculty, not an engineering one. Stick to structural categories (teaching vs. practice vs. state vs. source) and escalate anything that requires doctrinal judgment.

## 3. Answer-quality measurement (build if missing)

Track these continuously against a fixed, versioned question set (reuse the safety and bake-off question sets from Phase B where possible; add retrieval-focused questions):

- **Faithfulness** — the fraction of claims in a generated answer that are actually entailed by the retrieved source passages. This is your primary hallucination and false-attribution signal, directly tied to N3.
- **Answer relevancy** — does the answer address what was actually asked.
- **Context precision and recall** — did retrieval surface the passages actually needed, and how much irrelevant material came along.
- Use an existing framework (e.g. RAGAS or equivalent) rather than inventing metrics from scratch, so results are comparable to published baselines.
- Report results as a number with a date and the question-set version. Never estimate or interpolate a score; if it was not run, write "NOT RUN".

## 4. Ingestion quality (build if missing)

Four separate, checkable dimensions — report each with evidence, not an impression:

1. **Completeness.** Indexed sources vs. the full intended corpus, dated.
2. **Chunking fidelity.** Whether chunk boundaries preserve quotable, verbatim passages. A chunk that splits a sentence breaks both the verbatim-quote rule (N3) and the citation viewer (Phase C).
3. **Metadata completeness.** Every chunk should carry speaker, source title, timestamp or page, and language. Gaps here are gaps in the citation system.
4. **Freshness and dedup.** Whether re-ingesting a source creates duplicate nodes/vectors, and whether there is a process for updates when a rights holder corrects or adds material.

## 5. Scaling: low latency without losing accuracy

A distressed person at 3 a.m. will not wait 90+ seconds. Layer these, in this order of leverage, and measure each change rather than assuming it helped:

1. **Retrieve fewer, better chunks.** Roughly 5 highly relevant chunks typically beats 20 marginal ones — cheaper, faster, and often more faithful because there is less irrelevant context to confuse the model.
2. **Tune the vector index for the actual scale.** HNSW is the standard latency/recall trade-off; for much larger collections, scalar or binary quantization (or IVF-PQ) trades a little precision for large memory and speed gains. Only add this complexity if the corpus size justifies it.
3. **Partition by tenant/type where it narrows the search space** (Qdrant payload-based partitioning by content type, language or teacher), reducing contention under concurrent load.
4. **Keep hybrid + rerank, but protect the reranker from becoming the bottleneck**: pre-filter with a cheaper stage before the expensive cross-encoder, and batch reranking requests under concurrency.
5. **Semantic caching for repeated queries.** Distress-support questions recur across users; a cache keyed on semantic similarity (not exact string match) can cut LLM calls substantially — one production report cited roughly 40%.
6. **Model routing.** Cheap/fast models for classification (intent, risk tier); reserve the most capable model for final answer generation and for LightRAG's entity extraction, where the ~32B-parameter floor in Section 1 applies. Don't downgrade the extraction model to save cost — that's the one place a cheaper model silently breaks quality.
7. **If self-hosting generation**, continuous batching, speculative decoding and quantization at the serving layer matter; if calling the Claude API directly for any stage, look at prompt caching for large repeated context (check current docs at https://docs.claude.com/en/api/overview before implementing, since specifics change).

**Do not trust published throughput numbers, including any cited in this document's companion dossier** — vector-database benchmark blogs date quickly and are often vendor-adjacent. Measure latency and recall on the real corpus and real hardware before and after any change, and report both numbers.

## 6. What this does and does not fix

Closing the gaps in this file can move the "Technical" scorecard dimension meaningfully, because this work is entirely agent-doable with evidence. It does **not** substitute for the human-only gates elsewhere (clinician safety sign-off, rights approvals, a real pilot). A perfectly measured retrieval pipeline serving unregistered content, or answering a Tier-3 crisis with a beautifully faithful citation, is still a failure under N7 and N1 respectively. Retrieval quality is necessary, not sufficient.
