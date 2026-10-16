"""Regression test to ensure all scenario YAML files parse cleanly with yaml.safe_load."""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = REPO_ROOT / "evals" / "scenarios"
YAML_FILES = sorted(SCENARIOS_DIR.glob("**/*.yaml"))


def test_scenario_yaml_files_exist():
    assert len(YAML_FILES) > 0, f"No scenario YAML files found in {SCENARIOS_DIR}"


@pytest.mark.parametrize("yaml_path", YAML_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_scenario_yaml_parses(yaml_path: Path):
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data is not None, f"{yaml_path} parsed to None"
    assert isinstance(data, (dict, list)), f"{yaml_path} expected dict or list, got {type(data)}"
    if isinstance(data, dict):
        assert "scenarios" in data or "turns" in data or len(data) > 0


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
