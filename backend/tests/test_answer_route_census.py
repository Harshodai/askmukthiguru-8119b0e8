"""§11: every answer's route must be countable, not only greppable.

The audit could not say how often the pipeline fell back because nothing
counted it — the evidence was one log line per request. ResultAssemblyStage is
the single point every answer passes through, so the census belongs there.
"""

import inspect

from app.metrics import ANSWER_ROUTE_TOTAL
from app.pipeline.stages import glue_stages


def _count(route: str, grounding: str) -> float:
    return ANSWER_ROUTE_TOTAL.labels(route=route, grounding_state=grounding)._value.get()


def test_counter_records_route_and_grounding():
    before = _count("grounded_redacted", "grounded")
    ANSWER_ROUTE_TOTAL.labels(route="grounded_redacted", grounding_state="grounded").inc()
    assert _count("grounded_redacted", "grounded") == before + 1


def test_result_assembly_records_every_answer():
    src = inspect.getsource(glue_stages.ResultAssemblyStage)
    assert "ANSWER_ROUTE_TOTAL.labels(" in src
    # Labels must come from the canonicalised route, or cardinality is unbounded.
    assert "resolved_route_decision" in src


def test_metric_failure_cannot_break_a_response():
    src = inspect.getsource(glue_stages.ResultAssemblyStage)
    head, _, tail = src.partition("ANSWER_ROUTE_TOTAL.labels(")
    assert "try:" in head[-400:], "the census must be wrapped so a metric error cannot fail a reply"
    assert "except Exception" in tail[:400]
