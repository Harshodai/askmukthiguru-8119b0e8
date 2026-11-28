"""Capacity-test tooling: the load generator must refuse non-local targets, and the LLM stub
must hand the first-person relevance scorer the number of scores it asked for."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parents[2] / "scripts" / "ops"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, OPS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "url",
    ["https://api.askmukthiguru.com", "https://x.up.railway.app", "http://10.0.0.5:8000"],
)
def test_load_generator_refuses_non_local_targets(url):
    gen = _load("load_test_chat")
    with pytest.raises(SystemExit):
        gen.require_local(url)


def test_load_generator_accepts_loopback_and_distinct_questions():
    gen = _load("load_test_chat")
    gen.require_local("http://127.0.0.1:8100")
    assert gen.question(1, 0) != gen.question(1, 0)  # unique tail: never an exact-cache hit


def test_stub_scores_match_requested_clip_count_and_serve_threshold():
    stub = _load("load_test_llm_stub")
    user = (
        "Question: how do I forgive?\n\nClips (4 total — return exactly 4 integer score(s)):\n[1] a"
    )
    scores = stub._scores(user)
    assert len(scores) == 4 and all(0 <= s <= 3 for s in scores)
    stub.CFG["serve_ratio"] = 1.0
    assert max(stub._scores(user)) >= 2  # production min score is 2
    stub.CFG["serve_ratio"] = 0.0
    assert max(stub._scores(user)) < 2
    assert json.loads(json.dumps({"scores": scores}))["scores"] == scores


@pytest.mark.parametrize(
    "bad",
    [
        "https://evil.example/api/jobs/x",
        "//evil.example/x",
        "http://127.0.0.1/x",
        "api/jobs/x",
        None,
    ],
)
def test_poll_url_must_be_host_relative(bad):
    gen = _load("load_test_chat")
    with pytest.raises(ValueError):
        gen.safe_poll_path(bad)
    assert gen.safe_poll_path("/api/jobs/job_1") == "/api/jobs/job_1"
