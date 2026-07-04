# OKF: Config Pruning Lessons

> **Source:** Config audit session 2026-07-04
> **Domain:** Configuration Management, Technical Debt
> **Last updated:** 2026-07-04

## What Was Pruned (Confirmed Dead via grep)

| Config | Reason | File |
|--------|--------|------|
| `graph_hard_deadline_s` | Inline comment: "DEAD CONFIG" — LangGraph never reads it | config.py |
| `use_openrouter_for_simple` | OpenRouter not primary path when `llm_provider=sarvam_cloud` | config.py |
| `feature_lightweight_classifier` | Zero references in rag/ or routers/ | config.py |
| `whisper_local_device` | WhisperLocalService hardcodes to MPS — setting ignored | config.py |
| `generation_top_k_fast/standard/deep` | Zero reads outside config.py | config.py |
| `generation_top_p_standard/deep` | Same | config.py |
| `use_gateway_service` | Gateway deprecated per CLAUDE.md | config.py |

## What Was KEPT / Restored (False Positives)

| Config | Used By | Why Kept / Restored |
|--------|---------|---------------------|
| `ab_testing_enabled` | `app/pipeline/stages/graph_stage.py:69` | Active A/B test path |
| `ab_testing_ratio` | Same | Active A/B test path |
| `whisper_local_model` | `services/whisper_local_service.py:177` | Actively read |
| `adaptive_chunking_service.py` | `services/adaptive_chunking_adapter.py` | Base class (do NOT delete) |
| `nim_rpm_limit` | `services/nim_service.py:59` | Active rate limiting setup |
| `openrouter_rpm_limit` | `services/openrouter_service.py:61` | Active rate limiting setup |
| `use_cross_encoder_only` | `services/reranker_service.py:218` | Active reranking fallback logic |
| `rag_cache_alignment_enabled` | `rag/nodes/generation.py:467` | Active generation caching check |

## Critical Lesson

**Always grep EVERY file (including tests and adapters) before deleting.**
`adaptive_chunking_service.py` was wrongly identified as orphan — it's the base class for `AdaptiveChunkingAdapter`.
The grep command `grep -v "adaptive_chunking_service.py"` excluded the service file itself but missed the adapter and tests.

**Safe deletion workflow:**
```bash
# 1. Check all imports
grep -rn "ClassName\|module_name" backend/ --include="*.py"
# 2. Check tests explicitly
grep -rn "ClassName" backend/tests/ --include="*.py"
# 3. Check adapters/wrappers
grep -rn "from services.module" backend/ --include="*.py"
# Only delete if ALL grep results are 0
```

## What NOT To Ever Touch

- All RAG configs (`rag_top_k`, `rag_chunk_size`, `rag_dense_weight`, etc.)
- All reranking configs (`reranker_model`, `reranker_top_n`)
- RAPTOR configs (`raptor_levels`, `raptor_parent_summaries_enabled`)
- Semantic router configs
- Embedding configs
- Timeout configs (latency-critical)
- OKF injection flags
- Whisper model size (`whisper_model_size`)
- Sarvam cloud configs
- Memory / Serene Mind configs

## Config Size After Pruning

- Before: ~330+ settings in `Settings` class
- After: ~316 settings (removed 14 confirmed dead)
- Net effect: Faster class instantiation, cleaner `.env.example`, reduced cognitive load
