"""Regression tests for Failure Injection FI-17: Indic Crisis Copy in Native Languages.

Guarantees:
1. Authentic Tele-MANAS (14416) and emergency (112) guidance in:
   - Hindi (`hi`)
   - Telugu (`te`)
   - Tamil (`ta`)
   - Kannada (`kn`)
   - Marathi (`mr`)
2. Deterministic native-language referral prepending when preferred_lang is one of hi, te, ta, kn, mr.
3. ZERO runtime LLM calls (translate_text never awaited; pure static reviewed constants).
4. Verbatim preservation of helpline numbers and English safety questions.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.pipeline.stages.distress_stage import (
    INDIC_CRISIS_RESPONSES,
    INDIC_NEXT_STEPS,
    DistressStage,
)
from services.serene_mind_engine import (
    DistressAssessment,
    DistressLevel,
    IndicCrisisDict,
)

INDIC_LANGS = ["hi", "te", "ta", "kn", "mr"]

# Characteristic native script substrings for each language
NATIVE_SCRIPT_SNIPPETS = {
    "hi": "टेली-मानस",
    "te": "టెలి-మానస్",
    "ta": "டெலி-மானாஸ்",
    "kn": "ಟೆಲಿ-ಮಾನಸ್",
    "mr": "टेलि-मानस",
}


def _make_indic_context(preferred_lang: str):
    translation = AsyncMock()
    # Guard against accidental runtime LLM translation
    translation.translate_text = AsyncMock(
        side_effect=AssertionError("FAIL: runtime LLM translation called in crisis path!")
    )
    return SimpleNamespace(
        container=SimpleNamespace(
            translation=translation,
            serene_mind=None,
        ),
        is_indic=True,
        preferred_lang=preferred_lang,
        trace_id=f"test-trace-{preferred_lang}",
        start_time=time.time(),
        has_distress_keywords=True,
        routing_chain=[],
    )


def test_indic_crisis_responses_and_next_steps_structure():
    """Verify all 5 languages are defined with required response variants."""
    for lang in INDIC_LANGS:
        assert lang in INDIC_CRISIS_RESPONSES, f"Missing {lang} in INDIC_CRISIS_RESPONSES"
        assert lang in INDIC_NEXT_STEPS, f"Missing {lang} in INDIC_NEXT_STEPS"

        resp_dict = INDIC_CRISIS_RESPONSES[lang]
        steps_dict = INDIC_NEXT_STEPS[lang]

        assert isinstance(resp_dict, IndicCrisisDict)
        assert isinstance(steps_dict, IndicCrisisDict)

        for variant in ["crisis", "severe", "severe_ideation_checkin", "third_party_crisis"]:
            assert variant in resp_dict, (
                f"Missing variant {variant} in INDIC_CRISIS_RESPONSES[{lang}]"
            )
            assert variant in steps_dict, f"Missing variant {variant} in INDIC_NEXT_STEPS[{lang}]"
            assert len(resp_dict[variant].strip()) > 20
            assert len(steps_dict[variant].strip()) > 20


def test_helpline_numbers_present_in_all_5_indic_languages():
    """Verify authentic Tele-MANAS (14416) and Emergency (112) exist in all 5 languages."""
    for lang in INDIC_LANGS:
        resp = INDIC_CRISIS_RESPONSES[lang]
        steps = INDIC_NEXT_STEPS[lang]

        # Verify dict-level substring check
        assert "14416" in resp, f"14416 missing in INDIC_CRISIS_RESPONSES[{lang}]"
        assert "112" in resp, f"112 missing in INDIC_CRISIS_RESPONSES[{lang}]"
        assert "Tele-MANAS" in resp, f"Tele-MANAS missing in INDIC_CRISIS_RESPONSES[{lang}]"

        assert "14416" in steps, f"14416 missing in INDIC_NEXT_STEPS[{lang}]"
        assert "112" in steps, f"112 missing in INDIC_NEXT_STEPS[{lang}]"
        assert "Tele-MANAS" in steps, f"Tele-MANAS missing in INDIC_NEXT_STEPS[{lang}]"

        # Verify per-variant crisis copy contains the exact contact numbers
        assert "14416" in resp["crisis"]
        assert "112" in resp["crisis"]
        assert "14416" in steps["crisis"]
        assert "112" in steps["crisis"]


def test_indic_crisis_dict_behavior():
    """Verify IndicCrisisDict works seamlessly as both dict and string."""
    d = IndicCrisisDict({"crisis": "Call 14416 now", "severe": "Call 112 if in danger"})
    assert isinstance(d, dict)
    assert d["crisis"] == "Call 14416 now"
    assert d.get("severe") == "Call 112 if in danger"
    assert str(d) == "Call 14416 now"
    assert "14416" in d
    assert "112" in d
    assert d.startswith("Call")
    assert d.lower().startswith("call")
    assert d.strip() == "Call 14416 now"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", INDIC_LANGS)
async def test_distress_stage_prepends_indic_referral_all_5_languages(lang):
    """Verify distress_stage deterministically prepends native referral with 0 LLM calls."""
    ctx = _make_indic_context(preferred_lang=lang)
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS,
        confidence=1.0,
        detected_signals=["test-signal"],
        recommended_response_type="crisis",
    )

    result = await DistressStage._crisis_preemption_result(ctx, assessment)

    assert result is not None
    assert result.intent == "DISTRESS"
    assert result.route_decision == "crisis_preempted"
    assert result.route_metadata.get("crisis_copy_indic") == lang

    final_answer = result.final_answer

    # 1. Native script snippet must be present
    assert NATIVE_SCRIPT_SNIPPETS[lang] in final_answer, (
        f"Expected native snippet '{NATIVE_SCRIPT_SNIPPETS[lang]}' in final_answer for lang={lang}"
    )

    # 2. Both critical helpline numbers must appear verbatim
    assert "14416" in final_answer, f"14416 missing in final_answer for {lang}"
    assert "112" in final_answer, f"112 missing in final_answer for {lang}"
    assert "Tele-MANAS" in final_answer

    # 3. Fixed English reviewed crisis copy must still be present
    assert "Are you safe right now" in final_answer

    # 4. English crisis helpline resource block must lead
    assert final_answer.startswith("🆘")

    # 5. ZERO runtime LLM calls
    ctx.container.translation.translate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", INDIC_LANGS)
async def test_third_party_crisis_in_indic_languages(lang):
    """Verify third-party crisis referral contains helper guidance in native script."""
    ctx = _make_indic_context(preferred_lang=lang)
    assessment = DistressAssessment(
        level=DistressLevel.CRISIS,
        confidence=0.95,
        detected_signals=["third_party"],
        recommended_response_type="third_party_crisis",
    )

    result = await DistressStage._crisis_preemption_result(ctx, assessment)
    final_answer = result.final_answer

    # Third party helper guidance in native script
    assert NATIVE_SCRIPT_SNIPPETS[lang] in final_answer
    assert "112" in final_answer
    assert "14416" in final_answer
    assert "Thank you for caring enough" in final_answer

    # ZERO LLM calls
    ctx.container.translation.translate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", INDIC_LANGS)
async def test_severe_ideation_checkin_in_indic_languages(lang):
    """Verify passive ideation check-in delivers tender native copy and helplines."""
    ctx = _make_indic_context(preferred_lang=lang)
    assessment = DistressAssessment(
        level=DistressLevel.SEVERE,
        confidence=0.9,
        detected_signals=["passive_ideation"],
        recommended_response_type="severe_ideation_checkin",
    )

    result = await DistressStage._crisis_preemption_result(ctx, assessment)
    final_answer = result.final_answer

    assert NATIVE_SCRIPT_SNIPPETS[lang] in final_answer
    assert "14416" in final_answer
    assert "112" in final_answer
    assert "I hear real pain in what you're describing" in final_answer

    # ZERO LLM calls
    ctx.container.translation.translate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lang", "raw_message"),
    [
        ("hi", "मैं अपनी जान देना चाहता हूँ"),
        ("te", "నేను చనిపోవాలనుకుంటున్నాను"),
        ("ta", "நான் தற்கொலை செய்து கொள்ள விரும்புகிறேன்"),
        ("kn", "ನಾನು ಸಾಯಲು ಬಯಸುತ್ತೇನೆ"),
        ("mr", "मला आत्महत्या करायची आहे"),
    ],
)
async def test_distress_stage_run_end_to_end_indic(lang, raw_message):
    """End-to-end stage execution with raw native script crisis input."""
    stage = DistressStage()
    ctx = _make_indic_context(preferred_lang=lang)
    ctx.user_msg = raw_message
    ctx.state = {
        "user_msg_en": "I want to die",
        "distress_history": [],
    }

    result = await stage.run(ctx)

    assert result is not None
    assert result.intent == "DISTRESS"
    assert result.route_decision == "crisis_preempted"
    assert result.route_metadata["crisis_copy_indic"] == lang
    assert NATIVE_SCRIPT_SNIPPETS[lang] in result.final_answer
    assert "14416" in result.final_answer
    assert "112" in result.final_answer

    # ZERO LLM calls
    ctx.container.translation.translate_text.assert_not_awaited()
