#!/usr/bin/env python3
"""Guru registry and literal-name guard (T8-01 / T8-02 / GURU-010).

Verifies that:
1. `backend/config/gurus.yaml` adheres to the extended teacher registry schema
   (id, label, attribution_tag, aliases, rights_policy, attribution_policy, sources, allowed_surfaces).
2. All registered teachers dynamically generate impersonation refusal patterns.
3. Adding a new teacher to `gurus.yaml` extends serving, attribution, and guardrail boundaries
   without code modifications.
4. (T8-02) Lines in runtime code that spell a teacher name ("krishnaji", "preethaji") are a
   RATCHET: per-file counts in `scripts/guards/guru_literal_baseline.txt` may only go down.
   A new file or a higher count fails. A lower count also fails until the baseline is lowered.

Scope of the scan: line count, not meaning. It does not tell a routing literal from a
docstring, and it does not look at other teacher names or at Indic spellings.

Usage:
    python3 scripts/guards/guru_literal_guard.py                 # registry checks + ratchet
    python3 scripts/guards/guru_literal_guard.py --write-baseline  # lower the baseline (never raises)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add backend/ to sys.path so we can import services and guardrails
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASELINE_PATH = Path(__file__).resolve().parent / "guru_literal_baseline.txt"
SCAN_ROOTS = (
    "backend/app",
    "backend/rag",
    "backend/services",
    "backend/guardrails",
    "backend/domain",
    "backend/ingest",
    "src",
)
SCAN_SUFFIXES = {".py", ".ts", ".tsx"}
SKIP_DIRS = {"tests", "test", "__tests__", "node_modules", "locales", "__pycache__"}
#: The registry itself may name teachers.
EXEMPT_FILES = {"backend/services/guru_registry.py"}
LITERAL_RE = re.compile(r"krishnaji|preethaji", re.IGNORECASE)


def scan_literals(repo_root: Path) -> dict[str, int]:
    """Return {repo-relative path: number of lines naming a teacher} for runtime code."""
    counts: dict[str, int] = {}
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            parts = set(path.relative_to(repo_root).parts[:-1])
            name = path.name
            if (
                parts & SKIP_DIRS
                or rel in EXEMPT_FILES
                or ".test." in name
                or ".spec." in name
                or name.startswith("test_")
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            n = sum(1 for line in text.splitlines() if LITERAL_RE.search(line))
            if n:
                counts[rel] = n
    return counts


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rel, _, num = line.rpartition("\t")
        out[rel] = int(num)
    return out


def compare(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    errors: list[str] = []
    for rel, n in sorted(counts.items()):
        allowed = baseline.get(rel, 0)
        if n > allowed:
            errors.append(
                f"{rel}: {n} teacher-name lines, baseline allows {allowed}. "
                "Use services.guru_registry (aliases, labels) instead of a literal."
            )
    for rel, allowed in sorted(baseline.items()):
        n = counts.get(rel, 0)
        if n < allowed:
            errors.append(
                f"{rel}: now {n}, baseline {allowed}. Good. Lower the baseline: "
                "python3 scripts/guards/guru_literal_guard.py --write-baseline"
            )
    return errors


def write_baseline(counts: dict[str, int], path: Path = BASELINE_PATH) -> None:
    old = load_baseline(path) if path.exists() else {}
    raised = [r for r, n in counts.items() if n > old.get(r, 0)]
    if old and raised:
        raise SystemExit(f"Refusing to raise the baseline for: {', '.join(raised)}")
    lines = [
        "# T8-02 / GURU-010: lines naming a teacher in runtime code, per file.",
        "# RATCHET: counts may only go down. Format: <path><TAB><count>.",
        f"# Total at write time: {sum(counts.values())} lines in {len(counts)} files.",
    ]
    lines += [f"{r}\t{n}" for r, n in sorted(counts.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


from services.guru_registry import (
    get_gurus,
    get_impersonation_patterns,
    validate_guru_registry_schema,
)


def verify_guru_registry() -> list[str]:
    errors: list[str] = []

    # 1. Schema check
    schema_errors = validate_guru_registry_schema()
    if schema_errors:
        errors.extend(schema_errors)

    # 2. Dynamic impersonation generation check
    patterns = get_impersonation_patterns()
    if not patterns:
        errors.append("get_impersonation_patterns() returned no patterns")

    gurus = get_gurus()
    for g in gurus:
        # Every registered teacher must appear in generated impersonation patterns
        if not any(g.id in pat or g.label in pat for pat in patterns):
            errors.append(
                f"Guru '{g.id}' ({g.label}) is not covered by generated impersonation patterns"
            )

    return errors


def main() -> int:
    counts = scan_literals(REPO_ROOT)
    if "--write-baseline" in sys.argv:
        write_baseline(counts)
        print(f"[guru_literal_guard] baseline written: {sum(counts.values())} lines.")
        return 0
    errors = verify_guru_registry()
    if BASELINE_PATH.exists():
        errors.extend(compare(counts, load_baseline()))
    else:
        errors.append(f"missing baseline {BASELINE_PATH.name}; run with --write-baseline once")
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(
        "[guru_literal_guard] registry schema, impersonation patterns and literal ratchet PASSED "
        f"({sum(counts.values())} lines in {len(counts)} files)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
