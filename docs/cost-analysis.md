# Cost Analysis

No production billing account or provider mutation was used, so no dollar forecast is claimed. Main cost drivers are LLM generation tokens and retries, embeddings, reranking, OCR/multimodal processing, Redis/worker time, Supabase/Qdrant/Neo4j storage, telemetry volume, and cache misses.

A defensible model must use a representative approved question set and report cost per completed answer, queue admission, cache hit/miss, retry/fallback, embedding batch, and stored unit. It must preserve grounding, safety, tenant filters, and deletion guarantees while optimizing cost. Provider cost and capacity remain unmeasured because local chat probes were 429/readiness limited.

## Fresh cost evidence boundary — 2026-08-25

The bounded local chat probe produced 40/40 HTTP 429 admissions and therefore generated no trustworthy completed-answer token/cost sample. The no-backend browser TTS journey intentionally used fail-closed native speech and made no Sarvam HTTP request. These outcomes are useful boundary evidence but not a dollar estimate.

The cost gate remains blocked until an approved representative question set can run through the actual configured provider path with token counts, retries, cache hit/miss, embedding batches, queue completion, audio/ocr usage, and infrastructure resource time captured per completed answer. No provider billing account, production quota, or user data was changed during this audit.
