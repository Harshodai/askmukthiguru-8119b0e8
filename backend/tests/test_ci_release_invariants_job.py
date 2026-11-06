"""NEW-ANS-8: CI must run the release invariants as their own job.

Static check on `.github/workflows/lint-test.yml`. Whether the job is a REQUIRED
check for main is a branch-protection setting and needs the owner's agreement;
no file in the repo can prove or set it (UNPROVEN until the owner confirms).
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "lint-test.yml"


def test_release_invariants_job_runs_the_invariants_file_and_installs_deps():
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert "release-invariants" in jobs
    job = jobs["release-invariants"]
    assert job["name"] == "release-invariants"
    runs = [step.get("run", "") for step in job["steps"]]
    assert any("pytest tests/test_release_invariants.py" in r for r in runs)
    assert any("requirements.lock" in r for r in runs), "deps are not installed"
    env = next(s["env"] for s in job["steps"] if "test_release_invariants" in s.get("run", ""))
    # Fakes only: the job must not be given a real provider key.
    assert env["OPENROUTER_API_KEY"].startswith("mock-")


def test_release_invariants_file_exists():
    root = WORKFLOW.parents[2]
    assert (root / "backend" / "tests" / "test_release_invariants.py").is_file()
