# Run consolidated "Ruthless" Benchmark Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the comprehensive production-grade "Ruthless" benchmark suite, examine responses for key question pathways, and evaluate the complete set of system features.

**Architecture:** We will invoke `scripts/benchmarks/askmukthiguru_ruthless_benchmark.py` pointing to the active local backend container at `http://localhost:8000`. We will capture the complete stdout logs, parse the detailed query-response pairs, and generate an evaluative Markdown report highlighting performance, accuracy, and safety.

**Tech Stack:** Python 3.12, HTTPX, FastAPI, LangGraph, Qdrant, Redis, Neo4j, Supabase.

---

### Task 1: Environment Readiness and Pre-Flight Checks

**Files:**
- Verify: [backend/.env](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/.env)
- Verify: [scripts/benchmarks/askmukthiguru_ruthless_benchmark.py](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/benchmarks/askmukthiguru_ruthless_benchmark.py)

- [ ] **Step 1: Check FastAPI backend status**
  Run a health check against the local backend server.
  Run: `curl -s http://localhost:8000/api/health`
  Expected: JSON containing `{"status":"healthy","services":{"qdrant":true,"ollama":true,...}}`.

- [ ] **Step 2: Dry-run the pre-flight checks of the benchmark**
  Run the benchmark script with dummy or minimal configurations to ensure imports and network routes are functional.
  Run: `python3 scripts/benchmarks/askmukthiguru_ruthless_benchmark.py --url http://localhost:8000 --test-key super-secret-jwt-token-with-at-least-32-characters-long`
  Expected: Initial connection established, pre-flight checks starting.

---

### Task 2: Comprehensive Benchmark Execution

**Files:**
- Output: `scripts/benchmarks/benchmark_run.log`
- Test: [scripts/benchmarks/askmukthiguru_ruthless_benchmark.py](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/benchmarks/askmukthiguru_ruthless_benchmark.py)

- [ ] **Step 1: Execute the consolidated Ruthless Benchmark**
  Run the benchmark script, capturing the full stdout and stderr logs into a local log file.
  Run: `python3 scripts/benchmarks/askmukthiguru_ruthless_benchmark.py --url http://localhost:8000 > scripts/benchmarks/benchmark_run.log 2>&1`
  Expected: Command executes synchronously or in background, logging query runs.

- [ ] **Step 2: Monitor log output progress**
  Check the log file size and tail the active runs to verify sequential progress.
  Run: `tail -n 20 scripts/benchmarks/benchmark_run.log`
  Expected: Successive suite logs (Guardrails, Intent Traps, Doctrine, etc.) appearing.

---

### Task 3: Response Extraction and Feature Evaluation

**Files:**
- Output: `docs/superpowers/plans/comprehensive_benchmark_report.md`
- Modify: `docs/superpowers/plans/comprehensive_benchmark_report.md`

- [ ] **Step 1: Parse and categorize the benchmark responses**
  Analyze the logged outputs in `scripts/benchmarks/benchmark_run.log` for key test cases:
  - **Guardrails**: Prompt injection defense (e.g. "hack a computer").
  - **Intent Traps**: Safety/Crisis routing (e.g. "I want to die").
  - **Doctrine**: Accuracy of the Four Sacred Secrets and Soul Sync steps.
  - **Serene Mind triggers**: Distress identification and meditation flow mapping.
  - **Adversarial**: Responses to challenging/critical queries.
  - **Citations**: Inline source URL rendering check.
  - **Contradictions & Cache**: Self-consistency and Redis caching speedups.

- [ ] **Step 2: Draft the comprehensive feature evaluation report**
  Write a complete Markdown report documenting which features passed/failed, representative responses for each question pathway, and overall score metrics.
  Create: `docs/superpowers/plans/comprehensive_benchmark_report.md`
  Expected: Clean, formatted table of categories, latency profiles, and diagnostic details.

---

### Task 4: Local Git Commit

**Files:**
- Staged: `docs/superpowers/plans/2026-05-29-run-benchmark.md`, `docs/superpowers/plans/comprehensive_benchmark_report.md`

- [ ] **Step 1: Stage and commit the plans and report**
  Add files and save state locally.
  Run: `git add docs/superpowers/plans/2026-05-29-run-benchmark.md docs/superpowers/plans/comprehensive_benchmark_report.md`
  Run: `git commit -m "docs(benchmarks): complete ruthless benchmark suite evaluation and feature analysis"`
  Expected: Clean commit on branch.
