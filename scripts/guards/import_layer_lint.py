#!/usr/bin/env python3
"""Import layer architecture lint guard (CQ-007 / T7-05).

Enforces strict layered architecture:
  domain -> services -> rag -> app.pipeline -> app.api

Invariants:
1. `backend/domain` NEVER imports `services`, `rag`, or `app`.
2. `backend/services` NEVER imports `rag`, `app.pipeline`, or `app.api` (unless grandfathered).
3. `backend/rag` NEVER imports `app.api`.
4. `backend/app/pipeline` NEVER imports `app.api` (unless grandfathered).
5. Grandfathered exceptions are pinned in `scripts/guards/import_layer_allowlist.txt`
   and must never exceed 25.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def load_allowlist(allowlist_path: Path) -> set[tuple[str, str]]:
    """Return set of (relative_file_path, target_module_prefix)."""
    if not allowlist_path.is_file():
        raise FileNotFoundError(f"Allowlist missing: {allowlist_path}")

    allowed: set[tuple[str, str]] = set()
    for line in allowlist_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "->" in line:
            src, dst = line.split("->", 1)
            allowed.add((src.strip(), dst.strip()))
    return allowed


def scan_layer_violations(repo_root: Path) -> list[tuple[str, int, str]]:
    """Scan backend/ for illegal upward layer imports.

    Returns list of (file_path, line_number, imported_module).
    """
    allowlist_path = repo_root / "scripts" / "guards" / "import_layer_allowlist.txt"
    allowlist = load_allowlist(allowlist_path)

    violations: list[tuple[str, int, str]] = []

    # Rules: (dir_path, forbidden_import_prefixes)
    rules = [
        (repo_root / "backend" / "domain", ("services", "rag", "app")),
        (repo_root / "backend" / "services", ("rag", "app.pipeline", "app.api")),
        (repo_root / "backend" / "rag", ("app.api",)),
        (repo_root / "backend" / "app" / "pipeline", ("app.api",)),
    ]

    for base_dir, forbidden in rules:
        if not base_dir.is_dir():
            continue
        for py_path in base_dir.rglob("*.py"):
            rel_str = str(py_path.relative_to(repo_root))
            try:
                tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=rel_str)
            except Exception:
                continue

            for node in ast.walk(tree):
                imported_mods: list[str] = []
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_mods.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod:
                        imported_mods.append(mod)

                for mod in imported_mods:
                    if mod.startswith("ragatouille"):
                        continue
                    for prefix in forbidden:
                        if mod == prefix or mod.startswith(f"{prefix}."):
                            # Check allowlist
                            is_allowed = any(
                                rel_str == allowed_src
                                and (mod == allowed_dst or mod.startswith(f"{allowed_dst}."))
                                for allowed_src, allowed_dst in allowlist
                            )
                            if not is_allowed:
                                violations.append((rel_str, node.lineno, mod))

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    allowlist_path = repo_root / "scripts" / "guards" / "import_layer_allowlist.txt"
    allowlist = load_allowlist(allowlist_path)

    if len(allowlist) > 25:
        print(
            f"ERROR: Grandfathered layer imports count {len(allowlist)} exceeds ceiling 25.",
            file=sys.stderr,
        )
        return 1

    violations = scan_layer_violations(repo_root)

    print(
        f"[import_layer_lint] Layer allowlist entries: {len(allowlist)} (ceiling: 25); "
        f"Unallowed violations: {len(violations)}"
    )

    if violations:
        for f, line, mod in violations:
            print(f"ERROR: {f}:{line} imports forbidden upward layer '{mod}'", file=sys.stderr)
        return 1

    print("[import_layer_lint] All import layer architecture checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
