"""D14 (2026-10-25 data audit): seeker messages must not reach logs unscrubbed.

Seekers write about suicide, abuse and family names. Telemetry rows go through
``PIIScrubber``; a plain ``logger.info("... %s", query)`` does not. This is a
ratchet, not a clean bill: the audit confirmed two offenders (both fixed) and
this scan finds a number of other call sites that format a variable named like
seeker text. They are NOT all proven to carry raw text (some may log a
truncated or scrubbed value), so the budget is the count at the time of the fix.
It may only go down. Lower ``KNOWN_OFFENDER_BUDGET`` when you fix one.
"""

from __future__ import annotations

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
_LOGGER_NAMES = {"logger", "log", "_log", "logging"}
_SEEKER_NAMES = {
    "query",
    "retrieval_query",
    "user_msg",
    "user_message",
    "message",
    "question",
    "english_query",
    "last_user",
}
#: Offenders found on 2026-10-25 after fixing first_person_bridge and refiner (len() and hash uses excluded).
KNOWN_OFFENDER_BUDGET = 26
#: Files whose seeker-text logging was fixed and must stay fixed.
FIXED_FILES = {
    "app/pipeline/stages/first_person_bridge.py",
    "app/core/refiner.py",
}


def _safe_name_ids(arg: ast.AST) -> set[int]:
    """ids of Name nodes that only feed len(...) or a hash, which expose no text."""
    safe: set[int] = set()
    for sub in ast.walk(arg):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        is_len = isinstance(func, ast.Name) and func.id == "len"
        is_hash = isinstance(func, ast.Attribute) and func.attr in {"sha256", "md5", "blake2b"}
        if is_len or is_hash:
            safe.update(id(n) for n in ast.walk(sub) if isinstance(n, ast.Name))
    return safe


def _offenders() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for root in ("app", "services", "rag"):
        for path in sorted((_BACKEND / root).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(_BACKEND).as_posix()
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _LOG_METHODS
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in _LOGGER_NAMES
                ):
                    continue
                for arg in node.args:
                    safe = _safe_name_ids(arg)
                    hit = next(
                        (
                            sub.id
                            for sub in ast.walk(arg)
                            if isinstance(sub, ast.Name)
                            and sub.id in _SEEKER_NAMES
                            and id(sub) not in safe
                        ),
                        None,
                    )
                    if hit:
                        found.append((rel, node.lineno, hit))
                        break
    return found


def test_fixed_files_do_not_log_seeker_text_again():
    offenders = [o for o in _offenders() if o[0] in FIXED_FILES]
    assert offenders == [], offenders


def test_seeker_text_logging_budget_only_goes_down():
    offenders = _offenders()
    assert len(offenders) <= KNOWN_OFFENDER_BUDGET, (
        f"{len(offenders)} logger calls format seeker-text variables "
        f"(budget {KNOWN_OFFENDER_BUDGET}): {offenders}"
    )
