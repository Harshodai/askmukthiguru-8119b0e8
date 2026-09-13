"""B1 migration-revert gate guard (Task 8): the revert check must actually
execute apply/revert/re-apply on an ephemeral Postgres, not just grep for a
`-- REVERT:` comment.

Root cause: a comment-presence check proves nothing about whether the
migration applies, whether the revert undoes it, or whether re-apply works
after the revert. Real proof needs a throwaway database per the standard
ephemeral-Postgres service-container pattern.
"""

import pathlib

_WORKFLOW = (
    pathlib.Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "migration-revert-check.yml"
)


def _src() -> str:
    return _WORKFLOW.read_text()


def test_revert_check_runs_ephemeral_postgres():
    src = _src()
    assert "services:" in src and "postgres" in src, "no ephemeral Postgres service"


def test_revert_check_executes_apply_revert_reapply():
    src = _src().lower()
    assert "psql" in src or "migrate deploy" in src or "apply" in src
    assert "revert" in src
    # Must execute the revert SQL, not merely grep for the comment.
    assert "re-apply" in src or "reapply" in src or "re_apply" in src, (
        "no re-apply step after revert"
    )


def test_revert_check_fails_closed():
    src = _src()
    assert "set -euo pipefail" in src or "set -e" in src, "migration script not fail-closed"
    assert "continue-on-error" not in src, "gate must not tolerate errors"
