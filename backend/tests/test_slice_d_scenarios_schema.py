"""Slice D — scenarios YAML schema: required keys, dup IDs, severity labels.

Locks the eval-corpus contract that ``run_safety_scenarios.py`` and the
red-team harness rely on:

1. Required keys: every scenario carries a non-empty string ``id``, an int
   ``tier``, a non-empty ``title``, and a non-empty ``turns`` list whose
   entries each carry an int ``turn`` and non-empty string ``user``.
2. Turn order: ``turn`` numbers run 1..N with no gaps (escalation and
   must-include-by-turn-N assertions index on this).
3. Dup IDs: all 272 scenario ids are unique across all 17 files (verified
   live before pinning: total == unique).
4. Severity labels: ``tier`` is a real int in {0, 1, 2, 3} (never a bool or
   string); ``tags``/``language``, when present, are non-empty (list of
   non-empty strings / non-empty string).

Both file shapes are covered: the single-scenario top-level file and the
``scenarios:``-list files (including ``{id: ...}`` flow-style entries,
which parse as plain dicts).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = REPO_ROOT / "evals" / "scenarios"
YAML_FILES = sorted(SCENARIOS_DIR.glob("**/*.yaml"))

ALLOWED_TIERS = {0, 1, 2, 3}


def _entries_of(yaml_path: Path) -> list[dict]:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), f"{yaml_path}: top level must be a mapping"
    if "scenarios" in data:
        entries = data["scenarios"]
        assert isinstance(entries, list) and entries, f"{yaml_path}: empty scenarios"
        return entries
    assert "turns" in data, f"{yaml_path}: neither 'scenarios' nor 'turns' present"
    return [data]


def _all_entries() -> list[tuple[Path, dict]]:
    out = []
    for path in YAML_FILES:
        for entry in _entries_of(path):
            assert isinstance(entry, dict), f"{path}: scenario entry must be a mapping"
            out.append((path, entry))
    return out


def test_scenario_files_exist():
    assert len(YAML_FILES) == 17, f"expected 17 scenario files, found {len(YAML_FILES)}"


@pytest.mark.parametrize("yaml_path", YAML_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_scenario_required_keys(yaml_path: Path):
    for entry in _entries_of(yaml_path):
        sid = entry.get("id")
        assert isinstance(sid, str) and sid.strip(), f"{yaml_path}: bad id {sid!r}"
        assert isinstance(entry.get("tier"), int) and not isinstance(
            entry.get("tier"), bool
        ), f"{yaml_path} {sid}: tier must be int"
        assert isinstance(entry.get("title"), str) and entry["title"].strip(), (
            f"{yaml_path} {sid}: title required"
        )
        turns = entry.get("turns")
        assert isinstance(turns, list) and turns, f"{yaml_path} {sid}: turns required"
        for t in turns:
            assert isinstance(t, dict), f"{yaml_path} {sid}: turn must be a mapping"
            assert isinstance(t.get("turn"), int), f"{yaml_path} {sid}: turn needs int 'turn'"
            assert isinstance(t.get("user"), str) and t["user"].strip(), (
                f"{yaml_path} {sid}: turn needs non-empty 'user'"
            )


@pytest.mark.parametrize("yaml_path", YAML_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_scenario_turns_sequential_from_one(yaml_path: Path):
    for entry in _entries_of(yaml_path):
        nums = [t["turn"] for t in entry["turns"]]
        assert nums == list(range(1, len(nums) + 1)), (
            f"{yaml_path} {entry.get('id')}: turns must run 1..N, got {nums}"
        )


def test_scenario_ids_unique_across_corpus():
    seen: dict[str, Path] = {}
    total = 0
    for path, entry in _all_entries():
        total += 1
        sid = entry["id"]
        assert sid not in seen, f"duplicate scenario id {sid!r}: {seen[sid]} vs {path}"
        seen[sid] = path
    assert total == len(seen) > 0


def test_scenario_severity_labels_valid():
    for path, entry in _all_entries():
        tier = entry["tier"]
        assert tier in ALLOWED_TIERS, (
            f"{path} {entry.get('id')}: tier {tier!r} not a severity 0-3"
        )
        tags = entry.get("tags")
        if tags is not None:
            assert isinstance(tags, list) and tags, (
                f"{path} {entry.get('id')}: tags must be a non-empty list"
            )
            for tag in tags:
                assert isinstance(tag, str) and tag.strip(), (
                    f"{path} {entry.get('id')}: empty tag"
                )
        lang = entry.get("language")
        if lang is not None:
            assert isinstance(lang, str) and lang.strip(), (
                f"{path} {entry.get('id')}: language must be a non-empty string"
            )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
