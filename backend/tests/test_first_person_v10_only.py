"""v10-only serving: the legacy slot may alias the fp-context collection.

Owner decision 2026-10-30 (option b): production serves ``first_person_v10`` only,
with no ``first_person_v8``. The serving contract used to stop startup whenever
``FIRST_PERSON_COLLECTION`` named a context collection (B4). These tests pin the one
exception and everything that must stay strict around it:

* the alias is allowed only with the context harness AND the terminal flag on;
* every context-side check still runs under the alias;
* the legacy path stays unreachable (terminal), including the facet-split path;
* the boundary guard keyed on the legacy collection name stays on for v10 spans;
* the personalize stage never reads a legacy clip store that is not there.

Nothing here contacts Qdrant, an LLM or Docker.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import settings  # noqa: E402
from services import first_person_pipeline as pipeline_mod  # noqa: E402
from services.first_person_serving_contract import (  # noqa: E402
    FirstPersonServingContractError,
    assert_startup_safe,
    fingerprint_components,
    legacy_slot_aliases_context,
    legacy_store_preflight,
    load_contract,
    v10_only_mode_active,
    validate_serving_contract,
)
from services.first_person_store import FirstPersonStore  # noqa: E402

CONTRACT_PATH = _BACKEND / "config" / "first_person_serving_contract.json"
V10 = "first_person_v10"
V8 = "first_person_v8"


@pytest.fixture(scope="module")
def contract():
    return load_contract(CONTRACT_PATH)


def _validate(contract, *, legacy=V10, context=V10, harness=True, terminal=True):
    return validate_serving_contract(
        contract=contract,
        legacy_collection=legacy,
        context_collection=context,
        context_harness_enabled=harness,
        context_terminal_enabled=terminal,
    )


# ---------------------------------------------------------------------------
# the mode predicate
# ---------------------------------------------------------------------------
def test_mode_needs_alias_harness_and_terminal():
    kwargs = dict(
        legacy_collection=V10,
        context_collection=V10,
        context_harness_enabled=True,
        context_terminal_enabled=True,
    )
    assert v10_only_mode_active(**kwargs)
    assert not v10_only_mode_active(**{**kwargs, "context_harness_enabled": False})
    assert not v10_only_mode_active(**{**kwargs, "context_terminal_enabled": False})
    assert not v10_only_mode_active(**{**kwargs, "legacy_collection": V8})
    assert not v10_only_mode_active(**{**kwargs, "legacy_collection": ""})


@pytest.mark.parametrize("truthy_not_true", [1, "true", Mock()])
def test_terminal_flag_must_be_the_literal_true(truthy_not_true):
    """Same strictness as the pipeline's own terminal check."""
    assert not v10_only_mode_active(
        legacy_collection=V10,
        context_collection=V10,
        context_harness_enabled=True,
        context_terminal_enabled=truthy_not_true,
    )


@pytest.mark.parametrize("value", [None, 7, Mock(), ""])
def test_only_real_strings_can_alias(value):
    assert not legacy_slot_aliases_context(value, V10)
    assert not legacy_slot_aliases_context(V10, value)


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------
def test_v10_only_config_is_clean_against_the_shipped_contract(contract):
    report = _validate(contract)
    assert report.ok, report.errors
    assert any("v10-only mode" in warning for warning in report.warnings)
    assert report.context_collection == V10


def test_v10_only_config_passes_the_production_startup_gate(contract):
    assert_startup_safe(
        _validate(contract),
        is_production=True,
        legacy_route_enabled=True,
        context_harness_enabled=True,
    )


def test_alias_without_the_terminal_flag_still_stops_production(contract):
    report = _validate(contract, terminal=False)
    assert not report.ok
    assert any("both point at" in error for error in report.errors)
    with pytest.raises(FirstPersonServingContractError):
        assert_startup_safe(
            report,
            is_production=True,
            legacy_route_enabled=True,
            context_harness_enabled=True,
        )


def test_alias_without_the_harness_is_still_an_error(contract):
    report = _validate(contract, harness=False, terminal=True)
    assert not report.ok
    assert any("fp-context collection" in error for error in report.errors)


def test_alias_to_a_legacy_collection_is_still_an_error(contract):
    """The exception never covers the old schema: v8 on both slots is refused."""
    report = _validate(contract, legacy=V8, context=V8)
    assert not report.ok
    assert any("legacy-only collection" in error for error in report.errors)


def test_alias_to_an_undeclared_collection_is_still_an_error(contract):
    report = _validate(contract, legacy="first_person_v99", context="first_person_v99")
    assert not report.ok
    assert any("not declared" in error for error in report.errors)


def test_the_normal_two_slot_config_is_unchanged(contract):
    report = _validate(contract, legacy=V8, context=V10, terminal=True)
    assert report.ok, report.errors
    assert not any("v10-only mode" in warning for warning in report.warnings)


def test_default_arguments_keep_the_old_behaviour(contract):
    """Callers that do not know about the terminal flag see no change."""
    report = validate_serving_contract(
        contract=contract,
        legacy_collection=V10,
        context_collection=V10,
        context_harness_enabled=True,
    )
    assert not report.ok


def test_preflight_accepts_the_alias_only_with_both_flags(contract):
    ok = legacy_store_preflight(
        contract=contract,
        legacy_collection=V10,
        context_collection=V10,
        context_harness_enabled=True,
        context_terminal_enabled=True,
    )
    assert ok.ok, ok.errors
    assert not legacy_store_preflight(contract=contract, legacy_collection=V10).ok


def test_aliased_fingerprint_names_the_context_collection(contract):
    components = fingerprint_components(contract[V10])
    assert components["collection"] == V10
    assert components["schema"] == "fp-context-v1"
    assert all(components[key] for key in ("corpus_version", "evidence_policy"))


# ---------------------------------------------------------------------------
# the pipeline
# ---------------------------------------------------------------------------
def _contract_error(monkeypatch, *, harness, terminal, context=V10):
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", harness)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", terminal)
    monkeypatch.setattr(settings, "first_person_context_collection", context)
    pipeline = pipeline_mod.FirstPersonPipeline.__new__(pipeline_mod.FirstPersonPipeline)
    pipeline._store = FirstPersonStore.__new__(FirstPersonStore)
    pipeline._store._collection = V10
    pipeline._serving_contract_error_cache = pipeline_mod._CONTRACT_UNSET
    return pipeline._serving_contract_error()


def test_pipeline_serves_when_the_legacy_slot_is_v10_and_v10_only_is_on(monkeypatch):
    assert _contract_error(monkeypatch, harness=True, terminal=True) == ""


@pytest.mark.parametrize(("harness", "terminal"), [(True, False), (False, True), (False, False)])
def test_pipeline_refuses_when_either_flag_is_off(monkeypatch, harness, terminal):
    error = _contract_error(monkeypatch, harness=harness, terminal=terminal)
    assert error
    assert "fp-context collection" in error


def test_pipeline_refuses_a_v10_legacy_slot_with_a_different_context_collection(monkeypatch):
    error = _contract_error(monkeypatch, harness=True, terminal=True, context="")
    assert error
    assert "fp-context collection" in error


def _pipeline(monkeypatch, *, store_collection, context=V10, guard=False):
    monkeypatch.setattr(settings, "first_person_context_collection", context)
    monkeypatch.setattr(settings, "first_person_boundary_guard_enabled", guard)
    store = Mock()
    store.collection = store_collection
    return pipeline_mod.FirstPersonPipeline(store=store, serene_mind_engine=Mock())


def test_boundary_guard_stays_on_when_the_legacy_slot_is_v10(monkeypatch):
    """The guard is keyed on the legacy collection NAME (v6/v7/v8); a v10 slot must
    not silently switch it off for the harness spans."""
    pipeline = _pipeline(monkeypatch, store_collection=V10)
    assert pipeline._boundary_guard_enabled is True
    assert pipeline._content_quality_gate_enabled is True


def test_boundary_guard_for_the_v8_named_config_is_unchanged(monkeypatch):
    assert _pipeline(monkeypatch, store_collection=V8)._boundary_guard_enabled is True
    # A collection outside the keyed list, with no alias and no setting, stays off.
    other = _pipeline(monkeypatch, store_collection="first_person_v9")
    assert other._boundary_guard_enabled is False


def test_facet_split_is_skipped_while_the_harness_is_terminal(monkeypatch):
    """Compound decomposition searches only the legacy store, so it must not run
    in v10-only mode."""
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", True)
    monkeypatch.setattr(settings, "first_person_facet_split_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "")
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", False)

    decomposed = Mock(return_value=["a", "b"])
    monkeypatch.setattr(pipeline_mod, "_decompose_query_facets", decomposed)
    compound = Mock()
    monkeypatch.setattr(pipeline_mod.FirstPersonPipeline, "_execute_compound", compound)

    ctx_store = Mock()
    ctx_store.retrieve.return_value = []
    legacy = Mock()
    legacy.collection = V10
    legacy.search_hybrid.return_value = []
    pipeline = pipeline_mod.FirstPersonPipeline(
        store=legacy, serene_mind_engine=Mock(), context_store=ctx_store
    )
    pipeline._serving_contract_error_cache = ""
    pipeline._serene_mind.assess_distress.return_value = None

    result = pipeline.execute(
        query="How do I handle anger and also fear?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    decomposed.assert_not_called()
    compound.assert_not_called()
    legacy.search_hybrid.assert_not_called()
    assert result.status == "abstained"
    assert result.abstain_reason == "no_verified_clips"


def test_facet_split_still_runs_when_the_harness_is_not_terminal(monkeypatch):
    monkeypatch.setattr(settings, "first_person_context_harness_enabled", False)
    monkeypatch.setattr(settings, "first_person_context_terminal_enabled", False)
    monkeypatch.setattr(settings, "first_person_facet_split_enabled", True)
    monkeypatch.setattr(settings, "first_person_context_collection", "")

    decomposed = Mock(return_value=["only one facet"])
    monkeypatch.setattr(pipeline_mod, "_decompose_query_facets", decomposed)

    legacy = Mock()
    legacy.collection = V8
    legacy.search_hybrid.return_value = []
    pipeline = pipeline_mod.FirstPersonPipeline(store=legacy, serene_mind_engine=Mock())
    pipeline._serving_contract_error_cache = ""
    pipeline._serene_mind.assess_distress.return_value = None
    pipeline.execute(
        query="How do I handle anger and also fear?",
        query_dense_vector=[0.1] * 1024,
        cache_bypass=True,
    )

    decomposed.assert_called_once()


# ---------------------------------------------------------------------------
# the personalize stage
# ---------------------------------------------------------------------------
def test_personalize_declines_without_a_qdrant_read_when_the_slot_is_aliased(monkeypatch):
    from app.pipeline.stages import personalize_stage

    monkeypatch.setattr(settings, "first_person_collection", V10)
    monkeypatch.setattr(settings, "first_person_context_collection", V10)
    store_for_request = Mock(side_effect=AssertionError("legacy store must not be built"))
    monkeypatch.setattr(personalize_stage, "_store_for_request", store_for_request)

    assert (
        personalize_stage._lookup_servable_clip({"video_id": "abc", "timestamp_seconds": 12})
        is None
    )
    store_for_request.assert_not_called()


def test_personalize_still_reads_the_legacy_store_for_the_two_slot_config(monkeypatch):
    from app.pipeline.stages import personalize_stage

    monkeypatch.setattr(settings, "first_person_collection", V8)
    monkeypatch.setattr(settings, "first_person_context_collection", V10)
    store = Mock()
    store.get_clip_by_video_and_start.return_value = None
    monkeypatch.setattr(personalize_stage, "_store_for_request", Mock(return_value=store))

    assert (
        personalize_stage._lookup_servable_clip({"video_id": "abc", "timestamp_seconds": 12})
        is None
    )
    store.get_clip_by_video_and_start.assert_called_once()
