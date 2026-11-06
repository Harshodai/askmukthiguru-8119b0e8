"""NEW-LOV-02 (LOV findings): PRs from the Lovable bot cannot change sensitive paths
without a human review label.

Nothing here talks to GitHub. The CI job itself is UNPROVEN until a real PR from
`gpt-engineer-app[bot]` runs it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "guards" / "lovable_pr_paths.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "lovable-pr-guard.yml"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
BOT = "gpt-engineer-app[bot]"


def _load():
    spec = importlib.util.spec_from_file_location("lovable_pr_paths", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path",
    [
        "bun.lock",
        "bun.lockb",
        "README.md",
        "NOTES.md",
        ".env",
        ".env.local",
        "backend/.env.example",
        "package.json",
        "package-lock.json",
        "supabase/migrations/20261101_x.sql",
        "supabase/functions/eval-run/index.ts",
        "src/integrations/supabase/types.ts",
        "src/integrations/supabase/client.ts",
    ],
)
def test_sensitive_paths_are_flagged(path):
    assert _load().violations([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "src/components/chat/ChatInterface.tsx",
        "src/pages/Index.tsx",
        "docs/runbooks/ALERTING.md",  # only ROOT markdown files are protected
        "src/locales/en.json",
        "tests/e2e/a11y-smoke.spec.ts",
    ],
)
def test_ordinary_paths_are_not_flagged(path):
    assert _load().violations([path]) == []


def _run(files: list[str], author: str, labels: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PR_AUTHOR": author, "PR_LABELS": labels}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="\n".join(files),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_bot_pr_touching_a_protected_path_fails():
    result = _run(["package.json", "src/pages/Index.tsx"], BOT, "")
    assert result.returncode == 1
    assert "package.json" in result.stdout + result.stderr


def test_bot_pr_with_the_review_label_passes():
    assert _run(["package.json"], BOT, "bug,lovable-reviewed").returncode == 0


def test_human_pr_is_never_blocked_by_this_job():
    assert _run(["package.json"], "Harshodai", "").returncode == 0


def test_bot_pr_with_only_ordinary_files_passes():
    assert _run(["src/pages/Index.tsx"], BOT, "").returncode == 0


def test_workflow_runs_on_pull_request_runs_the_guards_and_never_merges():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = data.get("on") or data.get(True)
    assert "pull_request" in on
    assert {"labeled", "unlabeled"} <= set(on["pull_request"]["types"])
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/guards/lovable_pr_paths.py" in text
    assert "scripts/guards/lesson_guards.py" in text
    assert "lovable-reviewed" in text
    for forbidden in ("auto-merge", "gh pr merge", "merge_pull_request"):
        assert forbidden not in text


def test_codeowners_covers_every_protected_path():
    text = CODEOWNERS.read_text(encoding="utf-8")
    for pattern in (
        "/bun.lock*",
        "/package.json",
        "/package-lock.json",
        "/supabase/migrations/",
        "/supabase/functions/",
        "/src/integrations/supabase/",
    ):
        assert pattern in text, pattern
