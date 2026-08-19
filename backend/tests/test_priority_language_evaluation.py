from __future__ import annotations

from evaluation.priority_language_eval import check_response, load_dataset, validate_dataset
from services.language_router import LanguageRouter


def _grounded_response() -> dict:
    return {
        "response": "Take a gentle pause, notice the breath, and return to the moment with kindness.",
        "citations": ["https://example.org/approved"],
        "answer_evidence": {"source_count": 1, "evidence_support_label": "Teaching-supported"},
        "guidance_plan": {
            "attribution": {
                "label": "Guidance inspired by retrieved teachings",
                "source_backed": True,
            },
            "reflection_prompt": "What becomes clear when you pause?",
        },
    }


def test_priority_language_fixture_has_complete_approved_coverage():
    dataset = load_dataset(
        __import__("pathlib").Path(__file__).parents[1]
        / "evaluation/datasets/priority_languages_v1.json"
    )
    assert validate_dataset(dataset) == []
    assert {item["language"] for item in dataset["items"]} == {
        "en",
        "hinglish",
        "hi",
        "te",
        "ta",
        "kn",
    }


def test_grounded_case_requires_evidence_and_a_practical_next_step():
    item = {
        "id": "case",
        "language": "en",
        "requires_source_evidence": True,
        "expects_guidance": True,
    }
    assert check_response(item, _grounded_response())["passed"] is True
    response = _grounded_response()
    response["guidance_plan"] = None
    assert "guidance_plan_missing" in check_response(item, response)["failures"]


def test_crisis_case_rejects_a_guidance_plan():
    item = {"id": "case", "language": "hi", "expects_crisis_safe": True}
    response = {
        "response": "Please contact local emergency support and someone you trust right now.",
        "guidance_plan": {"attribution": {"label": "bad"}},
    }
    assert "crisis_guidance_plan_must_be_null" in check_response(item, response)["failures"]


def test_priority_language_fixture_routes_to_its_canonical_language():
    dataset = load_dataset(
        __import__("pathlib").Path(__file__).parents[1]
        / "evaluation/datasets/priority_languages_v1.json"
    )
    router = LanguageRouter()
    mismatches = {
        item["id"]: (router.detect(item["text"]).primary.value, item["expected_router_primary"])
        for item in dataset["items"]
        if router.detect(item["text"]).primary.value != item["expected_router_primary"]
    }
    assert mismatches == {}
