"""Config class guards (Task 6): every getattr(settings, ...) literal must be declared.

`services/llm_budget_guard.py` read `llm_budget_fail_closed` through
`getattr(settings, "llm_budget_fail_closed", False)` with no declared field,
so the generic guard silently ran fail-open even though its declared twin
`openrouter_budget_fail_closed` defaults True.
"""

import pathlib
import re

from app.config import Settings

_GUARD_FILES = (
    pathlib.Path(__file__).resolve().parents[1] / "services" / "llm_budget_guard.py",
    pathlib.Path(__file__).resolve().parents[1] / "app" / "openrouter_budget.py",
)

_GETATTR_RE = re.compile(r'getattr\(\s*settings\s*,\s*["\']([^"\']+)["\']')


def _getattr_literals() -> set[str]:
    names: set[str] = set()
    for path in _GUARD_FILES:
        names.update(_GETATTR_RE.findall(path.read_text()))
    return names


def test_getattr_names_are_declared():
    s = Settings()
    for n in sorted(_getattr_literals()):
        assert hasattr(s, n), n


def test_no_direct_os_environ_in_owned_modules():
    base = pathlib.Path(__file__).resolve().parents[1]
    for rel in ("app/config.py", "services/llm_budget_guard.py"):
        src = (base / rel).read_text()
        assert "os.environ" not in src, rel
        assert "os.getenv" not in src, rel
