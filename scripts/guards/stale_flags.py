#!/usr/bin/env python3
"""List boolean feature flags in backend/app/config.py that look stale.

Categories (static analysis only; it cannot see a deployed .env):
  UNUSED     the name appears nowhere except its declaration in config.py. Dead code: safe to delete.
  TEST_ONLY  the name appears only in tests (and docs/config files). Nothing in product code reads it.
  REDUNDANT  an .env.example / compose / workflow file sets it to the same value as its default.
             Informational: such a pin is often deliberate (safety flags); it is never fatal.

Exit 1 when an UNUSED flag is not listed in scripts/guards/stale_flags_allowlist.txt, so a new dead
flag fails CI instead of accumulating. TEST_ONLY and REDUNDANT are reported, never fatal.

  python3 scripts/guards/stale_flags.py [--json]
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "backend/app/config.py"
ALLOW = ROOT / "scripts/guards/stale_flags_allowlist.txt"
SKIP_SUFFIX = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".json", ".jsonl", ".xlsx", ".wav"}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENV_ASSIGN = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*['\"]?([A-Za-z0-9_.-]+)", re.M
)
TRUE, FALSE = {"true", "1", "yes", "on"}, {"false", "0", "no", "off"}


def bool_flags() -> dict[str, bool | None]:
    """name -> literal default (None when the default is not a plain True/False)."""
    tree = ast.parse(CONFIG.read_text())
    flags: dict[str, bool | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and ast.unparse(stmt.annotation) == "bool"
                ):
                    default = None
                    if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, bool):
                        default = stmt.value.value
                    flags[stmt.target.id] = default
    return flags


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if Path(f).suffix not in SKIP_SUFFIX]


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{path}"
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts"))
    )


def is_env_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        name.startswith(".env")
        or name.startswith("docker-compose")
        or path.startswith(".github/workflows/")
    )


def analyse() -> dict[str, dict]:
    flags = bool_flags()
    names = {n.lower(): n for n in flags}
    config_rel = str(CONFIG.relative_to(ROOT))
    code: Counter = Counter()
    tests: Counter = Counter()
    other: Counter = Counter()
    overrides: dict[str, set[bool]] = {}
    for rel in tracked_files():
        try:
            text = (ROOT / rel).read_text(errors="ignore")
        except OSError:
            continue
        counts = Counter(t.lower() for t in IDENT.findall(text) if t.lower() in names)
        if rel == config_rel:
            for key, n in counts.items():
                code[key] += n - 1  # the declaration itself
            continue
        bucket = (
            tests
            if is_test(rel)
            else other
            if rel.endswith((".md", ".txt")) or is_env_file(rel)
            else code
        )
        for key, n in counts.items():
            bucket[key] += n
        if is_env_file(rel):
            for var, val in ENV_ASSIGN.findall(text):
                if var.lower() in names and val.lower() in TRUE | FALSE:
                    overrides.setdefault(var.lower(), set()).add(val.lower() in TRUE)
    result: dict[str, dict] = {}
    for key, name in names.items():
        default = flags[name]
        if code[key] == 0 and tests[key] == 0 and other[key] == 0:
            kind = "UNUSED"
        elif code[key] == 0 and tests[key] > 0:
            kind = "TEST_ONLY"
        elif default is not None and overrides.get(key) == {default}:
            kind = "REDUNDANT"
        else:
            continue
        result[name] = {
            "kind": kind,
            "default": default,
            "tests": tests[key],
            "docs_or_env": other[key],
        }
    return dict(sorted(result.items(), key=lambda kv: (kv[1]["kind"], kv[0])))


def allowlisted() -> set[str]:
    if not ALLOW.exists():
        return set()
    return {
        ln.strip() for ln in ALLOW.read_text().splitlines() if ln.strip() and not ln.startswith("#")
    }


def main(argv: list[str]) -> int:
    report = analyse()
    allow = allowlisted()
    blocking = sorted(n for n, r in report.items() if r["kind"] == "UNUSED" and n not in allow)
    if "--json" in argv:
        print(json.dumps({"flags": report, "blocking": blocking}, indent=2))
    else:
        for name, r in report.items():
            print(
                f"{r['kind']:<10} {name}  (default={r['default']}, tests={r['tests']}, docs/env={r['docs_or_env']})"
            )
        print(f"\n{len(report)} stale-looking flag(s); {len(blocking)} blocking.")
    if blocking:
        print(
            "\nUNUSED flags (declared in config.py, read nowhere). Delete them, or list them in "
            "scripts/guards/stale_flags_allowlist.txt with a reason:\n  " + "\n  ".join(blocking),
            file=sys.stderr,
        )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
