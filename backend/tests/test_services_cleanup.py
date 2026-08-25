from rag.nodes import _services


def test_clear_services_clears_llm_gateway(monkeypatch) -> None:
    monkeypatch.setattr(_services, "_llm_gateway", object())

    _services.clear_services()

    assert _services._llm_gateway is None
