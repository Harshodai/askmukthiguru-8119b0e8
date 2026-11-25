"""Readiness scope contract: staging evidence is not production authorization."""

from scripts.ops.predeployment_checklist import readiness_exit_code


def test_staging_scope_can_pass_when_staging_checks_pass() -> None:
    assert readiness_exit_code("staging", True, False) == 0


def test_staging_scope_fails_when_staging_checks_fail() -> None:
    assert readiness_exit_code("staging", False, True) == 1


def test_production_scope_requires_owner_authorization() -> None:
    assert readiness_exit_code("production", True, False) == 1


def test_production_scope_requires_staging_evidence_too() -> None:
    assert readiness_exit_code("production", False, True) == 1


def test_production_scope_passes_only_when_both_gates_pass() -> None:
    assert readiness_exit_code("production", True, True) == 0
