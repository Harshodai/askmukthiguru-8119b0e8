"""NEW-OPS-8 / NEW-LOAD-4 / NEW-LOAD-5 / NEW-AI-3: one budget table, one capacity line.

The three scorer timeouts and the provider RPM limit used to live in four places
(config.py, two compose files, one constant in the pipeline). `llm_budget_table`
reads each from its single source and the compose files must not override the
Settings default with another value (D-PG13 decided 2026-11-07: the default stays 25 s; only the graded run pins 12 s).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.runtime_budget import capacity_snapshot, llm_budget_table, log_runtime_budget

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent


def _rows(settings=None):
    return {row["name"]: row for row in llm_budget_table(settings or Settings())}


def test_table_has_the_three_scorer_timeouts_and_the_rpm_limit():
    rows = _rows()
    for name in (
        "relevance_scorer_timeout_s",
        "answerability_gate_timeout_s",
        "jev_timeout_s",
        "openrouter_rpm_limit",
    ):
        assert name in rows, sorted(rows)
        assert rows[name]["value"] > 0
        assert rows[name]["source"]


def test_relevance_timeout_comes_from_settings():
    s = Settings(first_person_relevance_timeout_s=17.5)
    assert _rows(s)["relevance_scorer_timeout_s"]["value"] == 17.5


def test_jev_timeout_falls_back_to_the_intent_router_value():
    s = SimpleNamespace(
        first_person_relevance_timeout_s=25.0,
        jev_timeout_s=None,
        intent_router_jev_timeout_s=2.0,
        openrouter_rpm_limit=60,
        openrouter_daily_budget_usd=10.0,
        openrouter_max_request_cost_usd=0.03,
    )
    assert _rows(s)["jev_timeout_s"]["value"] == 2.0
    s.jev_timeout_s = 4.0
    assert _rows(s)["jev_timeout_s"]["value"] == 4.0


def test_daily_cap_headroom_row_states_the_sys014_number():
    rows = _rows(Settings())
    assert rows["daily_cap_full_path_requests"]["value"] == 111
    assert "SYS-014" in rows["daily_cap_full_path_requests"]["source"]


def test_compose_files_do_not_override_the_settings_default():
    """One value, one source (NEW-AI-3).

    D-PG13 (Harsha, 2026-11-07): the graded override is a stage pin, not a
    default. It is pinned at 12 s by tests/test_graded_run_preflight.py, so it is
    not checked here.
    """
    default = Settings.model_fields["first_person_relevance_timeout_s"].default
    for path in (
        BACKEND / "docker-compose.yml",
        BACKEND / "docker-compose.dev.yml",
        REPO_ROOT / "docker-compose.prod.yml",
    ):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = re.search(
                r"FIRST_PERSON_RELEVANCE_TIMEOUT_S\s*[:=]\s*[\"']?\$?\{?[^\d\"']*?([\d.]+)", line
            )
            if m:
                assert float(m.group(1)) == default, (path.name, line.strip(), default)


def test_capacity_snapshot_reports_cpu_executor_and_chat_cap(monkeypatch):
    monkeypatch.setattr("os.cpu_count", lambda: 8)
    snap = capacity_snapshot(SimpleNamespace(embed_thread_workers=0, max_concurrent_chat=12))
    assert snap["cpu_count"] == 8
    assert snap["default_executor_workers"] == min(32, 8 + 4)
    assert snap["embed_executor_workers"] == min(2, 8 // 2 or 1)
    assert snap["max_concurrent_chat"] == 12


def test_capacity_snapshot_honours_embed_thread_workers(monkeypatch):
    monkeypatch.setattr("os.cpu_count", lambda: None)
    snap = capacity_snapshot(SimpleNamespace(embed_thread_workers=3, max_concurrent_chat=5))
    assert snap["cpu_count"] == 1
    assert snap["embed_executor_workers"] == 3


def test_startup_log_lines(caplog):
    with caplog.at_level(logging.INFO, logger="rb-test"):
        log_runtime_budget(logging.getLogger("rb-test"), Settings())
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "LLM budget table:" in text
    assert "relevance_scorer_timeout_s=" in text
    assert "Capacity:" in text
    assert "cpu_count=" in text and "max_concurrent_chat=" in text


def test_main_lifespan_logs_the_budget_table():
    src = (BACKEND / "app" / "main.py").read_text()
    assert "log_runtime_budget(" in src
