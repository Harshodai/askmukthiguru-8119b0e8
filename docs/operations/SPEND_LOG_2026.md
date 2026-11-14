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

| 2026-11-14 | DONE: graded stack start at `d2f8e615` (warm-up, 20 FAQ questions) | graded-7 registration | 123.1291 | 123.4430 | 0.3139 (planned up to 2) | 0.43 |
| 2026-11-14 | DONE: graded-7 capture, 202 rows, 03:11 to 03:31 UTC | graded-7 registration | 123.4430 | 126.4314 | 2.9885 (planned up to 12) | 3.42 |
| 2026-11-14 | DONE: graded-7 grading, two graders on 41 served rows + unanswerable scoring. Runs host-side straight to the provider, so it is **not on this ledger** | graded-7 registration | n/a | n/a | estimated under 1 from list prices; not measured (planned up to 8) | about 4.4 |
| 2026-11-14 | DONE: five-path chat probe (6 turns), first run | Phase 4 verification | 126.4314 | 126.5235 | 0.0921 (planned up to 1) | about 4.5 |
| 2026-11-14 | DONE, not planned as its own row: second stack start at `2f26bbbd` (warm-up) and second five-path probe, needed after the follow-up fix | Phase 4 verification | 126.5235 | 126.8994 (read 07:59 UTC; another session was also active in this window) | 0.3759 at most | about 4.9 |
| 2026-11-14 | Attempted: 3 negative-control pairs from the host. All came back indeterminate (the host cannot reach the stack's Redis), so no provider call is believed to have been made | none | n/a | n/a | 0 expected | about 4.9 |
| 2026-11-14 | DONE: negative-control measurement of the comparative judge, 116 pairs, inside the container, two arms plus a 3-pair smoke run | same-clip analysis, "measure candidate A before any graded spend" | 126.8994 | 126.9193 | 0.0198 (planned worst case 10.44 in reservations) | about 4.9 |
| 2026-11-14 | DONE: graded-8 stack start at `4e1c2c4c` (warm-up); another session was active in the same window | graded-8 registration | 126.9193 | 127.3513 | 0.4320 at most (planned up to 2) | about 5.3 |
| 2026-11-14 | DONE: graded-8 capture, 202 rows, answerability gate on (manifest `spend_before`/`spend_after`) | graded-8 registration | 127.3513 | 130.2055 | 2.8542 (planned up to 12) | about 8.2 |
| 2026-11-14 | DONE: graded-8 grading, two graders on 40 served rows + unanswerable scoring; host-side, **not on this ledger** | graded-8 registration | n/a | n/a | estimated under 1 from list prices; not measured (planned up to 8) | about 9 |
| 2026-11-14 | Other session's persona and acceptance probes after graded-8 (not planned in this log) | none | 130.2055 | 130.3711 (read 16:5x UTC) | 0.1656 | about 9.2 |

Graded-7 total against its stop rule of 25: about 4.3. Graded-8 total against its stop rule of 25: about 4.3.
Engagement total against the cap of 90: about 9.2 (ledger 123.0053 to 130.3711 is 7.37; the two grading passes are estimates on top).
Result and evidence: `docs/audits/ENGINEERING_READINESS_REPORT_2026-11-14.md`.

What the ledger showed about itself: in the first half of the capture 54 model calls were cancelled
(caller timeout or a faster parallel candidate) and each kept its 0.03 reservation, so the ledger
reads higher than the provider's bill (owner item P2-e).

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
