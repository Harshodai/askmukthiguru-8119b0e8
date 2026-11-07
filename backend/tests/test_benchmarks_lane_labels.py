"""EVAL-003 / EVAL-004: legacy benchmarks say which path they measure.

``FIRST_PERSON_LLM_FALLBACK_ENABLED=false`` is the owner's live setting, so answers are a
verbatim clip or a static abstain. Benchmarks that score generated prose (faithfulness,
answer relevancy, voice closeness of prose) measure the dormant generating path. They carry
``LEGACY_GENERATION_PATH = True``. The serving-lane gate is ``evals/pr_suite`` with
``tests/test_offline_pr_suite.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1] / "benchmarks"

#: Static read (2026-11-07): each file scores generated answer prose or calls generation.
LEGACY_FILES = {
    "comprehensive_benchmark.py",
    "generate_dashboard.py",
    "golden_eval.py",
    "guru_voice_benchmark.py",
    "lightrag_answer_comparison.py",
    "native_eval.py",
    "ragas_eval.py",
    "run_comprehensive_ragas.py",
    "run_full_e2e_benchmark.py",
    "ruthless_benchmark.py",
}


def _declares_legacy(path: Path) -> bool:
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "LEGACY_GENERATION_PATH" for t in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and node.value.value is True
        ):
            return True
    return False


def test_legacy_generation_benchmarks_are_labelled():
    missing = sorted(f for f in LEGACY_FILES if not _declares_legacy(_BENCH / f))
    assert missing == [], f"add LEGACY_GENERATION_PATH = True to: {missing}"


def test_no_other_benchmark_claims_the_label():
    extra = sorted(
        p.name for p in _BENCH.glob("*.py") if p.name not in LEGACY_FILES and _declares_legacy(p)
    )
    assert extra == [], f"not in LEGACY_FILES: {extra}"


def test_readme_names_the_serving_lane_gate_and_every_legacy_file():
    text = (_BENCH / "README.md").read_text(encoding="utf-8")
    assert "evals/pr_suite" in text and "LEGACY_GENERATION_PATH" in text
    for name in LEGACY_FILES:
        assert name in text, name
