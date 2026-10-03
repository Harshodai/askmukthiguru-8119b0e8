"""Offline question generation (plan rev 2, card C1) -- no LLM, no Qdrant."""

import asyncio
import json

from scripts.ops.generate_first_person_questions import clean_questions, parse_llm_json, run


def _no_artifact(_q):
    return None


def test_clean_questions_filters_malformed_duplicate_and_artifact():
    raw = [
        "Why do I suffer?",
        "why do I suffer?",
        "Not a question.",
        "Hi?",
        42,
        "What is the beautiful state?",
        "The user wants me to analyze this?",
    ]
    flag = lambda q: "The user wants" if "user wants" in q else None  # noqa: E731
    assert clean_questions(raw, flag) == ["Why do I suffer?", "What is the beautiful state?"]
    assert clean_questions("not a list", _no_artifact) == []


def test_parse_llm_json_tolerates_prose_and_garbage():
    assert parse_llm_json('Sure! {"a": ["Q?"]} done') == {"a": ["Q?"]}
    assert parse_llm_json("no json") == {}
    assert parse_llm_json("{broken") == {}


def test_run_keeps_only_self_retrieving_questions_and_resumes(tmp_path):
    clips = [
        {"point_id": "p1", "verbatim_text": "Suffering is not a fact."},
        {"point_id": "p2", "verbatim_text": "Connection is the beautiful state."},
    ]
    reply = json.dumps(
        {
            "p1": ["Why do I suffer so much?", "What is connection really?"],
            "p2": ["What is connection really?"],
        }
    )
    calls = []

    async def llm(prompt):
        calls.append(prompt)
        return reply

    async def search(q):  # questions about connection retrieve p2 only
        return ["p2"] if "connection" in q else ["p1"]

    out = tmp_path / "q.json"
    summary = asyncio.run(run(clips, llm, search, _no_artifact, out))
    state = json.loads(out.read_text())
    assert state["kept"] == {
        "p1": ["Why do I suffer so much?"],
        "p2": ["What is connection really?"],
    }
    assert (summary["raw_questions"], summary["kept_questions"]) == (3, 2)
    assert summary["review_status"].startswith("UNREVIEWED")

    asyncio.run(run(clips, llm, search, _no_artifact, out))  # resume: nothing left to generate
    assert len(calls) == 1


def test_failed_batch_is_left_for_retry(tmp_path):
    async def llm(_prompt):
        raise TimeoutError("provider down")

    async def search(_q):
        return []

    out = tmp_path / "q.json"
    summary = asyncio.run(
        run([{"point_id": "p1", "verbatim_text": "x"}], llm, search, _no_artifact, out)
    )
    assert summary["clips_attempted"] == 0
