"""The FAQ warmer runs inside the server process and never changes live timeouts."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

from app.config import settings


def test_importing_the_warmer_does_not_change_live_timeouts():
    before = (settings.llm_timeout, settings.pipeline_timeout)
    import scripts.warm_cache as wc

    importlib.reload(wc)
    assert (settings.llm_timeout, settings.pipeline_timeout) == before


def test_run_in_process_writes_the_completion_marker(tmp_path, monkeypatch):
    import scripts.warm_cache as wc

    async def fake_main():
        wc.logger.info("Cache warming complete! Success: 0/0, Failed: 0/0")

    monkeypatch.setattr(wc, "main", fake_main)
    log = tmp_path / "warm_cache.log"
    asyncio.run(wc.run_in_process(log))
    assert "Cache warming complete" in log.read_text()


def test_entrypoint_starts_no_second_warmer_process():
    text = (Path(__file__).resolve().parents[1] / "docker-entrypoint.sh").read_text()
    assert "python -m scripts.warm_cache" not in text
    assert "WARM_CACHE_ON_START=true" in text


def test_default_is_off_so_tests_and_tools_never_warm():
    assert settings.warm_cache_on_start is False
