"""Readiness scope contract: staging evidence is not production authorization."""

from scripts.ops.predeployment_checklist import check_data_quality_qdrant, readiness_exit_code


def test_staging_scope_can_pass_when_staging_checks_pass() -> None:
    assert readiness_exit_code("staging", True, False) == 0


def test_staging_scope_fails_when_staging_checks_fail() -> None:
    assert readiness_exit_code("staging", False, True) == 1


def test_production_scope_requires_owner_authorization() -> None:
    assert readiness_exit_code("production", True, False) == 1


def test_production_scope_requires_staging_evidence_too() -> None:
    assert readiness_exit_code("production", False, True) == 1


def test_production_scope_passes_only_when_both_gates_pass() -> None:
    assert readiness_exit_code("production", True, True) == 0



def test_data_quality_gate_checks_the_v13_collection(monkeypatch) -> None:
    import httpx

    calls: list[tuple[str, float]] = []

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"result": {"points_count": 4099}}

    def fake_get(url: str, timeout: float) -> Response:
        calls.append((url, timeout))
        return Response()

    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setattr(httpx, "get", fake_get)

    passed, message = check_data_quality_qdrant()

    assert passed is True
    assert calls == [("https://qdrant.example/collections/first_person_v13_shadow", 5.0)]
    assert "first_person_v13_shadow" in message
    assert "v12_shadow" not in message
