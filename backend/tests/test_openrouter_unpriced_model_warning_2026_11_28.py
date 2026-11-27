"""Fallback cost table: unknown model ids warn once (still $0); refreshed rows (2026-11-28)."""

import logging

import pytest

from services import openrouter_service as svc
from services.openrouter_service import OpenRouterService


def test_unknown_model_is_priced_at_zero_and_warns_once(caplog):
    svc._UNPRICED_MODELS_WARNED.discard("vendor/unlisted-model")
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        first = OpenRouterService._fallback_cost(1_000, 1_000, "vendor/unlisted-model")
        second = OpenRouterService._fallback_cost(5_000, 5_000, "vendor/unlisted-model")
    assert first == 0.0 and second == 0.0
    hits = [r for r in caplog.records if "vendor/unlisted-model" in r.getMessage()]
    assert len(hits) == 1 and hits[0].levelno == logging.WARNING


def test_known_model_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING, logger=svc.logger.name):
        cost = OpenRouterService._fallback_cost(
            1_000_000, 1_000_000, "meta-llama/llama-3.3-70b-instruct"
        )
    assert cost == pytest.approx(0.59 + 0.79)
    assert not [r for r in caplog.records if "no entry" in r.getMessage()]


@pytest.mark.parametrize(
    ("model", "rates"),
    [
        ("deepseek/deepseek-chat", (0.2574, 1.0287)),
        ("meta-llama/llama-3.3-70b-instruct", (0.59, 0.79)),
        ("meta-llama/llama-3.1-8b-instruct", (0.05, 0.08)),
    ],
)
def test_rows_refreshed_2026_11_27(model, rates):
    assert svc._OPENROUTER_FALLBACK_RATES_PER_MILLION[model] == rates


def test_delisted_sarvam_row_kept_for_the_preset():
    assert "sarvamai/sarvam-m" in svc._OPENROUTER_FALLBACK_RATES_PER_MILLION
