"""NEW-RW-8 (RW-06): boot-time measurement log.

Runbook risk R-5: with no Memgraph the boot can wait up to 120 s for LightRAG and
180 s for background init, against a 330 s deploy healthcheck. Nothing measured it.
`BootTimer` records each phase and logs one `Boot timing:` line, so the first
staging deploy produces the number that decides whether a LightRAG skip flag is
needed. No such flag is added until that number exists.
"""

from __future__ import annotations

import logging

from app.boot_timing import BootTimer, worst_case_boot_seconds


def test_phases_are_recorded_in_order_with_outcome():
    clock = iter([0.0, 0.0, 2.0, 2.0, 9.5, 12.0])
    timer = BootTimer(now=lambda: next(clock))
    timer.start()
    with timer.phase("startup_checks"):
        pass
    with timer.phase("lightrag_init", budget_s=120):
        pass
    timer.record("background_init", 2.5, outcome="ok", budget_s=180)
    line = timer.summary(accepting=True)
    assert line.startswith("Boot timing:")
    assert "startup_checks=2.0s" in line
    assert "lightrag_init=7.5s/120s" in line
    assert "background_init=2.5s/180s" in line
    assert "total=" in line


def test_timeout_and_failure_outcomes_are_visible():
    timer = BootTimer(now=lambda: 0.0)
    timer.start()
    timer.record("lightrag_init", 120.0, outcome="timeout", budget_s=120)
    timer.record("background_init", 3.0, outcome="failed", budget_s=180)
    line = timer.summary(accepting=True)
    assert "lightrag_init=120.0s/120s(timeout)" in line
    assert "background_init=3.0s/180s(failed)" in line


def test_phase_context_marks_exceptions_as_failed():
    clock = iter([0.0, 1.0, 4.0, 4.0])
    timer = BootTimer(now=lambda: next(clock))
    timer.start()
    try:
        with timer.phase("lightrag_init", budget_s=120):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert "lightrag_init=3.0s/120s(failed)" in timer.summary(accepting=False)


def test_worst_case_boot_uses_the_two_timeouts():
    assert worst_case_boot_seconds(lightrag_timeout_s=120, background_timeout_s=180) == 300


def test_log_warns_when_total_exceeds_the_healthcheck_budget(caplog):
    timer = BootTimer(now=lambda: 0.0)
    timer.start()
    timer.record("lightrag_init", 120.0, outcome="timeout", budget_s=120)
    timer.record("background_init", 180.0, outcome="timeout", budget_s=180)
    with caplog.at_level(logging.INFO):
        timer.log(logging.getLogger("boot-test"), healthcheck_timeout_s=330, margin_s=60)
    assert any("Boot timing:" in r.getMessage() for r in caplog.records)
    # 300 s of phases leaves 30 s of the 330 s budget, under the 60 s margin asked for.
    assert any(r.levelno == logging.WARNING and "margin" in r.getMessage() for r in caplog.records)


def test_main_lifespan_uses_the_timer():
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    assert "BootTimer" in src
    assert 'timer.phase("lightrag_init"' in src
    assert 'timer.phase("background_init"' in src


def test_mark_last_relabels_the_previous_phase():
    timer = BootTimer(now=lambda: 0.0)
    timer.start()
    timer.record("lightrag_init", 120.0, outcome="failed", budget_s=120)
    timer.mark_last("timeout")
    assert "lightrag_init=120.0s/120s(timeout)" in timer.summary(accepting=True)
