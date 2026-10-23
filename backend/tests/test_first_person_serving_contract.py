"""Focused tests for the B4 serving-contract gate.

Public-release blocker **B4** (``docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md``):
the legacy first-person clip store and the fp-context parent/child store could
point at the same collection. The legacy path filters on
``first_person_eligible``, a field the fp-context-v1 schema does not carry, so
the two paths silently disagreed about what a record is.

These tests pin:

* the legacy store may not point at an fp-context collection;
* the context store may not point at a legacy-only collection;
* the two stores may not share one collection;
* an undeclared collection is an error, not a silent pass;
* the cache fingerprint carries the collection, its payload schema, its corpus
  version and its evidence policy;
* production stops the process on a violation, while the legacy path fails
  closed at request time outside production;
* a missing or malformed contract file fails closed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
if str(_BACKEND) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_BACKEND))

from services import first_person_serving_contract as contract_mod  # noqa: E402
from services.first_person_serving_contract import (  # noqa: E402
    CONTEXT_SCHEMA,
    LEGACY_SCHEMA,
    REQUIRED_FINGERPRINT_COMPONENTS,
    FirstPersonServingContractError,
    assert_startup_safe,
    fingerprint_components,
    legacy_store_preflight,
    load_contract,
    validate_serving_contract,
)

REPO_ROOT = _BACKEND.parent
CONTRACT_PATH = _BACKEND / "config" / "first_person_serving_contract.json"


@pytest.fixture(scope="module")
def contract():
    return load_contract(CONTRACT_PATH)


def _entry(contract, name, schema, role, corpus_version="v1", policy="policy-v1"):
    fields = (
        contract_mod.LEGACY_REQUIRED_PAYLOAD_FIELDS
        if role == contract_mod.ROLE_LEGACY
        else contract_mod.CONTEXT_REQUIRED_PAYLOAD_FIELDS
    )
    return contract_mod.CollectionContract(
        name=name,
        schema=schema,
        role=role,
        corpus_version=corpus_version,
        required_payload_fields=fields,
        evidence_policy=policy,
    )


# ---------------------------------------------------------------------------
# schema mismatch
# ---------------------------------------------------------------------------
def test_legacy_store_pointing_at_a_context_collection_is_an_error():
    contract = {
        "fp_context_v1": _entry({}, "fp_context_v1", CONTEXT_SCHEMA, contract_mod.ROLE_CONTEXT)
    }
    report = validate_serving_contract(
        contract=contract, legacy_collection="fp_context_v1", context_collection=""
    )
    assert not report.ok
    assert any("fp-context collection" in error for error in report.errors)


def test_context_store_pointing_at_a_legacy_collection_is_an_error():
    contract = {
        "first_person_v8": _entry({}, "first_person_v8", LEGACY_SCHEMA, contract_mod.ROLE_LEGACY)
    }
    report = validate_serving_contract(
        contract=contract,
        legacy_collection="first_person_v8",
        context_collection="first_person_v8",
        context_harness_enabled=True,
    )
    assert not report.ok
    assert any("legacy-only collection" in error for error in report.errors)


def test_both_stores_may_not_share_one_collection():
    contract = {"shared": _entry({}, "shared", LEGACY_SCHEMA, contract_mod.ROLE_LEGACY)}
    report = validate_serving_contract(
        contract=contract, legacy_collection="shared", context_collection="shared"
    )
    assert not report.ok
    assert any("both point at" in error for error in report.errors)


def test_undeclared_collection_is_an_error_not_a_silent_pass():
    report = validate_serving_contract(
        contract={}, legacy_collection="first_person_v99", context_collection=""
    )
    assert not report.ok
    assert any("not declared" in error for error in report.errors)


def test_empty_legacy_collection_is_an_error():
    report = validate_serving_contract(contract={}, legacy_collection="")
    assert not report.ok


def test_context_harness_enabled_without_a_context_collection_is_an_error():
    report = validate_serving_contract(
        contract={},
        legacy_collection="",
        context_collection="",
        context_harness_enabled=True,
    )
    assert not report.ok
    assert any("context harness is enabled" in error for error in report.errors)


# ---------------------------------------------------------------------------
# contract file loading
# ---------------------------------------------------------------------------
def test_shipped_contract_declares_both_schemas(contract):
    schemas = {entry.schema for entry in contract.values()}
    assert LEGACY_SCHEMA in schemas
    assert CONTEXT_SCHEMA in schemas


def test_shipped_contract_declares_the_live_v10_as_a_context_collection(contract):
    entry = contract["first_person_v10"]
    assert entry.schema == CONTEXT_SCHEMA
    assert entry.role == contract_mod.ROLE_CONTEXT
    assert "first_person_eligible" not in entry.required_payload_fields


def test_contract_file_is_valid_json_and_pins_the_required_fields():
    raw = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert raw["schema"] == contract_mod.CONTRACT_SCHEMA
    for name, entry in raw["collections"].items():
        assert entry["required_payload_fields"], name
        assert entry["corpus_version"], name
        assert entry["evidence_policy"], name


def test_missing_contract_file_fails_closed(tmp_path):
    with pytest.raises(FirstPersonServingContractError):
        load_contract(tmp_path / "nope.json")


def test_malformed_contract_file_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    with pytest.raises(FirstPersonServingContractError):
        load_contract(bad)


def test_contract_entry_omitting_required_payload_fields_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "schema": contract_mod.CONTRACT_SCHEMA,
                "collections": {
                    "c": {
                        "schema": LEGACY_SCHEMA,
                        "role": contract_mod.ROLE_LEGACY,
                        "corpus_version": "v1",
                        "required_payload_fields": ["verbatim_text"],
                        "evidence_policy": "p",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FirstPersonServingContractError):
        load_contract(bad)


# ---------------------------------------------------------------------------
# cache fingerprint scope
# ---------------------------------------------------------------------------
def test_fingerprint_components_cover_the_four_required_inputs():
    entry = _entry({}, "coll", LEGACY_SCHEMA, contract_mod.ROLE_LEGACY, "corpus-9", "evidence-9")
    components = fingerprint_components(entry)
    for key in REQUIRED_FINGERPRINT_COMPONENTS:
        assert key in components
    assert components["collection"] == "coll"
    assert components["schema"] == LEGACY_SCHEMA
    assert components["corpus_version"] == "corpus-9"
    assert components["evidence_policy"] == "evidence-9"


def test_pipeline_fingerprint_includes_the_contract_components():
    """The shipped pipeline fingerprint must carry the contract inputs."""
    from services.first_person_pipeline import FirstPersonPipeline

    pipeline = FirstPersonPipeline.__new__(FirstPersonPipeline)
    pipeline._store = type("S", (), {"collection": "first_person_v8"})()
    pipeline._collection_contract_cache = None
    pipeline._boundary_guard_enabled = False
    pipeline._content_quality_gate_enabled = False
    components = pipeline._serving_policy_components("allow", "block")
    for key in (
        "legacy_collection",
        "legacy_schema",
        "legacy_corpus_version",
        "evidence_policy",
    ):
        assert key in components, key
    assert components["legacy_collection"] == "first_person_v8"


# ---------------------------------------------------------------------------
# fail-closed behaviour
# ---------------------------------------------------------------------------
def test_production_stops_the_process_on_any_violation():
    report = validate_serving_contract(
        contract={}, legacy_collection="first_person_v99", context_collection=""
    )
    with pytest.raises(FirstPersonServingContractError):
        assert_startup_safe(
            report,
            is_production=True,
            legacy_route_enabled=True,
            context_harness_enabled=False,
        )


def test_context_harness_enabled_stops_the_process_on_a_context_violation():
    contract = {"legacy_only": _entry({}, "legacy_only", LEGACY_SCHEMA, contract_mod.ROLE_LEGACY)}
    report = validate_serving_contract(
        contract=contract,
        legacy_collection="legacy_only",
        context_collection="legacy_only",
        context_harness_enabled=True,
    )
    with pytest.raises(FirstPersonServingContractError):
        assert_startup_safe(
            report,
            is_production=False,
            legacy_route_enabled=True,
            context_harness_enabled=True,
        )


def test_legacy_path_fails_closed_at_request_time_outside_production():
    """The legacy path refuses to serve; the application keeps running."""
    contract = {
        "fp_context_v1": _entry({}, "fp_context_v1", CONTEXT_SCHEMA, contract_mod.ROLE_CONTEXT)
    }
    report = validate_serving_contract(
        contract=contract, legacy_collection="fp_context_v1", context_collection=""
    )
    assert not report.ok
    assert_startup_safe(
        report,
        is_production=False,
        legacy_route_enabled=True,
        context_harness_enabled=False,
    )
    preflight = legacy_store_preflight(contract=contract, legacy_collection="fp_context_v1")
    assert not preflight.ok
    with pytest.raises(FirstPersonServingContractError):
        preflight.raise_if_unsafe()


def test_legacy_preflight_is_clean_for_a_legacy_collection():
    contract = {
        "first_person_v8": _entry({}, "first_person_v8", LEGACY_SCHEMA, contract_mod.ROLE_LEGACY)
    }
    preflight = legacy_store_preflight(contract=contract, legacy_collection="first_person_v8")
    assert preflight.ok


def test_pipeline_reports_the_contract_violation_instead_of_serving():
    """The pipeline must not serve a clip through a mismatched collection."""
    from services import first_person_pipeline as pipeline_mod
    from services.first_person_store import FirstPersonStore

    pipeline = pipeline_mod.FirstPersonPipeline.__new__(pipeline_mod.FirstPersonPipeline)
    pipeline._store = FirstPersonStore.__new__(FirstPersonStore)
    pipeline._store._collection = "first_person_v10"
    pipeline._collection_contract_cache = None
    pipeline._serving_contract_error_cache = pipeline_mod._CONTRACT_UNSET
    error = pipeline._serving_contract_error()
    assert error
    assert "fp-context collection" in error


def test_a_test_double_store_is_not_gated():
    """A stand-in store cannot read a real collection, so it is not gated."""
    from services import first_person_pipeline as pipeline_mod

    pipeline = pipeline_mod.FirstPersonPipeline.__new__(pipeline_mod.FirstPersonPipeline)
    pipeline._store = type("S", (), {"collection": "t"})()
    pipeline._collection_contract_cache = None
    pipeline._serving_contract_error_cache = pipeline_mod._CONTRACT_UNSET
    assert pipeline._serving_contract_error() == ""
