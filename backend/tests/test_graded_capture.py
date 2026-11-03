"""Evidence rules of the graded capture runner (plan item F4, 2026-10-31)."""

from __future__ import annotations

import pytest

from scripts.ops.graded_capture import (
    build_row,
    cache_proof,
    refuse_if_evidence_exists,
    stamp_row,
    validity,
)


def test_a_cache_proof_that_says_cached_or_unreachable_blocks_the_run():
    assert cache_proof(0, "caches empty").ok
    assert not cache_proof(1, "2 exact-cache keys present").ok
    # exit 2 is "unreachable": unknown is not empty, so it must not pass
    assert not cache_proof(2, "redis unreachable").ok
    assert cache_proof(0, "").ok is True  # exit 0 is the prover's contract; output may be empty


def test_a_run_id_with_a_log_is_never_overwritten(tmp_path):
    run = tmp_path / "run1"
    run.mkdir()
    refuse_if_evidence_exists(run)  # empty directory is fine
    (run / "backend.log").write_text("evidence")
    with pytest.raises(FileExistsError):
        refuse_if_evidence_exists(run)


def test_existing_rows_or_manifest_also_block_a_rerun(tmp_path):
    for name in ("rows.jsonl", "manifest.json"):
        run = tmp_path / name.split(".")[0]
        run.mkdir()
        (run / name).write_text("{}")
        with pytest.raises(FileExistsError):
            refuse_if_evidence_exists(run)


def test_rows_are_stamped_with_commit_container_and_run():
    row = stamp_row({"id": "q1"}, sha="abc123", container_id="c0ffee", run_id="r1")
    assert (row["sha"], row["container_id"], row["run_id"]) == ("abc123", "c0ffee", "r1")


def test_row_keeps_server_latency_next_to_wall_clock():
    result = {
        "response": "A clip.",
        "route_decision": "first_person_bridge",
        "model_used": None,
        "latency_ms": 5321,
        "citations": [{"text_snippet": "A clip.", "speaker": "Sri Krishnaji", "url": "u"}],
        "safety_notices": ["n"],
    }
    row = build_row({"id": "q1", "question": "q"}, result, 202, 6.2)
    assert row["latency_ms"] == 5321 and row["sec"] == 6.2
    assert row["citations"][0]["speaker"] == "Sri Krishnaji"
    assert row["notices"] == ["n"]


def test_a_run_whose_log_shows_a_blocked_llm_is_invalid():
    bad = "Answerability check indeterminate (timeout/error): OpenRouter spend limit reached"
    verdict = validity(bad, (1.0, 2.0), (3.0, 4.0), preflight_ok=True)
    assert verdict["valid"] is False and verdict["reasons"]
    assert verdict["spend_after"] == {"day": 3.0, "month": 4.0}


def test_a_clean_log_and_a_passing_preflight_make_a_valid_run():
    assert validity("all good\n", (1.0, 2.0), (1.5, 2.5), preflight_ok=True)["valid"] is True
    assert validity("all good\n", (1.0, 2.0), (1.5, 2.5), preflight_ok=False)["valid"] is False


def test_the_frozen_116_are_labelled_a_tuning_set():
    from scripts.ops.graded_capture import _items

    items = _items(include_frozen=True, include_unanswerable=False)
    assert items and all(i["split"] == "tuning" for i in items)


def test_the_approved_bar_file_is_consistent():
    import json
    from pathlib import Path

    bar = json.loads(
        (
            Path(__file__).resolve().parents[2] / "evals/first_person/grading_pass_bar.json"
        ).read_text()
    )
    assert bar["approved"] is True and bar["approved_by"] == "Harsha"
    assert bar["min_showable_rate"] == 0.85 and bar["max_harmful"] == 0
    assert bar["p95_latency_s"] == 10
