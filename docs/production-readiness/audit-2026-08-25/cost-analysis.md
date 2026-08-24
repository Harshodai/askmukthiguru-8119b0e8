# Cost Analysis

No production billing account or provider mutation was used, so no dollar forecast is claimed. Main cost drivers are LLM generation tokens and retries, embeddings, reranking, OCR/multimodal processing, Redis/worker time, Supabase/Qdrant/Neo4j storage, telemetry volume, and cache misses.

A defensible model must use a representative approved question set and report cost per completed answer, queue admission, cache hit/miss, retry/fallback, embedding batch, and stored unit. It must preserve grounding, safety, tenant filters, and deletion guarantees while optimizing cost. Provider cost and capacity remain unmeasured because local chat probes were 429/readiness limited.
