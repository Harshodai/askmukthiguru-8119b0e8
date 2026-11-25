#!/usr/bin/env python3
"""Read-only audit preflight for reproducible repository evidence.

This command never changes files, services, databases, or deployment state. It records the
repository identity and dirty paths so an audit cannot accidentally attribute pre-existing
working-tree changes to the current remediation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def _root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() and (parent / "AGENTS.md").exists():
            return parent
    raise RuntimeError("repository root not found")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _parse_dirty_paths(status: str) -> list[str]:
    """Parse ``git status --short`` without losing its two-column prefix."""
    return [line[3:] for line in status.splitlines() if len(line) >= 4]


def collect_preflight(root: Path | None = None, scope: str = "local") -> dict[str, Any]:
    """Collect only repository metadata; no external or application calls are made."""
    root = root or _root()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    upstream = ""
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except subprocess.CalledProcessError:
        upstream = None
    dirty_paths = _parse_dirty_paths(status)
    return {
        "repository": str(root),
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
        "upstream": upstream,
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "evidence_scope": scope,
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--scope",
        choices=("local", "ci", "staging", "production"),
        default="local",
        help="label the evidence scope; this flag does not promote local evidence",
    )
    args = parser.parse_args(argv)
    result = collect_preflight(scope=args.scope)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"branch: {result['branch'] or '(detached)'}")
        print(f"head: {result['head']}")
        print(f"upstream: {result['upstream'] or '(none)'}")
        print(f"evidence_scope: {result['evidence_scope']}")
        print(f"dirty: {result['dirty']}")
        for path in result["dirty_paths"]:
            print(f"dirty_path: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
