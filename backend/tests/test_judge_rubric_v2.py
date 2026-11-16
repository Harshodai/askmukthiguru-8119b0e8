"""Judge rubric switch (v1 pinned, v2 strict completeness) and the offline replay tool."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from app.config import settings
from scripts.ops import run_judge_replay as rjr
from services import first_person_judge as fj
from services import first_person_pipeline as fpp

# sha256 of the v1 prompt at HEAD before the rubric switch; an edit must be a new version.
V1_PROMPT_SHA256 = "08f6fa04faf01305620321c031795be5f0689a50760dd35e795b79062c774cbf"
REPLY = json.dumps(
    {
        "scores": [
            {
                "i": 0,
                "relevance": 3,
                "answers": True,
                "is_complete_thought": True,
                "is_standalone": True,
                "covered_facets": ["general"],
                "content_safety": "clean",
            }
        ],
        "question_answerable": True,
    }
)


class StubLLM:
    def __init__(self, reply: str = REPLY) -> None:
        self.reply, self.systems = reply, []

    async def generate(self, **kw):
        self.systems.append(kw["system_prompt"])
        return self.reply


def test_v1_prompt_hash_pinned():
    assert hashlib.sha256(fj.JUDGE_SYSTEM_PROMPT.encode()).hexdigest() == V1_PROMPT_SHA256
    assert fj.judge_system_prompt("v1") == fj.JUDGE_SYSTEM_PROMPT


def test_v2_adds_five_categories_and_keeps_schema():
    v2 = fj.judge_system_prompt("v2")
    assert v2.startswith(fj.JUDGE_SYSTEM_PROMPT)
    block = v2[len(fj.JUDGE_SYSTEM_PROMPT) :]
    for n in "12345":
        assert f"\n{n}. " in block
    assert "merely related" in block
    assert len(block.split()) < 250
    # output schema sentence is the v1 one, untouched
    assert '{"scores": [{"i": 0, "relevance": 0, "answers": false,' in v2
    with pytest.raises(ValueError):
        fj.judge_system_prompt("v3")


@pytest.mark.parametrize("rubric", ["v1", "v2"])
def test_call_site_sends_active_rubric(monkeypatch, rubric):
    monkeypatch.setattr(settings, "first_person_judge_enabled", True)
    monkeypatch.setattr(settings, "first_person_judge_rubric", rubric)
    llm = StubLLM()
    out = asyncio.run(fpp._relevance_select_async("q", [{"verbatim_text": "t"}], llm))
    assert out == 0
    assert llm.systems == [fj.judge_system_prompt(rubric)]


def test_explicit_rubric_overrides_setting_without_mutation(monkeypatch):
    monkeypatch.setattr(settings, "first_person_judge_rubric", "v1")
    llm = StubLLM()
    asyncio.run(
        fj.judge_select_async(
            "q", [{"verbatim_text": "t"}], llm, minimum=3, timeout_s=5, rubric="v2"
        )
    )
    assert llm.systems == [fj.judge_system_prompt("v2")]
    assert settings.first_person_judge_rubric == "v1"


def test_parse_accepts_same_reply_under_both():
    assert fj.parse_judge_reply(REPLY, 1) is not None  # schema is rubric independent


def test_rubric_rekeys_cache_fingerprint(monkeypatch):
    monkeypatch.setattr(settings, "first_person_judge_rubric", "v1")
    assert fpp._judge_rubric_fingerprint() == {}
    monkeypatch.setattr(settings, "first_person_judge_rubric", "v2")
    assert fpp._judge_rubric_fingerprint() == {"judge_rubric": "v2"}


# --- replay tool ------------------------------------------------------------------------------


def _row(i, cited=True, answer="clip text"):
    return {
        "id": i,
        "question": "q",
        "answer": answer,
        "citations": [{"text": "c"}] if cited else [],
    }


GRADES = {
    "first": {
        "a": {"verdict": "showable"},
        "b": {"verdict": "showable"},
        "c": {"verdict": "not_showable"},
        "d": {"verdict": "not_showable"},
        "e": {"verdict": "unsure"},
        "f": {"verdict": "showable"},
    },
    "second": {
        "a": {"verdict": "showable"},
        "b": {"verdict": "showable"},
        "c": {"verdict": "not_showable"},
        "d": {"verdict": "showable"},
        "e": {"verdict": "showable"},
        "f": {"verdict": "showable"},
    },
}


def test_served_row_detection():
    rows = [_row("a"), _row("x", cited=False), _row("y", answer="  "), _row("z")]
    assert [r["id"] for r in rjr.served_rows(rows)] == ["a", "z"]


def test_dry_run_makes_zero_calls(monkeypatch, tmp_path, capsys):
    rows = tmp_path / "r.jsonl"
    rows.write_text("\n".join(json.dumps(_row(i)) for i in "ab") + "\n")
    g = tmp_path / "g.json"
    g.write_text("{}")
    monkeypatch.setattr(rjr, "_real_judge", lambda: pytest.fail("model must not be built"))
    assert rjr.main(["--rows", str(rows), "--grades", str(g), "--dry-run"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["max_calls"] == 4 and info["worst_case_reservation_usd"] == 0.12
    assert rjr.main(["--rows", str(rows), "--grades", str(g)]) == 2  # paid run needs the flag


def test_summary_arithmetic_with_indeterminate_and_twins():
    picks = {
        # id: (v1 pick, v2 pick)
        "a": (0, 0),
        "b": (0, None),
        "c": (0, None),
        "d": (None, None),
        "e": (0, 0),
        "f": (rjr.INDETERMINATE, 0),
    }
    calls = []

    async def judge(q, t, rub):
        calls.append(rub)
        pick = picks[row_id[0]][0 if rub == "v1" else 1]
        return pick, 3 if pick == 0 else 1

    row_id = [""]
    rows = [_row(i) for i in "abcdef"]

    async def run():
        # set the id the stub reads before each row (rows are processed in order)
        async def wrapped(q, t, rub):
            return await judge(q, t, rub)

        orig = rjr.grader_label

        def spy(g, i):
            row_id[0] = i
            return orig(g, i)

        rjr.grader_label = spy
        try:
            return await rjr.run_replay(rows, GRADES, [], {}, ["v1", "v2"], wrapped)
        finally:
            rjr.grader_label = orig

    out = asyncio.run(run())
    v1, v2 = out["summary"]["v1"], out["summary"]["v2"]
    # grader labels: a,b,f showable; c,d rejected; e mixed
    assert (
        v1["recall_of_showable"] == 1.0 and v1["showable_rows_total_decided"] == 2
    )  # f indeterminate
    assert v1["indeterminate_rows"] == 1 and v1["mixed_rows_excluded"] == 1
    assert v1["reject_rate_of_grader_rejected"] == 0.5 and v1["precision_of_kept"] == 0.6667
    assert v2["recall_of_showable"] == 0.6667 and v2["reject_rate_of_grader_rejected"] == 1.0
    assert v2["precision_of_kept"] == 1.0
    assert calls.count("v1") == calls.count("v2") == 6


def test_negatives_abstain_rate_and_identical_twins():
    texts = {"h1": "same clip"}
    negs = [{"control_id": f"n{i}", "question": "q", "clip_sha256_12": "h1"} for i in range(3)]
    seq = iter([None, 0, rjr.INDETERMINATE])

    async def judge(q, t, rub):
        return next(seq), None

    out = asyncio.run(rjr.run_replay([], {}, negs, texts, ["v1"], judge))
    s = out["summary"]["v1"]
    assert s["negatives_abstain_rate"] == 0.5 and s["negatives_indeterminate"] == 1
    with pytest.raises(KeyError):
        asyncio.run(rjr.run_replay([], {}, negs, {}, ["v1"], judge))


def test_both_copies_identical():
    from pathlib import Path

    here = Path(__file__).resolve().parents[1]
    a = here / "scripts" / "ops" / "run_judge_replay.py"
    b = here.parent / "scripts" / "ops" / "run_judge_replay.py"
    if not b.exists():
        pytest.skip("repo-root copy not visible (in-image run)")
    assert a.read_bytes() == b.read_bytes()
