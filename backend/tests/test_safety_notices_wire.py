"""Platform copy (support line, boundaries, framing) left the answer body, so every
live serializer must carry `safety_notices` or the copy silently disappears.

Found live (2026-10-30): the job/sync serializer in app/orchestrator.py built a
ChatResponse without it, so queued chats lost the copy while the unit tests (which
only exercise the bridge stage) stayed green.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.mark.parametrize("relpath", ["orchestrator.py", "api/chat.py"])
def test_every_chat_response_builder_sets_safety_notices(relpath):
    tree = ast.parse((APP / relpath).read_text(encoding="utf-8"))
    builders = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", "")) == "ChatResponse"
        and any(k.arg for k in n.keywords)  # keyword-built, not ChatResponse(**dict)
    ]
    assert builders, f"no ChatResponse(...) builder found in {relpath}"
    for call in builders:
        names = {k.arg for k in call.keywords}
        assert "safety_notices" in names, (
            f"{relpath}:{call.lineno} builds a ChatResponse without safety_notices"
        )
