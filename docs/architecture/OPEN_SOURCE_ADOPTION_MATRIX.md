# Open-Source Adoption Matrix — Ask Mukthi Guru

**Decision date:** 2026-08-14. **Scope:** multi-teacher spiritual RAG, provenance, ingestion quality, evaluation, observability, and future GPU serving.

## Executive decision

Do not replace the current Qdrant + Neo4j + LangGraph pipeline wholesale. The safer path is to preserve the existing source-release, rights, provenance, and tenant contracts, then add bounded adapters behind flags. The highest-value near-term adoption is **Docling for candidate document parsing**, **Ragas/Phoenix for held-out evaluation and tracing**, and **Neo4j’s first-party GraphRAG package for a retrieval spike**. Graphiti is a strong later candidate for temporal interaction/context graphs, but it must not own doctrinal truth or bypass the source-release registry.

## Candidate comparison

| Candidate | Evidence and license | Fit | Recommendation | Main guardrail |
|---|---|---|---|---|
| [Graphiti](https://github.com/getzep/graphiti) | Apache-2.0; 29k+ stars; temporal entities, facts, episodes, provenance, prescribed/learned ontology, hybrid retrieval | Strong for evolving user/context graphs and historical facts | **Spike behind flag**; keep Neo4j as the system of record initially | Every episode/edge must carry teacher, source release, rights status, and provenance span; no cross-teacher merge by name alone |
| [Docling](https://github.com/docling-project/docling) | MIT; 64k+ stars; layout-aware PDF, DOCX, HTML, audio/video/ASR, OCR, local execution | Strong for PDFs, scanned books, tables, and structured documents | **Adopt as a candidate parser** before semantic chunking | Preserve raw bytes, parser version, page/span coordinates, language, and rights; never publish directly |
| [Unstructured](https://github.com/Unstructured-IO/unstructured) | Apache-2.0; 15k+ stars; broad partitioning and connectors; optional analytics ping | Broad fallback for heterogeneous formats and batch connectors | **Keep as fallback/benchmark**, not a second default parser | Set analytics opt-out; pin extras; compare outputs against Docling on a golden corpus |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | MIT; 35k+ stars; local/global/DRIFT search and hierarchical communities | Useful research reference for corpus-level synthesis | **Do not adopt as runtime dependency now**; project says it is largely maintenance mode | Indexing cost and re-ingestion risk; use ideas selectively |
| [Neo4j GraphRAG Python](https://github.com/neo4j/neo4j-graphrag-python) | First-party Neo4j package; Apache/Python licensing files; active package with KG builder and retrievers | Directly compatible with existing Neo4j and Qdrant | **Build a measured retrieval spike** | No direct writes to production graph; enforce existing ontology and release IDs |
| [Ragas](https://github.com/vibrantlabsai/ragas) | Apache-2.0; 15k+ stars; objective metrics, test generation, feedback loops | Strong for held-out retrieval/answer evaluation | **Adopt in evaluation environment only** | Redact prompts/PII, pin model/judge versions, store dataset/version and confidence intervals |
| [Phoenix](https://github.com/Arize-ai/phoenix) | Open source; 11k+ stars; OpenTelemetry tracing, evals, datasets, experiments; LangGraph/OpenRouter integrations | Strong for debugging latency, retrieval, and model regressions | **Optional staging observability service** | Never expose traces publicly; sample/redact user text and secrets |
| [vLLM](https://github.com/vllm-project/vllm) | Apache-2.0; 89k+ stars; continuous batching, prefix caching, structured output, OpenAI-compatible API | Best default future GPU serving candidate | **Benchmark after funding/GPU availability** | Separate inference service; preserve gateway policy, budgets, timeouts, and rollback |
| [SGLang](https://github.com/sgl-project/sglang) | Apache-2.0; 31k+ stars; radix attention, structured outputs, multi-GPU/TPU support | Strong alternative for low-latency high-throughput serving | **Benchmark against vLLM on target Sarvam model** | No production switch without TTFT/quality/cost parity and a reversible endpoint flag |

## Integration order

1. Add parser adapters that emit the existing canonical source/chunk/provenance contract; benchmark Docling and Unstructured on a rights-approved golden set.
2. Add Ragas/Phoenix only to offline/staging evaluation and trace redaction paths; do not add judge calls to the user request path.
3. Run a Neo4j GraphRAG retrieval spike in a disposable namespace and compare recall, citation precision, latency, and memory against the current retriever.
4. Prototype Graphiti only for temporal user/context episodes and historical teaching metadata; keep doctrinal claims governed by the source-release registry.
5. Benchmark vLLM and SGLang as interchangeable OpenAI-compatible upstreams on funded GPU infrastructure; choose by measured TTFT, throughput, structured-output validity, and operating cost.

## Sources

[1]: https://github.com/getzep/graphiti — Graphiti official repository and README.
[2]: https://github.com/docling-project/docling — Docling official repository and README.
[3]: https://github.com/Unstructured-IO/unstructured — Unstructured official repository and README.
[4]: https://github.com/microsoft/graphrag — Microsoft GraphRAG repository; its README states the project is largely in maintenance mode.
[5]: https://github.com/neo4j/neo4j-graphrag-python — Neo4j first-party GraphRAG Python package.
[6]: https://github.com/vibrantlabsai/ragas — Ragas official repository.
[7]: https://github.com/Arize-ai/phoenix — Phoenix official repository.
[8]: https://github.com/vllm-project/vllm — vLLM official repository.
[9]: https://github.com/sgl-project/sglang — SGLang official repository.
