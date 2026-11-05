#!/usr/bin/env python3
"""Config lint guard (CQ-010 / T2-06).

Scans repository Python files for undeclared `getattr(settings, "...")` reads
where the attribute is not declared on ``app.config.Settings``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def get_declared_settings_members(config_path: Path) -> set[str]:
    """Extract all declared field names, assignments, and methods on Settings."""
    if not config_path.is_file():
        raise FileNotFoundError(f"Settings file not found: {config_path}")

    tree = ast.parse(config_path.read_text(encoding="utf-8"), filename=str(config_path))
    members: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    members.add(item.target.id)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            members.add(target.id)
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(item.name)
    return members


def find_undeclared_settings_reads(
    repo_root: Path,
) -> list[tuple[str, str, int]]:
    """Scan backend/ and scripts/ for undeclared getattr(settings, "attr", ...).

    Returns a list of tuples: (attribute_name, relative_file_path, line_number).
    """
    config_path = repo_root / "backend" / "app" / "config.py"
    declared_members = get_declared_settings_members(config_path)

    undeclared: list[tuple[str, str, int]] = []
    scan_dirs = [repo_root / "backend", repo_root / "scripts"]

    # Files where config or info is known not to refer to app.config.Settings
    ignored_subpaths = {
        "rag/nodes/utils.py",  # LangGraph RunnableConfig
        "migrations/maintenance_runner.py",  # Qdrant collection config
        "guardrails/rejection_handler.py",  # HuggingFace PretrainedConfig
        "benchmarks/quantization_pilot.py",  # Qdrant quantization config
    }

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_path in scan_dir.rglob("*.py"):
            parts = py_path.parts
            if ".venv" in parts or "node_modules" in parts or "__pycache__" in parts:
                continue

            rel_path = str(py_path.relative_to(repo_root))
            if any(rel_path.endswith(ignored) for ignored in ignored_subpaths):
                continue

            try:
                content = py_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_path))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "getattr" and len(node.args) >= 2:
                        obj, attr_arg = node.args[0], node.args[1]
                        if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                            attr_name = attr_arg.value
                            is_settings = False
                            if isinstance(obj, ast.Name) and obj.id in (
                                "settings",
                                "cfg",
                                "config",
                            ):
                                is_settings = True
                            elif isinstance(obj, ast.Attribute) and obj.attr in (
                                "settings",
                                "config",
                            ):
                                is_settings = True

                            if is_settings and attr_name not in declared_members:
                                undeclared.append((attr_name, rel_path, getattr(node, "lineno", 0)))

    return sorted(undeclared)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    undeclared = find_undeclared_settings_reads(repo_root)
    if undeclared:
        print(f"FAILED: Found {len(undeclared)} undeclared settings reads:", file=sys.stderr)
        for attr, path, line in undeclared:
            print(f"  {path}:{line}: undeclared getattr(settings, {attr!r})", file=sys.stderr)
        return 1

    print("PASS: 0 undeclared settings reads found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
