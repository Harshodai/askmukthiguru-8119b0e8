"""Ruff ratchets: lint and format debt may shrink, never grow.

**Why this exists.** `.github/workflows/lint-test.yml` ran `ruff check .` and
`ruff format --check .` as hard, whole-tree, pass/fail steps. Measured on
2026-09-16 against this tree, both were RED:

    ruff check .          -> 681 errors,  exit 1
    ruff format --check . -> 318 files would be reformatted, exit 1

A gate that is red on every commit is not enforcement — it is a step everyone
learns to ignore or delete, and it blocks unrelated PRs for debt they did not
create. So the whole-tree check becomes a RATCHET pinned at the measured
present state: pre-existing debt is grandfathered, and the counts can only go
down. Adding a new violation pushes the count above baseline and fails.

Same mechanism as ``tests/test_type_check_baseline.py`` (mypy, 1335) — one
pattern for all three static-analysis baselines rather than three inventions.

**Lower these numbers as debt is paid; never raise them to hide a regression.**
The known hole is deliberate and accepted: a count ratchet lets someone add N
violations while fixing N elsewhere. Per-rule or changed-files-only gating is
the upgrade path if that ever actually happens.

ponytail: shells out rather than importing ruff's Python API (ruff has no
stable one), so this test and a developer's own `ruff check .` always agree.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RUFF_VIOLATION_BASELINE = 681
RUFF_UNFORMATTED_FILE_BASELINE = 318

_BACKEND = Path(__file__).resolve().parents[1]
_CONCISE_VIOLATION_RE = re.compile(r"^\S.*:\d+:\d+: ", re.MULTILINE)
_WOULD_REFORMAT_RE = re.compile(r"^Would reformat: ", re.MULTILINE)


def _run_ruff(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.stdout


def count_lint_violations() -> int:
    return len(_CONCISE_VIOLATION_RE.findall(_run_ruff("check", ".", "--output-format=concise")))


def count_unformatted_files() -> int:
    return len(_WOULD_REFORMAT_RE.findall(_run_ruff("format", "--check", ".")))


def test_ruff_lint_violations_do_not_regress():
    found = count_lint_violations()
    assert found <= RUFF_VIOLATION_BASELINE, (
        f"ruff lint regressed: {found} violations > baseline "
        f"{RUFF_VIOLATION_BASELINE}. Fix the new violation(s) "
        "(`ruff check . --fix` handles most), or — only if debt was genuinely "
        "paid down elsewhere — lower RUFF_VIOLATION_BASELINE to match. Never "
        "raise it."
    )


def test_ruff_format_debt_does_not_regress():
    found = count_unformatted_files()
    assert found <= RUFF_UNFORMATTED_FILE_BASELINE, (
        f"ruff format debt regressed: {found} unformatted files > baseline "
        f"{RUFF_UNFORMATTED_FILE_BASELINE}. Run `ruff format <your files>` on "
        "what you touched, then lower the baseline if it dropped."
    )


if __name__ == "__main__":  # runnable self-check — this is what CI invokes
    lint = count_lint_violations()
    fmt = count_unformatted_files()
    print(f"ruff lint violations : {lint} (baseline {RUFF_VIOLATION_BASELINE})")
    print(f"ruff unformatted files: {fmt} (baseline {RUFF_UNFORMATTED_FILE_BASELINE})")
    regressed = lint > RUFF_VIOLATION_BASELINE or fmt > RUFF_UNFORMATTED_FILE_BASELINE
    print("RUFF_RATCHET=" + ("FAIL" if regressed else "PASS"))
    sys.exit(1 if regressed else 0)
