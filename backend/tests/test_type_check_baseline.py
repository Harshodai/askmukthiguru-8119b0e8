"""mypy ratchet: fails only if the type-error count regresses past the
measured baseline — never on the pre-existing debt itself.

Baseline measured 2026-09-16:
    .venv/bin/mypy app rag domain services routers \
        --ignore-missing-imports --explicit-package-bases
    -> 1335 errors in 128 files (383 source files checked; pyproject's
       [tool.mypy] has strict=false, so this is a loose baseline by design).

mypy was declared as a dev dependency (pyproject [dependency-groups.dev]) but
never actually invoked anywhere in CI before this test existed — a config
that nobody runs enforces nothing. This is the ratchet, not a clean-sweep
demand: BASELINE_ERROR_COUNT must go DOWN as errors are fixed, and must never
be raised to paper over a real regression — only lowered to match progress.

Shells out to mypy rather than using its Python API (that API is not a
public, version-stable surface) — same approach a CI step would take, so
this test and `.venv/bin/mypy ...` on the command line always agree.
Marked ``slow`` so a fast local loop can skip it (``pytest -m "not slow"``);
plain ``pytest`` (what CI and `make test` run) still executes it — no
default marker filter is configured, so nothing is silently opted out here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BASELINE_ERROR_COUNT = 1335

_BACKEND = Path(__file__).resolve().parents[1]
_MYPY_TARGETS = ["app", "rag", "domain", "services", "routers"]


def _run_mypy() -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            *_MYPY_TARGETS,
            "--ignore-missing-imports",
            "--explicit-package-bases",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.stdout


@pytest.mark.slow
def test_mypy_error_count_does_not_regress():
    output = _run_mypy()
    errors = output.count(": error:")
    assert errors <= BASELINE_ERROR_COUNT, (
        f"mypy error count regressed: {errors} > baseline {BASELINE_ERROR_COUNT} "
        f"across {_MYPY_TARGETS}. Fix the new error(s); if this is intentional "
        "debt being paid down elsewhere, lower BASELINE_ERROR_COUNT to match "
        "(never raise it to hide a regression). Tail of mypy output:\n" + output[-3000:]
    )


if __name__ == "__main__":  # runnable self-check
    output = _run_mypy()
    errors = output.count(": error:")
    print(f"mypy errors: {errors} (baseline {BASELINE_ERROR_COUNT})")
    sys.exit(1 if errors > BASELINE_ERROR_COUNT else 0)
