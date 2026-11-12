# Graded-run serving flags and grader models, 2026-11-12

Status: a list for the people who set prod env. It does **not** change any prod default. Source: `backend/docker-compose.graded.yml` and `backend/app/config.py` at the time of writing (VERIFIED by reading both).

## Flags the graded run pins that differ from the `Settings` default
Prod must set these too, or a graded result does not describe prod. Each row is a decision for Harsha before prod; none is a recommendation to turn on.

| Env var | Graded run | Settings default | Note |
|---|---|---|---|
| `FIRST_PERSON_ENRICHMENT_WINDOW_ENABLED` | true | false | Harsha's listen review (2026-11-07) asked for full story windows. |
| `FIRST_PERSON_GRAPH_EXPANSION_ENABLED` | true | false | |
| `FIRST_PERSON_TEACHING_UNIT_GRAPH_ENABLED` | true | false | |
| `FIRST_PERSON_HYDE_ENABLED` | true | false | Adds an LLM call per request (latency and cost). |
| `FIRST_PERSON_JUDGE_ENABLED` | true | false | LLM judge picks and scores clips. It never writes text. |
| `FIRST_PERSON_SERVE_UNREGISTERED` | true | false | Recorded pin O5. The rights gate `domain_rights_status == "licensed"` exists in code since 2026-11-04 (`9e17370`). Check it still blocks unlicensed spans with this flag on. |
| `FIRST_PERSON_RELEVANCE_TIMEOUT_S` | 12 | 25 | D-PG13: graded run only. |
| `OPENROUTER_EXTRA_ALLOWED_MODELS` | `anthropic/claude-haiku-5.5` | empty | Needed for the scorer. |

## Flags the graded run pins that equal the default (no action)
`FIRST_PERSON_CONTEXT_CANDIDATE_LIMIT=16`, `FIRST_PERSON_SERVE_WEAK_MATCH=true`, `FIRST_PERSON_FACET_SPLIT_ENABLED=true`, `FIRST_PERSON_COMPOUND_DIRECT_SERVING_ENABLED=true`, `FIRST_PERSON_RELEVANCE_MIN_SCORE=3` (since 2026-11-12), `FIRST_PERSON_LLM_FALLBACK_ENABLED=false`.

## Flags no longer pinned (2026-11-12)
- `FIRST_PERSON_UNCALIBRATED_DIRECT_ENABLED`: default false applies.
- `FIRST_PERSON_REQUIRE_VOICE_METHOD`: default false applies. The H2 gate in the grader still fails the run if a bare-flag speaker is served. Commit `6a11c64` lets the harness serve legacy centroid spans while this flag is false; that is an open owner decision.

## Graders (decision 2026-11-12, owner rule: no Opus 5.5 on OpenRouter)
- First grader: `anthropic/claude-haiku-5.5` (script default).
- Second grader: **`meta-llama/llama-3.3-70b-instruct`**. It is cheap (USD 0.12 / 0.30 per million tokens in `services/openrouter_service.py`), already on the repo's model allowlist, not Opus, not deepseek, and differs from the first grader.
- Product scorer is `anthropic/claude-haiku-5.5`. The first grader is the same model, so `check_judge_independence` will abort unless `--allow-shared-judge` is passed. Record that flag in the run report if used. A better fix is to make the first grader a different model from the scorer; I did not pick one because I could not verify another slug and price from the repo.
- Caveat (ASSUMPTION): `research/final-pass-bar-2026-10-30.md` asks for a judge stronger than the product scorer. A 70B open model is probably not stronger than Haiku 5.5 on this task. Keep the human 50-clip label sample as the check on both graders.
- Example: `--first-model anthropic/claude-haiku-5.5 --second-model meta-llama/llama-3.3-70b-instruct --allow-shared-judge`.

## Pass bar (restored 2026-11-12)
Showable >= 85%, served share >= 30%, core abstain >= 95%, p95 <= 10 s, harmful 0. The 2026-11-09 values (0.95 / 0.45) had no quoted approval and are kept in the bar file as an unapproved proposal.
