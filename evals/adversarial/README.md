# Adversarial suite (NEW-SEC-5 / NEW-AI-6)

Offline cases in `cases.jsonl`, run by `backend/tests/test_adversarial_suite.py`.
The backend CI test job runs that file with the rest of `backend/tests`. No
network, no Qdrant, no real provider: each LLM call gets a stub that returns a
fixed hostile or malformed reply, so a case measures how the system handles the
input.

Sources: `audits/audit-output-2026-11-04/specifications/PRODUCTION_RELIABILITY_SECURITY_AND_COST_SPEC.md`
§3.9.3 (ADV-*) and `AI_HARNESS_PROMPT_AND_CONTEXT_SPEC.md` §3.11 (numbered cases).

## Case fields

| Field | Meaning |
|---|---|
| `id` | Unique case id. |
| `ref` | Spec case it covers. |
| `check` | Runner function (`check_<name>` in the test file). |
| `payload` | Input for the check. |
| `expected` | Behaviour that passes. |
| `status` | `block`: must pass. `expected_fail_tracked`: a known gap; the runner asserts the gap is still there, so a fix fails the test until the case is promoted to `block`. |

## Known gaps (tracked, not closed)

| Case | Gap |
|---|---|
| ADV-S10c | A paraphrased injection with no listed phrase is not matched by the screen. The prompt fence is the control (harness spec case 10). |
| ADV-U2a | `canonicalize_route_decision` returns an unknown route name unchanged, so it is not a `RouteDecision` member. Fixing it changes route labels in responses and metrics; needs a decision. |

Injection patterns are English only (screen and memory extractor). Indic-script
and transliterated patterns need native-speaker review (D-22).

## Not run here (need a live or staged stack, UNPROVEN)

ADV-S1, ADV-S2 and ADV-S5 through the full HTTP pipeline; ADV-R1 (50-question
poisoning run); ADV-R4 (Qdrant read-only key); ADV-C1 to ADV-C4 (two real
accounts, RLS); ADV-X1 to ADV-X4 (body limits, 200 concurrent requests, rate
limits); ADV-B1 to ADV-B7 (route auth table, job abuse); ADV-K2 (crisis under an
open breaker). Existing tests cover parts of these (for example
`test_cache_personalization_leak.py`, `test_citation_contract.py`); a staged
run is still owed.
