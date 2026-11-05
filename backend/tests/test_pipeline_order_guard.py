"""Unit tests for T1-15 / CQ-009: Pipeline Order Documentation Guard."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.pipeline_order_guard import (
    BUILDER_PATH,
    CLAUDE_MD_PATH,
    get_runtime_pipeline_stages,
    verify_claude_md_pipeline_order,
)


def test_pipeline_order_in_claude_md_matches_runtime():
    stages = get_runtime_pipeline_stages(BUILDER_PATH)
    assert len(stages) == 19
    assert stages[0] == "KillSwitchStage"
    assert stages[1] == "CacheCheckStage"
    assert stages[4] == "DistressStage"
    assert stages[-1] == "ResultAssemblyStage"

    errors = verify_claude_md_pipeline_order(CLAUDE_MD_PATH, stages)
    assert errors == [], f"CLAUDE.md pipeline stage order mismatch: {errors}"
