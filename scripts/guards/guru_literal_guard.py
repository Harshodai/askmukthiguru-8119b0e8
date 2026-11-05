#!/usr/bin/env python3
"""Guru registry and literal-name guard (T8-01 / T8-02 / GURU-010).

Verifies that:
1. `backend/config/gurus.yaml` adheres to the extended teacher registry schema
   (id, label, attribution_tag, aliases, rights_policy, attribution_policy, sources, allowed_surfaces).
2. All registered teachers dynamically generate impersonation refusal patterns.
3. Adding a new teacher to `gurus.yaml` extends serving, attribution, and guardrail boundaries
   without code modifications.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend/ to sys.path so we can import services and guardrails
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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
    errors = verify_guru_registry()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("[guru_literal_guard] Guru registry schema and dynamic impersonation guard PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
