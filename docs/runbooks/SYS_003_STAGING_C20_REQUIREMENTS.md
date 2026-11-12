# SYS-003 Staging c20 Load Test Protocol & Requirements

**Item:** SYS-003 / T7-02 (Async First-Person Teaching Lane Under Load)  
**Status:** PARTIAL (implemented in code via `dcfb3a5` / `T7-02`; requires live staging c20 load verification before watchdog removal)  
**Target Environment:** Railway Staging Environment (IS_PRODUCTION=false, staging Redis, staging Qdrant)

---

## 1. Test Objectives

1. **Concurrency Validation (c=20):** Execute sustained load of 20 concurrent async chat requests across a 15-minute window without worker thread-pool exhaustion.
2. **Cancellation Bound:** Verify that client-side / gateway timeout disconnects propagate immediately, terminating in-flight provider calls and freeing reservations (verified in `test_first_person_bounded_cancel.py`).
3. **Latency Compliance:** Measure end-to-end request latency to ensure $p95 \le 10.0\text{ s}$ per `evals/first_person/grading_pass_bar.json`.
4. **Safety Route Parity:** Verify that crisis and distress prompts maintain instant response times (< 1.5 s) even while 19 background teacher queries are in flight.

---

## 2. Infrastructure Pre-Conditions

| Component | Required Setting | Verification Method |
|---|---|---|
| **Backend Workers** | Uvicorn running with `asyncio` loop; Celery worker active | `/api/healthz` reports `"status": "ok"` |
| **Redis Eviction** | `noeviction` policy with memory headroom $\ge 256\text{ MB}$ | `redis-cli INFO memory` |
| **First-Person Flags** | `FIRST_PERSON_PRIMARY_MODE=true`<br>`FIRST_PERSON_LLM_FALLBACK_ENABLED=false` | Check `/api/healthz` flags or env |
| **Watchdog** | Thread-pool deadlock watchdog active with 30s timeout | Check logs for `[Watchdog] active` |

---

## 3. Load Execution Commands

Run from a test runner machine against staging:

```bash
# 1. Warm-up pass (c=5, 60 seconds)
python scripts/ops/gate1_load_test.py \
  --target https://staging.askmukthi.guru \
  --concurrency 5 \
  --duration 60 \
  --output /tmp/c20_warmup.json

# 2. Main c=20 Stress Run (c=20, 900 seconds / 15 minutes)
python scripts/ops/gate1_load_test.py \
  --target https://staging.askmukthi.guru \
  --concurrency 20 \
  --duration 900 \
  --output /tmp/c20_main_run.json
```

---

## 4. Pass / Fail Acceptance Criteria

| Metric | Target | Fail Condition |
|---|---|---|
| **HTTP 5xx Errors** | 0% | Any unhandled 500 error |
| **HTTP 504 Gateway Timeouts** | 0 | Any worker deadlock causing 504 |
| **Latency p95** | $\le 10.0\text{ s}$ | $p95 > 10.0\text{ s}$ |
| **Thread Pool Saturation** | $\le 75\%$ active | Thread starvation / worker hang |
| **Crisis Response Latency** | $\le 2.0\text{ s}$ | Helplines delayed behind teacher queue |

---

## 5. Post-Test Remediation Gate

Only after this test exits with **PASS** on staging may the legacy synchronous fallback thread-pool watchdog be decommissioned and SYS-003 marked **CLOSED**.
