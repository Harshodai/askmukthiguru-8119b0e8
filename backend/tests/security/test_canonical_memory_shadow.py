"""Tests for canonical memory shadow mode — Phase 23."""
import pytest
from services.canonical_memory.shadow import (
    ShadowMode,
    ShadowResult,
    get_shadow_mode,
)


class TestShadowDisabled:
    def test_shadow_disabled_returns_not_executed(self):
        sm = ShadowMode(enabled=False)
        result = sm.run_canonical_pipeline("u1", "hello")
        assert result["executed"] is False
        assert result["reason"] == "shadow_disabled"

    def test_shadow_disabled_default(self):
        sm = ShadowMode()
        assert sm.enabled is False


class TestShadowEnabledCanonical:
    def test_canonical_executes(self):
        sm = ShadowMode(enabled=True)
        result = sm.run_canonical_pipeline("u1", "test message")
        assert result["executed"] is True
        assert result["user_id"] == "u1"
        assert result["message_length"] == 12
        assert result["decision"] == "extract_and_store"
        assert result["confidence"] == 0.85


class TestShadowLegacy:
    def test_legacy_always_executes(self):
        sm = ShadowMode(enabled=False)
        result = sm.run_legacy_pipeline("u1", "hello")
        assert result["executed"] is True
        assert result["method"] == "outbox"

    def test_legacy_message_length(self):
        sm = ShadowMode()
        result = sm.run_legacy_pipeline("u1", "short")
        assert result["message_length"] == 5


class TestCompareResults:
    def test_matching_results(self):
        sm = ShadowMode()
        canonical = {"decision": "extract_and_store"}
        legacy = {"method": "extract_and_store"}
        result = sm.compare_results(canonical, legacy)
        assert result.results_match is True

    def test_divergent_results(self):
        sm = ShadowMode()
        canonical = {"decision": "extract_and_store"}
        legacy = {"method": "outbox"}
        result = sm.compare_results(canonical, legacy)
        assert result.results_match is False

    def test_turn_id_generated(self):
        sm = ShadowMode()
        result = sm.compare_results({}, {})
        assert result.turn_id.startswith("shadow_")

    def test_timestamp_set(self):
        sm = ShadowMode()
        result = sm.compare_results({}, {})
        assert result.timestamp != ""


class TestRecordAndAccuracy:
    def test_record_single(self):
        sm = ShadowMode()
        sr = ShadowResult(
            turn_id="t1", canonical_decision="a", legacy_decision="a",
            results_match=True, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
        )
        sm.record_result(sr)
        assert len(sm._results) == 1

    def test_accuracy_no_results(self):
        sm = ShadowMode()
        acc = sm.get_accuracy()
        assert acc["total"] == 0
        assert acc["match_rate"] == 1.0
        assert acc["divergences"] == 0

    def test_accuracy_all_match(self):
        sm = ShadowMode()
        for i in range(5):
            sm.record_result(ShadowResult(
                turn_id=f"t{i}", canonical_decision="x", legacy_decision="x",
                results_match=True, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
            ))
        acc = sm.get_accuracy()
        assert acc["total"] == 5
        assert acc["matches"] == 5
        assert acc["match_rate"] == 1.0

    def test_accuracy_partial_match(self):
        sm = ShadowMode()
        sm.record_result(ShadowResult(
            turn_id="t1", canonical_decision="a", legacy_decision="a",
            results_match=True, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
        ))
        sm.record_result(ShadowResult(
            turn_id="t2", canonical_decision="b", legacy_decision="c",
            results_match=False, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
        ))
        acc = sm.get_accuracy()
        assert acc["matches"] == 1
        assert acc["divergences"] == 1
        assert acc["match_rate"] == 0.5


class TestDivergences:
    def test_no_divergences(self):
        sm = ShadowMode()
        sm.record_result(ShadowResult(
            turn_id="t1", canonical_decision="a", legacy_decision="a",
            results_match=True, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
        ))
        assert sm.get_divergences() == []

    def test_divergences_listed(self):
        sm = ShadowMode()
        sm.record_result(ShadowResult(
            turn_id="t1", canonical_decision="a", legacy_decision="b",
            results_match=False, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
        ))
        divs = sm.get_divergences()
        assert len(divs) == 1
        assert divs[0]["turn_id"] == "t1"
        assert divs[0]["canonical"] == "a"
        assert divs[0]["legacy"] == "b"


class TestGetSummary:
    def test_summary_empty(self):
        sm = ShadowMode(enabled=True)
        summary = sm.get_summary()
        assert summary["enabled"] is True
        assert summary["total_turns"] == 0
        assert summary["accuracy"]["match_rate"] == 1.0
        assert summary["recommendation"] == "promote_to_canonical"

    def test_summary_low_accuracy(self):
        sm = ShadowMode(enabled=False)
        for i in range(4):
            sm.record_result(ShadowResult(
                turn_id=f"t{i}", canonical_decision="x", legacy_decision="y",
                results_match=False, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
            ))
        summary = sm.get_summary()
        assert summary["enabled"] is False
        assert summary["divergences"] == 4
        assert summary["recommendation"] == "investigate_divergences"

    def test_summary_high_accuracy(self):
        sm = ShadowMode(enabled=True)
        for i in range(10):
            sm.record_result(ShadowResult(
                turn_id=f"t{i}", canonical_decision="x", legacy_decision="x",
                results_match=True, canonical_latency_ms=1.0, legacy_latency_ms=2.0,
            ))
        summary = sm.get_summary()
        assert summary["recommendation"] == "promote_to_canonical"


class TestEnableDisable:
    def test_enable(self):
        sm = ShadowMode(enabled=False)
        sm.enable()
        assert sm.enabled is True

    def test_disable(self):
        sm = ShadowMode(enabled=True)
        sm.disable()
        assert sm.enabled is False

    def test_toggle(self):
        sm = ShadowMode()
        sm.enable()
        assert sm.enabled is True
        sm.disable()
        assert sm.enabled is False


class TestGetShadowMode:
    def test_factory_default(self):
        sm = get_shadow_mode()
        assert isinstance(sm, ShadowMode)
        assert sm.enabled is False

    def test_factory_enabled(self):
        sm = get_shadow_mode(enabled=True)
        assert sm.enabled is True

    def test_factory_with_db(self):
        db = object()
        sm = get_shadow_mode(db_client=db, enabled=True)
        assert sm.db is db


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
