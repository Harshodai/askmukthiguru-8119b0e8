#!/usr/bin/env python3
"""CI tripwire for CRIT-1: JWT_SECRET must never unlock the benchmark backdoor.

A reintroduced coupling takes the form of a function scope in which the
X-Test-Key header value is derived from / compared against the token-signing
secret (jwt_secret / jwt_sec / JWT_SECRET). The historical v2 backdoor was
multi-line:

    test_key = request.headers.get("X-Test-Key")
    jwt_sec = getattr(settings, "jwt_secret", None)
    is_benchmark = bool(test_key and jwt_sec and test_key == jwt_sec)

A same-line grep cannot see that (the tokens are on separate lines), so this
scanner walks the AST instead and flags any function that references BOTH the
X-Test-Key header AND a jwt-secret token in its code. Docstrings/comments are
ignored (the guard's own docstring explains that JWT_SECRET is rejected, so a
naive text scan would false-positive on the very code that fixes this).

Files that fail to parse are scanned with a file-level both-tokens check
(a genuinely malformed file cannot host the coupling, and a hard failure on
it would only cause noise). Fail-closed: exit 1 on any coupling OR scan
error; exit 0 only when the tree is clean.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_HEADER_TOKEN = "X-Test-Key"
_JWT_TOKENS = ("jwt_secret", "jwt_sec", "JWT_SECRET")

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

# Files that intentionally send JWT_SECRET as X-Test-Key to ASSERT the server
# rejects it (regression / red-team test clients). They are the proof the guard
# works, not backdoor couplings, so the scanner must not flag them.
_EXCLUDED_FILES = {
    "test_no_jwt_secret_backdoor.py",
    "redteam_harness.py",
}


def _has_x_test_key(value: str) -> bool:
    return _HEADER_TOKEN in value


def _has_jwt_token(value: str) -> bool:
    return any(token in value for token in _JWT_TOKENS)


def _scan_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    hits = {"header": False, "jwt": False}
    body = list(func.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ) and isinstance(body[0].value.value, str):
        body = body[1:]
    for stmt in body:
        _walk_for_tokens(stmt, hits)
    return hits["header"] and hits["jwt"]


def _walk_for_tokens(node: ast.AST, hits: dict) -> None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if _has_x_test_key(node.value):
            hits["header"] = True
        elif _has_jwt_token(node.value):
            hits["jwt"] = True
    elif isinstance(node, ast.Name) and _has_jwt_token(node.id):
        hits["jwt"] = True
    elif isinstance(node, ast.Attribute) and _has_jwt_token(node.attr):
        hits["jwt"] = True
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        _walk_for_tokens(child, hits)


def _text_scan(path: Path) -> list[str]:
    """Fallback for files that fail to parse: file-level both-tokens check.

    Flags any file containing BOTH an X-Test-Key token AND a jwt-secret token
    (jwt_secret / jwt_sec / JWT_SECRET) at ANY distance. Strictly stronger than
    the old 200-char window (a coupling spread further apart or assembled
    across names evaded it) and still bounded: O(file length).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"error: {path}: {exc}"]
    findings = []
    if _has_x_test_key(text) and _has_jwt_token(text):
        for jwt in _JWT_TOKENS:
            if jwt in text:
                findings.append(
                    f"{path}: {jwt} and X-Test-Key present in same file (file unparseable)"
                )
    return findings


def _scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return _text_scan(path)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _scan_function(node):
                findings.append(
                    f"{path}:{node.lineno}: {node.name}() couples X-Test-Key with a jwt secret"
                )
    return findings


def main() -> int:
    findings: list[str] = []
    for path in _REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.name in _EXCLUDED_FILES:
            continue
        findings.extend(_scan_file(path))

    if findings:
        print("CRIT-1 gate failed: JWT_SECRET coupled with the benchmark X-Test-Key backdoor:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("CRIT-1 gate OK: no X-Test-Key/jwt-secret coupling found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
