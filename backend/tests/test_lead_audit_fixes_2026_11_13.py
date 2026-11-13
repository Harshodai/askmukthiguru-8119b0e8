"""Regression tests for the 2026-11-13 audit (config and routing findings).

- Settings declared `first_person_corpus_version` twice; the later annotation
  silently wins, so a future edit of the first one would do nothing.
- The ambiguous-domain router timed out on every call (27 of 27 in 12 h of local
  logs: measured 470-690 ms against a 0.45 s budget), so each ambiguous turn paid
  the wait and then took the fallback. It now defaults off.
- The YES/NO answerability gate was off in the live environment while the
  invariants describe it as always on; startup now says so.
"""

from __future__ import annotations

import ast
import logging
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.off_topic_stage import _AMBIGUOUS_DOMAIN_RE, OffTopicStage
from app.runtime_budget import log_runtime_budget, serving_gate_warnings

BACKEND = Path(__file__).resolve().parent.parent


def test_settings_declares_every_field_once():
    tree = ast.parse((BACKEND / "app" / "config.py").read_text())
    settings_cls = next(
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Settings"
    )
    names = Counter(
        n.target.id
        for n in settings_cls.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    )
    assert {name: count for name, count in names.items() if count > 1} == {}


def test_ambiguous_domain_router_is_off_by_default():
    assert Settings.model_fields["intent_router_ambiguous_domain_enabled"].default is False


@pytest.mark.asyncio
async def test_ambiguous_turn_takes_the_teaching_lane_without_calling_the_router(monkeypatch):
    import app.pipeline.stages.off_topic_stage as mod
    import services.jev_router_service as jev
    from app.config import settings

    question = next(
        q
        for q in (
            "what is the meaning of life",
            "how do I find peace at work",
            "why do I feel so restless",
        )
        if mod.is_spiritual_domain_query(q)
        and not mod.is_off_topic(q)
        and not mod.has_explicit_teaching_intent(q)
        and _AMBIGUOUS_DOMAIN_RE.search(q)
    )

    async def _must_not_be_called(self, _question):
        raise AssertionError("router called while the ambiguous-domain flag is off")

    monkeypatch.setattr(mod, "off_topic_handler_enabled", lambda: True)
    monkeypatch.setattr(settings, "intent_router_ambiguous_domain_enabled", False)
    monkeypatch.setattr(jev.JevRouterService, "classify", _must_not_be_called)

    ctx = PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=question,
        preferred_lang="en",
        session_id="sess-audit",
    )
    assert await OffTopicStage().run(ctx) is None
    assert ctx.state["domain_route"] == "teaching"
    assert ctx.state["general_knowledge_mode"] is False
    assert ctx.route_metadata["decision_method"] == "ambiguous_domain_teaching_default"


def _serving(**overrides):
    base = {
        "first_person_route_enabled": True,
        "first_person_chat_bridge_enabled": True,
        "first_person_answerability_check_enabled": True,
    }
    return SimpleNamespace(**{**base, **overrides})


def test_no_warning_while_the_answerability_gate_is_on():
    assert serving_gate_warnings(_serving()) == []


def test_warning_when_the_gate_is_off_and_first_person_chat_serves():
    warnings = serving_gate_warnings(_serving(first_person_answerability_check_enabled=False))
    assert len(warnings) == 1
    assert "FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=false" in warnings[0]


def test_no_warning_when_first_person_chat_is_not_serving():
    off = _serving(
        first_person_chat_bridge_enabled=False, first_person_answerability_check_enabled=False
    )
    assert serving_gate_warnings(off) == []


def test_startup_log_carries_the_gate_warning(caplog):
    posture = _serving(first_person_answerability_check_enabled=False)
    with caplog.at_level(logging.INFO, logger="audit-test"):
        log_runtime_budget(logging.getLogger("audit-test"), posture)
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert any(lvl == logging.WARNING and "Serving gate posture" in msg for lvl, msg in messages)
    assert any("LLM budget table:" in msg for _, msg in messages)
