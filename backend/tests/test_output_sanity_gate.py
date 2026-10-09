"""L-OUTPUT-SANITY-1: garbage / outage text is never a passing answer."""

import pytest

from app.constants import PROVIDER_UNAVAILABLE_ANSWER, is_graceful_degradation
from services.text_quality_filter import output_sanity_failure


def test_exclamation_garbage_rejected():
    assert output_sanity_failure("!" * 136) == "too_short"


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_rejected(text):
    assert output_sanity_failure(text) == "empty"


def test_provider_outage_text_rejected():
    msg = (
        "I'm here and listening. However, I'm experiencing a temporary connection issue "
        "with my backend services. Please try again shortly."
    )
    assert output_sanity_failure(msg) == "provider_degraded"


def test_symbol_noise_rejected():
    assert output_sanity_failure("?! ?! ?! ?! ?! ?! ?! ?! ?! a b c d e f g") is not None


def test_real_answer_passes():
    ans = "The Beautiful State is a state of connection, calm and joy that you can return to [Source: Ekam]."
    assert output_sanity_failure(ans) is None


def test_short_casual_ok_when_min_zero():
    assert output_sanity_failure("Namaste 🙏", min_alnum=0) is None


def test_hindi_answer_passes():
    assert output_sanity_failure("सुंदर अवस्था शांति, आनंद और जुड़ाव की अवस्था है।") is None


def test_replacement_text_is_still_recognised_as_degraded_by_cache_guard():
    assert is_graceful_degradation(PROVIDER_UNAVAILABLE_ANSWER)
