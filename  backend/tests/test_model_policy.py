


def test_policy_emits_optional_latency_preferences_only_when_enabled():
    policy = OpenRouterModelPolicy.from_settings(
        _settings(
            openrouter_provider_sort="latency",
            openrouter_provider_partition="none",
            openrouter_preferred_max_latency_p90=3.0,
        )
    )

    assert policy.provider_preferences()["sort"] == {"by": "latency", "partition": "none"}
    assert policy.provider_preferences()["preferred_max_latency"] == {"p90": 3.0}
    assert "preferred_min_throughput" not in policy.provider_preferences()


def test_policy_rejects_invalid_latency_preferences():
    with pytest.raises(ModelPolicyError, match="provider_sort"):
        OpenRouterModelPolicy.from_settings(_settings(openrouter_provider_sort="random"))
    with pytest.raises(ModelPolicyError, match="thresholds"):
        OpenRouterModelPolicy.from_settings(
            _settings(openrouter_preferred_max_latency_p90=3.0)
        )
