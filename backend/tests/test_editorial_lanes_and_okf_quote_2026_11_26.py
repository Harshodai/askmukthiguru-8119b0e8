"""Editorial search wiring (real container attributes, per-lane errors) and OKF-not-verbatim."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.api.editorial as editorial_api
from domain.evidence_contract import (
    ClaimEvidenceMapping,
    EpistemicCategory,
    EvidenceCandidate,
)
from services.evidence_adapters.claim_verifier import ClaimVerificationService


def _ev(
    eid: str, source: str, text: str = "Be still and know.", verified: bool | None = None
) -> EvidenceCandidate:
    return EvidenceCandidate(
        speaker_verified=(source == "qdrant") if verified is None else verified,
        evidence_id=eid,
        source_id=f"s-{eid}",
        text=text,
        retrieval_source=source,
        teacher_id="preethaji",
    )


class _Embedding:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _QdrantAdapter:
    seen: dict[str, Any] = {}

    def __init__(self, client: Any, collection: str) -> None:
        _QdrantAdapter.seen = {"client": client, "collection": collection}

    def search(self, **_: Any) -> list[EvidenceCandidate]:
        return [_ev("q1", "qdrant")]


class _OkfBoom:
    def search(self, **_: Any) -> list[EvidenceCandidate]:
        raise RuntimeError("okf exploded")


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)
    monkeypatch.setattr(editorial_api, "QdrantEvidenceAdapter", _QdrantAdapter)
    monkeypatch.setattr(editorial_api, "OKFEvidenceAdapter", _OkfBoom)


def test_search_uses_real_attributes_and_reports_failed_lane() -> None:
    real_client = object()
    container = SimpleNamespace(
        embedding=_Embedding(),
        qdrant_client=real_client,
        qdrant=SimpleNamespace(),  # wrapper must NOT be handed to the adapter
        memgraph_driver=None,
    )
    svc = editorial_api.get_editorial_service(container)  # type: ignore[arg-type]
    dossier = svc.generate_dossier(topic="stillness practice")
    assert _QdrantAdapter.seen["client"] is real_client
    assert [e.evidence_id for e in dossier.evidence_items] == ["q1"]
    assert "okf: RuntimeError: okf exploded" in dossier.lane_errors
    assert "memgraph: driver unavailable" in dossier.lane_errors


def test_missing_embedding_is_reported_not_silent() -> None:
    container = SimpleNamespace(qdrant_client=object(), memgraph_driver=None)
    svc = editorial_api.get_editorial_service(container)  # type: ignore[arg-type]
    dossier = svc.generate_dossier(topic="stillness practice")
    assert "embedding: service unavailable" in dossier.lane_errors


def _quote(eids: list[str], cat: EpistemicCategory) -> ClaimEvidenceMapping:
    return ClaimEvidenceMapping(
        claim_id="c1",
        claim_text="Be still and know.",
        epistemic_category=cat,
        evidence_ids=eids,
        teacher_attributed="preethaji",
    )


def test_okf_only_exact_quote_fails() -> None:
    rep = ClaimVerificationService().verify_claims(
        [_quote(["o1"], EpistemicCategory.VERBATIM_EVIDENCE)], [_ev("o1", "okf")]
    )
    assert not rep.passed
    assert rep.mappings[0].verification_status == "quote_mismatch"
    assert "OKF" in (rep.mappings[0].notes or "")


def test_qdrant_span_exact_quote_passes_even_beside_okf() -> None:
    rep = ClaimVerificationService().verify_claims(
        [_quote(["q1", "o1"], EpistemicCategory.VERBATIM_EVIDENCE)],
        [_ev("q1", "qdrant"), _ev("o1", "okf")],
    )
    assert rep.passed


def test_okf_still_supports_paraphrase() -> None:
    rep = ClaimVerificationService().verify_claims(
        [_quote(["o1"], EpistemicCategory.PARAPHRASE)], [_ev("o1", "okf")]
    )
    assert rep.passed


def test_memgraph_and_unverified_speaker_cannot_back_exact_quote() -> None:
    svc = ClaimVerificationService()
    for ev in (_ev("m1", "memgraph"), _ev("q2", "qdrant", verified=False)):
        rep = svc.verify_claims(
            [_quote([ev.evidence_id], EpistemicCategory.VERBATIM_EVIDENCE)], [ev]
        )
        assert rep.mappings[0].verification_status == "quote_mismatch"
        assert "verified speaker" in rep.mappings[0].notes


# --- real adapters, failing backends, via the editorial search wiring ---


class _BoomClient:
    def query_points(self, **_: Any) -> Any:
        raise ConnectionError("qdrant down")


class _BoomDriver:
    def session(self) -> Any:
        raise ConnectionError("bolt down")


def _real_container(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(embedding=_Embedding(), memgraph_driver=None, **kw)


def test_real_qdrant_adapter_failure_lands_in_lane_errors(monkeypatch) -> None:
    monkeypatch.undo()  # drop the fake QdrantEvidenceAdapter/OKF patches
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)
    svc = editorial_api.get_editorial_service(_real_container(qdrant_client=_BoomClient()))  # type: ignore[arg-type]
    d = svc.generate_dossier(topic="stillness practice")
    assert any(e.startswith("qdrant: ConnectionError: qdrant down") for e in d.lane_errors)


def test_real_memgraph_adapter_failure_lands_in_lane_errors(monkeypatch) -> None:
    monkeypatch.undo()
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)
    c = SimpleNamespace(embedding=_Embedding(), qdrant_client=None, memgraph_driver=_BoomDriver())
    d = editorial_api.get_editorial_service(c).generate_dossier(topic="stillness practice")  # type: ignore[arg-type]
    assert any(e.startswith("memgraph: ConnectionError: bolt down") for e in d.lane_errors)


def test_real_okf_loader_unavailable_lands_in_lane_errors(monkeypatch, tmp_path) -> None:
    import services.memory.okf_store as okf_store

    monkeypatch.undo()
    monkeypatch.setattr(okf_store, "OKF_DIR", tmp_path)  # empty dir: loader returns ([], None)
    monkeypatch.setattr(editorial_api, "_EDITORIAL_SINGLETON", None)
    c = _real_container(qdrant_client=None)
    d = editorial_api.get_editorial_service(c).generate_dossier(topic="stillness practice")  # type: ignore[arg-type]
    assert "okf: RuntimeError: OKF compiled index unavailable" in d.lane_errors


def test_qdrant_raise_on_error_keeps_first_error() -> None:
    from services.evidence_adapters import QdrantEvidenceAdapter

    class _Client:
        n = 0

        def query_points(self, **_: Any) -> Any:
            _Client.n += 1
            raise PermissionError("401 first") if _Client.n == 1 else ValueError("later")

    with pytest.raises(ValueError, match="later") as ei:
        QdrantEvidenceAdapter(_Client(), "c").search(
            query_dense=[0.1], raise_on_error=True, require_licensed=False
        )
    assert isinstance(ei.value.__cause__, PermissionError)
    assert "401 first" in str(ei.value.__cause__)


def test_evidence_pool_trust_flag_on_fact_check() -> None:
    import asyncio

    svc = editorial_api.get_editorial_service(SimpleNamespace(embedding=None, memgraph_driver=None))  # type: ignore[arg-type]
    assert svc is not None
    out = asyncio.run(
        editorial_api.fact_check_script(
            editorial_api.FactCheckRequest(blocks=[], evidence_pool=[]),
            _admin={},
            container=SimpleNamespace(embedding=None, memgraph_driver=None),  # type: ignore[arg-type]
        )
    )
    assert out["evidence_pool_trust"] == "server"
