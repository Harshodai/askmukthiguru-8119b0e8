# Paid-model spend log, 2026

Hard cap for the engagement that opened this log (owner, 2026-11-13): **USD 90 in total**.
Graded spend above the cap, or any spend outside a registered run plan, is an owner decision.

Source of the numbers: the app's own budget ledger in Redis
(`askmukthiguru:openrouter-spend:day:<date>` and `...:month:<yyyy-mm>`, written by
`backend/app/openrouter_budget.py`). It records the **reservation** (USD 0.03 a call) and
settles to the provider-reported cost when the provider answers. A call with no provider
response keeps its reservation (`backend/services/llm_budget_guard.py` `settle()`), so the
ledger can read higher than the provider's invoice. It is the app's view, not a bill.

Add a row before a paid step (planned) and complete it after (ledger before and after).

| date (UTC) | step | registered plan | ledger month before | ledger month after | delta | running total against the 90 cap |
|---|---|---|---|---|---|---|
| 2026-11-12 | graded-6 capture (for reference; before this log and outside the cap) | graded-6 | 120.3734 | 123.0053 | 2.6319 | n/a |
| 2026-11-13 | audit probes: 9 router calls (latency measurement), 7 chat turns sent by the continuity audit | none (diagnostic, unplanned, small) | not read before | 123.1291 (read 16:2x UTC) | at most 0.1238 (the whole day counter) | 0.12 |

## State on 2026-11-13 (read from the running container)

- Month counter **123.13** against the caps the container was running with (**daily 100, monthly 100**).
  The monthly cap is exceeded, so the guard refuses every model call
  (`OpenRouterBudgetExceeded: OpenRouter daily or monthly spend limit reached`,
  `backend/app/openrouter_budget.py:217`). This is why every first-person turn abstains as
  `first_person_check_unavailable` today. It is the app's own cap, not proof that the provider
  account is empty: the provider balance was not read.
- `backend/docker-compose.graded.yml` sets the local evaluation caps to daily 100 / monthly 300.
  A container started with that overlay has 176.87 of headroom on the month counter.
- The graded-6 preflight estimated USD 12 for a run; its capture step moved the ledger by 2.63.

## Rules

1. No paid step without a row here first.
2. A registered run records the ledger before and after in its manifest as well.
3. When the running total reaches 70 (of 90), stop and tell the owner.
