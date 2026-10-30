"""Slice D — second-quote gating: blocklist, same-video, answerability-NO.

The optional second quote must never widen serving past the integrity and
answerability contracts:

1. Blocklisted runner-up: quarantine wins — one citation, no "Recording 2".
   Uses a REAL blocklist file on disk (exercises the file-loading path, not
   a patched ``_quality_blocklist``).
2. Same-video runner-up: a second span from the SAME recording is not a
   separate recording — one citation, no "Recording 2".
3. Answerability-NO with two eligible clips: firm NO abstains with zero
   citations and SKIPS the relevance scorer (early-verdict path), labelled
   ``no`` (not ``indeterminate``).

Non-tautology notes: each test asserts the served SHAPE (citation count,
video identity, label absence, scorer call counts) produced by the real
pipeline ``execute`` with a three-kind stub LLM (answerability verdict /
relevance scores / rerank identity told apart by system prompt).
"""

from __future__ import annotations

import hashlib
import json
import re
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _ANSWERABILITY_SYSTEM_PROMPT,
    FirstPersonPipeline,
)

pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]

_GOOD_A = (
    "Suffering arises from resistance to what is. The moment you stop resisting, something "
    "shifts within you and you recognise the truth of this very moment of your life."
)
_GOOD_B = (
    "Stillness is not the absence of thought, it is the awareness in which thoughts arise and "
    "dissolve, and when you rest there, peace is already here with you always."
)


def _clip(text, vid, point_id=None, dense=(1.0, 0.0)):
    return {
        "point_id": point_id or vid,
        "video_id": vid,
        "start_ms": 65000,
        "end_ms": 85000,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "verbatim_text": text,
        "passage_dense": list(dense),
        "source_url": f"https://youtube.com/watch?v={vid}",
        "caption_status": "auto_transcript",
    }


class _ThreeKindLLM:
    """Answerability verdict / relevance scores / rerank identity by prompt."""

    def __init__(self, verdict="YES", scores="3,3"):
        self.verdict = verdict
        self.scores = scores
        self.relevance_calls = 0
        self.answerability_calls = 0

    async def generate(self, system_prompt="", user_prompt="", **kw):
        if system_prompt == _ANSWERABILITY_SYSTEM_PROMPT:
            self.answerability_calls += 1
            return self.verdict
        if "ANSWER a seeker's question" in system_prompt:
            self.relevance_calls += 1
            # When the JSON schema path is active, wrap CSV scores as JSON.
            if kw.get("response_format"):
                try:
                    scores = [int(t) for t in self.scores.replace(" ", "").split(",") if t]
                except ValueError:
                    scores = []
                import json

                return json.dumps({"scores": scores})
            return self.scores
        if "rank the clips" in system_prompt:
            n = len(re.findall(r"\[\d+\]", user_prompt or ""))
            return ",".join(str(i) for i in range(1, max(n, 1) + 1))
        return self.verdict


def _run(clips, llm, monkeypatch, tmp_path=None, block_ids=None):
    monkeypatch.setattr(settings, "first_person_second_quote_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_min_score", 3)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(
        "services.first_person_pipeline.is_youtube_video_available", lambda _v: True
    )
    # Hermetic: a local .env that enables the speculative cascade scores only
    # candidate #1 first, which changes how many scores the stub LLM must return.
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False, raising=False)
    if block_ids is not None:
        bf = tmp_path / "block.json"
        bf.write_text(json.dumps(sorted(block_ids)), encoding="utf-8")
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", str(bf))
    else:
        monkeypatch.setattr(settings, "first_person_quality_blocklist_path", "")
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = clips
    redis = MagicMock()
    redis.get.return_value = None
    pipeline = FirstPersonPipeline(
        store=store, redis_client=redis, calibration_profile=None, llm_service=llm
    )
    return pipeline.execute(query="What is stillness?", query_dense_vector=[1.0, 0.0])


def test_second_quote_blocklisted_runner_up_serves_one_citation(monkeypatch, tmp_path):
    """Quarantined runner-up is never served as Recording 2; the winner stays."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    # Blocklist runs BEFORE relevance scoring, so the scorer sees one clip.
    llm = _ThreeKindLLM(verdict="YES", scores="3")
    res = _run(
        [_clip(_GOOD_A, "vidA"), _clip(_GOOD_B, "vidB")],
        llm,
        monkeypatch,
        tmp_path,
        block_ids=["vidB"],
    )
    assert [c["video_id"] for c in res.citations] == ["vidA"]
    assert "Recording 2" not in res.answer_text
    assert _GOOD_B not in res.answer_text


def test_second_quote_same_video_span_is_not_a_second_recording(monkeypatch, tmp_path):
    """Two qualifying spans from ONE video serve a single citation."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)
    llm = _ThreeKindLLM(verdict="YES", scores="3,3")
    clips = [
        _clip(_GOOD_A, "vidA", point_id="vidA-seg1"),
        _clip(_GOOD_B, "vidA", point_id="vidA-seg2", dense=(0.9, 0.1)),
    ]
    res = _run(clips, llm, monkeypatch, tmp_path)
    assert len(res.citations) == 1
    assert "Recording 2" not in res.answer_text


def test_second_quote_answerability_no_abstains_with_zero_citations(monkeypatch, tmp_path):
    """Firm NO skips the scorer and serves nothing — no second quote leaks."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    llm = _ThreeKindLLM(verdict="NO", scores="3,3")
    res = _run([_clip(_GOOD_A, "vidA"), _clip(_GOOD_B, "vidB")], llm, monkeypatch, tmp_path)
    assert res.status == "abstained"
    assert res.citations == []
    assert res.answerability == "no"
    assert res.abstain_reason == "answerability_withheld"
    assert llm.relevance_calls == 0, "firm NO must skip rerank/scorer"
    assert "Recording" not in res.answer_text


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
