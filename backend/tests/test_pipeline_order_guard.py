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


# ---- T1-15 remainder: the same guard on backend/CLAUDE.md and docs/ -----------------------

from scripts.guards import pipeline_order_guard as pog  # noqa: E402

STAGES = get_runtime_pipeline_stages(BUILDER_PATH)


def test_arrow_chain_out_of_order_is_reported():
    text = "```\nKillSwitch -> CircuitBreaker -> Distress -> Graph\n```\n"
    problems = pog.chain_order_problems(text, STAGES)
    assert problems and "CircuitBreaker" in problems[0]


def test_arrow_chain_in_order_and_partial_is_fine():
    text = "KillSwitchStage\n  └──> CacheCheckStage\n        └──> DistressStage\n"
    assert pog.chain_order_problems(text, STAGES) == []


def test_bullets_after_a_chain_are_not_part_of_it():
    text = "A -> B\nKillSwitchStage -> DistressStage\n* **Distress**: x\n* **KillSwitch**: y\n"
    assert pog.chain_order_problems(text, STAGES) == []


def test_stage_number_and_count_claims_are_checked():
    text = "Stage 8: DistressStage and pipeline chain (17 stages)"
    problems = pog.stage_number_problems(text, STAGES)
    assert any("DistressStage" in p for p in problems)
    assert any("17" in p for p in problems)
    ok = f"Stage 5: DistressStage and pipeline chain ({len(STAGES)} stages)"
    assert pog.stage_number_problems(ok, STAGES) == []


def test_backend_claude_md_chain_matches_runtime():
    assert pog.verify_multiline_chain(REPO_ROOT / "backend" / "CLAUDE.md", STAGES) == []


def test_living_docs_are_clean_and_stale_docs_only_shrink():
    errors = pog.check_docs(REPO_ROOT, STAGES)
    assert errors == [], errors
