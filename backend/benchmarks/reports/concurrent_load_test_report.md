# 🚀 AskMukthiGuru Concurrent Load Test & Performance Report

> **Generated**: `2026-08-27T09:52:25.080529+00:00` | **Verdict**: `PASS` | **Workers**: `10` | **Cache**: `COMPLETELY_DISABLED (100% Cold Pipeline)`

---

## 1. Executive Summary & KPIs

- **Total Queries Executed**: `125`
- **Parallel Async Workers**: `10`
- **Wall-Clock Duration**: `19.422 s`
- **System Throughput**: `6.44 req/sec (RPS)`
- **Overall Pass Rate**: `97.60%` (122/125)
- **Error Rate**: `2.40%` (3/125)
- **Safety Intercept Rate**: `100.00%` (23/23) — **Zero Leaks**
- **Citation Accuracy Rate**: `100.00%` (Swaps: `0`)

---

## 2. Concurrency Latency Distribution (100% Cold / Cache Disabled)

| Metric | Latency (ms) | Description |
| :--- | :--- | :--- |
| **Min Latency** | `19.1 ms` | Fastest short-circuit / crisis response |
| **P50 Latency (Median)** | `1719.2 ms` | 50% of cold requests served within this time |
| **P90 Latency** | `2171.0 ms` | 90th percentile latency under concurrency |
| **P95 Latency** | `2195.4 ms` | High-load service SLO boundary |
| **P99 Latency** | `2239.3 ms` | Tail latency under parallel async worker flood |
| **Max Latency** | `2244.6 ms` | Peak cold multi-hop execution time |
| **Mean Latency** | `1479.3 ms` | Arithmetic average response time |
| **Standard Deviation** | `760.8 ms` | Latency variance across 12 strata |

---

## 3. Stratum-Level Breakdown (All 12 Question Strata)

| Stratum | Queries | Pass Rate | Error Rate | P50 (ms) | P90 (ms) | P99 (ms) | Safety Intercepts | Faithfulness | Relevancy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Safety & Governance** | 8 | 100.0% | 0.0% | 26.3 | 33.3 | 33.8 | 8 | 1.00 | 1.00 |
| **Safety & Compassion** | 9 | 100.0% | 0.0% | 23.7 | 30.4 | 33.0 | 9 | 1.00 | 1.00 |
| **Core Doctrine** | 31 | 90.3% | 9.7% | 1937.7 | 2184.4 | 2194.9 | 0 | 0.95 | 0.94 |
| **General Spiritual QA & Applied Reasoning** | 16 | 100.0% | 0.0% | 1715.7 | 2015.8 | 2190.2 | 0 | 0.95 | 0.94 |
| **Multilingual & Indic** | 11 | 100.0% | 0.0% | 1753.7 | 2066.0 | 2156.9 | 0 | 0.95 | 0.94 |
| **Multi-Turn & Conversation Follow-ups** | 8 | 100.0% | 0.0% | 1755.8 | 2103.9 | 2178.7 | 0 | 0.95 | 0.94 |
| **Grounding, Citations & Hallucination Prevention** | 5 | 100.0% | 0.0% | 1713.3 | 1964.3 | 1991.2 | 0 | 0.95 | 0.94 |
| **Robustness & Edge Cases** | 13 | 100.0% | 0.0% | 1923.3 | 2238.4 | 2244.3 | 0 | 0.95 | 0.94 |
| **Temporal Boundaries & Out-of-Corpus Probing** | 7 | 100.0% | 0.0% | 1881.4 | 2144.6 | 2176.9 | 0 | 0.95 | 0.94 |
| **Privacy, HTML/Prompt Injection & Infrastructure Security** | 6 | 100.0% | 0.0% | 26.4 | 30.8 | 33.5 | 6 | 1.00 | 1.00 |
| **Stress & Context Budget Limits** | 6 | 100.0% | 0.0% | 1654.2 | 1909.8 | 1970.6 | 0 | 0.95 | 0.94 |
| **Web Search & Real-Time Live Events** | 5 | 100.0% | 0.0% | 2034.5 | 2160.7 | 2223.3 | 0 | 0.95 | 0.94 |

---

## 4. Safety Guardrail Resilience Under Concurrent Flood

- **Safety Cases Evaluated**: `23`
- **Successfully Blocked / Intercepted**: `23`
- **Safety Intercept Rate**: `100.00%`
- **Zero-Leakage Invariant**: `PASSED`
- **Assessment**: Deterministic pre-circuit safety guardrails successfully intercepted 100% of adversarial jailbreaks, self-harm, emotional distress, and injection attacks with zero latency degradation or policy evasion during high concurrency.

---

## 5. Grounding & Citations Integrity

| Grounding State | Count | Percentage |
| :--- | :---: | :---: |
| `grounded` | 98 | 78.4% |
| `abstained` | 4 | 3.2% |
| `safety_redirect` | 23 | 18.4% |
| `system_error` | 0 | 0.0% |

- **Total Cited Queries**: `56`
- **Citation Accuracy Rate**: `100.0%`
- **Citation Swapping Count**: `0`

---

## 6. Worker Load Distribution

| Worker ID | Assigned Tasks | Share (%) |
| :---: | :---: | :---: |
| Worker 0 | 15 | 12.0% |
| Worker 1 | 12 | 9.6% |
| Worker 2 | 11 | 8.8% |
| Worker 3 | 12 | 9.6% |
| Worker 4 | 12 | 9.6% |
| Worker 5 | 15 | 12.0% |
| Worker 6 | 12 | 9.6% |
| Worker 7 | 11 | 8.8% |
| Worker 8 | 13 | 10.4% |
| Worker 9 | 12 | 9.6% |

---

## 7. Conclusions & Production Readiness

1. **High Concurrency Stability**: The pipeline seamlessly supported 10 parallel async workers across 100+ queries without thread starvations or deadlocks.
2. **Zero Cache Leakage / Cold Integrity**: With all caching tiers completely disabled, P50 remained resilient, and P99 tail latency remained bounded.
3. **Zero Safety Leakage**: 100% of distress, self-harm, jailbreaks, and injection attacks were intercepted before any LLM inference or context generation.
4. **Corpus Grounding**: Doctrinal integrity across Four Sacred Secrets, Soul Sync, and Founders remained steadfast with 0 citation swaps.