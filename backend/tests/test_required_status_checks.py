"""NEW-LOV-01 / L-REQUIRED-CHECK-NAME-IS-JOB-NAME-1:

Assert that the required status check names documented for branch protection on `main`
match the actual job identifiers and check-run names in the GitHub Actions workflow YAML files.

The required status checks are:
1. `release-invariants` (defined in .github/workflows/lint-test.yml)
2. `lovable-guard` (defined in .github/workflows/lovable-pr-guard.yml)

They must NOT be named after workflow files or workflow titles (e.g. `lovable-pr-guard`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "lint-test.yml"
LOVABLE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "lovable-pr-guard.yml"

DOCUMENTED_REQUIRED_CHECKS = {
    "release-invariants",
    "lovable-guard",
}


def _get_check_run_names(workflow_path: Path) -> dict[str, str]:
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", {})
    names = {}
    for job_id, job_def in jobs.items():
        name = job_def.get("name") or job_id
        names[job_id] = name
    return names


def test_required_check_names_match_actual_workflow_job_names():
    lint_test_jobs = _get_check_run_names(LINT_TEST_WORKFLOW)
    lovable_jobs = _get_check_run_names(LOVABLE_WORKFLOW)

    all_check_runs = set(lint_test_jobs.values()) | set(lovable_jobs.values())

    for req_check in DOCUMENTED_REQUIRED_CHECKS:
        assert req_check in all_check_runs, (
            f"Documented required check '{req_check}' does not match any check run in {all_check_runs}"
        )


def test_lovable_pr_guard_workflow_name_is_not_check_run_name():
    lovable_data = yaml.safe_load(LOVABLE_WORKFLOW.read_text(encoding="utf-8"))
    workflow_title = lovable_data.get("name")
    assert workflow_title == "lovable-pr-guard"

    lovable_jobs = _get_check_run_names(LOVABLE_WORKFLOW)
    assert "lovable-guard" in lovable_jobs.values()
    assert "lovable-pr-guard" not in lovable_jobs.values()
