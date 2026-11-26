"""HyDE is gated on the language of the RETRIEVAL query, not the UI language (2026-11-20).

The bridge retrieves with ``state["user_msg_en"]`` (already English for an Indic turn).
Gating HyDE on ``preferred_lang`` skipped it for every non-English turn, so Indic
questions retrieved with a bare translated sentence while the same English question
got the HyDE expansion. A failed translation leaves native text in ``user_msg_en``;
HyDE stays off for that (it would expand a non-English query).
"""

from unittest.mock import AsyncMock

import pytest

import app.pipeline.stages.first_person_bridge as bridge_module
from app.config import settings
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from tests.test_first_person_bridge import _container, _ctx, fp_pipeline  # noqa: F401

_TELUGU = "కోపాన్ని ఎలా నియంత్రించాలి?"


@pytest.fixture
def hyde(monkeypatch):
    monkeypatch.setattr(settings, "first_person_hyde_enabled", True)
    bridge_module._HYDE_CACHE.clear()
    container = _container()
    container.llm = AsyncMock()
    container.llm.generate_hyde = AsyncMock(return_value="a hypothetical teaching about anger")
    return container


async def _run(container, *, msg, lang, msg_en):
    ctx = _ctx(container, msg=msg, lang=lang, is_indic=lang != "en")
    ctx.state["user_msg_en"] = msg_en
    await FirstPersonBridgeStage().run(ctx)
    return container.llm.generate_hyde


@pytest.mark.asyncio
async def test_english_turn_still_runs_hyde(hyde, fp_pipeline):  # noqa: F811
    gen = await _run(
        hyde, msg="How do I control anger?", lang="en", msg_en="How do I control anger?"
    )
    gen.assert_awaited_once()


@pytest.mark.asyncio
async def test_indic_turn_with_english_retrieval_query_runs_hyde(hyde, fp_pipeline):  # noqa: F811
    gen = await _run(hyde, msg=_TELUGU, lang="te", msg_en="How do I control anger?")
    gen.assert_awaited_once()
    assert gen.await_args.kwargs["question"] == "How do I control anger?"


@pytest.mark.asyncio
async def test_untranslated_indic_query_skips_hyde(hyde, fp_pipeline):  # noqa: F811
    gen = await _run(hyde, msg=_TELUGU, lang="te", msg_en=_TELUGU)
    gen.assert_not_awaited()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("How do I control anger?", True),
        ("What is “suffering” — really?", True),
        ("Mera mann bechain rehta hai", True),
        (_TELUGU, False),
        ("मन को शांत कैसे करें?", False),
        ("ಕೋಪ ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?", False),
        ("غصہ کیسے کم کریں؟", False),
    ],
)
def test_retrieval_query_language_check(text, expected):
    assert bridge_module._retrieval_query_is_latin(text) is expected
