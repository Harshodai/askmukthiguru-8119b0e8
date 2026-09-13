"""B2/B3 hallucination-gate guard (Task 8): zero rows must hard-fail and the
workflow must not swallow failures with `continue-on-error`.

Root cause: `run_anomaly_check` returned `anomaly=False` on an empty window
while the workflow also set `continue-on-error: true` on the detector step, so
both "no traffic" and "detector crashed" reported the same green as "healthy".
Per the burn-rate practice, an empty observation window is indeterminate --
never a pass -- and the gate must fail closed.
"""

import pathlib

import scripts.ops.hallucination_anomaly as ha

_WORKFLOW = (
    pathlib.Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "hallucination-anomaly.yml"
)


def test_zero_rows_is_hard_fail(monkeypatch):
    monkeypatch.setattr(ha, "_fetch_responses", lambda since, until=None: [])
    result = ha.run_anomaly_check(lookback_days=1)
    assert result["metrics"]["total_responses"] == 0
    assert result["anomaly"] is True, "empty window must not read as healthy"
    assert result["alerts"].get("no_data") is True


def test_connection_error_still_fails_closed(monkeypatch):
    monkeypatch.setattr(ha, "_fetch_responses", lambda since, until=None: None)
    result = ha.run_anomaly_check(lookback_days=1)
    assert result["anomaly"] is True
    assert result["alerts"].get("connection_error") is True


def test_workflow_has_no_continue_on_error():
    src = _WORKFLOW.read_text()
    assert "continue-on-error" not in src, "detector step must fail the workflow"


def test_workflow_gate_fails_on_zero_rows():
    src = _WORKFLOW.read_text()
    assert "no_data" in src, "gate must explicitly handle the empty-window case"
