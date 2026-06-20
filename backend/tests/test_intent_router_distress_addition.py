
    try:
        result = await intent_module.intent_router(state, config=None)
    finally:
        intent_module._intent_classification_cache.pop(cache_key, None)

    assert result["intent"] == "FACTUAL"
    assert result["query_tier"] == "tier3_complex"
    assert result["evaluation_trace"].get("routing_reason") == "cache_hit"


class _DistressModerate:
    level = 2  # DistressLevel.MODERATE
    confidence = 0.8
    detected_signals = ["hopeless"]


class _FakeSereneMindDistress:
    def assess_distress(self, message, conversation_history=None):
        return _DistressModerate()


@pytest.mark.asyncio
async def test_intent_router_exception_fallback_routes_distress(monkeypatch):
    """If the classifier crashes, the fallback checks distress keywords and routes DISTRESS."""

    async def _impl(state, config=None):
        raise RuntimeError("classifier crashed")

    monkeypatch.setattr(intent_module, "_intent_router_impl", _impl)
    monkeypatch.setattr(
        intent_module._services, "_serene_mind", _FakeSereneMindDistress()
    )

    state = _make_state("I feel hopeless and cannot go on")
    result = await intent_module.intent_router(state, config=None)

    assert result["intent"] == "DISTRESS"
    assert result["query_tier"] == "tier2_simple"
    assert result["evaluation_trace"].get("routing_reason") == "intent_fallback_with_distress_check"


def test_intent_module_imports_without_indentation_error():
    """The module must parse and import successfully (regression for prior IndentationError)."""
    import ast

    import rag.nodes.intent as intent_mod

    source = intent_mod.__loader__.get_source(intent_mod.__name__)
    ast.parse(source)
