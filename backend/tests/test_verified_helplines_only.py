"""T4-07 / SAFE-004: Verified helplines only.

Ensures user-facing crisis and distress templates display only entries whose
`last_verified_by_call` is within the configured freshness window, plus the
national emergency service (112) which is verified by official listing and must
never be test-called. Tele-MANAS is preserved as the verified national mental
health line.
"""

from __future__ import annotations

from datetime import date, timedelta

from rag.meditation import get_distress_response
from services import crisis_helplines
from services.crisis_helplines import (
    Helpline,
    _is_call_verified_and_fresh,
    _only_call_verified,
    format_helplines_block,
    format_support_line,
)


def _fresh():
    crisis_helplines.get_helplines.cache_clear()
    return crisis_helplines.get_helplines()


def test_verified_only_filters_unverified_entries():
    """Unverified entries (missing last_verified_by_call) are excluded from verified_only block."""
    _fresh()
    block = format_helplines_block(style="bullet", intro="", verified_only=True)
    lines = block.splitlines()

    # Tele-MANAS and 112 must appear
    assert any("Tele-MANAS" in line for line in lines)
    assert any(line.rstrip().endswith("112") or ": 112" in line for line in lines)

    # Unverified lines must not appear
    for unverified_name in ("iCall", "AASRA", "Sneha", "Vandrevala", "Crisis Text Line"):
        assert not any(unverified_name in line for line in lines), (
            f"Unverified helpline {unverified_name} was displayed in verified_only block"
        )


def test_freshness_window_filters_stale_verifications():
    """An entry with last_verified_by_call older than max_age_days is excluded."""
    today = date.today()
    fresh_date = (today - timedelta(days=30)).isoformat()
    stale_date = (today - timedelta(days=250)).isoformat()

    fresh_line = Helpline(
        region="India",
        name="Fresh Line",
        contact="12345",
        last_verified_by_call=fresh_date,
    )
    stale_line = Helpline(
        region="India",
        name="Stale Line",
        contact="67890",
        last_verified_by_call=stale_date,
    )

    assert _is_call_verified_and_fresh(fresh_line, max_age_days=180) is True
    assert _is_call_verified_and_fresh(stale_line, max_age_days=180) is False

    filtered = _only_call_verified((fresh_line, stale_line), max_age_days=180)
    assert len(filtered) == 1
    assert filtered[0].name == "Fresh Line"


def test_national_line_112_never_requires_test_call():
    """112 is officially listed and must never be test-called; verified by definition."""
    emergency = Helpline(
        region="India",
        name="National Emergency Services",
        contact="112",
        last_verified_by_call=None,
    )
    assert _is_call_verified_and_fresh(emergency, max_age_days=30) is True


def test_tele_manas_fallback_when_all_expire():
    """If all entries expire, Tele-MANAS and 112 are preserved as the minimum fallback."""
    today = date.today()
    stale_date = (today - timedelta(days=400)).isoformat()

    stale_tele_manas = Helpline(
        region="India",
        name="Tele-MANAS",
        contact="14416",
        last_verified_by_call=stale_date,
    )
    stale_other = Helpline(
        region="India",
        name="Other Helpline",
        contact="99999",
        last_verified_by_call=stale_date,
    )

    filtered = _only_call_verified((stale_tele_manas, stale_other), max_age_days=180)
    assert any("Tele-MANAS" in h.name for h in filtered)
    assert not any("Other Helpline" in h.name for h in filtered)


def test_meditation_distress_response_renders_only_verified_lines():
    """get_distress_response() in rag/meditation renders only call-verified lines (SAFE-004)."""
    _fresh()
    response = get_distress_response()
    assert "Tele-MANAS" in response
    # Unverified numbers must not appear in the initial distress response
    assert "9152987821" not in response  # iCall
    assert "022 2754 6669" not in response  # AASRA
    assert "044-24640050" not in response  # Sneha


def test_format_support_line_excludes_unverified_contacts():
    """format_support_line() excludes unverified lines (such as unverified 988 or Samaritans)."""
    _fresh()
    support_line = format_support_line(verified_only=True)
    assert "Tele-MANAS" in support_line
    assert "14416" in support_line
    assert "112" in support_line
    # 988 and Samaritans are unverified in helplines.yaml
    assert "Samaritans" not in support_line
