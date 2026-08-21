#!/usr/bin/env python3
"""Fail closed on known catastrophic-backtracking regex shapes in runtime code.

This is intentionally conservative about the patterns it rejects. It does not
claim to prove every regex linear-time; it prevents the canonical unbounded
nested-quantifier class identified by OWASP while keeping the project’s normal
bounded and escaped patterns available.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterator, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (ROOT / "backend", ROOT / "src", ROOT / "whatsapp_bot")
EXCLUDED_PARTS = {"tests", "scripts/ingestion/corpus", "node_modules", "dist"}
REGEX_CALLS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "split"}
NESTED_GROUP_RE = re.compile(r"\((?:\?:)?(?P<body>[^()\n]*)\)(?P<outer>[+*]|\{[0-9]+,\})")
SIMPLE_REPEATED_TOKEN_RE = re.compile(
    r"^\s*(?:[A-Za-z0-9]|\\[AbBdDsSwW]|\[[^\]]+\])(?:[+*]|\{[0-9]+,\})\s*$"
)


def _has_ambiguous_nested_quantifier(pattern: str) -> bool:
    return any(SIMPLE_REPEATED_TOKEN_RE.fullmatch(match.group("body")) for match in NESTED_GROUP_RE.finditer(pattern))


def _excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel == part or rel.startswith(part + "/") for part in EXCLUDED_PARTS)


def _regex_literals(tree: ast.AST) -> Iterator[Tuple[int, str, str]]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Attribute) or function.attr not in REGEX_CALLS:
            continue
        if not node.args:
            continue
        try:
            value = ast.literal_eval(node.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(value, str):
            yield node.lineno, function.attr, value


def scan() -> list[str]:
    findings: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _excluded(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                findings.append(f"{path.relative_to(ROOT)}: parse failure: {exc}")
                continue
            for line, operation, pattern in _regex_literals(tree):
                if _has_ambiguous_nested_quantifier(pattern):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{line}: {operation} contains an unbounded nested quantifier: {pattern!r}"
                    )
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Regex safety findings:")
        print("\n".join(findings))
        return 1
    print("Regex safety check passed: no unbounded nested-quantifier literals found in runtime Python code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
