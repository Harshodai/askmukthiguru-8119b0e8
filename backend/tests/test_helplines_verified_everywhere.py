"""SAFE-004 remainder (T4-07): every crisis-helpline block shows call-verified lines only.

Owner decision quoted from audits/audit-output-2026-11-04/IMPLEMENTATION-AGENT-PROMPT.md:
"Owner decisions 2026-11-06 (Harsha, thread: "accept as it is"): (1) the distress
answer keeps call-verified lines only (Tele-MANAS today, no 112 or non-India line
until a call date is recorded)". T4-07 in the same file: "show only call-verified
helplines."

Two call sites passed ``verified_only=True`` before (intent.handle_distress and
rag/meditation). This file covers the rest, and the edge case that must never
happen: a seeker in crisis sees an empty block. When no line qualifies, the
filter falls back to the national line (Tele-MANAS) and the emergency number
(112, verified by its official listing and never test-called).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services import crisis_helplines as ch
from services.language_router import LanguageCode

BACKEND = Path(__file__).resolve().parents[1]
TELE_MANAS = "14416"


def _unverified_contacts() -> set[str]:
    return {h.contact.strip() for h in ch.get_helplines() if not ch._is_call_verified_and_fresh(h)}


def _assert_verified_block(text: str) -> None:
    assert text.strip(), "a crisis block must never be empty"
    assert TELE_MANAS in text
    for contact in _unverified_contacts():
        assert contact not in text, f"unverified number shown: {contact}"


def test_every_production_call_passes_verified_only():
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", ".venv/")) or rel == "services/crisis_helplines.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", getattr(node.func, "attr", None))
                == "format_helplines_block"
            ):
                kw = {k.arg: k.value for k in node.keywords}
                ok = (
                    isinstance(kw.get("verified_only"), ast.Constant)
                    and kw["verified_only"].value is True
                )
                if not ok:
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, f"format_helplines_block without verified_only=True: {offenders}"


@pytest.mark.parametrize("region_key", ["global", "india", "us", "uk", "unknown-region"])
def test_serene_mind_crisis_resource_is_verified_and_never_empty(region_key):
    from services.serene_mind_engine import get_crisis_resource

    _assert_verified_block(get_crisis_resource(region_key))


def test_system_prompt_distress_block_is_verified():
    from rag.prompts import system

    _assert_verified_block(system.build_distress_prompt())


def test_guardrail_block_templates_are_verified():
    from guardrails import lightweight_handler as lh

    rendered = [
        lh._resolve_block_response(category, "")
        for category, template in lh._BLOCK_RESPONSES.items()
        if "__HELPLINES__" in template
    ]
    assert rendered, "at least one guardrail template carries helplines"
    for text in rendered:
        _assert_verified_block(text)


@pytest.mark.parametrize("lang", [code.value for code in LanguageCode])
def test_kill_switch_block_is_verified_in_every_language(lang, monkeypatch):
    from app.config import settings
    from app.pipeline.stages.kill_switch_stage import KillSwitchStage

    monkeypatch.setattr(settings, "generation_kill_switch_enabled", True)
    ctx = MagicMock(preferred_lang=lang, trace_id="t", start_time=0.0)
    result = asyncio.run(KillSwitchStage().run(ctx))
    _assert_verified_block(result.final_answer)


@pytest.mark.parametrize("lang", [code.value for code in LanguageCode])
def test_support_line_is_verified_in_every_language(lang):
    # The support line is not translated; the same verified line goes to every
    # language (quotes and numbers are never translated).
    _assert_verified_block(ch.format_support_line())


def test_block_never_empty_when_no_line_is_fresh():
    for style in ("bullet", "inline", "compact_two_line"):
        for region in (None, "India", "United States", "United Kingdom", "Nowhere"):
            text = ch.format_helplines_block(
                region=region, style=style, verified_only=True, max_age_days=-1
            )
            assert text.strip(), (style, region)
            assert TELE_MANAS in text, (style, region)
