"""Regression tests for the helplines.yaml migration (PLAN.md Phase A2, 2026-09-21).

Helpline data moved from backend/config/router_routes.yaml to the repo-root
config/helplines.yaml with a richer schema (hours/languages/source_url/
last_verified). These tests guard: (a) the real repo-root file actually
loads via the real loader (not a mock), (b) the unverified-data warning
fires when last_verified is unset, (c) a malformed/missing file still falls
back safely rather than crashing the safety path.
"""

from pathlib import Path

from services import crisis_helplines


def test_real_config_file_loads_with_new_schema():
    """The actual repo-root config/helplines.yaml must load, not just a fixture."""
    crisis_helplines.get_helplines.cache_clear()
    helplines = crisis_helplines.get_helplines()

    assert len(helplines) > 0
    india = [h for h in helplines if h.region == "India"]
    assert any("Tele-MANAS" in h.name for h in india)
    # New fields introduced by this migration must be reachable, not just present on the dataclass.
    tele_manas = next(h for h in india if "Tele-MANAS" in h.name)
    assert tele_manas.hours is not None
    assert tele_manas.source_url is not None


def test_real_config_file_reports_unverified(caplog):
    """Every entry currently ships with last_verified unset — the loader must
    say so loudly rather than silently treating agent-populated data as launch-ready."""
    crisis_helplines.get_helplines.cache_clear()
    with caplog.at_level("WARNING"):
        helplines = crisis_helplines.get_helplines()

    assert not any(h.last_verified for h in helplines)
    assert any("unverified" in record.message.lower() for record in caplog.records)


def test_domestic_violence_helplines_also_load_from_new_file():
    crisis_helplines.get_domestic_violence_helplines.cache_clear()
    dv = crisis_helplines.get_domestic_violence_helplines()

    assert len(dv) > 0
    assert any("Domestic Violence" in h.name or "Women Helpline" in h.name for h in dv)


def test_missing_config_falls_back_safely(monkeypatch):
    """The safety path must never depend on the YAML file being present."""
    monkeypatch.setattr(
        crisis_helplines, "_resolve_config_path", lambda: Path("/nonexistent/helplines.yaml")
    )
    crisis_helplines.get_helplines.cache_clear()
    try:
        helplines = crisis_helplines.get_helplines()
        assert helplines == crisis_helplines._FALLBACK_HELPLINES
    finally:
        crisis_helplines.get_helplines.cache_clear()


def test_parse_helpline_entry_handles_missing_optional_fields():
    """A minimal entry (region/name/contact only, matching the old schema) must still parse."""
    entry = {"region": "India", "name": "Test Line", "contact": "123"}
    helpline = crisis_helplines._parse_helpline_entry(entry)

    assert helpline.region == "India"
    assert helpline.hours is None
    assert helpline.languages is None
    assert helpline.last_verified is None


def test_parse_helpline_entry_handles_language_list():
    entry = {"region": "India", "name": "Test", "contact": "123", "languages": ["hi", "en"]}
    helpline = crisis_helplines._parse_helpline_entry(entry)

    assert helpline.languages == ["hi", "en"]


if __name__ == "__main__":
    # ponytail: quick self-check without pytest
    test_real_config_file_loads_with_new_schema()
    test_domestic_violence_helplines_also_load_from_new_file()
    test_parse_helpline_entry_handles_missing_optional_fields()
    test_parse_helpline_entry_handles_language_list()
    print("crisis_helplines self-checks passed")
