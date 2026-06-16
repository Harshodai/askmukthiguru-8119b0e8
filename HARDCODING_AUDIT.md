# HARDCODING_AUDIT.md — Live audit of remaining hardcoded values

> Updated 2026-06-16. This audit is run periodically; the table below pins
> each hotspot and tracks remediation status. The goal is **zero
> business-logic hardcoding** — only true constants (e.g. HTTP status codes,
> regex word boundaries) belong in Python literals.

Audit commands live in `WHAT_TO_DO.md` §6. Re-run them before every release.

---

## Summary

| Severity | Count at start of Phase A | Fixed | Remaining |
|---|---|---|---|
| 🔴 P0 (safety — helpline numbers, crisis paths) | 3 sites duplicating data | 3 | **0** |
| 🟠 P1 (correctness — threshold magic numbers in business logic) | 12 | 0 | 12 |
| 🟡 P2 (model identifiers in service code) | 14 | 0 | 14 |
| 🔵 P3 (heuristic pattern lists in guardrails) | 5 lists | 0 | 5 |
| 🟢 P4 (true constants — boundary tokens, defaults) | many | n/a | n/a (acceptable) |

---

## 🔴 P0 — Crisis helplines (FIXED)

**Status: ✅ Fixed in Phase A.** All three call sites now consume from
`services.crisis_helplines.format_helplines_block()`, which reads from
`backend/config/router_routes.yaml`. Helpline data is centralized.

| Old location | Action |
|---|---|
| `backend/rag/meditation.py:88-91` | Replaced inline strings with `format_helplines_block(style="compact_two_line")` |
| `backend/guardrails/lightweight_handler.py:126-128` | Template now uses `__HELPLINES__` token, substituted by `_resolve_block_response()` |
| `backend/services/serene_mind_engine.py:193-208` | `CRISIS_RESOURCES` dict replaced with `_CrisisResourcesView` backed by YAML |

Test:
```python
from services.crisis_helplines import format_helplines_block
assert "9152987821" not in open("backend/rag/meditation.py").read()
assert "1860-2662-345" not in open("backend/guardrails/lightweight_handler.py").read()
```

---

## 🟠 P1 — Threshold magic numbers

These thresholds are *business logic decisions* (where to draw the line on
faithfulness, relevance, etc.), so they belong in Settings, not Python literals.

| File:line | Value | Used for | Recommended Settings field |
|---|---|---|---|
| `backend/rag/graph_strategies.py:116` | `0.25` | LettuceDetect hallucination threshold | `lettuce_detect_threshold` |
| `backend/rag/cot_verifier.py:97` | `>= 0.8` | CoVe "supported" verdict | `cove_supported_threshold` |
| `backend/rag/cot_verifier.py:97` | `>= 0.5` | CoVe "partial" verdict | `cove_partial_threshold` |
| `backend/rag/nodes/verification.py:68` | `>= 0.8` | Faithfulness floor | `faithfulness_floor` |
| `backend/rag/nodes/verification.py:316` | `>= 0.5` | Combined verifier passing ratio | `verifier_pass_ratio` |
| `backend/rag/nodes/reranking.py:46` | `0.01`, `0.05` | Complex / simple rerank thresholds | `rerank_threshold_complex`, `rerank_threshold_simple` |
| `backend/rag/nodes/reranking.py:170` | `threshold=0.3` | Reranking floor | `rerank_floor` |
| `backend/services/semantic_cache.py` | `0.92` | Cache hit similarity | `semantic_cache_threshold` (already exists, verify all references use it) |
| `backend/rag/nodes/intent.py` | meditation_step fallback | Intent state recovery | already in Settings |

**Action item**: One PR per file, moving each threshold to Settings. Each PR
must include a test that toggles the threshold via env var.

**Priority order**: faithfulness_floor and lettuce_detect_threshold first
(they directly gate the user-facing answer quality).

---

## 🟡 P2 — Model identifiers in service code

When a model name is hardcoded, you cannot swap models without a code change.
The provider-chain pattern (`LLM_PROVIDER_CHAIN` env var) is the standard
remediation. These call sites need to read from settings instead.

| File:line | Hardcoded model | Where it should live |
|---|---|---|
| `backend/app/telemetry_db.py:339` | `["sarvam-30b", "llama3.2:3b"]` | `settings.observed_models` |
| `backend/app/constants.py:107-109` | `"sarvam-30b"`, `"sarvam-105b"` | This is the legitimate Settings default — verify call sites read via `settings.MODEL_NAMES`, not import the constant directly. |
| `backend/app/core/feedback_store.py:40` | `"sarvam-105b"` | Pass model name from caller, not hardcoded |
| `backend/services/language_router.py:92-171` | `sarvam-30b-{language}` 9 entries | These are *recommendations* for downstream routing, not actual API calls. Acceptable for now but should move to YAML alongside language config. |

**Action item**: Audit each call site once Phase A7 (LLMGateway) is wired.
The LLMGateway is where model selection happens; nothing downstream should
need to know the model name.

---

## 🔵 P3 — Heuristic pattern lists in guardrails

`backend/guardrails/lightweight_handler.py` contains 5 hardcoded pattern lists:

| List | Lines | Purpose |
|---|---|---|
| `_HARMFUL_PATTERNS` | 16-?? | Self-harm, clinical-advice, manipulation regexes |
| `_OUTPUT_BLOCK_PATTERNS` | 163-?? | Patterns blocked from model OUTPUT |
| `_SPIRITUAL_CONTEXT_PATTERNS` | 170-?? | "Is this spiritual context" markers |
| `_EMOTIONAL_WELLNESS_PATTERNS` | 217-?? | Emotional-wellness override patterns |
| `_KNOWLEDGE_TRAP_PATTERNS` | 227-?? | Known doctrine-trap query templates |

**Status: not migrated yet.** Migrating these to YAML is a moderate-size
lift (~200 lines of code refactor, plus YAML schema design). The grep for
these patterns runs on every guardrail check, so the YAML loader needs to
be cached at startup.

**Recommendation**: Migrate as part of the next guardrails refactor. The
pattern is the same as `router_routes.yaml`:

```yaml
# backend/config/guardrail_patterns.yaml
output_block_patterns:
  - "(?i)\\bas an AI\\b"
  - "(?i)\\bI am an AI model\\b"
spiritual_context_patterns:
  - "(?i)\\b(beloved|dear one|seeker)\\b"
```

The patterns are inherently text-y, so YAML edits are also self-documenting
(unlike the current inline regexes that need comments).

---

## 🟢 P4 — Patterns it's OK to keep in code

Not every literal is a hardcoding bug. Acceptable patterns:

- HTTP status codes (`200`, `400`, `429`, `500`)
- Regex word boundaries (`\\b`, `^`, `$`)
- Standard library defaults (default timeout = 30s when no external policy
  exists)
- Cryptographic salt prefixes
- Test fixtures
- Migration script literals (one-shot)
- Logging format strings
- Color codes and CSS class names in frontend
- The keys in this very YAML schema (because they ARE the schema)

The rule: a literal is acceptable when:
  1. It is not a business decision (e.g. "0.8 is the faithfulness floor" IS
     a business decision)
  2. It is not user-facing (helpline numbers are user-facing)
  3. It does not need to vary across environments

---

## Self-test (add to CI)

```bash
#!/usr/bin/env bash
# scripts/check_hardcodings.sh — fails CI if any forbidden hardcoding regresses

set -e

# P0: no helpline numbers outside config / docs / tests
if grep -rnE '\b(9152987821|9820466726|988|741741|1860-2662-345)\b' backend/ \
    --include="*.py" \
    | grep -v 'tests/' \
    | grep -v 'config/'
then
    echo "❌ P0 regression: helpline number found in code"
    exit 1
fi

# No literal "meditation is complete" outside the centraliser
if grep -rn 'meditation is complete' backend/ --include="*.py" \
    | grep -v 'meditation.py' \
    | grep -v 'tests/'
then
    echo "❌ Hardcoded 'meditation is complete' string found"
    exit 1
fi

# AI-tells must not be in prompts.py
if grep -nE '(Based on what I found in the teachings|As an AI)' backend/rag/prompts.py
then
    echo "❌ AI-tell phrase found in prompts.py"
    exit 1
fi

echo "✅ Hardcoding audit passed"
```

Wire this into your CI pipeline. The audit takes <1s, runs on every PR.
