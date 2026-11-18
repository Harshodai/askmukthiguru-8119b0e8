#!/usr/bin/env python3
"""Exception ratchet guard (CQ-006 / T7-05).

Scans scoped directories (`backend/app`, `backend/rag`, `backend/services/first_person*`)
for:
1. Silent swallows (`except ...: pass` without logging, re-raising, or metric tracking).
2. Broad exception handlers (`except Exception:`, `except:`, `except BaseException:`).

Enforces that:
- 0 silent swallows exist in `backend/services/first_person*`.
- Total broad exception count does not exceed `scripts/guards/exception_baseline.txt`.
- The baseline is a ratchet: it only goes down.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def parse_baseline(baseline_path: Path) -> tuple[int, int, int]:
    """Return (max_broad_exceptions, max_silent_swallows, max_silent_swallows_fp)."""
    if not baseline_path.is_file():
        raise FileNotFoundError(f"Baseline file missing: {baseline_path}")

    max_broad = 1000
    max_swallows = 50
    max_swallows_fp = 0
    for line in baseline_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key == "max_broad_exceptions":
                max_broad = int(val)
            elif key == "max_silent_swallows":
                max_swallows = int(val)
            elif key == "max_silent_swallows_fp":
                max_swallows_fp = int(val)
    return max_broad, max_swallows, max_swallows_fp


def scan_exceptions(repo_root: Path) -> tuple[int, list[tuple[str, int]], list[tuple[str, int]]]:
    """Scan scoped directories and return (broad_count, all_silent_swallows, silent_swallows_fp)."""
    if (repo_root / "backend").is_dir():
        backend_dir = repo_root / "backend"
    else:
        backend_dir = repo_root

    targets = [
        backend_dir / "app",
        backend_dir / "rag",
        backend_dir / "services",
    ]

    broad_count = 0
    all_silent_swallows: list[tuple[str, int]] = []
    silent_swallows_fp: list[tuple[str, int]] = []

    for target in targets:
        if not target.is_dir():
            continue
        for py_path in target.rglob("*.py"):
            rel = py_path.relative_to(backend_dir)
            rel_str = f"backend/{rel}"

            is_fp_service = "backend/services" in rel_str and "first_person" in rel_str
            is_scoped = "backend/app" in rel_str or "backend/rag" in rel_str or is_fp_service
            if not is_scoped:
                continue

            try:
                tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=rel_str)
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    is_broad = node.type is None or (
                        isinstance(node.type, ast.Name)
                        and node.type.id in ("Exception", "BaseException")
                    )
                    if is_broad:
                        broad_count += 1
                        # Check silent swallow: body is a single `pass` on a broad catch
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                            all_silent_swallows.append((rel_str, node.lineno))
                            if is_fp_service:
                                silent_swallows_fp.append((rel_str, node.lineno))

    return broad_count, all_silent_swallows, silent_swallows_fp


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    baseline_path = repo_root / "scripts" / "guards" / "exception_baseline.txt"

    max_broad, max_swallows, max_swallows_fp = parse_baseline(baseline_path)
    broad_count, all_swallows, silent_swallows_fp = scan_exceptions(repo_root)

    print(
        f"[exception_ratchet] Broad exceptions: {broad_count} (baseline max: {max_broad}); "
        f"Total silent swallows: {len(all_swallows)} (max: {max_swallows}); "
        f"FP silent swallows: {len(silent_swallows_fp)} (max: {max_swallows_fp})"
    )

    errors = []
    if broad_count > max_broad:
        errors.append(
            f"Broad exception count {broad_count} exceeds baseline {max_broad}. "
            "Catch specific exceptions instead of broad `except Exception`."
        )

    if len(all_swallows) > max_swallows:
        errors.append(
            f"Total silent swallow count {len(all_swallows)} exceeds baseline {max_swallows}."
        )

    if len(silent_swallows_fp) > max_swallows_fp:
        errors.append(
            f"Found {len(silent_swallows_fp)} silent swallows in services/first_person*: {silent_swallows_fp}. "
            "Silent `pass` in exception handlers is forbidden."
        )

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("[exception_ratchet] All exception ratchet checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
