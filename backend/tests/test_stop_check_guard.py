"""scripts/guards/stop_check.sh: block only on unpushed commits; a dirty tree only warns."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/guards/stop_check.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    (work / "a.txt").write_text("a")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "init")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-u", "origin", "main")
    return work


def _run(cwd: Path, payload: str = "{}") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=cwd, input=payload, capture_output=True, text=True
    )


def test_clean_tree_passes_silently(repo: Path):
    result = _run(repo)
    assert result.returncode == 0
    assert result.stdout == ""


def test_dirty_tree_warns_but_does_not_block(repo: Path):
    (repo / "a.txt").write_text("changed")
    result = _run(repo)
    assert result.returncode == 0
    assert "systemMessage" in result.stdout
    assert "a.txt" in result.stdout


def test_unpushed_commit_blocks(repo: Path):
    (repo / "a.txt").write_text("changed")
    _git(repo, "commit", "-am", "local only")
    result = _run(repo)
    assert result.returncode == 2
    assert "1 unpushed commit" in result.stderr


def test_stop_hook_active_never_blocks_twice(repo: Path):
    (repo / "a.txt").write_text("changed")
    _git(repo, "commit", "-am", "local only")
    assert _run(repo, '{"stop_hook_active": true}').returncode == 0
