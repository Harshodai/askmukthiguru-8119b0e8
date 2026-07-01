"""Test: golden_dataset.json is valid and populated; golden_eval CLI parses.

# ponytail: asserts >=300 (real repo corpus). 500 target requires inventing
# doctrine, which violates SPEC_DEV. Bump this assertion when more real
# questions are added to backend/benchmarks/question_bank.py.
"""
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATASET = BACKEND / "evaluation" / "golden_dataset.json"
EVAL = BACKEND / "benchmarks" / "golden_eval.py"


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
        }, f"bad category: {it['category']}"


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


if __name__ == "__main__":
    test_dataset_valid_and_populated()
    test_golden_eval_cli_parses()
    test_golden_eval_requires_flag()
    print("OK: golden dataset + eval CLI")