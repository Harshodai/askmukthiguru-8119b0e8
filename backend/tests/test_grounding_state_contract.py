"""Every grounding_state the pipeline emits must validate against ChatResponse.

ChatResponse.grounding_state was a 4-value Literal while rag/nodes/generation.py
emitted eight distinct states. Constructing a ChatResponse on the missing ones
raised ValidationError — so either those response paths 500 in production, or
the contract was decorative and never enforced. Both are defects.

This pins the contract to the code by discovering the emitted values from source
rather than hardcoding a list, so a new response mode cannot silently reappear
outside the Literal.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from pydantic import ValidationError

from app.schemas import ChatResponse

_RAG_NODES = pathlib.Path(__file__).resolve().parents[1] / "rag" / "nodes"
_EMITTED_RE = re.compile(r'"grounding_state":\s*"([a-z_]+)"')


def _emitted_states() -> set[str]:
    found: set[str] = set()
    for path in _RAG_NODES.rglob("*.py"):
        found |= set(_EMITTED_RE.findall(path.read_text(encoding="utf-8")))
    return found


def test_source_emits_states_we_can_discover():
    """Guard the guard: if this regex stops matching, the test below is vacuous."""
    emitted = _emitted_states()
    assert len(emitted) >= 4, f"only found {emitted!r} — the discovery regex has gone stale"
    assert "grounded" in emitted


@pytest.mark.parametrize("state", sorted(_emitted_states()))
def test_every_emitted_state_validates(state: str):
    try:
        resp = ChatResponse(response="x", grounding_state=state)
    except ValidationError as exc:  # pragma: no cover - the message is the point
        pytest.fail(
            f"grounding_state={state!r} is emitted by rag/nodes but rejected by "
            f"ChatResponse — this path would 500. {exc.errors()[0].get('msg', '')}"
        )
    assert resp.grounding_state == state


def test_unknown_state_is_still_rejected():
    """Widening the contract must not turn it into a free-text field."""
    with pytest.raises(ValidationError):
        ChatResponse(response="x", grounding_state="totally_made_up_state")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
