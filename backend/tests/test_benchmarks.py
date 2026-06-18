from benchmarks.question_bank import QUERIES
from benchmarks.ruthless_benchmark import InfraResult, SingleResult, calculate_scores


def test_question_bank_contains_production_eval_categories():
    assert sum(len(items) for items in QUERIES.values()) >= 300
    for category in ["multi_turn", "cache", "self_rag", "cove", "citation_accuracy"]:
        assert category in QUERIES
        assert QUERIES[category]


def test_calculate_scores_includes_eval_dimensions():
    results = [
        SingleResult(
            category="citation_accuracy",
            query="book",
            latency_ms=100,
            status=200,
            intent="FACTUAL",
            citations=["https://www.amazon.in/Four-Sacred-Secrets-Prosperity-Beautiful/dp/1846046319"],
            response="amazon.in",
            keyword_score=1.0,
            passed=True,
            verification_passed=True,
            faithfulness=0.95,
        ),
        SingleResult(
            category="multi_turn:Sacred_Secrets_Journey",
            query="Which one?",
            latency_ms=100,
            status=200,
            intent="FOLLOW_UP",
            citations=["source"],
            response="third universal intelligence",
            keyword_score=1.0,
            passed=True,
            verification_passed=True,
            faithfulness=0.9,
        ),
        SingleResult(
            category="self_rag",
            query="fake fifth secret",
            latency_ms=100,
            status=200,
            intent="FACTUAL",
            citations=["source"],
            response="there is no fifth sacred secret",
            keyword_score=1.0,
            passed=True,
            verification_passed=True,
            faithfulness=0.9,
        ),
    ]
    infra = [InfraResult("FastAPI Backend", True, 1.0, 200)]

    scores = calculate_scores(results, infra)

    assert scores["citations"].score == 1.0
    assert scores["multi_turn"].score == 1.0
    assert scores["faithfulness"].score == 1.0
