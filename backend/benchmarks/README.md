# AskMukthiGuru Performance and Accuracy Benchmark Suite

This directory contains the unified benchmarking suite for the **AskMukthiGuru** RAG and spiritual advisor agent.

## Directory Structure

- `question_bank.py` — The ultimate collection of **250+ highly specialized queries** categorized into:
  1. Guardrails & Jailbreaks (Input validation & adversarial safety)
  2. Intent Classification Traps (Medical, Crisis, off-topic detection)
  3. Doctrine: Four Sacred Secrets
  4. Doctrine: Founders & Lokaa Foundation
  5. Doctrine: Manifest 2026 (Powers by month)
  6. Doctrine: Deeksha & Neuroscience
  7. Doctrine: Soul Sync (6-step meditation flow)
  8. Doctrine: Ekam Architecture & Peace Festival
  9. Silly & Nonsense Queries (Checking robustness under absurdity)
  10. Complex Multi-Hop Reasoning & Cross-Teaching Synthesis
  11. Hinglish & Multilingual (Sarvam 30B capability)
  12. Trick & Adversarial questions
  13. Emotional Gradients (Mild to severe distress vs crisis)
  14. Temporal Awareness
  15. Citation Accuracy
  16. Boundary Probing & Secular Discipline
  17. Latency Stress Testing

- `ruthless_benchmark.py` — High-performance HTTP client validation testing.
- `native_eval.py` — Native Ragas-style Ollama-powered context precision and answer faithfulness grader.
- `ragas_eval.py` — Legacy OpenAI-based Ragas evaluator.
- `run_all.py` — Unified runner that coordinates all suites, prints a beautiful dashboard, and publishes results.

## Running the Benchmarks

To run the complete suite, ensure the services are up and running, then execute:

```bash
python3 backend/benchmarks/run_all.py
```

### Options

- `--dry-run`: Runs only a small subset (1 question per category) to verify imports and endpoint status.
- `--endpoint <url>`: Customize the target API endpoint (default: `http://localhost:8000`).
