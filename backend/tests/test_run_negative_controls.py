"""Negative-control runner: arithmetic, dry-run spends nothing, output never carries clip text."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.ops import run_negative_controls as rnc

TEXTS = {"aaa": "SECRET CLIP ONE", "bbb": "SECRET CLIP TWO", "ccc": "SECRET CLIP THREE"}
CONTROLS = [
    {"control_id": f"neg_{i}", "question": f"q{i}", "clip_sha256_12": h}
    for i, h in enumerate(["aaa", "bbb", "ccc", "aaa"])
]


def _run(judge, cmp_=None):
    return asyncio.run(rnc.run_pairs(CONTROLS, TEXTS, judge, cmp_))


def test_abstain_rate_arithmetic():
    picks = iter([None, 0, None, -1])

    async def judge(q, t):
        return next(picks)

    out = _run(judge)
    assert out["counts"] == {"abstain": 2, "serve": 1, "indeterminate": 1}
    assert out["abstain_rate"] == 0.5 and out["n"] == 4


def test_comparative_only_called_on_judge_serve_and_can_abstain():
    called = []

    async def judge(q, t):
        return 0

    async def cmp_(q, t):
        called.append(q)
        return None if q in ("q0", "q1") else 0

    out = _run(judge, cmp_)
    assert called == ["q0", "q1", "q2", "q3"]
    assert out["counts"]["abstain"] == 2 and out["counts"]["serve"] == 2


def test_output_has_ids_and_hashes_but_no_clip_text():
    async def judge(q, t):
        return None

    blob = json.dumps(_run(judge))
    assert "SECRET" not in blob and "neg_0" in blob and "aaa" in blob


def test_missing_clip_text_raises():
    async def judge(q, t):
        return None

    with pytest.raises(KeyError):
        asyncio.run(
            rnc.run_pairs(
                [{"control_id": "x", "question": "q", "clip_sha256_12": "zzz"}], TEXTS, judge
            )
        )


def test_dry_run_makes_no_calls(monkeypatch, capsys):
    monkeypatch.setattr(rnc, "_real_deciders", lambda c: pytest.fail("model path touched"))
    assert rnc.main(["--dry-run", "--comparative", "--limit", "10"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["pairs"] == 10 and info["max_calls"] == 20
    assert info["worst_case_reservation_usd"] == round(20 * 0.03, 4)


def test_refuses_without_spend_flag(monkeypatch):
    monkeypatch.setattr(rnc, "_real_deciders", lambda c: pytest.fail("model path touched"))
    assert rnc.main(["--limit", "1"]) == 2


def test_clip_text_resolution_hashes_like_the_builder(tmp_path):
    import hashlib

    text = "a clip"
    h = hashlib.sha256(text.encode()).hexdigest()[:12]
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        json.dumps({"set": "frozen116", "id": "q1", "citations": [{"text": text}]})
        + "\n"
        + json.dumps({"set": "other", "citations": [{"text": "x"}]})
        + "\n"
    )
    assert rnc.clip_texts_by_hash(rows) == {h: text}
