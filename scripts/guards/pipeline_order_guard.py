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


_ARROW = re.compile(r"->|→|└──>|-->")
_BULLET = re.compile(r"^\s*[*-]\s")

#: Docs that must always match (living architecture docs).
LIVING_DOCS = (
    "backend/CLAUDE.md",
    "docs/wiki/architecture/overview.md",
    "docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md",
)
#: Dated or historical docs that quote an older or looser order. SHRINK-ONLY: a doc that
#: becomes clean must be removed from this list; a doc not listed here must be clean.
KNOWN_STALE_DOCS = frozenset(
    {
        "docs/RUTHLESS_PRODUCTION_EXECUTION.md",
        "docs/SESSION_REPORT_2026-10-03.md",
        "docs/agent/claude-md-archive/CLAUDE-full-2026-10-22.md",
        "docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md",
        "docs/plans/source_plans_2026-10-16/world_class_production_elevation_and_docker_redeploy.md",
    }
)


def _stage_index(stages: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, name in enumerate(stages):
        idx[name] = i
        idx[name[:-5] if name.endswith("Stage") else name] = i
    return idx


def chain_order_problems(text: str, stages: list[str]) -> list[str]:
    """Report arrow chains that name three or more stages out of runtime order.

    A chain is a run of consecutive non-bullet lines that each hold an arrow or a stage name,
    and at least one arrow. Partial chains are fine; the order must still agree.
    """
    idx = _stage_index(stages)
    pat = re.compile(r"\b(" + "|".join(sorted(idx, key=len, reverse=True)) + r")\b")
    lines = text.splitlines()
    problems: list[str] = []
    i = 0
    while i < len(lines):
        if _BULLET.match(lines[i]) or not (_ARROW.search(lines[i]) or pat.search(lines[i])):
            i += 1
            continue
        j = i
        while (
            j < len(lines)
            and not _BULLET.match(lines[j])
            and (_ARROW.search(lines[j]) or pat.search(lines[j]))
        ):
            j += 1
        block = "\n".join(lines[i:j])
        seq: list[int] = []
        for m in pat.finditer(block):
            k = idx[m.group(1)]
            if not seq or seq[-1] != k:
                seq.append(k)
        if _ARROW.search(block) and len(set(seq)) >= 3:
            for a, b in zip(seq, seq[1:]):
                if b < a:
                    problems.append(
                        f"line {i + 1}: {stages[b][:-5]} is listed after {stages[a][:-5]}, "
                        "but the runtime order is the reverse"
                    )
                    break
        i = j
    return problems


def stage_number_problems(text: str, stages: list[str]) -> list[str]:
    """Check 'Stage N: XStage' and 'pipeline chain (N stages)' claims."""
    problems: list[str] = []
    for m in re.finditer(r"Stage\s+(\d+)\s*[:\-–]\s*`?(\w+Stage)\b", text):
        n, name = int(m.group(1)), m.group(2)
        if name in stages and stages.index(name) + 1 != n:
            problems.append(f"'{m.group(0)}': runtime position is {stages.index(name) + 1}")
    for m in re.finditer(r"pipeline chain \((\d+) stages\)", text):
        if int(m.group(1)) != len(stages):
            problems.append(f"'{m.group(0)}': runtime has {len(stages)} stages")
    return problems


def verify_multiline_chain(doc_path: Path, stages: list[str]) -> list[str]:
    """backend/CLAUDE.md shows the full chain over several lines with arrows: match it exactly."""
    text = doc_path.read_text(encoding="utf-8")
    m = re.search(r"```\n(KillSwitch.*?)\n```", text, re.S)
    if not m:
        return [f"{doc_path.name}: full stage chain code block not found"]
    names = [s.strip() for s in re.split(r"→|->|\n", m.group(1)) if s.strip()]
    expected = [s[:-5] if s.endswith("Stage") else s for s in stages]
    if names != expected:
        return [f"{doc_path.name}: chain {names} != runtime {expected}"]
    return []


def check_docs(repo_root: Path, stages: list[str]) -> list[str]:
    errors: list[str] = []
    errors.extend(verify_multiline_chain(repo_root / "backend" / "CLAUDE.md", stages))
    docs = [repo_root / d for d in LIVING_DOCS] + sorted((repo_root / "docs").rglob("*.md"))
    seen: set[str] = set()
    for path in docs:
        rel = path.relative_to(repo_root).as_posix()
        if rel in seen or not path.is_file():
            continue
        seen.add(rel)
        text = path.read_text(encoding="utf-8", errors="ignore")
        problems = chain_order_problems(text, stages) + stage_number_problems(text, stages)
        if rel in LIVING_DOCS:
            errors.extend(f"{rel}: {p}" for p in problems)
        elif problems and rel not in KNOWN_STALE_DOCS:
            errors.append(f"{rel}: new stage-order drift: {problems[0]}")
        elif not problems and rel in KNOWN_STALE_DOCS:
            errors.append(f"{rel}: now clean. Remove it from KNOWN_STALE_DOCS.")
    for rel in sorted(KNOWN_STALE_DOCS - seen):
        errors.append(f"{rel}: listed in KNOWN_STALE_DOCS but the file is gone. Remove it.")
    return errors


def main() -> int:
    stages = get_runtime_pipeline_stages(BUILDER_PATH)
    errors = verify_claude_md_pipeline_order(CLAUDE_MD_PATH, stages)
    errors.extend(check_docs(REPO_ROOT, stages))
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
