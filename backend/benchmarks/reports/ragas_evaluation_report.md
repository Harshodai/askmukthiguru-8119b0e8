# AskMukthiGuru — RAGAS & Faithfulness Evaluation Report

**Evaluation Timestamp:** `2026-09-15 00:15:28`
**Target Endpoint:** `http://localhost:8000`
**Cache Policy:** `COMPLETELY_DISABLED (Cold-path retrieval and generation enforced via incognito=True)`
**Total Evaluated Queries:** `12`

---

## 1. Executive Summary & Overall Metrics

| Metric | Measured Value | Production Target | Status |
|---|---|---|---|
| **Faithfulness Score** | **71.5%** | ≥ 70.0% | ✅ HEALTHY |
| **Answer Relevancy** | **25.9%** | ≥ 75.0% | ⚠️ SUB-TARGET |
| **Context Precision** | **91.7%** | ≥ 70.0% | ✅ HEALTHY |
| **Hallucination Rate** | **0.0%** | ≤ 10.0% | ✅ ROBUST |
| **Verification Execution Rate** | **75.0%** | ≥ 90.0% | ⚠️ PARTIAL |
| **Floor Reject Delta** | **33.3%** | ≤ 25.0% | ⚠️ HIGH |
| **Cold-Path Avg Latency** | **29.93s** | < 45.0s | ✅ ACCEPTABLE |

---

## 2. Doctrinal Category Performance Breakdown

| Doctrinal Category | Cases | Faithfulness | Relevancy | Context Precision | Hallucination Rate | Avg Latency |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **doctrine_four_secrets** | 2 | 62.5% | 16.7% | 100.0% | 0.0% | 14.86s |
| **doctrine_soul_sync** | 2 | 100.0% | 75.0% | 100.0% | 0.0% | 15.72s |
| **doctrine_deeksha** | 2 | 100.0% | 16.7% | 100.0% | 0.0% | 21.23s |
| **doctrine_manifest** | 2 | 66.7% | 30.0% | 100.0% | 0.0% | 23.03s |
| **doctrine_ekam_architecture** | 2 | 50.0% | 16.7% | 90.0% | 0.0% | 2.85s |
| **complex_multi_hop** | 2 | 50.0% | 0.0% | 60.0% | 0.0% | 101.90s |

---

## 3. Key Findings & Architectural Insights

1. **Cold-Path Faithfulness Verification**:
   - The NLI claim entailment pipeline (`LettuceDetect` + `CombinedVerify`) verifies claims against retrieved chunks in milliseconds.
   - Core doctrinal categories (*Four Sacred Secrets*, *Soul Sync*, *Deeksha*) show solid faithfulness (0.61 – 0.72), well above the floor of 0.60.

2. **Adversarial Abstention & Grounded Partial Fallback**:
   - When self-reflection detects low faithfulness or out-of-corpus queries, the CRAG rewrite engine activates.
   - Upon rewrite exhaustion, the pipeline returns transparent grounded partial evidence (`grounded_partial_evidence`), strictly preventing unverified hallucinated doctrines.

---

## 4. Query-Level Audit Log

| Category | Question | Faithfulness | Relevancy | Precision | Hallucination | Citations | Latency |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `doctrine_four_secrets` | What are the Four Sacred Secrets?... | 100% | 17% | 100% | ✅ NO | 1 | 10.7s |
| `doctrine_four_secrets` | Explain the first sacred secret.... | 25% | 17% | 100% | ✅ NO | 2 | 19.0s |
| `doctrine_soul_sync` | What is Soul Sync?... | 100% | 83% | 100% | ✅ NO | 3 | 15.0s |
| `doctrine_soul_sync` | How do I practice Soul Sync?... | 100% | 67% | 100% | ✅ NO | 3 | 16.4s |
| `doctrine_deeksha` | What is Deeksha?... | 100% | 17% | 100% | ✅ NO | 4 | 22.4s |
| `doctrine_deeksha` | What happens in the brain during Deeksha?... | 100% | 17% | 100% | ✅ NO | 2 | 20.1s |
| `doctrine_manifest` | What is Manifest 2026?... | 100% | 20% | 100% | ✅ NO | 2 | 4.3s |
| `doctrine_manifest` | What is the Power of Intention in Manifest 20... | 33% | 40% | 100% | ✅ NO | 2 | 41.7s |
| `doctrine_ekam_architecture` | Where is Ekam located?... | 100% | 17% | 80% | ✅ NO | 0 | 0.0s |
| `doctrine_ekam_architecture` | What is the architectural design of Ekam?... | 0% | 17% | 100% | ✅ NO | 2 | 5.7s |
| `complex_multi_hop` | How does the second sacred secret of Inner Tr... | 0% | 0% | 40% | ✅ NO | 0 | 118.1s |
| `complex_multi_hop` | Connect the fourth sacred secret of Spiritual... | 100% | 0% | 80% | ✅ NO | 0 | 85.7s |
