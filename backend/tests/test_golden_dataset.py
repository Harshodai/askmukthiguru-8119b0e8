"""Test: golden_dataset.json is valid and populated; golden_eval CLI parses.

# ponytail: asserts >=300 (real repo corpus). 500 target requires inventing
# doctrine, which violates SPEC_DEV. Bump this assertion when more real
# questions are added to backend/benchmarks/question_bank.py.
"""

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DATASET = BACKEND / "evaluation" / "golden_dataset.json"
EVAL = BACKEND / "benchmarks" / "golden_eval.py"
RUN_GOLDEN_EVAL = BACKEND / "evaluation" / "run_golden_eval.py"


def test_dataset_valid_and_populated():
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    assert "items" in data and isinstance(data["items"], list)
    # 319 real questions exist in the repo; 500 would need invented doctrine.
    assert len(data["items"]) >= 300, f"expected >=300 real questions, got {len(data['items'])}"
    required = {"id", "query", "category", "expected_intent"}
    for it in data["items"]:
        assert required.issubset(it.keys()), f"item missing fields: {it}"
        assert it["category"] in {
            "doctrinal",
            "relational",
            "comparative",
            "practical_meditation",
            "multilingual",
            "adversarial_refusal",
            "safety_regression",
        }, f"bad category: {it['category']}"
    assert data.get("category_counts") == dict(Counter(it["category"] for it in data["items"]))


def test_golden_eval_cli_parses():
    r = subprocess.run(
        [sys.executable, str(EVAL), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "--smoke" in r.stdout and "--full" in r.stdout


def test_golden_eval_requires_flag():
    r = subprocess.run(
        [sys.executable, str(EVAL)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 2  # missing required flag -> usage error


def test_golden_eval_fails_without_backend_url():
    env = {k: v for k, v in os.environ.items() if k != "BACKEND_URL"}
    r = subprocess.run(
        [sys.executable, str(EVAL), "--smoke", "1"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert r.returncode == 1
    assert "BACKEND_URL not set, eval skipped" in r.stderr


def test_run_golden_eval_fails_without_backend_url(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "BACKEND_URL"}
    out_file = tmp_path / "report.json"
    r = subprocess.run(
        [
            sys.executable,
            str(RUN_GOLDEN_EVAL),
            "--dataset",
            str(DATASET),
            "--out",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert r.returncode == 1
    assert "BACKEND_URL not set, eval skipped" in r.stderr


def test_groundedness_zero_citations_and_empty_context():
    from benchmarks.golden_eval import groundedness

    # Closes the hallucination 1.0 loophole where answers without citations or context were compared against themselves
    assert groundedness("query", "hallucinated answer without context", "", has_citations=False) == 0.0
    assert groundedness("query", "hallucinated answer without context", "   ", has_citations=False) == 0.0
    assert groundedness("query", "hallucinated answer", "some context", has_citations=False) == 0.0
    assert groundedness("query", "hallucinated answer", "", has_citations=True) == 0.0
    assert groundedness("query", "hallucinated answer", "   ", has_citations=True) == 0.0


def test_groundedness_positive_lexical_fallback():
    from benchmarks.golden_eval import groundedness

    score = groundedness(
        query="what is soul sync?",
        answer="soul sync is a meditation practice of conscious breath",
        context="soul sync is a meditation practice focusing on conscious breath and stillness",
        has_citations=True,
    )
    assert score > 0.5


if __name__ == "__main__":
    test_dataset_valid_and_populated()
    test_golden_eval_cli_parses()
    test_golden_eval_requires_flag()
    test_golden_eval_fails_without_backend_url()
    test_groundedness_zero_citations_and_empty_context()
    test_groundedness_positive_lexical_fallback()
    print("OK: golden dataset + eval CLI tests pass")
