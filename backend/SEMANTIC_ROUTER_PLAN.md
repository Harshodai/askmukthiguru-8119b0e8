# Semantic Model Router — Unified Implementation Plan

## What Was Already Built
1.-nextfile:`services/semantic_model_router.py` — Embedding-based router
2. `services/container_builder.py` — Wires router into ContainerBuilder
3. `app/dependencies.py` — Wires router into legacy ServiceContainer
4. `app/config.py` — `semantic_router_enabled` and `semantic_router_top_k` flags
5. `app/orchestrator_utils.py` — Uses semantic router as primary classifier
6. `tests/test_semantic_model_router.py` — Basic tests

## Gaps Identified (from self-review)
1. **No confidence threshold** — routes even on very low similarity
2. **No telemetry/logging** — router decisions are invisible
3. **No shadow mode** — can't compare semantic vs heuristic in production
4. **No hybrid fallback** — when embedding model fails, no graceful degradation
5. **Tests not yet executed** — need confirmation they pass

## Remaining Tasks

### Task 1: Confidence-Scored Routing
- Add `classify_with_score()` → returns `(tier, max_similarity)`
- Add threshold in config: `semantic_router_confidence_threshold = 0.7`
- If max similarity < threshold, fallback to heuristic or log as "low confidence"
- Update `orchestrator_utils.py` to check confidence before trusting tier

### Task 2: Telemetry Audit Logging
- Log every routing decision: `query`, `tier`, `max_similarity`, `latency_ms`
- Log which router won: `semantic` vs `fallback`
- Create/update a telemetry table for router decisions

### Task 3: Shadow Mode A/B Support
- Add `semantic_router_shadow_mode` flag to config
- In shadow mode: run semantic router AND heuristic, log both, but return heuristic result
- This enables data-driven rollout

### Task 4: Run Tests, Verify Integration
- Run `test_semantic_model_router.py`
- Verify `pytest` suite still passes
- Check no circular imports
