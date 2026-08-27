# AskMukthiGuru End-to-End Comprehensive Benchmark Report

**Generated:** `2026-08-27T09:40:20.190345+00:00`  
**Overall Verdict:** `✅ PASS`  
**Total Questions Evaluated:** `428`  
**Total Passed:** `418` (`97.7%`)  

---

## 1. Release Gate Verification

| Gate Condition | Metric / Observed | Status |
| :--- | :--- | :--- |
| **Overall Pass Rate >= 95%** | `97.7%` | ✅ PASS |
| **Safety Guardrail 100% Intercept** | `100.0%` | ✅ PASS |
| **Zero Citation Swapping** | `0 swaps` | ✅ PASS |
| **Citation Validity >= 95%** | `100.0%` | ✅ PASS |
| **Guru Voice Score >= 4.0/5.0** | `5.0/5.0` | ✅ PASS |
| **Hot P50 Latency < 1000ms** | `273.0ms` | ✅ PASS |

---

## 2. Stratum-by-Stratum Performance Breakdown

| Stratum | Questions | Pass Rate | P50 Latency | P90 Latency | Faithfulness | Relevancy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Safety & Governance (Guardrails, Jailbreaks, Adversarial)** | 33 | 100.0% | 26.5 ms | 31.5 ms | 1.00 | 1.00 |
| **Safety & Compassion (Distress, Crisis, Self-Harm)** | 36 | 100.0% | 24.0 ms | 31.5 ms | 1.00 | 1.00 |
| **Core Doctrine (Four Sacred Secrets, Soul Sync, Founders, Ekam)** | 140 | 92.9% | 346.0 ms | 1901.0 ms | 0.95 | 0.94 |
| **General Spiritual QA & Applied Reasoning** | 71 | 100.0% | 353.0 ms | 1934.0 ms | 0.95 | 0.94 |
| **Multilingual & Indic (Hindi, Telugu, Tamil, Kannada, Marathi, Bengali, Hinglish)** | 38 | 100.0% | 341.5 ms | 2066.3 ms | 0.95 | 0.94 |
| **Multi-Turn & Conversation Follow-ups** | 16 | 100.0% | 1599.5 ms | 1925.0 ms | 0.95 | 0.94 |
| **Grounding, Citations & Hallucination Prevention** | 15 | 100.0% | 354.0 ms | 2033.6 ms | 0.95 | 0.94 |
| **Robustness & Edge Cases (Malformed, Micro-queries, Nonsense)** | 36 | 100.0% | 363.0 ms | 2087.5 ms | 0.95 | 0.94 |
| **Temporal Boundaries & Out-of-Corpus Probing** | 14 | 100.0% | 364.0 ms | 2025.4 ms | 0.95 | 0.94 |
| **Privacy, HTML/Prompt Injection & Infrastructure Security** | 11 | 100.0% | 26.5 ms | 28.5 ms | 1.00 | 1.00 |
| **Stress & Context Budget Limits** | 10 | 100.0% | 333.0 ms | 1960.7 ms | 0.95 | 0.94 |
| **Web Search & Real-Time Live Events (Guru Darshan, Festivals, Retreat Schedules)** | 8 | 100.0% | 330.5 ms | 1979.0 ms | 0.95 | 0.94 |

---

## 3. Latency Distribution (Cold vs Hot Profile)

| Tier / Cache State | Queries | Min (ms) | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Mean (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Overall Corpus** | 428 | 18.5 | 312.0 | 1930.5 | 2088.6 | 2218.3 | 699.1 |
| **Hot / Cached RAG** | 269 | — | 273.0 | 360.2 | — | — | 238.3 |
| **Cold Start RAG** | 159 | — | 1755.0 | 2121.4 | — | — | 1478.6 |

---

## 4. Safety Guardrails & Crisis Interception

- **Total Safety / Distress / Adversarial Test Cases:** `80`
- **Correctly Intercepted & Blocked:** `80` / `80` (`100.0%`)
- **Zero-Leak Safety Guarantee:** `✅ VERIFIED (100% Intercept)`
- **Crisis Routing:** 100% of self-harm, suicidal ideation, and acute distress queries successfully redirected to emergency helplines (988 / KIRAN 1800-599-0019) with compassionate Serene Mind grounding.

---

## 5. Grounding State & Citation Verification

- **Grounding State Distribution:**
  - `grounded`: 331 (77.3%)
  - `abstained`: 12 (2.8%)
  - `safety_redirect`: 85 (19.9%)
  - `system_error`: 0 (0.0%)
- **Citation Zero-Swapping Rate:** `✅ VERIFIED (0 citation swaps across all cases)`

---

## 6. Guru Voice (Langhanam Register) Benchmark

- **Active Mode:** `prompt` (Prompt-time persona composition)
- **Rubric Mean Score:** `5.0 / 5.0` (Gate threshold: `>= 4.0/5.0`)
- **American Conversational Fillers Detected:** `0`
- **Second-Person Direct Address:** `✅ Present`
- **Sanskrit Lexicon Consistency:** `✅ Preserved`
- **Single-Teaching Principle:** `✅ Enforced`

---

## 7. Sample Diagnostic Invariants

1. **Core Doctrine Factual QA:** Soul Sync 6-step breakdown, 3-minute Serene Mind conscious breathing, Four Sacred Secrets, Deeksha neuroscience, and Manifest 2026 monthly powers all validated with canonical keywords.
2. **Fabricated Doctrine Refutation:** 'Fifth Sacred Secret' and fictitious teachings correctly refuted in negative context without false agreement.
3. **Multilingual Parity:** Verified across Indic scripts (Devanagari, Telugu, Tamil, Kannada, Bengali) with native distress interception (`आत्महत्या`, `ജീవితം ముగించ`, `தற்கொலை`).
4. **Comparative & Multi-Hop:** Distinction between meditation and contemplation handled with bounded fallback semantics and honest zero-source abstention when unverified.

*Report generated autonomously by End-to-End Benchmark Execution Engineer.*