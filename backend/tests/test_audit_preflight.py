"""Read-only audit preflight parsing contracts."""

from scripts.ops.audit_preflight import _parse_dirty_paths


def test_parse_dirty_paths_preserves_status_columns() -> None:
    status = " M scripts/ops/audit_preflight.py\nA  backend/tests/test_audit_preflight.py\n?? docs/operations/current-truth-index.md\n"

    assert _parse_dirty_paths(status) == [
        "scripts/ops/audit_preflight.py",
        "backend/tests/test_audit_preflight.py",
        "docs/operations/current-truth-index.md",
    ]
