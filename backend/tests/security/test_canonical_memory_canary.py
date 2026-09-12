"""Tests for canonical memory canary deployment — Phase 24."""
import pytest
from services.canonical_memory.canary import (
    CanaryConfig,
    CanaryDeployment,
    CanaryStage,
    get_canary_deployment,
)


class TestCanaryOff:
    def test_canary_off(self):
        canary = get_canary_deployment(CanaryStage.OFF)
        assert canary.config.stage == CanaryStage.OFF
        assert canary.should_use_canonical("u1") is False

    def test_canary_off_returns_false_for_any_user(self):
        canary = get_canary_deployment(CanaryStage.OFF)
        assert canary.should_use_canonical("internal_admin") is False
        assert canary.should_use_canonical("whitelisted_user") is False


class TestCanaryInternalTesting:
    def test_canary_internal_testing(self):
        canary = get_canary_deployment(CanaryStage.INTERNAL_TESTING)
        assert canary.should_use_canonical("internal_dev") is True

    def test_canary_internal_testing_rejects_external(self):
        canary = get_canary_deployment(CanaryStage.INTERNAL_TESTING)
        assert canary.should_use_canonical("external_user") is False

    def test_canary_internal_testing_requires_prefix(self):
        canary = get_canary_deployment(CanaryStage.INTERNAL_TESTING)
        assert canary.should_use_canonical("internal_") is True
        assert canary.should_use_canonical("notinternal_1") is False


class TestCanaryWhitelist:
    def test_canary_whitelist(self):
        config = CanaryConfig(
            stage=CanaryStage.INTERNAL_TESTING,
            user_whitelist=["beta_user_1", "beta_user_2"],
        )
        canary = CanaryDeployment(config)
        assert canary.should_use_canonical("beta_user_1") is True
        assert canary.should_use_canonical("beta_user_2") is True
        assert canary.should_use_canonical("unknown_user") is False

    def test_canary_whitelist_works_across_stages(self):
        config = CanaryConfig(
            stage=CanaryStage.SMALL_PERCENTAGE,
            user_whitelist=["special_user"],
        )
        canary = CanaryDeployment(config)
        assert canary.should_use_canonical("special_user") is True
        assert canary.should_use_canonical("other_user") is False


class TestCanaryFullRollout:
    def test_canary_full_rollout(self):
        canary = get_canary_deployment(CanaryStage.FULL_ROLLOUT)
        assert canary.should_use_canonical("any_user") is True

    def test_canary_full_rollout_all_users(self):
        canary = get_canary_deployment(CanaryStage.FULL_ROLLOUT)
        assert canary.should_use_canonical("u12345") is True
        assert canary.should_use_canonical("internal_admin") is True
        assert canary.should_use_canonical("") is True


class TestRecordTurn:
    def test_record_turn_success(self):
        canary = get_canary_deployment()
        canary.record_turn(100.0, True)
        assert canary._metrics["turns"] == 1
        assert canary._metrics["errors"] == 0
        assert canary._metrics["total_latency_ms"] == 100.0

    def test_record_turn_error(self):
        canary = get_canary_deployment()
        canary.record_turn(500.0, False)
        assert canary._metrics["turns"] == 1
        assert canary._metrics["errors"] == 1
        assert canary._metrics["total_latency_ms"] == 500.0

    def test_record_multiple_turns(self):
        canary = get_canary_deployment()
        canary.record_turn(100.0, True)
        canary.record_turn(200.0, True)
        canary.record_turn(300.0, False)
        assert canary._metrics["turns"] == 3
        assert canary._metrics["errors"] == 1
        assert canary._metrics["total_latency_ms"] == 600.0


class TestCheckHealth:
    def test_check_health_healthy(self):
        canary = get_canary_deployment()
        for _ in range(10):
            canary.record_turn(50.0, True)
        health = canary.check_health()
        assert health["turns"] == 10
        assert health["error_rate"] == 0.0
        assert health["avg_latency_ms"] == 50.0
        assert health["healthy"] is True
        assert health["should_rollback"] is False

    def test_check_health_unhealthy_high_error_rate(self):
        canary = get_canary_deployment()
        for _ in range(10):
            canary.record_turn(50.0, False)
        health = canary.check_health()
        assert health["error_rate"] == 1.0
        assert health["healthy"] is False
        assert health["should_rollback"] is True

    def test_check_health_unhealthy_high_latency(self):
        config = CanaryConfig(latency_threshold_ms=100.0)
        canary = CanaryDeployment(config)
        for _ in range(10):
            canary.record_turn(500.0, True)
        health = canary.check_health()
        assert health["avg_latency_ms"] == 500.0
        assert health["healthy"] is False

    def test_check_health_should_promote(self):
        canary = get_canary_deployment()
        for _ in range(100):
            canary.record_turn(50.0, True)
        health = canary.check_health()
        assert health["should_promote"] is True

    def test_check_health_no_promote_under_threshold(self):
        canary = get_canary_deployment()
        for _ in range(50):
            canary.record_turn(50.0, True)
        health = canary.check_health()
        assert health["should_promote"] is False

    def test_check_health_no_turns(self):
        canary = get_canary_deployment()
        health = canary.check_health()
        assert health["turns"] == 0
        assert health["error_rate"] == 0.0
        assert health["healthy"] is True


class TestPromote:
    def test_promote(self):
        canary = get_canary_deployment(CanaryStage.OFF)
        result = canary.promote()
        assert result["new_stage"] == CanaryStage.INTERNAL_TESTING.value
        assert result["promoted"] is True

    def test_promote_through_all_stages(self):
        canary = get_canary_deployment(CanaryStage.OFF)
        canary.promote()
        assert canary.config.stage == CanaryStage.INTERNAL_TESTING
        canary.promote()
        assert canary.config.stage == CanaryStage.SMALL_PERCENTAGE
        canary.promote()
        assert canary.config.stage == CanaryStage.HALF_ROLLOUT
        canary.promote()
        assert canary.config.stage == CanaryStage.FULL_ROLLOUT

    def test_promote_already_full(self):
        canary = get_canary_deployment(CanaryStage.FULL_ROLLOUT)
        result = canary.promote()
        assert result["new_stage"] == CanaryStage.FULL_ROLLOUT.value

    def test_promote_from_rolled_back(self):
        canary = get_canary_deployment(CanaryStage.ROLLED_BACK)
        result = canary.promote()
        assert result["new_stage"] == CanaryStage.OFF.value
        assert canary.config.stage == CanaryStage.OFF


class TestRollback:
    def test_rollback(self):
        canary = get_canary_deployment(CanaryStage.HALF_ROLLOUT)
        result = canary.rollback()
        assert result["stage"] == CanaryStage.ROLLED_BACK.value
        assert result["rolled_back"] is True
        assert canary.config.stage == CanaryStage.ROLLED_BACK

    def test_rollback_stops_canonical(self):
        canary = get_canary_deployment(CanaryStage.FULL_ROLLOUT)
        canary.rollback()
        assert canary.should_use_canonical("any_user") is False


class TestGetStatus:
    def test_get_status(self):
        canary = get_canary_deployment(CanaryStage.INTERNAL_TESTING)
        canary.record_turn(100.0, True)
        status = canary.get_status()
        assert status["stage"] == "internal_testing"
        assert status["percentage"] == 0.0
        assert status["config"]["error_threshold"] == 0.05
        assert status["config"]["latency_threshold_ms"] == 2000.0
        assert status["config"]["min_satisfaction"] == 0.8
        assert status["metrics"]["turns"] == 1


class TestGetCanaryDeployment:
    def test_factory_default(self):
        canary = get_canary_deployment()
        assert isinstance(canary, CanaryDeployment)
        assert canary.config.stage == CanaryStage.OFF

    def test_factory_with_stage(self):
        canary = get_canary_deployment(CanaryStage.HALF_ROLLOUT)
        assert canary.config.stage == CanaryStage.HALF_ROLLOUT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
