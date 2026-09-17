"""Proves the unified eval harness (evaluation/bench.py) can actually FAIL.

Direct response to the owner's requirement (docs/HANDOFF_2026-09-16.md §8.F /
§9.7): this repo has shipped three benchmark artifacts that scored their own
reference and reported a perfect score. A harness that cannot go red is
decoration. This test feeds `score_row`/`aggregate` a deliberately WRONG
answer for each first-class failure signal and asserts it is caught, then
feeds a correct answer through the same path to prove the checks discriminate
rather than always firing.
"""

from __future__ import annotations

from evaluation.bench import _norm, aggregate, score_row


def _item(**overrides) -> dict:
    base = _norm(
        "t-001",
        "beautiful_state",
        "golden_qa_bank",
        "What is the Beautiful State?",
        must_mention=["beautiful state", "inner"],
        reject_if=["suffering is the goal"],
        should_abstain=False,
    )
    base.update(overrides)
    return base


def test_wrong_answer_is_scored_as_wrong():
    """A deliberately wrong answer must fail must_mention coverage AND trip
    the doctrinal-contradiction check -- not silently pass."""
    item = _item()
    raw = {
        "response": "Suffering is the goal of life and nothing else matters.",
        "grounding_state": "grounded",
        "citations": [],
        "evaluation_trace": {"retrieved_count": 3},
    }
    row = score_row(
        item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
    )

    assert row.coverage == 0.0, "wrong answer must not accidentally match must_mention terms"
    assert row.contradictions == ["suffering is the goal"], "reject_if phrase must be caught"
    assert not row.refused


def test_correct_answer_scores_clean():
    """Same item, a real answer -- proves the check above discriminates
    rather than failing everything unconditionally."""
    item = _item()
    raw = {
        "response": "The Beautiful State is an inner state of calm and connection.",
        "grounding_state": "grounded",
        "citations": [{"url": "https://youtube.com/watch?v=abc"}],
        "evaluation_trace": {"retrieved_count": 4},
    }
    row = score_row(
        item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
    )

    assert row.coverage == 1.0
    assert row.contradictions == []


def test_wrongly_refusing_an_answerable_question_fails_abstention_check():
    """should_abstain=False but the pipeline refused -> abstention_correct
    must be False, not silently None or True."""
    item = _item(should_abstain=False)
    raw = {
        "response": "I don't have that specific teaching in my knowledge base.",
        "grounding_state": "abstained",
        "citations": [],
        "evaluation_trace": {"retrieved_count": 0},
    }
    row = score_row(
        item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
    )

    assert row.refused is True
    assert row.abstention_correct is False


def test_answering_an_unanswerable_question_is_correct_not_a_failure():
    """Inverse of the above, and the owner's explicit example: refusing
    'the Fifth Sacred Secret' is CORRECT, not a failure."""
    item = _item(should_abstain=True, question="Tell me about the Fifth Sacred Secret.")
    raw = {
        "response": "I don't have that specific teaching in my knowledge base.",
        "grounding_state": "abstained",
        "citations": [],
        "evaluation_trace": {"retrieved_count": 0},
    }
    row = score_row(
        item, raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
    )

    assert row.refused is True
    assert row.abstention_correct is True


def test_wedged_pipeline_reports_as_system_error_not_correct_abstention():
    """The exact 2026-09-16 08:00 incident this harness must never mistake for
    a considered refusal: circuit breaker OPEN, 11ms latency, HTTP 200."""
    item = _item()
    raw = {
        "response": "The guru is unable to answer this question right now.",
        "grounding_state": "system_error",
        "citations": [],
        "evaluation_trace": None,
    }
    row = score_row(
        item, raw, latency_s=0.011, mode="anonymous", qdrant_client=None, voice_profile=None
    )

    assert row.system_error is True
    assert row.abstention_correct is None, (
        "a broken pipeline must not score as a correct abstention"
    )


def test_aggregate_gates_go_red_on_a_bad_report():
    """End-to-end: a report built entirely from wrong answers must fail
    report.gates_passed, using the real app.config.settings thresholds."""
    item = _item()
    wrong_raw = {
        "response": "Suffering is the goal of life and nothing else matters.",
        "grounding_state": "grounded",
        "citations": [],
        "evaluation_trace": {"retrieved_count": 3},
    }
    rows = [
        score_row(
            item, wrong_raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
        )
        for _ in range(5)
    ]
    report = aggregate(rows, mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")

    assert report.contradiction_count == 5
    assert report.gates_passed is False, (
        "5/5 contradicting answers must fail the harness's own gates"
    )


def test_aggregate_gates_pass_on_a_clean_report():
    """Same path, all-correct answers -- proves gates_passed=False above is a
    real signal and not the harness defaulting to red."""
    item = _item()
    good_raw = {
        "response": "The Beautiful State is an inner state of calm and connection.",
        "grounding_state": "grounded",
        "citations": [{"url": "https://youtube.com/watch?v=abc"}],
        "evaluation_trace": {"retrieved_count": 4},
    }
    rows = [
        score_row(
            item, good_raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
        )
        for _ in range(5)
    ]
    report = aggregate(rows, mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")

    assert report.contradiction_count == 0
    assert report.gates_passed is True


def test_all_unified_sources_load_cleanly_without_collision():
    """Every question source in DEFAULT_SOURCES must load and have zero ID collisions."""
    from evaluation.bench import DEFAULT_SOURCES, SOURCE_LOADERS, load_questions

    assert len(DEFAULT_SOURCES) >= 9, "must have at least 9 unified sources"
    assert set(DEFAULT_SOURCES) == set(SOURCE_LOADERS.keys())

    items = load_questions(DEFAULT_SOURCES, sample=None)
    assert len(items) >= 1200, f"expected >=1200 unified questions, got {len(items)}"
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids)), "duplicate question ID detected across unified sources"


def test_benchmarks_run_entrypoint():
    """benchmarks.run must exist and import evaluation.bench.main."""
    from benchmarks.run import main as run_main
    from evaluation.bench import main as bench_main

    assert run_main is bench_main


def test_misattribution_and_zero_retrieval_trigger_gate_failure():
    """First-person teaching claim + zero-retrieval canary must trigger gate failures."""
    item = _item()
    bad_raw = {
        "response": "I teach that the universe is an illusion.",
        "grounding_state": "grounded",
        "citations": [{"url": "http://invalid-url"}],
        "evaluation_trace": {"retrieved_count": 0},
    }
    row = score_row(
        item, bad_raw, latency_s=1.0, mode="anonymous", qdrant_client=None, voice_profile=None
    )
    assert "first_person_teaching_claim" in row.misattribution_flags
    assert row.zero_retrieval_canary is True

    report = aggregate([row], mode="e2e:anonymous", sources=["golden_qa_bank"], started_at="t0")
    assert report.gates_passed is False
    failed_names = {g.name for g in report.gates if not g.passed}
    assert "misattribution_rate" in failed_names
    assert "zero_retrieval_rate" in failed_names


if __name__ == "__main__":
    test_wrong_answer_is_scored_as_wrong()
    test_correct_answer_scores_clean()
    test_wrongly_refusing_an_answerable_question_fails_abstention_check()
    test_answering_an_unanswerable_question_is_correct_not_a_failure()
    test_wedged_pipeline_reports_as_system_error_not_correct_abstention()
    test_aggregate_gates_go_red_on_a_bad_report()
    test_aggregate_gates_pass_on_a_clean_report()
    test_all_unified_sources_load_cleanly_without_collision()
    test_benchmarks_run_entrypoint()
    test_misattribution_and_zero_retrieval_trigger_gate_failure()
    print("bench self-check OK: harness correctly goes red on wrong answers, green on correct ones")
