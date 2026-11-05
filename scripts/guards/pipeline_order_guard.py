#!/usr/bin/env python3
"""Pipeline order documentation guard (CQ-009 / T1-15).

Verifies that the stage order described in documentation (e.g. `CLAUDE.md`)
matches the exact runtime stage sequence built by
``app.pipeline.stages.pipeline_builder.build_default_pipeline()``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO_ROOT / "backend" / "app" / "pipeline" / "stages" / "pipeline_builder.py"
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"


def get_runtime_pipeline_stages(builder_path: Path) -> list[str]:
    """Parse pipeline_builder.py AST and extract Stage class names instantiated in build_default_pipeline."""
    if not builder_path.is_file():
        raise FileNotFoundError(f"Builder file missing: {builder_path}")

    tree = ast.parse(builder_path.read_text(encoding="utf-8"), filename=str(builder_path))
    stages: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_default_pipeline":
            for stmt in node.body:
                # Look for `stages = [...]` or `stages: list[Stage] = [...]` or `stages.extend([...])`
                targets_to_inspect = []
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and isinstance(
                    stmt.value, ast.List
                ):
                    targets_to_inspect.extend(stmt.value.elts)
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if (
                        isinstance(call.func, ast.Attribute)
                        and call.func.attr == "extend"
                        and call.args
                        and isinstance(call.args[0], ast.List)
                    ):
                        targets_to_inspect.extend(call.args[0].elts)

                for elt in targets_to_inspect:
                    if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name):
                        stages.append(elt.func.id)

    return stages


def verify_claude_md_pipeline_order(doc_path: Path, runtime_stages: list[str]) -> list[str]:
    """Verify that CLAUDE.md documents the exact same sequence of stages."""
    if not doc_path.is_file():
        return [f"Doc file missing: {doc_path}"]

    content = doc_path.read_text(encoding="utf-8")
    match = re.search(r"Chain\s*\([^)]+\):\s*([^\n]+)", content)
    if not match:
        return ["Could not find pipeline chain definition matching 'Chain (...): ...' in CLAUDE.md"]

    chain_str = match.group(1).strip()
    if ". " in chain_str:
        chain_str = chain_str.split(". ")[0].strip()
    # Normalize stage names (strip 'Stage' suffix for matching if doc uses short names)
    doc_stages_raw = [s.strip() for s in re.split(r"->|\s+->\s+", chain_str) if s.strip()]
    doc_stages = [re.sub(r"\s*\(.*?\)", "", s).rstrip(".").strip() for s in doc_stages_raw]
    # Filter empty or trailing details
    doc_stages = [s for s in doc_stages if s]

    # Map each runtime stage to both FullNameStage and ShortName
    expected_full = runtime_stages
    expected_short = [s[:-5] if s.endswith("Stage") else s for s in runtime_stages]

    errors: list[str] = []
    if len(doc_stages) != len(runtime_stages):
        errors.append(
            f"Doc has {len(doc_stages)} stages but runtime has {len(runtime_stages)} stages.\n"
            f"Doc: {doc_stages}\nRuntime: {expected_short}"
        )
        return errors

    for i, (doc_s, exp_short, exp_full) in enumerate(
        zip(doc_stages, expected_short, expected_full)
    ):
        if doc_s not in (exp_short, exp_full):
            errors.append(
                f"Stage {i + 1} mismatch: doc says '{doc_s}' but runtime is '{exp_short}' ({exp_full})"
            )

    return errors


def main() -> int:
    stages = get_runtime_pipeline_stages(BUILDER_PATH)
    errors = verify_claude_md_pipeline_order(CLAUDE_MD_PATH, stages)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(
        f"[pipeline_order_guard] Pipeline order in CLAUDE.md matches build_default_pipeline() "
        f"({len(stages)} stages verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
