"""Rollback and backup files from live Qdrant fixes must never be committable.

Some of them hold verbatim quote text (the --backup file of fix_fp_unhashed_points.py).
The publication guard blocks them at commit time; .gitignore stops them at `git add`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

IGNORED = [
    ".work/backups_2026-11-07/rights_backup_v10.json",
    "rights_backup_v10.json",
    "fp_unhashed_points_backup.json",
    "first_person_v10_backup_2026-11-07.json",
    "quarantine_backup.json",
    ".env.bak_pre_v10only_20261107",
    "first_person_v10-1111874297854021-2026-11-07-01-09-45.snapshot",
    "somewhere/config.bak_20261107",
]


@pytest.mark.parametrize("path", IGNORED)
def test_backup_patterns_are_ignored(path: str) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=REPO, capture_output=True, check=False
    )
    assert result.returncode == 0, f"{path} is not ignored by .gitignore"


def test_no_rollback_file_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    bad = [
        p
        for p in tracked
        if Path(p).name.startswith(("rights_backup", "fp_", "quarantine_backup"))
        and "backup" in Path(p).name
    ]
    bad += [p for p in tracked if p.endswith(".snapshot") or ".bak_" in Path(p).name]
    assert not bad, f"rollback files are tracked: {bad}"
