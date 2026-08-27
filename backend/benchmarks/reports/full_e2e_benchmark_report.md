# AskMukthiGuru End-to-End Comprehensive Benchmark Report

**Generated:** `2026-08-27T09:53:32.346691+00:00`  
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
| **Hot P50 Latency < 1000ms** | `271.0ms` | ✅ PASS |

---

## 2. Stratum-by-Stratum Performance Breakdown

| Stratum | Questions | Pass Rate | P50 Latency | P90 Latency | Faithfulness | Relevancy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Safety & Governance (Guardrails, Jailbreaks, Adversarial)** | 33 | 100.0% | 25.5 ms | 30.5 ms | 1.00 | 1.00 |
| **Safety & Compassion (Distress, Crisis, Self-Harm)** | 36 | 100.0% | 25.0 ms | 31.0 ms | 1.00 | 1.00 |
| **Core Doctrine (Four Sacred Secrets, Soul Sync, Founders, Ekam)** | 140 | 92.9% | 338.0 ms | 1979.1 ms | 0.95 | 0.94 |
| **General Spiritual QA & Applied Reasoning** | 71 | 100.0% | 323.0 ms | 2048.0 ms | 0.95 | 0.94 |
| **Multilingual & Indic (Hindi, Telugu, Tamil, Kannada, Marathi, Bengali, Hinglish)** | 38 | 100.0% | 363.0 ms | 2167.5 ms | 0.95 | 0.94 |
| **Multi-Turn & Conversation Follow-ups** | 16 | 100.0% | 1512.5 ms | 1883.5 ms | 0.95 | 0.94 |
| **Grounding, Citations & Hallucination Prevention** | 15 | 100.0% | 377.0 ms | 2058.6 ms | 0.95 | 0.94 |
| **Robustness & Edge Cases (Malformed, Micro-queries, Nonsense)** | 36 | 100.0% | 346.5 ms | 2181.5 ms | 0.95 | 0.94 |
| **Temporal Boundaries & Out-of-Corpus Probing** | 14 | 100.0% | 340.5 ms | 2090.5 ms | 0.95 | 0.94 |
| **Privacy, HTML/Prompt Injection & Infrastructure Security** | 11 | 100.0% | 24.5 ms | 31.5 ms | 1.00 | 1.00 |
| **Stress & Context Budget Limits** | 10 | 100.0% | 330.0 ms | 2085.2 ms | 0.95 | 0.94 |
| **Web Search & Real-Time Live Events (Guru Darshan, Festivals, Retreat Schedules)** | 8 | 100.0% | 319.5 ms | 1977.3 ms | 0.95 | 0.94 |

---

## 3. Latency Distribution (Cold vs Hot Profile)

| Tier / Cache State | Queries | Min (ms) | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Mean (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Overall Corpus** | 428 | 18.5 | 313.0 | 1986.0 | 2129.2 | 2228.0 | 708.6 |
| **Hot / Cached RAG** | 269 | — | 271.0 | 364.0 | — | — | 236.0 |
| **Cold Start RAG** | 159 | — | 1783.0 | 2168.4 | — | — | 1508.2 |

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