"""DEBUG can never leak (2026-11-28): LOG_DEBUG_LOGGERS turns on DEBUG for named loggers.

Exception text can echo the input that raised it (a validation error carries its value; a
provider error can carry a request body), and these modules handle seeker text, clip text
and LLM replies. So no DEBUG or INFO call in the first-person modules may format a bare
exception variable: log ``type(exc).__name__``. WARNING and ERROR lines on infrastructure
failures (Qdrant, Redis, files) keep their message on purpose.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

import app.main as main_module

_BACKEND = Path(__file__).resolve().parents[1]
_MODULES = (
    "services/first_person_pipeline.py",
    "services/first_person_legacy.py",
    "services/first_person_context_store.py",
    "services/first_person_context_harness.py",
    "services/first_person_judge.py",
    "app/pipeline/stages/first_person_bridge.py",
)
# Dotted logger name of each audited module (the logger is ``logging.getLogger(__name__)``).
_AUDITED_LOGGERS = {m[:-3].replace("/", ".") for m in _MODULES}
_EXC_NAMES = {
    "exc",
    "e",
    "_e",
    "_exc",
    "err",
    "error",
    "_hyde_exc",
    "_seen_exc",
    "_cs_exc",
    "_rec_exc",
    "try2_exc",
    "_t2_err",
    "_t2_emb_exc",
    "json_err",
    "refusal_exc",
    "settle_exc",
    "replay_exc",
}
_TEXT_NAMES = {"raw", "reply", "hyde_text", "verbatim_text", "assembled_answer_text"}


def _bare_name(node: ast.AST, names: set[str]) -> str | None:
    """A Name from ``names`` that is not wrapped in type(...) or len(...)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in {"type", "len"}:
            return None
    if isinstance(node, ast.Name) and node.id in names:
        return node.id
    for child in ast.iter_child_nodes(node):
        found = _bare_name(child, names)
        if found:
            return found
    return None


def _debug_info_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"debug", "info"}
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
        ):
            yield node


@pytest.mark.parametrize("module", _MODULES)
def test_debug_and_info_lines_never_format_exception_or_reply_text(module):
    offenders = []
    for call in _debug_info_calls(_BACKEND / module):
        for arg in call.args:
            hit = _bare_name(arg, _EXC_NAMES | _TEXT_NAMES)
            if hit:
                offenders.append((module, call.lineno, hit))
                break
    assert offenders == [], offenders


@pytest.mark.parametrize("module", _MODULES)
def test_debug_and_info_lines_never_attach_a_traceback(module):
    """exc_info=True prints the exception message, the same leak by another route."""
    offenders = [
        (module, call.lineno, kw.arg)
        for call in _debug_info_calls(_BACKEND / module)
        for kw in call.keywords
        if kw.arg in {"exc_info", "stack_info"}
    ]
    assert offenders == [], offenders


# --- LOG_DEBUG_LOGGERS --------------------------------------------------------------------


def test_the_allowlist_is_exactly_the_audited_modules():
    """Adding a module to the allowlist requires adding it to this audit, and vice versa."""
    assert main_module.DEBUG_LOGGER_ALLOWLIST == _AUDITED_LOGGERS


def test_default_changes_nothing():
    assert main_module.apply_debug_loggers("") == ([], 0)
    assert main_module.apply_debug_loggers("   ,, ") == ([], 0)


@pytest.fixture
def _restore_levels():
    names = list(main_module.DEBUG_LOGGER_ALLOWLIST) + [
        "services",
        "app",
        "rag",
        "services.openrouter_service",
    ]
    before = {n: logging.getLogger(n).level for n in names}
    yield
    for n, level in before.items():
        logging.getLogger(n).setLevel(level)


def test_audited_loggers_go_to_debug(_restore_levels):
    applied, ignored = main_module.apply_debug_loggers(
        "services.first_person_pipeline, app.pipeline.stages.first_person_bridge"
    )
    assert applied == ["services.first_person_pipeline", "app.pipeline.stages.first_person_bridge"]
    assert ignored == 0
    assert logging.getLogger("services.first_person_pipeline").level == logging.DEBUG


def test_parents_unaudited_and_junk_names_are_rejected_not_expanded(_restore_levels):
    before = {
        n: logging.getLogger(n).level
        for n in ("services", "app", "rag", "services.openrouter_service")
    }
    applied, ignored = main_module.apply_debug_loggers(
        "services,app,rag,services.openrouter_service,bad name!,../../etc,"
    )
    assert applied == []
    assert ignored == 6
    assert {n: logging.getLogger(n).level for n in before} == before


def test_setting_is_declared_and_empty_by_default():
    from app.config import Settings

    assert Settings.model_fields["log_debug_loggers"].default == ""
