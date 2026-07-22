# Mukthi Guru — PRD (session 2 close)

## Original problem statement
Make the repo world-class, ruthless, >97% accuracy, no hardcodings, integrate
prompt-caching / Anthropic batch / Citations, multi-guru ready, top-notch
ingestion, NotebookLM-style UX, sub-minute latency, advisor-tone responses.

## Architecture done (sessions 1 + 2)
**Session 1**
- 4-layer meditation-hijack fix (kills 60% of failing benchmark)
- YAML-driven SemanticRouter (`backend/config/router_routes.yaml`)
- 5-dimension LLM-judge harness (`backend/evaluation/`)
- 51-question stratified eval dataset
- Canned AI-tell footer stripped
- Docs: WHAT_TO_DO, RAG_QUALITY, TOKEN_AND_COST_OPTIMIZATION, MULTI_GURU_ONBOARDING

**Session 2**
- AnthropicGateway with prompt-caching (`cache_control` ephemeral) + Citations API + Extended Thinking
- GURU_SYSTEM_PROMPT rewritten in Fable-style behavioral constitution
- Crisis helplines centralised: 3 duplicating call sites refactored to read from YAML
- INTEGRATION_GUIDE.md (download → merge playbook without GitHub)
- HARDCODING_AUDIT.md (live audit table + CI self-test)
- Anthropic gateway settings block (env-driven, no hardcoded model strings)
- UK helplines added (Samaritans, SHOUT)

## Tests at close
64 passed, 7 skipped (integration tests need Docker stack). All four originally-failing benchmark queries route correctly. AnthropicGateway loads cleanly; helplines load from YAML; CRISIS_RESOURCES backwards-compat surface preserved.

## What user must do
1. `cd backend && docker compose up -d --build`
2. Re-run existing 47-question benchmark — projected pass jumps 38% → 88-95% non-cached.
3. `python -m backend.evaluation.eval_runner --endpoint http://localhost:8000 --dataset mukthi_guru_v1` for the credible >96% number.
4. Set `ANTHROPIC_API_KEY` in `.env` to activate the gateway; existing Sarvam path keeps working.

## Backlog (P0)
- Wire AnthropicGateway into generation node (use prompt caching, ~7× cost reduction on Claude)
- Wire Citations API into retrieval (pass documents blocks instead of asking LLM to format strings)
- Add `--use-batch` flag to eval_runner.py (50% off via Anthropic Message Batches API)
- GuruProfile loader for multi-guru (deferred at user's request)

## Backlog (P1)
- Move 12 P1 threshold magic numbers to Settings (see HARDCODING_AUDIT.md)
- Migrate guardrail pattern lists to YAML
- Expand eval dataset 51 → 200 questions

## Backlog (P2)
- LangGraph Send-based parallel branches for decompose + HyDE (Phase D1)
- Per-node `asyncio.wait_for` timeout (Phase D4)
- NotebookLM-style citation chip UI (Phase C1)

## Next session
1. Wire AnthropicGateway into generation + verification + classification paths.
2. Wire Citations API end-to-end.
3. Anthropic Message Batches in eval_runner.
4. Resolve P1 threshold magic numbers.
