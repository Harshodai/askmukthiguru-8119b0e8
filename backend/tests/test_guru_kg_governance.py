from __future__ import annotations

from services.guru_brain.guru_kg_service import GuruKGService


class _Session:
    def __init__(self, calls: list[tuple[str, dict]]) -> None:
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return []


class _Driver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def session(self):
        return _Session(self.calls)


def _allowed_source(**_kwargs) -> bool:
    return True


def _allowed_consent(**_kwargs) -> bool:
    return True


def test_empty_graph_never_fabricates_a_spiritual_arc() -> None:
    service = GuruKGService()
    assert service.traverse_guru_ontology("anxiety") == []


def test_empty_query_and_non_positive_limit_do_not_touch_graph() -> None:
    driver = _Driver()
    service = GuruKGService(neo4j_driver=driver)
    assert service.traverse_guru_ontology("   ") == []
    assert service.traverse_guru_ontology("anxiety", limit=0) == []
    assert driver.calls == []


def test_source_arc_write_requires_authoritative_provenance_and_authorizer() -> None:
    driver = _Driver()
    denied = GuruKGService(neo4j_driver=driver)
    result = denied.populate_ontology_arc(
        seeker_dilemma="fear",
        limiting_belief="worth depends on outcomes",
        teaching="Present Moment Awareness",
        target_state="Beautiful State",
        practice_step="Observe the breath",
        tenant_id="oneness",
        source_asset_id="video-123",
        source_url="https://youtube.com/watch?v=video-123",
        video_id="video-123",
        domain_rights_status="licensed",
    )
    assert result is False
    assert driver.calls == []


def test_authorized_source_arc_is_tenant_and_source_scoped() -> None:
    driver = _Driver()
    service = GuruKGService(
        neo4j_driver=driver,
        source_write_authorizer=_allowed_source,
    )
    assert service.populate_ontology_arc(
        seeker_dilemma="fear",
        limiting_belief="worth depends on outcomes",
        teaching="Present Moment Awareness",
        target_state="Beautiful State",
        practice_step="Observe the breath",
        tenant_id="oneness",
        source_asset_id="video-123",
        source_url="https://youtube.com/watch?v=video-123",
        video_id="video-123",
        domain_rights_status="licensed",
        speaker_verified=True,
        speaker_verification_reference="speaker-review-123",
    )
    assert len(driver.calls) == 1
    cypher, params = driver.calls[0]
    assert "tenant_id: $tenant_id" in cypher
    assert "source_asset_id: $source_asset_id" in cypher
    assert params["tenant_id"] == "oneness"
    assert params["source_asset_id"] == "video-123"
    assert params["speaker_verified"] is True
    assert params["speaker_verification_reference"] == "speaker-review-123"


def test_user_state_graph_write_requires_explicit_consent_authorizer() -> None:
    driver = _Driver()
    denied = GuruKGService(neo4j_driver=driver)
    assert not denied.record_user_state_transition(
        "user-1",
        "anxiety",
        "peace",
        tenant_id="oneness",
        consent_receipt_id="receipt-1",
    )
    assert driver.calls == []


def test_authorized_user_state_write_is_tenant_and_receipt_scoped() -> None:
    driver = _Driver()
    service = GuruKGService(
        neo4j_driver=driver,
        user_state_write_authorizer=_allowed_consent,
    )
    assert service.record_user_state_transition(
        "user-1",
        "anxiety",
        "peace",
        "reflection",
        tenant_id="oneness",
        consent_receipt_id="receipt-1",
    )
    assert len(driver.calls) == 1
    cypher, params = driver.calls[0]
    assert "consent_receipt_id: $consent_receipt_id" in cypher
    assert "tenant_id: $tenant_id" in cypher
    assert params["consent_receipt_id"] == "receipt-1"
    assert params["tenant_id"] == "oneness"



def test_graph_traversal_requires_tenant_scope_before_opening_driver() -> None:
    class _ExplodingDriver:
        def session(self):
            raise AssertionError("unscoped traversal must not open a graph session")

    service = GuruKGService(neo4j_driver=_ExplodingDriver())
    assert service.traverse_guru_ontology("anxiety") == []
    assert service.traverse_guru_ontology("anxiety", tenant_id=" ") == []


def test_graph_traversal_uses_tenant_predicates_and_transaction_timeout() -> None:
    class _Tx:
        def __init__(self, calls):
            self.calls = calls
            self.committed = False

        def run(self, query: str, **params):
            self.calls.append((query, params))
            return [
                {
                    "dilemma": "anxiety",
                    "belief": "peace depends on outcomes",
                    "teaching": "witnessing",
                    "state": "beautiful state",
                    "practice": "observe",
                    "guru": "verified teacher",
                    "tenant_id": "tenant_alpha",
                    "source_asset_id": "asset-42",
                    "source_url": "https://youtu.be/asset-42",
                    "video_id": "asset-42",
                    "domain_rights_status": "licensed",
                    "speaker_verified": True,
                    "speaker_verification_reference": "speaker-packet-42",
                }
            ]

        def commit(self):
            self.committed = True

        def rollback(self):
            return None

    class _SessionWithTx:
        def __init__(self, calls):
            self.calls = calls
            self.tx = _Tx(calls)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def begin_transaction(self, *, timeout=None):
            self.calls.append(("transaction", {"timeout": timeout}))
            return self.tx

    class _TenantDriver:
        def __init__(self):
            self.calls = []
            self.session_value = _SessionWithTx(self.calls)

        def session(self):
            return self.session_value

    driver = _TenantDriver()
    service = GuruKGService(neo4j_driver=driver)

    arcs = service.traverse_guru_ontology(
        "anxiety",
        limit=4,
        timeout=0.4,
        tenant_id="tenant_alpha",
    )

    assert len(arcs) == 1
    assert driver.session_value.tx.committed is True
    assert driver.calls[0] == ("transaction", {"timeout": 0.4})
    cypher, params = driver.calls[1]
    assert "tenant_id: $tenant_id" in cypher
    for relationship in ("driven", "dismantles", "transforms", "prescribes", "teaches"):
        assert f"{relationship}.tenant_id = $tenant_id" in cypher
        assert f"{relationship}.source_asset_id" in cypher
    assert "speaker_verified = true" in cypher
    assert "speaker_verification_reference" in cypher
    assert params["tenant_id"] == "tenant_alpha"



def test_source_arc_rejects_unverified_speaker_even_when_authorizer_is_present() -> None:
    driver = _Driver()
    service = GuruKGService(
        neo4j_driver=driver,
        source_write_authorizer=_allowed_source,
    )
    assert not service.populate_ontology_arc(
        seeker_dilemma="fear",
        limiting_belief="worth depends on outcomes",
        teaching="Present Moment Awareness",
        target_state="Beautiful State",
        practice_step="Observe the breath",
        tenant_id="oneness",
        source_asset_id="video-123",
        source_url="https://youtube.com/watch?v=video-123",
        video_id="video-123",
        domain_rights_status="licensed",
        speaker_verification_reference="speaker-review-123",
    )
    assert driver.calls == []


def test_source_arc_rejects_unlicensed_status_even_when_authorizer_is_present() -> None:
    driver = _Driver()
    service = GuruKGService(
        neo4j_driver=driver,
        source_write_authorizer=_allowed_source,
    )
    assert not service.populate_ontology_arc(
        seeker_dilemma="fear",
        limiting_belief="worth depends on outcomes",
        teaching="Present Moment Awareness",
        target_state="Beautiful State",
        practice_step="Observe the breath",
        tenant_id="oneness",
        source_asset_id="video-123",
        source_url="https://youtube.com/watch?v=video-123",
        video_id="video-123",
        domain_rights_status="pending",
        speaker_verified=True,
        speaker_verification_reference="speaker-review-123",
    )
    assert driver.calls == []
